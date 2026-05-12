"""Provider ABC and shared types for the memory plugin.

Defines the substrate-agnostic contract per the v1 minimal-contract decision
(2026-05-12-memory-v1-minimal-contract.md). No file handles or path
manipulation appear in this interface so future non-filesystem providers
(MCP-backed, etc.) can drop in cleanly.

Memory is append-only: there is no delete/update. Corrections are new
entries that consumers reconcile.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class Entry:
    """A memory entry: four frontmatter fields plus a free-markdown body.

    `type` is the semantic role (user | feedback | project | reference).
    `subject` is what the memory is about; it determines placement.
    They are independent.
    """

    name: str
    description: str
    type: str
    subject: str
    body: str


class MemoryCollisionError(Exception):
    """Raised by `put` when the resolved storage location already exists.

    Carries the resolved path/id so callers can decide policy (retry with
    a body-suffixed name, surface the error, etc.). The provider makes no
    policy choice beyond refusing to silently overwrite.
    """

    def __init__(self, path: str, message: str | None = None) -> None:
        super().__init__(message or f"memory entry already exists at {path}")
        self.path = path


class MemoryAmbiguousSubjectError(Exception):
    """Raised when subject resolution finds multiple candidates at the same depth.

    Callers can disambiguate by passing a path-shaped `subject`
    (e.g. `LOGOS/sophia`).
    """

    def __init__(
        self,
        subject: str,
        candidates: list[str],
        message: str | None = None,
    ) -> None:
        super().__init__(
            message
            or f"subject {subject!r} is ambiguous; candidates: {candidates!r}"
        )
        self.subject = subject
        self.candidates = candidates


class Provider(ABC):
    """Substrate-agnostic storage contract for memory entries.

    Implementations decide where and how entries are stored; this interface
    deals only in `Entry` values and opaque string identifiers returned by
    `put`. No file handles or path manipulation belong here.

    Append-only: no `delete`, no `update`.
    """

    @abstractmethod
    def list(
        self,
        type: str | None = None,
        subject: str | None = None,
    ) -> list[Entry]:
        """Return entries, optionally filtered by `type` and/or `subject`."""

    @abstractmethod
    def get(self, name: str, type: str) -> Entry | None:
        """Return the entry identified by (`name`, `type`), or None if absent."""

    @abstractmethod
    def put(self, entry: Entry) -> str:
        """Store `entry`; return the stored path/id.

        Raises `MemoryCollisionError` if the resolved location already
        exists. May raise `MemoryAmbiguousSubjectError` if subject
        resolution is ambiguous.
        """

    @abstractmethod
    def exists(self, name: str, type: str) -> bool:
        """Return True if an entry identified by (`name`, `type`) is stored."""
