"""Shared resolver for the memory vault root.

A single place that maps environment configuration to a vault root Path,
so the cli, the MCP server, memory_reader, and memory_writer all agree
on what "the vault" means and so the env-var name can change in one
place if it ever has to.

Reads $MEMORY_VAULT_DIR if set, otherwise falls back to
~/projects/vault.
"""
from __future__ import annotations

import os
from pathlib import Path


def resolve_vault_root() -> Path:
    env = os.environ.get("MEMORY_VAULT_DIR")
    return Path(env) if env else Path.home() / "projects" / "vault"
