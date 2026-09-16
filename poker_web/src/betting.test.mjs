import { test } from 'node:test';
import assert from 'node:assert/strict';
import { potPreset, sliderAmount } from './betting.ts';
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
  assert.equal(sliderAmount(500, 200n, max), 200n + (max - 200n) / 2n);
});
