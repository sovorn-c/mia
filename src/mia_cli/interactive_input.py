"""Native POSIX character-by-character interactive prompt with live floating slash command autocomplete and arrow-key selection."""

from __future__ import annotations

import sys
from pathlib import Path

from rich.console import Console

COMMAND_HINTS: list[tuple[str, str]] = [
    ("/help", "Show command menu & shortcuts (alias: /?)"),
    ("/login", "Authenticate AI providers & API keys (alias: /auth)"),
    ("/model", "Switch active LLM (Pi-style scoper) (alias: /llm)"),
    ("/profile", "Switch agent persona (coding, architect, minimal)"),
    ("/diff", "View git diff of session modifications (alias: /changes)"),
    ("/cost", "Show session tokens & USD cost (alias: /stats, /tokens)"),
    ("/compact", "Trigger context window compaction (alias: /compress)"),
    ("/sessions", "List saved session trees (alias: /history)"),
    ("/init", "Inspect repository context & AGENTS.md (alias: /bootstrap)"),
    ("/undo", "Revert latest file change made during session (alias: /revert)"),
    ("/clear", "Clear terminal screen (alias: /cls)"),
    ("/quit", "Save and exit cleanly (alias: /exit)"),
]


def interactive_select(
    title: str,
    options: list[tuple[str, str, str]],  # (id, label, description)
    default_idx: int = 0,
) -> str | None:
    """Prompt user to navigate with Up/Down arrow keys and press Enter to select (Claude Code/Pi style)."""
    if not options:
        return None

    if not sys.stdin.isatty():
        # Fallback for non-interactive / test environments
        try:
            line = input(
                f"{title} (Enter choice id or press Enter for default [{options[default_idx][0]}]): "
            ).strip()
            if not line:
                return options[default_idx][0]
            if line.isdigit() and 1 <= int(line) <= len(options):
                return options[int(line) - 1][0]
            for opt in options:
                if line.lower() == opt[0].lower():
                    return opt[0]
            return line
        except (KeyboardInterrupt, EOFError):
            return None

    import termios
    import tty

    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)

    current_idx = max(0, min(default_idx, len(options) - 1))
    num_options = len(options)

    # Print Title Header
    sys.stdout.write(
        f"\n\x1b[1;38;2;255;122;0m{title}\x1b[0m \x1b[2;37m(Use ↑/↓ arrows to navigate, Enter to select)\x1b[0m\n"
    )

    def render_options(idx: int) -> None:
        for i, (_id, label, desc) in enumerate(options):
            if i == idx:
                cursor = "\x1b[1;38;2;255;122;0m▸\x1b[0m "
                label_str = f"\x1b[1;38;2;255;122;0m{label:<20}\x1b[0m"
                desc_str = f"\x1b[38;2;243;244;246m{desc}\x1b[0m"
            else:
                cursor = "  "
                label_str = f"\x1b[38;2;156;163;175m{label:<20}\x1b[0m"
                desc_str = f"\x1b[2;37m{desc}\x1b[0m"
            sys.stdout.write(f"\r\x1b[K{cursor}{label_str} \x1b[2m│\x1b[0m {desc_str}\n")
        sys.stdout.flush()

    try:
        tty.setcbreak(fd)
        render_options(current_idx)

        while True:
            char = sys.stdin.read(1)

            # Ctrl+C or Ctrl+D
            if char in ("\x03", "\x04"):
                sys.stdout.write("\n")
                raise KeyboardInterrupt

            # Enter
            if char in ("\r", "\n"):
                sys.stdout.write(f"\x1b[1;32m✓ Selected: {options[current_idx][1]}\x1b[0m\n\n")
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
                        render_options(current_idx)
                    elif seq2 == "B":  # Down Arrow
                        current_idx = (current_idx + 1) % num_options
                        sys.stdout.write(f"\x1b[{num_options}A")
                        render_options(current_idx)

    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)


class LiveInteractivePrompt:
    """Zero-dependency POSIX interactive line reader with instant floating autocomplete menu."""

    def __init__(self, history_file: Path | None = None) -> None:
        self.console = Console()
        self.history_file = history_file or (Path.home() / ".mia" / "history")
        self.history: list[str] = self._load_history()
        self.history_idx: int = -1

    def _load_history(self) -> list[str]:
        if self.history_file and self.history_file.exists():
            try:
                lines = self.history_file.read_text(encoding="utf-8").splitlines()
                return [line.strip() for line in lines if line.strip()][-200:]
            except Exception:
                return []
        return []

    def _save_history(self) -> None:
        if self.history_file and self.history:
            try:
                self.history_file.parent.mkdir(parents=True, exist_ok=True)
                self.history_file.write_text(
                    "\n".join(self.history[-200:]) + "\n", encoding="utf-8"
                )
            except Exception:
                pass

    def read_prompt(self, prompt_prefix: str = "🥕 mia › ") -> str:
        """Read line interactively with real-time popup on '/'."""
        if not sys.stdin.isatty():
            try:
                return input(prompt_prefix).strip()
            except EOFError:
                raise

        import termios
        import tty

        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)

        buffer = ""
        cursor_pos = 0
        self.history_idx = -1
        rendered_menu_lines = 0

        try:
            tty.setcbreak(fd)

            self._render_line(prompt_prefix, buffer, cursor_pos, rendered_menu_lines)

            while True:
                char = sys.stdin.read(1)

                # Ctrl+C
                if char == "\x03":
                    self._clear_menu(rendered_menu_lines)
                    sys.stdout.write("\n")
                    sys.stdout.flush()
                    raise KeyboardInterrupt

                # Ctrl+D
                if char == "\x04" and not buffer:
                    self._clear_menu(rendered_menu_lines)
                    sys.stdout.write("\n")
                    sys.stdout.flush()
                    raise EOFError

                # Enter (\r or \n)
                if char in ("\r", "\n"):
                    self._clear_menu(rendered_menu_lines)
                    sys.stdout.write(
                        "\r\x1b[K"
                        + "\x1b[1;38;2;255;122;0m"
                        + prompt_prefix
                        + "\x1b[0m"
                        + buffer
                        + "\n"
                    )
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

                # Tab (\t) -> Autocomplete slash command
                elif char == "\t":
                    if buffer.startswith("/"):
                        matches = [cmd for cmd, _ in COMMAND_HINTS if cmd.startswith(buffer)]
                        if matches:
                            buffer = matches[0] + " "
                            cursor_pos = len(buffer)

                # ANSI Escape Sequences (Arrows, etc.)
                elif char == "\x1b":
                    seq1 = sys.stdin.read(1)
                    if seq1 == "[":
                        seq2 = sys.stdin.read(1)
                        # Up arrow -> History Prev
                        if seq2 == "A":
                            if self.history:
                                if self.history_idx == -1:
                                    self.history_idx = len(self.history) - 1
                                elif self.history_idx > 0:
                                    self.history_idx -= 1
                                buffer = self.history[self.history_idx]
                                cursor_pos = len(buffer)

                        # Down arrow -> History Next
                        elif seq2 == "B":
                            if self.history_idx != -1:
                                if self.history_idx < len(self.history) - 1:
                                    self.history_idx += 1
                                    buffer = self.history[self.history_idx]
                                    cursor_pos = len(buffer)
                                else:
                                    self.history_idx = -1
                                    buffer = ""
                                    cursor_pos = 0

                        # Right arrow
                        elif seq2 == "C" and cursor_pos < len(buffer):
                            cursor_pos += 1

                        # Left arrow
                        elif seq2 == "D" and cursor_pos > 0:
                            cursor_pos -= 1

                # Printable characters
                elif char.isprintable():
                    buffer = buffer[:cursor_pos] + char + buffer[cursor_pos:]
                    cursor_pos += 1

                rendered_menu_lines = self._render_line(
                    prompt_prefix, buffer, cursor_pos, rendered_menu_lines
                )

        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)

    def _render_line(
        self,
        prompt_prefix: str,
        buffer: str,
        cursor_pos: int,
        prev_menu_lines: int,
    ) -> int:
        """Render prompt line and instant floating autocomplete dropdown below."""
        self._clear_menu(prev_menu_lines)

        orange_prefix = "\x1b[1;38;2;255;122;0m" + prompt_prefix + "\x1b[0m"
        line_out = f"\r\x1b[K{orange_prefix}{buffer}"
        sys.stdout.write(line_out)

        menu_lines_count = 0

        if buffer.startswith("/"):
            query = buffer.split()[0].lower()
            matches = [item for item in COMMAND_HINTS if item[0].startswith(query)]
            if not matches:
                matches = COMMAND_HINTS[:6]

            menu_lines_count = len(matches) + 2
            sys.stdout.write(
                "\n\x1b[38;2;45;51;66m╭── \x1b[1;38;2;255;122;0mAvailable Commands\x1b[0m \x1b[38;2;107;114;128m(Press Tab or Enter)\x1b[0m \x1b[38;2;45;51;66m"
                + "─" * 28
                + "╮\x1b[0m\n"
            )
            for i, (cmd, desc) in enumerate(matches[:8]):
                arrow = "\x1b[1;38;2;255;122;0m▸\x1b[0m " if i == 0 else "  "
                cmd_colored = f"\x1b[1;38;2;255;122;0m{cmd:<11}\x1b[0m"
                desc_colored = f"\x1b[38;2;156;163;175m{desc[:48]}\x1b[0m"
                sys.stdout.write(
                    f"\x1b[38;2;45;51;66m│\x1b[0m {arrow}{cmd_colored} {desc_colored}\n"
                )

            sys.stdout.write("\x1b[38;2;45;51;66m╰" + "─" * 66 + "╯\x1b[0m")

            sys.stdout.write(f"\x1b[{menu_lines_count}A")

        prompt_visible_len = len(prompt_prefix)
        col = prompt_visible_len + cursor_pos + 1
        sys.stdout.write(f"\r\x1b[{col}C")
        sys.stdout.flush()

        return menu_lines_count

    def _clear_menu(self, menu_lines_count: int) -> None:
        """Erase any floating menu lines rendered below the prompt."""
        if menu_lines_count > 0:
            sys.stdout.write("\x1b[s")
            for _ in range(menu_lines_count):
                sys.stdout.write("\n\x1b[2K")
            sys.stdout.write("\x1b[u")
            sys.stdout.flush()
