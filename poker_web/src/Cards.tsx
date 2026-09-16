import { casinoCard } from './casinoCard';

const suits: Record<string, string> = { c: '♣', d: '♦', h: '♥', s: '♠' };
export function Cards({ cards, slots = 2, hidden = false, reveal }: { cards: string[]; slots?: number; hidden?: boolean; reveal?: { id: string; count: number; from: number } }) {
  return <span className="cards">{Array.from({ length: slots }, (_, index) => {
    const card = cards[index];
    if (!card) return <span key={index} aria-label={hidden ? '未公開底牌' : '尚未發牌'} className={hidden ? 'card back casino-card' : 'card blank'}>{hidden ? <img className="casino-art" src="/assets/cards/casino/back.png" alt="" draggable={false} /> : '·'}</span>;
    const animated = !!reveal && index >= reveal.from && index < reveal.count;
    const delay = animated ? (index - reveal.from) * 50 : 0;
    const value = card[0] === 'T' ? '10' : card[0];
    return <span data-suit={card[1]} key={index + card + (animated ? reveal.id : "")} aria-label={`${value}${suits[card[1]]}`} className={`card casino-card ${animated ? "board-deal" : ""}`} style={{ animationDelay: delay + "ms" }}><span className="card-face" style={{ animationDelay: delay + "ms" }}><img className="casino-art" src={casinoCard(card)} alt="" draggable={false} /></span>{animated ? <img className="deal-back" style={{ animationDelay: delay + "ms" }} src="/assets/cards/casino/back.png" alt="" draggable={false} /> : null}</span>;
  })}</span>;
}
