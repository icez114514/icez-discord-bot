# Windows acceptance preparation for #26

Recorded 2026-09-16 (Asia/Taipei), against
`6541ea98666d8cfa44facdfe61ebbade91469089` on `main`.
Scope confirmed by the user: Windows preparation only. This is a new verification
record, not a replacement for the historical [delivery record](DELIVERY.md).
No production service restart, database migration, external deployment, or Discord
message was performed. Issue #26 remains open; phone acceptance is pending.

## Reproduce the local checks

Run from the repository root in PowerShell. These commands assume the existing
separate environments and installed frontend dependencies. On a fresh checkout,
install `poker/requirements-dev.txt` into the dedicated poker environment and run
`npm --prefix poker_web ci` before building. Do not replace the crystal Bot's
environment with poker dependencies.

Run each command separately and check `$LASTEXITCODE` immediately; stop on a
nonzero result. Output is bounded below; capture a failing command's full output
to a private local file if the tail does not explain the failure.

```powershell
rtk git rev-parse HEAD
rtk git status --short
rtk proxy uv pip check --python poker/.venv-deploy/Scripts/python.exe 2>&1 | Select-Object -Last 20
rtk proxy poker/.venv-deploy/Scripts/python.exe -m unittest discover -s poker_tests 2>&1 | Select-Object -Last 35
rtk proxy .venv/Scripts/python.exe -m unittest discover -s tests 2>&1 | Select-Object -Last 25
rtk proxy poker/.venv-deploy/Scripts/python.exe -m mypy poker --follow-imports=silent --ignore-missing-imports --exclude vendor 2>&1 | Select-Object -Last 25
rtk proxy poker/.venv-deploy/Scripts/python.exe -m ruff check poker --select F --exclude vendor 2>&1 | Select-Object -Last 25
rtk proxy npm --prefix poker_web test 2>&1 | Select-Object -Last 20
rtk proxy npm --prefix poker_web run build 2>&1 | Select-Object -Last 25
rtk proxy poker/.venv-deploy/Scripts/python.exe -m poker check 2>&1 | Select-Object -Last 35
rtk proxy node poker_tests/personalization_browser.mjs 2>&1 | Select-Object -Last 25
rtk proxy node poker_tests/replay_browser.mjs 2>&1 | Select-Object -Last 25
rtk git diff --check
```

`check` reads the configured root `.env` and reports sanitized preflight facts;
it does not migrate, start, drain or resume the service. Never attach `.env` or
private snapshots to an issue. Its model/build/config checks do not prove OAuth,
tunnel reachability, or that the running service uses the newly built assets.

The browser scripts currently require Chrome at
`C:/Program Files/Google/Chrome/Application/chrome.exe`, Node with built-in
WebSocket support, and `poker/.venv/Scripts/python.exe`. They use temporary
databases and simulated Discord identities. The personalization suite also scripts
transport/state faults; the replay suite uses the real local service and engine.
Do not point either suite at production. Build first and avoid concurrent copies
of the same suite because its loopback ports are fixed.

## Results from this run

| Check | Result and boundary |
| --- | --- |
| Windows runtime | Windows 11 build 26200; deployment Python 3.12.14 / SQLite 3.53.1 |
| Dependency consistency | `uv pip check`: 31 installed packages compatible |
| Poker suite | 101 passed in 41.389 seconds using the deployment runtime |
| Existing Bot suite | 162 discovered; 103 passed, 59 existing opt-in DB tests skipped |
| Python typing | Success for 31 source files with the exact mypy flags above; untyped bodies are not comprehensively checked |
| Ruff | F checks passed for first-party poker code |
| Frontend | 19 passed; TypeScript and Vite production build passed |
| Node / npm | 22.17.0 / 10.9.2 |
| Preflight | WAL version gate, both fixed NPZ hashes, and static build passed; one account in each admin allowlist |
| Personalization browser | All reported checks passed; three themes at 1440/390/320px; no page exceptions |
| Replay browser | All reported checks passed; 1440/390/320px; no page exceptions |

The browser suites used their existing Python 3.10.6 test environment, distinct
from the deployment runtime. It is not evidence that this older runtime is safe
for production. Deployment `check` still reports phone acceptance unverified and
OAuth requiring a real browser.

The deployment environment has no `pip` module, and the older test environment's
pip does not support `--python`. Neither failed invocation was treated as a
dependency pass; the installed `uv` completed the check without changing packages.

Machine-readable browser evidence is in `tmp/issue32-browser/results.json` and
`tmp/issue33-browser/results.json`, with screenshots alongside. These directories
are reused by the existing scripts: file presence alone is not a pass, and old
failure screenshots can remain. Associate current results with the command exit
status, timestamp and Git SHA before retaining a copy. Automated layout and hit
target assertions passed; screenshots were not visually reviewed in this run
because the image reader could not initialize its Windows filesystem helper.

## Phone handoff: collect evidence, then decide

Use [DEPLOYMENT.md](DEPLOYMENT.md) for operational commands and rollback rules.
For every row below record date/time, exact Git SHA, device/runtime, operator,
steps, expected/actual result, private evidence location, and any unresolved fault.
Initial status of every row is **pending real-device or real-service evidence**.
Historical desktop OAuth evidence in DELIVERY.md is not a fresh phone result.

| Gate | Required procedure and evidence |
| --- | --- |
| Device inventory | Record actual total/available RAM, Android and Termux versions, Python/SQLite, WAL gate, native NumPy/eval7/cryptography availability, model hashes and fixed NPC startup. Record the pinned source revision and licenses; deploy only required runtime/assets. |
| Configuration and HTTPS | Verify stable hostname, WebSocket forwarding, exact Discord callback, guild eligibility, separate role allowlists/tokens, private backup/export paths and permissions. Keep the internal listener private. Use the existing domain/tunnel arrangement only after confirming availability and authorization; no paid purchase is implied. |
| Lifecycle and isolation | Record wake lock/battery settings; demonstrate single-owner rejection, independent Bot failure, tunnel reconnect, Android background/force-stop behavior and restart. All game/NPC/database execution must be on the phone without a resident computer. |
| Backup and restore | Observe 15-minute SQLite API snapshots and retention (24 hours plus seven daily copies). Export encrypted, save manually to the computer, decrypt to a private destination and restore into a NEW directory. Compare ledger, hands, Time Bank, sessions, themes and statistics; verify no duplicate payout/debit. |
| Upgrade and rollback | Drain; wait for zero active hands; stop; take and hash final backup; record code/data pair; install/build/migrate; start in maintenance; verify health/NPC/backup/accounting; explicitly resume. Exercise failure and restore the matching code/data pair; never just downgrade incompatible code. |
| Two-table load | Play both tables with independent human browsers and fixed NPCs for at least two continuous hours, at most six seats each. Keep scheduled backups enabled. Record activity, command latency, NPC counters, service plus worker CPU/RAM, temperature and clock evidence as described below. |
| Fault drills | In an isolated phone drill instance, test network loss, force-stop, disk exhaustion, stuck NPC, transaction interruption, valid/corrupt snapshots and unknown contributions. Record recovery time and verified money outcomes. Target <=5 minutes; unknown funds remain frozen, never guessed. |
| Identity and gameplay | Real guild allow/deny, Taipei 04:00 scan and API failure, wait/sit-out/disconnect exemptions, revoke-all, subsidy race, controller takeover, expired invitation, capacity, close during hand, offline all-in and restart without redeal. |
| UI, privacy and Discord | Same-table M/N/O, theme persistence after login, switching without timer/input reset, red/black cards, mobile/desktop controls, authorized public/private statistics parity and role isolation. Inspect private network/log evidence for unrevealed cards. Actual Discord sends require explicit user authorization. |
| Latest merged contracts | Recheck ready-before-action, same-command retry after unknown acknowledgement, preselection invalidation, replay isolation, huge chip amounts and small screens. Follow PERSONALIZATION.md and REPLAY.md; neither feature requires a schema migration. |

Theme preferences are server-backed and belong in restore comparisons. BB display,
bet presets, four-color and large-card preferences are per-account localStorage
on the same device; they are not restored by a server snapshot or promised across
devices. Preserve this distinction when recording login/restore results.

For the phone load run, from its configured private repository directory:

```sh
python -m poker.monitor --output backups/poker/phone-two-table-UNIQUE-RUN.jsonl --duration 7200 --interval 5
```

The monitor records observations; it neither drives two tables nor declares a
pass. Start it before play and record the actual overlapping two-table interval
separately; extend collection if setup consumed part of the two hours. A monitor
error, missing measurements or an idle interval is not a passing load result.

- `command_p95_ms` is the rolling last 10,000 table-create/command samples,
  including rejected/replayed calls, queue wait and transaction time; it excludes
  external network, player waiting and asynchronous NPC inference. Record sample
  counts/window coverage with the <200ms target. Do not average rolling p95 values
  and label that the p95 of the whole run; report the observed windows explicitly.
- Compute NPC timeout rate from the interval deltas of `npc.timeouts` and
  `npc.requests`, target <1%. Zero requests cannot establish a pass. Counter resets
  require separate intervals and a recorded restart; do not subtract across them.
- Service CPU is cumulative and excludes the NPC process. Collect worker/OS CPU
  and RAM separately. Missing RSS/thermal readings are unknown, not zero.
- Loop delay and wall-clock step measure scheduler delay and clock changes,
  not absolute clock accuracy; separately record the reference and measured offset.
- Record accounting errors/crashes and actual recovery intervals. Snapshot RPO
  <=15 minutes depends on successful backups; whole-phone loss recovers only to
  the last manual export. Neither recovery target is certified by Windows tests.

Keep #26 open until its complete acceptance criteria have evidence. When remaining
work depends on unavailable phone/Discord configuration, use `ready-for-human`
through the normal issue workflow; do not check off those criteria from this file.
This preparation run does not change issue labels or claim final acceptance.

## Review and document checks

Independent Standards review: 0 findings. Independent Spec review: 0 findings
within the user-confirmed Windows preparation scope. Both reviewed the staged
documentation against the baseline above; test results came from this run's
command evidence, not new test runs by the reviewers. UTF-8 decoding, preserved
LF line endings, and staged diff whitespace checks passed.
