# Poker table UI acceptance

The existing classic walnut, midnight oak and burgundy leather palette tokens are unchanged. The reference image guides the table layout, overlapping circular seat plaques, hero cards/countdown, central pot/board and lower-right betting controls. The existing six-seat limit remains unchanged. Portraits use local symbols because table projections do not expose Discord avatars.

Bet presets are raise-to totals: own contribution + call + fraction of the pot after calling, clamped to the server's legal minimum/maximum. A short stack below the minimum can only choose its all-in total. Every all-in still requires confirmation. Off-turn, expired, disconnected, frozen and non-controlling clients cannot act. All monetary calculations use integers.

Audio uses local Kenney Casino Audio and Interface Sounds files under CC0; sources and original license files are in `poker_web/public/assets/audio`. Effects cover dealing, chips, folding, checks, own-turn prompts, timebank use, final-five-second ticks and settlement. User interaction unlocks browser audio. Mute persists locally; background pages, repeated projections and reconnect baselines do not replay events. Failed audio never blocks a command.

Table options retain themes, top-up, sit-out, departure and host actions. Bottom-left information shows the current hand and up to 80 publicly observed session events; this is not a complete server-side historical hand archive.

Verification:
- `npm --prefix poker_web run build`: TypeScript and Vite pass.
- `npm --prefix poker_web test`: 7 betting/audio tests pass (Node 22+ with type stripping).
- `node poker_tests/ui_acceptance.mjs`: isolated test server + real headless Chrome; six seats, illegal raise rejection, preset bounds, all-in confirmation, audio decoding/playback, persisted mute, three themes and 390/320px overflow checks.
- `poker/.venv-deploy/Scripts/python.exe -m unittest discover -s poker_tests -q`: all 83 tests pass.
- Screenshots and isolated test databases stay under project-local `backups/poker/` (ignored).

Standards review and spec review: no unresolved findings after fixing legacy CSS duplication and adding accepted-check audio coverage.
