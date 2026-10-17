# PTA Carnival Booth Lottery — Implementation Specification

**Status:** Codex handoff draft (2026-10-17)  
**Approach:** Decision-complete where specified; unresolved decisions explicitly flagged.  
**Goal:** Replace first-come-first-served class booth selection with a fair, reproducible, auditable lottery and manageable PTA workflow.

## 1. Product boundaries

Build (1) an offline Windows desktop application distributed as a standalone `.exe`, containing the lottery validator, feasibility solver, randomization, committed draw, preview, and CSV/audit exports; and (2) a Google Forms + Google Sheets + Apps Script administration workflow for intake, review, corrections, notifications, confirmations, exception tracking, and publishing. No paid hosting or API is required. Retain maintainable Python source. Do not make the desktop executable require Google credentials or Internet connectivity.

**Current-year defaults:** 22 classes; 9 game booths; 13 food booths; 3 distinct ranked proposals per class. Class count and category targets are adjustable in the desktop app for future years. Require `game_target + food_target == class_count` for a complete one-booth-per-class draw. All three proposal slots are mandatory; game/food combinations are unrestricted.

## 2. Locked policy decisions

1. One verified entry per **class**, not per family or room parent. Room parent changes do not change class identity. Shared Google Form with dropdown of all class IDs; collect name/email privately.
2. Each class submits three distinct ranked booth ideas, each with category, name, and description. All three are acceptable to the class; assignments outside these choices require explicit consent. Submitting early confers no advantage.
3. Proposals are private during intake; never publish other classes' proposals for selection. PTA reviews safety/feasibility, category, and duplicate-equivalence. Automatically *suggest* exact/similar names; PTA alone decides merges, based also on descriptions. Distinct standardized booth IDs represent unique booth activities; at most one class gets each booth ID.
4. PTA-rejected proposals may be replaced before the applicable correction deadline; preserve previous versions. Three approved, distinct standardized booth IDs per class are required to enter the official lottery.
5. Missing submissions: send reminders and offer a **uniform grace period** before freezing. Grace-period duration is configurable; 48 hours is a recommendation, **not a locked decision**. Unresolved missing submissions go to PTA review.
6. Before the official draw, perform a deterministic feasibility check for a full assignment with category quotas and uniqueness. If infeasible, privately invite **all potentially helpful classes** to voluntarily revise choices, without disclosing others' private proposals or promising any lottery advantage. Review changes and rerun feasibility. If still infeasible, stop and escalate; do not silently relax quotas or force assignments.
7. Lexicographic allocation priorities: (i) maximize participating classes, (ii) maximize approved **unique first-choice** assignments, where the first-choice booth ID is proposed by no other class at any rank, (iii) maximize number of first choices overall, (iv) maximize second choices, (v) use one frozen randomized class priority as deterministic tie-breaker. Do not misrepresent unique-first protection as guaranteed. In a full official draw, enforce exact category targets and one booth per class. No official draw if complete allocation is infeasible.
8. Random class priority can be generated automatically using cryptographically secure randomness with saved seed, **or** entered from a physical manual drawing of every class ID. One administrator may enter/verify a manual drawing; no second witness specifically required. Choose and lock method before official run; validate manual order is a permutation of all class IDs. Random priority is generated only at official draw, never during feasibility.
9. Two administrators review/approve the frozen input before the official draw (separate from manual-draw witnessing). Only 2–3 designated PTA admins edit private workbook; other officers receive a **separate sanitized read-only** dashboard, not merely a hidden tab.
10. Windows GUI, standalone `.exe`, local Python solver (OR-Tools recommended), CSV export/import. GUI screens: Import/Validate, Configuration & Feasibility, Official Draw, Committed Results & Export. Results are **committed before preview**. Preview is read-only; no reroll on preview, restart, or re-export. Record input snapshot/checksum, configuration, algorithm/app versions, randomization, class order, assignments, objective values, timestamps, and approvals. Original run is immutable; any exceptional replacement run requires documented authorization and preserves original record.
11. Privately email each class only its assigned booth, category, rank, and confirmation deadline. Allow 48 hours measured from actual send time; send a reminder at ~24 hours. Explicit accept = confirmed; timely decline = PTA review; no response at deadline = **auto-accepted**. Preserve distinction between explicit and automatic acceptance. Notify parents of this rule before submission.
12. Declines, withdrawals, and post-draw adjustments are PTA-managed **exceptions**, not reruns. Document reason, consent from any class whose confirmed assignment changes, approving administrator, and resulting roster version. Do not automatically assign unsubmitted choices or silently alter category quotas. **Exception approval authority (single/dual/tiered) remains undecided.**
13. Publish the complete roster **only after** confirmations and PTA exception review, and only if final validation passes. Publish both a sanitized read-only Google Sheet and a printable letter-size PDF, showing class, assigned booth, and category; no private contacts, original preferences, or internal lottery details. Version both after approved post-publication changes.
14. **Desktop packaging distribution:** Windows standalone executable (PyInstaller suggested); source preserved for maintenance. Distribution details (one-file vs one-folder, code signing) are implementation choices, not policy.

## 3. Personas and authorization

- **Room parent:** submit on behalf of one class; submit approved revisions; privately confirm or decline own class's assignment. Class dropdown alone is not authentication. PTA must verify authoritative submission and confirmation identity; tokenized links need server-side validation, expiration, and replay controls, not merely prefilled fields.
- **PTA lead admin:** manage submissions and reviews, export frozen data, operate desktop draw, import results, manage notices and exceptions.
- **PTA backup admins:** review submissions, proposals, duplicates, corrections; participate in frozen-input signoff. Any administrative action authorization must be enforced by script/service workflow where feasible; protected cells alone are not a security boundary.
- **Other PTA officers:** sanitized read-only dashboard.
- **Public/room parents collectively:** only published finalized roster.

## 4. Core data model

Use stable identifiers and versioning. Recommended entities:

- `Class`: `class_id`, `display_name`, `active`, authorized contact references (private only).
- `Submission`: `submission_id`, `class_id`, `submitted_at`, `submitter`, `verification_status`, `version`, `supersedes`.
- `Proposal`: `proposal_id`, `class_id`, `rank` (1..3), `original_name`, `description`, `proposed_category`, `canonical_booth_id`, `approval_status`, `review_reason`, `version`.
- `Booth`: `booth_id`, `canonical_name`, `category`, `pta_approval`, `duplicate_decision_history`.
- `CorrectionRequest`: `request_id`, `class_id`, `reason`, `deadline`, `status`, `proposal_versions`.
- `LotterySnapshot`: `run_id`, `schema_version`, `classes`, `approved_proposals`, `booth_catalog`, `game_target`, `food_target`, `input_hash`, `approved_by`, `approved_at`.
- `LotteryRun`: `run_id`, `method`, `seed_or_manual_order`, `priority_order`, `solver_version`, `objective_vector`, `assignments`, `committed_at`, `output_hash`.
- `Notification`: `run_id`, `class_id`, `message_id`, `sent_at`, `deadline_at`, `reminder_at`, `delivery_status`.
- `Confirmation`: `run_id`, `class_id`, `response`, `response_at`, `effective_status`, `token_reference`.
- `Exception`: `exception_id`, `type`, `affected_classes`, `reason`, `resolution`, `consents`, `approver`, `timestamp`, `roster_version`.
- `PublishedRoster`: `version`, `entries`, `approved_at`, `published_at`, `sheet_link`, `pdf_reference`.

Keep raw Google Form responses unchanged. Normalize into versioned tables. Maintain append-only event/audit history for material decisions.

## 5. Offline input/output contract

Export `classes.csv`, `approved_proposals.csv`, and `config.json` as a single versioned snapshot directory or ZIP. **Do not export room parent names or emails** to the desktop solver.

`classes.csv`: `class_id,display_name` (one row per class).

`approved_proposals.csv`: `class_id,rank,proposal_id,booth_id,category` (exactly three ranks per class; booth IDs distinct within class). Canonical booth names may be in separate `booths.csv` for display; if included, all instances of one booth ID must match name/category.

`config.json`: `schema_version`, `event_id`, `class_count`, `game_target`, `food_target`, `snapshot_created_at`, `approval_ids`, and hash manifest. Use canonical UTF-8, consistent line endings/ordering and SHA-256 manifest for repeatable verification.

Output `assignments.csv` (`run_id,class_id,booth_id,category,assigned_rank`), `lottery_audit.json`, `feasibility_report.json`, `lottery_summary.txt`. All outputs reference the same run ID and snapshot hash. Reject imports if identifiers, totals, categories, hashes, or run IDs disagree. Import must be idempotent.

## 6. Solver specification

Use a binary variable `x[c,b]` for each approved `(class, booth)` edge. Hard constraints for full draw: `sum_b x[c,b] == 1` for every class; `sum_c x[c,b] <= 1` for every booth; category sums equal configured targets; no edges for unapproved proposals. Validate exact count, ranks 1..3, distinct booth IDs per class, booth ID/category consistency, valid quotas, and approved snapshot. Feasibility is a separate solve without randomness.

Compute `unique_first(c)` from the **entire approved set**: the class's rank-1 booth ID appears in no other class's proposals at any rank. Lexicographically optimize objectives using sequential solves with equality locks on earlier optimum values, rather than arbitrary weighted approximations. Objectives: number assigned (for diagnostics/partial feasibility only), unique-first assignments, all first-choice assignments, second-choice assignments, then a deterministic random-priority tie-break. For the official run, require full assignment as a hard constraint; never issue a partial official roster. Clearly specify deterministic final tie-breaking for multiple optima: e.g., lexicographically minimize assigned rank/booth ordering in priority order after previous objectives are locked, with stable canonical booth ID ordering. Ensure tie-breaking does not inadvertently override higher objectives. Save solver status and validate solution independently before committing.

**Feasibility correction diagnostics:** identify candidate classes that *could* help by changing choices. This is a diagnostic, not a mathematically guaranteed minimal repair set; conservative broad outreach is acceptable. Avoid presenting any single class as the cause of infeasibility. Do not draw priority or commit a run during diagnostics.

## 7. Desktop state machine and crash recovery

States: `DRAFT_IMPORT` -> `VALIDATED` -> `FEASIBLE` -> `APPROVED_FROZEN` -> `COMMITTING` -> `COMMITTED` -> `EXPORTED`. Configuration/input edits invalidate feasibility and approvals. Randomization mode locks at `APPROVED_FROZEN`. On Run, write a durable run-intent record **before revealing any assignment**, then atomically commit seed/order, input hash, output, and audit. On crash/restart, recover the existing committed result or fail closed with an explicit recovery workflow; do not create a fresh draw for the same event/run ID. Exports can be repeated without modifying assignments. Keep original immutable if a separately authorized corrective run is necessary.

The GUI must label feasibility tests as nonofficial; results preview must clearly say `OFFICIAL — COMMITTED`. A confirmation click should warn that rerolls are not allowed. Errors should be actionable and must not expose private data.

## 8. Google workflow and automation

Private workbook tabs (names illustrative): `Classes`, `Form Responses`, `Submissions`, `Proposals`, `Duplicate Review`, `Booth Inventory`, `Correction Requests`, `Lottery`, `Confirmations`, `Exceptions`, `Audit Log`, `Admin Dashboard`. Public dashboard and final roster in **separate sanitized spreadsheets**.

Apps Script responsibilities: intake validation and duplicate-class flags; reminders and grace notices; similarity suggestions (never auto-merge); review/correction notices; export frozen validated snapshot; verify/import official results; send private assignment emails and track actual send timestamps; send ~24h reminders; process responses; transition nonresponses to auto-accepted at 48h; exceptions and publication gating; produce sanitized roster and printable PDF.

Time triggers may not fire at exact minutes. Enforce `now >= sent_at + 48 hours` and reject/route late declines according to documented policy; do not falsely claim exact scheduler timing. Use script locks and idempotency keys for email and status transitions. Confirmation links must not expose other classes' information. Document Google quota limitations and recovery from failed sends.

## 9. Publication gate

Publish only if: every included class has exactly one approved current assignment; no duplicate booth IDs; game/food counts match configured targets; all responses are explicit or auto-accepted; no unresolved declines or exceptions; designated PTA approval recorded. Export sanitized read-only Sheet and versioned PDF. If post-publication exception changes roster, keep historical versions and publish updated version with date.

## 10. Security, privacy, and audit

Apply least privilege to private workbook, Apps Script, and Drive folders. Do not expose private workbook by publishing or hiding tabs. Store only needed contact information; keep it out of optimizer exports and public outputs. Protect confirmation links from cross-class use and replay; document that emailed bearer tokens can be forwarded, so consider class-email verification or admin reconciliation for disputes. Sanitize spreadsheet formula injection on CSV import/export and public display; enforce strict CSV schema and safe file paths. No arbitrary execution from CSV. Preserve approval, duplicate resolution, seed/manual order, frozen hash, run output, confirmations, exceptions, and publication history. Define a PTA-approved retention/deletion policy before live rollout.

## 11. Acceptance tests

1. Exactly one verified entry per class; duplicate class submissions are flagged, never automatically treated as separate classes.
2. Missing initial deadline triggers reminder/grace; late unresolved classes block official draw and go to PTA review.
3. Every class has ranks 1,2,3 and three distinct approved booth IDs; otherwise official draw blocked.
4. Similar names are flagged but never merged without PTA decision; identical canonical booth IDs cannot be assigned twice.
5. Reject booth/category inconsistencies, missing booth IDs, wrong class count, invalid quotas, or unapproved proposal.
6. Feasibility succeeds only when full unique matching meets configured targets; e.g., 14 food-only classes with 13 food slots fails.
7. Feasibility failure produces targeted correction workflow, with all potentially helpful classes eligible for private invitation, no random draw.
8. Optimizer maximizes unique-first outcomes *only after* full participation; compare against brute-force enumeration on small synthetic cases to verify lexicographic ordering.
9. Full 22-class default allocation yields 22 unique classes, 22 unique booth IDs, 9 games, 13 foods; changing targets validates against new settings.
10. Automatic draw saves seed/order and is reproducible; manual draw rejects missing/duplicate IDs and accepts one-admin verification.
11. Official result is committed before preview; restarting, clicking twice, or exporting repeatedly cannot reroll or overwrite.
12. Import of tampered/mismatched output fails; repeat import is idempotent.
13. Assignment notifications are private, and 48h deadline uses actual send time; reminder occurs approximately 24h later.
14. Explicit accept confirms; timely decline enters PTA review; no response after deadline becomes `AUTO_ACCEPTED`, distinct from `CONFIRMED`.
15. A withdrawal creates a logged exception, preserves original draw, requires affected-class consent for changed confirmed assignment, and does not auto-rerun.
16. Publication blocked on unresolved exception or quota mismatch; final Sheet/PDF have same roster version and contain no private data.
17. Unprivileged officer cannot access raw responses through sanitized dashboard; negative authorization tests included.
18. Packaged Windows executable starts and completes a sample run on a clean test machine without Python installed or network access.

## 12. Implementation plan for Codex

**Milestone 0 — Repo & decisions:** establish Python project, dependency lock, schema fixtures, ADRs, CI, test runner, and a `DECISIONS.md` with locked/unresolved rules. Do not connect real Google accounts.

**Milestone 1 — Solver core:** implement schema/parser, validation, feasibility, exact lexicographic optimizer, auto/manual class priority, independent result verifier, synthetic and property-based tests. CLI/internal API permitted for development but not required for PTA users.

**Milestone 2 — Audit and committed runs:** immutable snapshots, SHA-256 manifests, run-intent/recovery state machine, atomic persistence, export formats, tamper/replay tests.

**Milestone 3 — Windows GUI:** Tkinter import/configure/feasibility/approval/draw/preview/export, accessibility and user-friendly errors. Support annual configurations.

**Milestone 4 — Windows packaging:** PyInstaller build, ZIP packaging, checksums, clean-machine smoke test, operator manual. Do not assert SmartScreen/code-signing bypass.

**Milestone 5 — Google integration:** Form design/instructions, Sheet schemas, Apps Script processing, correction/duplicate workflow, exports/imports, notices, confirmation token handling, scheduled transitions, exceptions, separate sanitized dashboard and versioned PDF. Use mock data and dry-run email mode first.

**Milestone 6 — End-to-end rehearsal:** simulate 22 classes, conflicts, corrections, draw, confirmation outcomes, withdrawals, publication, failure recovery. Train 2–3 PTA admins; secure board approval before production.

## 13. Unresolved decisions / do not invent policy

- **Exception approval:** single admin vs two-person vs tiered; earlier recommendation was single but user did not choose. Make configurable or block sensitive approvals pending decision.
- **Grace-period length:** uniform grace selected, exact length not approved (48h recommended).
- **Rejected-proposal and targeted-correction response deadlines:** set by PTA per event, not yet fixed.
- **Room parent authorization:** shared class dropdown alone does not authenticate; choose approved roster verification, email identity validation, and confirmation token flow before live use.
- **Who approves final publication** and how approval is recorded: administrator approval implied, detailed authority not settled.
- **Manual drawing physical protocol:** one person may enter/verify; physical randomness method not prescribed.
- **Post-deadline decline handling:** late declines should be routed to PTA exceptions; do not quietly reverse auto-acceptance.
- **Retention policy, event dates, actual class roster, school name, notification sender, Google permissions:** supply before live launch.
- **Windows support target:** Windows 10/11 suggested, but final OS compatibility must be tested.
- **Algorithmic tie-break nuance:** random class priority is a last-stage tie-breaker, not sequential greedy assignment; write and test an explicit deterministic ordering.

## 14. Codex execution prompt

> Implement this specification incrementally. First read `SPEC.md` and extract locked requirements, assumptions, and unresolved policy. Start with Milestone 0 and Milestone 1 only. Create deterministic fixtures, exact lexicographic solver tests, and a feasibility checker before any GUI or Google integration. Do not implement unresolved PTA policy as if approved. Never claim a draw is fair without tests validating the objective hierarchy. Keep official draws immutable and auditable. After Milestone 1, report files changed, test results, assumptions, and blockers, then await review before proceeding.
