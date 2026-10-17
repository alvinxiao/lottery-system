# ADR 0001. Exact solver core and strict snapshot boundary

Status accepted for Milestones 0 and 1.

## Context

Allocation must satisfy a complete matching and exact category counts while preserving the specified objective hierarchy. The original repository contains the specification and no application. The initial deliverable must be testable without real PTA data or an official-draw workflow.

## Decision

`domain.py` owns frozen `Class`, `Proposal`, `Config`, `Snapshot`, and `Assignment` records and cross-record invariants. `snapshot.py` owns untrusted CSV/JSON parsing, canonical serialization, fixed filenames, checksums, and metadata checks. It accepts directories only and rejects symbolic-link input files. `priority.py` owns pure permutation and replay utilities and explicit cryptographic seed creation. `solver.py` owns CP-SAT constraints and exact sequential objective locks. `verify.py` owns independent constraint checking and objective recomputation. `cli.py` exposes validation and nonofficial feasibility only.

Input flows from directory parsing into a validated snapshot, then into either feasibility or optimization with an explicitly supplied permutation. Optimization returns immutable assignments and an objective vector after independent verification. No assignments flow into a preview or persistence system in this milestone.

Sequential solves maximize unique-first assignments, first choices, and second choices, then minimize each class's rank in priority order. Each solve must prove OPTIMAL. Exactly one booth occupies each rank, so this final ordering fully determines the allocation without an additional booth comparison. Feasibility accepts a demonstrated full solution but distinguishes unproved status from infeasibility.

## Alternatives considered

A brute-force enumerator is simple and independent but grows exponentially. It remains the small-case test oracle. A weighted single solve risks incorrect dominance or integer scaling errors and is rejected. A greedy priority allocator can violate global feasibility or earlier objectives and is rejected. CP-SAT supplies explicit feasibility and optimality statuses and exact integer constraints.

## Consequences

Large inputs may require repeated solves. Optional limits apply to each stage and fail closed if optimality is unproved. The checker validates returned constraints and reported objectives but does not independently establish optimality. Exhaustive generated small-instance tests supply that evidence. Frozen metadata is a consistency contract, not administrator authentication. Official use remains blocked pending later persistence and authorization controls.
