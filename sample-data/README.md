# Manual rehearsal data

These fictional examples let you try the whole draw without entering your own roster. No names, email addresses, approvals, safety decisions, or proposals represent real people or real PTA decisions. Do not use this data for a live event.

`ready-to-draw/` is a valid frozen snapshot for 22 classes, with three ranked proposals per class and two synthetic administrator IDs. It has a complete unique matching with 9 carnival games and 13 Chinese food booths. Shared first choices make some classes receive lower choices. Foods include jiaozi, baozi, scallion pancakes, fried rice, chow mein, wonton soup, tangyuan, egg tarts, tea eggs, spring rolls, sesame balls, tofu pudding, and zhajiang noodles. The CSV preserves Chinese names as UTF-8.

`infeasible/` is syntactically valid but has 14 food-only classes and only 13 food slots. Expect feasibility to fail. It should never produce an official roster.

`manual-priority.txt` is a fixed practice permutation of all class IDs, one per line. It is supplied test input, not a random drawing. `google-intake.json` has fictional private contacts at the reserved `example.invalid` domain, intake submissions, and mock review decisions for a Google workflow rehearsal. Keep dry-run email enabled. None of these addresses can receive mail.

The booth approvals are synthetic. Balloon darts means soft-tip darts with adult supervision for this rehearsal. A real PTA must separately approve safety, food handling, allergens, equipment, and duplicate-equivalence decisions.

## Start a desktop rehearsal

Run commands from the repository root. Install dependencies with `uv sync --locked --dev` if needed. Create a separate output directory and use a rehearsal database, never your production database.

```sh
uv run python -m lottery.gui --database rehearsal-runs.sqlite3
```

On Windows, you can also start the packaged executable with `--database rehearsal-runs.sqlite3`.

1. Import the `sample-data/ready-to-draw` directory. Keep 22 classes, 9 games, and 13 foods.
2. Run the nonofficial feasibility check. Expect success.
3. Choose manual priority and paste the contents of `sample-data/manual-priority.txt`, or choose automatic priority. Lock the method before approval.
4. Record the two mock approvals as `DEMO-admin-alex` and `DEMO-admin-robin`.
5. Use a clearly labeled rehearsal run ID. Commit the draw and inspect the committed results. Expect 22 distinct classes and booths, 9 games, and 13 foods.
6. Export to a separate directory such as `rehearsal-exports/first-draw`. Inspect the assignment CSV, audit, feasibility report, and summary.
7. Restart, open the same database, and reopen that committed run. Results must match. Re-exporting must preserve the assignments.
8. Import `sample-data/infeasible`. Run feasibility again. Expect a quota conflict and no official draw.

The same event cannot be drawn again in one database. For a fresh practice session, use a new rehearsal database or generate data with a new event ID. Do not delete a real event's database to obtain a different outcome.

## Validate from the command line

These two commands only validate inputs and check feasibility. They never draw priority or commit results.

```sh
uv run lottery validate sample-data/ready-to-draw
uv run lottery feasibility sample-data/ready-to-draw
uv run lottery feasibility sample-data/infeasible
```

The last command should return exit status 1 with `feasible: false`.

## Regenerate or customize the event ID

The generator reproduces the checked-in bytes without randomness. It generates snapshots, fixed practice priority, and mock intake only. It never produces official assignments.

```sh
uv run python scripts/generate_sample_data.py
uv run python scripts/generate_sample_data.py --output rehearsal-input --event-id DEMO-carnival-rehearsal-02
uv run pytest tests/test_sample_data.py
```

Choose a new output directory for customized practice data. The generator refuses to overwrite edited or unknown files unless you explicitly pass `--force`. Even with `--force`, unrelated files remain untouched and symbolic links are refused. The generator never rewrites this README.

Do not hand-edit a snapshot CSV without updating its manifest. Regenerating gives each file its correct SHA-256 hash. If `uv` cannot write its default cache in a restricted cloud environment, set `UV_CACHE_DIR=/tmp/lottery-uv-cache` first.

## Google intake rehearsal

`google-intake.json` contains a `config` object for `Core.create`, 22 `classes`, matching `submissions`, and `review_decisions` keyed by class ID. Initialize the mock event with the supplied configuration and class roster, verify each fictional contact through the administrator workflow, then submit and review the records in order. The single mock exception approver and publication approver are explicit test policy only. The 48-hour grace setting is a rehearsal choice, not an adopted PTA policy.

The optimizer snapshots contain no contact details. Keep Google intake separate from public outputs. Never replace the invalid addresses with real contacts until authorized administrators have approved live access, retention, notification, and exception policies.
