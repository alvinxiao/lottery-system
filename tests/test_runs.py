from concurrent.futures import ThreadPoolExecutor
import sqlite3
import pytest
from lottery.runs import RunStore, PendingRun, RunConflict
from helpers import sample, write_snapshot


@pytest.fixture
def directory(tmp_path):
    return write_snapshot(
        tmp_path / "input", sample([[("a", "game"), ("b", "game"), ("c", "game")]], 1)
    )


def test_repeat_restart_and_event_alias(directory, tmp_path):
    path = tmp_path / "runs.sqlite"
    store = RunStore(path)
    first = store.commit(directory, run_id="r1")
    assert first.operator_approvals == ()
    assert RunStore(path).recover("r1") == first
    assert store.commit(directory, run_id="r2") == first
    with pytest.raises(RunConflict):
        store.commit(directory, run_id="r1", method="manual", manual_order=["c0"])
    assert store.history(first.event_id) == [
        {
            "run_id": "r1",
            "event_id": first.event_id,
            "input_hash": first.input_hash,
            "committed": 1,
        }
    ]
    with sqlite3.connect(path) as db:
        with pytest.raises(sqlite3.IntegrityError):
            db.execute("UPDATE runs SET result=NULL")
        with pytest.raises(sqlite3.IntegrityError):
            db.execute("DELETE FROM events")


def test_crash_preserves_seed_and_pending_has_no_preview(
    directory, tmp_path, monkeypatch
):
    import lottery.runs as module

    store = RunStore(tmp_path / "runs.sqlite")
    solve = module.optimize
    captured = []

    def fail(snapshot, order):
        captured.append(tuple(order))
        raise RuntimeError("simulated crash")

    monkeypatch.setattr(module, "optimize", fail)
    with pytest.raises(RuntimeError):
        store.commit(directory, run_id="r1")
    with pytest.raises(PendingRun):
        store.get("r1")
    monkeypatch.setattr(
        module, "new_seed", lambda: pytest.fail("Must reuse persisted seed")
    )
    monkeypatch.setattr(module, "optimize", solve)
    result = store.recover("r1")
    assert result.priority_order == captured[0]


def test_concurrent_draw_is_idempotent(directory, tmp_path, monkeypatch):
    import lottery.runs as module

    calls = []
    solve = module.optimize

    def counted(*args):
        calls.append(1)
        return solve(*args)

    monkeypatch.setattr(module, "optimize", counted)
    store = RunStore(tmp_path / "runs.sqlite")
    with ThreadPoolExecutor(2) as pool:
        results = list(
            pool.map(lambda name: store.commit(directory, run_id=name), ["one", "two"])
        )
    assert results[0] == results[1]
    assert len(calls) == 1


def test_manual_and_changed_snapshot(directory, tmp_path):
    store = RunStore(tmp_path / "runs.sqlite")
    result = store.commit(
        directory, run_id="manual", method="manual", manual_order=["c0"]
    )
    assert result.seed is None
    other = write_snapshot(
        tmp_path / "other", sample([[("d", "game"), ("e", "game"), ("f", "game")]], 1)
    )
    with pytest.raises(RunConflict):
        store.commit(other, run_id="new")


def test_infeasible_no_random_or_intent(tmp_path, monkeypatch):
    import lottery.runs as module

    directory = write_snapshot(
        tmp_path / "input", sample([[("a", "game"), ("b", "game"), ("c", "game")]], 0)
    )
    store = RunStore(tmp_path / "runs.sqlite")
    monkeypatch.setattr(
        module, "new_seed", lambda: pytest.fail("Infeasible inputs cannot draw")
    )
    with pytest.raises(module.Infeasible):
        store.commit(directory, run_id="bad")
    assert store.list_runs() == []


def test_explicit_replacement_authority_preserves_original(directory, tmp_path):
    from lottery.runs import ReplacementAuthorization, ReplacementAuthority
    from lottery.domain import ValidationError

    store = RunStore(tmp_path / "runs.sqlite")
    original = store.commit(directory, run_id="original")
    other = write_snapshot(
        tmp_path / "other", sample([[("d", "game"), ("e", "game"), ("f", "game")]], 1)
    )
    authority = ReplacementAuthority("PTA motion 42", ("chair", "principal"), 2)
    with pytest.raises(ValidationError):
        store.replace(
            "original",
            other,
            run_id="replacement",
            authorization=ReplacementAuthorization(
                "motion-42", "Corrected approved booth", ("chair",), authority
            ),
        )
    assert len(store.list_runs()) == 1
    auth = ReplacementAuthorization(
        "motion-42", "Corrected approved booth", ("chair", "principal"), authority
    )
    replacement = store.replace(
        "original",
        other,
        run_id="replacement",
        authorization=auth,
        operator_approvals=("admin-a", "admin-b"),
    )
    assert replacement.operator_approvals == ("admin-a", "admin-b")
    assert replacement.replacement.original_run_id == original.run_id
    assert replacement.replacement.original_output_hash == original.output_hash
    assert store.get("original") == original
    assert (
        store.replace("original", other, run_id="another-id", authorization=auth)
        == replacement
    )
    assert len(store.history(original.event_id)) == 2


def test_recovery_runtime_mismatch_fails_closed(directory, tmp_path, monkeypatch):
    import lottery.runs as module
    from lottery.domain import ValidationError

    store = RunStore(tmp_path / "runs.sqlite")

    def crash(*args):
        raise RuntimeError("crash")

    monkeypatch.setattr(module, "optimize", crash)
    with pytest.raises(RuntimeError):
        store.commit(directory, run_id="pending")
    monkeypatch.setattr(module, "ALGORITHM_VERSION", "different")
    with pytest.raises(ValidationError, match="runtime versions"):
        store.recover("pending")
    with pytest.raises(PendingRun):
        store.get("pending")


def test_failure_after_solve_before_final_commit_recovers_same_plan(
    directory, tmp_path, monkeypatch
):
    import lottery.runs as module

    store = RunStore(tmp_path / "runs.sqlite")
    original_event = store._event

    def crash(db, run_id, action):
        if action == "COMMITTED":
            raise RuntimeError("crash before commit")
        return original_event(db, run_id, action)

    monkeypatch.setattr(store, "_event", crash)
    with pytest.raises(RuntimeError):
        store.commit(directory, run_id="official")
    with pytest.raises(PendingRun):
        store.get("official")
    monkeypatch.setattr(store, "_event", original_event)
    monkeypatch.setattr(
        module, "new_seed", lambda: pytest.fail("Recovery cannot redraw")
    )
    assert store.recover("official") == store.recover("official")


@pytest.mark.parametrize(
    "run_id",
    [
        "../outside",
        "a/b",
        r"a\b",
        "a..b",
        "CON",
        "nul.txt",
        "LPT1",
        "trailing.",
        " leading",
        "=formula",
        "a\n",
    ],
)
def test_run_identifiers_are_portable_safe_paths(directory, tmp_path, run_id):
    from lottery.domain import ValidationError

    store = RunStore(tmp_path / "runs.sqlite")
    with pytest.raises(ValidationError):
        store.commit(directory, run_id=run_id)
    assert store.list_runs() == []


def test_sql_replace_cannot_bypass_immutability(directory, tmp_path):
    path = tmp_path / "runs.sqlite"
    store = RunStore(path)
    original = store.commit(directory, run_id="official")
    with sqlite3.connect(path) as db:
        with pytest.raises(sqlite3.IntegrityError):
            db.execute("INSERT OR REPLACE INTO runs SELECT * FROM runs")
        with pytest.raises(sqlite3.IntegrityError):
            db.execute("INSERT OR REPLACE INTO events SELECT * FROM events")
    assert store.get("official") == original


def test_actual_operator_signoffs_survive_recovery_and_export(tmp_path, monkeypatch):
    from dataclasses import replace
    import lottery.runs as module
    from lottery.exports import export_run, verify_export

    source = sample([[("a", "game"), ("b", "game"), ("c", "game")]], 1)
    source = replace(
        source,
        config=replace(source.config, approval_ids=("admin-a", "admin-b", "admin-c")),
    )
    directory = write_snapshot(tmp_path / "input", source)
    store = RunStore(tmp_path / "runs.sqlite")
    solve = module.optimize

    def crash(*args):
        raise RuntimeError("crash after intent")

    monkeypatch.setattr(module, "optimize", crash)
    with pytest.raises(RuntimeError):
        store.commit(
            directory,
            run_id="actual-signoffs",
            operator_approvals=("admin-a", "admin-c"),
        )
    monkeypatch.setattr(module, "optimize", solve)
    result = store.recover("actual-signoffs")
    assert result.approvals == ("admin-a", "admin-b", "admin-c")
    assert result.operator_approvals == ("admin-a", "admin-c")
    assert RunStore(store.path).get(result.run_id) == result
    export = export_run(store, result.run_id, tmp_path / "export")
    audit = verify_export(export)
    assert audit["approvals"] == ["admin-a", "admin-b", "admin-c"]
    assert audit["operator_approvals"] == ["admin-a", "admin-c"]
    with pytest.raises(RunConflict, match="signoffs"):
        store.commit(
            directory, run_id="alias", operator_approvals=("admin-a", "admin-b")
        )


@pytest.mark.parametrize(
    "approvals", [(), ("admin-a",), ("admin-a", "admin-a"), ("admin-a", "unknown")]
)
def test_invalid_operator_signoffs_create_no_intent(directory, tmp_path, approvals):
    from lottery.domain import ValidationError

    store = RunStore(tmp_path / "runs.sqlite")
    with pytest.raises(ValidationError):
        store.commit(directory, run_id="signoffs", operator_approvals=approvals)
    assert store.list_runs() == []
