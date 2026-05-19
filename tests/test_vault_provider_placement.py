"""Tests for the <entity>/.memory/<file> placement contract."""
from __future__ import annotations

from datetime import date
from pathlib import Path

from providers.base import Entry
from providers.vault import VaultProvider


def _make_vault(tmp_path: Path) -> Path:
    """Create a minimal PARA vault with one project."""
    root = tmp_path / "vault"
    (root / "10-projects" / "agent-swarm").mkdir(parents=True)
    return root


def test_entry_filed_under_entity_dot_memory_subdir(tmp_path: Path) -> None:
    root = _make_vault(tmp_path)
    provider = VaultProvider(vault_root=root)
    entry = Entry(
        name="example",
        description="example description",
        type="feedback",
        subject="agent-swarm",
        body="body content\n",
    )

    stored_path = provider.put(entry)

    today = date.today().isoformat()
    expected = root / "10-projects" / "agent-swarm" / ".memory" / f"{today}-example.md"
    assert Path(stored_path) == expected
    assert expected.exists()


def test_entry_type_not_in_path(tmp_path: Path) -> None:
    """`type` is frontmatter, not a path segment."""
    root = _make_vault(tmp_path)
    provider = VaultProvider(vault_root=root)
    for entry_type in ("user", "feedback", "project", "reference"):
        entry = Entry(
            name=f"e-{entry_type}",
            description="x",
            type=entry_type,
            subject="agent-swarm",
            body="b\n",
        )
        path = Path(provider.put(entry))
        # The path must NOT contain a directory segment named after the type.
        assert entry_type not in path.parts


def test_user_subject_lands_under_vault_root_dot_memory(tmp_path: Path) -> None:
    """subject == 'user' continues to map to vault root, now into .memory/ subdir."""
    root = _make_vault(tmp_path)
    provider = VaultProvider(vault_root=root)
    entry = Entry(
        name="cross-cutting",
        description="x",
        type="user",
        subject="user",
        body="b\n",
    )

    stored_path = Path(provider.put(entry))

    assert stored_path.parent == root / ".memory"
