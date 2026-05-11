---
date: 2026-05-10
project: memory
---

# Decision: `Provider` interface operations are substrate-agnostic — must admit non-filesystem implementations

## Decision (1 sentence)

The `Provider` ABC in `lib/providers/base.py` defines operations in domain terms (`read(name) -> Entry`, `write(entry)`, `list(type=None)`, `delete(name)`, `read_index()`, `write_index(entries)`) — never in substrate terms (no file handles, no path manipulation, no open/close/seek) — so future MCP-backed providers (Serena, memory-as-MCP, others) can satisfy the interface without contortion.

## Alternatives considered

- **File-shaped interface** (`open(path) -> handle`, `read_bytes(handle)`, `write_bytes(handle, data)`, `close(handle)`). *Rejected.* Encodes the filesystem substrate into the API. An MCP-backed impl would have to fake file handles or invent path conventions, both of which leak the wrong abstraction into consumers.
- **Lowest-common-denominator key-value** (`get(key)`, `put(key, value)`). *Rejected.* Loses the entry-type structure that's load-bearing for memory (the four-types decision). Consumers would have to encode `(name, type)` into composite keys, defeating the point of having `list(type=...)`.
- **Defer the abstraction; write `FilesystemProvider` first, extract interface later.** *Rejected.* This was tempting (YAGNI for the MCP case), but writing `VaultProvider` alongside in v0 (per the two-providers decision) means the interface is exercised by two impls from day one — extracting after-the-fact would require shimming `VaultProvider` to whatever shape `FilesystemProvider` accidentally adopted.

## Why this won

The interface only has to be honest about what readers and writers actually need: a way to fetch an entry by name, write one, list by type, delete, and manage an index. None of those require filesystem semantics. Operating in domain terms keeps the door open for MCP-backed substrates (which are clearly imagined per Phase 2 of continuity's `2026-05-07-implementation-plan.md`, even though they're out of scope for memory v0) without retrofit.

The 2026-05-10 in-conversation correction explicitly flagged the re-derived plan's mistake of making the `Provider` interface filesystem-shaped. This decision is the codification of that correction.

## Stakeholders

- c-daly
