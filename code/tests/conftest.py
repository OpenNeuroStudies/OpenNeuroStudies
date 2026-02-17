"""Root conftest.py — shared fixtures and path setup for all tests."""

import subprocess
import sys
from pathlib import Path

# Make workflow.lib importable: add code/ to sys.path so `workflow.lib` resolves
sys.path.insert(0, str(Path(__file__).parent.parent))

# Repository root — ask git, avoids any __file__ counting ambiguity
REPO_ROOT = Path(
    subprocess.check_output(
        ["git", "rev-parse", "--show-toplevel"],
        text=True,
        cwd=Path(__file__).parent,
    ).strip()
)
