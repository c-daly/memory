"""Advisory provider-root lock for memory writes.

The lock is intentionally local and filesystem-backed: it serializes memory
writers that share one provider root without introducing a storage backend.
It assumes a local filesystem where ``O_CREAT | O_EXCL`` is atomic; network or
special mounts may need a different lock strategy.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import os
from pathlib import Path
import socket
import threading
import time
from collections.abc import Iterator

LOCK_FILENAME = ".memory.lock"
DEFAULT_TIMEOUT_SECONDS = 10.0
POLL_INTERVAL_SECONDS = 0.05

_HELD_LOCKS = threading.local()


class MemoryLockTimeoutError(TimeoutError):
    """Raised when a memory lock cannot be acquired before the timeout."""


def lock_path(root: Path) -> Path:
    """Return the provider-root lockfile path."""
    return Path(root) / LOCK_FILENAME


def _held_counts() -> dict[Path, int]:
    counts = getattr(_HELD_LOCKS, "counts", None)
    if counts is None:
        counts = {}
        _HELD_LOCKS.counts = counts
    return counts


def _metadata(context: str | None) -> str:
    lines = [
        f"pid: {os.getpid()}",
        f"hostname: {socket.gethostname()}",
        f"acquired_at: {datetime.now(timezone.utc).isoformat()}",
    ]
    if context:
        lines.append(f"context: {context}")
    return "\n".join(lines) + "\n"


def _existing_lock_message(path: Path) -> str:
    try:
        existing = path.read_text(encoding="utf-8").strip()
    except OSError:
        existing = "(unable to read lock metadata)"
    if not existing:
        existing = "(lockfile was empty)"
    return (
        f"timed out waiting for memory lock at {path}. "
        f"Existing lock metadata:\n{existing}\n"
        "If no memory writer is running, inspect and remove the lockfile manually."
    )


@contextmanager
def memory_lock(
    root: Path,
    timeout_s: float = DEFAULT_TIMEOUT_SECONDS,
    context: str | None = None,
) -> Iterator[None]:
    """Acquire a provider-root advisory lock.

    The lock is re-entrant for the same thread and root so write-time recovery
    can call rebuild_from_scan() while the outer write still owns the lock.
    """
    root = Path(root).resolve()
    path = lock_path(root)
    counts = _held_counts()

    if counts.get(root, 0) > 0:
        counts[root] += 1
        try:
            yield
        finally:
            counts[root] -= 1
            if counts[root] == 0:
                del counts[root]
        return

    deadline = time.monotonic() + timeout_s
    fd: int | None = None
    while True:
        try:
            fd = os.open(
                path,
                os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                0o644,
            )
            try:
                os.write(fd, _metadata(context).encode("utf-8"))
            except OSError:
                os.close(fd)
                fd = None
                try:
                    path.unlink()
                except FileNotFoundError:
                    pass
                raise
            break
        except FileExistsError:
            if time.monotonic() >= deadline:
                raise MemoryLockTimeoutError(_existing_lock_message(path))
            time.sleep(POLL_INTERVAL_SECONDS)

    counts[root] = 1
    try:
        yield
    finally:
        try:
            if fd is not None:
                os.close(fd)
        finally:
            counts[root] -= 1
            if counts[root] == 0:
                del counts[root]
            try:
                path.unlink()
            except FileNotFoundError:
                pass
