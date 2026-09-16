import { clamp } from './betting.ts';

export function positiveInteger(value: unknown): value is string {
  return typeof value === 'string' && /^[0-9]+$/.test(value) && BigInt(value) > 0n;
}

export function stackDisplay(stack: string, blind: string | undefined, bb: boolean) {
  if (!bb || !positiveInteger(blind)) return BigInt(stack).toLocaleString('zh-TW');
  const scaled = BigInt(stack) * 100n, divisor = BigInt(blind);
  const rounded = (scaled + divisor / 2n) / divisor;
  const fraction = (rounded % 100n).toString().padStart(2, '0').replace(/0+$/, '');
  return `${scaled % divisor ? '≈' : ''}${rounded / 100n}${fraction ? '.' + fraction : ''} BB`;
}

export function ratio(value: string): [number, number] | null {
  const fraction = /^(\d{1,4})\/(\d{1,4})$/.exec(value);
  if (fraction) return +fraction[1] > 0 && +fraction[2] > 0 ? [+fraction[1], +fraction[2]] : null;
  if (!/^\d{1,4}(\.\d{1,2})?$/.test(value) || Number(value) <= 0) return null;
  const [whole, part = ''] = value.split('.');
  return [Number(whole + part), 10 ** part.length];
}

export function bbPreset(blind: string | undefined, multiple: string, minimum: bigint, maximum: bigint) {
  const parsed = ratio(multiple);
  if (!positiveInteger(blind) || !parsed) return null;
  return clamp(BigInt(blind) * BigInt(parsed[0]) / BigInt(parsed[1]), minimum, maximum).toString();
}

export type Preferences = { bb: boolean; fourColor: boolean; large: boolean; preflop: string[]; postflop: string[] };
const defaults: Preferences = { bb: false, fourColor: false, large: false, preflop: ['2', '2.5', '3', '4', '5'], postflop: ['1/3', '1/2', '2/3', '1', '2'] };
type Storage = Pick<globalThis.Storage, 'getItem' | 'setItem'>;
const validPresets = (value: unknown): value is string[] => Array.isArray(value) && value.length === 5 && value.every(v => typeof v === 'string' && ratio(v));
export function readPreferences(storage: Storage | undefined, user: string): Preferences {
  let saved;
  try { saved = JSON.parse(storage?.getItem('poker.table.v1:' + user) ?? '{}'); } catch { /* optional persistence */ }
  return {
    bb: saved?.bb === true, fourColor: saved?.fourColor === true, large: saved?.large === true,
    preflop: validPresets(saved?.preflop) ? saved.preflop : [...defaults.preflop],
    postflop: validPresets(saved?.postflop) ? saved.postflop : [...defaults.postflop],
  };
}
export function savePreferences(storage: Storage | undefined, user: string, value: Preferences) {
  try { if (!storage) return false; storage.setItem('poker.table.v1:' + user, JSON.stringify(value)); return true; } catch { return false; }
}
