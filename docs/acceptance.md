# Acceptance coverage and rollout

The numbered cases follow section 11 of [the specification](spec.md). Automated checks use fictional records. They do not connect to real Google accounts or send mail.

| Case | Implemented behavior | Repeatable evidence |
| --- | --- | --- |
| 1 | One authoritative class entry, duplicate flags, preserved submission versions | `google/test/workflow.test.js` intake and review cases |
| 2 | Uniform configured grace, reminders, unresolved intake blocks freezing | Google grace and late-duplicate cases |
| 3 | Exactly three approved ranks with distinct booth IDs | Python boundary tests and Google freeze cases |
| 4 | Advisory similarity, explicit canonical decisions, unique assigned booths | Google correction/review cases and Python solver oracle |
| 5 | Strict roster, rank, category, quota, approval, and checksum validation | `tests/test_boundaries.py`, `tests/test_catalog.py`, and Google import cases |
| 6 | Full matching with exact quotas; fourteen food-only classes cannot fit thirteen slots | Python solver test, Google draft maxflow test, and `sample-data/infeasible` |
| 7 | Broad private voluntary correction outreach, no random diagnostic draw | Google feasibility and correction workflow; desktop feasibility output |
| 8 | Exact staged allocation priorities, independently compared with exhaustive solutions | `tests/test_solver.py` generated oracle cases |
| 9 | Twenty-two classes, twenty-two unique booths, nine games and thirteen foods | Solver, sample, visible GUI, packaged, and cross-language rehearsal checks |
| 10 | Saved cryptographic seed replay; exact manual permutation | Priority tests and durable restart checks |
| 11 | Durable intent before solve, committed result before preview, no reroll on retries | `tests/test_runs.py`, `tests/test_desktop.py`, and `tests/test_gui.py` |
| 12 | Strict bundle verification and idempotent import | `tests/test_exports.py` and Google tamper/idempotence cases |
| 13 | Per-class private assignment notices; actual send receipt owns 24/48-hour timing | Google mail-ledger and authenticated deadline-detail cases |
| 14 | Explicit confirmation, timely decline review, and distinct automatic acceptance | Google response, replay, and deadline cases |
| 15 | Documented exceptions, explicit affected-class consent, configured approval, preserved original run | Google consent/category tests, replacement audit tests, and rehearsal |
| 16 | Final validation and approval gate; separate sanitized, versioned Sheet and letter PDF | Google publication, PDF retry, sanitization, and permission tests |
| 17 | Server-side administrator and verified-recipient authorization | Google officer/blank-session, identity-token, replay, and consent negatives |
| 18 | Native standalone bundle completes offline sample draw and bundled GUI startup | Windows packaging CI and [clean-machine checklist](windows-packaging.md) |

## Run the rehearsal

```sh
uv sync --frozen
uv run --frozen python scripts/check.py
npm test --prefix google
uv run --frozen python scripts/rehearse.py --output rehearsal-output
```

The cross-language rehearsal writes the approved Google snapshot, local draw database, official export bundle, final synthetic state, sanitized roster, and summary. It proves agreement between the JavaScript export/import boundaries and Python's committed result. One class explicitly accepts, one declines and later consents to a resolved exception, and the other twenty become automatically accepted. The same output directory reuses its committed draw on retry.

Use [the manual sample walkthrough](../sample-data/README.md) to repeat the desktop actions yourself. Rehearsal output has a marker and cannot overwrite an arbitrary existing directory. It uses only reserved `example.invalid` contacts and calls no Google service.

## Complete production acceptance

Two or three designated PTA administrators must rehearse on their real staging deployment before live use. Confirm their separate identities, private workbook/state permissions, external parent Google identity flow, send quotas, delivery recovery, read-only public access, and letter-size PDF appearance. Have each administrator perform signoff, import, exception handling, and publication using fictional records first.

Adopt the unresolved event policy explicitly, including authoritative contacts, deadlines, grace duration, exception and publication authority, retention, and supported Windows versions. Record school approval and operator training. Neither generated approvals nor passing code tests supply that approval.

Hosted Windows CI uses a runner that also has developer tools installed, removes Python from the executable's PATH, blocks its networking, and requires a frozen binary. That demonstrates a bundled offline runtime. The separate clean-machine test on the PTA's supported Windows versions remains an operator acceptance step. Google OAuth, GIS origins, actual delivery, and account permissions also require staging evidence rather than mock-service results.
