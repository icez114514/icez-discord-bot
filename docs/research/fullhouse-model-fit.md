# fullhouse-bot: strategy and game-contract fit

Reviewed 2026-09-15 at immutable commit `e504793d480b1b975f25258d25939b45c6dbd5a4`. Scope: static runtime, feature encoder and relevant training contract; no training or strength benchmark. Licensing and local inference timings are separate workstreams.

## Conclusion

Suitable as a pretrained candidate for an integration prototype, **not yet an accepted strong approximate-GTO NPC for the full 2-6-player persistent-chip game**. The runtime makes genuine mixed-strategy selections and reads only the NPC's own cards plus public state. However, short-handed strength, side-pot strategy and competition-weight provenance remain unverified. Several integration changes are required even before gameplay evaluation.

## Evidence and implications

### Blind units must be adapted

Both runtime modules assume BB=100 and a 10,000-chip reference stack. The user's 10/20 game cannot pass raw money values: a 400-chip buy-in is 20 BB to the game but looks like 4 BB to the existing code. Its short-stack rule would activate incorrectly. Prefer scaling every chip-valued field and action-log amount by 5 into the model contract, then converting raises back with explicit chip rounding and authoritative legal-action validation. Changing only the named constants is insufficient: the encoder also compares current bets to a literal 100. This is unit adaptation, not a need to retrain for different chip denominations.

Sources: [bot.py L26-L28](https://github.com/advitrocks9/fullhouse-bot/blob/e504793d480b1b975f25258d25939b45c6dbd5a4/bot/bot.py#L26-L28), [short-stack threshold L260-L274](https://github.com/advitrocks9/fullhouse-bot/blob/e504793d480b1b975f25258d25939b45c6dbd5a4/bot/bot.py#L260-L274), [features L696-L736](https://github.com/advitrocks9/fullhouse-bot/blob/e504793d480b1b975f25258d25939b45c6dbd5a4/bot/features.py#L696-L736).

### Mixed strategy is real, but restricted

The advantage inference normalizes positive regrets; if all are nonpositive it uses a uniform distribution over allowed actions. The runtime samples that distribution, rather than taking argmax. Five output actions cover fold, check/call, half-pot raise, pot-size raise and all-in. All-in is masked out when effective stack/pot is at least 4; other bet sizes are unavailable to the NPC. This is a restricted action abstraction, not the full no-limit game. Humans can still use other legal amounts if the authoritative game supports them, but strategy quality against those sizes must be tested. Action probabilities share a module-level fixed-seed PRNG; isolated NPC workers started identically should not all reuse the same random stream.

Sources: [regret matching L147-L161](https://github.com/advitrocks9/fullhouse-bot/blob/e504793d480b1b975f25258d25939b45c6dbd5a4/bot/deep_cfr_lookup.py#L147-L161), [sampling and translation L374-L430](https://github.com/advitrocks9/fullhouse-bot/blob/e504793d480b1b975f25258d25939b45c6dbd5a4/bot/bot.py#L374-L430), [mask L765-L805](https://github.com/advitrocks9/fullhouse-bot/blob/e504793d480b1b975f25258d25939b45c6dbd5a4/bot/features.py#L765-L805), [seed L41](https://github.com/advitrocks9/fullhouse-bot/blob/e504793d480b1b975f25258d25939b45c6dbd5a4/bot/bot.py#L41).

### Short stacks use a hand-written rule

At effective stack <=12 BB preflop, a deterministic chart bypasses the network and the later model-action mask. It uses the largest nonfolded opponent stack to derive effective stack, coarse hand tiers, position and pot odds. This is not proof of solved push/fold play, especially with multiple opponents. Short all-ins, raises that do not reopen action and other engine constraints need final validation outside this bot. Below 12 BB is reachable even with the accepted minimum 20 BB buy-in.

Source: [push/fold and decision flow L260-L371](https://github.com/advitrocks9/fullhouse-bot/blob/e504793d480b1b975f25258d25939b45c6dbd5a4/bot/bot.py#L260-L371).

### Six-player training does not establish 2-5-player quality

The main training entry point fixes N_PLAYERS=6. The encoder and position rules accept fewer players, but the experiment ledger places mixed 2-6-player training in archived v25 and explicitly identifies short-handed coverage as an issue. Runtime support is therefore not evidence of strong play at every table size.

Sources: [training player count L24](https://github.com/advitrocks9/fullhouse-bot/blob/e504793d480b1b975f25258d25939b45c6dbd5a4/training/train.py#L24), [experiment ledger L21-L36](https://github.com/advitrocks9/fullhouse-bot/blob/e504793d480b1b975f25258d25939b45c6dbd5a4/docs/research/experiments.md#L21-L36).

### Stacks may drift, but coverage remains bounded

Current training supports randomized per-player stacks while conserving 100 BB per initial player overall; it does not train exclusively at equal 100 BB stacks. Nevertheless, six-player randomized stacks conserve 600 BB total, whereas persistent cash tables with replenishment and repeated join/leave can exceed that distribution. This code support does not establish which distribution the bundled weights actually saw. The adapter must supply complete current-hand logs: without them the encoder estimates invested money as 10,000 minus current stack, which is wrong for arbitrary starting stacks.

Sources: [stack sampler L168-L180](https://github.com/advitrocks9/fullhouse-bot/blob/e504793d480b1b975f25258d25939b45c6dbd5a4/training/traverse_fast.py#L168-L180), [use of randomized stacks L327-L330](https://github.com/advitrocks9/fullhouse-bot/blob/e504793d480b1b975f25258d25939b45c6dbd5a4/training/traverse_fast.py#L327-L330), [investment fallback L719-L753](https://github.com/advitrocks9/fullhouse-bot/blob/e504793d480b1b975f25258d25939b45c6dbd5a4/bot/features.py#L719-L753).

### No hidden cards used; limited multiplayer/side-pot representation

The runtime reads `your_cards` and `community_cards`, not opponents' hole cards or future deck cards. Preserve that observation boundary in the integration. Preflop equity is a table against one random opponent; postflop strength is a normalized current hand evaluator score, not a current multiway equity calculation. Public features include active-player count, sorted opponent stacks and maximum opponent contribution, but no explicit per-pot eligibility and amount vectors. Once anyone is all-in, the minimum active stack used in the SPR feature can become zero even when deeper opponents remain. These are strategy-representation limits, not proof the game engine cannot settle side pots. The ledger says multiway-equity v21 and explicit side-pot v23 variants were parked because of input-shape mismatch.

Sources: [runtime observations and card features L640-L690](https://github.com/advitrocks9/fullhouse-bot/blob/e504793d480b1b975f25258d25939b45c6dbd5a4/bot/features.py#L640-L690), [hand-score implementation L362-L370](https://github.com/advitrocks9/fullhouse-bot/blob/e504793d480b1b975f25258d25939b45c6dbd5a4/bot/features.py#L362-L370), [equity generation L54-L78](https://github.com/advitrocks9/fullhouse-bot/blob/e504793d480b1b975f25258d25939b45c6dbd5a4/tooling/data_tools/preflop_equity.py#L54-L78), [public features L699-L756](https://github.com/advitrocks9/fullhouse-bot/blob/e504793d480b1b975f25258d25939b45c6dbd5a4/bot/features.py#L699-L756), [parked models L12-L19](https://github.com/advitrocks9/fullhouse-bot/blob/e504793d480b1b975f25258d25939b45c6dbd5a4/docs/research/experiments.md#L12-L19).

### Silent fallback can disguise a broken model

`decide` catches every exception and checks if possible, otherwise calls when money is owed. Missing eval7 can thus turn postflop decisions into silent calling rather than visibly failing the model. Model files missing at import fail earlier, so not all load failures are swallowed. Production integration should validate dependencies/model at startup, count inference failures, log safely, and suspend faulty NPC operation with the agreed timeout policy rather than quietly passing off fallback play as the learned strategy. This matters because losses change persistent player balances.

Sources: [fallback L343-L371](https://github.com/advitrocks9/fullhouse-bot/blob/e504793d480b1b975f25258d25939b45c6dbd5a4/bot/bot.py#L343-L371), [eval7 required L78-L89](https://github.com/advitrocks9/fullhouse-bot/blob/e504793d480b1b975f25258d25939b45c6dbd5a4/bot/features.py#L78-L89).

## Strength claim boundary

Local opponent-pool performance, the use of Deep CFR, and a mixed output distribution do not establish low exploitability in this user's 2-6-player game. Additionally, the ledger identifies a finals v29 model plus overlay on an archive tag, while describing v17 as shipped in the main table. Do not assign the advertised external finals placement to the downloadable main weights without provenance. An acceptance gate needs separate results at 2, 3, 4, 5 and 6 players; short/deep stacks; off-menu human raises; side-pot situations; and held-out competent opponents, with enough samples and confidence intervals. No training is required merely to perform these checks.

Source: [version ledger](https://github.com/advitrocks9/fullhouse-bot/blob/e504793d480b1b975f25258d25939b45c6dbd5a4/docs/research/experiments.md#L10-L28).
