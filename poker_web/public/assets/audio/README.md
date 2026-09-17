Original sound effects by Kenney, CC0; the selected A3 click uses Mixkit (see below).

Sources: https://kenney.nl/assets/casino-audio and https://kenney.nl/assets/interface-sounds

deal.ogg: casino / card-slide-1.ogg
chips.ogg: casino / chips-handle-2.ogg
fold.ogg: casino / card-shove-1.ogg
settle.ogg: casino / chips-stack-1.ogg
click.ogg: interface / click_001.ogg
turn.ogg: interface / confirmation_001.ogg
tick.ogg: interface / tick_001.ogg
bank.ogg: interface / pluck_001.ogg

2026-09-16 mix revision: existing CC0 cues are high-pass filtered at 160Hz,
low-pass filtered at 6.5kHz, and faded from 0.30 to 0.42s. `check.ogg` is a dry
0.12s tap derived from chips-handle-2 (220Hz high-pass / 3kHz low-pass).
Playback uses quieter foley, subdued countdowns and no success beep per command.

Finalized voice packs (2026-09-16) are in `voices/oneesan` (御姊),
`voices/shoujo` (少女), and `voices/nekomimi` (貓娘). Each has six
Japanese action announcements: call, bet, fold, check, raise, all-in.
Three-bet, four-bet and higher re-raises use the selected pack's Bet clip.
`voices/manifest.json` pins the approved files by SHA-256 and records
seeds, durations, reference hashes, captions and trim information.
The original root-level `voice-*.ogg` files are legacy assets; playback
now resolves voice cues exclusively through the selected pack directory.

These are synthetic announcements generated locally with Irodori-TTS-v4.1-Small,
not recordings from poker platforms and not covered by the Kenney CC0 licenses.
The private user-provided reference recordings are not included.
Pack 1 uses 此花瑠璃, pack 2 uses 早緒きむり, pack 3 uses 猫乃しろね.
Only pack 1 has a calm-performance Caption; packs 2 and 3 have none.

See `docs/specs/poker-voice-packs.md` for the approved selections and behavior.
Do not use the legacy tools/generate_action_voice.py to overwrite these
finalized files: their parameters and selected takes differ. Runtime serves
only static Vorbis clips; no model, reference audio or TTS dependency runs
on the phone. Preferences remain local to this browser and account.

2026-09-18: Interface click changed to user-selected A3.
click-a3.ogg: Mixkit / Cool interface click tone (SFX 2568).
Source: https://mixkit.co/free-sound-effects/interface/
Original: https://assets.mixkit.co/active_storage/sfx/2568/2568-preview.mp3
License: Mixkit Sound Effects Free License, https://mixkit.co/license/#sfxFree
Converted to Ogg Vorbis without trimming, pitch changes or extra filtering.
Existing interface volume controls apply. Other cue categories are unchanged.
click.ogg remains a legacy Kenney asset.
