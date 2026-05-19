"""Tests for FilesystemProvider.resolve_scope()."""
from __future__ import annotations


def test_filesystem_provider_resolve_scope_returns_empty_for_missing(tmp_path):
    from providers.filesystem import FilesystemProvider

    provider = FilesystemProvider(root=tmp_path)
    entries = provider.resolve_scope("anything")

    assert entries == []
