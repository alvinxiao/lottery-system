# Windows standalone distribution

Build on Windows using Python 3.12 and the locked development environment:

```powershell
uv sync --frozen --python 3.12
uv run --frozen python scripts/build_desktop.py
uv run --frozen python scripts/packaged_smoke.py dist/PTACarnivalLottery/PTACarnivalLottery.exe sample-data/ready-to-draw --gui
```

The build creates a one-folder application, a ZIP named for the native OS and architecture, and a `.zip.sha256` checksum. The ZIP includes `sample-data/` and the desktop guide for manual rehearsals. Distribute the entire ZIP. After extraction, keep the `.exe` and `_internal` folder together. Run `PTACarnivalLottery.exe` to open the desktop app. The app stores its local database under `%LOCALAPPDATA%\PTACarnivalLottery`; retain and back up that database to preserve committed runs. Source builds use `uv run lottery-gui`. For rehearsal, run `PTACarnivalLottery.exe --database rehearsal-runs.sqlite3` to keep sample history in a separate database.

The executable includes Python, OR-Tools, SQLite, and Tk. Operators do not install Python, supply Google credentials, or connect to the Internet for draws. PyInstaller is pinned in the lockfile. Its specification collects OR-Tools native libraries and version metadata. Windows packages must be built on Windows; Linux builds are useful developer checks and do not establish Windows compatibility.

The Windows CI job builds the ZIP, blocks outbound traffic for the executable with Windows Firewall, removes development Python from its subprocess PATH, and runs the executable from an isolated temporary working directory. The executable verifies that it is frozen, imports the 22-class sample, checks feasibility, obtains two distinct sample approvals, commits, restarts with the same database, verifies the unchanged result, and repeats byte-identical verified exports. A separate bundled Tk check creates actual screen widgets. Artifacts are uploaded for review; the job does not publish a release or sign binaries. Hosted `windows-latest` testing alone does not certify Windows 10 and Windows 11 compatibility.

## Clean-machine operator acceptance

Before live use, a PTA operator should perform this checklist on each supported Windows version, using a standard account on a machine without Python installed:

1. Download the ZIP and checksum through a trusted distribution channel. Run `Get-FileHash .\PTACarnivalLottery-Windows-AMD64.zip -Algorithm SHA256` and compare with the supplied checksum. A checksum detects corruption; it does not prove publisher identity.
2. Extract the whole ZIP. Disconnect networking and start the executable. Follow school IT policy for unsigned binaries and SmartScreen; do not bypass a warning merely to complete this test.
3. Import `sample-data/ready-to-draw`, check the 22-class/9-game/13-food configuration, and run the nonofficial feasibility check.
4. Select automatic or complete manual order, enter the two sample administrator IDs from `config.json`, and commit a sample run. Confirm the preview says `OFFICIAL — COMMITTED`.
5. Export to an empty directory. Close and reopen the app, open the same committed run, and export again. Confirm assignments and audit hashes match. Verify no redraw is offered for that event.
6. Test malformed and infeasible sample directories. Confirm errors explain the correction and no official draw is available.
7. Keep the sample database separate from live events. Record OS version, architecture, ZIP SHA-256, date, operator, startup result, draw/export result, and any warnings before approving distribution.

Sample approvals are demonstrations of the workflow, not identity authentication. Use the separate Google administration security and production-readiness checklist before handling real classes.
