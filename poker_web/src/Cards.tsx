const suits: Record<string, string> = { c: '♣', d: '♦', h: '♥', s: '♠' };
export function Cards({ cards, slots = 2, hidden = false }: { cards: string[]; slots?: number; hidden?: boolean }) {
  return <span className="cards">{Array.from({ length: slots }, (_, index) => {
    const card = cards[index];
    if (!card) return <span data-suit={card?.[1]} key={index} aria-label={hidden ? '未公開底牌' : '尚未發牌'} className={hidden ? 'card back' : 'card blank'}>{hidden ? '♠' : '·'}</span>;
    const value = card[0] === 'T' ? '10' : card[0];
    return <span data-suit={card?.[1]} key={index} aria-label={`${value}${suits[card[1]]}`} className={card.endsWith('h') || card.endsWith('d') ? 'card red' : 'card'}><b>{value}<small>{suits[card[1]]}</small></b><span>{suits[card[1]]}</span></span>;
  })}</span>;
}

