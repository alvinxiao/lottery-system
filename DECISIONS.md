# Policy and implementation decisions

[docs/spec.md](docs/spec.md) remains the product contract. The request to implement the whole specification supersedes its original Milestone 1 pause. All implementation milestones are now in scope.

## Allocation rules

A full draw requires one approved proposal per class, unique assigned booth IDs, and exact game and food targets. Every class needs ranks 1, 2, and 3 with distinct approved canonical booths. Unique-first eligibility considers every other class at every rank. Sequential CP-SAT solves lock unique-first, first-choice, then second-choice optima before class-priority tie-breaking. Each optimization stage must prove optimality.

Feasibility creates no random priority and reveals no assignment. Infeasibility blocks official intent creation. Correction diagnostics conservatively include every potentially helpful class without blame or disclosure of private proposals.

## Official runs

SQLite owns durable run intent and immutable committed results. The intent records the frozen snapshot, method, seed or manual order, and runtime versions before solving. Recovery reuses that plan. One original event slot prevents accidental rerolls even when a new run ID is supplied. Committed records remain readable after software updates, while unfinished recovery fails closed if its required runtime changes.

Results appear only after commit. Repeated export is deterministic and refuses conflicting destination content. Replacement draws require an explicit authorization record and configured authority, preserve the original, and link their audits. Operator-entered authority assertions are not identity authentication. The desktop is operated under PTA machine access and in-person review procedures.

The directory interchange format uses canonical UTF-8 CSV and JSON. The snapshot hash is SHA-256 of config bytes, binding the CSV manifest without self-reference. Output hashes bind canonical run fields, excluding the output hash itself. Neither checksum establishes provenance.

## Google administration

Private intake, raw responses, contacts, reviews, and audit state stay separate from sanitized officer dashboards and published rosters. Administrator operations validate the active identity against configured administrators. Parent confirmations validate both a private one-use token and the verified contact identity. GET requests do not record responses.

Actual successful email sends start the 48-hour response window. Timely explicit acceptance and deadline auto-acceptance remain distinct. Ambiguous sends require reconciliation instead of automatic duplicate delivery. Declines and withdrawals are exceptions, not rerolls. Changed assignments require affected-class consent and configured PTA approval. Publication requires complete validation, accepted confirmations, resolved exceptions, and designated approval.

## PTA decisions required for live operation

No production defaults are invented for grace duration, correction deadlines, exception approval authority, publication authority, authoritative contact verification, retention, event dates, school identity, or supported Windows versions. Live-sensitive operations block when their required policy is absent. The sample data supplies explicit fictional policy only for rehearsals.

Automatic priority uses a cryptographic saved seed and a versioned replay algorithm. Manual priority requires a complete permutation and permits one person to enter and verify the physical draw. Two separate input approvals are still required. Packaging uses a one-folder executable and ZIP checksum. Code signing and distribution trust remain operator choices, not security warnings to bypass.

## Validation limits

Local tests use synthetic records, mocked Google services, and dry-run messaging. They do not establish Google production permissions, actual email delivery, quota capacity, or school policy approval. Hosted Windows packaged smoke tests demonstrate the tested runner environment. Separate operator acceptance on each supported Windows version remains necessary before live distribution.
