import json
from pathlib import Path
import shutil
import subprocess
import sys

import pytest


@pytest.mark.skipif(
    shutil.which("node") is None,
    reason="Node.js is required for cross-language rehearsal",
)
def test_full_synthetic_rehearsal_and_retry(tmp_path):
    root = Path(__file__).resolve().parents[1]
    command = [
        sys.executable,
        str(root / "scripts" / "rehearse.py"),
        "--output",
        str(tmp_path / "rehearsal"),
    ]
    first = subprocess.run(command, cwd=root, text=True, capture_output=True)
    assert first.returncode == 0, first.stdout + first.stderr
    result = json.loads(first.stdout.strip().splitlines()[-1])
    assert result["classes"] == 22
    assert result["exceptions_resolved"] >= 1
    second = subprocess.run(command, cwd=root, text=True, capture_output=True)
    assert second.returncode == 0, second.stdout + second.stderr
    assert (
        json.loads(second.stdout.strip().splitlines()[-1])["output_hash"]
        == result["output_hash"]
    )
    public = json.loads(
        (tmp_path / "rehearsal/publication/sanitized-roster.json").read_text(
            encoding="utf-8"
        )
    )
    assert len(public["entries"]) == 22
    assert all(
        not (set(row) & {"email", "contact_name", "proposals", "assigned_rank"})
        for row in public["entries"]
    )
