"""Pytest fixtures for memory tests."""
import sys
from pathlib import Path

# Add lib/ to path so tests can import providers, memory_reader, memory_writer
sys.path.insert(0, str(Path(__file__).parent.parent / "lib"))
