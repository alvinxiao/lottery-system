"""Exercise the actual manual rehearsal artifacts, including their negative case."""

import importlib.util
import json
from pathlib import Path

import pytest

from lottery.domain import Category
from lottery.snapshot import load_snapshot
from lottery.solver import feasibility, optimize

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "generate_sample_data", ROOT / "scripts/generate_sample_data.py"
)
generator = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(generator)


def test_ready_to_draw_has_default_quota_matching_and_rank_conflicts():
    snapshot = load_snapshot(ROOT / "sample-data/ready-to-draw")
    assert len(snapshot.classes) == 22
    assert len(snapshot.proposals) == 66
    assert feasibility(snapshot).feasible
    priority = (ROOT / "sample-data/manual-priority.txt").read_text().splitlines()
    solution = optimize(snapshot, priority)
    assert len(solution.assignments) == 22
    assert len({a.booth_id for a in solution.assignments}) == 22
    assert sum(a.category == Category.GAME for a in solution.assignments) == 9
    assert sum(a.category == Category.FOOD for a in solution.assignments) == 13
    first_choices = [p.booth_id for p in snapshot.proposals if p.rank == 1]
    assert len(set(first_choices)) < len(first_choices)
    assert any(a.assigned_rank > 1 for a in solution.assignments)
    booths = (ROOT / "sample-data/ready-to-draw/booths.csv").read_text(encoding="utf-8")
    assert "饺子" in booths and "豆花" in booths and "炸酱面" in booths


def test_infeasible_sample_exceeds_food_slots_without_invalid_input():
    snapshot = load_snapshot(ROOT / "sample-data/infeasible")
    food_only = [
        c
        for c in snapshot.classes
        if all(
            p.category == Category.FOOD
            for p in snapshot.proposals
            if p.class_id == c.class_id
        )
    ]
    assert len(food_only) == 14
    report = feasibility(snapshot)
    assert not report.feasible
    assert set(report.correction_candidates) == {c.class_id for c in snapshot.classes}


def test_generator_reproduces_checked_in_bytes_and_is_idempotent(tmp_path):
    generator.generate(tmp_path)
    generator.generate(tmp_path)
    for relative, expected in generator.generated_files().items():
        assert (tmp_path / relative).read_bytes() == expected
        assert (ROOT / "sample-data" / relative).read_bytes() == expected


def test_generator_preserves_existing_manual_changes_and_unrelated_files(tmp_path):
    generator.generate(tmp_path)
    altered = tmp_path / "ready-to-draw/classes.csv"
    altered.write_text("My manual changes\n")
    with pytest.raises(ValueError, match="different or unrecognized"):
        generator.generate(tmp_path)
    assert altered.read_text() == "My manual changes\n"
    extra = tmp_path / "personal-notes.txt"
    extra.write_text("Keep this")
    generator.generate(tmp_path, force=True)
    assert extra.read_text() == "Keep this"


def test_new_event_id_rehashes_config_without_changing_proposals(tmp_path):
    generator.generate(tmp_path, event_id="DEMO-carnival-new-rehearsal")
    custom = load_snapshot(tmp_path / "ready-to-draw")
    original = load_snapshot(ROOT / "sample-data/ready-to-draw")
    assert custom.config.event_id == "DEMO-carnival-new-rehearsal"
    assert custom.input_hash != original.input_hash
    assert custom.proposals == original.proposals


def test_mock_google_contacts_cannot_receive_live_mail():
    intake = json.loads((ROOT / "sample-data/google-intake.json").read_text(encoding="utf-8"))
    assert intake["demo_only"] is True
    assert intake["dry_run"] is True
    assert len(intake["submissions"]) == 22
    for submission in intake["submissions"]:
        assert submission["email"].endswith("@example.invalid")
        assert len(submission["proposals"]) == 3
    assert all(
        admin["email"].endswith("@example.invalid")
        for admin in intake["administrators"]
    )


def test_generator_rejects_symbolic_links_even_with_force(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    output = tmp_path / "output"
    output.mkdir()
    try:
        (output / "ready-to-draw").symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("Platform does not permit creating test symbolic links")
    with pytest.raises(ValueError, match="symbolic links"):
        generator.generate(output, force=True)
    assert not list(outside.iterdir())


def test_generator_rejects_unsafe_event_id_without_writing(tmp_path):
    with pytest.raises(ValueError, match="spreadsheet-safe"):
        generator.generate(tmp_path / "output", event_id="=FORMULA")
    assert not (tmp_path / "output").exists()
