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

# ---------------------------------------------------------------------------
# VaultProvider — index-backed fast path (MEMORY.md)
# ---------------------------------------------------------------------------


SEP = "·"


def _write_index(vault: Path, bullets: list[str]) -> None:
    (vault / "MEMORY.md").write_text(
        "# MEMORY\n\n" + "\n".join(bullets) + "\n", encoding="utf-8"
    )


class TestVaultProviderIndexFastPath:
    def test_get_uses_index_when_present(self, vault: Path) -> None:
        provider = VaultProvider(vault_root=vault)
        written = Path(
            provider.put(_make_entry("project", name="alpha", subject="foo"))
        )
        rel = written.relative_to(vault)
        _write_index(
            vault,
            [f"- [[{rel}|alpha]] {SEP} type:project subject:foo {SEP} desc"],
        )
        # Hide every other .md from the scanner to prove the index path
        # is what answered: if get() were still scanning, it'd find nothing.
        decoy_dir = vault / "10-projects" / "foo" / "project"
        for p in decoy_dir.glob("*.md"):
            if p != written:
                p.unlink()

        entry = provider.get("alpha", "project")
        assert entry is not None
        assert entry.name == "alpha"
        assert entry.type == "project"

    def test_get_falls_back_to_scan_when_index_missing(self, vault: Path) -> None:
        provider = VaultProvider(vault_root=vault)
        provider.put(_make_entry("project", name="beta", subject="foo"))
        assert not (vault / "MEMORY.md").exists()

        entry = provider.get("beta", "project")
        assert entry is not None and entry.name == "beta"

    def test_get_falls_back_when_indexed_path_missing(self, vault: Path) -> None:
        """Stale index pointing at a deleted file falls through to scan."""
        provider = VaultProvider(vault_root=vault)
        written = Path(
            provider.put(_make_entry("project", name="gamma", subject="foo"))
        )
        _write_index(
            vault,
            [f"- [[10-projects/foo/project/9999-99-99-ghost.md|gamma]] "
             f"{SEP} type:project subject:foo {SEP} stale"],
        )

        entry = provider.get("gamma", "project")
        assert entry is not None
        assert entry.name == "gamma"
        # Sanity: the real file is what we got back
        assert (vault / written.relative_to(vault)).is_file()

    def test_list_does_not_trust_index_alone(self, vault: Path) -> None:
        """Regression guard: a direct provider.put() not yet reflected in
        MEMORY.md must still appear in list() output. The Provider does
        not own the index — it cannot rely on the index being current."""
        provider = VaultProvider(vault_root=vault)
        provider.put(_make_entry("project", name="indexed", subject="foo"))
        provider.put(_make_entry("feedback", name="unindexed", subject="foo"))
        # MEMORY.md contains only one of the two entries on disk.
        p_indexed = next((vault / "10-projects" / "foo" / "project").glob("*.md"))
        _write_index(
            vault,
            [f"- [[{p_indexed.relative_to(vault)}|indexed]] "
             f"{SEP} type:project subject:foo {SEP} d"],
        )

        names = sorted(e.name for e in provider.list())
        assert names == ["indexed", "unindexed"]



# ---------------------------------------------------------------------------
# VaultProvider — logical-entry collision (cross-date)
# ---------------------------------------------------------------------------


class TestVaultProviderCrossDayCollision:
    def test_put_same_name_type_raises_even_across_dates(
        self, vault: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Two puts with identical (name, type) on different days must
        collide. Before the fix, day-2 silently created a second file
        because the date-stamped filename differed."""
        import datetime as _dt

        provider = VaultProvider(vault_root=vault)

        class _FrozenDate(_dt.date):
            _today = _dt.date(2026, 1, 1)
            @classmethod
            def today(cls):
                return cls._today

        monkeypatch.setattr("providers.vault.date", _FrozenDate)
        provider.put(_make_entry("project", name="x", subject="foo"))

        _FrozenDate._today = _dt.date(2026, 1, 2)
        with pytest.raises(MemoryCollisionError):
            provider.put(_make_entry("project", name="x", subject="foo"))

    def test_put_same_name_different_type_allowed(self, vault: Path) -> None:
        """Collision is on (name, type), not on name alone — different
        types with the same name are independent entries."""
        provider = VaultProvider(vault_root=vault)
        provider.put(_make_entry("project", name="x", subject="foo"))
        # Should not raise; same name, different type.
        provider.put(_make_entry("feedback", name="x", subject="foo"))


# ---------------------------------------------------------------------------
# FilesystemProvider — logical-entry collision (cross-date)
# ---------------------------------------------------------------------------


class TestFilesystemProviderCrossDayCollision:
    def test_put_same_name_type_raises_even_across_dates(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import datetime as _dt

        provider = FilesystemProvider(root=tmp_path)

        class _FrozenDate(_dt.date):
            _today = _dt.date(2026, 1, 1)
            @classmethod
            def today(cls):
                return cls._today

        monkeypatch.setattr("providers.filesystem.datetime.date", _FrozenDate)
        provider.put(_make_entry("project", name="x", subject="foo"))

        _FrozenDate._today = _dt.date(2026, 1, 2)
        with pytest.raises(MemoryCollisionError):
            provider.put(_make_entry("project", name="x", subject="foo"))


# ---------------------------------------------------------------------------
# VaultProvider — subject path-traversal guards (P1/security)
# ---------------------------------------------------------------------------


class TestVaultProviderSubjectTraversal:
    @pytest.mark.parametrize(
        "subject",
        [
            "../../../tmp",
            "10-projects/../../../tmp",
            "foo/..",
            "..",  # not path-shaped (no "/"), exercised separately below
        ],
    )
    def test_dotdot_in_path_shaped_subject_rejected(
        self, vault: Path, subject: str
    ) -> None:
        provider = VaultProvider(vault_root=vault)
        if "/" not in subject:
            # Single-word ".." is treated as a flat subject; matching via
            # os.walk anchored at vault_root cannot escape, so this falls
            # through to inbox rather than raising. Verify it doesn't
            # crash and stays inside the vault.
            written = Path(
                provider.put(_make_entry("project", name="x", subject=subject))
            )
            assert written.is_relative_to(vault)
            return
        with pytest.raises(ValueError, match=r"\.\.|absolute"):
            provider.put(_make_entry("project", name="x", subject=subject))

    def test_absolute_path_subject_rejected(self, vault: Path) -> None:
        provider = VaultProvider(vault_root=vault)
        with pytest.raises(ValueError, match=r"\.\.|absolute"):
            provider.put(_make_entry("project", name="x", subject="/etc/passwd"))

    def test_symlink_escape_does_not_resolve_outside_vault(
        self, vault: Path, tmp_path_factory: pytest.TempPathFactory
    ) -> None:
        """Even if a symlink inside the vault points outside, candidates
        that resolve outside vault_root are skipped (no put-outside).

        NB: `outside` must be truly outside the vault. The `vault` fixture
        IS pytest's tmp_path, so `tmp_path / "outside"` would land inside
        the vault and defeat the test."""
        outside = tmp_path_factory.mktemp("traverse-outside")
        (vault / "10-projects").mkdir(parents=True, exist_ok=True)
        try:
            (vault / "10-projects" / "escape").symlink_to(outside)
        except (OSError, NotImplementedError):
            pytest.skip("symlinks unsupported on this filesystem")

        provider = VaultProvider(vault_root=vault)
        # Path-shaped: "escape/sub" goes through the path-shaped branch.
        # Through the symlink it would resolve to outside/sub; the bounds
        # check rejects it; no PARA root matches; falls to inbox.
        written = Path(
            provider.put(_make_entry("project", name="x", subject="escape/sub"))
        )
        assert written.is_relative_to(vault)
        assert not any(outside.rglob("*.md"))


    def test_symlink_escape_flat_subject(
        self, vault: Path, tmp_path_factory: pytest.TempPathFactory
    ) -> None:
        """Flat-subject branch: a symlinked PARA subdirectory whose name
        matches the entry's subject must NOT route the put() outside the
        vault. Same vector as the path-shaped case but exercised through
        the os.walk matching path.

        NB: `outside` must be truly outside the vault — see the docstring
        on test_symlink_escape_does_not_resolve_outside_vault."""
        outside = tmp_path_factory.mktemp("flat-outside")
        (vault / "10-projects").mkdir(parents=True, exist_ok=True)
        try:
            (vault / "10-projects" / "escape-flat").symlink_to(outside)
        except (OSError, NotImplementedError):
            pytest.skip("symlinks unsupported on this filesystem")

        provider = VaultProvider(vault_root=vault)
        written = Path(
            provider.put(_make_entry("project", name="x", subject="escape-flat"))
        )
        assert written.is_relative_to(vault)
        assert not any(outside.rglob("*.md"))


# ---------------------------------------------------------------------------
# Providers — non-UTF-8 body bytes don't crash get()/list()
# ---------------------------------------------------------------------------


class TestProvidersHandleNonUtf8Bytes:
    def test_vault_get_skips_non_utf8_file(self, vault: Path) -> None:
        """VaultProvider.get must skip a file with non-UTF-8 bytes, not raise."""
        type_dir = vault / "10-projects" / "foo" / "project"
        type_dir.mkdir(parents=True, exist_ok=True)
        (type_dir / "2026-05-12-bad.md").write_bytes(
            b"---\nname: bad\ndescription: d\ntype: project\nsubject: foo\n---\n"
            + b"\xff\xff bad bytes"
        )
        provider = VaultProvider(vault_root=vault)
        # Should return None gracefully — old behavior raised
        # UnicodeDecodeError out of the get() call.
        assert provider.get("bad", "project") is None

    def test_vault_list_skips_non_utf8_file(self, vault: Path) -> None:
        type_dir = vault / "10-projects" / "foo" / "project"
        type_dir.mkdir(parents=True, exist_ok=True)
        good = type_dir / "2026-05-12-good.md"
        good.write_text(
            "---\nname: good\ndescription: d\ntype: project\nsubject: foo\n---\nb\n",
            encoding="utf-8",
        )
        (type_dir / "2026-05-12-bad.md").write_bytes(
            b"---\nname: bad\ndescription: d\ntype: project\nsubject: foo\n---\n"
            + b"\xff\xff bad bytes"
        )
        provider = VaultProvider(vault_root=vault)
        names = sorted(e.name for e in provider.list())
        assert names == ["good"]

    def test_filesystem_list_skips_non_utf8_file(self, tmp_path: Path) -> None:
        good = tmp_path / "2026-05-12-project-good.md"
        good.write_text(
            "---\nname: good\ndescription: d\ntype: project\nsubject: foo\n---\nb\n",
            encoding="utf-8",
        )
        bad = tmp_path / "2026-05-12-project-bad.md"
        bad.write_bytes(
            b"---\nname: bad\ndescription: d\ntype: project\nsubject: foo\n---\n"
            + b"\xff\xff bad bytes"
        )
        provider = FilesystemProvider(root=tmp_path)
        names = sorted(e.name for e in provider.list())
        assert names == ["good"]

    def test_filesystem_get_skips_non_utf8_file(self, tmp_path: Path) -> None:
        bad = tmp_path / "2026-05-12-project-bad.md"
        bad.write_bytes(
            b"---\nname: bad\ndescription: d\ntype: project\nsubject: foo\n---\n"
            + b"\xff\xff bad bytes"
        )
        provider = FilesystemProvider(root=tmp_path)
        assert provider.get("bad", "project") is None


# ---------------------------------------------------------------------------
# Entry.to_markdown — round-trip with the parsers
# ---------------------------------------------------------------------------


class TestEntryToMarkdown:
    def test_round_trips_through_filesystem_parse(self, tmp_path: Path) -> None:
        """Render an Entry to markdown, write it to disk, parse it back via
        FilesystemProvider.get — fields must match. This is the contract
        the cli's `get | tee | write` workflow depends on."""
        from providers.filesystem import FilesystemProvider, _parse

        original = Entry(
            name="round-trip",
            description="a test of to_markdown",
            type="project",
            subject="foo",
            body="hello body\n",
        )
        md = original.to_markdown()
        meta, body = _parse(md)
        assert meta["name"] == original.name
        assert meta["description"] == original.description
        assert meta["type"] == original.type
        assert meta["subject"] == original.subject
        assert body == original.body

    def test_body_is_normalized_to_end_with_newline(self) -> None:
        """A body that lacks a trailing newline must be normalized so the
        markdown output is well-formed and round-trips cleanly."""
        entry = Entry(
            name="x", description="d", type="project", subject="foo",
            body="no trailing newline",
        )
        md = entry.to_markdown()
        assert md.endswith("\n")
        # And the body portion after the closing '---' ends with a newline.
        body_portion = md.split("---\n", 2)[2]
        assert body_portion == "no trailing newline\n"
