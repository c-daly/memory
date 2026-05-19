"""Tests for VaultProvider.brief()."""
from __future__ import annotations

from datetime import date
from pathlib import Path

from providers.base import Entry
from providers.vault import VaultProvider


def _seed_vault(tmp_path: Path) -> Path:
    """Create a vault with one user-level entry and two entities with .memory dirs."""
    root = tmp_path / "vault"
    (root / ".memory").mkdir(parents=True)
    (root / "10-projects" / "alpha" / ".memory").mkdir(parents=True)
    (root / "10-projects" / "beta" / ".memory").mkdir(parents=True)
    # A third entity without a .memory dir — must NOT appear in inventory.
    (root / "10-projects" / "gamma").mkdir(parents=True)
    return root


def _write_entry(
    root: Path, rel: str, name: str, description: str, type_: str, subject: str
) -> None:
    e = Entry(name=name, description=description, type=type_, subject=subject, body="b\n")
    path = root / rel / f"{date.today().isoformat()}-{name}.md"
    path.write_text(e.to_markdown())


def test_brief_includes_user_level_entries(tmp_path: Path) -> None:
    root = _seed_vault(tmp_path)
    _write_entry(root, ".memory", "principle-one", "first user-level rule", "user", "user")

    provider = VaultProvider(vault_root=root)
    brief = provider.brief()

    assert "principle-one" in brief
    assert "first user-level rule" in brief


def test_brief_includes_entity_inventory(tmp_path: Path) -> None:
    root = _seed_vault(tmp_path)

    provider = VaultProvider(vault_root=root)
    brief = provider.brief()

    assert "alpha" in brief
    assert "beta" in brief
    assert "gamma" not in brief


def test_brief_empty_vault_emits_recognizable_skeleton(tmp_path: Path) -> None:
    root = tmp_path / "vault"
    root.mkdir()

    provider = VaultProvider(vault_root=root)
    brief = provider.brief()

    assert brief.strip() != ""
    assert "memory" in brief.lower()


def test_brief_user_section_lists_one_bullet_per_entry(tmp_path: Path) -> None:
    root = _seed_vault(tmp_path)
    _write_entry(root, ".memory", "rule-a", "desc a", "user", "user")
    _write_entry(root, ".memory", "rule-b", "desc b", "feedback", "user")

    provider = VaultProvider(vault_root=root)
    brief = provider.brief()

    lines = [l for l in brief.splitlines() if l.startswith("-")]
    assert any("rule-a" in l for l in lines)
    assert any("rule-b" in l for l in lines)
