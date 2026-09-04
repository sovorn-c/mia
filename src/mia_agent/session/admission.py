"""Process-local exclusive session admission management."""

from __future__ import annotations

import threading


class SessionAdmission:
    """Process-local admission tracker for Agent-owned Sessions."""

    _active_sessions: set[tuple[str, str]] = set()
    _lock = threading.Lock()

    @classmethod
    def acquire(cls, agent_id: str, session_id: str) -> bool:
        """Attempt to acquire exclusive ownership of an (agent_id, session_id) pair.

        Returns True if acquired, False if session is currently busy.
        """
        key = (agent_id, session_id)
        with cls._lock:
            if key in cls._active_sessions:
                return False
            cls._active_sessions.add(key)
            return True

    @classmethod
    def release(cls, agent_id: str, session_id: str) -> None:
        """Release ownership of an (agent_id, session_id) pair."""
        key = (agent_id, session_id)
        with cls._lock:
            cls._active_sessions.discard(key)

    @classmethod
    def is_admitted(cls, agent_id: str, session_id: str) -> bool:
        """Check if an (agent_id, session_id) pair is currently active."""
        key = (agent_id, session_id)
        with cls._lock:
            return key in cls._active_sessions

    @classmethod
    def clear_all(cls) -> None:
        """Reset admission state for testing."""
        with cls._lock:
            cls._active_sessions.clear()
