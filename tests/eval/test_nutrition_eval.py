from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_run_evals_cli_passes():
    root = Path(__file__).resolve().parents[2]
    completed = subprocess.run(
        [sys.executable, "scripts/run_evals.py", "--eval", "nutrition"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["passed"] is True
    assert payload["num_cases"] == 20
