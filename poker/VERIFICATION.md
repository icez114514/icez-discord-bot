# Verification for issue #22

Date: 2026-09-15 (Asia/Taipei). Review base: `92724c2c1039dae4a4d9f3fb21d68e8efbd76cc2`.

## Results

| Check | Result |
| --- | --- |
| Dedicated Python 3.10.6 environment, pinned runtime dependencies | Installed; `pip check`: no broken requirements |
| `poker/.venv/Scripts/python.exe -m unittest discover -s poker_tests` | 19 tests passed |
| Existing Bot `.venv/Scripts/python.exe -m unittest discover -s tests` | 160 tests collected; 101 passed, 59 opt-in database tests skipped (`RUN_DB_TESTS=0`) |
| `mypy --check-untyped-defs poker` | Passed, 13 service files |
| Ruff formatting and F checks | Passed after removing unused imports |
| `npm run build` | TypeScript and Vite passed; static assets produced |
| Actual CLI `migrate` / `serve` | Both loopback listeners healthy; homepage served; second owner rejected; restart reacquired lock |
| Headless Edge / Playwright, latest backend and pinned runtime | Simulated login, 1,000 -> 5,000 subsidy, disabled repeat claim, logout, relogin retaining 5,000 |
| Mobile 390px viewport | No horizontal overflow; no JavaScript page errors; screenshot visually inspected |
| `git diff --check` | Passed |

The system Python lacked existing Bot dependencies; rerunning with the existing
Bot virtual environment resolved the import failures. The new service has its own
virtual environment and never adds game dependencies to the Bot requirements.

## Standards review

Independent standards review found no hard documented violations and one optional
duplicated-code concern in eligibility checks. Extracted `protected_since_snapshot`
and retained both transactional checks. Follow-up review: **0 unresolved findings**.

## Spec review

Independent spec review found two persistence/replay issues:

1. Funds needed to persist a hand snapshot/version and Time Bank spending together.
   Commands now atomically update the hand version/snapshot, money/event records,
   or persisted action deadlines and 5-second spending (four extensions maximum).
   `test_hand_persistence.py` verifies stale rejection, atomic update and replay.
2. The HTTP subsidy route returned fresh account data rather than the saved outcome.
   It now returns the frozen result; `GET /api/account` gives current data separately.
   `test_http_replay.py` verifies replay after an intervening adjustment.

Follow-up spec review: **0 unresolved findings**.

## Limits

Browser login used an explicitly gated TEST Discord transport. No real Discord
OAuth/guild permission, production HTTPS or Termux phone acceptance was performed.
No complete table/NPC gameplay or production backup/restore was claimed. The 59
existing database integration tests need their separate opt-in test environment.
See [README](README.md) for reproducible startup, test mode and integration contracts.