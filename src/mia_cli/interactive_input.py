"""Clean, modern terminal input engine with Tab-completion and history (Pi & Tau inspired)."""

from __future__ import annotations

import readline
import sys
from pathlib import Path

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
            return options[state] + " "
        return None


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


class LiveInteractivePrompt:
    """Rock-solid, zero-ghost-trail prompt reader with native Readline history and Tab completion."""

    def __init__(self, history_file: Path | None = None) -> None:
        self.history_file = history_file or (Path.home() / ".mia" / "history")
        self.history: list[str] = self._load_history()
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
                readline.write_history_file(str(self.history_file))
            except Exception:
                pass

    def read_prompt(self, prompt_prefix: str = "🥕 mia › ") -> str:
        """Read a single prompt line with clean history and zero cursor jumping."""
        try:
            colored_prompt = f"\x1b[1;38;2;255;122;0m{prompt_prefix}\x1b[0m"
            raw_input = input(colored_prompt).strip()
            if raw_input:
                self._save_history()
            return raw_input
        except EOFError:
            raise
        except KeyboardInterrupt:
            sys.stdout.write("\n")
            raise
