# Poker service, accounts and gameplay (#22–#26)

Local deployment, shared .env, backups, encryption, upgrade and phone acceptance:
[DEPLOYMENT.md](DEPLOYMENT.md). That document supersedes the foundation-only
configuration and future-deployment notes below.

For current schema 4, statistics, administration and Discord commands, see
[STATISTICS.md](STATISTICS.md). For multiplayer tables and themes, see
[MULTIPLAYER.md](MULTIPLAYER.md).

For the complete single-table game, fixed NPC, schema 2 upgrade and verification,
see [GAMEPLAY.md](GAMEPLAY.md). Run `python -m poker migrate` with the service
stopped before upgrading. The sections below retain the account foundation contract.

Independent Python 3.10+ FastAPI service and React/TypeScript/Vite account page.
The existing Bot, crystal balance and Neon database are not imported or migrated.
The game runs in one process on the phone; the desktop builds static frontend files.

## Install and run

From the repository root, create a separate environment:

```sh
python -m venv poker/.venv
poker/.venv/bin/python -m pip install -r poker/requirements.txt
cd poker_web
npm ci
npm run build
cd ..
```

On Windows, use `poker\.venv\Scripts\python.exe` instead of
`poker/.venv/bin/python`. Node 22.12+ is needed only on the build machine.
Copy `poker_web/dist` to the same relative path on the phone with the Python source.
The service serves these files itself; no Node development server runs on the phone.

Set environment variables in your service manager or private shell environment.
This service deliberately does not read the existing Bot's `.env`.

| Variable | Required value |
| --- | --- |
| `POKER_ENV` | `production` (default), `development`, or explicit `test` |
| `POKER_DATA_DIR` | Absolute private directory, e.g. `$HOME/.local/share/icez-poker` in Termux; never shared Android storage |
| `POKER_ORIGIN` | Exact HTTPS origin without trailing slash, e.g. `https://poker.example.org` |
| `POKER_CLIENT_ID` | Discord application ID |
| `POKER_CLIENT_SECRET` | Application client secret |
| `POKER_BOT_TOKEN` | Token of the Bot installed in the configured guild |
| `POKER_GUILD_ID` | Required Discord community ID |
| `POKER_READER_TOKEN` | Random credential of at least 16 characters for Bot queries |
| `POKER_FUNDS_TOKEN` | Different random credential for fund administration |
| `POKER_FUNDS_ADMINS` | Comma-separated Discord user IDs authorized for fund adjustments |
| `POKER_TABLE_ADMINS` | Independent allowlist for account/table management |
| `POKER_PUBLIC_PORT` | Local public listener port, default 8765 |
| `POKER_INTERNAL_PORT` | Separate local Bot listener port, default 8766 |

Generate internal credentials with `python -c "import secrets; print(secrets.token_urlsafe(32))"`.
For local development set `POKER_ENV=development` and
`POKER_ORIGIN=http://127.0.0.1:8765`. Register that exact callback URL,
`http://127.0.0.1:8765/auth/callback`, in the Discord Developer Portal.
Production uses `POKER_ORIGIN/auth/callback` with HTTPS. Only `identify` is requested.

```sh
python -m poker check
python -m poker migrate
python -m poker serve
```

`check` validates configuration and prints the actual SQLite version. It does not
validate credentials, phone support, HTTPS or guild access. `migrate` explicitly
initializes schema 1 then upgrades through schema 4 in explicit transactions; it preserves existing accounts and refuses
unknown versions. Stop the service before migrating. All entry points take the
same OS exclusive lock, so a second worker or migrator fails before using the DB.
`Ctrl+C` stops both listeners and drains the writer. The OS releases the lock on
process death; do not delete the lock file. Health: `GET /health` on port 8765.

Both listeners bind **127.0.0.1**. The later deployment ticket must forward only
port 8765 through HTTPS, never 8766. Access logging is disabled so callback query
codes do not reach logs. Configure the eventual proxy the same way. Credentials
and OAuth tokens stay on the server; only a hashed local session token is stored.
Cookie: HttpOnly, SameSite=Lax, Secure under HTTPS, no Domain. The browser cookie
has a 400-day retention limit; local sessions have no daily or Discord-token TTL.
Logout or confirmed revocation invalidates every session for that account.

## Reproducible local TEST demonstration

This mode uses a simulated Discord boundary and is **not real OAuth acceptance**.
It is a separate entry point, explicitly gated by `POKER_ENV=test`; production
rejects mock transports and automatic test initialization. It binds loopback only.
Use a fresh disposable directory for each scenario and do not supply real tokens.

```sh
export POKER_ENV=test
python -m poker.demo --data-dir /absolute/private/demo-full
# In a browser open http://127.0.0.1:8765 and click Discord login.
# The simulated account starts with 50,000 and cannot claim a subsidy.
```

Stop it, then demonstrate eligibility in a different disposable directory:

```sh
python -m poker.demo --data-dir /absolute/private/demo-low --eligible
```

The second scenario records an explicit test admin debit to 1,000. Claim 4,000,
then verify a second claim is unavailable. Logout, login, stop and restart: the
opening debit and initial gift do not repeat. The page labels TEST mode. On
PowerShell use `$env:POKER_ENV='test'` and a Windows absolute data directory.

## Public boundary

- `GET /auth/login`, `GET /auth/callback`: one-use, ten-minute OAuth state bound to
  a separate browser cookie, authorization code exchange, then Bot guild lookup.
- `GET /api/account`: authenticated balance projection and subsidy eligibility.
  All Discord IDs and amounts are decimal strings; the frontend formats with BigInt.
- `POST /api/subsidy`: JSON `{ "command_id": "unique-intent-id" }`. Origin must
  equal configured origin. Both session revalidation and subsidy commit occur in
  the writer transaction. Every accepted or rejected command replays its result.
- `POST /auth/logout`: same-origin; revoke all devices, retain assets/history.
- `WS /ws/presence`: authenticated same-origin table-interface attachment for the
  next game ticket. Server assigns connection ID. Send `{"type":"heartbeat"}`
  every 30 seconds; `{"type":"leave"}` explicitly ends interface presence.
  This is not a seat or action-control channel. The account page never attaches it.
  Transport disconnect gets 120 seconds; silent heartbeat loss gets 30 seconds
  detection plus 120 seconds grace. Each device has a separate authenticated row.
  Revocation is rechecked on each message and every one second while idle.

The page renders login, available/table/in-flight/settled balances, eligibility,
claim result, errors, retry and logout. No user identity or chip amount is taken
from an unauthenticated browser command.

## Transaction contract for the next game ticket

Use `await store.command(command_id, kind, **payload)` **inside the game service**.
Bot/NPC processes use their bounded APIs and never open this store.
Public browser routes cannot submit arbitrary engine commands.

| Kind | Payload and effect |
| --- | --- |
| `buy_in` | `user_id, table_id, amount`; move available to table; one table/account; resulting stack 2,000-10,000; no active hand |
| `leave` | `user_id`; return remaining table stack only outside an active hand |
| `start_hand` | `hand_id, table_id, players, snapshot`; lock 2-6 funded participants, at least one human; recheck human sessions; atomic participant persistence |
| `bet` | `hand_id, user_id, amount`; table to pot, preserve settled assets |
| `settle` | `hand_id, payouts` mapping IDs to decimal strings; optional final `snapshot, opportunities`; sum payouts must equal contributions; atomically update ledger, terminal hand, statistics and Time Bank hand progress |
| `void` | `hand_id`; return every contribution once, retain unrelated adjustments, no statistics/Time Bank rewards |
| `action`, `time_bank` | `hand_id,user_id,opportunity_id`; persist a 20-second action deadline or atomically spend 5 seconds and extend the saved deadline, at most four times per opportunity; active human participants only |
| vent | `hand_id, expected_version, snapshot`; persist the next version and event before acknowledgment |
| `subsidy` | `user_id`; no active hand or recovery funds; available+table strictly below 5,000; once per Taipei 04:00 day |
| `adjust` | `user_id, amount` (signed string), `actor, reason`; audited admin change, no negative balances |
| `npc_supply`, `npc_reclaim` | `user_id` prefixed `npc:`, positive `amount, actor, reason`; explicit system funding/recovery of idle NPC table stack |

These are accounting contracts, not a poker rule engine. The next ticket must
validate legal turn, legal wager, control endpoint, table capacity, invitations,
side pots, hand privacy and version before calling the money boundary. It must
serialize table commands with this writer. Snapshots/events are private service
records and are not sent to browsers. Persisted invitations and admin audit tables
are extension points; table-management permissions remain separate from funds.

Money is Python integer / SQLite INTEGER, bounded 0..9,000,000,000,000,000 per
balance; no float money input. Insufficient amounts reject the whole transaction.
Commands use a canonical payload fingerprint and immutable outcome; reused IDs
with changed payload reject. A savepoint rolls back failed money changes while
preserving the rejection outcome. Gift and external system sources are distinct
ledger categories; database triggers prevent ledger updates/deletions.

One executor thread is the single write queue, including auth/presence/snapshot
changes. WAL, synchronous FULL and foreign keys are enabled. Synchronous SQLite
work is off the event loop. A cancellation does not interrupt a submitted commit;
retry with the same ID. Active hands persist through restart and freeze subsidy
eligibility. The next engine should recover `store.hand(id)` and events; if it
cannot recover, issue one `void` command. A settled hand cannot be refunded.
Corrupt/unverifiable contributions must stay frozen for investigation, never guessed.

Each valid settlement records opportunities and net result for each dealt human,
including folded players. It advances a persisted modulo-10 progress counter and
adds 5 seconds every ten valid hands, capped at 60 seconds. Void hands add neither.
Action timing decisions and gameplay are the next ticket; no full game is
claimed here. Action-clock rows and hand/event snapshots hold action deadlines and spending
state, alongside the account Time Bank field, for that integration. Each hand command increments its version; optional `expected_version` and `snapshot` join money changes in the same transaction. `store.hand(id)` returns the snapshot, ordered events and action clocks for recovery. Replayed HTTP subsidies return the frozen original result; use GET /api/account for the latest projection.

## Eligibility worker

At Taipei 04:00, one durable day snapshot selects accounts with active sessions.
On startup after downtime it creates/resumes the current eligibility day once.
It does not replay older days. Presence/120-second grace skips that account for
the day, even waiting/sitting out/folded/all-in. Skipped accounts are never appended
back when they leave. Each account records verified, skipped, revoked or retry.

Discord queries happen outside SQLite transactions. Before lookup and before
revocation commit, the same writer checks presence and presence/login generation;
a new attachment or re-login during lookup prevents stale revocation. Only 404
Unknown Member (10007) **and** a successful Bot guild lookup permits revocation.
401/403, Unknown Guild, 429, 5xx, timeout and malformed errors retain sessions.
Requests are serialized; Retry-After / exhausted bucket headers defer further
requests. Durable job retry backs off from 60 seconds to one hour, with status
and attempt logs containing no tokens. Interrupted checking rows resume as retry.

## Bot integration

`poker.bot_client.PokerClient` is an optional adapter for the existing Bot.
It only calls loopback HTTP, with deadlines; it has no database write capability.
The optional Bot integration now registers the three poker queries documented in [STATISTICS.md](STATISTICS.md).

- `GET /accounts/{id}` and `GET /scans`: reader bearer credential.
- `POST /adjustments`: separate funds bearer credential plus `X-Actor-ID` in the
  configured funds whitelist; body has `command_id,user_id,amount,reason`.
- The trusted Bot must take actor ID from the authenticated Discord interaction,
  never a user-supplied actor argument. The server rechecks the whitelist.
- Remote clients, browser Origin headers, wrong role/credential are rejected.
- Bot failure does not stop game processes or existing sessions.

## Verification

```sh
cd poker_web
npm ci
npm run build
cd ..
python -m pip install -r poker/requirements-dev.txt
python -m unittest discover -s poker_tests
python -m mypy --check-untyped-defs poker
```

The dev requirements add mypy and ruff; neither is a runtime dependency. The runtime test starts both actual listeners and checks the built static homepage, so build the frontend before running the suite.
Tests use temporary real SQLite databases and HTTPX's external Discord boundary.
They cover concurrent/repeated login, subsidy concurrency and 04:00 rollover,
failed/replayed commands, transfer/settlement conservation, void recovery,
subprocess kill/replay, state/Origin checks, API errors, session revocation races
and internal credential/role isolation. Existing Bot tests run separately via
`python -m unittest discover -s tests` (database integration tests may require their
existing explicit test environment).

### Remaining real-device acceptance

No real Discord credentials, stable HTTPS endpoint or Termux phone were supplied.
Actual guild permissions/OAuth callback, Termux dependency installation and SQLite
build, cookie behavior across devices, phone restart/storage-failure drills and
full gameplay are **not verified** by mocks. Deployment/backups/restore drills,
HTTPS forwarding and the actual game/NPC engine belong to subsequent tickets.
Check the phone's SQLite build against current official WAL release notes before
production. The 15-minute consistent backup and encrypted computer export policy
is a deployment requirement, not implemented or claimed by this foundation.

Sources: [issue #22](https://github.com/icez114514/icez-discord-bot/issues/22),
[Discord OAuth](https://docs.discord.com/developers/topics/oauth2),
[Discord guild API](https://docs.discord.com/developers/resources/guild),
[SQLite WAL](https://sqlite.org/wal.html),
[FastAPI WebSockets](https://fastapi.tiangolo.com/advanced/websockets/).