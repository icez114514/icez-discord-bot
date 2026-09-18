export function clamp(value: bigint, minimum: bigint, maximum: bigint) {
  return value < minimum ? minimum : value > maximum ? maximum : value;
}
export function potPreset(pot: string, call: string, bet: string, numerator: number, denominator: number, minimum: bigint, maximum: bigint) {
  const afterCall = BigInt(pot) + BigInt(call);
  return raiseAmount(BigInt(bet) + BigInt(call) + afterCall * BigInt(numerator) / BigInt(denominator), minimum, maximum).toString();
}
export function sliderAmount(position: number, minimum: bigint, maximum: bigint) {
  return raiseAmount(minimum + (maximum - minimum) * BigInt(Math.round(position)) / 1000n, minimum, maximum);
}

// Ordinary raises use 50-chip increments; the exact stack remains a legal all-in.
export function raiseAmount(value: bigint, minimum: bigint, maximum: bigint) {
  if (value >= maximum) return maximum;
  const first = ((minimum + 49n) / 50n) * 50n;
  return clamp(value / 50n * 50n, first < maximum ? first : maximum, maximum);
}
export function validRaise(value: bigint, minimum: bigint, maximum: bigint) {
  return value >= minimum && value <= maximum && (value % 50n === 0n || value === maximum);
}
export function stepRaise(value: bigint, direction: number, minimum: bigint, maximum: bigint) {
  return raiseAmount(direction > 0 ? (value / 50n + 1n) * 50n : (value - 1n) / 50n * 50n, minimum, maximum);
}
