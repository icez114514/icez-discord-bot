export function clamp(value: bigint, minimum: bigint, maximum: bigint) {
  return value < minimum ? minimum : value > maximum ? maximum : value;
}
export function potPreset(pot: string, call: string, bet: string, numerator: number, denominator: number, minimum: bigint, maximum: bigint) {
  const afterCall = BigInt(pot) + BigInt(call);
  return clamp(BigInt(bet) + BigInt(call) + afterCall * BigInt(numerator) / BigInt(denominator), minimum, maximum).toString();
}
export function sliderAmount(position: number, minimum: bigint, maximum: bigint) {
  return minimum + (maximum - minimum) * BigInt(Math.round(position)) / 1000n;
}
