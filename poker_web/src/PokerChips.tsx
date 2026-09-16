import { chipStacks } from './chipStacks';
/** Bounded decorative piles; the adjacent number remains the exact total. */
export function PokerChips({ amount }: { amount: string }) {
  return <span className="poker-chips" aria-hidden="true">{chipStacks(amount).map(chip => <svg key={chip.value.toString()} className="chip-pile" viewBox="0 0 46 48" data-denomination={chip.value.toString()} data-count={chip.count.toString()}>
    <ellipse cx="23" cy="42" rx="21" ry="5" fill="#000" opacity=".3" />
    {Array.from({ length: chip.visible }, (_, index) => 34 - index * 5).map(y => <g key={y}>
      <ellipse cx="23" cy={y + 4} rx="20" ry="10" fill={chip.edge} stroke="#24231e" />
      <path d={`M5 ${y}v5 M14 ${y + 7}v5 M30 ${y + 7}v5 M41 ${y}v5`} stroke="#e8d9bd" strokeWidth="4" />
      <ellipse cx="23" cy={y} rx="20" ry="10" fill={chip.color} stroke="#efcf9e" />
      <ellipse cx="23" cy={y} rx="17" ry="8" fill="none" stroke="#f6e6c9" strokeWidth="3" strokeDasharray="6 7" />
      <ellipse cx="23" cy={y} rx="12" ry="6" fill={chip.edge} stroke="#eab68d" strokeWidth=".8" />
      <text x="23" y={y + 3} textAnchor="middle" fill="#fff7df" fontSize="8" fontWeight="bold">{chip.value.toString()}</text>
    </g>)}
  </svg>)}</span>;
}
