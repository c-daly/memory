"""Provider ABC contract tests."""
from __future__ import annotations

import pytest

from providers.base import Provider


def test_provider_has_resolve_scope():
    """The Provider ABC must declare resolve_scope() method."""
    assert hasattr(Provider, "resolve_scope")
    assert callable(Provider.resolve_scope)


def test_provider_default_resolve_scope_raises_not_implemented():
    class StubProvider(Provider):
        def list(self, type=None, subject=None):
            return []

        def get(self, name, type):
            return None

        def put(self, entry):
            return ""

        def exists(self, name, type):
            return False

    p = StubProvider()
    with pytest.raises(NotImplementedError):
        p.resolve_scope("foo")
