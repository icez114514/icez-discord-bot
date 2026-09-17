"""Rebuild only the two web joker faces with the existing casino drawing primitives."""
import importlib.util
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('casino_generator', ROOT/'casino_assets/embossed/generate.py')
generator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(generator)
for name, color in [('Xr', generator.RED), ('Xb', generator.BLACK)]:
    image = generator.stock()
    generator.centered_text(image, 'JOKER', Path('C:/Windows/Fonts/georgiab.ttf'), (125,265,750,190), color)
    generator.jester(image)
    image.save(ROOT/'poker_web/public/assets/cards/casino'/f'{name}.png')