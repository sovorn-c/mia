"""Production-grade terminal input engine with prompt_toolkit, floating slash autocomplete & pinned status toolbar."""

from __future__ import annotations

import asyncio
import contextlib
import sys
import time
from collections.abc import Callable, Iterable
from html import escape
from pathlib import Path
from typing import Any

from prompt_toolkit.application import Application
from prompt_toolkit.application.current import get_app
from prompt_toolkit.completion import CompleteEvent, Completer, Completion
from prompt_toolkit.document import Document
from prompt_toolkit.filters import Condition
from prompt_toolkit.formatted_text import HTML, AnyFormattedText, StyleAndTextTuples
from prompt_toolkit.history import FileHistory, History, InMemoryHistory
from prompt_toolkit.key_binding import KeyBindings, KeyPressEvent
from prompt_toolkit.keys import Keys
from prompt_toolkit.layout import HSplit, Layout, Window
from prompt_toolkit.layout.controls import BufferControl, FormattedTextControl
from prompt_toolkit.layout.dimension import Dimension
from prompt_toolkit.shortcuts import PromptSession
from prompt_toolkit.styles import Style
from prompt_toolkit.utils import get_cwidth
from prompt_toolkit.widgets import Frame, Label, TextArea

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
        "selector-frame": "#2D3342",
        "selector-title": "bold #FF7A00",
        "selector-hint": "#6B7280",
        "selector-search": "#E5E7EB",
        "selector-item": "#E5E7EB",
        "selector-selected": "bold #FF7A00",
        "selector-muted": "#9CA3AF",
        "selector-error": "#F87171",
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


def _safe_status_text(value: str) -> str:
    """Keep user-controlled status values single-line and safe for prompt_toolkit HTML."""
    clean = " ".join(str(value).replace("\r", " ").replace("\n", " ").split())
    return escape(clean, quote=False)


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
    workspace_name = _safe_status_text(workspace_name)
    model_name = _safe_status_text(model_name)
    agent_id = _safe_status_text(agent_id) if agent_id else None
    session_id = _safe_status_text(session_id) if session_id else None
    run_state = _safe_status_text(run_state)
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
        self.approval_active: bool = False
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
        self.approval_session: PromptSession[str] = PromptSession(
            style=MIA_STYLE,
            input=input,
            output=output,
        )
        self._install_completion_menu_anchor()

    def _install_completion_menu_anchor(self) -> None:
        """Anchor the completion popup at the slash, not the query cursor."""
        for control in self.session.layout.find_all_controls():
            if isinstance(control, BufferControl) and control.buffer is self.session.default_buffer:
                control.menu_position = self._completion_menu_position

    def _completion_menu_position(self) -> int | None:
        """Return the buffer offset of the active slash command."""
        state = self.session.default_buffer.complete_state
        if state is None:
            return None

        before_cursor = state.original_document.text_before_cursor
        line = before_cursor.rsplit("\n", 1)[-1]
        stripped_line = line.lstrip()
        if not stripped_line.startswith("/"):
            return None

        line_start = state.original_document.cursor_position - len(line)
        return line_start + len(line) - len(stripped_line)

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

        # Completion navigation must win over history navigation while the menu is open.
        @kb.add("up")
        def _completion_up(event: KeyPressEvent) -> None:
            event.current_buffer.auto_up()

        @kb.add("down")
        def _completion_down(event: KeyPressEvent) -> None:
            event.current_buffer.auto_down()

        @kb.add("tab")
        def _completion_next(event: KeyPressEvent) -> None:
            buffer = event.current_buffer
            if buffer.complete_state:
                buffer.complete_next()
            else:
                buffer.start_completion(select_first=True)

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

    async def read_approval_async(self, prompt_prefix: str = "Approve? [y/N] ") -> str:
        """Read approval in a separate prompt-toolkit focus, never from the draft buffer."""
        if not sys.stdin.isatty() and not getattr(self.approval_session, "_input", None):
            return ""
        try:
            return await self.approval_session.prompt_async(
                [("class:prompt", prompt_prefix)],
                default="",
            )
        except (asyncio.CancelledError, EOFError, KeyboardInterrupt, OSError):
            return ""

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


def _single_line(text: str) -> str:
    return " ".join(str(text).replace("\r", " ").replace("\n", " ").split())


def _truncate_selector_text(text: str, width: int) -> str:
    if width <= 0:
        return ""
    if get_cwidth(text) <= width:
        return text
    if width == 1:
        return "…"
    result: list[str] = []
    used = 0
    for char in text:
        char_width = get_cwidth(char)
        if used + char_width > width - 1:
            break
        result.append(char)
        used += char_width
    return "".join(result) + "…"


def _selector_matches(query: str, option: tuple[str, str, str]) -> bool:
    haystack = " ".join(option).lower()
    return all(
        token in haystack or _is_subsequence(token, haystack) for token in query.lower().split()
    )


def _is_subsequence(needle: str, haystack: str) -> bool:
    cursor = iter(haystack)
    return all(char in cursor for char in needle)


def _selector_width() -> int:
    try:
        return max(20, get_app().output.get_size().columns)
    except Exception:
        return 80


def _run_selector_application[T](application: Application[T]) -> T:
    """Run a modal selector from sync code or while Mia's async loop is active."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return application.run()
    return application.run(in_thread=True, handle_sigint=False)


def interactive_multi_select(
    title: str,
    options: list[tuple[str, str, str]],
    selected_ids: Iterable[str] = (),
    *,
    _input: Any = None,
    _output: Any = None,
) -> list[str] | None:
    """Select multiple options with Pi-style search, scrolling, and safe terminal cleanup."""
    if not options:
        return []
    if _input is None and _output is None and not (sys.stdin.isatty() and sys.stdout.isatty()):
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

    items = list(options)
    option_ids = [option[0] for option in items]
    selected = set(selected_ids).intersection(option_ids)
    current_idx = 0
    max_visible = 8
    search = TextArea(
        height=1,
        prompt="Filter: ",
        multiline=False,
        wrap_lines=False,
        style="class:selector-search",
    )

    def filtered() -> list[tuple[int, tuple[str, str, str]]]:
        query = _single_line(search.text)
        return [
            (index, option)
            for index, option in enumerate(items)
            if _selector_matches(query, option)
        ]

    def current_item() -> tuple[int, tuple[str, str, str]] | None:
        visible = filtered()
        if not visible:
            return None
        return visible[min(current_idx, len(visible) - 1)]

    def render_list() -> StyleAndTextTuples:
        visible = filtered()
        if not visible:
            return [("class:selector-muted", "  No matching options")]

        selected_position = min(current_idx, len(visible) - 1)
        start = max(0, min(selected_position - max_visible // 2, len(visible) - max_visible))
        end = min(start + max_visible, len(visible))
        width = _selector_width() - 4
        fragments: StyleAndTextTuples = []
        for position in range(start, end):
            _, (_, label, description) = visible[position]
            prefix = "▸ " if position == selected_position else "  "
            marker = "◉" if visible[position][1][0] in selected else "○"
            text = f"{prefix}{marker} {_single_line(label)}"
            if description:
                text += f"  │ {_single_line(description)}"
            style = (
                "class:selector-selected"
                if position == selected_position
                else "class:selector-item"
            )
            fragments.append((style, _truncate_selector_text(text, width)))
            if position < end - 1:
                fragments.append(("", "\n"))

        if start > 0 or end < len(visible):
            fragments.extend(
                [
                    ("", "\n"),
                    (
                        "class:selector-muted",
                        f"  ({selected_position + 1}/{len(visible)})",
                    ),
                ]
            )
        return fragments

    def render_footer() -> StyleAndTextTuples:
        visible_count = len(filtered())
        text = f"Space toggle · Ctrl+A all · Ctrl+X clear · Enter save · Esc cancel · {len(selected)}/{visible_count} visible"
        return [("class:selector-hint", _truncate_selector_text(text, _selector_width() - 4))]

    def invalidate(_event: Any = None) -> None:
        nonlocal current_idx
        current_idx = min(current_idx, max(0, len(filtered()) - 1))
        with contextlib.suppress(Exception):
            get_app().invalidate()

    search.buffer.on_text_changed += invalidate
    list_control = FormattedTextControl(render_list, focusable=True, show_cursor=False)
    footer_control = FormattedTextControl(render_footer)
    root = Frame(
        HSplit(
            [
                Label(title, style="class:selector-title"),
                Label("Type to filter · ↑↓ navigate", style="class:selector-hint"),
                search,
                Window(
                    content=list_control,
                    height=Dimension(min=1, max=max_visible + 1),
                    wrap_lines=False,
                    dont_extend_height=True,
                ),
                Window(content=footer_control, height=1, dont_extend_height=True),
            ]
        ),
        style="class:selector-frame",
    )
    bindings = KeyBindings()

    def move(delta: int) -> None:
        nonlocal current_idx
        visible = filtered()
        if visible:
            current_idx = (current_idx + delta) % len(visible)
            invalidate()

    @bindings.add("tab")
    def _focus_next(event: KeyPressEvent) -> None:
        event.app.layout.focus_next()

    @bindings.add(Keys.BackTab)
    def _focus_previous(event: KeyPressEvent) -> None:
        event.app.layout.focus_previous()

    @bindings.add("up")
    def _up(event: KeyPressEvent) -> None:
        move(-1)

    @bindings.add("down")
    def _down(event: KeyPressEvent) -> None:
        move(1)

    @bindings.add("pageup")
    def _page_up(event: KeyPressEvent) -> None:
        move(-max_visible)

    @bindings.add("pagedown")
    def _page_down(event: KeyPressEvent) -> None:
        move(max_visible)

    @bindings.add(
        "space",
        filter=Condition(lambda: not search.text or get_app().layout.has_focus(list_control)),
    )
    def _toggle(event: KeyPressEvent) -> None:
        item = current_item()
        if item:
            option_id = item[1][0]
            if option_id in selected:
                selected.remove(option_id)
            else:
                selected.add(option_id)
            invalidate()

    @bindings.add("c-a")
    def _select_all(event: KeyPressEvent) -> None:
        selected.update(option_ids)
        invalidate()

    @bindings.add("c-x")
    def _clear_all(event: KeyPressEvent) -> None:
        selected.clear()
        invalidate()

    @bindings.add("enter")
    def _submit(event: KeyPressEvent) -> None:
        event.app.exit(result=[option_id for option_id in option_ids if option_id in selected])

    @bindings.add("escape")
    @bindings.add("c-c")
    def _cancel(event: KeyPressEvent) -> None:
        event.app.exit(result=None)

    app: Application[list[str] | None] = Application(
        layout=Layout(root, focused_element=search),
        key_bindings=bindings,
        style=MIA_STYLE,
        full_screen=False,
        erase_when_done=True,
        enable_page_navigation_bindings=False,
        input=_input,
        output=_output,
    )
    try:
        return _run_selector_application(app)
    except (EOFError, KeyboardInterrupt):
        return None


def interactive_select(
    title: str,
    options: list[tuple[str, str, str]],  # (id, label, description)
    default_idx: int = 0,
    on_delete: Callable[[str], None] | None = None,
    *,
    _input: Any = None,
    _output: Any = None,
) -> str | None:
    """Select one option with Pi-style search, scrolling, and safe terminal cleanup."""
    if not options:
        return None

    items = list(options)
    default_idx = max(0, min(default_idx, len(items) - 1))
    if _input is None and _output is None and not (sys.stdin.isatty() and sys.stdout.isatty()):
        try:
            prompt_str = f"{title} [1-{len(items)}] (default: {default_idx + 1}): "
            raw = input(prompt_str).strip()
            if not raw:
                return items[default_idx][0]
            if raw.lower() in ("0", "q", "quit", "cancel", "esc"):
                return None
            if raw.isdigit() and 1 <= int(raw) <= len(items):
                return items[int(raw) - 1][0]
            for option in items:
                if raw.lower() in (option[0].lower(), option[1].lower()):
                    return option[0]
            return items[default_idx][0]
        except (KeyboardInterrupt, EOFError, OSError):
            return None

    current_idx = default_idx
    max_visible = 8
    confirming_delete = False
    status_message = ""
    search = TextArea(
        height=1,
        prompt="Filter: ",
        multiline=False,
        wrap_lines=False,
        style="class:selector-search",
    )

    def filtered() -> list[tuple[int, tuple[str, str, str]]]:
        query = _single_line(search.text)
        return [
            (index, option)
            for index, option in enumerate(items)
            if _selector_matches(query, option)
        ]

    def current_item() -> tuple[int, tuple[str, str, str]] | None:
        visible = filtered()
        if not visible:
            return None
        return visible[min(current_idx, len(visible) - 1)]

    def render_list() -> StyleAndTextTuples:
        visible = filtered()
        if not visible:
            return [("class:selector-muted", "  No matching options")]

        selected_position = min(current_idx, len(visible) - 1)
        start = max(0, min(selected_position - max_visible // 2, len(visible) - max_visible))
        end = min(start + max_visible, len(visible))
        width = _selector_width() - 4
        fragments: StyleAndTextTuples = []
        for position in range(start, end):
            _, (_, label, description) = visible[position]
            prefix = "▸ " if position == selected_position else "  "
            text = f"{prefix}{_single_line(label)}"
            if description:
                text += f"  │ {_single_line(description)}"
            style = (
                "class:selector-selected"
                if position == selected_position
                else "class:selector-item"
            )
            fragments.append((style, _truncate_selector_text(text, width)))
            if position < end - 1:
                fragments.append(("", "\n"))

        if start > 0 or end < len(visible):
            fragments.extend(
                [
                    ("", "\n"),
                    (
                        "class:selector-muted",
                        f"  ({selected_position + 1}/{len(visible)})",
                    ),
                ]
            )
        return fragments

    def render_footer() -> StyleAndTextTuples:
        visible_count = len(filtered())
        if status_message:
            text = status_message
            style = "class:selector-error"
        else:
            delete_hint = " · Ctrl+D delete" if on_delete else ""
            text = f"Enter select · Esc cancel · ↑↓ navigate · {visible_count} options{delete_hint}"
            style = "class:selector-hint"
        return [(style, _truncate_selector_text(text, _selector_width() - 4))]

    def invalidate(_event: Any = None) -> None:
        nonlocal current_idx
        current_idx = min(current_idx, max(0, len(filtered()) - 1))
        with contextlib.suppress(Exception):
            get_app().invalidate()

    search.buffer.on_text_changed += invalidate
    list_control = FormattedTextControl(render_list, focusable=True, show_cursor=False)
    footer_control = FormattedTextControl(render_footer)
    root = Frame(
        HSplit(
            [
                Label(title, style="class:selector-title"),
                Label("Type to filter · ↑↓ navigate", style="class:selector-hint"),
                search,
                Window(
                    content=list_control,
                    height=Dimension(min=1, max=max_visible + 1),
                    wrap_lines=False,
                    dont_extend_height=True,
                ),
                Window(content=footer_control, height=1, dont_extend_height=True),
            ]
        ),
        style="class:selector-frame",
    )
    bindings = KeyBindings()

    def move(delta: int) -> None:
        nonlocal current_idx
        visible = filtered()
        if visible:
            current_idx = (current_idx + delta) % len(visible)
            invalidate()

    @bindings.add("tab")
    def _focus_next(event: KeyPressEvent) -> None:
        event.app.layout.focus_next()

    @bindings.add(Keys.BackTab)
    def _focus_previous(event: KeyPressEvent) -> None:
        event.app.layout.focus_previous()

    @bindings.add("up")
    def _up(event: KeyPressEvent) -> None:
        move(-1)

    @bindings.add("down")
    def _down(event: KeyPressEvent) -> None:
        move(1)

    @bindings.add("pageup")
    def _page_up(event: KeyPressEvent) -> None:
        move(-max_visible)

    @bindings.add("pagedown")
    def _page_down(event: KeyPressEvent) -> None:
        move(max_visible)

    @bindings.add(
        "d",
        filter=Condition(
            lambda: on_delete is not None and get_app().layout.has_focus(list_control)
        ),
    )
    @bindings.add("c-d")
    def _request_delete(event: KeyPressEvent) -> None:
        nonlocal confirming_delete, status_message
        if current_item() is not None:
            confirming_delete = True
            status_message = "Delete selected item? Enter confirms · Esc cancels"
            invalidate()

    @bindings.add("enter")
    def _submit(event: KeyPressEvent) -> None:
        nonlocal confirming_delete, status_message
        item = current_item()
        if item is None:
            return
        if confirming_delete and on_delete is not None:
            try:
                on_delete(item[1][0])
            except Exception as exc:
                confirming_delete = False
                status_message = f"Delete failed: {type(exc).__name__}"
                invalidate()
                return
            items.pop(item[0])
            if not items:
                event.app.exit(result=None)
                return
            confirming_delete = False
            status_message = ""
            invalidate()
            return
        event.app.exit(result=item[1][0])

    @bindings.add("escape")
    def _escape(event: KeyPressEvent) -> None:
        nonlocal confirming_delete, status_message
        if confirming_delete:
            confirming_delete = False
            status_message = ""
            invalidate()
            return
        event.app.exit(result=None)

    @bindings.add("c-c")
    def _cancel(event: KeyPressEvent) -> None:
        event.app.exit(result=None)

    app: Application[str | None] = Application(
        layout=Layout(root, focused_element=search),
        key_bindings=bindings,
        style=MIA_STYLE,
        full_screen=False,
        erase_when_done=True,
        enable_page_navigation_bindings=False,
        input=_input,
        output=_output,
    )
    try:
        return _run_selector_application(app)
    except (EOFError, KeyboardInterrupt):
        return None
