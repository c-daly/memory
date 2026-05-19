"""Tests for VaultProvider.resolve_scope(subject)."""
from __future__ import annotations

from datetime import date
from pathlib import Path

from providers.base import Entry
from providers.vault import VaultProvider


def _make_vault(tmp_path: Path) -> Path:
    root = tmp_path / "vault"
    (root / "10-projects" / "alpha" / ".memory").mkdir(parents=True)
    (root / "10-projects" / ".memory").mkdir(parents=True)  # bucket-level
    (root / ".memory").mkdir(parents=True)  # vault-root user-level
    return root


def _write_entry(
    root: Path, rel: str, name: str, description: str, type_: str, subject: str
) -> None:
    e = Entry(name=name, description=description, type=type_, subject=subject, body="b\n")
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(e.to_markdown())


def test_resolve_scope_returns_entity_entries(tmp_path: Path) -> None:
    root = _make_vault(tmp_path)
    _write_entry(
        root, "10-projects/alpha/.memory/2026-05-19-only-alpha.md",
        "only-alpha", "entity-level desc", "project", "alpha",
    )

    provider = VaultProvider(vault_root=root)
    entries = provider.resolve_scope("alpha")

    names = [e.name for e in entries]
    assert "only-alpha" in names


def test_resolve_scope_walks_up_through_bucket_and_root(tmp_path: Path) -> None:
    root = _make_vault(tmp_path)
    _write_entry(
        root, "10-projects/alpha/.memory/2026-05-19-e1.md",
        "e1", "entity-level", "project", "alpha",
    )
    _write_entry(
        root, "10-projects/.memory/2026-05-19-e2.md",
        "e2", "bucket-level", "project", "10-projects",
    )
    _write_entry(
        root, ".memory/2026-05-19-e3.md",
        "e3", "user-level", "user", "user",
    )

    provider = VaultProvider(vault_root=root)
    entries = provider.resolve_scope("alpha")

    names = [e.name for e in entries]
    assert "e1" in names
    assert "e2" in names
    assert "e3" in names


def test_resolve_scope_orders_nearest_first(tmp_path: Path) -> None:
    root = _make_vault(tmp_path)
    _write_entry(
        root, "10-projects/alpha/.memory/2026-05-19-entity.md",
        "entity-e", "entity", "project", "alpha",
    )
    _write_entry(
        root, "10-projects/.memory/2026-05-19-bucket.md",
        "bucket-e", "bucket", "project", "10-projects",
    )
    _write_entry(
        root, ".memory/2026-05-19-user.md",
        "user-e", "user", "user", "user",
    )

    provider = VaultProvider(vault_root=root)
    entries = provider.resolve_scope("alpha")
    names = [e.name for e in entries]

    assert names.index("entity-e") < names.index("bucket-e") < names.index("user-e")


def test_resolve_scope_dedupes_on_type_name_subject(tmp_path: Path) -> None:
    """If the same (type, name, subject) appears twice on the walk, return it once."""
    root = _make_vault(tmp_path)
    _write_entry(
        root, "10-projects/alpha/.memory/2026-05-19-dup.md",
        "dup", "first", "project", "alpha",
    )
    _write_entry(
        root, "10-projects/.memory/2026-05-19-dup.md",
        "dup", "second", "project", "alpha",
    )

    provider = VaultProvider(vault_root=root)
    entries = provider.resolve_scope("alpha")
    dups = [e for e in entries if e.name == "dup"]

    assert len(dups) == 1
    assert dups[0].description == "first"


def test_resolve_scope_returns_empty_for_unknown_subject(tmp_path: Path) -> None:
    """Unknown subject is treated as omit_section: empty list, no raise."""
    root = _make_vault(tmp_path)
    provider = VaultProvider(vault_root=root)

    entries = provider.resolve_scope("does-not-exist")

    assert entries == []


def test_resolve_scope_returns_empty_on_ambiguous_subject(tmp_path: Path) -> None:
    """Ambiguous subject (multiple PARA dirs match at same depth) -> omit_section: []."""
    root = tmp_path / "vault"
    # Create TWO entities at the same PARA depth with the same name.
    (root / "10-projects" / "shared" / ".memory").mkdir(parents=True)
    (root / "20-areas" / "shared" / ".memory").mkdir(parents=True)
    provider = VaultProvider(vault_root=root)

    entries = provider.resolve_scope("shared")

    assert entries == []


def test_resolve_scope_skips_unreadable_files(tmp_path: Path) -> None:
    """A bad file (non-UTF-8 bytes) in a .memory/ dir must not break the walk."""
    root = tmp_path / "vault"
    (root / "10-projects" / "alpha" / ".memory").mkdir(parents=True)

    # Write a valid entry alongside a bad-bytes file.
    valid = Entry(
        name="good", description="readable", type="project",
        subject="alpha", body="b\n",
    )
    (root / "10-projects" / "alpha" / ".memory" / "2026-05-19-good.md").write_text(
        valid.to_markdown()
    )
    # Non-UTF-8 bytes (invalid sequence).
    (root / "10-projects" / "alpha" / ".memory" / "2026-05-19-bad.md").write_bytes(
        b"\xff\xfe\x00not-utf8"
    )

    provider = VaultProvider(vault_root=root)
    entries = provider.resolve_scope("alpha")

    # The valid entry should still appear; the bad file is silently skipped.
    assert any(e.name == "good" for e in entries)
