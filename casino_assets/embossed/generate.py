"""Reproduce the white embossed deck with Pillow typography and geometry.

No AI image is edited. The approved concept is rebuilt from native drawing
primitives so every rank and suit shares exact coordinates and styling.
Fonts are supplied by the host and are not redistributed with the deck.
"""
import argparse
import hashlib
import html
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageFilter

SIZE = (1000, 1400)
RANKS = ('A', '2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K')
SUITS = ('spades', 'hearts', 'diamonds', 'clubs')
SYMBOLS = ('\u2660', '\u2665', '\u2666', '\u2663')
BLACK, RED = '#12151b', '#c50920'


def stock():
    image = Image.new('RGBA', SIZE)
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((3, 3, 996, 1396), 58, fill='white', outline='#e4e6e8', width=3)
    # Shallow paired shadow/highlight grooves, with a completely white center.
    shadow = Image.new('RGBA', SIZE)
    sd = ImageDraw.Draw(shadow)
    for inset in (51, 68):
        sd.rounded_rectangle((inset, inset + 5, 999-inset, 1399-inset + 5),
                             48, outline='#e0e3e6', width=5)
    image.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(3)))
    draw = ImageDraw.Draw(image)
    for inset in (51, 68):
        draw.rounded_rectangle((inset, inset-2, 999-inset, 1399-inset-2),
                               48, outline='white', width=5)
        draw.rounded_rectangle((inset+5, inset+5, 994-inset, 1394-inset),
                               43, outline='#f2f3f4', width=2)
    return image


def centered_text(image, text, path, box, color):
    x, y, width, height = box
    size = 600
    while True:
        font = ImageFont.truetype(str(path), size)
        left, top, right, bottom = font.getbbox(text)
        if right-left <= width and bottom-top <= height:
            break
        size -= 1
    ImageDraw.Draw(image).text((x+(width-right+left)/2-left,
                               y+(height-bottom+top)/2-top),
                              text, font=font, fill=color)


def jester(image):
    draw = ImageDraw.Draw(image)
    # A simple two-color jester cap stays recognizable at card-table scale.
    draw.polygon([(275, 990), (205, 755), (370, 815), (500, 675),
                  (540, 965)], fill=BLACK)
    draw.polygon([(500, 675), (620, 815), (795, 755), (725, 990),
                  (500, 965)], fill=RED)
    for x, y, color in ((205, 745, BLACK), (500, 665, BLACK), (795, 745, RED)):
        draw.ellipse((x-37, y-37, x+37, y+37), fill=color)
    draw.rounded_rectangle((270, 960, 730, 1055), 35, fill=BLACK)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--rank-font', type=Path, default=Path('C:/Windows/Fonts/georgiab.ttf'))
    parser.add_argument('--suit-font', type=Path, default=Path('C:/Windows/Fonts/seguisym.ttf'))
    parser.add_argument('--output', type=Path, default=Path(__file__).resolve().parent)
    args = parser.parse_args()
    root = args.output
    (root/'cards').mkdir(parents=True, exist_ok=True)
    manifest = {'name': 'White embossed', 'size': list(SIZE), 'cards': [],
                'generation': 'Pillow native typography and geometry',
                'rank_font': args.rank_font.name, 'suit_font': args.suit_font.name}
    for value in range(53):
        image = stock()
        if value == 52:
            centered_text(image, 'JOKER', args.rank_font, (125, 265, 750, 190), BLACK)
            jester(image)
            rank, suit, label = 'JOKER', 'joker', 'Joker'
        else:
            rank, suit = RANKS[value % 13], SUITS[value // 13]
            color = RED if value // 13 in (1, 2) else BLACK
            centered_text(image, rank, args.rank_font, (150, 225, 700, 405), color)
            centered_text(image, SYMBOLS[value // 13], args.suit_font,
                          (215, 745, 570, 470), color)
            label = rank + SYMBOLS[value // 13]
        file = root/'cards'/f'{value}.png'
        image.save(file)
        manifest['cards'].append({'id': value, 'rank': rank, 'suit': suit,
                                  'label': label, 'file': f'cards/{value}.png',
                                  'sha256': hashlib.sha256(file.read_bytes()).hexdigest()})
    back = stock()
    draw = ImageDraw.Draw(back)
    # The same neutral, rotationally symmetric back for every concealed card.
    for extent in (180, 240, 300):
        points = [(500, 700-extent), (500+extent*.72, 700),
                  (500, 700+extent), (500-extent*.72, 700), (500, 700-extent)]
        draw.line(points, fill='#c3c9cf', width=9, joint='curve')
    draw.ellipse((469, 669, 531, 731), fill='#adb6c0')
    back.save(root/'back.png')
    manifest['back'] = {'file': 'back.png', 'sha256': hashlib.sha256((root/'back.png').read_bytes()).hexdigest()}
    (root/'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    tiles = []
    for card in manifest['cards']:
        tiles.append(f'<a class="card" href="{card["file"]}"><img loading="lazy" src="{card["file"]}" alt="{html.escape(card["label"])}"><span>{html.escape(card["label"])}</span></a>')
    tiles.append('<a class="card" href="back.png"><img src="back.png" alt="Back"><span>Back</span></a>')
    page = '''<!doctype html><html lang="zh-Hant"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>白色壓印牌組</title><style>
body{margin:0;padding:28px;background:#253138;color:#fff;font:16px system-ui}h1{margin:0 0 12px}p{color:#cbd3d8}main{display:grid;grid-template-columns:repeat(auto-fill,minmax(155px,1fr));gap:22px}.card{color:#fff;text-decoration:none;text-align:center}.card img{width:100%;aspect-ratio:5/7;object-fit:contain;display:block;margin-bottom:8px}a{color:#e0ebff}</style><h1>白色壓印牌組</h1><p>52 張一般牌 + Joker + 共用牌背 · 點擊查看原尺寸</p><main>''' + ''.join(tiles) + '</main></html>'
    (root/'gallery.html').write_text(page, encoding='utf-8')
    print('Created 53 faces and one shared back.')


if __name__ == '__main__':
    main()
