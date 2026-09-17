/** Same suit/rank indexing used by casino_images.TableRenderer. */
export function casinoCard(card: string): string | undefined {
  if(card === "Xr" || card === "Xb") return `/assets/cards/casino/${card}.png`;
  const rank = 'A23456789TJQK'.indexOf(card[0]);
  const suit = 'shdc'.indexOf(card[1]);
  return card.length === 2 && rank >= 0 && suit >= 0 ? `/assets/cards/casino/${suit * 13 + rank}.png` : undefined;
}
