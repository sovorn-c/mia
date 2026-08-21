"""Minimalist, rock-solid interactive prompt with dynamic live-filtering slash command dropdown."""

from __future__ import annotations

import readline
import sys
from pathlib import Path

from rich.console import Console

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
    ("/init", "Inspect repository context & AGENTS.md (alias: /bootstrap)"),
    ("/undo", "Revert latest file change made during session (alias: /revert)"),
    ("/clear", "Clear terminal screen and redraw banner (alias: /cls)"),
    ("/quit", "Save session tree and exit cleanly (alias: /exit)"),
]


class REPLCompleter:
    """Readline tab-completion handler for slash commands."""

    def __init__(self, commands: list[str]) -> None:
        self.commands = sorted(commands)

    def complete(self, text: str, state: int) -> str | None:
        options = [cmd for cmd in self.commands if cmd.startswith(text)]
        if state < len(options):
            return options[state]
        return None


def interactive_select(
    title: str,
    options: list[tuple[str, str, str]],  # (id, label, description)
    default_idx: int = 0,
) -> str | None:
    """Dual-mode interactive selection menu supporting both instant numeric keys (1..N) and arrow keys (Up/Down + Enter).

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


class LiveInteractivePrompt:
    """Interactive line reader with dynamic live-filtering slash command dropdown."""

    def __init__(self, history_file: Path | None = None) -> None:
        self.console = Console()
        self.history_file = history_file or (Path.home() / ".mia" / "history")
        self.history: list[str] = self._load_history()
        self._history_idx: int = -1
        self._setup_readline()

    def _setup_readline(self) -> None:
        """Configure readline with history and Tab-completion across platforms."""
        try:
            self.history_file.parent.mkdir(parents=True, exist_ok=True)
            if self.history_file.exists():
                readline.read_history_file(str(self.history_file))

            commands = [cmd for cmd, _ in COMMAND_HINTS]
            delims = readline.get_completer_delims().replace("/", "").replace("-", "")
            readline.set_completer_delims(delims)
            readline.set_completer(REPLCompleter(commands).complete)

            doc = getattr(readline, "__doc__", "") or ""
            if "libedit" in doc:
                readline.parse_and_bind("bind ^I rl_complete")
                readline.parse_and_bind("bind ^I complete")
            else:
                readline.parse_and_bind("tab: complete")

            readline.set_history_length(1000)
        except Exception:
            pass

    def _load_history(self) -> list[str]:
        if self.history_file and self.history_file.exists():
            try:
                lines = self.history_file.read_text(encoding="utf-8").splitlines()
                return [line.strip() for line in lines if line.strip()][-200:]
            except Exception:
                return []
        return []

    def _save_history(self) -> None:
        if self.history_file:
            try:
                self.history_file.parent.mkdir(parents=True, exist_ok=True)
                if self.history:
                    self.history_file.write_text(
                        "\n".join(self.history[-200:]) + "\n", encoding="utf-8"
                    )
                readline.write_history_file(str(self.history_file))
            except Exception:
                pass

    def _clear_dropdown(self, count: int) -> None:
        """Erase dropdown lines rendered below the prompt."""
        if count > 0:
            sys.stdout.write("\x1b[s")  # Save cursor
            for _ in range(count):
                sys.stdout.write("\n\x1b[2K")
            sys.stdout.write("\x1b[u")  # Restore cursor
            sys.stdout.flush()

    def _render_state(
        self,
        prompt_prefix: str,
        buffer: str,
        cursor_pos: int,
        prev_dropdown_count: int,
    ) -> int:
        """Render prompt and dynamic live-filtered slash command dropdown below."""
        self._clear_dropdown(prev_dropdown_count)

        colored_pfx = f"\x1b[1;38;2;255;122;0m{prompt_prefix}\x1b[0m"
        sys.stdout.write(f"\r\x1b[2K{colored_pfx}{buffer}")

        dropdown_count = 0
        if buffer.startswith("/"):
            query = buffer.split()[0].lower()
            matches = [item for item in COMMAND_HINTS if item[0].startswith(query)]
            if matches:
                dropdown_count = min(len(matches), 5)
                sys.stdout.write("\x1b[s")  # Save cursor at prompt line
                for i, (cmd, desc) in enumerate(matches[:5]):
                    pointer = "🥕 " if i == 0 else "   "
                    cmd_col = f"\x1b[1;38;2;255;122;0m{cmd:<10}\x1b[0m"
                    desc_col = f"\x1b[38;2;156;163;175m{desc[:48]}\x1b[0m"
                    sys.stdout.write(f"\n\x1b[2K  {pointer}{cmd_col} \x1b[2m│\x1b[0m {desc_col}")
                sys.stdout.write("\x1b[u")  # Restore cursor back to prompt line

        # Set cursor to correct column
        pfx_len = len(prompt_prefix)
        col = pfx_len + cursor_pos + 1
        sys.stdout.write(f"\x1b[{col}G")
        sys.stdout.flush()
        return dropdown_count

    def read_prompt(self, prompt_prefix: str = "🥕 mia › ") -> str:
        """Read prompt with real-time character-by-character slash filtering and tab autocomplete."""
        if not sys.stdin.isatty():
            try:
                line = input(prompt_prefix).strip()
                return line
            except EOFError:
                raise

        import termios
        import tty

        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)

        buffer = ""
        cursor_pos = 0
        self._history_idx = -1
        dropdown_count = 0

        try:
            tty.setcbreak(fd)
            dropdown_count = self._render_state(prompt_prefix, buffer, cursor_pos, dropdown_count)

            while True:
                char = sys.stdin.read(1)

                # Ctrl+C
                if char == "\x03":
                    self._clear_dropdown(dropdown_count)
                    sys.stdout.write("\n")
                    sys.stdout.flush()
                    raise KeyboardInterrupt

                # Ctrl+D
                if char == "\x04" and not buffer:
                    self._clear_dropdown(dropdown_count)
                    sys.stdout.write("\n")
                    sys.stdout.flush()
                    raise EOFError

                # Enter (\r or \n)
                if char in ("\r", "\n"):
                    self._clear_dropdown(dropdown_count)
                    sys.stdout.write("\n")
                    sys.stdout.flush()
                    line = buffer.strip()
                    if line and (not self.history or self.history[-1] != line):
                        self.history.append(line)
                        self._save_history()
                    return line

                # Backspace (\x7f or \x08)
                if char in ("\x7f", "\x08"):
                    if cursor_pos > 0:
                        buffer = buffer[: cursor_pos - 1] + buffer[cursor_pos:]
                        cursor_pos -= 1
                        dropdown_count = self._render_state(
                            prompt_prefix, buffer, cursor_pos, dropdown_count
                        )
                    continue

                # Tab (\t) -> Autocomplete matching slash command
                if char == "\t":
                    if buffer.startswith("/"):
                        query = buffer.split()[0].lower()
                        matches = [cmd for cmd, _ in COMMAND_HINTS if cmd.startswith(query)]
                        if len(matches) == 1:
                            buffer = matches[0] + " "
                            cursor_pos = len(buffer)
                            dropdown_count = self._render_state(
                                prompt_prefix, buffer, cursor_pos, dropdown_count
                            )
                        elif len(matches) > 1:
                            # Complete common prefix
                            prefix = matches[0]
                            for m in matches[1:]:
                                while not m.startswith(prefix) and prefix:
                                    prefix = prefix[:-1]
                            if len(prefix) > len(buffer):
                                buffer = prefix
                                cursor_pos = len(buffer)
                            dropdown_count = self._render_state(
                                prompt_prefix, buffer, cursor_pos, dropdown_count
                            )
                    continue

                # ANSI Escape Sequences (Arrows)
                if char == "\x1b":
                    seq1 = sys.stdin.read(1)
                    if seq1 == "[":
                        seq2 = sys.stdin.read(1)
                        # Up arrow -> History prev
                        if seq2 == "A":
                            if self.history:
                                if self._history_idx == -1:
                                    self._history_idx = len(self.history) - 1
                                elif self._history_idx > 0:
                                    self._history_idx -= 1
                                buffer = self.history[self._history_idx]
                                cursor_pos = len(buffer)
                                dropdown_count = self._render_state(
                                    prompt_prefix, buffer, cursor_pos, dropdown_count
                                )
                        # Down arrow -> History next
                        elif seq2 == "B":
                            if self._history_idx != -1:
                                if self._history_idx < len(self.history) - 1:
                                    self._history_idx += 1
                                    buffer = self.history[self._history_idx]
                                else:
                                    self._history_idx = -1
                                    buffer = ""
                                cursor_pos = len(buffer)
                                dropdown_count = self._render_state(
                                    prompt_prefix, buffer, cursor_pos, dropdown_count
                                )
                        # Left arrow
                        elif seq2 == "D" and cursor_pos > 0:
                            cursor_pos -= 1
                            dropdown_count = self._render_state(
                                prompt_prefix, buffer, cursor_pos, dropdown_count
                            )
                        # Right arrow
                        elif seq2 == "C" and cursor_pos < len(buffer):
                            cursor_pos += 1
                            dropdown_count = self._render_state(
                                prompt_prefix, buffer, cursor_pos, dropdown_count
                            )
                    continue

                # Normal printable characters
                if char.isprintable():
                    buffer = buffer[:cursor_pos] + char + buffer[cursor_pos:]
                    cursor_pos += 1
                    dropdown_count = self._render_state(
                        prompt_prefix, buffer, cursor_pos, dropdown_count
                    )

        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
