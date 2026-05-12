"""memory MCP server. Exposes write/list/get/rebuild-index via FastMCP.

Mirrors the path-setup + tool-registration pattern from continuity/lib/server.py.
Invoked by bin/memory-server via the plugin-local .venv.
"""
import sys
from pathlib import Path

# Add this dir to path so siblings can be imported (mirrors continuity)
sys.path.insert(0, str(Path(__file__).parent))

from mcp.server.fastmcp import FastMCP  # noqa: E402

import index  # noqa: E402
import memory_reader  # noqa: E402
import memory_writer  # noqa: E402
from config import resolve_vault_root  # noqa: E402

mcp = FastMCP("memory")


@mcp.tool()
def memory_write(
    type: str, name: str, subject: str, description: str, body: str
) -> str:
    """Write a memory entry. Returns the stored path."""
    return memory_writer.write(
        name=name,
        description=description,
        type=type,
        subject=subject,
        body=body,
    )


@mcp.tool()
def memory_list(type: str | None = None, subject: str | None = None) -> str:
    """List memory entries (optionally filtered). Returns markdown bullet list."""
    entries = memory_reader.list(type=type, subject=subject)
    if not entries:
        return "(no entries)"
    lines = []
    for e in entries:
        lines.append(
            f"- type:{e.type} subject:{e.subject} name:{e.name} — {e.description}"
        )
    return "\n".join(lines)


@mcp.tool()
def memory_get(name: str, type: str) -> str:
    """Read a single memory entry. Returns markdown (frontmatter + body) or 'not found'."""
    entry = memory_reader.get(name=name, type=type)
    if entry is None:
        return "not found"
    return entry.to_markdown()


@mcp.tool()
def memory_rebuild_index() -> int:
    """Regenerate the MEMORY.md index from filesystem scan. Returns entry count."""
    vault_root = resolve_vault_root()
    return index.rebuild_from_scan(vault_root)


if __name__ == "__main__":
    mcp.run()
