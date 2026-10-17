# Remaining-milestone implementation record

The scope expanded from the reviewed solver core to all remaining specification milestones. The user authorized autonomous review and merge. The specification and license remain unchanged.

| Decision or finding | Implemented response | Evidence |
| --- | --- | --- |
| Draw retries must never create fresh randomness | SQLite event reservation, durable intent, immutable committed records, explicit recovery | Concurrent and crash-injection run tests |
| Separate intent/result files complicate Windows recovery | Chose transactional SQLite over filesystem coordination | [ADR 0002](adr/0002-committed-runs.md) |
| Input metadata and actual desktop signoffs are different assertions | Retain both source approvals and operator approvals in the intent and hashed audit | Three-source-admin/two-operator regression |
| UI edits could differ from reviewed settings | Compare visible settings before approval/draw and disable frozen settings | Actual Tk settings regression |
| Packaging can accidentally depend on development Python | Test the frozen native executable with a restricted PATH and blocked network | Native bundle and Windows package smoke scripts |
| Dry-run cleanup could erase live confirmation tokens | Delete only tokens tied to cleared rehearsal notifications | Mixed DRY_RUN/SENT/SENDING adapter regression |
| Duplicate intake could bypass the deadline | Apply grace cutoff to repeat submissions unless an explicit correction grants an extension | Late-duplicate regression |
| Consent could permit a canonical category change | Bind consent to canonical booth/category and reject inconsistent roster categories | Consent/category attack regression |
| Parents need an exact deadline without exposing private data on GET | Authenticated details POST shows only their own assignment and actual deadline without consuming the token | Identity/deadline adapter regression |
| Infeasible input must remain correctable before freeze | Deterministic category-capacity maxflow before Google signoff, independent of desktop optimization | Fourteen-food-only draft case |
| Published documents must survive failed PDF requests without duplicate versions | Persist prepared artifact IDs, retry the same version, and share sanitized files read-only | Adapter PDF-failure/retry tests |
| Sample data must remain useful for manual tests | Deterministic carnival/Chinese-food generator, separate feasible/infeasible cases, mock intake, and walkthrough | Sample regeneration and full cross-language rehearsal |
| Windows checkout converted canonical inputs to CRLF | Pin repository text to LF and retain test failures as CI annotations | Reproduced with `git -c core.autocrlf=true checkout-index`; corrected checkout loads successfully |

Independent reviewers tested the durable desktop boundaries and Google service boundaries. Their findings were fixed with regression tests. Cursor-only control tools and prescribed pstack model families were unavailable, so the implementation used the available Codex agents, actual Tk widgets and CLI subprocesses, native executable tests, and Google service fakes. Production Google services were not contacted.
