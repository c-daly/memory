#!/usr/bin/env zsh
# relocate-smoke-entry.sh — one-shot move of the existing single memory entry
# from its <entity>/<type>/ location (v1 layout) to <entity>/.memory/ (v2
# layout) and rebuild MEMORY.md so memory_reader.get() continues to resolve.
#
# Idempotent: if the entry is already at the new location, this exits clean.
# Refuses to overwrite if both locations exist (manual review required).
#
# Environment:
#   MEMORY_VAULT_DIR   Required. Path to the vault root.
#   DRY=1              Print planned actions without executing.

set -euo pipefail

: "${MEMORY_VAULT_DIR:?MEMORY_VAULT_DIR must be set}"

old="$MEMORY_VAULT_DIR/10-projects/constellation/project/2026-05-16-t1-memory-read-provider-shipped-2026-05-16.md"
new_dir="$MEMORY_VAULT_DIR/10-projects/constellation/.memory"
new="$new_dir/2026-05-16-t1-memory-read-provider-shipped-2026-05-16.md"

if [[ -f "$new" && ! -f "$old" ]]; then
  echo "[relocate-smoke-entry] already at new location: $new"
  exit 0
fi

if [[ -f "$new" && -f "$old" ]]; then
  echo "[relocate-smoke-entry] both locations exist; manual review required" >&2
  echo "  old: $old" >&2
  echo "  new: $new" >&2
  exit 2
fi

if [[ ! -f "$old" ]]; then
  echo "[relocate-smoke-entry] nothing to do; old location does not exist: $old" >&2
  exit 0
fi

echo "[relocate-smoke-entry] $old -> $new"
if [[ "${DRY:-}" == "1" ]]; then
  echo "[relocate-smoke-entry] DRY=1; skipping move + rebuild"
  exit 0
fi

mkdir -p "$new_dir"
mv "$old" "$new"

# Remove the now-empty <entity>/project/ dir if it has no other entries.
old_parent="$(dirname "$old")"
if [[ -d "$old_parent" ]] && [[ -z "$(ls -A "$old_parent")" ]]; then
  rmdir "$old_parent"
fi

echo "[relocate-smoke-entry] rebuilding MEMORY.md"
"$(dirname "$0")/../bin/memory" rebuild-index

echo "[relocate-smoke-entry] done"
