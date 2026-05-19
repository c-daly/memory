#!/usr/bin/env zsh
# migrate-auto-memory.sh — Walk auto-memory dirs and migrate entries
# through `bin/memory write`. Interactive by default; --batch accepts
# the heuristic suggestion without prompting. DRY=1 prints without
# writing.
#
# Per design v2: destinations land at <entity>/.memory/<file>.md (the
# writer handles the dot-prefix; this script only chooses the subject).
# Per-entry Obsidian aliases are NOT preserved.
#
# Environment:
#   AUTO_MEMORY_DIR    Root of auto-memory dirs to walk.
#                      Default: ~/.claude/projects
#   MEMORY_VAULT_DIR   Required by bin/memory.
#   MEMORY_ROOT        Plugin install root (default: parent dir of this script).
#   DRY=1              Print proposed migrations; do not call bin/memory write.

set -uo pipefail

AUTO_MEMORY_DIR="${AUTO_MEMORY_DIR:-$HOME/.claude/projects}"
script_dir="${0:A:h}"
memory_root="${MEMORY_ROOT:-${script_dir:h}}"
memory_bin="$memory_root/bin/memory"

BATCH=0
if [[ "${1:-}" == "--batch" ]]; then
  BATCH=1
fi

# Subject heuristic. Returns the inferred subject for a basename.
infer_subject() {
  local basename="$1"
  case "$basename" in
    project_memory_plugin_*|feedback_check_memory_*|project_memory_*)
      echo "memory" ;;
    project_marketplace_*|reference_marketplace_*)
      echo "fearsidhe-plugins" ;;
    feedback_orchestrate_*|feedback_review_response_*|reference_agent_swarm_*)
      echo "agent-swarm" ;;
    reference_vault_*|project_vault_*)
      echo "vault" ;;
    project_*)
      echo "user" ;;
    feedback_*|reference_*)
      echo "user" ;;
    *)
      echo "user" ;;
  esac
}

# Parse a top-level frontmatter field from a memory file.
parse_frontmatter() {
  local file="$1" key="$2"
  awk -v k="$key" '
    /^---$/ { count++; if (count==2) exit; next }
    count==1 {
      sub(/^[ \t]*/, "")
      if (substr($0, 1, length(k)+1) == k ":") {
        sub(/^[^:]+:[ \t]*/, "")
        print
        exit
      }
    }
  ' "$file"
}

# Parse the nested metadata.type field.
parse_type() {
  local file="$1"
  awk '
    /^---$/ { count++; if (count==2) exit; next }
    count==1 && /^[ \t]*type:/ {
      sub(/^[^:]+:[ \t]*/, "")
      print
      exit
    }
  ' "$file"
}

migrate_one() {
  local file="$1"
  local basename name desc type subj
  basename="$(basename "$file" .md)"

  name="$(parse_frontmatter "$file" "name")"
  desc="$(parse_frontmatter "$file" "description")"
  type="$(parse_type "$file")"
  subj="$(infer_subject "$basename")"

  if [[ -z "$name" || -z "$type" ]]; then
    echo "[skip] $file (missing name or type in frontmatter)" >&2
    return 0
  fi

  if [[ "$BATCH" == "0" && "${DRY:-0}" != "1" ]]; then
    echo
    echo "Entry:       $file"
    echo "Name:        $name"
    echo "Description: $desc"
    echo "Type:        $type"
    echo "Suggested subject: $subj"
    printf "Confirm [enter to accept, or type a different subject]: "
    read user_subj
    if [[ -n "$user_subj" ]]; then
      subj="$user_subj"
    fi
  fi

  echo "[migrate] name=$name type=$type subject=$subj  ($file)"

  if [[ "${DRY:-0}" == "1" ]]; then
    return 0
  fi

  # Extract the body (everything after the closing ---).
  local body
  body="$(awk '
    BEGIN { c=0 }
    /^---$/ {
      if (c < 2) { c++; next }
    }
    c >= 2 { print }
  ' "$file")"

  if printf '%s' "$body" | "$memory_bin" write \
        --type "$type" --name "$name" --subject "$subj" --description "$desc" \
        > /dev/null 2>&1; then
    return 0
  fi

  # Re-run capturing stderr so we can detect collisions.
  local err
  err="$(printf '%s' "$body" | "$memory_bin" write \
        --type "$type" --name "$name" --subject "$subj" --description "$desc" 2>&1)" || true

  if [[ "$err" == *"already exists"* || "$err" == *"MemoryCollisionError"* ]]; then
    echo "[skip] already migrated: $name (collision)" >&2
    return 0
  fi

  echo "[error] $name: $err" >&2
  return 1
}

fail=0
while IFS= read -r f; do
  migrate_one "$f" || fail=1
done < <(find "$AUTO_MEMORY_DIR" -type f -name '*.md' ! -name 'MEMORY.md' -path '*/memory/*')

exit "$fail"
