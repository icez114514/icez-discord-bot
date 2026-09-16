/** Decorative clay-style stack; the adjacent text remains the exact amount. */
export function PokerChips() {
  return <svg className="poker-chips" viewBox="0 0 46 40" aria-hidden="true">
    <ellipse cx="23" cy="34" rx="21" ry="5" fill="#000" opacity=".3" />
    {[26, 21, 16].map(y => <g key={y}>
      <ellipse cx="23" cy={y + 4} rx="20" ry="10" fill="#701e28" stroke="#3e1019" />
      <path d={`M5 ${y}v5 M14 ${y + 7}v5 M30 ${y + 7}v5 M41 ${y}v5`} stroke="#e8d9bd" strokeWidth="4" />
      <ellipse cx="23" cy={y} rx="20" ry="10" fill="#bd3c49" stroke="#efcf9e" strokeWidth="1" />
      <ellipse cx="23" cy={y} rx="17" ry="8" fill="none" stroke="#f6e6c9" strokeWidth="3" strokeDasharray="6 7" />
      <ellipse cx="23" cy={y} rx="12" ry="6" fill="#8f2533" stroke="#eab68d" strokeWidth=".8" />
      <path d={`M23 ${y - 4}l4 4-4 4-4-4z`} fill="#f3dab1" />
    </g>)}
  </svg>;
}
