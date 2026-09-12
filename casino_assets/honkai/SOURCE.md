# Honkai Impact 3rd character deck

53 independently generated card faces (standard 52 plus one Joker) and one shared back.
Card ID = suit index * 13 + rank index; suits: spades, hearts, diamonds, clubs; ranks: A through K.
Joker ID is 52. Character/outfit assignments and generation status are recorded in manifest.json.

## Art direction
The user-approved style reference is style-reference.png: clean original-game-anime cel shading,
recognizable Honkai Impact 3rd characters in canonical battlesuits, white card stock,
simple pale lavender frame and large legible corner indices. Individual prompts are in prompts/.
Images are generated adaptations, not extracted official assets. Canonical design details are
interpreted by the image model and may differ from official originals.
The generated PNG files are preserved unchanged. They are fitted to the game's card size at render time.

## References
- Character and battlesuit catalog: https://marisaimpact.com/valk
- Battlesuit index: https://honkaiimpact3.fandom.com/wiki/Battlesuits
- Approved Kiana reference: https://www.pocketgamer.com/honkai-impact-3rd/version-kiana-update-feb-16/
- Approved Mei reference: https://marisaimpact.com/valk/hoo
- Approved Elysia reference: https://honkaiimpact3.hoyoverse.com/strategy/character/detail/102737
- The requested Danbooru page was unavailable (HTTP 403); game_asset/highres tags were not verified.

Generated using the built-in OpenAI image_gen tool, 2026-09-12.
Characters and source designs are from Honkai Impact 3rd by miHoYo / HoYoverse.
The existing classic deck retains its own separate source record.

## Validation
- All 53 face IDs (0-52) and the shared back decode successfully; all face files have distinct SHA-256 hashes.
- Every face was visually checked during generation for its rank and suit. Q of spades was corrected with image_gen.
- Full non-database suite: 98 passed, 59 database tests intentionally skipped; mypy passed for casino_images.py.
- Local 1200x800 initial, selected and settled Pai Gow previews inspected; common back, side-by-side layout and represented-Joker sorting retained.
- Discord desktop/mobile acceptance remains pending, as previously requested.
