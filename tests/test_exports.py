import hashlib
import json
import pytest
from helpers import sample, write_snapshot
from lottery.domain import ValidationError
from lottery.runs import RunStore
from lottery.exports import export_run, verify_export
from lottery.snapshot import canonical_json, load_snapshot


def test_export_roundtrip_and_byte_identical(tmp_path):
    directory = write_snapshot(
        tmp_path / "input", sample([[("a", "game"), ("b", "game"), ("c", "game")]], 1)
    )
    store = RunStore(tmp_path / "runs.sqlite")
    run = store.commit(directory, run_id="official")
    first = export_run(store, run.run_id, tmp_path / "export")
    second = export_run(store, run.run_id, tmp_path / "export2")
    assert {
        p.relative_to(first): p.read_bytes() for p in first.rglob("*") if p.is_file()
    } == {
        p.relative_to(second): p.read_bytes() for p in second.rglob("*") if p.is_file()
    }
    assert (
        verify_export(first, load_snapshot(directory))["output_hash"] == run.output_hash
    )
    (first / "assignments.csv").write_text("tampered\n")
    with pytest.raises(ValidationError):
        verify_export(first)


def test_rehashed_csv_tamper_still_rejected(tmp_path):
    directory = write_snapshot(
        tmp_path / "input", sample([[("a", "game"), ("b", "game"), ("c", "game")]], 1)
    )
    store = RunStore(tmp_path / "runs.sqlite")
    store.commit(directory, run_id="official")
    export = export_run(store, "official", tmp_path / "export")
    path = export / "assignments.csv"
    path.write_text(path.read_text().replace("official,", "other,"))
    audit_path = export / "lottery_audit.json"
    audit = json.loads(audit_path.read_bytes())
    audit["hash_manifest"]["assignments.csv"] = hashlib.sha256(
        path.read_bytes()
    ).hexdigest()
    audit_path.write_bytes(canonical_json(audit))
    with pytest.raises(ValidationError):
        verify_export(export)


def test_replacement_export_retains_policy_and_original_link(tmp_path):
    from lottery.runs import ReplacementAuthorization, ReplacementAuthority

    source = write_snapshot(
        tmp_path / "input", sample([[("a", "game"), ("b", "game"), ("c", "game")]], 1)
    )
    store = RunStore(tmp_path / "runs.sqlite")
    original = store.commit(source, run_id="original")
    auth = ReplacementAuthorization(
        "auth-1",
        "Approved correction",
        ("chair",),
        ReplacementAuthority("Adopted policy", ("chair",), 1),
    )
    replacement = store.replace(
        "original", source, run_id="replacement", authorization=auth
    )
    directory = export_run(store, replacement.run_id, tmp_path / "export")
    audit = verify_export(directory)
    assert audit["replacement"]["original_output_hash"] == original.output_hash
    assert audit["replacement"]["authorization"]["authority"]["required_approvers"] == 1
