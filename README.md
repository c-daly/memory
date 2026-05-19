# memory

Durable agent observation memory for Claude Code — `user`, `feedback`, `project`, `reference` notes that persist across sessions.

## Status

v1.0.0 + append-locking (T3) + entity-locality enforcement (audit #6) shipped. Memory writes through a PARA-aware vault provider with provider-root advisory locking. Subject resolution supports an optional alias registry for naming-drift cases.

## Architecture

**Reader / writer split.** `memory_reader` and `memory_writer` are the two entry points consumers interact with. Both bind to a `Provider`.

**Providers.** Two ship: `VaultProvider` (default; PARA-aware; files entries to `<vault>/10-projects/<project>/.memory/<YYYY-MM-DD>-<slug>.md` — the entry's `type` lives in YAML frontmatter, not the path) and `FilesystemProvider` (generic flat layout; used by tests + for plain-filesystem setups).

**Entry types.** Four hard-coded: `user`, `feedback`, `project`, `reference`. Each entry is one Markdown file with YAML frontmatter (`name`, `description`, `type`, `subject`) plus body. `MEMORY.md` at the vault root is the index — one line per entry, parsed and rewritten atomically.

**Concurrency.** A provider-root advisory lockfile (`.memory.lock`) serializes `memory_writer.write()`, `index.append()`, and `index.rebuild_from_scan()`. Re-entrant for the same thread/root. Same-host stale locks recover only when the recorded PID is proven dead.

**Subject → entity routing (PARA).** Subjects must resolve to a directory under `10-projects/`, `20-areas/`, or `30-resources/`. No match raises `MemorySubjectNotFoundError` with the available candidates — the inbox-fallback antipattern was removed in audit #6. An optional alias registry at `<vault>/.memory-aliases.yaml` handles naming drift (e.g. `memory-plugin: memory`). Real PARA dirs always win over aliases.

**Sovereignty.** No cross-plugin runtime dependencies. Memory works whether or not continuity, agent-swarm, or any other plugin is present.

## Surface

**CLI** (via `bin/memory`):

```
memory write --type T --name N --subject S --description D    # body from stdin
memory list  [--type T] [--subject S]
memory get   --name N --type T
memory rebuild-index                                          # rescan vault, regenerate MEMORY.md
```

**MCP** (via `bin/memory-server`, FastMCP):

- `memory_write(type, name, subject, description, body)` — write; returns stored path or `error: ...`
- `memory_list(type=None, subject=None)` — list as markdown bullets
- `memory_get(name, type)` — single entry as markdown or `not found`
- `memory_rebuild_index()` — regenerate MEMORY.md; returns count

## Configuration

The vault root is resolved from `$MEMORY_VAULT_DIR` if set, otherwise `~/projects/vault`. No config file required.

Optional alias registry at `<vault>/.memory-aliases.yaml` (YAML map of `<incoming-subject>: <canonical-subject>`). Real PARA dirs always win over aliases; aliases are only consulted when direct resolution misses. Malformed YAML or a non-mapping file degrades to "no aliases" — aliases are convenience, never load-bearing.

## Runtime dependencies

memory's MCP server uses the [mcp](https://pypi.org/project/mcp/) Python package (FastMCP). Installed into a plugin-local `.venv/`, not into the host Python.

### First-run setup

If `uv` (https://docs.astral.sh/uv/) is on `PATH`, `bin/memory-server` and `bin/memory` auto-bootstrap `.venv` on first invocation. No manual steps required.

If `uv` is unavailable, create the venv manually:

```
cd ~/.claude/plugins/memory
python3 -m venv .venv
.venv/bin/pip install mcp 'pyyaml>=6.0'
```

The CLI and MCP server share the same venv.

## Layout

```
.claude-plugin/plugin.json   # Claude Code plugin manifest
.mcp.json                    # MCP server registration (uses ${MEMORY_ROOT})
bin/memory                   # CLI wrapper
bin/memory-server            # MCP server wrapper
lib/cli.py                   # CLI subcommands
lib/server.py                # MCP server (FastMCP)
lib/memory_reader.py         # read entry point
lib/memory_writer.py         # write entry point (atomic, lock-serialized)
lib/index.py                 # MEMORY.md format + atomic read/append/rebuild
lib/lock.py                  # provider-root advisory locking (T3)
lib/config.py                # vault-root resolution
lib/providers/base.py        # Provider ABC + Entry + error types
lib/providers/vault.py       # PARA-aware; default
lib/providers/filesystem.py  # flat; tests + plain-filesystem
tests/                       # pytest (116 tests; 100% pass)
```

Plans and decisions for this plugin live in `<vault>/10-projects/memory/`.
