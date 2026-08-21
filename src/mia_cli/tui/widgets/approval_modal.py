"""Interactive security approval modal dialog."""

from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Center, Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Static


class ApprovalModal(ModalScreen[bool]):
    """Modal dialog asking user to approve or reject a sensitive command/tool call."""

    DEFAULT_CSS = """
    ApprovalModal {
        align: center middle;
        background: rgba(0, 0, 0, 0.7);
    }

    #modal-card {
        width: 60;
        height: auto;
        background: #16191E;
        border: thick #FF7A00;
        padding: 1 2;
    }

    #modal-buttons {
        margin-top: 1;
        align: center middle;
    }

    Button {
        margin: 0 1;
    }
    """

    def __init__(self, action_name: str, details: str, agent_id: str = "coder") -> None:
        super().__init__()
        self.action_name = action_name
        self.details = details
        self.agent_id = agent_id

    def compose(self) -> ComposeResult:
        with Center():
            with Vertical(id="modal-card"):
                yield Static(
                    Text.assemble(
                        ("⚠️ Security Approval Required (", "bold #F59E0B"),
                        (f"@{self.agent_id}", "bold #38BDF8"),
                        (")", "bold #F59E0B"),
                    )
                )
                yield Static(
                    Text(
                        f"Agent requested to execute '{self.action_name}':\n\n{self.details}",
                        style="#F3F4F6",
                    )
                )
                with Horizontal(id="modal-buttons"):
                    yield Button("Approve (Y)", variant="success", id="btn-approve")
                    yield Button("Reject (N)", variant="error", id="btn-reject")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-approve":
            self.dismiss(True)
        else:
            self.dismiss(False)
