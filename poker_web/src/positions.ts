type Hand = { button: number; players: { id: string }[] };
/** Positions belong to the original participants, not the remaining unfolded players. */
export function handPositions(hand: Hand | null | undefined): Record<string, string> {
  if (!hand || hand.players.length < 2 || hand.players.length > 6 || !Number.isInteger(hand.button) || hand.button < 0 || hand.button >= hand.players.length) return {};
  const labels: Record<number, string[]> = {
    2: ['BTN / SB', 'BB'],
    3: ['BTN', 'SB', 'BB'],
    4: ['BTN', 'SB', 'BB', 'CO'],
    5: ['BTN', 'SB', 'BB', 'HJ', 'CO'],
    6: ['BTN', 'SB', 'BB', 'UTG', 'HJ', 'CO'],
  };
  return Object.fromEntries(hand.players.map((player, index) => [player.id, labels[hand.players.length][(index - hand.button + hand.players.length) % hand.players.length]]));
}
