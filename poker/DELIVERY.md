# Issue #26 local delivery evidence

Date: 2026-09-16 (Asia/Taipei).
Baseline: 11e7bc5da974c24e114a5bfa51b003f8a4fee576.
Initial implementation commit: a7b5d3c; follow-up review fixes are in subsequent
commits on the same branch. No GitHub issue was closed and no deployment-ready
phone claim is made.

## Environment and configuration

- Windows 11 build 26200; dedicated Python 3.12.14 / SQLite 3.53.1.
- Original Python 3.10.6 / SQLite 3.37.2 environment was retained; production
  preflight rejects that SQLite build. Existing crystal Bot environment unchanged.
- Shared root .env supported, with dedicated poker role/API credentials.
  Both administrator allowlists contain the user-selected account.
- Backups and exports are inside the repository at backups/poker/snapshots and
  backups/poker/exports, excluded from Git. Earlier empty C-drive backup directories
  were removed. Live game DB is separate from the crystal Bot database.
- Windows backup and live-data directories restricted to the operating account
  and SYSTEM. No .env contents were printed or committed.
- Fixed model and preflop SHA-256 checks passed.
- New runtime dependency compatibility check passed (31 installed packages).

## Automated checks

- Full poker suite: 82 cases passed in 26.210 seconds after fixing two existing
  Windows/new-Python test cleanup assumptions (explicitly close SQLite connection;
  terminate the venv launcher and its child in the crash drill).
- Final export-default change: all 10 deployment tests passed; this includes one
  additional regression case, so the final suite contains 83 cases. The 83-case
  full suite was not rerun merely to restate the prior result.
- After final path/lifecycle fixes: runtime + deployment targeted set, 10 passed.
- Existing Bot: 162 discovered, 103 passed, 59 existing opt-in DB tests skipped.
- mypy poker --follow-imports=silent --ignore-missing-imports --exclude vendor:
  passed, 28 service modules.
- ruff check poker --select F --exclude vendor: passed.
- poker_web npm run build: TypeScript and production Vite build passed.
- git diff --check: passed.

New evidence covers committed WAL data, concurrent writer ordering, backup
failure retaining the prior snapshot, 24h/seven-daily retention, encryption
roundtrip/wrong password/tampering, no-overwrite restore, retained sessions and
idempotent ledger replay, and settled-hand restore comparing account/Time Bank,
theme preferences and statistics. Maintenance permits hand completion while
rejecting new joins/table creation and stopping subsequent hands.

## Actual local service and external checks

- Local service started in the dedicated environment; fixed NPC ready.
- Automatic startup snapshot and manual authenticated backup both completed.
- Actual dedicated Cloudflare hostname https://poker.ice-z.net:
  homepage 200; /health 200 with schema 4; unauthenticated /api/account 401;
  /auth/login 303 with configured client ID and exact callback.
- Actual Discord API read-only checks: Bot application 200, configured guild 200,
  administrator guild membership 200. Initial OAuth application ID differed from
  the Bot application's ID; separate apps are possible, so this alone is not
  proof of an error.
- User initially reported an invalid OAuth response, then updated settings.
  Service was drained (zero active hands), backed up, restarted and resumed to
  load the updated .env. User then confirmed successful real Discord login.
  An additional consistent snapshot was saved after that login.
- No actual Discord message or slash-command response was sent during this work.
- Browser automation runtime was unavailable; no simulated login was claimed as
  real OAuth acceptance.

## Independent review

Standards and Spec agents reviewed the nonempty baseline-to-implementation diff.
Standards identified one minor unused export-directory setting; fixed by using it
as the default export destination and verified by a regression test and follow-up
review. Zero outstanding findings on either axis.

## Remaining acceptance

The user owns later physical-phone testing. See DEPLOYMENT.md for the complete
matrix: authenticated WebSocket gameplay, real
Discord command delivery, two-hour two-table phone load/thermal measurements,
Android lifecycle/storage/network faults, real-device restore and upgrade drills,
and cross-device privacy/UI checks. Metrics from an idle Windows server do not
establish command p95 or NPC timeout-rate targets under real load.
