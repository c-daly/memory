"""Tests for provider-root memory locking."""
from __future__ import annotations

from pathlib import Path
import os
import socket

import pytest

from lock import MemoryLockTimeoutError, lock_path, memory_lock


def test_memory_lock_creates_metadata_and_removes_lockfile(tmp_path: Path) -> None:
    path = lock_path(tmp_path)

    with memory_lock(tmp_path, context="test-context"):
        text = path.read_text(encoding="utf-8")
        assert "pid:" in text
        assert "hostname:" in text
        assert "acquired_at:" in text
        assert "context: test-context" in text

    assert not path.exists()


def test_lock_path_resolves_relative_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "vault"
    root.mkdir()
    monkeypatch.chdir(tmp_path)

    assert lock_path(Path("vault")) == root.resolve() / ".memory.lock"


def test_memory_lock_is_reentrant_for_same_thread_and_root(tmp_path: Path) -> None:
    path = lock_path(tmp_path)

    with memory_lock(tmp_path, context="outer"):
        with memory_lock(tmp_path, context="inner"):
            assert path.exists()
        assert path.exists()

    assert not path.exists()


def test_memory_lock_breaks_stale_same_host_dead_pid(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = lock_path(tmp_path)
    path.write_text(
        "pid: 999999\n"
        f"hostname: {socket.gethostname()}\n"
        "acquired_at: 2026-05-16T00:00:00+00:00\n"
        "context: stale\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(os, "kill", lambda pid, sig: (_ for _ in ()).throw(ProcessLookupError))

    with memory_lock(tmp_path, timeout_s=0.01, context="new-owner"):
        text = path.read_text(encoding="utf-8")
        assert "context: new-owner" in text

    assert not path.exists()


def test_memory_lock_does_not_break_live_pid_lock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = lock_path(tmp_path)
    path.write_text(
        "pid: 123\n"
        f"hostname: {socket.gethostname()}\n"
        "acquired_at: 2026-05-16T00:00:00+00:00\n"
        "context: live\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(os, "kill", lambda pid, sig: None)

    with pytest.raises(MemoryLockTimeoutError):
        with memory_lock(tmp_path, timeout_s=0.01, context="blocked"):
            pass

    assert path.exists()


def test_memory_lock_timeout_includes_existing_metadata(tmp_path: Path) -> None:
    path = lock_path(tmp_path)
    path.write_text("pid: 123\nhostname: test-host\ncontext: existing\n", encoding="utf-8")

    with pytest.raises(MemoryLockTimeoutError) as exc:
        with memory_lock(tmp_path, timeout_s=0.01, context="blocked"):
            pass

    message = str(exc.value)
    assert str(path) in message
    assert "pid: 123" in message
    assert "hostname: test-host" in message
    assert "remove the lockfile manually" in message


def test_memory_lock_removes_lockfile_if_metadata_write_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = lock_path(tmp_path)

    def fail_write(fd: int, data: bytes) -> int:
        raise OSError("disk full")

    monkeypatch.setattr(os, "write", fail_write)

    with pytest.raises(OSError, match="disk full"):
        with memory_lock(tmp_path, context="write-fails"):
            pass

    assert not path.exists()
