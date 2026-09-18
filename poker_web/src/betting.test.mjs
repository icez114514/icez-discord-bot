import { test } from 'node:test';
import assert from 'node:assert/strict';
import { potPreset, sliderAmount, raiseAmount, stepRaise, validRaise } from './betting.ts';
test('pot-sized raise includes call and existing contribution', () => {
  assert.equal(potPreset('300', '100', '50', 1, 1, 250n, 2000n), '550');
  assert.equal(potPreset('301', '0', '0', 1, 3, 100n, 2000n), '100');
});
test('presets clamp to legal full raise or short all-in', () => {
  assert.equal(potPreset('100', '0', '0', 1, 3, 200n, 1000n), '200');
  assert.equal(potPreset('1000', '100', '0', 2, 1, 150n, 150n), '150');
});
test('slider endpoints preserve integers beyond Number precision', () => {
  const max = 900719925474099312345n;
  assert.equal(sliderAmount(0, 200n, max), 200n);
  assert.equal(sliderAmount(1000, 200n, max), max);
  assert.equal(sliderAmount(500, 200n, max), raiseAmount(200n + (max - 200n) / 2n, 200n, max));
});

test('all sizing uses 50-chip units except exact all-in', () => {
  for(let i=0;i<1000;i++) assert.equal(sliderAmount(i, 125n, 1023n)%50n,0n);
  assert.equal(sliderAmount(1000,125n,1023n),1023n);
  assert.equal(raiseAmount(133n,125n,1000n),150n);
  assert.equal(stepRaise(1023n,-1,150n,1023n),1000n);
  assert.equal(stepRaise(1000n,1,150n,1023n),1023n);
  assert.equal(validRaise(175n,100n,1023n),false);
  assert.equal(validRaise(1023n,100n,1023n),true);
});
