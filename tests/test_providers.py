"""Tests for FilesystemProvider and VaultProvider.

Covers the v1 minimal Provider contract:
    - put/get round-trip
    - list filters (type, subject)
    - exists semantics
    - MemoryCollisionError on duplicate puts
    - VaultProvider PARA filing rule incl. flat subjects, nested subjects,
      path-shaped disambiguation, ambiguous-subject errors, the `user`
      special-case, inbox fallback, and on-demand type-subfolder creation.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from providers.base import (
    Entry,
    MemoryAmbiguousSubjectError,
    MemoryCollisionError,
)
from providers.filesystem import FilesystemProvider
from providers.vault import VaultProvider

ENTRY_TYPES = ("user", "feedback", "project", "reference")


def _make_entry(
    type: str,
    name: str | None = None,
    subject: str = "foo",
    description: str = "a test entry",
    body: str = "hello body\n",
) -> Entry:
    return Entry(
        name=name or f"{type}-note",
        description=description,
        type=type,
        subject=subject,
        body=body,
    )


# ---------------------------------------------------------------------------
# FilesystemProvider
# ---------------------------------------------------------------------------


class TestFilesystemProvider:
    @pytest.mark.parametrize("entry_type", ENTRY_TYPES)
    def test_put_get_round_trip(self, tmp_path: Path, entry_type: str) -> None:
        provider = FilesystemProvider(root=tmp_path)
        entry = _make_entry(entry_type)

        path = provider.put(entry)
        assert Path(path).exists()

        fetched = provider.get(name=entry.name, type=entry.type)
        assert fetched is not None
        assert fetched.name == entry.name
        assert fetched.description == entry.description
        assert fetched.type == entry.type
        assert fetched.subject == entry.subject
        assert fetched.body == entry.body

    def test_list_no_filter_returns_all(self, tmp_path: Path) -> None:
        provider = FilesystemProvider(root=tmp_path)
        for entry_type in ENTRY_TYPES:
            provider.put(_make_entry(entry_type))

        all_entries = provider.list()
        assert len(all_entries) == len(ENTRY_TYPES)
        assert {e.type for e in all_entries} == set(ENTRY_TYPES)

    def test_list_filters_by_type(self, tmp_path: Path) -> None:
        provider = FilesystemProvider(root=tmp_path)
        for entry_type in ENTRY_TYPES:
            provider.put(_make_entry(entry_type))

        only_user = provider.list(type="user")
        assert len(only_user) == 1
        assert only_user[0].type == "user"

        only_project = provider.list(type="project")
        assert len(only_project) == 1
        assert only_project[0].type == "project"

    def test_list_filters_by_subject(self, tmp_path: Path) -> None:
        provider = FilesystemProvider(root=tmp_path)
        provider.put(_make_entry("project", name="a", subject="foo"))
        provider.put(_make_entry("project", name="b", subject="bar"))
        provider.put(_make_entry("reference", name="c", subject="foo"))

        foo_entries = provider.list(subject="foo")
        assert len(foo_entries) == 2
        assert {e.name for e in foo_entries} == {"a", "c"}

        bar_entries = provider.list(subject="bar")
        assert len(bar_entries) == 1
        assert bar_entries[0].name == "b"

    def test_exists_before_and_after_put(self, tmp_path: Path) -> None:
        provider = FilesystemProvider(root=tmp_path)
        entry = _make_entry("user")

        assert provider.exists(name=entry.name, type=entry.type) is False
        provider.put(entry)
        assert provider.exists(name=entry.name, type=entry.type) is True

    def test_collision_raises(self, tmp_path: Path) -> None:
        provider = FilesystemProvider(root=tmp_path)
        entry = _make_entry("project", name="dup", subject="foo")
        provider.put(entry)

        with pytest.raises(MemoryCollisionError) as excinfo:
            provider.put(entry)
        assert excinfo.value.path  # carries the resolved path


# ---------------------------------------------------------------------------
# VaultProvider
# ---------------------------------------------------------------------------


@pytest.fixture
def vault(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Create a PARA-shaped fake vault rooted at tmp_path.

    Layout:
        10-projects/foo/
        10-projects/LOGOS/sophia/
        10-projects/LOGOS/chiron/
        20-areas/personal/
        20-areas/personal/sophia/   <- collides w/ 10-projects/LOGOS/sophia
                                       at the same depth to force ambiguity
        30-resources/refs/
    """
    (tmp_path / "10-projects" / "foo").mkdir(parents=True)
    (tmp_path / "10-projects" / "LOGOS" / "sophia").mkdir(parents=True)
    (tmp_path / "10-projects" / "LOGOS" / "chiron").mkdir(parents=True)
    (tmp_path / "20-areas" / "personal").mkdir(parents=True)
    (tmp_path / "20-areas" / "personal" / "sophia").mkdir(parents=True)
    (tmp_path / "30-resources" / "refs").mkdir(parents=True)
    monkeypatch.setenv("MEMORY_VAULT_DIR", str(tmp_path))
    return tmp_path


class TestVaultProviderPlacement:
    def test_flat_subject_resolves_to_top_level_project(self, vault: Path) -> None:
        provider = VaultProvider(vault_root=vault)
        entry = _make_entry("project", name="note-1", subject="foo")

        written = Path(provider.put(entry))
        assert written.exists()
        # File lands under 10-projects/foo/<type>/<filename>
        rel = written.relative_to(vault)
        assert rel.parts[0] == "10-projects"
        assert rel.parts[1] == "foo"
        assert rel.parts[2] == "project"  # type subfolder
        assert rel.name.endswith(".md")

    def test_nested_subject_resolved_by_recursive_walk(self, vault: Path) -> None:
        provider = VaultProvider(vault_root=vault)
        entry = _make_entry("reference", name="chiron-note", subject="chiron")

        written = Path(provider.put(entry))
        rel = written.relative_to(vault)
        assert rel.parts[:3] == ("10-projects", "LOGOS", "chiron")
        assert rel.parts[3] == "reference"

    def test_ambiguous_subject_raises(self, vault: Path) -> None:
        provider = VaultProvider(vault_root=vault)
        entry = _make_entry("project", name="sophia-note", subject="sophia")

        with pytest.raises(MemoryAmbiguousSubjectError) as excinfo:
            provider.put(entry)

        candidates = excinfo.value.candidates
        assert isinstance(candidates, list)
        assert len(candidates) == 2
        joined = "\n".join(candidates)
        assert str(vault / "10-projects" / "LOGOS" / "sophia") in joined
        assert str(vault / "20-areas" / "personal" / "sophia") in joined

    def test_path_shaped_subject_disambiguates(self, vault: Path) -> None:
        provider = VaultProvider(vault_root=vault)
        entry = _make_entry("feedback", name="sophia-fb", subject="LOGOS/sophia")

        written = Path(provider.put(entry))
        rel = written.relative_to(vault)
        assert rel.parts[:3] == ("10-projects", "LOGOS", "sophia")
        assert rel.parts[3] == "feedback"

    def test_user_subject_lands_at_vault_root(self, vault: Path) -> None:
        provider = VaultProvider(vault_root=vault)
        entry = _make_entry("user", name="a-user-pref", subject="user")

        written = Path(provider.put(entry))
        rel = written.relative_to(vault)
        # Lands directly under <vault_root>/<type>/<filename>
        assert rel.parts[0] == "user"
        assert rel.name.endswith(".md")
        # No PARA prefix in the path.
        assert "10-projects" not in rel.parts
        assert "00-inbox" not in rel.parts

    def test_unresolvable_subject_falls_into_inbox(self, vault: Path) -> None:
        provider = VaultProvider(vault_root=vault)
        entry = _make_entry(
            "reference", name="mystery", subject="no-such-thing"
        )

        written = Path(provider.put(entry))
        rel = written.relative_to(vault)
        assert rel.parts[0] == "00-inbox"
        assert rel.parts[1] == "reference"

    def test_type_subfolder_created_on_first_use(self, vault: Path) -> None:
        provider = VaultProvider(vault_root=vault)
        type_dir = vault / "10-projects" / "foo" / "project"
        assert not type_dir.exists()

        provider.put(_make_entry("project", name="first", subject="foo"))
        assert type_dir.is_dir()

    def test_env_var_resolves_vault_root(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Constructing without vault_root reads MEMORY_VAULT_DIR."""
        (tmp_path / "10-projects" / "foo").mkdir(parents=True)
        monkeypatch.setenv("MEMORY_VAULT_DIR", str(tmp_path))
        provider = VaultProvider()

        assert provider.vault_root == tmp_path
        written = Path(
            provider.put(_make_entry("project", name="x", subject="foo"))
        )
        assert written.is_relative_to(tmp_path)
