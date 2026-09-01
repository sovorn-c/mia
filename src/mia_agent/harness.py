"""Headless agent loop harness coordinating turns, steps, and tool execution."""

from __future__ import annotations

import time
from collections.abc import AsyncIterator, Callable, Sequence
from dataclasses import dataclass
from typing import Any

from mia_agent.events import (
    AgentErrorEvent,
    AgentEvent,
    AssistantChunkEvent,
    StepEndEvent,
    StepStartEvent,
    ToolCallEvent,
    ToolResultEvent,
    TurnCompleteEvent,
    TurnStartEvent,
)
from mia_agent.session.compactor import (
    ContextCompactor,
    estimate_chat_messages_tokens,
)
from mia_agent.session.entries import CompactionEntry, LeafEntry, MessageEntry
from mia_agent.session.jsonl import JsonlSessionStore
from mia_agent.session.tree import SessionTree
from mia_ai.providers.base import LLMProvider
from mia_ai.types import ChatMessage, TokenUsage, ToolCall, ToolDefinition
from mia_middleware.access import sanitize_arguments
from mia_middleware.pipeline import ToolCallContext, ToolPipeline


@dataclass(frozen=True, slots=True)
class CompactionResult:
    """Estimated outcome of an explicit context compaction."""

    before_tokens: int
    after_tokens: int
    summary: str


class AgentHarness:
    """Headless agent loop that drives multi-turn, multi-step LLM interactions."""

    def __init__(
        self,
        *,
        provider: LLMProvider,
        model: str,
        system_prompt: str = "You are Mia, an expert AI software engineer.",
        tools: Sequence[Any] | None = None,
        tool_executor: Callable[[str, dict[str, Any]], Any] | None = None,
        pipeline: ToolPipeline | None = None,
        max_steps_per_turn: int = 25,
        session_id: str = "default",
        messages: Sequence[ChatMessage] | None = None,
        session_store: JsonlSessionStore | None = None,
        compactor: ContextCompactor | None = None,
        last_entry_id: str | None = None,
        tool_context_metadata: dict[str, Any] | None = None,
    ) -> None:
        self.provider = provider
        self.model = model
        self.system_prompt = system_prompt
        self.tools = list(tools or [])
        self.tool_executor = tool_executor
        self.pipeline = pipeline
        self.max_steps_per_turn = max_steps_per_turn
        self.session_id = session_id
        self._messages: list[ChatMessage] = list(messages or [])
        self.session_store = session_store
        self.compactor = compactor
        self._last_entry_id = last_entry_id
        self.tool_context_metadata = dict(tool_context_metadata or {})
        self._turn_counter = 0
        self._current_step = 0

    @property
    def messages(self) -> list[ChatMessage]:
        """Return the current conversation history."""
        return list(self._messages)

    def append_message(self, message: ChatMessage) -> None:
        """Append a message to the history."""
        self._messages.append(message)

    def clear_history(self) -> None:
        """Clear all conversation history."""
        self._messages.clear()

    def compact_context(self) -> CompactionResult | None:
        """Compact active context and append a durable session checkpoint when configured."""
        if self.compactor is None or not self._messages:
            return None

        before_tokens = estimate_chat_messages_tokens(self._messages)
        compacted_messages, summary_text = self.compactor.compact_messages(self._messages)
        self._messages = compacted_messages

        if self.session_store:
            compaction_entry = CompactionEntry(
                parent_id=self._last_entry_id,
                summary=summary_text,
            )
            self.session_store.append_entry(compaction_entry)
            self._last_entry_id = compaction_entry.id
            self.session_store.append_entry(LeafEntry(entry_id=compaction_entry.id))

        return CompactionResult(
            before_tokens=before_tokens,
            after_tokens=estimate_chat_messages_tokens(self._messages),
            summary=summary_text,
        )

    def navigate_to(self, entry_id: str) -> list[ChatMessage]:
        """Move the active branch to an existing entry without rewriting session history."""
        if self.session_store is None:
            raise ValueError("Session navigation requires a session store")

        tree = SessionTree(self.session_store.load_entries())
        target = tree.get_entry(entry_id)
        if target is None:
            raise ValueError(f"Session entry not found: {entry_id}")

        path = tree.get_path_to_entry(entry_id)
        self._messages = tree.extract_messages_from_path(path)
        self._last_entry_id = entry_id
        self.session_store.append_entry(LeafEntry(entry_id=entry_id))
        return self.messages

    def _get_tool_definitions(self) -> list[ToolDefinition]:
        """Extract ToolDefinitions from registered tool objects."""
        definitions: list[ToolDefinition] = []
        for t in self.tools:
            if hasattr(t, "to_tool_definition"):
                definitions.append(t.to_tool_definition())
            elif isinstance(t, ToolDefinition):
                definitions.append(t)
            elif hasattr(t, "name") and hasattr(t, "description") and hasattr(t, "parameters"):
                definitions.append(
                    ToolDefinition(
                        name=t.name,
                        description=t.description,
                        parameters=t.parameters,
                    )
                )
        return definitions

    async def _execute_tool_core(self, tool_name: str, args: dict[str, Any]) -> Any:
        # 1. Check custom tool_executor
        if self.tool_executor:
            res = self.tool_executor(tool_name, args)
            if hasattr(res, "__await__"):
                return await res
            return res

        # 2. Check registered tool objects
        for tool in self.tools:
            name = getattr(tool, "name", None)
            if name == tool_name:
                execute_fn = getattr(tool, "execute", None) or (tool if callable(tool) else None)
                if execute_fn:
                    res = execute_fn(**args)
                    if hasattr(res, "__await__"):
                        return await res
                    return res

        raise ValueError(f"Tool '{tool_name}' not found in registered tools.")

    async def _execute_tool(self, call_id: str, tool_name: str, args: dict[str, Any]) -> Any:
        """Dispatch a single tool call through pipeline (if present) to the matching tool handler."""
        if self.pipeline:
            ctx = ToolCallContext(
                session_id=self.session_id,
                step_index=self._current_step,
                call_id=call_id,
                tool_name=tool_name,
                arguments=args,
                metadata=dict(self.tool_context_metadata),
            )
            return await self.pipeline.execute(
                ctx,
                lambda: self._execute_tool_core(tool_name, ctx.arguments),
            )
        return await self._execute_tool_core(tool_name, args)

    async def prompt(self, user_text: str) -> AsyncIterator[AgentEvent]:
        """Run a full turn for the given user prompt."""
        self._turn_counter += 1
        yield TurnStartEvent(turn_index=self._turn_counter, user_prompt=user_text)

        # 1. Context compaction if threshold exceeded
        if self.compactor and self.compactor.should_compact(self._messages):
            compacted_msgs, summary_text = self.compactor.compact_messages(self._messages)
            self._messages = compacted_msgs
            if self.session_store:
                c_entry = CompactionEntry(parent_id=self._last_entry_id, summary=summary_text)
                self.session_store.append_entry(c_entry)
                self._last_entry_id = c_entry.id

        # 2. Append user message to history & session store
        user_msg = ChatMessage(role="user", content=user_text)
        self._messages.append(user_msg)
        if self.session_store:
            u_entry = MessageEntry(parent_id=self._last_entry_id, message=user_msg)
            self.session_store.append_entry(u_entry)
            self._last_entry_id = u_entry.id

        tool_defs = self._get_tool_definitions()
        step_index = 0
        total_cost = 0.0

        while step_index < self.max_steps_per_turn:
            step_index += 1
            self._current_step = step_index
            yield StepStartEvent(step_index=step_index)

            accumulated_text: list[str] = []
            tool_calls: list[ToolCall] = []
            step_usage = TokenUsage()
            finish_reason: str | None = None
            provider_error: str | None = None

            # Stream from LLM
            async for chunk in self.provider.stream(
                model=self.model,
                messages=self._messages,
                tools=tool_defs if tool_defs else None,
                system=self.system_prompt,
            ):
                if chunk.type == "text_delta" and chunk.delta:
                    accumulated_text.append(chunk.delta)
                    yield AssistantChunkEvent(delta_text=chunk.delta)
                elif chunk.type == "thought_delta" and chunk.thought:
                    yield AssistantChunkEvent(thought_delta=chunk.thought)
                elif chunk.type == "tool_call_end" and chunk.tool_call:
                    tool_calls.append(chunk.tool_call)
                elif chunk.type == "error":
                    error_msg = str(sanitize_arguments(chunk.error or "Unknown provider error"))
                    provider_error = error_msg
                    accumulated_text.append(f"\n[Error: {error_msg}]\n")
                    yield AssistantChunkEvent(delta_text=f"\n[Error: {error_msg}]\n")
                elif chunk.type == "finish":
                    finish_reason = chunk.finish_reason
                    if chunk.usage:
                        step_usage = chunk.usage
                        total_cost += chunk.usage.cost_usd

            assistant_text = "".join(accumulated_text)
            if provider_error is not None:
                yield AgentErrorEvent(error=provider_error, step_index=step_index)

            # Record assistant response in message history & session store
            asst_msg = ChatMessage(
                role="assistant",
                content=assistant_text,
                tool_calls=tool_calls if tool_calls else None,
            )
            self._messages.append(asst_msg)
            if self.session_store:
                a_entry = MessageEntry(parent_id=self._last_entry_id, message=asst_msg)
                self.session_store.append_entry(a_entry)
                self._last_entry_id = a_entry.id

            # If tool calls were made, execute them
            if tool_calls:
                for tc in tool_calls:
                    yield ToolCallEvent(
                        call_id=tc.id,
                        tool_name=tc.name,
                        arguments=tc.arguments,
                    )

                    start_time = time.perf_counter()
                    is_error = False
                    try:
                        result = await self._execute_tool(tc.id, tc.name, tc.arguments)
                    except Exception as exc:
                        result = f"Error executing {tc.name}: {exc}"
                        is_error = True
                    duration_ms = (time.perf_counter() - start_time) * 1000.0

                    yield ToolResultEvent(
                        call_id=tc.id,
                        tool_name=tc.name,
                        output=result,
                        is_error=is_error,
                        duration_ms=duration_ms,
                    )

                    # Append tool result to messages & session store
                    tool_msg = ChatMessage(
                        role="tool",
                        tool_call_id=tc.id,
                        tool_name=tc.name,
                        content=str(result) if not isinstance(result, str) else result,
                    )
                    self._messages.append(tool_msg)
                    if self.session_store:
                        t_entry = MessageEntry(parent_id=self._last_entry_id, message=tool_msg)
                        self.session_store.append_entry(t_entry)
                        self._last_entry_id = t_entry.id

            yield StepEndEvent(
                step_index=step_index,
                input_tokens=step_usage.input_tokens,
                output_tokens=step_usage.output_tokens,
            )

            # If no tool calls were requested or stop reason is "stop", we are done
            if not tool_calls or finish_reason == "stop":
                if self.session_store and self._last_entry_id:
                    self.session_store.append_entry(LeafEntry(entry_id=self._last_entry_id))
                yield TurnCompleteEvent(
                    total_steps=step_index,
                    total_cost_usd=total_cost,
                    stop_reason="stop",
                )
                return

        # If loop exited due to max steps
        if self.session_store and self._last_entry_id:
            self.session_store.append_entry(LeafEntry(entry_id=self._last_entry_id))
        yield TurnCompleteEvent(
            total_steps=step_index,
            total_cost_usd=total_cost,
            stop_reason="max_steps",
        )
