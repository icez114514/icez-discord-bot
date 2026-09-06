# Casino latency validation — 2026-09-06

Implementation baseline: `89e684591191f025823238afb06d54ecca466d0b`.
Pool/lifecycle commit: `600d360`. Query consolidation and telemetry are the second commit.

## Reproducible database measurements

Windows Python 3.10, the same configured Neon endpoint, sequential operations in a disposable
`casino_test_<UUID>` schema with one seeded account. Each phase performs one unrecorded warm-up,
then 20 measured operations. No production accounts are read or modified by the benchmark.
Baseline ran before editing database.py; the optimized run used the new implementation.
No Discord calls or image synthesis are included. P95 is nearest-rank (19th of 20).

| Operation | Before median / P95 (ms) | After median / P95 (ms) | Median reduction |
|---|---:|---:|---:|
| Open lobby | 3392.35 / 3437.90 | 603.63 / 628.43 | 82.2% |
| Change wager | 2325.87 / 2377.11 | 578.12 / 607.11 | 75.1% |

Both exceed the agreed 40% database-stage median reduction. Raw samples are retained in
[casino-latency-samples.json](casino-latency-samples.json); harness: [benchmark_casino.py](../benchmark_casino.py).
Commands: `.venv/Scripts/python.exe benchmark_casino.py --output <before.json>` on the baseline,
then the same command with `--optimized --output <after.json>` on the updated implementation.

The improvement combines connection reuse and fewer operations: lobby drops from three checkouts
to one, wager changes from two to one. New operations still require transaction start, local
settings, account locking, SQL reads/writes and commit; these remaining database round trips are
included in the measurements. Pool waits are included in DB time, not added to it.

## Validation status

Pool contracts cover reuse, read/write alternation, row-factory reset, cancellation rollback,
broken-connection replacement, capacity timeout and idempotent close. New panel contracts cover
fresh balance snapshots, stale source rejection, active-game departure blocking, atomic rollback,
and connection return before rendering. Telemetry tests cover concurrent correlation isolation,
secret-free logging, cancelled lock waits and pool cleanup after startup failure.

The initial full run (92 tests) exposed three history failures and one fixture cleanup error.
Combining timeout configuration into SELECT acquires a snapshot, so history can no longer
change isolation afterward. Connection checkout now accepts an explicit isolation level;
history requests REPEATABLE READ before the first SQL. The next borrower resets to READ COMMITTED.
The accidental undefined fixture cleanup variable was removed. Existing history tests and the
pool mode-reset test serve as regressions. A rerun during edits hit Python's cached old module imports; a fresh-process, frozen-source run
resolved that test-runner artifact. The final complete suite passed: 100 tests, no skips,
with RUN_DB_TESTS=1 across three independent-schema process groups (74 + 11 + 15 tests;
130.235s, 157.745s and 228.508s respectively). All financial and recovery contracts passed.
The final offline run passed 55 tests and explicitly skipped 45 database tests.
Mypy passed database.py, casino_store.py, casino_commands.py, casino_records.py and latency.py;
pip check and git diff --check passed. Expanding mypy to crystal_commands.py also reveals two
pre-existing User|Member narrowing errors, unrelated to this change; these were not suppressed.

Final groups are reproducible with PYTHONPATH=tests and RUN_DB_TESTS=1: run unittest for
(test_blackjack_database), (test_casino_database), and all remaining test modules separately,
or use the documented sequential discovery command for the same 100 cases.

## Review

Standards axis: no documented-standard violations or required smell refactors.
Spec axis: startup correlation and unmeasured direct Discord deliveries were identified and fixed.
Follow-up review confirmed both fixes and the pre-query isolation change; handled failure status now also records errors accurately.


## Discord measurement boundary

No real player interaction has been measured for this change yet. Local interaction substitutes
verify behavior, not Discord/network latency. After restart, run /賭場 and change wagers in the test
server; collect at least 20 `Operation timing` samples per action. Separate total_ms from db_ms,
compose_ms, update_ms and auth_ms, and retain cold-start samples separately. Permissions remain
live-checked and may add HTTP delay. No fixed end-to-end response-time claim is made.

Pool lifecycle follows the [official Psycopg pool contract](https://www.psycopg.org/psycopg3/docs/advanced/pool.html): returning a connection commits or rolls back the transaction.

No schema migration is needed for this performance update. Rollback changes code and restarts
the process; it never rewrites financial data.


## Runtime verification

At 18:17 Asia/Taipei on 2026-09-06 there was no running project Bot process to stop.
Started the updated bot in the background (launcher PID 78104), confirmed database startup
status=ok with connection=cold (1834.5ms including warm-up and schema checks), three commands
synced to the configured test guild, and Discord login completed. No migration command was run.
Runtime output is local only at `C:/Temp/crystal-bot-latency.stdout.log` and
`C:/Temp/crystal-bot-latency.stderr.log`. These files are not committed.
Live player-interaction totals remain pending user activity; startup timing is not gameplay latency.
