# Desktop operator guide

Run `lottery-gui` from the installed source environment or open the packaged Windows application. No Google credentials, network connection, or private parent contacts are needed. See [Windows packaging](windows-packaging.md) for building and testing the executable.

The application stores durable official draws in `PTACarnivalLottery/runs.sqlite3` under Windows Local AppData, or `~/.local/share` elsewhere. Preserve this database and your exported audit folders. Use **Choose run database** to open an existing database after moving computers or restarting. The run archive works before importing any snapshot.

## Rehearse with generated data

Use the scenario folders under `sample-data`, generated with `python scripts/generate_sample_data.py`. Each snapshot folder contains its CSV files and `config.json`. These are synthetic school classes, carnival games, and Chinese food booths. Use a separate database for rehearsals. Each event permits one official draw, so reopening and exporting a rehearsal repeats the saved result rather than generating a new lottery.

## Import and check

1. Choose **Import snapshot folder** on the first tab. Validation checks the schema, manifest hashes, three distinct ranked proposals per class, category consistency, quotas, and recorded approval IDs. The application makes a local copy; the source folder stays unchanged.
2. Review class count and game/food quotas on the second tab. For a future year, first import its new class roster and proposals. Apply configuration to create another local snapshot copy. The class count must match the imported roster and the two quotas must sum to that count.
3. Run **Check feasibility (nonofficial)**. This creates neither assignments nor random class priority. An infeasible input stops the workflow. Invite all listed potentially helpful classes to revise privately; do not identify any class as responsible. Import the corrected approved snapshot and repeat the check.

Changing configuration clears feasibility and approvals. Changing method clears approvals. Changed or corrupted input detected during signoff or commit requires reimport and review. You cannot edit an approved frozen input.

## Approve and draw

1. Choose automatic randomness or enter a physical manual draw, one class ID per line. Select **Set drawing method / verify manual order**. Manual order must contain every class ID exactly once; one administrator may enter and verify it.
2. Have two distinct administrators separately enter their IDs and select **Record this administrator’s approval**. Their IDs must appear in the imported snapshot approval list. The second signoff freezes the input and method.
3. Enter a stable run ID and select **Commit official draw**. Read the no-reroll warning and confirm. Controls stay disabled while solving and committing.
4. Results appear only when the durable store returns a committed record, labeled **OFFICIAL — COMMITTED**. The table shows class, readable booth name when supplied, category, and assigned rank.

The desktop records operator-entered administrator IDs; it does not authenticate those people. Operate it under the PTA's access and in-person review procedures. Protect the machine and database from unauthorized access.

## Recover and export

If interrupted, reopen the same database and refresh the archive. Open a committed record directly. If an intent is pending, select **Recover selected pending run**. Recovery uses its original saved snapshot, seed, and class order. Do not delete the database or start a new event to obtain a preferred result.

Select **Export committed result folder** to write the assignments, audit, feasibility report, summary, and frozen snapshot. Choose the export parent folder; the application creates a child folder named for the run. Repeated export preserves the same assignments. Existing conflicting export content is rejected rather than overwritten.

Declines, withdrawals, and changed assignments belong in the PTA exception workflow; they are not rerolls. A separately authorized corrective run must preserve the original audit. This application does not invent an exception approval policy.

## Accessibility and verification

All actions have visible text labels and use native Tk controls with keyboard focus. Move among controls with Tab, activate focused buttons with Space, and select tabs with the native keyboard controls. Resize the window for a larger results table. Errors stop the action and explain the correction or recovery step.

Run `DISPLAY=:99 .venv/bin/python -m pytest tests/test_desktop.py tests/test_gui.py` on a Linux display server, or run the same tests with the installed Python on Windows. The Tk smoke test constructs the actual four screens; it skips Linux hosts without a display. Controller tests cover approvals, invalidation, durable restart, pending recovery, and repeat exports.

The audit retains the source snapshot's full approval list and separately records the two actual desktop operator signoffs. If the snapshot lists three administrators and the first and third approve in the application, the operator signoff record includes only those two IDs. These remain operator-entered assertions, not authenticated identities.
