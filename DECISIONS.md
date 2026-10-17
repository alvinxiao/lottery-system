# Decisions

The authoritative requirements remain [docs/spec.md](docs/spec.md). This implementation stops after Milestone 1 for review.

## Locked rules implemented

- Full participation is a hard constraint. Infeasibility blocks optimization output.
- Each class has exactly three approved ranked distinct booth IDs. Booth identity and category remain consistent.
- Exact game and food quotas and globally unique assigned booth IDs are mandatory.
- Objective locks preserve unique-first, first-choice, then second-choice counts before class-priority tie-breaking.
- Unique-first considers every other class's proposals at every rank.
- Feasibility uses no randomized class priority. All classes remain eligible for private correction outreach.
- Manual priority needs every class exactly once. Automatic priority has a reproducible versioned seed algorithm.
- Frozen-input metadata records at least two distinct approval IDs. Recorded IDs do not authenticate people.

## Implementation choices

Version 1 accepts canonical snapshot directories, not ZIP files. Categories are lowercase `game` and `food`. SHA-256 of canonical config bytes identifies a snapshot and binds the CSV manifest. Neither checksum nor approval metadata establishes trusted provenance. The operator must obtain the snapshot through an authorized process.

Pure frozen domain objects, boundary validation, and an independent result checker separate input handling from solving. Sequential CP-SAT solves prove each exact objective before locking it. A supplied priority uniquely orders rank choices after those locks. Priority generation is a library utility and is not an official draw. The CLI exposes only nonofficial validation and feasibility.

## Unresolved policy and deferred controls

No defaults are invented for exception approval authority, grace-period duration, correction deadlines, authoritative room-parent identity verification, final publication authority, physical drawing procedure, retention, event dates, school identity, or Windows support target. Late declines remain a future PTA exception workflow.

Milestone 2 must implement immutable official runs, intent-before-preview, atomic commit and crash recovery, audit records, tamper/replay protection, and exports before exposing an official draw. Subsequent milestones own GUI, Windows packaging and clean-machine verification, Google integrations, private notices, confirmations, exceptions, and publication. No real Google accounts are connected here.
