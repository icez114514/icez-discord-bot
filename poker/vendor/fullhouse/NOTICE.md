# Fixed fullhouse-bot runtime

Source: [fullhouse-bot at e504793](https://github.com/advitrocks9/fullhouse-bot/tree/e504793d480b1b975f25258d25939b45c6dbd5a4).
The three bot modules and two NPZ files are copied from that pinned revision.
See LICENSE for the original MIT notice and upstream exclusions.

Model SHA-256: 1102326b68da95564de147106612df71cb891b42f0726ba0212d3b9a5bcae295.
Preflop SHA-256: 6b3b74778854fcebcd3179753c0252392e5f4118e6b623375c98fafa372863b3.

The adapter preserves the short-stack strategy, network weights and five action
classes. It bypasses only the upstream decide() exception-swallowing wrapper.
Errors become observable worker failures and authoritative check/fold fallbacks.
The engine validates every returned action, including all-in reopening rights.
No strength comparison, retraining, opponent selection or GTO proof is claimed.

Only NumPy and eval7 are used by this runtime. No competition engine, submitted
bots, upload endpoint, arbitrary runner, classifier pickle or training tools ship.
A subprocess is not a complete sandbox: production deployment must use a separate
OS identity/permissions denying access to ledger data and Discord credentials.
The environment passed to the worker contains no service credentials.