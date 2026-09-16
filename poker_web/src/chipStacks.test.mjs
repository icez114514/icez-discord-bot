import { test } from 'node:test';
import assert from 'node:assert/strict';
import { chipStacks, collectedPot } from './chipStacks.ts';
test('casino denominations preserve exact amounts with bounded visible stacks', () => {
  for (const amount of ['0','1','5','50','100','875','999999999999999999999999999']) {
    const stacks = chipStacks(amount);
    assert.equal(stacks.reduce((n, s) => n + s.value * s.count, 0n), BigInt(amount));
    assert(stacks.every(s => s.visible > 0 && s.visible <= 5));
  }
  assert.deepEqual(chipStacks('50').map(s => [s.value, s.count]), [[25n, 2n]]);
  assert.notEqual(chipStacks('50')[0].color, chipStacks('100')[0].color);
});
test('pot stacks exclude uncollected wagers and disappear after settlement', () => {
  assert.equal(collectedPot('300',['100','200'],false),'0');
  assert.equal(collectedPot('300',['0','0'],false),'300');
  assert.equal(collectedPot('800',['100','200'],false),'500');
  assert.equal(collectedPot('800',['0','0'],true),'0');
});
