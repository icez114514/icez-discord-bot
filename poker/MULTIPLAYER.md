# Multiplayer and appearance (#24)

Extends the #23 table authority and real hold'em engine. See [GAMEPLAY.md](GAMEPLAY.md)
for money, action clocks, recovery, NPC isolation and authenticated presence contracts.

## Upgrade

Stop the service and run `python -m poker migrate` before restarting. Schema 3 adds
`account_preferences`; schema 1/2 money, sessions, hands and command records are
retained. Normal startup rejects old schemas. Build `poker_web` with `npm run build`.

Existing `main` tables remain playable. New tables have server-generated IDs.
The single SQLite writer checks capacity, creates the table and debits the buy-in
in one transaction. At most two tables with reserved seats or an unfinished hand
are active. Empty created tables close after the final human's hand settles;
remaining NPC stacks return to the system ledger. A closing hand still consumes
capacity. Six physical seats include NPCs; a human replacing an NPC waits for the
same seat at the next hand boundary.

## API

All endpoints require the existing authenticated session. Mutations require the
same-origin header. No observer endpoint is provided.

- `GET /api/tables`: public table summaries and the caller's current table ID.
- `POST /api/tables`: `{command_id, name, private, amount}` creates and joins once.
  Replay the original payload after uncertain delivery; a new intent needs a new ID.
- `GET /api/table`: resumes the account's own table. An optional `table_id` queries
  admission status. Private admission additionally needs `X-Table-Invitation`.
  Nonmembers receive no roster, hand or cards.
- `POST /api/table/commands`: extends the existing command with a variable `table_id`
  and optional `invitation` for private joins. Existing version/control validation
  and durable replay behavior are retained.
- `WS /ws/table`: attaches to the account's current table and retains the existing
  single-controller, personalized projection, heartbeat and departure behavior.
- `GET /api/table/invitation`: private host only; returns the current invitation.
- `POST /api/table/invitation`: private host and current controller only;
  `{command_id, control}` rotates once. Prior links immediately fail admission.
- `GET /api/preferences` and `PUT /api/preferences` (`{theme}`): account-only visual
  preferences. Unknown values fall back to `classic_walnut`. These writes do not
  touch table versions, hands, money, clocks or presence.

Invitation links use `/#invite=<table-id>:<secret>`. The fragment does not enter
HTTP access logs. The UI submits the secret in a header/body; it is not included
in lobby summaries or table broadcasts. Existing seated members remain admitted
when a host rotates the link. Invited users still need a valid Discord login.

## Frontend integration

`ThemeProvider` wraps the common application container and uses CSS custom
properties on the document root. `ThemePicker` works in account settings and in
the live table without remounting it. #25 can place statistics/navigation content
inside this provider and reuse `Modal` and the shared theme variables.

The only themes are 典藏胡桃 (`classic_walnut`, default), 墨藍橡木 (`midnight_oak`)
and 酒紅皮革 (`burgundy_leather`). Preferences persist per account. Saves are
serialized; failure retains the current display and shows a retry message.

The approved reference is the local commit
`cc47ab4ae17614a198a34f9c0500201a1e57753e`,
`docs/prototypes/poker-j-club.prototype.html`. It was available locally during
implementation; this task does not claim that prototype branch was published.
Production materials, previews, table perspective and card artwork use CSS and
text symbols with no external image assets or dependency on untracked prototypes.
Cards keep #FFFEFB / #14191E / #C51E32 across all themes.

## Reusable verification

- `poker/.venv/Scripts/python.exe -m unittest discover -s poker_tests`
- `poker/.venv/Scripts/python.exe -m mypy poker --follow-imports=silent --ignore-missing-imports --exclude vendor`
- `poker/.venv/Scripts/python.exe -m ruff check poker --select F --exclude vendor`
- `npm --prefix poker_web run build`
- `node poker_tests/browser_acceptance.mjs` (Windows Chrome and Node with native
  WebSocket support). Uses isolated temporary profiles and a loopback test server;
  only Discord OAuth responses are simulated. The production engine, ledger,
  network, NPC and client run normally. Screenshots go to `tmp/issue24-browser`.

API tests cover atomic capacity races, private invitation invalidation, card
projection, account preference isolation, command replay and two active hands
through restart, in addition to the existing gameplay suite. The browser harness
covers two independent sessions, real settlements, personal themes, all-in
confirmation, failures, reconnect, public/private entry and 320/390px layouts.

Real Discord OAuth, physical phone/Termux load, production HTTPS and deployment
remain #26. No external service deployment or GitHub issue closure is implied.
## Review and validation record (2026-09-16)

Baseline: `62ca0224b6a8bfd7a752d72392403d02f43d3e38`.
Implementation: `434b4df`; reviewed fixes: `de4951e`.

- Full Poker suite: 50 passed. After consolidating capacity admission, all five
  lobby API tests passed again.
- Existing Bot suite: 160 collected, 101 passed, 59 opt-in database tests skipped.
- TypeScript/Vite production build, mypy (20 service modules), Ruff F checks and
  `pip check` passed.
- Standards review: no documented violations. Both low-priority suggestions
  (duplicate admission rules and player-name formatting) were resolved and rechecked.
- Spec review: fixed stale public-table admission retry. The dialog now adopts
  the returned table version, retains the buy-in input and requires confirmation.
  Its browser regression first reproduced the failure, then passed with the fix.
  Independent recheck found no remaining material Spec findings.
- Final Chrome acceptance passed on the reviewed implementation: three consecutive
  real settlements with two independent identities; all three themes; 320/390px
  six-seat layouts with board-overlap and horizontal-overflow assertions; private
  invitation rotation and old-link rejection; stale admission reconfirmation;
  failed topup; failed theme save; all-in confirmation/settlement and bankrupt
  return when applicable; same-hand navigation recovery and live transport reconnect.
- A third browser with the same account was correctly denied operation. The second
  device then stayed offline for the real 120-second grace (no accelerated clock);
  its seat expired and both table chips and in-flight chips returned to zero.
  HTTP/WebSocket projections contained no other unrevealed cards or full deck,
  and there were no JavaScript page errors. Desktop and phone-width screenshots
  were visually inspected. Discord identity remained explicitly simulated.
