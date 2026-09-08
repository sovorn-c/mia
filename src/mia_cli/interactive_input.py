"""Production-grade terminal input engine with prompt_toolkit, floating slash autocomplete & pinned status toolbar."""

from __future__ import annotations

import asyncio
import contextlib
import sys
import time
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

from prompt_toolkit.completion import CompleteEvent, Completer, Completion
from prompt_toolkit.document import Document
from prompt_toolkit.formatted_text import HTML, AnyFormattedText
from prompt_toolkit.history import FileHistory, History, InMemoryHistory
from prompt_toolkit.key_binding import KeyBindings, KeyPressEvent
from prompt_toolkit.shortcuts import PromptSession
from prompt_toolkit.styles import Style

COMMAND_HINTS: list[tuple[str, str]] = [
    ("/help", "Show the command menu and aliases (alias: /?)"),
    ("/login", "Authenticate an AI provider (alias: /auth)"),
    ("/logout", "Remove stored credentials (alias: /signout)"),
    ("/model", "Switch the active model (alias: /llm)"),
    ("/scoped-models", "Discover and set models used by Ctrl+P cycling"),
    ("/agent", "Show or switch the active Agent"),
    ("/diff", "Show the Git diff or report Git errors (alias: /changes)"),
    ("/cost", "Show session token and cost totals (alias: /stats, /tokens)"),
    ("/compact", "Compact active context when history is available (alias: /compress)"),
    ("/sessions", "List saved session trees (alias: /history)"),
    ("/resume", "Resume or delete a saved session"),
    ("/tree", "Explore and fork the session tree (alias: /branch)"),
    ("/inspect", "Show post-turn audit details (alias: /logs)"),
    ("/thinking", "Toggle model reasoning trace visibility (alias: /trace)"),
    ("/init", "Check for basic repository context files (alias: /bootstrap)"),
    ("/clear", "Clear the terminal and redraw the banner (alias: /cls)"),
    ("/quit", "Save the session and exit (alias: /exit)"),
]

MIA_STYLE = Style.from_dict(
    {
        "prompt": "bold #FF7A00",
        "completion-menu": "bg:default #E5E7EB",
        "completion-menu.completion": "bg:default #9CA3AF",
        "completion-menu.completion.current": "bold bg:default #FF7A00",
        "completion-menu.meta": "bg:default #6B7280 italic",
        "completion-menu.meta.completion": "bg:default #6B7280 italic",
        "completion-menu.meta.completion.current": "bold bg:default #FF7A00 italic",
        "completion-menu.multi-column-meta": "bg:default #6B7280",
        "scrollbar": "bg:default",
        "scrollbar.background": "bg:default",
        "scrollbar.button": "bg:default #FF7A00",
        "bottom-toolbar": "noreverse bg:default #9CA3AF",
        "bottom-toolbar.text": "noreverse bg:default #9CA3AF",
        "bottom-toolbar.accent": "bold bg:default #FF7A00",
        "bottom-toolbar.dim": "bg:default #6B7280",
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


class SafeFileHistory(History):
    """Resilient FileHistory wrapper that gracefully falls back to in-memory on any permission/IO error."""

    def __init__(self, filename: str | None = None) -> None:
        super().__init__()
        self._delegate: History
        if filename:
            try:
                p = Path(filename)
                p.parent.mkdir(parents=True, exist_ok=True)
                if p.exists():
                    p.read_text(encoding="utf-8", errors="ignore")
                else:
                    p.touch(exist_ok=True)
                self._delegate = FileHistory(str(p))
            except Exception:
                self._delegate = InMemoryHistory()
        else:
            self._delegate = InMemoryHistory()

    def load_history_strings(self) -> Iterable[str]:
        try:
            return self._delegate.load_history_strings()
        except Exception:
            return []

    def store_string(self, string: str) -> None:
        with contextlib.suppress(Exception):
            self._delegate.store_string(string)


def format_status_toolbar(
    workspace_name: str = "mia",
    model_name: str = "mimo-v2.5",
    tokens: int = 0,
    window_tokens: int | None = None,
    thinking_enabled: bool = False,
    *,
    agent_id: str | None = None,
    session_id: str | None = None,
    run_state: str = "idle",
    width: int | None = None,
) -> HTML:
    """Render clean status info line below the prompt, adjusted with zero background."""
    tokens_str = f"{tokens / 1000:.1f}k" if tokens >= 1000 else str(tokens)
    if window_tokens is not None and window_tokens > 0:
        pct = (tokens / max(1, window_tokens)) * 100
        pct_str = f"{pct:.1f}%" if tokens > 0 else "0%"
        window_str = f"{window_tokens // 1000}k" if window_tokens >= 1000 else str(window_tokens)
        token_display = f"⚡ {tokens_str}/{window_str} ({pct_str})"
    else:
        token_display = f"⚡ {tokens_str}"

    if width is not None and width < 60:
        return HTML(
            f"<style fg='#9CA3AF'>📁 <b>{workspace_name}</b> │ 🧠 <b>{model_name}</b> │ "
            f"{token_display} │ <style fg='#FF7A00'>[{run_state}]</style></style>"
        )

    thinking_badge = (
        " <style fg='#FF7A00'>[💭 on]</style>"
        if thinking_enabled
        else " <style fg='#6B7280'>[💭 off]</style>"
    )

    agent_part = f"🤖 <b>{agent_id}</b> │ " if agent_id else ""
    session_part = f"🆔 <b>{session_id}</b> │ " if session_id else ""
    state_badge = f" <style fg='#FF7A00'>[{run_state}]</style> │" if run_state else ""

    return HTML(
        f"<style fg='#9CA3AF'>  📁 <b>{workspace_name}</b> │ "
        f"{agent_part}"
        f"🧠 <b>{model_name}</b> │ "
        f"{session_part}"
        f"{token_display}{thinking_badge} │"
        f"{state_badge} "
        f"<b>/help</b></style>"
    )


format_status_info = format_status_toolbar


class LivePromptSession:
    """Production prompt_toolkit session managing floating slash autocompletion, keybindings, and persistent history."""

    def __init__(
        self,
        history_file: Path | None = None,
        toolbar_callback: Callable[[], AnyFormattedText] | None = None,
        input: Any = None,
        output: Any = None,
    ) -> None:
        self.history_file = history_file or (Path.home() / ".mia" / "history")
        self.toolbar_callback = toolbar_callback
        self.history = SafeFileHistory(str(self.history_file))
        self.completer = SlashCompleter()
        self._last_escape_time = 0.0
        self.is_busy: bool = False
        self.draft_text: str = ""
        self.on_cancel_callback: Callable[[], None] | None = None
        self.bindings = self._create_keybindings()
        self.session: PromptSession[str] = PromptSession(
            history=self.history,
            completer=self.completer,
            key_bindings=self.bindings,
            style=MIA_STYLE,
            complete_while_typing=True,
            input=input,
            output=output,
            reserve_space_for_menu=8,
        )

    def get_draft(self) -> str:
        """Return the current draft text from the active buffer or stored draft."""
        with contextlib.suppress(Exception):
            if (
                hasattr(self.session, "app")
                and self.session.app
                and self.session.app.current_buffer
            ):
                text = self.session.app.current_buffer.text
                if text:
                    self.draft_text = text
        return self.draft_text

    def set_draft(self, text: str) -> None:
        """Set the draft text in storage and the active buffer if available."""
        self.draft_text = text
        with contextlib.suppress(Exception):
            if (
                hasattr(self.session, "app")
                and self.session.app
                and self.session.app.current_buffer
            ):
                self.session.app.current_buffer.text = text

    def restore_draft(self, text: str | None = None) -> None:
        """Restore draft text to active buffer or storage."""
        target = text if text is not None else self.draft_text
        self.set_draft(target)

    def _handle_escape(self, event: KeyPressEvent) -> None:
        """Apply Pi-style escape behavior to the current prompt buffer."""
        buffer = event.current_buffer
        if self.is_busy:
            if buffer.complete_state:
                buffer.cancel_completion()
            return
        if buffer.complete_state:
            buffer.cancel_completion()
            self._last_escape_time = 0.0
        elif buffer.text:
            buffer.reset()
            self._last_escape_time = 0.0
        else:
            now = time.monotonic()
            if now - self._last_escape_time <= 0.5:
                self._last_escape_time = 0.0
                buffer.text = "/tree"
                buffer.validate_and_handle()
            else:
                self._last_escape_time = now

    def _create_keybindings(self) -> KeyBindings:
        kb = KeyBindings()

        # Enter: Submit prompt when idle, block submission during an active Run without queueing
        @kb.add("enter")
        def _handle_enter(event: KeyPressEvent) -> None:
            if self.is_busy:
                if event.current_buffer.text:
                    self.draft_text = event.current_buffer.text
                return
            event.current_buffer.validate_and_handle()

        # Ctrl+C: Clear active input buffer when idle; signal cancel while busy without dropping draft
        @kb.add("c-c")
        def _clear_buffer(event: KeyPressEvent) -> None:
            if self.is_busy:
                if event.current_buffer.text:
                    self.draft_text = event.current_buffer.text
                if self.on_cancel_callback:
                    self.on_cancel_callback()
                return
            event.current_buffer.reset()
            self.draft_text = ""

        # Ctrl+J / Alt+Enter: Insert newline for multi-line prompts
        @kb.add("c-j")
        def _insert_newline(event: KeyPressEvent) -> None:
            event.current_buffer.insert_text("\n")

        @kb.add("escape", "enter")
        def _insert_newline_alt(event: KeyPressEvent) -> None:
            event.current_buffer.insert_text("\n")

        # Esc: cancel completion/clear input. Double-Esc on an empty editor opens /tree,
        # matching Pi's 500 ms guard against accidental tree navigation.
        @kb.add("escape")
        def _escape_handler(event: KeyPressEvent) -> None:
            self._handle_escape(event)

        # Pi-style model selection and scoped-model cycling.
        @kb.add("c-l")
        def _model_picker_shortcut(event: KeyPressEvent) -> None:
            if self.is_busy:
                return
            if event.current_buffer.text and not event.current_buffer.text.startswith("/"):
                self.draft_text = event.current_buffer.text
            event.current_buffer.text = "/model"
            event.current_buffer.validate_and_handle()

        @kb.add("c-p")
        def _model_cycle_shortcut(event: KeyPressEvent) -> None:
            if self.is_busy:
                return
            if event.current_buffer.text and not event.current_buffer.text.startswith("/"):
                self.draft_text = event.current_buffer.text
            event.current_buffer.text = "/model next"
            event.current_buffer.validate_and_handle()

        # Ctrl+O: Post-turn detail audit inspector shortcut
        @kb.add("c-o")
        def _inspect_shortcut(event: KeyPressEvent) -> None:
            if self.is_busy:
                return
            if event.current_buffer.text and not event.current_buffer.text.startswith("/"):
                self.draft_text = event.current_buffer.text
            event.current_buffer.text = "/inspect"
            event.current_buffer.validate_and_handle()

        # Shift+Tab is Pi's thinking shortcut. Ctrl+Tab is indistinguishable from Tab
        # in standard terminal input, so binding it would break completion.
        @kb.add("s-tab")
        def _thinking_cycle_shortcut(event: KeyPressEvent) -> None:
            if self.is_busy:
                return
            if event.current_buffer.text and not event.current_buffer.text.startswith("/"):
                self.draft_text = event.current_buffer.text
            event.current_buffer.text = "/thinking"
            event.current_buffer.validate_and_handle()

        # Ctrl+T: Toggle thinking trace shortcut
        @kb.add("c-t")
        def _thinking_shortcut(event: KeyPressEvent) -> None:
            if self.is_busy:
                return
            if event.current_buffer.text and not event.current_buffer.text.startswith("/"):
                self.draft_text = event.current_buffer.text
            event.current_buffer.text = "/thinking"
            event.current_buffer.validate_and_handle()

        return kb

    async def read_prompt_async(
        self,
        prompt_prefix: str = "› ",
        bottom_toolbar: Any = None,
    ) -> str:
        """Async prompt user with floating slash completions, bracketed paste, and inline status info immediately below."""
        if not sys.stdin.isatty() and not getattr(self.session, "_input", None):
            try:
                return input(prompt_prefix).strip()
            except KeyboardInterrupt:
                return ""
            except EOFError:
                raise

        formatted_prompt: AnyFormattedText = [("class:prompt", prompt_prefix)]
        active_toolbar = (
            bottom_toolbar
            if bottom_toolbar is not None
            else (self.toolbar_callback() if self.toolbar_callback else None)
        )

        try:
            default_text = self.draft_text or ""
            result = await self.session.prompt_async(
                formatted_prompt,
                bottom_toolbar=active_toolbar,
                default=default_text,
                reserve_space_for_menu=8,
            )
            if not self.is_busy:
                self.draft_text = ""
            return result.strip()
        except asyncio.CancelledError:
            self.get_draft()
            raise
        except KeyboardInterrupt:
            # Handle empty Ctrl+C
            return ""
        except EOFError:
            raise

    def read_prompt(
        self,
        prompt_prefix: str = "› ",
        bottom_toolbar: Any = None,
    ) -> str:
        """Prompt user with floating slash completions, bracketed paste, and inline status info immediately below."""
        if not sys.stdin.isatty() and not getattr(self.session, "_input", None):
            try:
                return input(prompt_prefix).strip()
            except KeyboardInterrupt:
                return ""
            except EOFError:
                raise

        formatted_prompt: AnyFormattedText = [("class:prompt", prompt_prefix)]
        active_toolbar = (
            bottom_toolbar
            if bottom_toolbar is not None
            else (self.toolbar_callback() if self.toolbar_callback else None)
        )

        try:
            default_text = self.draft_text or ""
            result = self.session.prompt(
                formatted_prompt,
                bottom_toolbar=active_toolbar,
                default=default_text,
                reserve_space_for_menu=8,
            )
            self.draft_text = ""
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

    async def read_prompt_async(self, prompt_prefix: str = "› ") -> str:
        return await self._session.read_prompt_async(prompt_prefix)

    def read_prompt(self, prompt_prefix: str = "› ") -> str:
        return self._session.read_prompt(prompt_prefix)


def interactive_multi_select(
    title: str,
    options: list[tuple[str, str, str]],
    selected_ids: Iterable[str] = (),
) -> list[str] | None:
    """Select multiple vertical options; Enter saves and Escape cancels."""
    if not options:
        return []

    option_ids = [option[0] for option in options]
    selected = set(selected_ids).intersection(option_ids)
    if not sys.stdin.isatty():
        try:
            raw = input(f"{title} (comma-separated numbers, Enter saves, Esc cancels): ").strip()
            if not raw:
                return None
            numbers = [int(value.strip()) for value in raw.split(",")]
            if not all(1 <= number <= len(options) for number in numbers):
                return None
            return [options[number - 1][0] for number in numbers]
        except (ValueError, KeyboardInterrupt, EOFError, OSError):
            return None

    import os
    import select
    import shutil
    import termios
    import tty

    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    current_idx = 0
    terminal_lines = shutil.get_terminal_size((80, 24)).lines
    viewport_size = max(1, min(len(options), terminal_lines - 4))
    window_start = 0

    sys.stdout.write(
        f"\n\x1b[1;38;2;255;122;0m🥕 {title}\x1b[0m "
        "\x1b[2;37m(Space toggle, ↑/↓ move, Enter save, Esc cancel)\x1b[0m\n"
    )
    sys.stdout.write("\x1b[38;2;45;51;66m" + "─" * 68 + "\x1b[0m\n")

    def keep_current_visible() -> None:
        nonlocal window_start
        if current_idx < window_start:
            window_start = current_idx
        elif current_idx >= window_start + viewport_size:
            window_start = current_idx - viewport_size + 1

    def render() -> None:
        end = min(window_start + viewport_size, len(options))
        for index in range(window_start, end):
            option_id, label, desc = options[index]
            marker = "[x]" if option_id in selected else "[ ]"
            cursor = "🥕 " if index == current_idx else "   "
            color = "1;38;2;255;122;0m" if index == current_idx else "38;2;156;163;175m"
            suffix = f" \x1b[2m│\x1b[0m {desc}" if desc else ""
            sys.stdout.write(f"\r\x1b[K{cursor}\x1b[{color}{marker} {label}\x1b[0m{suffix}\n")
        sys.stdout.flush()

    def read_key() -> bytes:
        key = os.read(fd, 1)
        if key != b"\x1b":
            return key
        readable, _, _ = select.select([fd], [], [], 0.05)
        if not readable:
            return key
        prefix = os.read(fd, 1)
        if prefix not in (b"[", b"O"):
            return key
        readable, _, _ = select.select([fd], [], [], 0.05)
        if not readable:
            return key
        return key + prefix + os.read(fd, 1)

    try:
        tty.setcbreak(fd)
        render()
        while True:
            raw_bytes = read_key()
            if not raw_bytes:
                continue
            if raw_bytes == b"\x1b":
                sys.stdout.write("\n\x1b[2;37m(Selection cancelled)\x1b[0m\n\n")
                return None
            if raw_bytes == b"\x03":
                raise KeyboardInterrupt
            if raw_bytes in (b"\x1b[A", b"\x1bOA"):
                current_idx = (current_idx - 1) % len(options)
            elif raw_bytes in (b"\x1b[B", b"\x1bOB"):
                current_idx = (current_idx + 1) % len(options)
            elif raw_bytes == b" ":
                option_id = options[current_idx][0]
                if option_id in selected:
                    selected.remove(option_id)
                else:
                    selected.add(option_id)
            elif raw_bytes == b"\x01":
                selected = set(option_ids)
            elif raw_bytes == b"\x18":
                selected.clear()
            elif raw_bytes in (b"\r", b"\n"):
                return [option_id for option_id in option_ids if option_id in selected]
            else:
                continue
            keep_current_visible()
            sys.stdout.write(f"\x1b[{viewport_size}A")
            render()
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)


def interactive_select(
    title: str,
    options: list[tuple[str, str, str]],  # (id, label, description)
    default_idx: int = 0,
    on_delete: Callable[[str], None] | None = None,
) -> str | None:
    """Select an option, optionally supporting confirmed Ctrl+D/d deletion."""
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
            if raw.lower() in ("0", "q", "quit", "cancel", "esc"):
                return None
            if raw.isdigit() and 1 <= int(raw) <= num_options:
                return options[int(raw) - 1][0]
            for opt in options:
                if raw.lower() == opt[0].lower() or raw.lower() == opt[1].lower():
                    return opt[0]
            return options[default_idx][0]
        except (KeyboardInterrupt, EOFError, OSError):
            return None

    import os
    import termios
    import tty

    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)

    current_idx = default_idx

    # Print Title Header
    delete_hint = ", Ctrl+D/d delete" if on_delete else ""
    sys.stdout.write(
        f"\n\x1b[1;38;2;255;122;0m🥕 {title}\x1b[0m \x1b[2;37m(Press 1-{num_options}, or use ↑/↓ + Enter{delete_hint}, Esc to cancel)\x1b[0m\n"
    )
    sys.stdout.write("\x1b[38;2;45;51;66m" + "─" * 68 + "\x1b[0m\n")

    def render_all(selected_idx: int) -> None:
        for i, (_id, label, desc) in enumerate(options):
            num_prefix = f" {i + 1}. "
            separator = f" \x1b[2m│\x1b[0m {desc}" if desc else ""
            if i == selected_idx:
                cursor = "🥕 "
                line_str = f"\x1b[1;38;2;255;122;0m{num_prefix}{label:<18}\x1b[0m{separator}"
            else:
                cursor = "   "
                line_str = f"\x1b[38;2;156;163;175m{num_prefix}{label:<18}\x1b[0m{separator}"
            sys.stdout.write(f"\r\x1b[K{cursor}{line_str}\n")
        sys.stdout.flush()

    def redraw_menu(option_count: int, extra_lines: int = 0) -> None:
        """Clear the previous menu and render it at the same terminal position."""
        sys.stdout.write(f"\x1b[{option_count}A")
        line_count = option_count + extra_lines
        for _ in range(line_count):
            sys.stdout.write("\r\x1b[K\n")
        sys.stdout.write(f"\x1b[{line_count}A")
        render_all(current_idx)

    try:
        tty.setcbreak(fd)
        render_all(current_idx)

        while True:
            # Read atomic raw bytes directly from fd to avoid Python TextIOWrapper buffer desync
            raw_bytes = os.read(fd, 32)
            if not raw_bytes:
                continue

            # Ctrl+D/d: request deletion when this selector explicitly allows it.
            if on_delete and raw_bytes in (b"\x04", b"d", b"D"):
                selected_id, selected_label, _ = options[current_idx]
                sys.stdout.write(
                    f"\r\x1b[KDelete '{selected_label}'? Press Enter to delete, Esc to cancel"
                )
                sys.stdout.flush()
                confirmation = os.read(fd, 32)
                if confirmation in (b"\r", b"\n"):
                    try:
                        on_delete(selected_id)
                    except Exception as exc:
                        sys.stdout.write(f"\r\x1b[KDelete failed: {exc}\n")
                        sys.stdout.flush()
                        return None
                    old_count = num_options
                    options.pop(current_idx)
                    num_options -= 1
                    if not options:
                        sys.stdout.write(f"\r\x1b[KDeleted: {selected_label}\n\n")
                        sys.stdout.flush()
                        return None
                    current_idx = min(current_idx, num_options - 1)
                    redraw_menu(old_count, extra_lines=1)
                else:
                    redraw_menu(num_options, extra_lines=1)
                continue

            # Ctrl+C (\x03)
            if raw_bytes == b"\x03":
                sys.stdout.write("\n")
                raise KeyboardInterrupt

            # Standalone Escape key (Esc) -> cancel selection cleanly
            if raw_bytes == b"\x1b":
                sys.stdout.write("\n\x1b[2;37m(Selection cancelled)\x1b[0m\n\n")
                sys.stdout.flush()
                return None

            # Up Arrow (\x1b[A or \x1bOA)
            if raw_bytes in (b"\x1b[A", b"\x1bOA"):
                current_idx = (current_idx - 1) % num_options
                sys.stdout.write(f"\x1b[{num_options}A")
                render_all(current_idx)
                continue

            # Down Arrow (\x1b[B or \x1bOB)
            if raw_bytes in (b"\x1b[B", b"\x1bOB"):
                current_idx = (current_idx + 1) % num_options
                sys.stdout.write(f"\x1b[{num_options}A")
                render_all(current_idx)
                continue

            # Enter (\r or \n)
            if raw_bytes in (b"\r", b"\n"):
                sys.stdout.write(f"\n\x1b[1;32m✓ Selected: {options[current_idx][1]}\x1b[0m\n\n")
                sys.stdout.flush()
                return options[current_idx][0]

            # Direct single-number key entry (1..9)
            if raw_bytes.isdigit():
                num = int(raw_bytes.decode(errors="ignore"))
                if 1 <= num <= num_options:
                    current_idx = num - 1
                    sys.stdout.write(
                        f"\n\x1b[1;32m✓ Selected: {options[current_idx][1]}\x1b[0m\n\n"
                    )
                    sys.stdout.flush()
                    return options[current_idx][0]

    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
