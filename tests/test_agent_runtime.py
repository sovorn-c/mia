from __future__ import annotations

import pytest
from pydantic import ValidationError

from mia_agent.runtime_models import RuntimeIdentity


def test_runtime_identity_contains_only_canonical_attribution() -> None:
    identity = RuntimeIdentity(
        run_id="run-1",
        task_id="root",
        agent_id="mia",
        session_id="session-1",
        parent_session_id="parent-session-1",
    )

    assert identity.model_dump() == {
        "run_id": "run-1",
        "task_id": "root",
        "agent_id": "mia",
        "session_id": "session-1",
        "parent_session_id": "parent-session-1",
    }

    with pytest.raises(ValidationError):
        RuntimeIdentity(
            run_id="run-1",
            task_id="root",
            agent_id="mia",
            session_id="session-1",
            mode="single",
        )
