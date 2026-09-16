# Table feedback and NPC pacing

User-requested follow-up, 2026-09-16. Review baseline: `541fe3e`.

## Platform references and audio

- [PokerStars sound settings](https://www.pokerstars.com/pt-BR/help/articles/sound-settings/21840/)
  documents master/per-event volume and local preview.
- [GGPoker Action Voice](https://legal.ggpoker.com/nl/poker-games/table-social-features/)
  describes spoken table actions and voice selection in sound settings.
- [GGPoker workspace guidance](https://legal.ggpoker.com/zh-cn/blog/setting-up-your-ggpoker-workspace-for-maximum-results/)
  emphasizes action/all-in alerts and keeping table audio unobtrusive.

The implementation adopts separate spoken action and foley controls, short dry
card/chip cues, subdued reminders, and no extra success beep for each command.
Existing Kenney CC0 foley is filtered/faded to at most 420ms; check uses a 120ms
chip tap. Asset provenance and mastering settings live in
`poker_web/public/assets/audio/README.md`.

Eight synthetic voice clips were generated locally with Irodori-TTS-v4.1-Small,
using the user's selected greeting reference (actual filename `00_挨拶.wav`).
They announce Japanese poker terms for call, bet, fold, check, raise, three-bet,
four-bet and all-in. The generator in `poker_web/tools/generate_action_voice.py`
uses the existing TTS environment/cached models; production only serves OGG files.
The reference audio and model are not packaged with the game.

Voice has its own volume (zero mutes only voice). At most one spoken action plays
at a time; a fresh action interrupts an older announcement to avoid a delayed
speech backlog. All-in has precedence over its underlying call/raise. Blind
posting does not speak. The existing event cursor prevents duplicate delivery,
reconnect, background-tab or historical/replay actions from producing sounds.
Existing per-account sound settings migrate with a default for the new category.

## Stable geometry and visible actions

A reproduced desktop turn transition changed table height from 825.515625px to
912px and moved the action dock by 86.484375px. The conditional preselection UI
created an implicit fifth grid row; deleting it redistributed the table height.
The grid now reserves that row, and the inactive preselection panel keeps its
space while hidden/inert. Connection, status/error, retry and action feedback do
not introduce new layout rows. Fixed geometry is per viewport; normal responsive
resize and deliberate large-card preference changes still change layout.

Confirmed action badges sit below the avatar/name plate, persist until that
player's next action or a new hand/context, and use a dedicated all-in color.
The server adds public `bet_level` metadata: the preflop big blind is level 1;
the first raise is level 2 and re-raise level 3; postflop starts at 0. This drives
3-BET/4-BET labels and voice without guessing from monetary deltas. Amounts remain
exact integers; a clipped badge retains its complete text in its title.

## NPC timing

The user explicitly replaces the prior two-second total turn window with a
five-second turn deadline. Model inference retains its own two-second budget.
At each NPC turn, persist a randomized ready time 1.0..4.7 seconds after the turn
starts, leaving scheduling headroom before the five-second deadline. A triangular
distribution shifts toward longer waits for later streets, more active opponents
and a higher call price relative to the public pot. Distributions overlap; private
hole cards and chosen actions do not affect timing. This is a public-complexity
heuristic, not a claim that the model knows a decision's true difficulty.

Inference starts immediately; the result waits until the ready time outside the
writer/inference locks. Pending tasks are keyed by hand/turn, allowing both tables
to think concurrently. Inference itself remains serialized through the fixed
worker. On restart the saved ready time/deadline remain authoritative. Late output
still takes the existing legal-check/otherwise-fold path, and repeated failures
still sit the NPC out. No model weights, legal actions or accounting rules change;
no schema migration is needed. An OS stall cannot provide a wall-clock guarantee
of service delivery, but no intentional thinking wait extends past five seconds.

## Verification

- Browser regression first failed on the old desktop geometry, then passed at
  1440/390/320px. It also checks call/bet/check/fold/3-bet/4-bet/all-in labels and
  persistence beyond the former 1400ms removal; all three themes/large cards and
  existing reconnect/preselection tests pass. Desktop and 320px screenshots were
  visually inspected.
- Timing tests cover bounded randomized distributions, public-complexity shift,
  independence from private strength, concurrent two-table waits and one result
  per turn. Rule tests check authoritative preflop three-bet and postflop reset.
- Audio tests cover event-to-voice selection, all-in precedence, blind silence,
  independent voice volume and one active speaker. Assets decode with ffmpeg;
  original generated clips range from 0.92 to 1.48 seconds before mastering.
- The existing real-service replay browser suite passes with no replay commands,
  audio or JavaScript exceptions. Browsers still use simulated Discord identities.
- Game-flow tests pin random thinking to the allowed one-second minimum. The
  five-NPC replacement drill permits two rounds of those waits; the late-output
  regression explicitly crosses the current hand deadline. No assertions removed.

No production restart or external deployment is performed by this follow-up.
Install the backend and built frontend together using DEPLOYMENT.md when deploying.

Final automated results: poker 104 passed (56.420s); frontend 22 passed after
the audio-order fix; existing Bot 162 discovered / 103 passed / 59 opt-in DB
skips; TypeScript/Vite, first-party mypy (32 modules) and Ruff F checks passed.
Independent Standards and Spec review both identified the same deferred-audio
ordering race. Its regression failed (two voices started instead of one) before
the fix; voice requests now carry an order token so an older decode completion
cannot interrupt the newest action. Targeted Standards and Spec re-review: 0 unresolved findings on both axes.
