# Issue #32: personalized betting and reconnect safety

Baseline: `c1c0a53605df09ab388c35a6ce4fe17365ed4869`.
Implementation: `b5abb53`, followed by the numeric all-in confirmation fix.

## Behavior and contracts

- Public table state carries string-valued `rules.small_blind` and
  `rules.big_blind` from the same constants used by the game engine.
  `hand.call_amount` is the viewer's current capped call, including when
  another player acts; it is not permission to act.
- Only the viewer's table stack toggles BB display. BigInt division preserves
  arbitrary integer precision, uses at most two decimals, and marks rounded
  values with an approximation sign. The button's accessible name/title gives
  the original integer. Invalid or absent blinds display the original amount.
- Five preflop BB presets and five postflop pot presets only populate the draft.
  Fractional chips round down before clamping to authoritative raise-to limits.
  All-in confirmation compares numeric values, including leading-zero input.
- Versioned device preferences are isolated by account. Invalid or unavailable
  storage falls back safely; persistence failure does not block play.
  Four-color and large-card styles apply to the shared live/replay card renderer.
- Preselection is bound to table, hand, street, control endpoint, fixed call
  amount, and the public event sequence. Other players' normal turn increments
  preserve it. Relevant state changes, missing event continuity, own actions,
  replay entry and disconnect clear it. An all-in call never auto-executes.
- A socket opening is only a transport connection. Its ready snapshot establishes
  synchronization; HTTP acknowledgements never establish current control.
  Pending requests block new intents. Retries reuse the original object,
  command ID, control token and body. A request timeout leaves the result unknown.
- Revoked/stopped connections cannot be revived by delayed messages. Visible
  connection feedback is immediate; polite assistive announcements stabilize
  for 1.5 seconds to avoid announcing brief connection flaps.
  Deadlines use server time; existing server timeout and accounting rules remain.

## Verification

- `poker/.venv/Scripts/python.exe -m unittest discover -s poker_tests`:
  101 passed.
- `.venv/Scripts/python.exe -m unittest discover -s tests`:
  162 collected, 103 passed, 59 existing opt-in database tests skipped.
- `npm --prefix poker_web test`: 19 passed.
- `npm --prefix poker_web run build`: TypeScript and production build passed.
- `mypy poker --follow-imports=silent --ignore-missing-imports --exclude vendor`:
  passed, 31 modules; Ruff F checks for changed Python files passed.
- `node poker_tests/personalization_browser.mjs`: passed. Covers exact huge
  amounts, unknown blinds, draft-only/custom presets, pot sizing, legal limits,
  expired turns, short/leading-zero all-ins, fixed call/check preselection,
  normal turns, invalidation, replay isolation, lost acknowledgement, exact
  retry, transport-open-before-ready, terminal states, preference persistence,
  and actual hit-target checks at 1440/390/320px across all three themes with
  large text/cards. Screenshots and machine-readable results are written to
  `tmp/issue32-browser`; the 320px screenshot was visually inspected.
- `node poker_tests/replay_browser.mjs`: existing real-service replay suite passed,
  including privacy, live deadlines, return to live state and no replay commands.
- `git diff --check`: passed.

The new browser suite uses scripted transport faults/public state and simulated
Discord login. Public-state serialization and idempotency are covered by backend
integration tests; existing replay acceptance uses the real local service.
This is not physical-phone or production Discord OAuth acceptance. No deployment
was performed.

## Review

Independent Standards review: no findings.
Independent Spec review found a leading-zero all-in confirmation bypass. The
browser regression failed before the numeric comparison fix and passed after it.
