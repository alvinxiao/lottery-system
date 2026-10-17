import os
import sys
import pytest


@pytest.mark.skipif(
    sys.platform != "win32" and not os.environ.get("DISPLAY"),
    reason="Actual Tk smoke requires a display; Windows CI supplies native Tk",
)
def test_real_tk_screens():
    from lottery.gui import smoke_test

    smoke_test()


@pytest.mark.skipif(
    sys.platform != "win32" and not os.environ.get("DISPLAY"),
    reason="Actual Tk regression requires a display",
)
def test_visible_settings_must_match_reviewed_snapshot(tmp_path):
    import tkinter as tk
    from lottery.gui import LotteryApp
    from helpers import sample, write_snapshot

    root = tk.Tk()
    root.withdraw()
    try:
        app = LotteryApp(root, tmp_path / "gui.sqlite3")
        directory = write_snapshot(
            tmp_path / "source",
            sample([[("a", "game"), ("b", "game"), ("c", "game")]], 1),
        )
        app.session.import_snapshot(directory)
        app.count.set("1")
        app.games.set("1")
        app.food.set("0")
        app.ensure_settings_applied()
        app.games.set("0")
        with pytest.raises(ValueError, match="Visible settings differ"):
            app.ensure_settings_applied()
        app.games.set("1")
        app.method.set("manual")
        app.order.insert("1.0", "c0")
        with pytest.raises(ValueError, match="Visible settings differ"):
            app.ensure_settings_applied()
        app.set_method()
        app.session.check_feasibility()
        app.admin.set("admin-a")
        app.approve()
        app.admin.set("admin-b")
        app.approve()
        assert str(app.order.cget("state")) == "disabled"
        assert all(
            str(widget.cget("state")) == "disabled" for widget in app.method_controls
        )
    finally:
        root.destroy()


@pytest.mark.skipif(
    sys.platform != "win32" and not os.environ.get("DISPLAY"),
    reason="Actual Tk workflow requires a display",
)
def test_full_sample_through_visible_callbacks(tmp_path, monkeypatch):
    import csv
    from pathlib import Path
    import time
    import tkinter as tk
    from lottery.desktop import State
    from lottery.gui import LotteryApp

    sample = Path(__file__).resolve().parents[1] / "sample-data/ready-to-draw"
    root = tk.Tk()
    root.withdraw()
    errors = []
    monkeypatch.setattr("lottery.gui.filedialog.askdirectory", lambda **kw: str(sample))
    monkeypatch.setattr("lottery.gui.messagebox.askyesno", lambda *a, **kw: True)
    monkeypatch.setattr("lottery.gui.messagebox.showerror", lambda *a, **kw: errors.append(a))
    try:
        app = LotteryApp(root, tmp_path / "gui-full.sqlite3")
        app.import_folder()
        app.work(app.session.check_feasibility, app.feasible)

        def finish():
            deadline = time.monotonic() + 20
            while app.busy and time.monotonic() < deadline:
                root.update()
                time.sleep(0.01)
            assert not app.busy
            assert not errors

        finish()
        assert app.session.state == State.FEASIBLE
        app.set_method()
        for actor in app.session.snapshot.config.approval_ids[:2]:
            app.admin.set(actor)
            app.approve()
        app.run_id.set("gui-synthetic-draw")
        app.draw()
        finish()
        assert app.session.state == State.COMMITTED
        assert "OFFICIAL — COMMITTED" in app.result_label.get()
        assert len(app.results.get_children()) == 22
        with (sample / "booths.csv").open(encoding="utf-8", newline="") as file:
            names = {row["booth_id"]: row["canonical_name"] for row in csv.DictReader(file)}
        rows = [app.results.item(item, "values") for item in app.results.get_children()]
        assert {row[0] for row in rows} == {names[a.booth_id] for a in app.session.result.assignments}
        assert any("饺子" in row[0] for row in rows)
        assert len(app.session.result.operator_approvals) == 2
    finally:
        root.destroy()
