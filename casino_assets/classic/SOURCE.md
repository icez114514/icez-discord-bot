# Classic playing card artwork

Source: https://github.com/hayeah/playing-cards-assets
Pinned revision: 1e4497c05c3da9956c9f517bd386e9a7090ff7fa
Upstream README identifies the artwork as public domain, sourced from
https://code.google.com/p/vector-playing-cards/ . PNG files are copied without modification.

Card IDs: suit index * 13 + rank index. Suits: spades, hearts, diamonds, clubs.
Ranks: ace, 2 through 10, jack, queen, king. Back: upstream png/back.png.
The renderer adds the white rounded card stock and scales artwork to fit without cropping.

## Generated Joker (card 52)

`cards/52.png` was generated for this project on 2026-09-12 using the built-in OpenAI image generation tool. It is separate from the upstream 52-card artwork described above.
The original generated PNG is copied unchanged into this repository; the existing renderer fits it into the card frame at runtime.
Prompt: [JOKER-PROMPT.md](JOKER-PROMPT.md).
