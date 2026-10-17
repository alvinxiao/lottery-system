"""Headless desktop workflow: only durable committed records can become previews."""

from enum import StrEnum
import json
import os
from pathlib import Path
import tempfile

from .domain import ValidationError
from .priority import manual_priority
from .snapshot import canonical_json, load_snapshot
from .solver import feasibility


class State(StrEnum):
    DRAFT_IMPORT = "DRAFT_IMPORT"
    VALIDATED = "VALIDATED"
    FEASIBLE = "FEASIBLE"
    APPROVED_FROZEN = "APPROVED_FROZEN"
    COMMITTING = "COMMITTING"
    COMMITTED = "COMMITTED"
    EXPORTED = "EXPORTED"


def default_database():
    base = (
        Path(os.environ["LOCALAPPDATA"])
        if os.environ.get("LOCALAPPDATA")
        else Path.home() / ".local" / "share"
    )
    return base / "PTACarnivalLottery" / "runs.sqlite3"


class DesktopSession:
    def __init__(self, store, workspace=None):
        self.store = store
        self.workspace = (
            Path(workspace)
            if workspace
            else Path(tempfile.mkdtemp(prefix="lottery-desktop-"))
        )
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.state = State.DRAFT_IMPORT
        self.snapshot = None
        self.directory = None
        self.result = None
        self.approvals = []
        self.method = "automatic"
        self.manual_order = None
        self.report = None

    def _editable(self):
        if self.state in (
            State.APPROVED_FROZEN,
            State.COMMITTING,
            State.COMMITTED,
            State.EXPORTED,
        ):
            raise ValidationError(
                "Frozen input cannot change. Import a new snapshot to start a separate review."
            )

    def _copy(self, source, config=None):
        target = Path(tempfile.mkdtemp(prefix="snapshot-", dir=self.workspace))
        for name in (
            "classes.csv",
            "approved_proposals.csv",
            "config.json",
            "booths.csv",
        ):
            path = Path(source) / name
            if path.exists():
                (target / name).write_bytes(path.read_bytes())
        if config is not None:
            (target / "config.json").write_bytes(canonical_json(config))
        snapshot = load_snapshot(target)
        self.directory, self.snapshot = target, snapshot
        self.approvals = []
        self.result = self.report = None
        self.state = State.VALIDATED
        return snapshot

    def import_snapshot(self, path):
        if self.state == State.COMMITTING:
            raise ValidationError("Wait for the durable draw to finish.")
        load_snapshot(path)
        self.method, self.manual_order = "automatic", None
        return self._copy(path)

    def configure(self, class_count, game_target, food_target):
        self._editable()
        if self.snapshot is None:
            raise ValidationError("Import a snapshot first.")
        config = json.loads(
            (self.directory / "config.json").read_text(encoding="utf-8")
        )
        config.update(
            class_count=class_count, game_target=game_target, food_target=food_target
        )
        return self._copy(self.directory, config)

    def check_feasibility(self):
        self._editable()
        if self.snapshot is None:
            raise ValidationError("Import and validate a snapshot first.")
        self._unchanged()
        self.report = feasibility(self.snapshot)
        self.state = State.FEASIBLE if self.report.feasible else State.VALIDATED
        self.approvals = []
        return self.report

    def set_method(self, method, manual_order=None):
        self._editable()
        if self.snapshot is None:
            raise ValidationError("Import a snapshot first.")
        if method not in ("automatic", "manual"):
            raise ValidationError("Choose automatic or manual drawing.")
        order = (
            manual_priority(
                [c.class_id for c in self.snapshot.classes], manual_order or ()
            )
            if method == "manual"
            else None
        )
        self.method, self.manual_order = method, order
        self.approvals = []

    def _unchanged(self):
        try:
            unchanged = load_snapshot(self.directory) == self.snapshot
        except ValidationError:
            unchanged = False
        if not unchanged:
            self.state = State.DRAFT_IMPORT
            self.approvals = []
            self.result = None
            raise ValidationError(
                "Input changed. Import it again, check feasibility, and obtain fresh approvals."
            )

    def approve(self, admin_id):
        if self.state != State.FEASIBLE:
            raise ValidationError(
                "Establish feasibility before obtaining two separate approvals."
            )
        self._unchanged()
        expected = self.snapshot.config.approval_ids
        if admin_id not in expected or admin_id in self.approvals:
            raise ValidationError(
                "Use a distinct administrator ID recorded in the snapshot approval list."
            )
        self.approvals.append(admin_id)
        if len(self.approvals) == 2:
            self.state = State.APPROVED_FROZEN

    def commit(self, run_id):
        if self.state != State.APPROVED_FROZEN:
            raise ValidationError(
                "Two separate approvals are required before the official draw."
            )
        self._unchanged()
        self.state = State.COMMITTING
        try:
            result = self.store.commit(
                self.directory,
                run_id=run_id,
                method=self.method,
                manual_order=self.manual_order,
                operator_approvals=tuple(self.approvals),
            )
        except Exception:
            # Retry is safe only after proving no intent exists for this event.
            try:
                records = self.store.history(self.snapshot.config.event_id)
            except Exception:
                records = None
            if records == []:
                self.state = State.APPROVED_FROZEN
            raise
        self.result = result
        self.state = State.COMMITTED
        return result

    def open_run(self, run_id):
        if self.state == State.COMMITTING:
            raise ValidationError("Use explicit recovery for a pending draw.")
        result = self.store.get(run_id)
        self.result = result
        self.state = State.COMMITTED
        return result

    def recover(self, run_id):
        self.state = State.COMMITTING
        self.result = None
        result = self.store.recover(run_id)
        self.result, self.state = result, State.COMMITTED
        return result

    def history(self, event_id=None):
        return self.store.history(event_id) if event_id else self.store.list_runs()

    def export(self, destination):
        if self.state not in (State.COMMITTED, State.EXPORTED) or self.result is None:
            raise ValidationError("Open a committed result before exporting.")
        from .exports import export_run

        output = export_run(self.store, self.result.run_id, destination)
        self.state = State.EXPORTED
        return output
