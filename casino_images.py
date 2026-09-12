"""Cached, replaceable table assets; accepts only the public Game projection."""

import io
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

from blackjack import total
import paigow
from casino_rules import dice_points


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
        self.paigow_background = self.asset('background.png', Image.new('RGBA', (1200, 1800), '#0a2427'))
        self.cards = {card: self.asset(f'cards/{card}.png', self.card(card)) for card in range(53)}
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
        draw.rounded_rectangle((1, 1, 142, 198), radius=9, fill='#fffdf8',
                               outline='#bcc5bf', width=2)
        if value == paigow.JOKER:
            draw.rounded_rectangle((9, 9, 134, 190), radius=8, fill='#2f2149', outline='#d2ae60', width=3)
            draw.text((72, 45), 'JOKER', font=font(24), fill='#f8d98b', anchor='mm')
            draw.text((72, 103), '*', font=font(80), fill='#f8d98b', anchor='mm')
            draw.text((72, 161), 'WILD', font=font(22), fill='#f8d98b', anchor='mm')
            return image
        name = 'back.png' if value is None else f'cards/{value}.png'
        source = Path(__file__).with_name('casino_assets') / 'classic' / name
        try:
            with Image.open(source) as artwork:
                face = ImageOps.contain(artwork.convert('RGBA'), (132, 188), Image.Resampling.LANCZOS)
            image.alpha_composite(face, ((144-face.width)//2, (200-face.height)//2))
            return image
        except (OSError, ValueError):
            pass  # Keep a usable procedural fallback if packaged artwork is missing.
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


    def paigow_table(self, game):
        # Portrait table: each side's front two cards sit ABOVE its back five.
        image = self.paigow_background.copy()
        draw = ImageDraw.Draw(image)
        draw.rounded_rectangle((24, 24, 1176, 1776), radius=40, outline='#97784d', width=3)
        for top, bottom in ((90, 825), (860, 1630)):
            draw.rounded_rectangle((48, top, 1152, bottom), radius=26,
                                   fill='#123c3c', outline='#35605a', width=2)
        names = ('HIGH CARD', 'PAIR', 'TWO PAIR', 'THREE OF A KIND', 'STRAIGHT',
                 'FLUSH', 'FULL HOUSE', 'FOUR OF A KIND', 'STRAIGHT FLUSH', 'FIVE OF A KIND')
        draw.text((65, 43), 'PAI GOW POKER', font=font(30), fill='#e6d7b5')
        draw.text((1135, 47), 'WILD JOKER / NO COMMISSION', font=font(19), fill='#a8c4be', anchor='ra')

        def group(cards, y, heading, indices=None, comparison=None):
            hidden = None in cards
            ordered = list(cards) if hidden else paigow.display_order(cards)
            evaluation = None if hidden else paigow.evaluate(ordered)
            caption = 'HIDDEN' if evaluation is None else names[evaluation.score[0]]
            if indices is not None and not game.front:
                evaluation = None
                caption = 'NOT ARRANGED'
            if comparison is not None:
                caption += ' / ' + {1: 'WIN', 0: 'TIE: DEALER WINS', -1: 'LOSS'}[comparison]
            draw.text((600, y - 33), heading, font=font(25), fill='#e6d7b5', anchor='mm')
            x = (1200 - len(ordered) * 168 - (len(ordered) - 1) * 20) // 2
            for card in ordered:
                sprite = self.back if card is None else self.cards[card]
                image.alpha_composite(sprite.resize((168, 233), Image.Resampling.LANCZOS), (x, y))
                if indices is not None:
                    draw.rounded_rectangle((x + 63, y + 238, x + 105, y + 265), radius=8, fill='#eadbb9')
                    draw.text((x + 84, y + 251), str(indices[card]), font=font(21), fill='#163c3c', anchor='mm')
                if card == paigow.JOKER and evaluation is not None and evaluation.joker_as is not None:
                    joker = evaluation.joker_as
                    rank = ('A', '2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K')[joker % 13]
                    suit = ('S', 'H', 'D', 'C')[joker // 13]
                    draw.text((x + 84, y + 211), f'= {rank}{suit}', font=font(18), fill='#f8d98b', anchor='mm')
                x += 188
            draw.text((600, y + 283), caption, font=font(22), fill='#c6d8ce', anchor='mm')

        if game.status == 'void':
            draw.text((600, 840), 'VOID / FULL REFUND', font=font(42), fill='#e6d7b5', anchor='mm')
        else:
            if game.status == 'active':
                dealer_low, dealer_high = [None] * 2, [None] * 5
            else:
                dealer_low, dealer_high = paigow.split(game.dealer, game.dealer_front)
            group(dealer_low, 150, 'DEALER / FRONT 2')
            group(dealer_high, 510, 'DEALER / BACK 5')
            player = paigow.display_order(game.player)
            indices = {card: i + 1 for i, card in enumerate(player)}
            if game.front:
                low, high = paigow.split(player, game.front)
                comparison = (None, None)
                if game.status == 'settled':
                    comparison, _ = paigow.compare(low, high, dealer_low, dealer_high)
                group(low, 945, 'YOU / FRONT 2', indices, comparison[0])
                group(high, 1305, 'YOU / BACK 5', indices, comparison[1])
            else:
                # Display all cards in A-K order without claiming an unchosen split.
                group(player[:2], 945, 'YOUR CARDS 1-2 / CHOOSE FRONT TWO', indices)
                group(player[2:], 1305, 'YOUR CARDS 3-7 / NOT YET ARRANGED', indices)
        status = 'ARRANGE / CONFIRM' if game.status == 'active' else (game.outcome or game.status).upper()
        draw.text((65, 1680), status, font=font(23), fill='#e6d7b5')
        returned = 'PENDING' if game.status == 'active' else compact(game.returned)
        draw.text((1135, 1680), f'WAGER {compact(game.wager)} / RETURN {returned}',
                  font=font(21), fill='#c6d8ce', anchor='ra')
        if game.status != 'active':
            draw.text((1135, 1720), f'NET {compact(game.net)} / BALANCE {compact(game.balance_after)}',
                      font=font(19), fill='#c6d8ce', anchor='ra')
        output = io.BytesIO()
        image.convert('RGB').save(output, format='PNG')
        return output.getvalue()

    def render(self, game):
        if game.game == 'paigow':
            return self.paigow_table(game)
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
                dealer_points, player_points = str(dice_points(game.dice[3:])), str(dice_points(game.dice[:3]))
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
