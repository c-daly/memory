#!/usr/bin/env zsh
# check-memory-path-usage.sh — Layer-2 verification aggregator.
#
# Scans CC session JSONLs and reports totals (across all logs found in
# CC_SESSION_DIR) for two categories:
#   - auto-memory: `Write` to ~/.claude/projects/*/memory/*.md
#   - plugin:     mcp__plugin_memory_memory__memory_write OR
#                 `bash`-style invocations of bin/memory write
#
# Per-day or per-session breakdowns are intentionally out of scope; a
# simple total is sufficient for the cutover criterion.
#
# Environment:
#   CC_SESSION_DIR   Root holding session JSONLs.
#                    Default: ~/.claude/projects

set -uo pipefail

CC_SESSION_DIR="${CC_SESSION_DIR:-$HOME/.claude/projects}"

auto=0
plugin=0

while IFS= read -r line; do
  case "$line" in
    *'"name":"Write"'*'/.claude/projects/'*'/memory/'*)
      auto=$((auto+1))
      ;;
    *'mcp__plugin_memory_memory__memory_write'*)
      plugin=$((plugin+1))
      ;;
    *'"name":"Bash"'*'bin/memory'*'write'*)
      plugin=$((plugin+1))
      ;;
  esac
done < <(find "$CC_SESSION_DIR" -type f -name '*.jsonl' -exec cat {} +)

echo "auto-memory: $auto"
echo "plugin: $plugin"
