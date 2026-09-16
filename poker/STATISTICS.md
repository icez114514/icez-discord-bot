# Statistics, administration and Discord (#25)

Extends the #24 handoff at `ed4ec10e4701000761f7f803b3c3af7dbd85d82e`.

## Upgrade and configuration

Stop the service, take a consistent backup, then run `python -m poker migrate`.
Schema 4 adds disabled accounts, per-hand statistics, durable management commands
and immutable management audit records. The migration backfills completed #23/#24
snapshots in the same transaction as its schema marker. Incomplete pre-engine
fixture snapshots without dealt cards/time are not invented as historical data.
Normal startup rejects older schemas. Build `poker_web` with `npm run build`.

- `POKER_TABLE_ADMINS`: comma-separated Discord account IDs for account disable,
  table close, player removal and statistical projection repair.
- `POKER_FUNDS_ADMINS`: independent allowlist for chip adjustments and ledger reads.
- Both lists default empty. Discord guild permissions and table ownership grant
  neither role. An account may explicitly belong to both lists.
- The existing Bot requires `pip install -r requirements.txt`, `POKER_READER_TOKEN`,
  `POKER_GUILD_ID`, and optionally `POKER_INTERNAL_PORT` (8766). The read credential
  must match the game service. The Bot's query adapter needs no funds credential.
  Its normal command sync registers `/德撲 餘額`, `/德撲 榜單`, `/德撲 數據` when configured.

## Query contract

`GET /api/statistics?period=all&opponents=all` uses the authenticated session only.
Periods are `all`, `30`, `7`; opponents are `all`, `human`, `mixed`. A supplied
`user_id` must equal the caller, including when the caller is an administrator.
The response combines the caller's private counts with the public leaderboard in
one writer transaction and one query time. Public rows expose only current settled
assets, effective hands and net win rate; ties use competition ranks and stable
account ID order. NPC accounts never appear on the leaderboard.

The Bot calls `GET /statistics` on the authenticated loopback listener with the
reader credential, interaction `X-Actor-ID` and configured `X-Guild-ID`. The service
checks guild membership and disabled state and calls the exact same query function.
The Bot takes no target-user argument and replies ephemerally. Crystal commands
and their PostgreSQL balances are unchanged. No real Discord messages were sent
while implementing this ticket.

Each committed hand has integer numerator/denominator pairs for net win, VPIP,
PFR, 3-bet, fold to 3-bet, flop C-bet and showdown pot-share rate, plus formula
version, net, classification and settlement time. Original actions, automatic
flags, contributions, refunds and payouts remain in the durable hand/settlement
events. Replaying action history uses the engine's raise legality, including short
all-in reopening rights. A refund is included once in net and excluded from W$SD.
Classification uses only the dealt roster, including an NPC that later folds.
Windows use settlement times in [start, query time), with Asia/Taipei display.
Counts are summed before ratios; assets are never filtered. Zero denominators show
an em dash; positive denominators display one decimal and the relevant low-sample
warning (100 hands for net win/VPIP/PFR, 20 opportunities for other metrics).

## Management contract

`GET /api/roles` exposes only the caller's allowlisted capabilities.
`GET /api/management` provides redacted account/table states. No invitation,
private cards, deck or other player's private metrics are returned.
`POST /api/management/commands` accepts `{command_id, action, target, reason,
amount?}`; actions are `adjust`, `disable`, `close`, `remove`, `rebuild`.
Mutations also require the existing same-origin guard. Identity comes from the
session, and permissions are rechecked within the mutation transaction.

Commands persist both successful results and business-rule failures. Identical
retries replay the original result; changing an intent under an existing ID fails.
The browser preserves an uncertain intent in account-scoped session storage until
it gets a definite result. Adjustments change only available and settled funds,
with nonnegative balances enforced in the writer transaction. Audit includes
actor, target, reason, time, command and before/after balances. Loopback adjustments
use the same authority. Ordinary host controls cannot close a table.

Close marks the table closed to new hands immediately; the current hand continues
normally, including all-in entitlements. Disable immediately revokes sessions and
blocks future login, marking the current seat for departure. Remove marks just
the seat. All use existing hand-boundary cashout. Management distinguishes closing,
closed, open and frozen tables and supports explicit refresh after settlement.

`GET /api/management/audit?after=<id>&user_id=<optional target>` and
`GET /api/management/ledger/<user_id>?after=<id>` provide cursor-paged audit/ledger
records. Ledger amounts are decimal strings and retain shared hand/command IDs
for tracing transfers across accounts. Management audit never exposes statistical
repair evidence to another player.

`rebuild` is an audited projection correction: it reverses the stored per-hand
projection, rebuilds from the unique authoritative settlement event, and replays
the affected accounts' chronological Time Bank debit/award history with its cap.
Before/after evidence is retained atomically in immutable audit. Active hands or
missing settlement evidence are rejected; a void event rebuilds no statistics.
It does not rewrite the immutable money ledger or accept client-supplied outcomes.
Changing a historical money outcome is not supported by this projection repair;
explicit authorized balance adjustments remain separately audited.

## Verification

- Poker suite: `poker/.venv/Scripts/python.exe -m unittest discover -s poker_tests -q`.
- Bot suite: `.venv/Scripts/python.exe -m unittest discover -s tests -q`.
- Service typing: `python -m mypy poker --follow-imports=silent --ignore-missing-imports --exclude vendor`.
- Lint: `python -m ruff check poker --select F --exclude vendor`.
- Frontend: `npm --prefix poker_web run build`.
- Browser: `node poker_tests/browser_acceptance.mjs`, isolated temporary DB and
  hidden Chrome profiles. Only OAuth identity responses are simulated; the engine,
  settlements, HTTP/WebSocket transport and UI run normally.

Formula cases cover walk, forced all-in, small-blind completion, short raises,
call-only all-in, cold 3-bet, 4-bet exclusion, C-bet lead exclusion, side-pot wins
with net loss, refund-only losses and zero/low denominators. Integration covers
exclusive query end/inclusive rolling start, fixed mixed classification, voids,
replay, restart, schema 3 backfill, repair of corrupt derived counters/progress,
web/loopback equality, cross-account privacy, role forgery, chip races, all-in close
and disabled-login enforcement. Browser checks retain the live socket while the
statistics dialog is open and verify desktop/mobile filters and management close.

Physical phone performance, real Discord OAuth/command delivery, production HTTPS
and deployment remain #26.
