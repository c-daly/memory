"""memory_reader: high-level read entry-point used by callers and the CLI/server.

Two operations:
- list(type=None, subject=None) -> list[Entry] — consults MEMORY.md as the index of record
- get(name, type) -> Entry | None — looks up the path via the index, parses the file

If MEMORY.md is missing or empty, list/get fall back to rebuild_from_scan once.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

import yaml

import index
from providers.base import Entry

log = logging.getLogger(__name__)


def _resolve_vault_root() -> Path:
    env = os.environ.get("MEMORY_VAULT_DIR")
    return Path(env) if env else Path.home() / "projects" / "vault"


def _parse_entry_file(abs_path: Path) -> Entry | None:
    """Parse a memory entry markdown file (YAML frontmatter + body) into an Entry.

    Frontmatter is delimited by lines that are *only* '---'. A bare
    substring split would fire inside the frontmatter for any field
    whose value contains '---' (e.g. description='setup --- teardown'),
    making the entry silently invisible on read.
    """
    try:
        text = abs_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        # Non-UTF-8 bytes in an entry file shouldn't crash list()/get();
        # treat the file as malformed and skip it, same as a read error.
        return None
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
        fm = yaml.safe_load("".join(lines[1:end])) or {}
    except yaml.YAMLError:
        return None
    if not isinstance(fm, dict):
        return None
    body = "".join(lines[end + 1:]).lstrip("\n")
    required = ("name", "description", "type", "subject")
    if not all(fm.get(k) for k in required):
        return None
    return Entry(
        name=str(fm["name"]),
        description=str(fm["description"]),
        type=str(fm["type"]),
        subject=str(fm["subject"]),
        body=body,
    )


def list(type: str | None = None, subject: str | None = None) -> "list[Entry]":  # noqa: A001
    """List memory entries from MEMORY.md, optionally filtered by type and/or subject."""
    vault_root = _resolve_vault_root()
    entries = index.read(vault_root)
    if not entries:
        # Docstring contract: fall back to rebuild whenever the index is
        # *missing or empty*. The previous \`if not memory_md.exists()\`
        # guard only covered the missing case — a header-only or
        # truncated MEMORY.md silently returned an empty list.
        log.warning(
            "MEMORY.md missing or empty at %s; rebuilding from filesystem scan",
            vault_root / "MEMORY.md",
        )
        index.rebuild_from_scan(vault_root)
        entries = index.read(vault_root)
    result: "list[Entry]" = []
    for ie in entries:
        if type is not None and ie.type != type:
            continue
        if subject is not None and ie.subject != subject:
            continue
        full = vault_root / ie.path
        parsed = _parse_entry_file(full)
        if parsed is not None:
            result.append(parsed)
    return result


def get(name: str, type: str) -> Entry | None:  # noqa: A002
    """Look up an entry by (name, type) via the index; return parsed Entry or None.

    Honors the module-level contract: if MEMORY.md is missing or empty,
    rebuild from a filesystem scan once and retry the lookup. A miss on
    a non-empty index is treated as a real miss and *not* re-scanned —
    only missing/empty index triggers fallback.
    """
    vault_root = _resolve_vault_root()
    rel = index.lookup(vault_root, name, type)
    if rel is None:
        if not index.read(vault_root):
            log.warning(
                "MEMORY.md missing or empty at %s; rebuilding from filesystem scan",
                vault_root / "MEMORY.md",
            )
            index.rebuild_from_scan(vault_root)
            rel = index.lookup(vault_root, name, type)
        if rel is None:
            return None
    full = vault_root / rel
    return _parse_entry_file(full)
