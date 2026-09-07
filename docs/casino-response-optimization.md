# Casino response optimization — 2026-09-06

## Changes

- Keep debit and settlement as separate transactions. After acquiring the account lock,
  batch prerequisite reads and ordered debit writes using psycopg pipeline. Combine account
  updates and ledger insertion in one SQL statement. No automatic financial retries or migrations.
- Audit navigation acknowledges first, checks live authorization before reading, then again
  before publishing. Remove repeated authorization HTTP from the framework guard and internal
  navigation lock. Owner/stale-view guards stay local; opening a Modal still requires one live
  authorization check before responding with the Modal. No authorization cache is introduced.
- Timestamp parsed interaction dispatch, handler entry and acknowledgement start/end. Record
  event-loop lag every 30 seconds to the existing rotating timing file, never routine console output.

## Database measurements

Same Windows environment and configured PostgreSQL endpoint, disposable schemas, one warm-up
and 20 sequential samples for each operation. Normal Bot background activity remains running;
full regression tests were run after benchmarking, not concurrently. Deterministic dice wins and
blackjack naturals include the payout path. Non-natural blackjack turns are covered by regression,
but these figures must not be presented as measurements of every possible hand.

| Operation | Before median / P95 (ms) | After median / P95 (ms) | Median reduction |
|---|---:|---:|---:|
| Dice start | 1811.1 / 1849.8 | 1268.1 / 1290.3 | 30.0% |
| Dice replay | 1904.6 / 1925.6 | 1268.0 / 1283.6 | 33.4% |
| Blackjack start | 1810.0 / 1835.2 | 1263.5 / 1320.4 | 30.2% |
| Blackjack replay | 1926.6 / 1954.2 | 1265.2 / 1393.7 | 34.3% |

Raw samples: [casino-roundtrip-samples.json](casino-roundtrip-samples.json).
Harness: [benchmark_roundtrips.py](../benchmark_roundtrips.py), invoked as
`python benchmark_roundtrips.py <output.json>` on each code version. The before run loaded the
pre-batching CasinoStore implementation (the same store code as commit d85ecfb) before edits.
P95 uses nearest-rank (19th of 20). These numbers exclude Discord and image delivery.

## Verification and operating limits

New contracts prove that SQL failure and cancellation during batched debit roll back balance
and operation token, and that the next operation can use the store. Audit tests require defer
before HTTP, exactly two live checks on navigation, and no record publication after revocation.
Telemetry tests separate interaction age from acknowledgement HTTP and detect a deliberate
50ms event-loop stall. The complete PostgreSQL-enabled regression passed all 107 tests
(79 general/pool/UI tests, 11 blackjack database tests, and 17 casino database tests),
including concurrent financial operations, recovery, and interrupted commits. The offline run
passed with 47 database tests skipped. Mypy passed for the four modified runtime modules;
`git diff --check` passed. Independent Spec and Standards reviews found no actionable issues.

Interaction ages compare the host UTC clock with Discord timestamps and can include clock skew.
`dispatch_wait_ms` and `ack_http_ms` use monotonic time. Only parsed dispatch is observed, not
raw network arrival; early transport/decoding and client image loading remain outside that seam.
`ack_http_ms` is a subset of `update_ms`, not an additional additive stage. 10062 handling remains
safe termination of that interaction; instrumentation does not eliminate external network delay.

Pipeline requires libpq 14+; the installed pinned Windows binary supports it. Pool sizes, account
locks, operation tokens, unique constraints, version checks and settlement recovery remain in place.
No change is made to the background expiry interval or authorization policy.

## Runtime rollout

Restarted the verified project Bot process after validation. At 20:38:31 local time,
three test-server commands synced; at 20:38:34 the Bot logged in successfully. Background
expiry operations continue successfully through the warm pool. Routine operation timing
remains in `logs/latency.log`, with no timing spam in redirected console output.
Real Discord interaction latency and new acknowledgement-age fields still require user
operations after this rollout; the database benchmark does not establish end-to-end latency.
