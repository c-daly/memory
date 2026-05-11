---
date: 2026-05-10
project: memory
---

# Decision: Ship two providers in v0 — `FilesystemProvider` (default) + `VaultProvider`

## Decision (1 sentence)

Memory v0 ships both `FilesystemProvider` (generic, no-dependencies floor; the default) and `VaultProvider` (vault-aware; built on the same filesystem substrate), rather than only the filesystem reference impl as the narrative initially implied.

## Alternatives considered

- **Filesystem only in v0; defer vault until a later phase.** *Rejected.* This was the framing in `narrative.md` ("Vault provider — out of scope for v0. Filesystem-only in v0."). The cost of adding `VaultProvider` is small because both providers share the filesystem substrate; deferring it just delays the obvious second user (the vault is the durable cross-machine record memory wants to write to anyway). The "out of scope" framing was a scoping discipline that became overcautious once the substrate was clear.
- **Vault as the only provider in v0; treat filesystem as the test fixture.** *Rejected.* `FilesystemProvider` has independent value as the no-dependencies floor — installable without a vault setup, usable for `~/.claude/memory/` style local-only deployments. Making vault the only path would silently require a vault to use memory at all.
- **One pluggable filesystem provider with a vault flag.** *Rejected.* Conflates two responsibilities (substrate vs vault semantics) into one class. Two classes that share substrate code via composition or extension is cleaner than one class with a mode bit.

## Why this won

Both providers are filesystem-substrate; the marginal cost of `VaultProvider` over `FilesystemProvider` is whatever vault-specific logic it adds (resolving the configured tenant subtree per `2026-05-08-reader-writer-architecture.md`, vault-root resolution from env). That's small. Shipping both now establishes the multi-provider pattern from day one — the `Provider` interface is exercised by two concrete impls before any external consumer needs to write a third, which keeps the abstraction honest.

The lost 2026-05-09 sample-providers decision (per `vault/10-projects/memory/2026-05-09-desktop-spill-losses.md`) framed providers as samples that could be extracted to a shared `claude-providers` package later. That framing is preserved as a future option but is not load-bearing on this v0 decision; it's a packaging concern, not an architecture one.

## Stakeholders

- c-daly
