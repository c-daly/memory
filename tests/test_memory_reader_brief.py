"""Tests for memory_reader.brief() dispatch + stitching."""
from __future__ import annotations

from datetime import date
from pathlib import Path

import memory_reader
from providers.base import Entry


def _seed(tmp_path: Path) -> Path:
    root = tmp_path / "vault"
    (root / ".memory").mkdir(parents=True)
    (root / "10-projects" / "alpha" / ".memory").mkdir(parents=True)
    e = Entry(name="x", description="hello", type="user", subject="user", body="b\n")
    (root / ".memory" / f"{date.today().isoformat()}-x.md").write_text(e.to_markdown())
    return root


def test_brief_returns_string(tmp_path: Path, monkeypatch) -> None:
    root = _seed(tmp_path)
    monkeypatch.setenv("MEMORY_VAULT_DIR", str(root))

    out = memory_reader.brief()

    assert isinstance(out, str)
    assert "x" in out
    assert "hello" in out


def test_brief_includes_provider_heading(tmp_path: Path, monkeypatch) -> None:
    root = _seed(tmp_path)
    monkeypatch.setenv("MEMORY_VAULT_DIR", str(root))

    out = memory_reader.brief()

    assert "# Memory" in out


def test_brief_factory_failure_does_not_propagate(tmp_path: Path, monkeypatch) -> None:
    """If the provider factory itself raises, dispatch returns skeleton instead of crashing."""
    monkeypatch.setenv("MEMORY_VAULT_DIR", "/nonexistent/absolutely-not-here")

    out = memory_reader.brief()

    assert isinstance(out, str)
