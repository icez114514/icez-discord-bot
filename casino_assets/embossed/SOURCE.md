# White embossed deck

The selected C / white embossed concept is reproduced with native Pillow
typography and geometry, not by editing the AI preview or generating each
rank separately. This keeps all ranks, suits, colors and spacing consistent.

- 52 regular faces, one Joker (ID 52), and one shared back.
- Card ID = suit index * 13 + rank index.
- Suits: spades, hearts, diamonds, clubs. Ranks: A, 2-10, J, Q, K.
- 1000 x 1400 RGBA PNG; white stock, shallow embossed border, central rank
  and suit only. No corner indices.
- Joker: central JOKER label and a red/black jester-cap symbol.
- Fonts: Georgia Bold and Segoe UI Symbol from the build host. Font binaries
  are not redistributed and are not required by the bot at runtime.
- Rebuild: `.venv/Scripts/python.exe casino_assets/embossed/generate.py`.
  Other hosts can supply --rank-font and --suit-font paths.
- Original approved concept: style-reference.png (built-in image_gen).
- Default runtime assets: this directory. Custom cards/<ID>.png and back.png
  overrides still take precedence; missing packaged cards fall back to classic.
- Runtime uses preloaded small images and performs no generation or font loading.

Validation (2026-09-12):
- All 54 images decode, have the expected dimensions and distinct SHA-256 hashes.
- Full-card overview and initial/settled Pai Gow previews visually inspected.
- 98 non-database tests passed; 59 database tests intentionally skipped.
- mypy passed for casino_images.py.
- Image.open disabled after preload: previews and 10 warm renders succeeded.
- Local warm-render median: 20.8 ms; initial/selected/result PNG: 73-97 KiB.
- Discord desktop/mobile acceptance remains pending as previously requested.
