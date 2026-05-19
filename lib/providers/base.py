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

    def to_markdown(self) -> str:
        """Render this Entry as a YAML-frontmatter markdown document.

        Frontmatter is serialized via yaml.safe_dump so values that
        would otherwise break naive interpolation (e.g. a description
        containing '#' which YAML treats as a comment, or ':' which
        starts a key, or embedded newlines) round-trip correctly.

        The body is normalized to end with a newline so the output is
        itself a valid memory file: piping get() into a file and
        replaying it through write() round-trips the entry.
        """
        import yaml as _yaml
        frontmatter = {
            "name": self.name,
            "description": self.description,
            "type": self.type,
            "subject": self.subject,
        }
        fm_text = _yaml.safe_dump(frontmatter, sort_keys=False).strip()
        body = self.body if self.body.endswith("\n") else self.body + "\n"
        return f"---\n{fm_text}\n---\n{body}"


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


class MemorySubjectNotFoundError(Exception):
    """Raised when subject does not resolve to any PARA entity directory.

    Memory entries must live close to their entity. When a `subject`
    doesn't match any directory under `10-projects/`, `20-areas/`, or
    `30-resources/` (and isn't the `user` special case), the provider
    refuses to silently file the entry in `00-inbox/` — that would
    route memory away from its entity. Callers should fix the subject
    or register an alias in `<vault>/.memory-aliases.yaml`.

    Carries the original subject, the alias (if one was followed and
    still failed to resolve), and the available PARA entity names so
    callers can surface a helpful error.
    """

    def __init__(
        self,
        subject: str,
        candidates: list[str],
        alias: str | None = None,
        message: str | None = None,
    ) -> None:
        if message is None:
            via_alias = f" (via alias to {alias!r})" if alias else ""
            preview = ", ".join(candidates[:8])
            if len(candidates) > 8:
                preview += f", ... ({len(candidates) - 8} more)"
            message = (
                f"subject {subject!r}{via_alias} did not match any PARA "
                f"project directory; available: [{preview}]"
            )
        super().__init__(message)
        self.subject = subject
        self.alias = alias
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

    def resolve_scope(self, subject: str) -> list[Entry]:
        """Return entries in scope for `subject`.

        Scope is a vertical walk-up from `subject`'s entity dir through
        every ancestor `.memory/` dir, nearest-first, deduplicated by
        (type, name, subject). Lateral relations are explicitly out of
        scope (v2 design decision: cross-references emerge from content).

        Default: NotImplementedError. Failure mode in production
        dispatchers is `omit_section` — log and drop, never raise.
        """
        raise NotImplementedError(
            f"{type(self).__name__} does not implement resolve_scope()"
        )
