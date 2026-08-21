"""Production-grade terminal input engine with prompt_toolkit, floating slash autocomplete & pinned status toolbar."""

from __future__ import annotations

import sys
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

from prompt_toolkit import PromptSession
from prompt_toolkit.completion import CompleteEvent, Completer, Completion
from prompt_toolkit.document import Document
from prompt_toolkit.formatted_text import HTML, AnyFormattedText
from prompt_toolkit.history import FileHistory
from prompt_toolkit.key_binding import KeyBindings, KeyPressEvent
from prompt_toolkit.shortcuts import CompleteStyle
from prompt_toolkit.styles import Style

COMMAND_HINTS: list[tuple[str, str]] = [
    ("/help", "Show command menu, shortcuts & tools (alias: /?)"),
    ("/login", "Authenticate AI provider via API key or Auth (alias: /auth)"),
    ("/logout", "Remove stored credentials & sign out (alias: /signout)"),
    ("/model", "Switch active LLM scoped to authenticated providers (alias: /llm)"),
    ("/profile", "Switch agent persona (coding, architect, minimal)"),
    ("/diff", "View git diff of session modifications (alias: /changes)"),
    ("/cost", "Show session tokens & USD cost (alias: /stats, /tokens)"),
    ("/compact", "Trigger context window compaction (alias: /compress)"),
    ("/sessions", "List saved session trees (alias: /history)"),
    ("/tree", "Explore and fork session conversation branch (alias: /branch)"),
    ("/inspect", "Open post-turn detail audit viewer & diffs (alias: /logs)"),
    ("/thinking", "Toggle model reasoning trace visibility (alias: /trace)"),
    ("/stop", "Halt the active running agent turn (alias: /abort)"),
    ("/init", "Inspect repository context & AGENTS.md (alias: /bootstrap)"),
    ("/clear", "Clear terminal screen and redraw banner (alias: /cls)"),
    ("/quit", "Save session tree and exit cleanly (alias: /exit)"),
]

MIA_STYLE = Style.from_dict(
    {
        "prompt": "bold #FF7A00",
        "completion-menu": "bg:#282C34 #E5E7EB",
        "completion-menu.completion": "bg:#282C34 #E5E7EB",
        "completion-menu.completion.current": "bold bg:#FF7A00 #000000",
        "completion-menu.meta": "bg:#21252B #9CA3AF italic",
        "completion-menu.meta.completion.current": "bold bg:#FF7A00 #202020",
        "bottom-toolbar": "bg:#161922 #9CA3AF",
        "bottom-toolbar.accent": "bold #FF7A00",
        "bottom-toolbar.dim": "#6B7280",
    }
)


class SlashCompleter(Completer):
    """Dynamic floating completer for slash commands in prompt_toolkit."""

    def __init__(self, commands: list[tuple[str, str]] | None = None) -> None:
        self.commands = commands or COMMAND_HINTS

    def get_completions(
        self, document: Document, complete_event: CompleteEvent
    ) -> Iterable[Completion]:
        text = document.text_before_cursor
        line = text.lstrip()
        if not line.startswith("/"):
            return

        parts = line.split()
        if len(parts) > 1 and not line.endswith(" "):
            return

        query = parts[0].lower() if parts else "/"
        for cmd, desc in self.commands:
            if cmd.lower().startswith(query):
                yield Completion(
                    cmd,
                    start_position=-len(query),
                    display=cmd,
                    display_meta=desc,
                )


def format_status_toolbar(
    workspace_name: str = "mia",
    model_name: str = "mimo-v2.5",
    tokens: int = 0,
    window_tokens: int = 128000,
    thinking_enabled: bool = False,
) -> HTML:
    """Render a clean, 1-line pinned status toolbar below the prompt."""
    pct = (tokens / max(1, window_tokens)) * 100
    pct_str = f"{pct:.1f}%" if tokens > 0 else "0%"
    tokens_str = f"{tokens / 1000:.1f}k" if tokens >= 1000 else str(tokens)
    window_str = f"{window_tokens // 1000}k" if window_tokens >= 1000 else str(window_tokens)

    thinking_badge = (
        " <style fg='#FF7A00'>[💭 thinking: on]</style>"
        if thinking_enabled
        else " <style fg='#6B7280'>[💭 thinking: off]</style>"
    )

    return HTML(
        f"<b>📁 {workspace_name}</b> │ "
        f"<b>🧠 {model_name}</b> │ "
        f"⚡ {tokens_str}/{window_str} ({pct_str}){thinking_badge} │ "
        f"<style fg='#9CA3AF'><b>Esc:</b> Tree • <b>Ctrl+O:</b> Logs • <b>/help</b></style>"
    )


class LivePromptSession:
    """Production prompt_toolkit session managing floating slash autocompletion, keybindings, and persistent history."""

    def __init__(
        self,
        history_file: Path | None = None,
        toolbar_callback: Callable[[], AnyFormattedText] | None = None,
    ) -> None:
        self.history_file = history_file or (Path.home() / ".mia" / "history")
        self.history_file.parent.mkdir(parents=True, exist_ok=True)
        self.history = FileHistory(str(self.history_file))
        self.toolbar_callback = toolbar_callback
        self.completer = SlashCompleter()
        self.bindings = self._create_keybindings()
        self.session: PromptSession[str] = PromptSession(
            history=self.history,
            completer=self.completer,
            key_bindings=self.bindings,
            style=MIA_STYLE,
            complete_while_typing=True,
            complete_style=CompleteStyle.COLUMN,
            reserve_space_for_menu=8,
        )

    def _create_keybindings(self) -> KeyBindings:
        kb = KeyBindings()

        # Ctrl+C: Clear active input buffer without killing session
        @kb.add("c-c")
        def _clear_buffer(event: KeyPressEvent) -> None:
            event.current_buffer.reset()

        # Ctrl+J / Alt+Enter: Insert newline for multi-line prompts
        @kb.add("c-j")
        def _insert_newline(event: KeyPressEvent) -> None:
            event.current_buffer.insert_text("\n")

        @kb.add("escape", "enter")
        def _insert_newline_alt(event: KeyPressEvent) -> None:
            event.current_buffer.insert_text("\n")

        # Esc: Session tree navigator shortcut
        @kb.add("escape")
        def _tree_shortcut(event: KeyPressEvent) -> None:
            event.current_buffer.text = "/tree"
            event.current_buffer.validate_and_handle()

        # Ctrl+O: Post-turn detail audit inspector shortcut
        @kb.add("c-o")
        def _inspect_shortcut(event: KeyPressEvent) -> None:
            event.current_buffer.text = "/inspect"
            event.current_buffer.validate_and_handle()

        # Ctrl+T: Toggle thinking trace shortcut
        @kb.add("c-t")
        def _thinking_shortcut(event: KeyPressEvent) -> None:
            event.current_buffer.text = "/thinking"
            event.current_buffer.validate_and_handle()

        return kb

    async def read_prompt_async(
        self,
        prompt_prefix: str = "🥕 mia › ",
        bottom_toolbar: Any = None,
    ) -> str:
        """Async prompt user with floating slash completions, bracketed paste, and pinned bottom toolbar."""
        if not sys.stdin.isatty():
            try:
                return input(prompt_prefix).strip()
            except EOFError:
                raise

        toolbar = bottom_toolbar or (self.toolbar_callback() if self.toolbar_callback else None)
        formatted_prompt: AnyFormattedText = [("class:prompt", prompt_prefix)]

        try:
            result = await self.session.prompt_async(
                formatted_prompt,
                bottom_toolbar=toolbar,
                reserve_space_for_menu=6,
            )
            return result.strip()
        except KeyboardInterrupt:
            # Handle empty Ctrl+C
            return ""
        except EOFError:
            raise

    def read_prompt(
        self,
        prompt_prefix: str = "🥕 mia › ",
        bottom_toolbar: Any = None,
    ) -> str:
        """Prompt user with floating slash completions, bracketed paste, and pinned bottom toolbar."""
        if not sys.stdin.isatty():
            try:
                return input(prompt_prefix).strip()
            except EOFError:
                raise

        toolbar = bottom_toolbar or (self.toolbar_callback() if self.toolbar_callback else None)
        formatted_prompt: AnyFormattedText = [("class:prompt", prompt_prefix)]

        try:
            result = self.session.prompt(
                formatted_prompt,
                bottom_toolbar=toolbar,
                reserve_space_for_menu=6,
            )
            return result.strip()
        except KeyboardInterrupt:
            # Handle empty Ctrl+C
            return ""
        except EOFError:
            raise


class LiveInteractivePrompt:
    """Backward-compatible adapter for LivePromptSession."""

    def __init__(self, history_file: Path | None = None) -> None:
        self._session = LivePromptSession(history_file=history_file)

    async def read_prompt_async(self, prompt_prefix: str = "🥕 mia › ") -> str:
        return await self._session.read_prompt_async(prompt_prefix)

    def read_prompt(self, prompt_prefix: str = "🥕 mia › ") -> str:
        return self._session.read_prompt(prompt_prefix)


def interactive_select(
    title: str,
    options: list[tuple[str, str, str]],  # (id, label, description)
    default_idx: int = 0,
) -> str | None:
    """Clean interactive selection menu supporting both instant numeric keys (1..N) and arrow keys (Up/Down + Enter).

    Guarantees zero-flicker stability and clean terminal restoration.
    """
    if not options:
        return None

    num_options = len(options)
    default_idx = max(0, min(default_idx, num_options - 1))

    if not sys.stdin.isatty():
        try:
            prompt_str = f"{title} [1-{num_options}] (default: {default_idx + 1}): "
            raw = input(prompt_str).strip()
            if not raw:
                return options[default_idx][0]
            if raw.isdigit() and 1 <= int(raw) <= num_options:
                return options[int(raw) - 1][0]
            for opt in options:
                if raw.lower() == opt[0].lower() or raw.lower() == opt[1].lower():
                    return opt[0]
            return options[default_idx][0]
        except (KeyboardInterrupt, EOFError):
            return None

    import termios
    import tty

    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)

    current_idx = default_idx

    # Print Title Header
    sys.stdout.write(
        f"\n\x1b[1;38;2;255;122;0m🥕 {title}\x1b[0m \x1b[2;37m(Press 1-{num_options}, or use ↑/↓ + Enter)\x1b[0m\n"
    )
    sys.stdout.write("\x1b[38;2;45;51;66m" + "─" * 68 + "\x1b[0m\n")

    def render_all(selected_idx: int) -> None:
        for i, (_id, label, desc) in enumerate(options):
            num_prefix = f" {i + 1}. "
            if i == selected_idx:
                cursor = "🥕 "
                line_str = f"\x1b[1;38;2;255;122;0m{num_prefix}{label:<18}\x1b[0m \x1b[2m│\x1b[0m \x1b[38;2;243;244;246m{desc}\x1b[0m"
            else:
                cursor = "   "
                line_str = f"\x1b[38;2;156;163;175m{num_prefix}{label:<18}\x1b[0m \x1b[2m│\x1b[0m \x1b[2;37m{desc}\x1b[0m"
            sys.stdout.write(f"\r\x1b[K{cursor}{line_str}\n")
        sys.stdout.flush()

    try:
        tty.setcbreak(fd)
        render_all(current_idx)

        while True:
            char = sys.stdin.read(1)

            # Ctrl+C or Ctrl+D
            if char in ("\x03", "\x04"):
                sys.stdout.write("\n")
                raise KeyboardInterrupt

            # Enter
            if char in ("\r", "\n"):
                sys.stdout.write(f"\n\x1b[1;32m✓ Selected: {options[current_idx][1]}\x1b[0m\n\n")
                sys.stdout.flush()
                return options[current_idx][0]

            # Direct single-number key entry (1..9)
            if char.isdigit():
                num = int(char)
                if 1 <= num <= num_options:
                    current_idx = num - 1
                    sys.stdout.write(
                        f"\n\x1b[1;32m✓ Selected: {options[current_idx][1]}\x1b[0m\n\n"
                    )
                    sys.stdout.flush()
                    return options[current_idx][0]

            # ANSI Arrow Navigation
            if char == "\x1b":
                seq1 = sys.stdin.read(1)
                if seq1 == "[":
                    seq2 = sys.stdin.read(1)
                    if seq2 == "A":  # Up Arrow
                        current_idx = (current_idx - 1) % num_options
                        sys.stdout.write(f"\x1b[{num_options}A")
                        render_all(current_idx)
                    elif seq2 == "B":  # Down Arrow
                        current_idx = (current_idx + 1) % num_options
                        sys.stdout.write(f"\x1b[{num_options}A")
                        render_all(current_idx)

    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
