"""Session tree traversal, branch navigation, and message reconstruction."""

from __future__ import annotations

from mia_agent.session.entries import (
    CompactionEntry,
    LeafEntry,
    MessageEntry,
    SessionEntry,
)
from mia_ai.types import ChatMessage


class SessionTreeError(ValueError):
    """Raised when session entry graph is invalid, disconnected, or cyclic."""


class SessionTree:
    """Represents a session history directed tree with branch and compaction support."""

    def __init__(self, entries: list[SessionEntry] | None = None) -> None:
        self._entries_by_id: dict[str, SessionEntry] = {}
        self._all_entries: list[SessionEntry] = []
        self._active_leaf_id: str | None = None

        if entries:
            for entry in entries:
                self.add_entry(entry)

    @property
    def entries(self) -> list[SessionEntry]:
        """Return all recorded session entries in insertion order."""
        return list(self._all_entries)

    def add_entry(self, entry: SessionEntry) -> None:
        """Add an entry to the tree structure."""
        if entry.id in self._entries_by_id:
            raise SessionTreeError(f"Duplicate session entry ID: {entry.id}")

        self._entries_by_id[entry.id] = entry
        self._all_entries.append(entry)

        if isinstance(entry, LeafEntry) and entry.entry_id:
            self._active_leaf_id = entry.entry_id
        elif not isinstance(entry, LeafEntry):
            # Default active leaf is the most recent non-leaf entry
            self._active_leaf_id = entry.id

    def get_entry(self, entry_id: str) -> SessionEntry | None:
        """Retrieve entry by unique ID."""
        return self._entries_by_id.get(entry_id)

    def get_path_to_entry(self, target_id: str) -> list[SessionEntry]:
        """Traverse backwards from target_id to root and return the chronological path."""
        path: list[SessionEntry] = []
        visited: set[str] = set()
        current_id: str | None = target_id

        while current_id is not None:
            if current_id in visited:
                raise SessionTreeError(f"Cycle detected at session entry: {current_id}")
            visited.add(current_id)

            entry = self._entries_by_id.get(current_id)
            if entry is None:
                raise SessionTreeError(f"Missing referenced parent session entry: {current_id}")

            path.append(entry)
            current_id = entry.parent_id

        path.reverse()
        return path

    def get_active_path(self) -> list[SessionEntry]:
        """Return the root-to-leaf path for the active session branch."""
        if not self._active_leaf_id:
            return []
        return self.get_path_to_entry(self._active_leaf_id)

    def extract_messages_from_path(self, path: list[SessionEntry]) -> list[ChatMessage]:
        """Reconstruct the effective ChatMessage list from a path, factoring in compactions."""
        messages: list[ChatMessage] = []

        for entry in path:
            if isinstance(entry, MessageEntry):
                messages.append(entry.message)
            elif isinstance(entry, CompactionEntry):
                # Replace prior messages specified in compaction
                if entry.replaces_entry_ids:
                    # Filter out messages from replaced entries
                    # In chronological path, insert summary message
                    messages = [
                        ChatMessage(
                            role="user",
                            content=f"Previous conversation summary:\n{entry.summary}",
                        )
                    ]
                else:
                    messages.append(
                        ChatMessage(
                            role="user",
                            content=f"Previous conversation summary:\n{entry.summary}",
                        )
                    )

        return messages
