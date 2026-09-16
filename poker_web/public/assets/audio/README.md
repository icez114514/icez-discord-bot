Sound effects by Kenney, CC0.

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

`voice-*.ogg` are synthetic action announcements generated locally with
Irodori-TTS-v4.1-Small using the user-selected `00_挨拶.wav` greeting reference
(此花瑠璃). They are not recordings from PokerStars or GGPoker and are not covered
by the Kenney CC0 licenses. The private reference clip is not included.
Six Japanese poker terms: call, bet, fold, check, raise and all-in.
Three-bet, four-bet and higher re-raises all use the Bet clip; their visual
labels still show the actual raise level. The voice is separately adjustable/mutable and never used in replay.

Rebuild using tools/generate_action_voice.py with the local Irodori environment,
cached models, NVIDIA CUDA and ffmpeg. Seeds 260916..260920 and 260923, bf16 model, 12s max
reference, duration scale 0.85; loudness target -18 LUFS, true peak -2dB,
mono 48kHz Vorbis quality 5. Runtime serves only these static clips; no TTS
model, reference audio or TTS dependency runs on the phone.
