import json
import pytest
from lottery.desktop import DesktopSession, State
from lottery.domain import ValidationError
from lottery.runs import RunStore
from lottery.snapshot import canonical_json
from helpers import sample, write_snapshot


@pytest.fixture
def session(tmp_path):
    source = write_snapshot(
        tmp_path / "source", sample([[("a", "game"), ("b", "game"), ("c", "game")]], 1)
    )
    result = DesktopSession(RunStore(tmp_path / "runs.sqlite3"), tmp_path / "local")
    result.import_snapshot(source)
    return result


def freeze(session):
    assert session.check_feasibility().feasible
    session.approve("admin-a")
    assert session.state == State.FEASIBLE
    session.approve("admin-b")
    assert session.state == State.APPROVED_FROZEN


def test_full_lifecycle_restart_and_repeat_export(session, tmp_path):
    assert session.state == State.VALIDATED
    freeze(session)
    run = session.commit("official")
    assert session.state == State.COMMITTED
    assert session.result == run
    restarted = DesktopSession(RunStore(session.store.path))
    assert restarted.open_run("official") == run
    assert restarted.export(tmp_path / "export") == restarted.export(
        tmp_path / "export"
    )
    assert restarted.state == State.EXPORTED
    with pytest.raises(ValidationError):
        restarted.commit("reroll")


def test_configuration_is_copy_and_invalidates_approval(session):
    old = session.directory
    session.check_feasibility()
    session.approve("admin-a")
    session.configure(1, 1, 0)
    assert session.directory != old
    assert session.approvals == []
    assert session.state == State.VALIDATED
    with pytest.raises(ValidationError):
        session.approve("admin-b")
    with pytest.raises(ValidationError):
        session.configure(22, 9, 13)


def test_manual_validation_two_distinct_approvals_and_freeze(session):
    with pytest.raises(ValidationError):
        session.set_method("manual", [])
    session.set_method("manual", ["c0"])
    session.check_feasibility()
    session.approve("admin-a")
    with pytest.raises(ValidationError):
        session.approve("admin-a")
    with pytest.raises(ValidationError):
        session.approve("unlisted")
    session.approve("admin-b")
    with pytest.raises(ValidationError):
        session.set_method("automatic")
    with pytest.raises(ValidationError):
        session.configure(1, 1, 0)
    assert session.commit("manual").seed is None


def test_changed_input_invalidates_frozen_approval(session):
    freeze(session)
    path = session.directory / "config.json"
    raw = json.loads(path.read_text())
    raw["event_id"] = "changed-event"
    path.write_bytes(canonical_json(raw))
    with pytest.raises(ValidationError, match="Input changed"):
        session.commit("bad")
    assert session.state == State.DRAFT_IMPORT
    assert session.approvals == []
    assert session.result is None


def test_crash_has_no_preview_and_explicit_recovery(session, monkeypatch):
    import lottery.runs as module

    freeze(session)
    original = module.optimize
    monkeypatch.setattr(
        module, "optimize", lambda *args: (_ for _ in ()).throw(RuntimeError("crash"))
    )
    with pytest.raises(RuntimeError):
        session.commit("recover-me")
    assert session.state == State.COMMITTING
    assert session.result is None
    with pytest.raises(ValidationError):
        session.export("not-visible")
    monkeypatch.setattr(module, "optimize", original)
    monkeypatch.setattr(
        module, "new_seed", lambda: pytest.fail("No new randomness in recovery")
    )
    restarted = DesktopSession(RunStore(session.store.path))
    recovered = restarted.recover("recover-me")
    assert recovered == restarted.open_run("recover-me")
    assert restarted.state == State.COMMITTED


def test_method_change_clears_approvals(session):
    session.check_feasibility()
    session.approve("admin-a")
    session.set_method("manual", ["c0"])
    assert session.approvals == []
    assert session.state == State.FEASIBLE


def test_corrupt_input_clears_approvals_and_preview(session):
    freeze(session)
    (session.directory / "classes.csv").write_text("tampered\n")
    with pytest.raises(ValidationError, match="Input changed"):
        session.commit("bad")
    assert session.state == State.DRAFT_IMPORT
    assert session.approvals == []
    assert session.result is None


def test_feasibility_never_generates_draw(session, monkeypatch):
    import lottery.runs as module

    monkeypatch.setattr(
        module, "new_seed", lambda: pytest.fail("Feasibility must not randomize")
    )
    assert session.check_feasibility().feasible
    assert session.result is None
    assert session.store.list_runs() == []


def test_preintent_validation_failure_can_retry(session):
    freeze(session)
    with pytest.raises(ValidationError):
        session.commit("")
    assert session.state == State.APPROVED_FROZEN
    assert session.store.list_runs() == []
    assert session.commit("valid").run_id == "valid"


def test_actual_operator_signoffs_are_separate_from_source_approvals(session):
    path = session.directory / "config.json"
    config = json.loads(path.read_text())
    config["approval_ids"] = ["admin-a", "admin-b", "admin-c"]
    path.write_bytes(canonical_json(config))
    session.import_snapshot(session.directory)
    session.check_feasibility()
    session.approve("admin-a")
    session.approve("admin-c")
    result = session.commit("actual-signoffs")
    assert result.approvals == ("admin-a", "admin-b", "admin-c")
    assert result.operator_approvals == ("admin-a", "admin-c")
