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
    """If _default_providers itself raises, brief() returns a skeleton, never raises."""
    def _boom():
        raise RuntimeError("factory failure (simulated)")
    monkeypatch.setattr(memory_reader, "_default_providers", _boom)

    out = memory_reader.brief()

    assert isinstance(out, str)
    assert "_No providers contributed._" in out


def test_brief_includes_entity_inventory(tmp_path: Path, monkeypatch) -> None:
    """Non-user subjects with entries appear in the entity-inventory section."""
    root = tmp_path / "vault"
    (root / ".memory").mkdir(parents=True)
    (root / "10-projects" / "alpha").mkdir(parents=True)
    # Write an entry with subject=alpha through the public API path: file
    # directly under the resolved entity dir, parsed via provider.list().
    alpha_entry = Entry(
        name="ent-alpha", description="alpha first entry",
        type="project", subject="alpha", body="b\n",
    )
    (root / "10-projects" / "alpha" / f"{date.today().isoformat()}-ent-alpha.md").write_text(
        alpha_entry.to_markdown()
    )
    # Rebuild the index so memory_reader.list() sees it.
    monkeypatch.setenv("MEMORY_VAULT_DIR", str(root))
    import index
    index.rebuild_from_scan(root)

    out = memory_reader.brief()

    assert "## Entities with memory" in out
    assert "alpha" in out
    assert "alpha first entry" in out


def test_brief_provider_list_failure_omits_section(tmp_path: Path, monkeypatch) -> None:
    """If provider.list() raises, the brief still returns a string (omit_section)."""
    class _FailingProvider:
        def list(self, type=None, subject=None):
            raise RuntimeError("simulated list() failure")

    monkeypatch.setattr(memory_reader, "_default_providers", lambda: [_FailingProvider()])

    out = memory_reader.brief()

    assert isinstance(out, str)
    # No sections rendered → fallback skeleton.
    assert "_No entries._" in out or "_No providers contributed._" in out
