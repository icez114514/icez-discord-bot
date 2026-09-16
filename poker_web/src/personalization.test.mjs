import { test } from 'node:test';
import assert from 'node:assert/strict';
import { stackDisplay, bbPreset } from './personalization.ts';

test('BB display preserves huge integers and marks only rounded values', () => {
  assert.equal(stackDisplay('900719925474099312345', '100', true), '9007199254740993123.45 BB');
  assert.equal(stackDisplay('1250', '100', true), '12.5 BB');
  assert.equal(stackDisplay('2999', '1000', true), '≈3 BB');
  for (const blind of [undefined, '0', '-1', 'oops']) {
    assert.equal(stackDisplay('1250', blind, true), '1,250');
  }
});

test('fractional BB raise-to floors integer chips then respects server limits', () => {
  assert.equal(bbPreset('101', '2.5', 202n, 1000n), '252');
  assert.equal(bbPreset('101', '2.5', 300n, 1000n), '300');
  assert.equal(bbPreset('101', '2.5', 150n, 150n), '150');
  assert.equal(bbPreset(undefined, '2.5', 200n, 1000n), null);
});

import { readPreferences, savePreferences } from './personalization.ts';
test('preferences isolate accounts and survive unavailable or corrupt storage', () => {
  const values = new Map();
  const storage = { getItem: key => values.get(key) ?? null, setItem: (key, value) => values.set(key, value) };
  const a = { ...readPreferences(storage, 'a'), bb: true, fourColor: true, large: true, preflop: ['2', '2.5', '3', '4', '5'] };
  assert.equal(savePreferences(storage, 'a', a), true);
  assert.deepEqual(readPreferences(storage, 'a'), a);
  assert.equal(readPreferences(storage, 'b').bb, false);
  values.set('poker.table.v1:a', '{"preflop":["0"],"bb":"yes"}');
  assert.equal(readPreferences(storage, 'a').bb, false);
  assert.equal(readPreferences(storage, 'a').preflop.length, 5);
  const broken = { getItem() { throw Error(); }, setItem() { throw Error(); } };
  assert.equal(readPreferences(broken, 'a').large, false);
  assert.equal(savePreferences(broken, 'a', a), false);
});

test('rounded BB values and extreme raise presets remain exact', () => {
  assert.equal(stackDisplay('900719925474099312345', '1000', true), '≈900719925474099312.35 BB');
  assert.equal(bbPreset('900719925474099312345', '2.5', 0n, 9999999999999999999999n), '2251799813685248280862');
});
