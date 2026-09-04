"""memory_reader: high-level read entry-point used by callers and the CLI/server.

Two operations:
- list(type=None, subject=None) -> list[Entry] — consults MEMORY.md as the index of record
- get(name, type) -> Entry | None — looks up the path via the index, parses the file

If MEMORY.md is missing or empty, list/get fall back to rebuild_from_scan once.
"""
from __future__ import annotations

import logging
from pathlib import Path

import yaml

import index
from config import resolve_vault_root as _resolve_vault_root
from providers.base import Entry

log = logging.getLogger(__name__)


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
    rebuild from a filesystem scan once and retry the lookup.

    A miss on a non-empty index falls back to a filesystem lookup for that one
    name. Promotion removes an entry's line from the index while leaving the
    file in place, so "not listed" no longer implies "not present" -- and a
    promotion's `promotes` tag has to stay followable to the entry it names.
    The fallback reads files and never rewrites the index.
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
            # The index lists *current answers*; the entry files are the
            # record. A promoted-away entry is deliberately absent from the
            # index but still on disk, and its promotion's `promotes` tag
            # points at it by name -- so a miss falls back to the filesystem
            # rather than reporting the entry gone. Without this the tag would
            # name something nothing can fetch.
            return _find_entry_on_disk(vault_root, name, type)
    full = vault_root / rel
    return _parse_entry_file(full)


def _find_entry_on_disk(vault_root: Path, name: str, type: str) -> Entry | None:
    """Scan `.memory/` directories for the entry with this name and type.

    Only reached on an index miss, which is rare: either a promoted-away entry
    being followed from a promotion's tag, or a name that was never written.
    """
    for path in sorted(vault_root.rglob(".memory/*.md")):
        entry = _parse_entry_file(path)
        if entry is not None and entry.name == name and entry.type == type:
            return entry
    return None


def _default_providers() -> list["Provider"]:
    """Return the configured provider list for this plugin.

    v2: a single VaultProvider rooted at MEMORY_VAULT_DIR. Future
    plurality is an interface concession; today this returns a list of
    one. Callers iterating the list will pick up additional providers
    automatically when registered.
    """
    from providers.vault import VaultProvider
    return [VaultProvider(vault_root=_resolve_vault_root())]


def brief() -> str:
    """Compose memory's session-start brief from provider data.

    Two sections:
    1. User-level entries (subject == "user"), bulleted.
    2. Entity inventory: each subject (other than "user") with at least
       one entry, with the first entry's description as a one-line summary.

    Composition is a consumer concern; providers only expose raw data.
    Failure mode: omit_section — provider and factory failures are
    logged and dropped, never raise.
    """
    try:
        providers = _default_providers()
    except Exception as exc:  # noqa: BLE001 — omit_section by contract
        log.warning("provider factory failed: %s", exc)
        return "# Memory\n\n_No providers contributed._\n"

    user_entries: list = []
    entries_by_subject: dict[str, list] = {}
    for provider in providers:
        try:
            all_entries = provider.list()
        except Exception as exc:  # noqa: BLE001
            log.warning(
                "provider %s list() failed: %s", type(provider).__name__, exc,
            )
            continue
        for entry in all_entries:
            if entry.subject == "user":
                user_entries.append(entry)
            else:
                entries_by_subject.setdefault(entry.subject, []).append(entry)

    sections: list[str] = []
    if user_entries:
        bullets = [
            f"- {e.name} — {e.description}"
            for e in sorted(user_entries, key=lambda e: e.name)
        ]
        sections.append("## User-level\n" + "\n".join(bullets))
    if entries_by_subject:
        inv_bullets = []
        for subject in sorted(entries_by_subject):
            first = sorted(entries_by_subject[subject], key=lambda e: e.name)[0]
            inv_bullets.append(f"- {subject} — {first.description}")
        sections.append("## Entities with memory\n" + "\n".join(inv_bullets))

    if not sections:
        return "# Memory\n\n_No entries._\n"
    return "# Memory\n\n" + "\n\n".join(sections) + "\n"


def resolve_scope(subject: str) -> list[Entry]:
    """Aggregate in-scope entries for `subject` across registered providers.

    Provider failures AND factory failures are logged and dropped
    (omit_section). Dedup across providers on (type, name, subject);
    nearest-first order is preserved per provider.
    """
    try:
        providers = _default_providers()
    except Exception as exc:  # noqa: BLE001
        log.warning("provider factory failed: %s", exc)
        return []

    seen: set[tuple[str, str, str]] = set()
    results: list[Entry] = []
    for provider in providers:
        try:
            piece = provider.resolve_scope(subject)
        except Exception as exc:  # noqa: BLE001
            log.warning(
                "provider %s resolve_scope(%r) failed: %s",
                type(provider).__name__, subject, exc,
            )
            continue
        for entry in piece:
            key = (entry.type, entry.name, entry.subject)
            if key in seen:
                continue
            seen.add(key)
            results.append(entry)
    return results
