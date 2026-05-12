"""memory CLI: thin argparse surface over memory_writer/memory_reader/index.

Subcommands:
    memory write --type T --name N --subject S --description D    # body from stdin
    memory list  [--type T] [--subject S]
    memory get   --name N --type T
    memory rebuild-index

Invoked via bin/memory, which execs the plugin .venv python on this file.
bin/memory passes the file path directly (not as a package), so we put the
sibling lib/ directory on sys.path before importing the in-tree modules.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# Make sibling modules (memory_writer, memory_reader, index, providers)
# importable when this file is invoked as a script (lib/cli.py).
sys.path.insert(0, str(Path(__file__).parent))

import index  # noqa: E402
import memory_reader  # noqa: E402
import memory_writer  # noqa: E402
from providers.base import (  # noqa: E402
    MemoryAmbiguousSubjectError,
    MemoryCollisionError,
)


from config import resolve_vault_root as _resolve_vault_root  # noqa: E402


def cmd_write(args: argparse.Namespace) -> int:
    body = sys.stdin.read()
    try:
        path = memory_writer.write(
            name=args.name,
            description=args.description,
            type=args.type,
            subject=args.subject,
            body=body,
        )
    except (ValueError, MemoryCollisionError, MemoryAmbiguousSubjectError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    print(path)
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    entries = memory_reader.list(type=args.type, subject=args.subject)
    for entry in entries:
        print(f"{entry.type}:{entry.subject}:{entry.name} \u2014 {entry.description}")
    return 0


def cmd_get(args: argparse.Namespace) -> int:
    entry = memory_reader.get(args.name, args.type)
    if entry is None:
        print("not found", file=sys.stderr)
        return 1
    sys.stdout.write(entry.to_markdown())
    return 0


def cmd_rebuild_index(args: argparse.Namespace) -> int:
    vault_root = _resolve_vault_root()
    count = index.rebuild_from_scan(vault_root)
    print(count)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="memory",
        description="Durable agent-observation memory CLI.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_write = sub.add_parser("write", help="Write a memory entry (body from stdin).")
    p_write.add_argument("--type", required=True)
    p_write.add_argument("--name", required=True)
    p_write.add_argument("--subject", required=True)
    p_write.add_argument("--description", required=True)
    p_write.set_defaults(func=cmd_write)

    p_list = sub.add_parser("list", help="List memory entries from MEMORY.md.")
    p_list.add_argument("--type", default=None)
    p_list.add_argument("--subject", default=None)
    p_list.set_defaults(func=cmd_list)

    p_get = sub.add_parser("get", help="Fetch one entry by (name, type).")
    p_get.add_argument("--name", required=True)
    p_get.add_argument("--type", required=True)
    p_get.set_defaults(func=cmd_get)

    p_rebuild = sub.add_parser(
        "rebuild-index",
        help="Rescan the vault and rewrite MEMORY.md from frontmatter.",
    )
    p_rebuild.set_defaults(func=cmd_rebuild_index)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
