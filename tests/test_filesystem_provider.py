"""Tests for FilesystemProvider.brief() and resolve_scope()."""
from __future__ import annotations


def test_filesystem_provider_brief_returns_minimal_string(tmp_path):
    from providers.filesystem import FilesystemProvider

    provider = FilesystemProvider(root=tmp_path)
    brief = provider.brief()

    assert isinstance(brief, str)
    assert "filesystem" in brief.lower()


def test_filesystem_provider_resolve_scope_returns_empty_for_missing(tmp_path):
    from providers.filesystem import FilesystemProvider

    provider = FilesystemProvider(root=tmp_path)
    entries = provider.resolve_scope("anything")

    assert entries == []
