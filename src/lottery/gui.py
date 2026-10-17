"""Offline Tk interface. Worker threads never touch Tk widgets."""

import argparse
import csv
import io
from pathlib import Path
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from .desktop import DesktopSession, State, default_database
from .runs import RunStore


class LotteryApp:
    def __init__(self, root, database=None):
        self.root = root
        root.title("PTA Carnival Booth Lottery")
        root.geometry("1060x760")
        root.minsize(850, 650)
        self.session = DesktopSession(RunStore(database or default_database()))
        self.jobs = queue.Queue()
        self.busy = False
        self.status = tk.StringVar(
            value="Import a snapshot, or open the run archive to resume an existing draw."
        )
        self.controls = []
        ttk.Label(
            root, text="Carnival booth lottery", font=("TkDefaultFont", 20, "bold")
        ).pack(anchor="w", padx=24, pady=(20, 4))
        ttk.Label(
            root, text="Offline • Private contacts stay outside this application"
        ).pack(anchor="w", padx=24)
        bar = ttk.Frame(root)
        bar.pack(fill="x", padx=24, pady=12)
        self.button(bar, "Choose run database…", self.choose_database).pack(side="left")
        self.button(bar, "Refresh run archive", self.refresh_history).pack(
            side="left", padx=8
        )
        self.tabs = ttk.Notebook(root)
        self.tabs.pack(fill="both", expand=True, padx=24)
        self.pages = []
        for title in (
            "1  Import / Validate",
            "2  Configuration & Feasibility",
            "3  Official Draw",
            "4  Committed Results & Export",
        ):
            page = ttk.Frame(self.tabs, padding=18)
            self.tabs.add(page, text=title)
            self.pages.append(page)
        self.build_import()
        self.build_config()
        self.build_draw()
        self.build_results()
        ttk.Label(root, textvariable=self.status, wraplength=1000).pack(
            fill="x", padx=24, pady=14
        )
        self.refresh_history()
        root.after(100, self.poll)
        root.protocol("WM_DELETE_WINDOW", self.close)

    def close(self):
        if self.busy:
            messagebox.showinfo(
                "Please wait",
                "A task is still running. Wait for it to finish before closing.",
                parent=self.root,
            )
        else:
            self.root.destroy()

    def button(self, parent, text, command):
        button = ttk.Button(parent, text=text, command=lambda: self.action(command))
        self.controls.append(button)
        return button

    def action(self, command):
        if self.busy:
            return
        try:
            command()
        except Exception as exc:
            self.status.set(
                "Action stopped. Correct the input or open the archive to recover a pending run."
            )
            messagebox.showerror("Action required", str(exc), parent=self.root)

    def entry(self, parent, label, value=""):
        ttk.Label(parent, text=label).pack(anchor="w", pady=(10, 3))
        variable = tk.StringVar(value=value)
        field = ttk.Entry(parent, textvariable=variable)
        field.pack(fill="x")
        self.controls.append(field)
        return variable

    def build_import(self):
        page = self.pages[0]
        ttk.Label(
            page,
            text="A verified snapshot, ready for review",
            font=("TkDefaultFont", 14, "bold"),
        ).pack(anchor="w")
        ttk.Label(
            page,
            text="Choose the folder containing classes.csv, approved_proposals.csv and config.json.\nOptional booths.csv supplies readable booth names. Hashes and all proposal rules are checked.",
            wraplength=900,
        ).pack(anchor="w", pady=12)
        self.button(page, "Import snapshot folder…", self.import_folder).pack(
            anchor="w"
        )
        self.import_info = tk.StringVar(value="No snapshot imported.")
        ttk.Label(page, textvariable=self.import_info, wraplength=900).pack(
            anchor="w", pady=20
        )

    def build_config(self):
        page = self.pages[1]
        ttk.Label(
            page,
            text="Nonofficial feasibility check — no assignments or random priority",
            font=("TkDefaultFont", 12, "bold"),
            wraplength=900,
        ).pack(anchor="w")
        self.count = self.entry(page, "Number of classes", "22")
        self.games = self.entry(page, "Game booths", "9")
        self.food = self.entry(page, "Food booths", "13")
        self.button(
            page, "Apply configuration to a new local snapshot copy", self.configure
        ).pack(anchor="w", pady=12)
        self.button(
            page,
            "Check feasibility (nonofficial)",
            lambda: self.work(self.session.check_feasibility, self.feasible),
        ).pack(anchor="w")
        self.feasibility_info = tk.StringVar(
            value="Import a snapshot first. Configuration changes require a fresh check and approvals."
        )
        ttk.Label(page, textvariable=self.feasibility_info, wraplength=900).pack(
            anchor="w", pady=18
        )

    def build_draw(self):
        page = self.pages[2]
        ttk.Label(
            page,
            text="Freeze, approve, then commit once",
            font=("TkDefaultFont", 14, "bold"),
        ).pack(anchor="w")
        ttk.Label(
            page,
            text="Two distinct snapshot administrator IDs must approve separately. The second approval locks the method.\nManual drawing requires every class ID exactly once; one administrator may enter and verify it.",
            wraplength=900,
        ).pack(anchor="w", pady=8)
        self.method = tk.StringVar(value="automatic")
        self.method_controls = []
        for method in ("automatic", "manual"):
            widget = ttk.Radiobutton(
                page, text=method.title(), value=method, variable=self.method
            )
            widget.pack(anchor="w")
            self.controls.append(widget)
            self.method_controls.append(widget)
        ttk.Label(page, text="Manual class order (one ID per line)").pack(anchor="w")
        self.order = tk.Text(page, height=4, width=40)
        self.order.pack(fill="x")
        self.controls.append(self.order)
        self.method_controls.append(self.order)
        method_button = self.button(
            page, "Set drawing method / verify manual order", self.set_method
        )
        method_button.pack(anchor="w", pady=6)
        self.method_controls.append(method_button)
        self.admin = self.entry(page, "Approving administrator ID")
        self.button(page, "Record this administrator’s approval", self.approve).pack(
            anchor="w", pady=6
        )
        self.run_id = self.entry(page, "Official run ID")
        self.button(page, "Commit official draw…", self.draw).pack(anchor="w", pady=10)

    def build_results(self):
        page = self.pages[3]
        ttk.Label(
            page,
            text="Run archive — open committed results or explicitly recover a pending intent",
        ).pack(anchor="w")
        self.archive = ttk.Treeview(page, columns=("event", "status"), height=4)
        self.archive.heading("#0", text="Run ID")
        self.archive.heading("event", text="Event")
        self.archive.heading("status", text="Status")
        self.archive.pack(fill="x", pady=6)
        row = ttk.Frame(page)
        row.pack(fill="x")
        self.button(row, "Open selected committed run", self.open_selected).pack(
            side="left"
        )
        self.button(
            row,
            "Recover selected pending run (saved seed/order)",
            self.recover_selected,
        ).pack(side="left", padx=8)
        self.result_label = tk.StringVar(
            value="No committed result open. Previews never reroll."
        )
        ttk.Label(
            page,
            textvariable=self.result_label,
            font=("TkDefaultFont", 11, "bold"),
            wraplength=900,
        ).pack(anchor="w", pady=14)
        table = ttk.Frame(page)
        table.pack(fill="both", expand=True)
        self.results = ttk.Treeview(
            table, columns=("booth", "category", "rank"), height=9
        )
        self.results.heading("#0", text="Class")
        for column, title in (
            ("booth", "Assigned booth"),
            ("category", "Category"),
            ("rank", "Rank"),
        ):
            self.results.heading(column, text=title)
        scroll = ttk.Scrollbar(table, orient="vertical", command=self.results.yview)
        self.results.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self.results.pack(side="left", fill="both", expand=True)
        self.button(page, "Export committed result folder…", self.export).pack(
            anchor="w", pady=10
        )

    def import_folder(self):
        folder = filedialog.askdirectory(
            parent=self.root, title="Choose snapshot folder"
        )
        if not folder:
            return
        snapshot = self.session.import_snapshot(folder)
        for widget in self.controls:
            widget.configure(state="normal")
        self.method.set("automatic")
        self.order.delete("1.0", "end")
        self.count.set(str(snapshot.config.class_count))
        self.games.set(str(snapshot.config.game_target))
        self.food.set(str(snapshot.config.food_target))
        self.import_info.set(
            f"VALIDATED · Event {snapshot.config.event_id}\n{len(snapshot.classes)} classes · SHA-256 {snapshot.input_hash}\nRecorded approval IDs: {', '.join(snapshot.config.approval_ids)}"
        )
        self.results.delete(*self.results.get_children())
        self.result_label.set("No committed result open.")
        self.status.set(
            "Snapshot validated. Continue to configuration and nonofficial feasibility."
        )
        self.tabs.select(1)

    def configure(self):
        self.session.configure(
            int(self.count.get()), int(self.games.get()), int(self.food.get())
        )
        self.feasibility_info.set(
            "Configuration saved to a new local snapshot. Run feasibility again; approvals cleared."
        )

    def feasible(self, report):
        self.feasibility_info.set(
            "FEASIBLE — full assignment possible. No official assignments generated."
            if report.feasible
            else "INFEASIBLE — stop. Invite all potentially helpful classes to revise privately: "
            + ", ".join(report.correction_candidates)
        )
        self.status.set(self.feasibility_info.get())

    def set_method(self):
        self.session.set_method(
            self.method.get(),
            self.order.get("1.0", "end").split()
            if self.method.get() == "manual"
            else None,
        )
        self.status.set(
            "Drawing method verified. Obtain two separate administrator approvals."
        )

    def ensure_settings_applied(self):
        snapshot = self.session.snapshot
        if snapshot is None:
            raise ValueError("Import a snapshot first.")
        counts = (int(self.count.get()), int(self.games.get()), int(self.food.get()))
        expected = (
            snapshot.config.class_count,
            snapshot.config.game_target,
            snapshot.config.food_target,
        )
        order = (
            tuple(self.order.get("1.0", "end").split())
            if self.method.get() == "manual"
            else None
        )
        if (
            counts != expected
            or self.method.get() != self.session.method
            or order != self.session.manual_order
        ):
            raise ValueError(
                "Visible settings differ from the reviewed snapshot. Apply configuration and check feasibility, or set the drawing method again before obtaining fresh approvals. Frozen settings require importing a new snapshot."
            )

    def lock_frozen_settings(self):
        if self.session.state in (
            State.APPROVED_FROZEN,
            State.COMMITTING,
            State.COMMITTED,
            State.EXPORTED,
        ):
            for widget in self.controls:
                if widget.master == self.pages[1] or widget in self.method_controls:
                    widget.configure(state="disabled")

    def approve(self):
        self.ensure_settings_applied()
        self.session.approve(self.admin.get().strip())
        self.admin.set("")
        self.status.set(
            f"{len(self.session.approvals)} of 2 approvals recorded · {self.session.state}"
        )
        self.lock_frozen_settings()

    def draw(self):
        self.ensure_settings_applied()
        if not messagebox.askyesno(
            "Commit the official draw?",
            "This draw is permanent. Rerolls are not allowed. Results appear only after durable commit. Continue?",
            parent=self.root,
        ):
            return
        run_id = self.run_id.get().strip()
        self.work(lambda: self.session.commit(run_id), self.show_result)

    def work(self, command, callback):
        if self.busy:
            return
        self.busy = True
        for widget in self.controls:
            widget.configure(state="disabled")
        self.status.set(
            "Working… Please wait. Do not close the application during an official commit."
        )

        def run():
            try:
                self.jobs.put((callback, command(), None))
            except Exception as exc:
                self.jobs.put((callback, None, exc))

        threading.Thread(target=run, daemon=True).start()

    def poll(self):
        try:
            callback, result, error = self.jobs.get_nowait()
        except queue.Empty:
            pass
        else:
            self.busy = False
            for widget in self.controls:
                widget.configure(state="normal")
            if error:
                self.status.set(
                    "Operation stopped. Refresh the archive; recover an existing pending run rather than starting another draw."
                )
                messagebox.showerror("Action required", str(error), parent=self.root)
            else:
                self.action(lambda: callback(result))
            self.action(self.refresh_history)
            self.lock_frozen_settings()
        self.root.after(100, self.poll)

    def choose_database(self):
        path = filedialog.askopenfilename(
            parent=self.root,
            title="Open existing run database",
            filetypes=[("SQLite database", "*.sqlite3 *.db"), ("All files", "*")],
        )
        if path:
            self.session = DesktopSession(RunStore(path))
            self.results.delete(*self.results.get_children())
            self.result_label.set("Database opened. Select a run below.")
            self.refresh_history()
            self.tabs.select(3)

    def refresh_history(self):
        self.archive.delete(*self.archive.get_children())
        for run in self.session.history():
            self.archive.insert(
                "",
                "end",
                iid=run["run_id"],
                text=run["run_id"],
                values=(
                    run["event_id"],
                    "COMMITTED"
                    if run.get("committed", run.get("status") == "COMMITTED")
                    else "PENDING — recover",
                ),
            )

    def selected(self):
        selection = self.archive.selection()
        if not selection:
            raise ValueError("Select a run from the archive first.")
        return selection[0]

    def open_selected(self):
        self.show_result(self.session.open_run(self.selected()))

    def recover_selected(self):
        run_id = self.selected()
        self.work(lambda: self.session.recover(run_id), self.show_result)

    def show_result(self, run):
        self.results.delete(*self.results.get_children())
        files = self.session.store.snapshot_files(run.run_id)
        names = {}
        if "booths.csv" in files:
            names = {
                row["booth_id"]: row["canonical_name"]
                for row in csv.DictReader(
                    io.StringIO(files["booths.csv"].decode("utf-8"))
                )
            }
        classes = {
            row["class_id"]: row["display_name"]
            for row in csv.DictReader(io.StringIO(files["classes.csv"].decode("utf-8")))
        }
        for assignment in run.assignments:
            self.results.insert(
                "",
                "end",
                text=classes.get(assignment.class_id, assignment.class_id),
                values=(
                    names.get(assignment.booth_id, assignment.booth_id),
                    assignment.category.value,
                    assignment.assigned_rank,
                ),
            )
        self.result_label.set(f"OFFICIAL — COMMITTED · {run.run_id} · {run.event_id}")
        self.status.set(
            f"Immutable result saved {run.committed_at}. Exporting or reopening preserves this exact draw."
        )
        self.tabs.select(3)

    def export(self):
        if self.session.result is None:
            raise ValueError("Open a committed run before exporting.")
        destination = filedialog.askdirectory(
            parent=self.root, title="Choose export parent folder"
        )
        if destination:
            output = self.session.export(Path(destination) / self.session.result.run_id)
            self.status.set(f"Export verified and saved: {output}")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Offline PTA carnival lottery")
    parser.add_argument("--database", type=Path)
    options = parser.parse_args(argv)
    root = tk.Tk()
    LotteryApp(root, options.database)
    root.mainloop()


if __name__ == "__main__":
    main()


def smoke_test():
    """Construct actual Tk screens without needing a production database."""
    import tempfile

    with tempfile.TemporaryDirectory() as folder:
        root = tk.Tk()
        root.withdraw()
        try:
            app = LotteryApp(root, Path(folder) / "smoke.sqlite3")
            root.update_idletasks()
            root.update()
            assert len(app.tabs.tabs()) == 4
        finally:
            root.destroy()
