"""Durable official draws. Pending plans survive failures without new randomness."""

from collections.abc import Sequence
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
from importlib.metadata import version
import json
import re
from pathlib import Path
import sqlite3
import tempfile

from .domain import Assignment, Category, ValidationError
from .priority import ALGORITHM_VERSION, automatic_priority, manual_priority, new_seed
from .snapshot import canonical_json, load_snapshot
from .solver import optimize, feasibility, Infeasible, SolveIncomplete
from .verify import verify_solution


class PendingRun(RuntimeError):
    pass


class RunConflict(ValidationError):
    pass


def validate_run_id(value):
    """Run IDs are portable directory names as well as semantic identifiers."""
    reserved = {
        "CON",
        "PRN",
        "AUX",
        "NUL",
        *(f"COM{i}" for i in range(1, 10)),
        *(f"LPT{i}" for i in range(1, 10)),
    }
    if (
        not isinstance(value, str)
        or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", value)
        or ".." in value
        or value.endswith(".")
        or value.split(".")[0].upper() in reserved
    ):
        raise ValidationError(
            "Run ID must be a portable identifier (letters, digits, dots, underscores, hyphens; no traversal or reserved names)"
        )


def validate_operator_approvals(values, source_approvals, *, allow_empty=True):
    if not isinstance(values, tuple) or any(
        not isinstance(value, str) for value in values
    ):
        raise ValidationError(
            "Operator approvals must be an immutable sequence of administrator IDs"
        )
    if allow_empty and not values:
        return
    if (
        len(values) < 2
        or len(set(values)) != len(values)
        or not set(values) <= set(source_approvals)
    ):
        raise ValidationError(
            "Operator signoff requires at least two distinct source-approved administrator IDs"
        )


def digest(value):
    return hashlib.sha256(canonical_json(value)).hexdigest()


@dataclass(frozen=True)
class ReplacementAuthority:
    """Explicit externally approved policy; no implicit authorized administrators."""

    policy_reference: str
    authorized_approvers: tuple[str, ...]
    required_approvers: int


@dataclass(frozen=True)
class ReplacementAuthorization:
    authorization_id: str
    reason: str
    approvers: tuple[str, ...]
    authority: ReplacementAuthority

    def validate(self):
        authority = self.authority
        if (
            not isinstance(authority, ReplacementAuthority)
            or not isinstance(self.approvers, tuple)
            or not isinstance(authority.authorized_approvers, tuple)
        ):
            raise ValidationError(
                "Replacement policy and approvals must be immutable typed records"
            )
        text = (
            self.authorization_id,
            self.reason,
            *self.approvers,
            authority.policy_reference,
            *authority.authorized_approvers,
        )
        if any(
            not isinstance(v, str)
            or not v.strip()
            or v != v.strip()
            or any(ord(c) < 32 for c in v)
            or v.startswith(("=", "+", "-", "@"))
            for v in text
        ):
            raise ValidationError("Replacement authorization needs safe nonempty text")
        if (
            type(authority.required_approvers) is not int
            or authority.required_approvers < 1
            or authority.required_approvers > len(authority.authorized_approvers)
            or len(set(authority.authorized_approvers))
            != len(authority.authorized_approvers)
        ):
            raise ValidationError(
                "Replacement authority must explicitly define its approval threshold"
            )
        if (
            len(set(self.approvers)) != len(self.approvers)
            or len(self.approvers) < authority.required_approvers
            or not set(self.approvers) <= set(authority.authorized_approvers)
        ):
            raise ValidationError(
                "Replacement authorization does not satisfy the configured authority"
            )


@dataclass(frozen=True)
class ReplacementRecord:
    original_run_id: str
    original_output_hash: str
    authorization: ReplacementAuthorization


@dataclass(frozen=True)
class CommittedRun:
    run_id: str
    event_id: str
    input_hash: str
    assignments: tuple[Assignment, ...]
    priority_order: tuple[str, ...]
    method: str
    seed: str | None
    objective_vector: tuple[int, ...]
    committed_at: str
    output_hash: str
    approvals: tuple[str, ...]
    algorithm_version: str
    solver_version: str
    app_version: str
    replacement: ReplacementRecord | None = None
    operator_approvals: tuple[str, ...] = ()

    def to_dict(self):
        return asdict(self) | {
            "schema_version": 1,
            "record_type": "committed_run",
            "status": "OPTIMAL",
        }


def parse_run(raw):
    fields = set(CommittedRun.__dataclass_fields__) | {
        "schema_version",
        "record_type",
        "status",
    }
    if (
        not isinstance(raw, dict)
        or set(raw) != fields
        or raw["schema_version"] != 1
        or raw["record_type"] != "committed_run"
        or raw["status"] != "OPTIMAL"
    ):
        raise ValidationError("Invalid committed run record")
    raw = dict(raw)
    if type(raw["schema_version"]) is not int:
        raise ValidationError("Invalid record schema version")
    for key in ("schema_version", "record_type", "status"):
        raw.pop(key)
    try:
        if any(
            not isinstance(raw[key], (list, tuple))
            for key in (
                "assignments",
                "priority_order",
                "objective_vector",
                "approvals",
                "operator_approvals",
            )
        ):
            raise ValidationError("Run collection fields must be arrays")
        if raw["replacement"] is not None:
            replacement = dict(raw["replacement"])
            auth = dict(replacement["authorization"])
            authority = dict(auth["authority"])
            authority["authorized_approvers"] = tuple(authority["authorized_approvers"])
            auth["authority"] = ReplacementAuthority(**authority)
            auth["approvers"] = tuple(auth["approvers"])
            auth = ReplacementAuthorization(**auth)
            auth.validate()
            replacement["authorization"] = auth
            raw["replacement"] = ReplacementRecord(**replacement)
        raw["assignments"] = tuple(
            Assignment(**(a | {"category": Category(a["category"])}))
            for a in raw["assignments"]
        )
        for key in (
            "priority_order",
            "objective_vector",
            "approvals",
            "operator_approvals",
        ):
            raw[key] = tuple(raw[key])
        result = CommittedRun(**raw)
        validate_run_id(result.run_id)
        validate_operator_approvals(result.operator_approvals, result.approvals)
        if result.replacement is not None:
            validate_run_id(result.replacement.original_run_id)
            original_hash = result.replacement.original_output_hash
            if (
                not isinstance(original_hash, str)
                or not re.fullmatch("[a-f0-9]{64}", original_hash)
                or result.replacement.original_run_id == result.run_id
            ):
                raise ValidationError("Invalid original run linkage")
        strings = (
            result.run_id,
            result.event_id,
            result.input_hash,
            result.committed_at,
            result.output_hash,
            result.algorithm_version,
            result.solver_version,
            result.app_version,
            *result.priority_order,
            *result.approvals,
        )
        if any(
            not isinstance(v, str)
            or not v.strip()
            or v != v.strip()
            or any(ord(c) < 32 for c in v)
            or v.startswith(("=", "+", "-", "@"))
            for v in strings
        ):
            raise ValidationError("Unsafe or malformed run text")
        if any(type(v) is not int for v in result.objective_vector) or len(
            result.objective_vector
        ) != 3 + len(result.priority_order):
            raise ValidationError("Invalid objective values")
        if (
            not result.priority_order
            or len(set(result.priority_order)) != len(result.priority_order)
            or len(set(result.approvals)) != len(result.approvals)
            or len(result.approvals) < 2
        ):
            raise ValidationError(
                "Priority and approvals must be unique complete identifiers"
            )
        if (
            len(result.assignments) != len(result.priority_order)
            or {a.class_id for a in result.assignments} != set(result.priority_order)
            or len({a.booth_id for a in result.assignments}) != len(result.assignments)
            or any(
                type(a.assigned_rank) is not int or a.assigned_rank not in (1, 2, 3)
                for a in result.assignments
            )
        ):
            raise ValidationError("Malformed assignment records")
        if result.method not in ("automatic", "manual"):
            raise ValidationError("Invalid run method")
        if result.method == "automatic" and (
            not isinstance(result.seed, str)
            or len(result.seed) != 64
            or any(c not in "0123456789abcdef" for c in result.seed)
        ):
            raise ValidationError("Automatic draw requires a 256-bit seed")
        if any(
            len(value) != 64 or any(c not in "0123456789abcdef" for c in value)
            for value in (result.input_hash, result.output_hash)
        ):
            raise ValidationError("Invalid SHA-256 digest")
        if result.method == "manual" and result.seed is not None:
            raise ValidationError("Manual draw cannot have a seed")
        timestamp = datetime.fromisoformat(result.committed_at.replace("Z", "+00:00"))
        if timestamp.tzinfo is None:
            raise ValidationError("Commit timestamp requires a timezone")
        if (
            digest({k: v for k, v in result.to_dict().items() if k != "output_hash"})
            != result.output_hash
        ):
            raise ValidationError("Committed run hash mismatch")
        return result
    except (TypeError, ValueError, KeyError) as exc:
        raise ValidationError("Malformed committed run") from exc


def snapshot_from_files(files):
    with tempfile.TemporaryDirectory() as directory:
        for name, content in files.items():
            if name not in (
                "config.json",
                "classes.csv",
                "approved_proposals.csv",
                "booths.csv",
            ):
                raise ValidationError("Unexpected snapshot member")
            Path(directory, name).write_text(content, encoding="utf-8", newline="")
        return load_snapshot(directory)


class RunStore:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS runs(run_id TEXT PRIMARY KEY, event_id TEXT NOT NULL,
                    input_hash TEXT NOT NULL, plan TEXT NOT NULL, result TEXT, event_key TEXT UNIQUE NOT NULL);
                CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY, run_id TEXT NOT NULL,
                    action TEXT NOT NULL, timestamp TEXT NOT NULL);
                CREATE TRIGGER IF NOT EXISTS no_replace_run BEFORE INSERT ON runs
                    WHEN EXISTS(SELECT 1 FROM runs WHERE run_id=NEW.run_id OR event_key=NEW.event_key)
                    BEGIN SELECT RAISE(ABORT,'Run already exists'); END;
                CREATE TRIGGER IF NOT EXISTS no_replace_event BEFORE INSERT ON events
                    WHEN EXISTS(SELECT 1 FROM events WHERE id=NEW.id)
                    BEGIN SELECT RAISE(ABORT,'Audit event already exists'); END;
                CREATE TRIGGER IF NOT EXISTS immutable_run BEFORE UPDATE ON runs
                    WHEN OLD.result IS NOT NULL BEGIN SELECT RAISE(ABORT,'Committed run is immutable'); END;
                CREATE TRIGGER IF NOT EXISTS immutable_intent BEFORE UPDATE ON runs
                    WHEN OLD.run_id != NEW.run_id OR OLD.event_id != NEW.event_id OR OLD.input_hash != NEW.input_hash OR OLD.plan != NEW.plan OR OLD.event_key != NEW.event_key
                    BEGIN SELECT RAISE(ABORT,'Run intent is immutable'); END;
                CREATE TRIGGER IF NOT EXISTS no_delete_run BEFORE DELETE ON runs
                    BEGIN SELECT RAISE(ABORT,'Run intent cannot be deleted'); END;
                CREATE TRIGGER IF NOT EXISTS no_update_event BEFORE UPDATE ON events
                    BEGIN SELECT RAISE(ABORT,'Audit is append only'); END;
                CREATE TRIGGER IF NOT EXISTS no_delete_event BEFORE DELETE ON events
                    BEGIN SELECT RAISE(ABORT,'Audit is append only'); END;
            """)

    @contextmanager
    def _connect(self):
        db = sqlite3.connect(self.path, timeout=120, isolation_level=None)
        try:
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA synchronous=FULL")
            db.execute("PRAGMA journal_mode=DELETE")
            yield db
        finally:
            db.close()

    def _event(self, db, run_id, action):
        db.execute(
            "INSERT INTO events(run_id,action,timestamp) VALUES(?,?,?)",
            (run_id, action, datetime.now(timezone.utc).isoformat()),
        )

    def commit(
        self,
        snapshot_directory,
        *,
        run_id: str,
        method="automatic",
        manual_order: Sequence[str] | None = None,
        operator_approvals: tuple[str, ...] | None = None,
    ):
        return self._commit(
            snapshot_directory,
            run_id=run_id,
            method=method,
            manual_order=manual_order,
            replacement=None,
            operator_approvals=operator_approvals,
        )

    def replace(
        self,
        original_run_id,
        snapshot_directory,
        *,
        run_id: str,
        authorization: ReplacementAuthorization,
        method="automatic",
        manual_order: Sequence[str] | None = None,
        operator_approvals: tuple[str, ...] | None = None,
    ):
        if not isinstance(authorization, ReplacementAuthorization):
            raise ValidationError("Explicit replacement authorization is required")
        authorization.validate()
        original = self.get(original_run_id)
        snapshot = load_snapshot(snapshot_directory)
        if snapshot.config.event_id != original.event_id:
            raise RunConflict("Replacement must belong to the original event")
        replacement = ReplacementRecord(
            original.run_id, original.output_hash, authorization
        )
        return self._commit(
            snapshot_directory,
            run_id=run_id,
            method=method,
            manual_order=manual_order,
            replacement=replacement,
            operator_approvals=operator_approvals,
        )

    def _commit(
        self,
        snapshot_directory,
        *,
        run_id,
        method,
        manual_order,
        replacement,
        operator_approvals,
    ):
        validate_run_id(run_id)
        snapshot = load_snapshot(snapshot_directory)
        files = {
            name: Path(snapshot_directory, name).read_text(encoding="utf-8")
            for name in ("config.json", "classes.csv", "approved_proposals.csv")
        }
        if Path(snapshot_directory, "booths.csv").exists():
            files["booths.csv"] = Path(snapshot_directory, "booths.csv").read_text(
                encoding="utf-8"
            )
        # Validate the captured bytes, closing the read-after-validation race.
        if snapshot_from_files(files) != snapshot:
            raise ValidationError("Snapshot changed while importing")
        if operator_approvals is not None:
            validate_operator_approvals(
                operator_approvals, snapshot.config.approval_ids, allow_empty=False
            )
        ids = [c.class_id for c in snapshot.classes]
        if method not in ("automatic", "manual") or (
            method == "automatic" and manual_order is not None
        ):
            raise ValidationError(
                "Choose automatic or manual drawing; automatic accepts no order"
            )
        order = manual_priority(ids, manual_order or ()) if method == "manual" else None
        event_key = (
            "original:" + snapshot.config.event_id
            if replacement is None
            else "replacement:" + replacement.authorization.authorization_id
        )
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                existing = db.execute(
                    "SELECT * FROM runs WHERE run_id=? OR event_key=?",
                    (run_id, event_key),
                ).fetchall()
                if existing:
                    if (
                        len(existing) != 1
                        or existing[0]["input_hash"] != snapshot.input_hash
                        or existing[0]["event_id"] != snapshot.config.event_id
                    ):
                        raise RunConflict(
                            "Event or run already has a different frozen snapshot"
                        )
                    saved = json.loads(existing[0]["plan"])
                    if (
                        operator_approvals is not None
                        and tuple(saved["operator_approvals"]) != operator_approvals
                    ):
                        raise RunConflict("Existing operator signoffs are locked")
                    if saved["replacement"] != json.loads(
                        canonical_json(asdict(replacement) if replacement else None)
                    ):
                        raise RunConflict(
                            "Existing replacement authorization is locked"
                        )
                    if saved["method"] != method or (
                        method == "manual" and saved["priority_order"] != list(order)
                    ):
                        raise RunConflict("Existing draw method/order is locked")
                    actual_id = existing[0]["run_id"]
                else:
                    if not feasibility(snapshot).feasible:
                        raise Infeasible(
                            "No official draw: frozen snapshot is infeasible"
                        )
                    seed = new_seed() if method == "automatic" else None
                    order = automatic_priority(ids, seed) if seed else order
                    plan = {
                        "schema_version": 1,
                        "files": files,
                        "method": method,
                        "seed": seed,
                        "priority_order": order,
                        "algorithm_version": ALGORITHM_VERSION,
                        "solver_version": version("ortools"),
                        "app_version": version("lottery-system"),
                        "replacement": asdict(replacement) if replacement else None,
                        "operator_approvals": operator_approvals or (),
                    }
                    db.execute(
                        "INSERT INTO runs VALUES(?,?,?,?,NULL,?)",
                        (
                            run_id,
                            snapshot.config.event_id,
                            snapshot.input_hash,
                            canonical_json(plan).decode(),
                            event_key,
                        ),
                    )
                    self._event(db, run_id, "INTENT")
                    actual_id = run_id
                db.commit()
            except BaseException:
                db.rollback()
                raise
        return self.recover(actual_id)

    def recover(self, run_id):
        # This writer lock covers solving: competing callers cannot run divergent plans.
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                row = db.execute(
                    "SELECT * FROM runs WHERE run_id=?", (run_id,)
                ).fetchone()
                if row is None:
                    raise KeyError(run_id)
                if row["result"] is not None:
                    result = self._checked(row)
                else:
                    plan, snapshot = self._plan(row, enforce_runtime=True)
                    solution = optimize(snapshot, plan["priority_order"])
                    if solution.status != "OPTIMAL":
                        raise SolveIncomplete(
                            "Official draw requires proven optimality"
                        )
                    verify_solution(
                        snapshot,
                        solution.assignments,
                        plan["priority_order"],
                        solution.objective_vector,
                    )
                    result = CommittedRun(
                        run_id,
                        row["event_id"],
                        row["input_hash"],
                        solution.assignments,
                        tuple(plan["priority_order"]),
                        plan["method"],
                        plan["seed"],
                        solution.objective_vector,
                        datetime.now(timezone.utc).isoformat(),
                        "",
                        snapshot.config.approval_ids,
                        ALGORITHM_VERSION,
                        plan["solver_version"],
                        plan["app_version"],
                        plan["replacement"],
                        tuple(plan["operator_approvals"]),
                    )
                    raw = result.to_dict()
                    raw["output_hash"] = digest(
                        {k: v for k, v in raw.items() if k != "output_hash"}
                    )
                    result = parse_run(json.loads(canonical_json(raw)))
                    db.execute(
                        "UPDATE runs SET result=? WHERE run_id=?",
                        (canonical_json(result.to_dict()).decode(), run_id),
                    )
                    self._event(db, run_id, "COMMITTED")
                db.commit()
                return result
            except BaseException:
                db.rollback()
                raise

    def _plan(self, row, *, enforce_runtime=False):
        plan = json.loads(row["plan"])
        if (
            not isinstance(plan, dict)
            or set(plan)
            != {
                "schema_version",
                "files",
                "method",
                "seed",
                "priority_order",
                "algorithm_version",
                "solver_version",
                "app_version",
                "replacement",
                "operator_approvals",
            }
            or type(plan["schema_version"]) is not int
            or plan["schema_version"] != 1
        ):
            raise ValidationError("Unsupported run intent")
        if enforce_runtime and (
            plan["algorithm_version"],
            plan["solver_version"],
            plan["app_version"],
        ) != (ALGORITHM_VERSION, version("ortools"), version("lottery-system")):
            raise ValidationError(
                "Saved runtime versions differ; recover with the original application/toolchain"
            )
        if (
            not isinstance(plan["files"], dict)
            or not isinstance(plan["operator_approvals"], list)
            or not isinstance(plan["priority_order"], list)
        ):
            raise ValidationError("Run intent has malformed collection fields")
        snapshot = snapshot_from_files(plan["files"])
        validate_operator_approvals(
            tuple(plan["operator_approvals"]), snapshot.config.approval_ids
        )
        if (
            snapshot.input_hash != row["input_hash"]
            or snapshot.config.event_id != row["event_id"]
        ):
            raise ValidationError("Run intent snapshot mismatch")
        ids = [c.class_id for c in snapshot.classes]
        if plan["method"] == "automatic":
            expected = automatic_priority(ids, plan["seed"])
        elif plan["method"] == "manual" and plan["seed"] is None:
            expected = manual_priority(ids, plan["priority_order"])
        else:
            raise ValidationError("Invalid draw method")
        if tuple(plan["priority_order"]) != expected:
            raise ValidationError("Priority order mismatch")
        return plan, snapshot

    def _checked(self, row):
        result = parse_run(json.loads(row["result"]))
        plan, snapshot = self._plan(row)
        if (
            result.run_id != row["run_id"]
            or result.input_hash != row["input_hash"]
            or result.event_id != row["event_id"]
            or result.method != plan["method"]
            or result.seed != plan["seed"]
            or result.priority_order != tuple(plan["priority_order"])
            or result.approvals != snapshot.config.approval_ids
            or result.operator_approvals != tuple(plan["operator_approvals"])
            or (result.algorithm_version, result.solver_version, result.app_version)
            != (plan["algorithm_version"], plan["solver_version"], plan["app_version"])
            or canonical_json(result.replacement and asdict(result.replacement))
            != canonical_json(plan["replacement"])
        ):
            raise ValidationError("Stored result and intent disagree")
        verify_solution(
            snapshot, result.assignments, result.priority_order, result.objective_vector
        )
        return result

    def get(self, run_id):
        with self._connect() as db:
            row = db.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()
            if row is None:
                raise KeyError(run_id)
            if row["result"] is None:
                raise PendingRun(
                    "Official draw intent exists; recover this run before viewing results"
                )
            return self._checked(row)

    def snapshot_files(self, run_id):
        self.get(run_id)
        with self._connect() as db:
            row = db.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()
            plan, _ = self._plan(row)
            return {
                name: value.encode("utf-8") for name, value in plan["files"].items()
            }

    def list_runs(self):
        with self._connect() as db:
            return [
                dict(row)
                for row in db.execute(
                    "SELECT run_id,event_id,input_hash,CASE WHEN result IS NULL THEN 'PENDING' ELSE 'COMMITTED' END AS status FROM runs ORDER BY rowid"
                )
            ]

    def history(self, event_id):
        with self._connect() as db:
            return [
                dict(row)
                for row in db.execute(
                    "SELECT run_id,event_id,input_hash,result IS NOT NULL AS committed FROM runs WHERE event_id=?",
                    (event_id,),
                )
            ]
