# PTA booth lottery

This repository implements the specification's Milestones 0 and 1. Administrators can validate frozen snapshot files and run a nonofficial feasibility check. The Python API can optimize synthetic or approved snapshots for development. It cannot perform an official draw.

## Development

Install Python 3.12 or newer and [uv](https://docs.astral.sh/uv/). From this checkout, run:

```sh
uv sync --frozen
uv run --frozen python scripts/check.py
uv run --frozen lottery --help
uv run --frozen lottery validate tests/fixtures/valid-small
uv run --frozen lottery feasibility tests/fixtures/valid-small
```

On restricted cloud machines, set `UV_CACHE_DIR` to a writable directory such as `/tmp/lottery-uv-cache`. Use the existing isolated checkout. Do not create a worktree for ordinary cloud tasks.

The check script runs the real pytest suite, including an exhaustive independent allocation oracle over generated small inputs, input validation, objective verification, subprocess CLI checks, and a 22-class allocation. CI runs the same command on Linux and Windows. Windows CI does not validate standalone packaging.

## Snapshot version 1

Use a directory containing `classes.csv`, `approved_proposals.csv`, and `config.json`. Headers follow [the specification](docs/spec.md). Categories are the lowercase strings `game` and `food`. Exactly three approved distinct choices per class are required. This format does not contain contact information or proposal approval flags. Exporters must supply only PTA-approved choices.

CSV is UTF-8 without BOM, with LF line endings, a final newline, exact header order, and Python CSV minimal quoting. Row order is preserved and may vary without affecting the optimum. JSON is UTF-8, sorted keys, compact separators, unescaped Unicode, and a final LF. See `lottery.snapshot.canonical_json`. The manifest maps each supported CSV filename to its lowercase SHA-256 hex digest. Optional `booths.csv` uses `booth_id,canonical_name,category` and must cover exactly the referenced booth IDs.

Configuration has exactly `schema_version`, `event_id`, `class_count`, `game_target`, `food_target`, `snapshot_created_at`, `approval_ids`, and `hash_manifest`. Schema version is 1. Timestamps must include a timezone. Approval IDs require two distinct entries. These are recorded assertions, not authenticated administrator identities. The snapshot hash is SHA-256 of the canonical config bytes, which bind all CSV hashes without self-reference. Hashes establish consistency, not authenticity.

The CLI returns 0 for validation or feasible inputs, 1 for proved infeasibility, and 2 for invalid inputs or an incomplete solve. Feasibility never creates priority, displays assignments, or commits a run. Infeasible diagnostics conservatively include every class as eligible for private correction outreach. They do not identify blame or a minimal repair set.

## Python API

`load_snapshot(path)` parses and validates directory inputs. Frozen dataclasses in `lottery.domain` represent the internal contract. `feasibility(snapshot)` checks full allocation without random priority. `optimize(snapshot, priority)` returns assignments and the exact objective vector only after every stage proves optimal. `verify_assignments` checks constraints independently. `verify_solution` additionally recomputes the reported objective vector, without claiming to prove global optimality.

The optimizer locks unique-first count, first-choice count, second-choice count, then each class's negated assigned rank in the supplied priority order. Unique-first considers competing proposals at all ranks. Ranks are distinct, so minimizing each class's rank uniquely determines its booth. Class and proposal input order do not alter the result. A time limit applies separately to each stage. UNKNOWN and merely FEASIBLE optimization outcomes raise `SolveIncomplete` without returning an allocation.

`automatic_priority(class_ids, seed)` is a pure replay utility. Its `sha256-counter-fisher-yates-v1` algorithm sorts class IDs, decodes a 32-byte lowercase hexadecimal seed, and applies reverse Fisher-Yates. Each candidate is SHA-256 of seed bytes followed by a 16-byte unsigned big-endian counter starting at zero. Rejection sampling discards integers outside the largest multiple of the current range below 2^256. `new_seed()` uses `secrets.token_hex(32)`. No CLI generates randomness. `manual_priority` requires an exact permutation. These utilities do not authenticate or witness a physical drawing.

## Scope and review

[DECISIONS.md](DECISIONS.md) records locked and unresolved policy. [The architecture decision](docs/adr/0001-solver-core.md) explains module ownership and alternatives. Audit persistence, committed official draws, GUI, packaging, Google integration, notification identity, and publication gates belong to later milestones. Do not use this development core for a live draw before those controls exist.
