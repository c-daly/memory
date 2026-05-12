"""MEMORY.md index module.

Self-contained; owns the MEMORY.md format and operations on it.
No imports from providers.

MEMORY.md bullet format (one per line):
    - [[<path>|<name>]] SEP type:<T> subject:<S> SEP <description>

Where SEP is U+00B7 (middle dot). <path> is relative to vault_root.
"""
from __future__ import annotations

import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path

import yaml

INDEX_FILENAME = "MEMORY.md"
INDEX_HEADER = (
    "# MEMORY\n\n"
    "Auto-maintained by memory_writer. One bullet per entry. Do not hand-edit.\n\n"
)

_SEP = "\u00b7"

_BULLET_RE = re.compile(
    r"^- \[\[(?P<path>[^|\]]+)\|(?P<name>[^\]]+)\]\]"
    + r"\s+" + re.escape(_SEP) + r"\s+type:(?P<type>\S+)\s+subject:(?P<subject>\S+)"
    + r"\s+" + re.escape(_SEP) + r"\s+(?P<description>.*)$"
)


@dataclass
class IndexEntry:
    name: str
    type: str
    subject: str
    path: str
    description: str


def _index_path(vault_root: Path) -> Path:
    return Path(vault_root) / INDEX_FILENAME


def _format_bullet(entry: IndexEntry) -> str:
    return (
        f"- [[{entry.path}|{entry.name}]] {_SEP} "
        f"type:{entry.type} subject:{entry.subject} {_SEP} {entry.description}"
    )


def _atomic_write(target: Path, text: str) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=target.name + ".", suffix=".tmp", dir=str(target.parent)
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.replace(tmp_name, target)
    except Exception:
        try:
            os.unlink(tmp_name)
        except FileNotFoundError:
            pass
        raise


def read(vault_root: Path) -> list[IndexEntry]:
    """Parse <vault_root>/MEMORY.md. Return [] if missing. Skip malformed lines silently."""
    path = _index_path(vault_root)
    if not path.exists():
        return []
    entries: list[IndexEntry] = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.rstrip("\n")
            if not line.startswith("- [["):
                continue
            m = _BULLET_RE.match(line)
            if not m:
                continue
            entries.append(
                IndexEntry(
                    name=m.group("name").strip(),
                    type=m.group("type").strip(),
                    subject=m.group("subject").strip(),
                    path=m.group("path").strip(),
                    description=m.group("description").strip(),
                )
            )
    return entries


def append(
    vault_root: Path,
    name: str,
    type: str,
    subject: str,
    path: str,
    description: str,
) -> None:
    """Append a bullet line for the new entry; create MEMORY.md with header if missing.

    `path` is relative to vault_root. Write is atomic (tempfile + os.replace).
    """
    index_file = _index_path(vault_root)
    entry = IndexEntry(
        name=name, type=type, subject=subject, path=path, description=description
    )
    bullet = _format_bullet(entry)

    if index_file.exists():
        existing = index_file.read_text(encoding="utf-8")
        if existing and not existing.endswith("\n"):
            existing += "\n"
        new_text = existing + bullet + "\n"
    else:
        new_text = INDEX_HEADER + bullet + "\n"

    _atomic_write(index_file, new_text)


def lookup(vault_root: Path, name: str, type: str) -> str | None:
    """Return the path of the IndexEntry matching (name, type), else None."""
    for entry in read(vault_root):
        if entry.name == name and entry.type == type:
            return entry.path
    return None


def lookup_subject(vault_root: Path, subject: str) -> str | None:
    """Return folder (parent of entry path) for any IndexEntry whose subject matches, else None.

    Serves as the subject-resolution cache for memory_writer.
    """
    for entry in read(vault_root):
        if entry.subject == subject:
            parent = str(Path(entry.path).parent)
            return parent if parent not in ("", ".") else ""
    return None


def _parse_frontmatter(text: str) -> dict | None:
    """Parse YAML frontmatter from a Markdown file content. Return dict or None."""
    if not text.startswith("---"):
        return None
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None
    end = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end = i
            break
    if end is None:
        return None
    fm_text = "\n".join(lines[1:end])
    try:
        data = yaml.safe_load(fm_text)
    except yaml.YAMLError:
        return None
    if not isinstance(data, dict):
        return None
    return data


def rebuild_from_scan(vault_root: Path) -> int:
    """Walk vault_root recursively; rebuild MEMORY.md from .md files with all 4 fields.

    Returns the count of indexed entries.
    """
    vault_root = Path(vault_root)
    entries: list[IndexEntry] = []

    for md_path in sorted(vault_root.rglob("*.md")):
        if md_path.resolve() == _index_path(vault_root).resolve():
            continue
        try:
            text = md_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        fm = _parse_frontmatter(text)
        if not fm:
            continue
        name = fm.get("name")
        description = fm.get("description")
        type_ = fm.get("type")
        subject = fm.get("subject")
        if not (name and description and type_ and subject):
            continue
        rel = md_path.relative_to(vault_root).as_posix()
        entries.append(
            IndexEntry(
                name=str(name),
                type=str(type_),
                subject=str(subject),
                path=rel,
                description=str(description),
            )
        )

    body = INDEX_HEADER + "".join(_format_bullet(e) + "\n" for e in entries)
    _atomic_write(_index_path(vault_root), body)
    return len(entries)
