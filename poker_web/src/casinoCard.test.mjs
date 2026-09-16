import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { casinoCard } from './casinoCard.ts';

test('all 52 web faces reuse the current casino embossed artwork and indexing', () => {
  for (const [suitIndex, suit] of [...'shdc'].entries()) {
    for (const [rankIndex, rank] of [...'A23456789TJQK'].entries()) {
      const id = suitIndex * 13 + rankIndex;
      assert.equal(casinoCard(rank + suit), `/assets/cards/casino/${id}.png`);
      assert.deepEqual(readFileSync(new URL(`../public/assets/cards/casino/${id}.png`, import.meta.url)), readFileSync(new URL(`../../casino_assets/embossed/cards/${id}.png`, import.meta.url)));
    }
  }
  assert.deepEqual(readFileSync(new URL('../public/assets/cards/casino/back.png', import.meta.url)), readFileSync(new URL('../../casino_assets/embossed/back.png', import.meta.url)));
  assert.equal(casinoCard('bad'), undefined);
});
