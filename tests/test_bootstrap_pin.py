from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent


def test_bootstrap_installs_mcp_below_2():
    for script in ("bin/memory", "bin/memory-server"):
        text = (ROOT / script).read_text()
        for line in text.splitlines():
            if "pip install" in line and not line.lstrip().startswith("#"):
                assert "'mcp>=1,<2'" in line or '"mcp>=1,<2"' in line, (script, line)
