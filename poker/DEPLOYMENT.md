# Local deployment and Termux handoff (#26)

This delivery implements local operation tooling. Windows tests are not phone,
real-browser OAuth, Discord message-delivery, or two-hour load acceptance.
Do not close #26 until the outstanding acceptance matrix below has evidence.

## Runtime and configuration

Use the separate poker environment; never migrate the crystal Bot database.
The desktop deployment runtime is Python 3.12.14 / SQLite 3.53.1.
Production check/migrate/serve reject known pre-fix WAL builds. Accepted lines:
SQLite >=3.51.3, 3.50.7+, or 3.44.6+ within those maintenance branches.
[SQLite WAL release guidance](https://sqlite.org/wal.html).

From the repository root on Windows:

    poker/.venv-deploy/Scripts/python.exe -m poker check
    poker/.venv-deploy/Scripts/python.exe -m poker migrate
    poker/.venv-deploy/Scripts/python.exe -m poker serve

Install pinned runtime dependencies with -r poker/requirements.txt. The desktop
build is cd poker_web, npm ci, npm run build. No Node server runs in production.
The optional .python download and .venv-deploy folders are excluded from Git.

The CLI reads only the repository-root .env (UTF-8/BOM supported), with environment
variables taking precedence and interpolation disabled. --env-file explicitly
selects another file. Test subprocesses using POKER_ENV=test do not auto-load it.
Existing APPLICATION_ID, CLIENT_SECRET, DISCORD_TOKEN, DISCORD_GUILD_ID are
fallbacks for POKER_CLIENT_ID, POKER_CLIENT_SECRET, POKER_BOT_TOKEN, POKER_GUILD_ID.
Explicit POKER values win. The web service never imports the crystal Bot.

Set POKER_ORIGIN=https://poker.ice-z.net and register the exact Discord callback
https://poker.ice-z.net/auth/callback. Separate table/account and funds allowlists:
POKER_TABLE_ADMINS and POKER_FUNDS_ADMINS. Local configuration assigns both to the
user-selected account. POKER_READER_TOKEN and POKER_FUNDS_TOKEN must differ.
Secrets are never included in committed examples or emitted by check.

POKER_BACKUP_DIR and POKER_EXPORT_DIR are absolute paths. The local user-selected
destinations are backups/poker/snapshots and backups/poker/exports under the
repository. They are ignored by Git and never served by the static-file route.
The live DB remains POKER_DATA_DIR/poker.db in a private user-home directory.
On Windows restrict the backup/data/config ACLs to the operating account and
SYSTEM. POSIX directories use 0700, snapshot/export files 0600. Do not put
plaintext backups in Android shared storage.

## Tunnel

Use a dedicated icez-poker tunnel on the machine running the service.
Published hostname poker.ice-z.net, empty path, service http://127.0.0.1:8765.
Never forward 8766. Preserve HTTP and /ws/table WebSocket traffic, disable
request/query/body logging, and never log OAuth callback codes or invitations.
Use the existing domain; no domain purchase or paid service is authorized.
The tunnel only carries traffic; game, SQLite, and fixed NPC run locally.

When moving to the phone, drain/stop the desktop, take a final consistent backup,
restore on the phone, and move this tunnel's connector. Do not run two separate
game databases behind replicas of the same tunnel. Other desktop tunnels remain
independent. The hostname and OAuth callback do not need to change.

## Backup and restore

Startup schedules a consistent SQLite backup immediately, then every 900 seconds.
Failures retain prior backups and retry in 60 seconds. Backups use sqlite3.backup
on the serialized writer outside transactions; they include committed WAL data.
Snapshot integrity, foreign keys, and balances versus the immutable ledger are
checked before publication. This verification detects discrepancies, not every
possible game-level corruption. Unknown contributions remain frozen by recovery.

Retain all successful snapshot-* files from the last 24 hours and seven separate
daily-YYYY-MM-DD files (UTC). Daily snapshots are the first successful snapshot of
each available day; downtime does not invent missing days. upgrade-* files are
manual rollback anchors and are not pruned. No cloud upload occurs.
Snapshots contain sessions and private game state: do not publish them.

While running:

    python -m poker backup --actor YOUR_FUNDS_ADMIN_ID
    python -m poker status

The CLI contacts the authenticated loopback endpoint. If the listener is absent,
backup opens the stopped store with its exclusive lock. It never bypasses an
occupied lock. status reports last backup time/error. A 15-minute RPO is a target
only while successful snapshots stay within that age; errors/downtime violate it.
Whole-device loss recovers only as far as the last manually saved export.

Export a completed snapshot interactively (password is never an argv argument):

    python -m poker export --source backups/poker/snapshots/SNAPSHOT.db --destination backups/poker/exports/EXPORT.enc
    python -m poker decrypt --source backups/poker/exports/EXPORT.enc --destination backups/poker/exports/RESTORED.db

Use a unique strong passphrase, at least 12 characters, and store it separately.
Encryption uses Scrypt (N=131072,r=8,p=1), random 16-byte salt, AES-256-GCM,
random 12-byte nonce, authenticated version/header, and a 16-byte tag.
Processing streams in 1 MiB chunks; KDF needs about 128 MiB. Authentication must
succeed before plaintext is published; wrong passwords, tampering and existing
destinations fail without replacing anything. Filesystem hard links are required
for atomic no-overwrite publication (NTFS/ext4 supported).
Save the printed SHA-256 along with the export. After decrypt, obtain the
plaintext SHA-256 for the restore input. Retain it in the operator's drill record.

Restore always targets a NEW empty data directory, even during rollback:

    python -m poker restore --source backups/poker/exports/RESTORED.db --destination ABSOLUTE_PRIVATE_NEW_DATA_DIR --sha256 TRUSTED_PLAINTEXT_SHA256

An existing database or WAL is refused; the live service's OS lock is respected.
Restored data starts in maintenance. Point POKER_DATA_DIR at the restored
directory, select its matching code release, explicitly migrate if required,
start, check status and verify accounts/ledger/hands/Time Bank/sessions/themes/
statistics before resume. No refund is guessed; frozen tables require investigation.
The restore command does not itself log in players or settle/replay hands.

## Controlled upgrade and rollback

1. Record the current Git SHA, dependency lock, model hashes, schema and paths.
2. python -m poker drain creates a durable maintenance marker. It stops new joins,
   table creation, NPC admission and new hands. Current hands/actions continue.
3. Poll python -m poker status until active_hands=0. Frozen/unresolved hands block
   the upgrade; investigate instead of forcing a refund or deleting the marker.
4. Stop the service (Ctrl+C); the writer drains and the process lock is released.
5. Take a final backup. Keep its SHA-256 and the old code release together.
6. Install the selected release and dependencies, rebuild static files. Run check,
   then migrate. Existing DB migrations create an additional verified upgrade
   snapshot under the lock BEFORE schema changes and refuse active hands.
7. Start the service. Maintenance persists on failure or restart. Verify status,
   NPC ready, backup success, /health, accounting and browser behavior.
8. python -m poker resume requires no frozen tables, an available NPC, and a
   successful backup no older than 900 seconds. It explicitly restores admission.

On failure leave maintenance enabled. Do not merely downgrade code across a
schema change: stop, restore the matching pre-upgrade database to a fresh private
directory, select the matching old release, and verify before resuming.
Replayed intent IDs and terminal hand settlements are preserved by full snapshots.
Upgrade backups are retained until the operator deliberately retires them.

## Observability and phone operation

/health is public and intentionally minimal. /operations and /scans exist only
on 127.0.0.1:8766 behind the reader token; backup mutations require the funds
credential and funds allowlist. No cards, decks, invitation tokens, session tokens,
or credentials are included in operational output.

Command p95 covers the last 10000 table-create/table-command calls, from writer
queue admission through transaction completion. Includes rejected/replayed calls;
excludes external network, player waiting, and asynchronous NPC inference.
writer_p95 is a separate broad metric including reads and backups. Snapshot work
can increase queued command latency, so include scheduled snapshots in load tests.
NPC counters expose decisions, timeouts and failures. Process CPU is cumulative
service CPU seconds; it excludes the separate NPC process. Measure that process
and OS-wide CPU/RAM with the phone's own tools too. Linux/Android RSS comes from
/proc/self/status; unavailable readings are null. Accessible thermal zones are
reported with their kernel names/types; blocked readings are absent.
Clock metrics track maximum loop delay and wall-clock step against monotonic time,
not absolute NTP accuracy. Validate absolute clock offset separately.

    python -m poker.monitor --output backups/poker/phone-two-table.jsonl --duration 7200 --interval 5

This only records measurements; humans must actually play in two independent
browsers with fixed NPCs on BOTH active tables. It does not assert acceptance.

On Termux: record getprop ro.build.version.release, termux-info, /proc/meminfo,
python --version, and python's sqlite3.sqlite_version; do not infer RAM from model.
Keep code/data under Termux private HOME. Install compatible pinned NumPy/eval7/
cryptography builds, verify model hashes with check, and run fixed NPC startup.
Native dependencies and compilation on Android remain a real-device check.
Only three pinned upstream bot modules, two NPZ files and LICENSE/NOTICE ship;
exclude tests/prototypes/caches/other bots/pickle/training/competition assets.
See vendor/fullhouse/NOTICE.md for source revision, licenses and hashes.
The current subprocess has the same OS identity as the service: separate OS
isolation of the NPC on Android is NOT verified and must not be claimed.

Use termux-wake-lock, disable Android battery optimization for Termux, and retain
a foreground notification. Use termux-services or a persistent terminal session
to supervise the game and cloudflared separately; terminate via drain then Ctrl+C.
On network loss, inspect tunnel reconnect and /health; do not start a second game
worker or delete poker.lock. Boot/force-stop recovery and thermal throttling need
physical-phone drills. Unlock wake lock with termux-wake-unlock after stopping.

## Outstanding acceptance evidence

For each scenario save date, Git SHA, device/runtime, procedure, actual result,
metrics and limitations. No row below is marked passed by simulated identities.

- Real browser OAuth callback, correct guild admission/rejection, daily Taipei
  04:00 scans and Discord API failures, revoke-all sessions, and role isolation.
- Actual Discord slash-command delivery and web/public/private statistics parity
  (requires explicit user authorization before sending messages).
- Two active tables for >=2 hours on the phone, <=6 seats each including fixed
  NPCs, independent real browsers; command p95<200ms, NPC timeout<1%, no accounting
  errors or crash. Record CPU/RAM/temperature/clock measurement scope.
- Network disconnect, Android force-stop, disk-full, stuck NPC, transaction
  interruption, valid/corrupt snapshots, and unverifiable contributions.
  Recovery target <=5 minutes or verified safe refund; unknown funds stay frozen.
- Full restore drill comparing ledger, hands, Time Bank, sessions, themes, stats;
  upgrade failure stays in maintenance and rollback does not double settle.
- Subsidy concurrency, multi-window controller, invitation invalidation, capacity,
  close during a hand, all-in offline entitlement, restart without redeal.
- Same-table M/N/O themes, switch without timer/input reset, login preference
  persistence, clear red/black cards, mobile/desktop controls, and no other
  player's unrevealed cards in network traffic or logs.
