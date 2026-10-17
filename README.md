# PTA carnival booth lottery

An offline desktop lottery and a Google Forms, Sheets, and Apps Script administration workflow implement [the specification](docs/spec.md). The desktop validates approved proposals, checks exact category feasibility, commits one auditable official draw, recovers interrupted runs, and exports verified results. Google administration handles intake, reviews, corrections, private notifications, confirmations, exceptions, and sanitized publication.

## Try the desktop with sample data

Install Python 3.12 or newer and [uv](https://docs.astral.sh/uv/). From the checkout, run:

```sh
uv sync --frozen
uv run --frozen lottery-gui --database rehearsal-runs.sqlite3
```

Import `sample-data/ready-to-draw`. It contains 22 fictional classes, nine carnival games, and thirteen Chinese food booths. Follow [the manual rehearsal](sample-data/README.md) to check feasibility, record the two mock approvals, commit, export, and reopen the same result. `sample-data/infeasible` demonstrates a quota conflict. [The generator](scripts/generate_sample_data.py) reproduces both datasets and supports new rehearsal event IDs.

Windows operators can use the standalone executable without Python or Internet access. See [Windows distribution](docs/windows-packaging.md) for CI artifacts, building, and clean-machine acceptance. Keep the executable beside its bundled `_internal` directory after extracting the ZIP.

[The desktop guide](docs/desktop-guide.md) explains configuration, signoffs, permanent draws, recovery, and exports. The application stores durable run history in a local SQLite database. Preserve that database and the exported audit folders. Reopening, double-clicking, or exporting never creates another draw for the event.

## Prepare the Google workflow

Use [the Google setup guide](google/README.md) to configure designated administrators, authoritative contacts, event deadlines, and PTA policy, then deploy the Apps Script sources. Dry-run email is the default. Google account authorization, Drive sharing, and live delivery are operator actions. No real accounts or recipients are used by the local tests.

The Google workflow exports canonical approved snapshots for the offline desktop and imports its verified committed bundles. Parent contacts and original preferences stay in the private workbook and state file. Public sheets and PDFs contain only the finalized class, booth, and category.

## Run the checks

```sh
uv run --frozen python scripts/check.py
uv run --frozen python scripts/rehearse.py --output rehearsal-output
cd google
npm test
npm run build
```

The Python suite compares the optimizer against exhaustive enumeration, checks the 22-class quotas, exercises crash recovery and concurrent retries, verifies exports and authorized replacements, and drives the desktop controller. Display-backed Tk tests run on Windows and on Linux with a display server. Google tests exercise the business rules and service adapters with synthetic identities and delivery receipts.

The rehearsal script takes fictional Google intake through review, snapshot export, an actual committed desktop draw, verified Google import, explicit and automatic acceptance, a consented exception, and approved sanitized roster output. It writes reviewable files under the selected directory and makes no Google or email calls. Repeating it reuses the same committed draw.

The command-line input checks remain nonofficial:

```sh
uv run --frozen lottery validate sample-data/ready-to-draw
uv run --frozen lottery feasibility sample-data/ready-to-draw
```

Use the existing isolated checkout for cloud tasks. If the default cache is not writable, set `UV_CACHE_DIR` to `/tmp/lottery-uv-cache`. Do not create a worktree for ordinary cloud tasks.

## Data and trust boundaries

Snapshots use versioned canonical UTF-8 CSV, a SHA-256 manifest, and compact sorted JSON with a final LF. The input hash binds the config bytes and all CSV hashes. The result audit records frozen input, approvals, randomization, versions, objectives, timestamps, and its output hash. Export bundles include the original snapshot and can be independently checked with `lottery.exports.verify_export`.

Hashes detect corruption and disagreement. They do not authenticate the operator or prevent a machine administrator from replacing the entire database. Desktop approval IDs are recorded assertions. Google administrative operations and parent confirmations enforce identity at their service boundaries.

[Policy decisions](DECISIONS.md) distinguish implemented rules from event-specific authority that PTA must configure. Exception and publication authority, identity verification, retention, deadlines, and Windows support approval are not invented by the application. Live rollout requires those decisions and an operator rehearsal. [Architecture decisions](docs/adr) record persistence and solver design.
