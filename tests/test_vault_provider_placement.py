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


def test_bucket_subject_files_under_bucket_memory(tmp_path: Path) -> None:
    """subject in PARA_ROOTS files at <vault>/<bucket>/.memory/<file>."""
    root = tmp_path / "vault"
    (root / "10-projects").mkdir(parents=True)
    provider = VaultProvider(vault_root=root)
    entry = Entry(
        name="bucket-test",
        description="about all projects",
        type="project",
        subject="10-projects",
        body="b\n",
    )

    stored = Path(provider.put(entry))

    expected = root / "10-projects" / ".memory" / f"{date.today().isoformat()}-bucket-test.md"
    assert stored == expected
    assert expected.exists()


def test_all_para_buckets_resolve_as_subjects(tmp_path: Path) -> None:
    """Each of 10-projects / 20-areas / 30-resources is a valid subject."""
    root = tmp_path / "vault"
    for bucket in ("10-projects", "20-areas", "30-resources"):
        (root / bucket).mkdir(parents=True)
    provider = VaultProvider(vault_root=root)

    for bucket in ("10-projects", "20-areas", "30-resources"):
        entry = Entry(
            name=f"t-{bucket}",
            description="x",
            type="project",
            subject=bucket,
            body="b\n",
        )
        stored = Path(provider.put(entry))
        assert stored.parent == root / bucket / ".memory"
