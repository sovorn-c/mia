"""Context window estimation and structured conversation compaction."""

from __future__ import annotations

import json

from mia_ai.types import ChatMessage, ToolCall

CHARS_PER_TOKEN = 4
MESSAGE_OVERHEAD_TOKENS = 4
DEFAULT_CONTEXT_WINDOW_TOKENS = 128_000
DEFAULT_COMPACTION_THRESHOLD_RATIO = 0.8
DEFAULT_KEEP_RECENT_TOKENS = 16_000

COMPACTION_SUMMARY_PREFIX = "Previous conversation summary:\n"


def estimate_text_tokens(text: str) -> int:
    """Estimate token count from a raw string (roughly 4 characters per token)."""
    if not text:
        return 0
    return max(1, (len(text) + CHARS_PER_TOKEN - 1) // CHARS_PER_TOKEN)


def estimate_tool_call_tokens(tc: ToolCall) -> int:
    """Estimate token count for a tool invocation call."""
    raw = f"{tc.name}:{json.dumps(tc.arguments)}"
    return estimate_text_tokens(raw) + 8


def estimate_chat_message_tokens(message: ChatMessage) -> int:
    """Estimate token count for a single ChatMessage."""
    tokens = MESSAGE_OVERHEAD_TOKENS
    if isinstance(message.content, str):
        tokens += estimate_text_tokens(message.content)
    elif isinstance(message.content, list):
        tokens += estimate_text_tokens(json.dumps(message.content))

    if message.tool_calls:
        for tc in message.tool_calls:
            tokens += estimate_tool_call_tokens(tc)

    return tokens


def estimate_chat_messages_tokens(messages: list[ChatMessage]) -> int:
    """Estimate total token count across a sequence of messages."""
    return sum(estimate_chat_message_tokens(m) for m in messages)


class ContextCompactor:
    """Evaluates context capacity and applies structured summarization at 80% threshold."""

    def __init__(
        self,
        context_window_tokens: int = DEFAULT_CONTEXT_WINDOW_TOKENS,
        compaction_threshold_ratio: float = DEFAULT_COMPACTION_THRESHOLD_RATIO,
        keep_recent_tokens: int = DEFAULT_KEEP_RECENT_TOKENS,
    ) -> None:
        self.context_window_tokens = context_window_tokens
        self.compaction_threshold_ratio = compaction_threshold_ratio
        self.keep_recent_tokens = keep_recent_tokens

    @property
    def threshold_tokens(self) -> int:
        """The token threshold that triggers compaction."""
        return int(self.context_window_tokens * self.compaction_threshold_ratio)

    def should_compact(self, messages: list[ChatMessage]) -> bool:
        """Check if active messages exceed the 80% context window threshold."""
        total_tokens = estimate_chat_messages_tokens(messages)
        return total_tokens >= self.threshold_tokens

    def compact_messages(
        self,
        messages: list[ChatMessage],
        custom_instructions: str | None = None,
    ) -> tuple[list[ChatMessage], str]:
        """Split messages into older prefix and recent suffix, then produce a compacted message list.

        Returns (compacted_messages, structured_summary).
        """
        if not messages:
            return [], "No prior messages to compact."

        # Find suffix to keep
        accumulated_tokens = 0
        split_index = len(messages)

        for idx in range(len(messages) - 1, -1, -1):
            msg_tokens = estimate_chat_message_tokens(messages[idx])
            if (
                accumulated_tokens + msg_tokens > self.keep_recent_tokens
                and idx < len(messages) - 1
            ):
                split_index = idx + 1
                break
            accumulated_tokens += msg_tokens
            split_index = idx

        # Ensure we always compact at least some prefix if messages > 2
        if split_index == 0 and len(messages) > 2:
            split_index = max(1, len(messages) // 2)

        prefix_messages = messages[:split_index]
        suffix_messages = messages[split_index:]

        # Build structured summary from prefix
        summary_text = self._build_structured_summary(prefix_messages, custom_instructions)

        summary_msg = ChatMessage(
            role="user",
            content=f"{COMPACTION_SUMMARY_PREFIX}{summary_text}",
        )

        compacted = [summary_msg] + suffix_messages
        return compacted, summary_text

    def _build_structured_summary(
        self,
        messages: list[ChatMessage],
        custom_instructions: str | None = None,
    ) -> str:
        """Generate structured checkpoint summary."""
        goals: list[str] = []
        done_items: list[str] = []
        decisions: list[str] = []

        for msg in messages:
            if msg.role == "user" and isinstance(msg.content, str):
                first_line = msg.content.strip().split("\n")[0][:100]
                if not first_line.startswith("Previous conversation summary:"):
                    goals.append(first_line)
            elif msg.role == "tool" and msg.tool_name:
                done_items.append(f"Executed tool `{msg.tool_name}` (Call ID: {msg.tool_call_id})")
            elif msg.role == "assistant" and isinstance(msg.content, str) and msg.content:
                first_line = msg.content.strip().split("\n")[0][:100]
                if first_line:
                    decisions.append(first_line)

        goal_str = "\n".join(f"- {g}" for g in goals[:3]) if goals else "- General assistance"
        done_str = "\n".join(f"- [x] {d}" for d in done_items[:5]) if done_items else "- [x] Setup"
        decision_str = (
            "\n".join(f"- **Note**: {d}" for d in decisions[:3])
            if decisions
            else "- **Decision**: Followed standard implementation plan."
        )

        custom_note = f"\n\n## Custom Context\n{custom_instructions}" if custom_instructions else ""

        return (
            f"## Goal\n{goal_str}\n\n"
            f"## Constraints & Preferences\n- Preserved session context\n\n"
            f"## Progress\n### Done\n{done_str}\n\n"
            f"### In Progress\n- Continuing current turn execution\n\n"
            f"## Key Decisions\n{decision_str}\n\n"
            f"## Next Steps\n1. Continue with remaining tasks{custom_note}"
        )
