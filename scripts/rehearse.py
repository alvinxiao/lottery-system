"""Exercise the offline desktop and Google core with fictional data only."""

import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys

from lottery.desktop import DesktopSession
from lottery.exports import verify_export
from lottery.runs import RunStore


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("rehearsal-output"))
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    output = args.output.absolute()
    if output.is_symlink() or any(p.is_symlink() for p in output.parents):
        parser.error("Choose a rehearsal directory without symbolic links")
    marker = output / ".synthetic-lottery-rehearsal"
    if output.exists() and any(output.iterdir()) and not marker.is_file():
        parser.error(
            "Existing output is not a generated rehearsal; choose an empty directory"
        )
    if output.exists() and any(p.is_symlink() for p in output.rglob("*")):
        parser.error("Rehearsal output must not contain symbolic links")
    node = shutil.which("node")
    if not node:
        parser.error("Install Node.js 20 or newer for the Google workflow rehearsal")
    fixture = root / "sample-data" / "google-intake.json"
    sample = json.loads(fixture.read_text(encoding="utf-8"))
    if sample.get("demo_only") is not True or sample.get("dry_run") is not True:
        parser.error("The rehearsal requires the checked-in fictional dry-run fixture")
    if any(
        not row["email"].endswith("@example.invalid") for row in sample["submissions"]
    ):
        parser.error("Rehearsal contacts must use the reserved example.invalid domain")
    output.mkdir(parents=True, exist_ok=True)
    marker.write_text(
        "Synthetic data only. No Google services or mail are called.\n",
        encoding="utf-8",
    )
    bridge = root / "google" / "scripts" / "rehearse.js"
    subprocess.run(
        [node, str(bridge), "prepare", str(fixture), str(output / "intake")],
        check=True,
        cwd=root,
    )
    store = RunStore(output / "runs.sqlite3")
    session = DesktopSession(store, workspace=output / "desktop")
    snapshot = session.import_snapshot(output / "intake" / "frozen")
    if not session.check_feasibility().feasible:
        raise RuntimeError("Synthetic 22-class event must be feasible")
    session.set_method("automatic")
    for admin in snapshot.config.approval_ids[:2]:
        session.approve(admin)
    run = session.commit("synthetic-rehearsal")
    session.export(output / "official-export")
    if RunStore(store.path).get(run.run_id) != run:
        raise RuntimeError("Restart changed the committed draw")
    verify_export(output / "official-export", snapshot)
    subprocess.run(
        [
            node,
            str(bridge),
            "complete",
            str(output / "intake" / "state.json"),
            str(output / "official-export"),
            str(output / "publication"),
        ],
        check=True,
        cwd=root,
    )
    summary = json.loads(
        (output / "publication" / "summary.json").read_text(encoding="utf-8")
    )
    if summary["classes"] != 22 or summary["explicit"] + summary["auto_accepted"] != 22:
        raise RuntimeError(
            "Not every synthetic class reached an accepted final assignment"
        )
    print(
        json.dumps(
            {
                "result": "PASS",
                "output": str(output),
                "run_id": run.run_id,
                "output_hash": run.output_hash,
                **summary,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
