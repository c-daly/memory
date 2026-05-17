"""memory_writer: high-level write entry-point used by callers and the CLI/server.

Validates inputs, delegates storage to a Provider (VaultProvider by default),
and updates MEMORY.md via lib.index.

Memory is append-only at this layer: callers receive `MemoryCollisionError`
from the provider when a resolved location is already taken; the provider
makes no overwrite decision.
"""
from __future__ import annotations

from pathlib import Path

import index
from config import resolve_vault_root as _resolve_vault_root
from lock import memory_lock
from providers.base import Entry, Provider
from providers.vault import VaultProvider

VALID_TYPES = {"user", "feedback", "project", "reference"}


def _get_provider() -> Provider:
    """Construct the default production provider (VaultProvider)."""
    return VaultProvider(vault_root=_resolve_vault_root())


def write(
    name: str,
    description: str,
    type: str,
    subject: str,
    body: str,
    provider: Provider | None = None,
) -> str:
    """Validate, store via provider, and append a MEMORY.md bullet.

    Returns the stored path/id reported by the provider.

    Raises:
        ValueError: if `type` is not one of VALID_TYPES, or if `name`,
            `description`, or `subject` is empty/whitespace.
        MemoryCollisionError: re-raised from the provider when the resolved
            location already exists.
        MemoryAmbiguousSubjectError: re-raised from the provider when subject
            resolution is ambiguous.
    """
    if type not in VALID_TYPES:
        raise ValueError(
            f"invalid type: {type!r}; expected one of {sorted(VALID_TYPES)!r}"
        )
    for field_name, val in (
        ("name", name),
        ("description", description),
        ("subject", subject),
    ):
        if not val or not val.strip():
            raise ValueError(f"{field_name} is required")

    # The MEMORY.md bullet format embeds every field verbatim on a
    # single line, with this shape:
    #   - [[<path>|<name>]] · type:T subject:S · <description>
    # A field containing a character that conflicts with the format
    # produces a bullet that the parser silently skips — put() succeeds
    # but the entry never appears in list()/get() results.
    #
    # Reject the conflicting characters at the writer (the only
    # supported entry point) so a malformed entry never reaches the
    # index.
    if any(c in name for c in "]|\r\n"):
        raise ValueError(
            f"name must not contain ']', '|', or newline characters "
            f"(they break the [[path|name]] bullet link); got {name!r}"
        )
    if "\r" in description or "\n" in description:
        raise ValueError(
            f"description must not contain newline characters "
            f"(bullets are one line each); got {description!r}"
        )
    if any(c.isspace() for c in subject):
        raise ValueError(
            f"subject must not contain whitespace; got {subject!r}"
        )
    if "\u00b7" in subject:
        raise ValueError(
            f"subject must not contain the index separator '\u00b7'; "
            f"got {subject!r}"
        )

    provider = provider if provider is not None else _get_provider()
    # Always source vault_root from the provider, not from the env, so an
    # injected provider with a custom root keeps its index file and entry
    # files in the same directory tree. Previously memory_writer pulled
    # vault_root from MEMORY_VAULT_DIR independently, which silently
    # misaligned index and storage when a caller passed a provider with
    # a different root.
    vault_root = Path(provider.root)

    with memory_lock(vault_root, context="memory_writer.write"):
        entry = Entry(
            name=name,
            description=description,
            type=type,
            subject=subject,
            body=body,
        )
        path = provider.put(entry)

        # Convert to a vault-relative path for the index. If the provider stored
        # the entry outside vault_root (e.g. a test FilesystemProvider rooted
        # elsewhere), fall back to the raw path the provider returned.
        try:
            rel_path = Path(path).relative_to(vault_root).as_posix()
        except ValueError:
            rel_path = path

        index.append(vault_root, name, type, subject, rel_path, description)
        return path
