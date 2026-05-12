"""Tests for lib/memory_writer.py: validation, round-trip, collision."""
from __future__ import annotations

from pathlib import Path

import pytest

import index
import memory_writer
from providers.base import MemoryCollisionError
from providers.filesystem import FilesystemProvider


@pytest.fixture
def vault(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point MEMORY_VAULT_DIR at tmp_path so index.append writes here."""
    monkeypatch.setenv("MEMORY_VAULT_DIR", str(tmp_path))
    return tmp_path


@pytest.fixture
def provider(vault: Path) -> FilesystemProvider:
    return FilesystemProvider(root=vault)


@pytest.mark.parametrize("entry_type", ["user", "feedback", "project", "reference"])
def test_write_round_trip_each_type(
    vault: Path, provider: FilesystemProvider, entry_type: str
) -> None:
    returned = memory_writer.write(
        name=f"sample-{entry_type}",
        description=f"a {entry_type} entry",
        type=entry_type,
        subject="demo",
        body="body text\n",
        provider=provider,
    )
    # Provider returned a real file path that exists.
    assert Path(returned).exists()

    # MEMORY.md gained a bullet visible via index.read.
    entries = index.read(vault)
    matching = [e for e in entries if e.name == f"sample-{entry_type}"]
    assert len(matching) == 1
    e = matching[0]
    assert e.type == entry_type
    assert e.subject == "demo"
    assert e.description == f"a {entry_type} entry"


@pytest.mark.parametrize("bad_type", ["invalid", "USER", ""])
def test_write_invalid_type_raises(
    vault: Path, provider: FilesystemProvider, bad_type: str
) -> None:
    with pytest.raises(ValueError):
        memory_writer.write(
            name="x",
            description="d",
            type=bad_type,
            subject="s",
            body="b",
            provider=provider,
        )


def test_write_empty_name_raises(vault: Path, provider: FilesystemProvider) -> None:
    with pytest.raises(ValueError):
        memory_writer.write(
            name="",
            description="d",
            type="user",
            subject="s",
            body="b",
            provider=provider,
        )
    with pytest.raises(ValueError):
        memory_writer.write(
            name="   ",
            description="d",
            type="user",
            subject="s",
            body="b",
            provider=provider,
        )


def test_write_empty_description_raises(
    vault: Path, provider: FilesystemProvider
) -> None:
    with pytest.raises(ValueError):
        memory_writer.write(
            name="x",
            description="",
            type="user",
            subject="s",
            body="b",
            provider=provider,
        )


def test_write_empty_subject_raises(
    vault: Path, provider: FilesystemProvider
) -> None:
    with pytest.raises(ValueError):
        memory_writer.write(
            name="x",
            description="d",
            type="user",
            subject="",
            body="b",
            provider=provider,
        )


def test_write_collision_raises(
    vault: Path, provider: FilesystemProvider
) -> None:
    # First write succeeds.
    first_path = memory_writer.write(
        name="dup",
        description="first",
        type="user",
        subject="alice",
        body="one",
        provider=provider,
    )
    assert Path(first_path).exists()

    # Second write with same (type, name) hits today-dated filename collision.
    with pytest.raises(MemoryCollisionError):
        memory_writer.write(
            name="dup",
            description="second",
            type="user",
            subject="alice",
            body="two",
            provider=provider,
        )


@pytest.mark.parametrize("bad_subject", ["Project Alpha", "foo bar", "tab\there", "line\nbreak"])
def test_write_subject_with_whitespace_raises(
    vault: Path, provider: FilesystemProvider, bad_subject: str
) -> None:
    """Subjects containing whitespace would break MEMORY.md bullet parsing.

    The bullet format reserves whitespace as a field delimiter; an entry
    written with 'Project Alpha' as its subject would round-trip into an
    index line that the parser would silently skip.
    """
    with pytest.raises(ValueError, match="whitespace"):
        memory_writer.write(
            name="x",
            description="d",
            type="project",
            subject=bad_subject,
            body="b",
            provider=provider,
        )


def test_write_subject_with_separator_raises(
    vault: Path, provider: FilesystemProvider
) -> None:
    """Subjects must not contain the bullet separator character ('·').

    The separator is what splits a bullet into its (path|name) | type/subject |
    description segments; a subject containing it would scramble parsing.
    """
    with pytest.raises(ValueError, match="separator"):
        memory_writer.write(
            name="x",
            description="d",
            type="project",
            subject="foo·bar",
            body="b",
            provider=provider,
        )


def test_write_subject_with_slash_allowed(
    vault: Path, provider: FilesystemProvider
) -> None:
    """PARA-style path subjects (slashes, dashes) remain valid."""
    path = memory_writer.write(
        name="x",
        description="d",
        type="project",
        subject="10-projects/memory",
        body="b",
        provider=provider,
    )
    assert path


def test_write_uses_provider_root_not_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When a custom provider is injected, MEMORY.md must be written
    inside that provider's root — not at the env-configured vault.

    Previously memory_writer re-resolved vault_root from MEMORY_VAULT_DIR
    independently, so the bullet landed at the env path while the entry
    file lived at the provider's path: silent index/storage misalignment.
    """
    env_vault = tmp_path / "env-vault"
    env_vault.mkdir()
    provider_root = tmp_path / "actual-root"
    provider_root.mkdir()
    monkeypatch.setenv("MEMORY_VAULT_DIR", str(env_vault))

    provider = FilesystemProvider(root=provider_root)
    memory_writer.write(
        name="x",
        description="d",
        type="project",
        subject="foo",
        body="b",
        provider=provider,
    )

    # Bullet must be in the provider's root, NOT in the env-configured one.
    assert (provider_root / "MEMORY.md").is_file()
    assert not (env_vault / "MEMORY.md").exists()


@pytest.mark.parametrize("bad_name", ["foo]bar", "foo|bar", "foo\nbar", "foo\rbar"])
def test_write_name_with_bullet_unsafe_chars_raises(
    vault: Path, provider: FilesystemProvider, bad_name: str
) -> None:
    """`]`, `|`, '\\n', '\\r' in name break the [[path|name]] portion of
    the bullet — without this guard, put() succeeds and the index file
    is written, but every future read/lookup silently drops the entry."""
    with pytest.raises(ValueError, match=r"name must not contain"):
        memory_writer.write(
            name=bad_name,
            description="d",
            type="project",
            subject="foo",
            body="b",
            provider=provider,
        )


@pytest.mark.parametrize("bad_desc", ["a\nb", "a\rb"])
def test_write_description_with_newline_raises(
    vault: Path, provider: FilesystemProvider, bad_desc: str
) -> None:
    """Descriptions are the bullet's tail on a single line; embedded
    newlines split the bullet and orphan everything after the break."""
    with pytest.raises(ValueError, match=r"description must not contain newline"):
        memory_writer.write(
            name="x",
            description=bad_desc,
            type="project",
            subject="foo",
            body="b",
            provider=provider,
        )
