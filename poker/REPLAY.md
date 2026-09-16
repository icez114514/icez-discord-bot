# Participant hand history and replay (#33)

Replay support starts with hands **dealt after installation of replay format 1**
(introduced 2026-09-16). The marker is written at deal time, not added to existing
hands. Existing hands, including hands already in progress during an upgrade,
remain listed but report incomplete/unsupported history. Void hands also report
that full replay is unavailable. No missing action is inferred from a final
snapshot, and this change does not backfill historical events.

The engine stores its full ordered presentation stream inside the settlement
snapshot, in the same authoritative transaction as contributions and payouts.
Format 1 includes explicit showdown and completion boundaries. The new events
contain no hole cards. Replay reads the event referenced by the unique settlement
record, checks contributions, payouts, individual pot awards, refunds, action
history and final player/board state, then returns viewer-specific frames. A
missing or inconsistent record yields an explicit incomplete response with no
frames. Neither the table's rolling 256-event buffer nor the client's 80-entry
connection log is a history source.

## Read contract and retention

- `GET /api/hands?limit=20&before=<cursor>` lists only completed hands in which
  the authenticated account participated. Default 20, maximum 50; invalid limits
  or cursors return 422. Results are newest-dealt first using persistent hand
  row IDs. `next_cursor` is exclusive and null at the end. Newer rows do not shift
  older pages. The UI offers newer/older pages and refreshes the latest hand.
- `GET /api/hands/{hand_id}` reauthenticates and checks durable `participants`
  membership on every read. Unknown, active and nonparticipant hands all return
  404; revoked sessions return 401. Leaving or closing a table does not remove
  historical participation. Responses have the application's `Cache-Control:
  no-store` policy.
- Frames disclose the viewer's own cards from deal, and other players' cards only
  starting at the recorded showdown event, excluding folded players. Private
  snapshots, remaining deck, tokens, command payloads and future public cards are
  never returned as raw events. Final summaries intentionally show lawful final
  public information; starting replay resets to the deal frame.
- Existing retention is unchanged. No TTL, automatic deletion, pruning, account
  ledger removal, audit removal, public sharing or export is introduced. Existing
  backup/restore policy covers these records. History endpoints never write game
  commands or accounting entries. No database migration is required.

## UI and live table

Both the lobby and table offer previous-hand summary/history. The summary lists
each recorded street's public actions and board, with the existing authoritative
main/side-pot awards and separate refunds. Playback has previous/next, play/pause,
street jumps and final settlement. Player stacks include receipts only as their
recorded payout/refund steps are reached.

The replay component owns its state and only issues history GET requests. It does
not pass historical frames into live presentation/audio. While the modal is open,
the existing table connection and deadline continue; live presentation effects
are suppressed and a live-turn/remaining-time notice links back to the live table.
Closing returns to the latest live state without replaying old WIN or receipt
effects. Playback pauses in a background tab and timers/requests are cleaned up
on close. There is no pause or extension of server action deadlines.

## Verification

- `poker/.venv/Scripts/python.exe -m unittest poker_tests.test_hand_replay`
  covers participant/nonparticipant reads, active-hand rejection, leaving,
  process restart, revoked sessions, pagination, incomplete/legacy evidence,
  more than 80 events, reveal timing and split main/side pots plus refunds.
- `npm --prefix poker_web run build` checks TypeScript and builds current assets.
- `node poker_tests/replay_browser.mjs` uses three isolated headless Chrome
  profiles, a temporary real service/database and simulated Discord login.
  Offline fixtures are produced through the engine and durable money commands
  before the service starts; UI history is never intercepted or fabricated.
  It verifies summaries, steps, play/pause, street jumps, lawful reveal timing,
  split awards/refunds, pagination, legacy notices, denied access, no replay
  command/audio/WIN effects, live-turn deadlines, return-to-live actions and
  reload recovery. Layout checks and screenshots cover 1440, 390 and 320 pixels.
  Evidence is written to `tmp/issue33-browser/` (not committed).

No deployment or real Discord OAuth verification is part of this change.

### Recorded result (2026-09-16)

- Poker suite: 100 passed, including six new history HTTP tests.
- Frontend unit tests: 12 passed; TypeScript and production build passed.
- Existing Bot suite: 162 tests, 59 existing opt-in database tests skipped.
- Browser acceptance: all scenarios above passed with no JavaScript exceptions;
  the 320px screenshot was visually inspected after fixing the responsive grid.
- Ruff F checks and diff whitespace checks passed. All changed files strictly
  decode as UTF-8 without BOM; existing LF/CRLF conventions were preserved.
- First-party mypy (`--check-untyped-defs --exclude poker/vendor poker`) still
  reports eight existing errors in `statistics.py` and `management.py`. Running
  the identical command against fixed base
  `75710b2c0f65677767fd9d8ee18d01a1f467cbd3` produces the same eight diagnostics;
  the new replay module adds none. Including vendored sources reports additional
  pre-existing vendor typing problems.
## Standards review

Independent review against `75710b2c0f65677767fd9d8ee18d01a1f467cbd3` found no
hard documented violations or actionable design smells. Domain terminology is
consistent and the extracted card component avoids duplicating live rendering.

## Spec review

The independent review found one completeness issue: a missing final collection
could leave nonzero street bets while history was still marked complete. Replay
now requires every final street bet to be zero. The HTTP regression first failed
without the fix, then passed with the fix; missing-action, old-version and
missing-collection cases each start from pristine evidence. Targeted independent
re-review found no unresolved requirement gaps or scope expansion.

Final review counts: Standards 0 unresolved; Spec 0 unresolved (1 finding fixed).