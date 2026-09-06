"""Cached, replaceable table assets; accepts only the public Game projection."""

import io
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

from blackjack import total


def font(size):
    return ImageFont.load_default(size=size)


def compact(value):
    text = str(value)
    return text if len(text) <= 14 else text[:6] + '...' + text[-4:]


class TableRenderer:
    def __init__(self, directory):
        self.directory = Path(directory)
        background = Image.new('RGBA', (1200, 800), '#0a2427')
        draw = ImageDraw.Draw(background)
        draw.rounded_rectangle((24, 24, 1176, 776), radius=48, outline='#97784d', width=3)
        draw.ellipse((85, 92, 1115, 760), fill='#123c3c', outline='#35605a', width=2)
        draw.line((110, 422, 1090, 422), fill='#416660', width=2)
        self.background = self.asset('background.png', background)
        self.cards = {card: self.asset(f'cards/{card}.png', self.card(card)) for card in range(52)}
        self.back = self.asset('back.png', self.card(None))
        self.dice = {value: self.asset(f'dice/{value}.png', self.die(value)) for value in range(1, 7)}

    def asset(self, name, placeholder):
        try:
            with Image.open(self.directory / name) as image:
                return ImageOps.fit(image.convert('RGBA'), placeholder.size)
        except (OSError, ValueError):
            return placeholder.convert('RGBA')

    def card(self, value):
        image = Image.new('RGBA', (144, 200))
        draw = ImageDraw.Draw(image)
        draw.rounded_rectangle((1, 1, 142, 198), radius=14, fill='#fcf6e9' if value is not None else '#263e68',
                               outline='#bca16b', width=3)
        if value is None:
            for inset in (15, 25, 35):
                draw.rounded_rectangle((inset, inset, 143-inset, 199-inset), radius=8, outline='#88a5ce', width=2)
            draw.text((72, 99), '?', font=font(48), fill='#e6d7b5', anchor='mm')
        else:
            rank = ('A', '2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K')[value % 13]
            color = '#a23248' if value // 13 in (1, 2) else '#233b45'
            draw.text((14, 10), rank, font=font(30), fill=color)
            draw.text((72, 98), rank, font=font(52), fill=color, anchor='mm')
            draw.text((72, 158), ('SPADES', 'HEARTS', 'DIAMONDS', 'CLUBS')[value // 13],
                      font=font(15), fill=color, anchor='mm')
        return image

    def die(self, value):
        image = Image.new('RGBA', (164, 164))
        draw = ImageDraw.Draw(image)
        draw.rounded_rectangle((2, 2, 161, 161), radius=26, fill='#fcf6e9', outline='#bca16b', width=3)
        dots = {1: [(1, 1)], 2: [(0, 0), (2, 2)], 3: [(0, 0), (1, 1), (2, 2)],
                4: [(0, 0), (2, 0), (0, 2), (2, 2)],
                5: [(0, 0), (2, 0), (1, 1), (0, 2), (2, 2)],
                6: [(0, 0), (2, 0), (0, 1), (2, 1), (0, 2), (2, 2)]}
        for x, y in dots[value]:
            x, y = 40 + x * 42, 40 + y * 42
            draw.ellipse((x-11, y-11, x+11, y+11), fill='#a23248' if value == 1 else '#233b45')
        return image

    def row(self, image, sprites, y):
        if not sprites:
            return
        width = min(sprites[0].width, (1030 - 12 * (len(sprites)-1)) // len(sprites))
        height = round(sprites[0].height * width / sprites[0].width)
        left = (1200 - (width + 12) * len(sprites) + 12) // 2
        for sprite in sprites:
            image.alpha_composite(sprite.resize((width, height)), (left, y + (200-height)//2))
            left += width + 12

    def render(self, game):
        image = self.background.copy()
        draw = ImageDraw.Draw(image)
        draw.text((65, 52), 'CRYSTAL CASINO', font=font(28), fill='#e6d7b5')
        title = 'BLACKJACK' if game.game == 'blackjack' else 'THREE DICE'
        draw.text((1135, 57), title, font=font(22), fill='#a8c4be', anchor='ra')
        if game.status == 'void':
            draw.text((600, 360), 'VOID / FULL REFUND', font=font(42), fill='#e6d7b5', anchor='mm')
        else:
            if game.game == 'blackjack':
                dealer = [self.back if card is None else self.cards[card] for card in game.dealer]
                player = [self.cards[card] for card in game.player]
                dealer_points = str(total(game.dealer)) if None not in game.dealer else str(total(game.dealer[:1])) + ' + ?'
                player_points = str(total(game.player))
            else:
                dealer = [self.dice[value] for value in game.dice[3:]]
                player = [self.dice[value] for value in game.dice[:3]]
                dealer_points, player_points = str(sum(game.dice[3:])), str(sum(game.dice[:3]))
            draw.text((600, 140), 'DEALER  /  ' + dealer_points, font=font(24), fill='#c6d8ce', anchor='mm')
            self.row(image, dealer, 175)
            draw.text((600, 457), 'YOU  /  ' + player_points, font=font(24), fill='#e6d7b5', anchor='mm')
            self.row(image, player, 490)
        status = 'YOUR TURN' if game.status == 'active' else (game.outcome or game.status).upper()
        draw.text((65, 731), status, font=font(24), fill='#e6d7b5')
        draw.text((1135, 735), 'WAGER ' + compact(game.wager) + '  /  RETURN ' +
                  ('PENDING' if game.status == 'active' else compact(game.returned)),
                  font=font(20), fill='#c6d8ce', anchor='ra')
        output = io.BytesIO()
        image.convert('RGB').save(output, format='PNG')
        return output.getvalue()


@lru_cache(maxsize=4)
def renderer(directory):
    return TableRenderer(directory)
