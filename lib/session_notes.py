# lib/session_notes.py
"""Lightweight in-session notes: cheap anchors the main agent appends during a
session, folded into the record by session_recorder at PreCompact/SessionEnd.

Slice-1 limitation: a single pending file under the plugin var dir, so concurrent
sessions interleave. Acceptable for now; revisit with session-id scoping later.
"""
from __future__ import annotations

from pathlib import Path


def notes_path(root: Path) -> Path:
    return Path(root) / "var" / "pending-notes.md"


def append_note(text: str, root: Path, stamp: str) -> None:
    p = notes_path(root)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        f.write(f"- [{stamp}] {text.strip()}\n")


def read_notes(root: Path) -> str:
    p = notes_path(root)
    if not p.is_file():
        return ""
    return p.read_text(encoding="utf-8")


def clear_notes(root: Path) -> None:
    p = notes_path(root)
    if p.exists():
        p.unlink()
