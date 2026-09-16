import { casinoCard } from './casinoCard';

const suits: Record<string, string> = { c: '♣', d: '♦', h: '♥', s: '♠' };
export function Cards({ cards, slots = 2, hidden = false }: { cards: string[]; slots?: number; hidden?: boolean }) {
  return <span className="cards">{Array.from({ length: slots }, (_, index) => {
    const card = cards[index];
    if (!card) return <span key={index} aria-label={hidden ? '未公開底牌' : '尚未發牌'} className={hidden ? 'card back casino-card' : 'card blank'}>{hidden ? <img className="casino-art" src="/assets/cards/casino/back.png" alt="" draggable={false} /> : '·'}</span>;
    const value = card[0] === 'T' ? '10' : card[0];
    return <span data-suit={card[1]} key={index} aria-label={`${value}${suits[card[1]]}`} className="card casino-card"><img className="casino-art" src={casinoCard(card)} alt="" draggable={false} /></span>;
  })}</span>;
}
