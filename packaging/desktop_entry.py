"""Standalone launcher; diagnostic paths run before starting the desktop UI."""

import argparse
from pathlib import Path
import sys


def self_test(snapshot_path, destination):
    from lottery.desktop import DesktopSession
    from lottery.exports import verify_export
    from lottery.runs import RunStore

    root = Path(destination)
    root.mkdir(parents=True, exist_ok=True)
    database = root / "runs.sqlite3"
    session = DesktopSession(RunStore(database), workspace=root / "workspace")
    snapshot = session.import_snapshot(snapshot_path)
    if not session.check_feasibility().feasible:
        raise RuntimeError("Sample must be feasible")
    session.set_method("automatic")
    for admin in snapshot.config.approval_ids[:2]:
        session.approve(admin)
    run = session.commit("packaged-smoke")
    # Construct a new store and desktop session to prove restart cannot reroll.
    restarted = DesktopSession(RunStore(database), workspace=root / "restart")
    recovered = restarted.open_run(run.run_id)
    if recovered != run:
        raise RuntimeError("Restart changed committed result")
    assignments = recovered.assignments
    if len(assignments) != snapshot.config.class_count:
        raise RuntimeError("Incomplete assignment")
    if len({a.booth_id for a in assignments}) != len(assignments):
        raise RuntimeError("Duplicate booth assignment")
    if (
        sum(a.category.value == "game" for a in assignments)
        != snapshot.config.game_target
    ):
        raise RuntimeError("Incorrect game quota")
    if (
        sum(a.category.value == "food" for a in assignments)
        != snapshot.config.food_target
    ):
        raise RuntimeError("Incorrect food quota")
    destination = root / "export"
    restarted.export(destination)
    before = {
        str(p.relative_to(destination)): p.read_bytes()
        for p in destination.rglob("*")
        if p.is_file()
    }
    restarted.export(destination)
    after = {
        str(p.relative_to(destination)): p.read_bytes()
        for p in destination.rglob("*")
        if p.is_file()
    }
    if before != after or verify_export(destination)["output_hash"] != run.output_hash:
        raise RuntimeError("Export changed committed result")
    (root / "smoke-passed.txt").write_text(
        f"frozen={bool(getattr(sys, 'frozen', False))}\nclasses={len(assignments)}\noutput_hash={run.output_hash}\n",
        encoding="utf-8",
    )


def main():
    parser = argparse.ArgumentParser(description="PTA Carnival Lottery desktop")
    parser.add_argument("--self-test", type=Path, metavar="SNAPSHOT")
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--database", type=Path, help="Use a separate local run database"
    )
    parser.add_argument("--gui-smoke", action="store_true")
    parser.add_argument("--require-frozen", action="store_true")
    args = parser.parse_args()
    if args.require_frozen and not getattr(sys, "frozen", False):
        parser.error("This check requires the bundled executable")
    if args.self_test:
        if args.output is None:
            parser.error("--self-test requires --output")
        self_test(args.self_test.resolve(), args.output.resolve())
    elif args.gui_smoke:
        from lottery.gui import smoke_test

        smoke_test()
    else:
        from lottery.gui import main as gui_main

        gui_main(["--database", str(args.database)] if args.database else [])


if __name__ == "__main__":
    main()
