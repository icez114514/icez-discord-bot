# Table presentation (issue #31)

Review base: `ac27093c9b393d0969e32a777ff6a60dd044ebc7`.
Verified on Windows, 2026-09-16. No deployment is included.

## Public contract

Authenticated table projections include `event_seq`, `server_time`, and the last
256 `events`. Each event has a durable table-local `seq`, stable `id`, server
`at` time, and `kind`. Hand events also carry `hand_id`. These records are
persisted atomically with the table and account transaction; HTTP replies and WS
projections reuse their identity. They contain no deck, private cards, control
token, or private snapshot.

- `action`: player `user`, normalized action (including opening `bet`),
  decimal-string incremental `amount`, street `raise_to`, and `all_in`.
- `collect`: per-player decimal-string `amounts`. These bets are already
  included in the authoritative hand pot; collection never increases it.
- `deal` / `board`: confirmed dealing boundaries; board events include only
  public community cards.
- `payout`: player, exact amount, and stable `pot_id`.
- `refund`: player, amount, and `uncalled` or `void` reason.
- `turn` / `bank`: player, hand and turn identity.
- `topup`: player and completed amount, emitted only after success.

Hand `settlement` exposes ordered pots with amounts, winners, and each player's
exact `awards`, including odd chips allocated by the existing server loop.
Refunds are separate. The existing `payouts` total continues to include refunds
for compatibility. Neither figure is the player's net hand profit. Historical
settlements without recorded per-pot awards return no detailed settlement rather
than estimating an allocation. Recovery builds void refund details from the
verified contribution ledger, never a damaged hand snapshot.

## Client behavior

The shared consumer runs at transport ingress, before React batching. First
load, reconnect, background changes, table changes, missing ranges and records
older than three server seconds establish a silent baseline. No snapshot
difference is used to guess intermediate actions. Presentation queues are
bounded to about 2.2 seconds; animation does not update balances or deadlines.

Chip travel lasts 280 ms; action labels last 1.4 seconds. WIN appears at payout
arrival for 1.2 seconds, once per hand/player. Additional pots still travel;
refund-only receipts never produce WIN. Changing hand, table or seat roster
clears transient effects. Device reduced-motion settings and the saved option
both disable travel/pulse animation.

Audio preferences use `poker-sound:v1:<account>` in local storage, with an
in-memory per-account fallback. Master gain, four category gains, mute and
reduced motion are saved. Preview is local and obeys all gains/mute. Gesture
unlock preloads the existing licensed audio files; check/collection/refund and
interface cues reuse these assets at distinct rates. Six concurrent voices
reserve capacity for reminders; newer settlement cues can replace older
settlement/general voices, while reminders retain priority. Loads taking over
600 ms do not replay late. Settings display the last audio diagnostic.

## Verification

| Check | Result |
| --- | --- |
| Full `poker_tests` unittest discovery | 94 passed |
| Full existing Bot `tests` discovery | 162 collected, 103 passed, 59 opt-in database tests skipped |
| Frontend `npm test` | 12 passed |
| TypeScript + Vite build | Passed |
| Ruff on changed Python source/tests | Passed |
| Mypy on changed server modules with imports skipped | Passed |
| Browser acceptance | Passed; actual headless Chrome and Web Audio |
| Standards / spec reviews | No unresolved findings |

The repository-wide `mypy --check-untyped-defs poker` check reports 15 existing
errors in four unchanged files: `statistics.py`, `management.py`, and the two
vendored FullHouse modules `features.py` / `bot.py`. These are outside this change.

Run the presentation browser check from the repository root after building
`poker_web`:

```powershell
rtk proxy node poker_tests/presentation_browser.mjs
```

It starts an isolated loopback test server and hidden Chrome profiles. Real
rules-engine public recordings drive a browser-only transport fixture. It checks
multi-player collection, main/two side pots, a refund-only recipient, a single
player winning multiple pots, duplicate delivery, combined board/settlement/refund
audio identities, mute/preview, preference reload, slow cold audio loads, silent
background/reconnect baselines, and reduced motion. Screenshots cover action/WIN
states in all three themes at 1440, 390 and 320 px. Reports and screenshots are
written to `tmp/issue31-browser`; the server and browser processes are cleaned up.

HTTP/WS integration tests separately exercise the real service transaction,
replayed commands, contribution amounts, public privacy, and durable void refunds.
The rule tests verify exact split/odd-chip and side-pot awards. Browser login uses
the existing simulated Discord transport; real Discord OAuth and physical-device
speaker output were not tested.
