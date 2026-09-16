# Poker table UI acceptance

The existing classic walnut, midnight oak and burgundy leather palette tokens are unchanged. The reference image guides the table layout, overlapping circular seat plaques, hero cards/countdown, central pot/board and lower-right betting controls. The existing six-seat limit remains unchanged. Authenticated players now receive current-table Discord guild profiles through a separate best-effort endpoint. Names prefer guild nickname then username; avatars prefer guild then global then Discord default images.

Bet presets are raise-to totals: own contribution + call + fraction of the pot after calling, clamped to the server's legal minimum/maximum. A short stack below the minimum can only choose its all-in total. Every all-in still requires confirmation. Off-turn, expired, disconnected, frozen and non-controlling clients cannot act. All monetary calculations use integers.

Audio uses local Kenney Casino Audio and Interface Sounds files under CC0; sources and original license files are in `poker_web/public/assets/audio`. Effects cover dealing, chips, folding, checks, own-turn prompts, timebank use, final-five-second ticks and settlement. User interaction unlocks browser audio. Mute persists locally; background pages, repeated projections and reconnect baselines do not replay events. Failed audio never blocks a command.

Table options retain themes, top-up, sit-out, departure and host actions. Bottom-left information shows the current hand and up to 80 publicly observed session events; this is not a complete server-side historical hand archive.

Verification:
- `npm --prefix poker_web run build`: TypeScript and Vite pass.
- `npm --prefix poker_web test`: 7 betting/audio tests pass (Node 22+ with type stripping).
- `node poker_tests/ui_acceptance.mjs`: isolated test server + real headless Chrome; six seats, illegal raise rejection, preset bounds, all-in confirmation, audio decoding/playback, persisted mute, three themes and 390/320px overflow checks.
- `poker/.venv-deploy/Scripts/python.exe -m unittest discover -s poker_tests -q`: all 93 tests pass, including profile authorization/cache/fallback coverage.
- Screenshots and isolated test databases stay under project-local `backups/poker/` (ignored).

Standards review and spec review: no unresolved findings after fixing legacy CSS duplication and adding accepted-check audio coverage.

## Compact desktop and guild profiles

Desktop layout uses the available viewport height with the hero seat centered and the smaller betting panel to its right. Chrome verifies no document scrolling at 1280x720, 1366x768, 1920x1080 and 1280x640, plus the existing mobile widths. Three original theme palettes and gameplay/sound rules remain unchanged.

GET /api/table/profiles requires the existing session and exposes only current-table human profiles (id, display_name, avatar_url). Five-minute memory cache, per-user task coalescing and stale data on failure keep Discord independent of table actions. Cosmetic fetches defer while the shared Discord authentication boundary is busy and use a two-second timeout. The CSP permits images from self and cdn.discordapp.com only. No database migration or additional OAuth scope is needed.

The recovery test now holds its child at the tenth committed transaction, ensuring the crash exercise actually kills a live writer instead of racing a completed process on fast disks.

Local rollout verified: maintenance drain with zero active hands, project-local backup, service restart and resume succeeded. Public health returns 200 and unauthenticated profiles returns 401. A direct read of the configured guild member and avatar returned 200.
