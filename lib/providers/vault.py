"""VaultProvider: filesystem-backed Provider with PARA-aware filing rule v1.

Resolves an entry's `subject` to a folder under a PARA-style vault
(`10-projects/`, `20-areas/`, `30-resources/`), then files the entry as
`<folder>/<type>/<YYYY-MM-DD>-<slug>.md`. Unrecognized subjects fall into
`00-inbox/`; `subject == "user"` files at the vault root.

Placement logic is encapsulated in `_resolve_placement` so v2's
configurable, .gitignore-style placement rules can swap in by replacing
only that one method.
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
    Provider,
)

PARA_ROOTS = ("10-projects", "20-areas", "30-resources")
INBOX = "00-inbox"
_REQUIRED_FRONTMATTER = ("name", "description", "type", "subject")


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

    # -- placement (the v1 filing rule; isolated for v2 swap-in) ---------

    def _resolve_subject_folder(self, subject: str) -> Path:
        """Map an entry's subject to a folder under vault_root."""
        if "/" in subject:
            rel = Path(subject)
            for root in PARA_ROOTS:
                candidate = self.vault_root / root / rel
                if candidate.is_dir():
                    return candidate
            return self.vault_root / INBOX

        matches: list[Path] = []
        for root in PARA_ROOTS:
            root_path = self.vault_root / root
            if not root_path.is_dir():
                continue
            for dirpath, dirnames, _ in os.walk(root_path):
                for d in dirnames:
                    if d == subject:
                        matches.append(Path(dirpath) / d)

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

        if subject == "user":
            return self.vault_root
        return self.vault_root / INBOX

    def _resolve_placement(self, entry: Entry) -> Path:
        """Return the full target path for `entry` under the v1 filing rule."""
        folder = self._resolve_subject_folder(entry.subject)
        filename = f"{date.today().isoformat()}-{_slugify(entry.name)}.md"
        return folder / entry.type / filename

    # -- serialization ---------------------------------------------------

    @staticmethod
    def _serialize(entry: Entry) -> str:
        frontmatter = {
            "name": entry.name,
            "description": entry.description,
            "type": entry.type,
            "subject": entry.subject,
        }
        fm_text = yaml.safe_dump(frontmatter, sort_keys=False).strip()
        return f"---\n{fm_text}\n---\n{entry.body}"

    @staticmethod
    def _parse(text: str) -> Entry | None:
        """Parse a memory file. Return None if it's not a valid memory entry."""
        if not text.startswith("---\n"):
            return None
        try:
            _, fm_text, body = text.split("---\n", 2)
        except ValueError:
            return None
        try:
            data = yaml.safe_load(fm_text) or {}
        except yaml.YAMLError:
            return None
        if not isinstance(data, dict):
            return None
        if not all(k in data for k in _REQUIRED_FRONTMATTER):
            return None
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
        except OSError:
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
        target.write_text(self._serialize(entry), encoding="utf-8")
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
            except OSError:
                continue
            entry = self._parse(text)
            if entry is not None:
                yield path, entry

    def get(self, name: str, type: str) -> Entry | None:
        path = self._index_lookup_path(name, type)
        if path is not None:
            try:
                entry = self._parse(path.read_text(encoding="utf-8"))
            except OSError:
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
