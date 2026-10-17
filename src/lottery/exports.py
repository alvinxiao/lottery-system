"""Portable deterministic exports with independent consistency checks.

Hashes detect corruption; they do not authenticate an administrator's identity.
"""

import csv
from dataclasses import asdict
import hashlib
import io
import json
from pathlib import Path

from .domain import ValidationError
from .priority import automatic_priority, manual_priority
from .runs import parse_run, snapshot_from_files
from .snapshot import canonical_json, load_snapshot
from .verify import verify_solution


def _csv(run):
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(["run_id", "class_id", "booth_id", "category", "assigned_rank"])
    for a in run.assignments:
        writer.writerow(
            [run.run_id, a.class_id, a.booth_id, a.category.value, a.assigned_rank]
        )
    return output.getvalue().encode("utf-8")


def _report(run):
    return {
        "schema_version": 1,
        "run_id": run.run_id,
        "input_hash": run.input_hash,
        "output_hash": run.output_hash,
        "feasible": True,
        "status": "OPTIMAL",
        "objective_vector": run.objective_vector,
    }


def _summary(run):
    return f"Official lottery {run.run_id}\nEvent: {run.event_id}\nInput SHA-256: {run.input_hash}\nOutput SHA-256: {run.output_hash}\nStatus: OPTIMAL\nClasses assigned: {len(run.assignments)}\n".encode(
        "utf-8"
    )


def export_run(store, run_id, destination_directory):
    run = store.get(run_id)
    files = {
        "snapshot/" + name: data for name, data in store.snapshot_files(run_id).items()
    }
    files |= {
        "assignments.csv": _csv(run),
        "feasibility_report.json": canonical_json(_report(run)),
        "lottery_summary.txt": _summary(run),
    }
    snapshot = snapshot_from_files(
        {
            name.removeprefix("snapshot/"): value.decode("utf-8")
            for name, value in files.items()
            if name.startswith("snapshot/")
        }
    )
    audit = run.to_dict() | {
        "input_snapshot": {
            "classes": [asdict(c) for c in snapshot.classes],
            "proposals": [asdict(p) for p in snapshot.proposals],
            "config": asdict(snapshot.config),
        },
        "hash_manifest": {
            name: hashlib.sha256(data).hexdigest() for name, data in files.items()
        },
    }
    files["lottery_audit.json"] = canonical_json(audit)
    root = Path(destination_directory)
    root.mkdir(parents=True, exist_ok=True)
    for name, data in files.items():
        path = root / name
        if path.is_symlink() or path.parent.is_symlink():
            raise ValidationError("Export paths cannot be symlinks")
        path.parent.mkdir(exist_ok=True)
        if path.exists() and path.read_bytes() != data:
            raise ValidationError(
                "Destination contains different export; choose an empty directory"
            )
    for name, data in files.items():
        (root / name).write_bytes(data)
    verify_export(root)
    return root


def verify_export(directory, expected_snapshot=None):
    root = Path(directory)
    try:
        path = root / "lottery_audit.json"
        if path.is_symlink() or (root / "snapshot").is_symlink():
            raise ValidationError("Export members cannot be symlinks")
        data = path.read_bytes()
        audit = json.loads(data)
        if not isinstance(audit, dict) or not isinstance(
            audit.get("hash_manifest"), dict
        ):
            raise ValidationError("Audit and hash manifest must be objects")
        if canonical_json(audit) != data:
            raise ValidationError("Audit must be canonical JSON")
        core = {
            k: v
            for k, v in audit.items()
            if k not in ("input_snapshot", "hash_manifest")
        }
        run = parse_run(core)
        manifest = audit["hash_manifest"]
        expected = {
            "assignments.csv",
            "feasibility_report.json",
            "lottery_summary.txt",
            "snapshot/config.json",
            "snapshot/classes.csv",
            "snapshot/approved_proposals.csv",
        }
        if "snapshot/booths.csv" in manifest:
            expected.add("snapshot/booths.csv")
        if set(manifest) != expected:
            raise ValidationError("Unknown or missing export members")
        for name, sha in manifest.items():
            member = root / name
            if (
                member.is_symlink()
                or hashlib.sha256(member.read_bytes()).hexdigest() != sha
            ):
                raise ValidationError("Export member hash mismatch: " + name)
        snapshot = load_snapshot(root / "snapshot")
        if (
            snapshot.input_hash != run.input_hash
            or snapshot.config.event_id != run.event_id
            or snapshot.config.approval_ids != run.approvals
        ):
            raise ValidationError("Run and snapshot disagree")
        if expected_snapshot is not None and snapshot != expected_snapshot:
            raise ValidationError("Export does not match expected frozen snapshot")
        embedded = {
            "classes": [asdict(c) for c in snapshot.classes],
            "proposals": [asdict(p) for p in snapshot.proposals],
            "config": asdict(snapshot.config),
        }
        if canonical_json(embedded) != canonical_json(audit["input_snapshot"]):
            raise ValidationError("Embedded snapshot differs from files")
        ids = [c.class_id for c in snapshot.classes]
        if run.method == "automatic":
            order = automatic_priority(ids, run.seed)
        elif run.method == "manual" and run.seed is None:
            order = manual_priority(ids, run.priority_order)
        else:
            raise ValidationError("Invalid randomization method")
        if tuple(order) != run.priority_order:
            raise ValidationError("Priority disagrees with seed")
        verify_solution(
            snapshot, run.assignments, run.priority_order, run.objective_vector
        )
        if (
            (root / "assignments.csv").read_bytes() != _csv(run)
            or (root / "feasibility_report.json").read_bytes()
            != canonical_json(_report(run))
            or (root / "lottery_summary.txt").read_bytes() != _summary(run)
        ):
            raise ValidationError("Export files disagree with committed run")
        return audit
    except ValidationError:
        raise
    except (OSError, ValueError, TypeError, KeyError) as exc:
        raise ValidationError(f"Invalid export: {exc}") from exc
