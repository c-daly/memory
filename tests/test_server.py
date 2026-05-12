"""Smoke test for lib/server.py via the plugin-local .venv.

The FastMCP server depends on the `mcp` package, which is only available in
the plugin-local .venv. We invoke .venv/bin/python in a subprocess to verify
the module imports cleanly and registers the four expected tools.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent


def test_server_imports_and_registers_tools():
    venv_py = ROOT / ".venv" / "bin" / "python"
    if not venv_py.exists():
        pytest.skip(".venv not bootstrapped")
    code = (
        "import asyncio, sys;"
        "sys.path.insert(0, 'lib');"
        "import server;"
        "assert server.mcp.name == 'memory', server.mcp.name;"
        "tools = asyncio.run(server.mcp.list_tools());"
        "names = sorted(t.name for t in tools);"
        "expected = ['memory_get', 'memory_list', 'memory_rebuild_index', 'memory_write'];"
        "assert names == expected, names;"
        "print('ok')"
    )
    result = subprocess.run(
        [str(venv_py), "-c", code],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "ok" in result.stdout


def test_memory_write_returns_error_string_on_validation_failure():
    """memory_write surfaces business-validation failures as 'error: ...'
    strings, matching cli.cmd_write's contract. Without the guard, an
    MCP client sees a FastMCP-wrapped traceback for routine input
    validation."""
    venv_py = ROOT / ".venv" / "bin" / "python"
    if not venv_py.exists():
        pytest.skip(".venv not bootstrapped")
    code = (
        "import sys;"
        "sys.path.insert(0, \'lib\');"
        "from server import memory_write;"
        # `memory_write` is wrapped by FastMCP; access the raw callable
        # via the .fn attribute (FastMCP convention) or call as-is if
        # it remained callable. Use the underlying function directly to
        # bypass the protocol wrapper.
        "fn = getattr(memory_write, \'fn\', memory_write);"
        "out = fn(type=\'not-a-real-type\', name=\'x\', "
        "subject=\'foo\', description=\'d\', body=\'b\');"
        "assert isinstance(out, str) and out.startswith(\'error: \'), out;"
        "print(\'ok\')"
    )
    result = subprocess.run(
        [str(venv_py), "-c", code],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "ok" in result.stdout
