"""Tests for memory_reader.resolve_scope() dispatch."""
from __future__ import annotations

from datetime import date
from pathlib import Path

import memory_reader
from providers.base import Entry


def _seed(tmp_path: Path) -> Path:
    root = tmp_path / "vault"
    (root / "10-projects" / "alpha" / ".memory").mkdir(parents=True)
    e = Entry(name="ent1", description="alpha-scoped", type="project", subject="alpha", body="b\n")
    (root / "10-projects" / "alpha" / ".memory" / f"{date.today().isoformat()}-ent1.md").write_text(e.to_markdown())
    return root


def test_resolve_scope_returns_entries_for_subject(tmp_path: Path, monkeypatch) -> None:
    root = _seed(tmp_path)
    monkeypatch.setenv("MEMORY_VAULT_DIR", str(root))

    entries = memory_reader.resolve_scope("alpha")

    assert any(e.name == "ent1" for e in entries)


def test_resolve_scope_unknown_subject_returns_empty(tmp_path: Path, monkeypatch) -> None:
    root = _seed(tmp_path)
    monkeypatch.setenv("MEMORY_VAULT_DIR", str(root))

    entries = memory_reader.resolve_scope("nope")

    assert entries == []
