import { test } from 'node:test';
import assert from 'node:assert/strict';
import { handPositions } from './positions.ts';

test('positions rotate around every dealer for two through six players', () => {
  const labels = { 2: ['BTN / SB', 'BB'], 3: ['BTN','SB','BB'], 4: ['BTN','SB','BB','CO'], 5: ['BTN','SB','BB','HJ','CO'], 6: ['BTN','SB','BB','UTG','HJ','CO'] };
  for (let count = 2; count <= 6; count++) {
    const players = Array.from({ length: count }, (_, i) => ({ id: `player-${i}`, folded: i % 2 === 0 }));
    for (let button = 0; button < count; button++) {
      const positions = handPositions({ players, button });
      for (let offset = 0; offset < count; offset++) assert.equal(positions[players[(button + offset) % count].id], labels[count][offset]);
      assert.equal(positions['pending-player'], undefined);
    }
  }
});
test('no invented positions before a hand or for invalid dealer indices', () => {
  assert.deepEqual(handPositions(null), {});
  for (const button of [-1, 2, .5]) assert.deepEqual(handPositions({ button, players: [{id:'a'},{id:'b'}] }), {});
});
