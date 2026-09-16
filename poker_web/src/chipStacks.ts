// House denominations follow common casino colors; high values are house-specific.
export const denominations = [
  { value: 5000n, color: '#ce7432', edge: '#794016' },
  { value: 1000n, color: '#dfb841', edge: '#876a20' },
  { value: 500n, color: '#8a58aa', edge: '#4f2a68' },
  { value: 100n, color: '#343b43', edge: '#151a20' },
  { value: 25n, color: '#278765', edge: '#14543d' },
  { value: 5n, color: '#bd3c49', edge: '#701e28' },
  { value: 1n, color: '#e6e1d3', edge: '#929185' },
] as const;
export function chipStacks(amount: string) {
  let remaining = BigInt(amount);
  return denominations.flatMap(chip => {
    const count = remaining / chip.value;
    remaining %= chip.value;
    return count > 0n ? [{ ...chip, count, visible: Number(count > 5n ? 5n : count) }] : [];
  });
}
export function collectedPot(pot: string, bets: string[], settled: boolean) {
  if (settled) return '0';
  const amount = BigInt(pot) - bets.reduce((sum, bet) => sum + BigInt(bet), 0n);
  return (amount > 0n ? amount : 0n).toString();
}
