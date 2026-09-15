# Issue #23 implementation notes

This work adds a minimal single shared table at /api/table. Full multi-table lobby,
private-table invitations, mobile art and deployment remain later tickets.

## Data and startup

Run `python -m poker migrate` with the service stopped before upgrading.
Schema 2 adds game_tables, game_commands and game_audit in one migration; schema 1
accounts, ledger entries, sessions and existing hand records are retained.
Normal service startup refuses the old schema instead of silently migrating it.

Install poker/requirements.txt in the independent poker environment and build
poker_web with `npm run build`. The fixed worker uses NumPy 2.2.6 and eval7 0.1.10.
Its two data files are checked against pinned SHA-256 digests at startup.

## Command contract

POST /api/table/commands accepts a strict JSON object:

- command_id: unique intent ID (reuse the entire original payload after uncertain delivery).
- table_id: main; version: latest table version; kind: requested operation.
- control: server-issued WebSocket connection ID for every operation after joining.
- act additionally requires hand_id, turn, action, and a decimal-string amount for raise.
- join/topup require a decimal-string amount. remove_npc requires npc_id.

Kinds: join, act, topup, sitout, sit_in, leave, add_npc, remove_npc, close.
Amounts describe chips; raise amounts mean the total bet for the current street.
Invalid raises are rejected. Commands are authenticated again inside the writer.
Accepted and rejected outcomes are durable; responses include a separate fresh,
account-specific state. A replay never repeats a money operation.

WS /ws/table uses the existing authenticated presence records. It assigns control,
accepts heartbeats and explicit interface leave, and sends only the account's
private projection. Only the current controller can act. The connection deadline,
seat expiry and hand/action deadlines are separate records.
A not-yet-seated account receives only its join status, not table observations.

## Atomicity and recovery

The existing single SQLite writer serializes table operations. Each complete table
transition, all associated account money operations, hand events, clocks and
settlement statistics commit together. No in-memory authoritative hand survives
outside that transaction. Broadcasts read the committed state.

Startup reconciles participant contributions with immutable pot-transfer ledger
entries and current in-flight balances. Unverifiable money freezes the table for
investigation. A recoverable private snapshot keeps the original action deadline;
an unrecoverable active hand with verifiable contributions is voided once,
including all blind and folded-player contributions. Already terminal hands are
not refunded by the recovery pass. Repeated startup cannot repeat a terminal
money transition.

## Fixed NPC

See [source and adaptation notice](vendor/fullhouse/NOTICE.md).
The worker receives its two private cards, public board, public stack/betting
history and legal constraints. The process environment contains no Discord or
ledger credentials. The service owns all legality and money decisions.
The adapter preserves the upstream short-stack policy and five output classes,
while exposing errors hidden by upstream decide(). Raise history is converted to
upstream bet-to amounts, with explicit street boundaries.

The queue holds at most eight requests; the two-second request deadline includes
queueing. Bad/late output checks if legal or folds, and three consecutive failures
sit the NPC out next hand with visible status. A timed-out process is stopped so
a stale reply cannot be reused. A service restart reloads the fixed runtime.

A local subprocess does not provide a full OS sandbox. Deployment must separately
deny the worker identity access to private ledger files and service credentials.
This change does not claim phone validation, real Discord OAuth acceptance,
model-strength evaluation, GTO proof, or production deployment.

## Verification (2026-09-16)

- All 45 poker tests passed with the dedicated Python 3.10 environment.
- Existing Bot suite: 160 collected, 101 passed, 59 opt-in database tests skipped.
- TypeScript/Vite production build passed.
- mypy checked 18 service modules; Ruff F checks passed; pip check passed.
- Real headless Chrome completed a human/fixed-NPC hand, displayed a 400-chip
  settlement and persisted remaining stacks; no JavaScript page errors.
  Table screenshot was inspected. Discord identity was explicitly simulated.
- Rule tests cover roster validation, heads-up position, short blinds, cumulative
  short-all-in reopening, multiple side pots, uncalled refunds, odd chips and ranks.
- HTTP/WS tests cover two identities, card privacy, single control, illegal raises,
  four timing extensions, repeated turns, ten-hand rewards through restart,
  countdown departure, failed queued topup, seat expiry, NPC replacement/failure,
  all-in departure, committed-but-undelivered action replay, snapshot restoration,
  inconsistent clocks, void refunds and unverifiable-money freezing.
- This repository has no GitHub Actions workflow; no remote CI run is claimed.

Run: `poker/.venv/Scripts/python.exe -m unittest discover -s poker_tests`.
Build poker_web first because the CLI integration test serves its production files.
The runtime test stops its own Windows process tree, including the NPC worker.

## Review

Independent Standards and Spec reviews compared baseline d7e3643 with the
implementation commit 64bb5bf. Standards found no hard rule violations and one
shared-validation improvement; Spec found one NPC deadline authority gap.
Both were fixed with red/green regression tests and independently rechecked:
HTTP and WebSocket now share required-field validation, and NPC results recheck
their deadline inside the serialized write transaction before applying an action.
No unresolved Standards or Spec findings remain.
