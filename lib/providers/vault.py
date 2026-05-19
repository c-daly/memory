"""VaultProvider: filesystem-backed Provider with PARA-aware filing rule v2.

Resolves an entry's `subject` to a folder under a PARA-style vault
(`10-projects/`, `20-areas/`, `30-resources/`), then files the entry as
`<entity>/.memory/<YYYY-MM-DD>-<slug>.md` — a dot-prefixed,
tooling-managed subdir alongside the entity's other notes. The entry's
`type` lives in YAML frontmatter, not the path.

Subjects that don't resolve to a real PARA entity (or its alias) raise
`MemorySubjectNotFoundError`; the inbox fallback was removed in audit #6
(2026-05-17) to enforce entity-locality. `subject == "user"` is the one
non-entity placement and files at `<vault>/.memory/<file>`.

Placement logic is encapsulated in `_resolve_placement` so future
substrate-specific placement rules can swap in by replacing only that
one method.
"""

from __future__ import annotations

import os
import re
from datetime import date
from pathlib import Path

import yaml

from .base import (
    Entry,
    MemoryAmbiguousSubjectError,
    MemoryCollisionError,
    MemorySubjectNotFoundError,
    Provider,
)

PARA_ROOTS = ("10-projects", "20-areas", "30-resources")
INBOX = "00-inbox"
_REQUIRED_FRONTMATTER = ("name", "description", "type", "subject")
_ALIASES_FILENAME = ".memory-aliases.yaml"


def _slugify(name: str) -> str:
    """Kebab-case a name for use in filenames."""
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", name).strip("-").lower()
    return slug or "entry"


class VaultProvider(Provider):
    """Filesystem-backed Provider that files into a PARA-style vault."""

    def __init__(self, vault_root: Path | None = None) -> None:
        if vault_root is None:
            env = os.environ.get("MEMORY_VAULT_DIR")
            vault_root = Path(env) if env else Path.home() / "projects" / "vault"
        self.vault_root = Path(vault_root)
        # Alias for the substrate-agnostic Provider.root attribute that
        # callers (e.g. memory_writer) rely on to align their index-write
        # location with the provider's actual storage root.
        self.root = self.vault_root

    # -- placement (the v1 filing rule; isolated for v2 swap-in) ---------

    def _load_aliases(self) -> dict[str, str]:
        """Load `<vault>/.memory-aliases.yaml`. Empty dict if missing/invalid.

        Format: a YAML mapping from incoming-subject to canonical-subject:

            memory-plugin: memory
            constellation-v2: constellation

        A missing file, an unreadable file, malformed YAML, or non-mapping
        top-level content all return an empty dict — aliases are a
        convenience, never load-bearing for correctness.
        """
        alias_file = self.vault_root / _ALIASES_FILENAME
        if not alias_file.is_file():
            return {}
        try:
            text = alias_file.read_text(encoding="utf-8")
            data = yaml.safe_load(text) or {}
        except (OSError, UnicodeDecodeError, yaml.YAMLError):
            return {}
        if not isinstance(data, dict):
            return {}
        return {
            str(k): str(v)
            for k, v in data.items()
            if isinstance(k, str) and isinstance(v, str)
        }

    def _para_candidate_names(self) -> list[str]:
        """Sorted list of basenames of directories directly under PARA roots.

        Used to populate the candidate list in `MemorySubjectNotFoundError`
        so callers can offer the user a useful "did you mean..." surface.
        Walks only one level deep — nested project layouts (e.g.
        `LOGOS/sophia`) are addressed via path-shaped subjects, not by
        flattening every nested name into the candidate set.
        """
        names: list[str] = []
        for root in PARA_ROOTS:
            root_path = self.vault_root / root
            if root_path.is_dir():
                names.extend(
                    p.name for p in root_path.iterdir() if p.is_dir()
                )
        return sorted(set(names))

    def _try_subject_resolve(self, subject: str) -> Path | None:
        """Attempt to resolve `subject` to a PARA folder; return None on miss.

        Returns the matching directory `Path` if the subject resolves
        unambiguously to a PARA entity, or None if there's simply no
        match (which the caller may convert into either an alias lookup
        or a `MemorySubjectNotFoundError`).

        Raises:
            ValueError: invalid path-shaped subject (absolute or contains '..').
            MemoryAmbiguousSubjectError: flat subject matches multiple PARA
                entities at the same depth and cannot be disambiguated.
        """
        vault_resolved = self.vault_root.resolve()

        if "/" in subject:
            rel = Path(subject)
            if rel.is_absolute() or ".." in rel.parts:
                raise ValueError(
                    f"subject must be a vault-relative path without '..' "
                    f"segments; got {subject!r}"
                )
            for root in PARA_ROOTS:
                candidate = (self.vault_root / root / rel).resolve()
                # Defense in depth: a symlink inside the vault could escape
                # on resolution. Drop candidates that don't stay under the
                # resolved vault_root.
                if not candidate.is_relative_to(vault_resolved):
                    continue
                if candidate.is_dir():
                    return candidate
            return None

        matches: list[Path] = []
        for root in PARA_ROOTS:
            root_path = self.vault_root / root
            if not root_path.is_dir():
                continue
            for dirpath, dirnames, _ in os.walk(root_path):
                for d in dirnames:
                    if d != subject:
                        continue
                    candidate = Path(dirpath) / d
                    # os.walk does not follow symlinks by default, but it
                    # still surfaces a symlinked directory's *name* in
                    # `dirnames`. Resolve and bound to keep writes inside
                    # the vault.
                    if candidate.resolve().is_relative_to(vault_resolved):
                        matches.append(candidate)

        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            def depth(p: Path) -> int:
                return len(p.relative_to(self.vault_root).parts)

            shallowest = min(depth(p) for p in matches)
            shallow = [p for p in matches if depth(p) == shallowest]
            if len(shallow) == 1:
                return shallow[0]
            raise MemoryAmbiguousSubjectError(
                subject=subject,
                candidates=[str(p) for p in shallow],
            )

        return None

    def _resolve_subject_folder(self, subject: str) -> Path:
        """Map an entry's subject to a folder under vault_root.

        Resolution order:
        1. `subject == "user"` → vault root (special-case for user-scoped
           memories; not subject to alias lookup).
        2. Direct resolution against PARA entity directories.
        3. Alias lookup (from `<vault>/.memory-aliases.yaml`) only when
           direct resolution misses. Real PARA dirs win over aliases —
           an alias is a fallback for naming drift, not a redirect.
        4. If neither direct nor alias resolution finds a match, raise
           `MemorySubjectNotFoundError`. Memory entries must live close
           to their entity; silently filing into `00-inbox/` is a bug,
           not a tolerable default.

        Path-shaped subjects (containing '/') must be relative and free of
        '..' parts: a subject is a hint about *where in the vault* an
        entry belongs, never an escape hatch out of it.
        """
        if subject == "user":
            return self.vault_root

        direct = self._try_subject_resolve(subject)
        if direct is not None:
            return direct

        aliases = self._load_aliases()
        aliased = aliases.get(subject)
        if aliased is not None:
            via_alias = self._try_subject_resolve(aliased)
            if via_alias is not None:
                return via_alias
            raise MemorySubjectNotFoundError(
                subject=subject,
                alias=aliased,
                candidates=self._para_candidate_names(),
            )

        raise MemorySubjectNotFoundError(
            subject=subject,
            candidates=self._para_candidate_names(),
        )

    def _resolve_placement(self, entry: Entry) -> Path:
        """Return the full target path for `entry` under the v2 filing rule.

        Entries land in a `.memory/` (dot-prefixed) subdir under their
        entity. Dot-prefix marks the dir as plugin-managed (paralleling
        `.git/`, `.obsidian/`) and avoids collision with same-named
        PARA entities (`vault/10-projects/memory/` is the memory-plugin
        project dir; `vault/10-projects/.memory/` is bucket-level memory
        storage). `type` is frontmatter only; it does not appear in the
        path.
        """
        folder = self._resolve_subject_folder(entry.subject)
        filename = f"{date.today().isoformat()}-{_slugify(entry.name)}.md"
        return folder / ".memory" / filename

    def resolve_scope(self, subject: str) -> list["Entry"]:
        """Walk up from <subject>/.memory/ through ancestor .memory/ dirs.

        Order: nearest-first (entity -> bucket -> vault root). Dedup key
        is (type, name, subject); the nearest occurrence wins. Unknown
        subject returns an empty list (omit_section).
        """
        try:
            entity_dir = self._resolve_subject_folder(subject)
        except (MemorySubjectNotFoundError, MemoryAmbiguousSubjectError, ValueError):
            return []

        vault_root_resolved = self.vault_root.resolve()
        memory_dirs: list[Path] = []
        cur = entity_dir.resolve()
        # Walk up until we cross vault_root. Use `is_relative_to` for the
        # safety check to match the existing in-vault check in
        # `_try_subject_resolve`.
        while True:
            try:
                if not cur.is_relative_to(vault_root_resolved):
                    break
            except (OSError, ValueError):
                break
            mem = cur / ".memory"
            if mem.is_dir():
                memory_dirs.append(mem)
            if cur == vault_root_resolved:
                break
            parent = cur.parent
            try:
                if not parent.resolve().is_relative_to(vault_root_resolved):
                    # Walked above vault_root somehow (symlinks, etc); stop.
                    break
            except (OSError, ValueError):
                break
            cur = parent

        seen: set[tuple[str, str, str]] = set()
        results: list["Entry"] = []
        for mem in memory_dirs:
            for md in sorted(mem.glob("*.md")):
                entry = self._parse(md.read_text(encoding="utf-8"))
                if entry is None:
                    continue
                key = (entry.type, entry.name, entry.subject)
                if key in seen:
                    continue
                seen.add(key)
                results.append(entry)
        return results

    # -- serialization ---------------------------------------------------

    @staticmethod
    def _parse(text: str) -> Entry | None:
        """Parse a memory file. Return None if it's not a valid memory entry.

        Frontmatter is delimited by lines that are *only* '---'. The
        previous text.split delimiter could fire inside the frontmatter
        for any field whose value happened to end with '---' on a line
        (yaml.safe_dump emits unquoted bare values directly, so a
        description ending in '---' produces exactly that pattern).
        """
        lines = text.splitlines(keepends=True)
        if not lines or lines[0].rstrip("\r\n") != "---":
            return None
        end = None
        for i in range(1, len(lines)):
            if lines[i].rstrip("\r\n") == "---":
                end = i
                break
        if end is None:
            return None
        try:
            data = yaml.safe_load("".join(lines[1:end])) or {}
        except yaml.YAMLError:
            return None
        if not isinstance(data, dict):
            return None
        if not all(k in data for k in _REQUIRED_FRONTMATTER):
            return None
        body = "".join(lines[end + 1:])
        if body.startswith("\n"):
            body = body[1:]
        return Entry(
            name=str(data["name"]),
            description=str(data["description"]),
            type=str(data["type"]),
            subject=str(data["subject"]),
            body=body,
        )

    # -- index-backed fast path (MEMORY.md) ------------------------------

    # Format owned by lib/index.py in the writer/reader layer; kept here as
    # the read-side contract so VaultProvider can answer get/list without
    # rglob-ing the entire vault. SEP and bullet shape match index.py.
    _INDEX_SEP = "\u00b7"
    _INDEX_BULLET_RE = re.compile(
        r"^- \[\[(?P<path>[^|\]]+)\|(?P<name>[^\]]+)\]\]"
        + r"\s+\u00b7\s+type:(?P<type>\S+)\s+subject:(?P<subject>\S+)"
        + r"\s+\u00b7\s+"
    )

    def _index_path(self) -> Path:
        return self.vault_root / "MEMORY.md"

    def _index_lookup_path(self, name: str, type: str) -> Path | None:
        """Return absolute path for (name, type) via MEMORY.md, or None.

        None means either MEMORY.md is missing, the entry is not indexed,
        or the indexed file no longer exists on disk; in any of those
        cases the caller should fall back to the full scan.
        """
        idx = self._index_path()
        if not idx.is_file():
            return None
        try:
            text = idx.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return None
        for line in text.splitlines():
            m = self._INDEX_BULLET_RE.match(line)
            if m is None:
                continue
            if m.group("name") == name and m.group("type") == type:
                full = self.vault_root / m.group("path")
                return full if full.is_file() else None
        return None

    # -- Provider API ----------------------------------------------------

    def put(self, entry: Entry) -> str:
        # Logical-entry collision: an entry with the same (name, type)
        # may already exist under a different date-stamped filename.
        # Without this check, day-N put() succeeds while day-1 still
        # exists, leaving two files for one logical entry and making
        # exists()/get() nondeterministic.
        if self.exists(entry.name, entry.type):
            raise MemoryCollisionError(
                path=f"<{entry.type}:{entry.name}> already exists in vault"
            )
        target = self._resolve_placement(entry)
        if target.exists():
            raise MemoryCollisionError(path=str(target))
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(entry.to_markdown(), encoding="utf-8")
        return str(target)

    def _iter_entries(self):
        """Yield (path, Entry) for every valid memory file under vault_root."""
        if not self.vault_root.is_dir():
            return
        for path in sorted(self.vault_root.rglob("*.md")):
            if not path.is_file():
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            entry = self._parse(text)
            if entry is not None:
                yield path, entry

    def get(self, name: str, type: str) -> Entry | None:
        path = self._index_lookup_path(name, type)
        if path is not None:
            try:
                entry = self._parse(path.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError):
                entry = None
            if entry is not None and entry.name == name and entry.type == type:
                return entry
            # indexed file failed to parse cleanly; fall through to scan
        for _, entry in self._iter_entries():
            if entry.name == name and entry.type == type:
                return entry
        return None

    def exists(self, name: str, type: str) -> bool:
        return self.get(name, type) is not None

    def list(
        self,
        type: str | None = None,
        subject: str | None = None,
    ) -> list[Entry]:
        # Always scan, never trust the index alone: a Provider direct-put
        # (tests, alternate writers) doesn't update MEMORY.md, so an
        # index-only list() would silently drop those entries. list() is
        # inherently O(matching_entries); the win that motivated the
        # fast path was get()'s O(N) — that one stays index-backed.
        results: list[Entry] = []
        for _, entry in self._iter_entries():
            if type is not None and entry.type != type:
                continue
            if subject is not None and entry.subject != subject:
                continue
            results.append(entry)
        return results
