# memory

Durable agent observation memory for Claude Code — `user`, `feedback`, `project`, `reference` notes that persist across sessions.

## Status

Phase 0 (scaffold). Implementation plan: [`.claude/plans/2026-05-10-memory-v0.md`](.claude/plans/2026-05-10-memory-v0.md).

This plugin is a re-derivation after the original 2026-05-09 plan was lost in a desktop spill — see [`<vault>/10-projects/memory/2026-05-09-desktop-spill-losses.md`](https://github.com/c-daly/vault) for the loss record. The architectural commitments are intact via the vault narrative and continuity's `2026-05-08-reader-writer-architecture.md`.

## Architecture (v0)

**Reader / Writer split.** `memory_reader` and `memory_writer` are the two entry points the agent interacts with. Both bind to a configured `Provider`.

**Providers.** Two ship in v0: `FilesystemProvider` (default; generic) and `VaultProvider` (vault-aware). The `Provider` interface is abstract enough to admit non-filesystem implementations (MCP-backed providers in a future phase).

**Memory types.** Four — `user`, `feedback`, `project`, `reference`. Each entry is one Markdown file with YAML frontmatter (`name`, `description`, `type`) plus body. `MEMORY.md` is an index file (one line per memory) loaded on session start.

**Sovereignty.** No cross-plugin runtime dependencies. Sibling plugins (continuity, agent-swarm) can be absent or arrive later; their absence degrades gracefully.

## Out of scope for v0

- Obsidian extraction (future Obsidian plugin owns vault semantics).
- Cross-plugin coordination at runtime.
- MCP-backed providers (future phase).
- Schema registration / typed schemas — files just have `type: user|feedback|project|reference`.

## Surface (planned)

- **CLI:** `memory read <name>`, `memory write --name X --type T --description D [--body -|@file]`, `memory list [--type T]`, `memory delete <name>`, `memory migrate <src-dir>`.
- **MCP:** `memory__read`, `memory__write`, `memory__list`, `memory__delete`.
- Both surfaces map to the same `memory_reader` / `memory_writer` underneath.

## Layout

```
.claude/plans/                   # implementation plans (mirrored to vault)
.claude/decisions/               # architectural decisions (mirrored to vault)
.claude-plugin/plugin.json       # Claude Code plugin manifest
.mcp.json                        # MCP server registration
bin/memory                       # CLI wrapper
bin/memory-server                # MCP server wrapper
lib/providers/base.py            # Provider ABC
lib/providers/filesystem.py      # default; generic
lib/providers/vault.py           # vault-aware
lib/memory_reader.py             # read entry point
lib/memory_writer.py             # write entry point
lib/config.py                    # resolves Provider from ~/.config/memory/config.yaml
lib/server.py                    # MCP server
lib/cli.py                       # CLI subcommands
tests/                           # pytest
```

See the implementation plan for phase-by-phase build order.
