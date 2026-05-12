"""Filesystem-backed `Provider` with a flat layout.

This provider is intentionally simple: every entry lives directly under
`root` as a single markdown file with YAML frontmatter. It is the v1 test
fixture provider; the richer filing rule lives in `VaultProvider`.

File format::

    ---
    name: ...
    description: ...
    type: ...
    subject: ...
    ---
    <body>

Filename: ``<YYYY-MM-DD>-<type>-<slug>.md`` where ``slug`` is the
kebab-cased ``entry.name`` and the date is todays date at write time.
"""

from __future__ import annotations

import datetime
import pathlib
import re

import yaml

from .base import Entry, MemoryCollisionError, Provider

_SLUG_NONWORD = re.compile(r"[^a-z0-9]+")


def _kebab(name: str) -> str:
    """Lowercase, hyphen-separated slug suitable for a filename component."""
    slug = _SLUG_NONWORD.sub("-", name.lower()).strip("-")
    return slug or "entry"


def _parse(text: str) -> tuple[dict, str]:
    """Split a markdown-with-frontmatter document into (meta, body)."""
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---\n", 4)
    if end == -1:
        return {}, text
    data = yaml.safe_load(text[4:end])
    meta = data if isinstance(data, dict) else {}
    body = text[end + 5 :]
    return meta, body


class FilesystemProvider(Provider):
    """Flat filesystem provider: one markdown file per entry under `root`."""

    def __init__(self, root: pathlib.Path) -> None:
        if not isinstance(root, pathlib.Path):
            raise TypeError(f"root must be a pathlib.Path, got {type(root).__name__}")
        self.root = root

    def put(self, entry: Entry) -> str:
        self.root.mkdir(parents=True, exist_ok=True)
        # Logical-entry collision: an entry with the same (name, type)
        # may already exist under a different date-stamped filename.
        # Without this check, day-N put() succeeds while day-1 still
        # exists, leaving two files for one logical entry.
        if self.exists(entry.name, entry.type):
            raise MemoryCollisionError(
                path=f"<{entry.type}:{entry.name}> already exists in root"
            )
        date = datetime.date.today().isoformat()
        slug = _kebab(entry.name)
        target = self.root / f"{date}-{entry.type}-{slug}.md"
        if target.exists():
            raise MemoryCollisionError(path=str(target))
        meta = {
            "name": entry.name,
            "description": entry.description,
            "type": entry.type,
            "subject": entry.subject,
        }
        frontmatter = yaml.safe_dump(meta, sort_keys=False).rstrip("\n")
        target.write_text(f"---\n{frontmatter}\n---\n{entry.body}", encoding="utf-8")
        return str(target)

    def get(self, name: str, type: str) -> Entry | None:
        if not self.root.exists():
            return None
        slug = _kebab(name)
        suffix = f"-{type}-{slug}.md"
        for path in self.root.glob(f"*{suffix}"):
            meta, body = _parse(path.read_text(encoding="utf-8"))
            return Entry(
                name=meta.get("name", name),
                description=meta.get("description", ""),
                type=meta.get("type", type),
                subject=meta.get("subject", ""),
                body=body,
            )
        return None

    def exists(self, name: str, type: str) -> bool:
        return self.get(name, type) is not None

    def list(
        self,
        type: str | None = None,
        subject: str | None = None,
    ) -> list[Entry]:
        if not self.root.exists():
            return []
        entries: list[Entry] = []
        for path in sorted(self.root.glob("*.md")):
            meta, body = _parse(path.read_text(encoding="utf-8"))
            entry = Entry(
                name=meta.get("name", path.stem),
                description=meta.get("description", ""),
                type=meta.get("type", ""),
                subject=meta.get("subject", ""),
                body=body,
            )
            if type is not None and entry.type != type:
                continue
            if subject is not None and entry.subject != subject:
                continue
            entries.append(entry)
        return entries
