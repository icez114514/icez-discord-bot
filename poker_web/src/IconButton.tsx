import { useEffect, useId, useLayoutEffect, useRef, useState, type ButtonHTMLAttributes } from 'react';
import { createPortal } from 'react-dom';

const paths = {
  back: 'M15 5 8 12l7 7M8 12h13',
  info: 'M12 11v6m0-10v1M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20',
  history: 'M3 11a9 9 0 1 1 2 7M3 4v7h7m2-5v6l4 2',
  volume: 'M11 4 5 9H2v6h3l6 5V4m4 4a6 6 0 0 1 0 8m3-11a10 10 0 0 1 0 14',
  muted: 'M11 4 5 9H2v6h3l6 5V4m5 5 6 6m0-6-6 6',
  settings: 'M4 7h16M4 17h16M8 4v6m8 4v6',
  person: 'M16 6a4 4 0 1 1-8 0 4 4 0 0 1 8 0M4 22v-3a8 8 0 0 1 16 0v3',
  stats: 'M4 20V10m8 10V4m8 16v-7',
  manage: 'M12 2 3 6v6c0 5 9 10 9 10s9-5 9-10V6L12 2m-4 10 3 3 5-6',
  log: 'M5 3h14v18H5V3m4 5h6m-6 4h6m-6 4h6',
  connected: 'M3 8a15 15 0 0 1 18 0M6 12a10 10 0 0 1 12 0m-9 4a5 5 0 0 1 6 0m-3 4h.01',
  warning: 'M12 3 2 21h20L12 3m0 6v5m0 3v1',
  clock: 'M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20m0 4v6l4 2',
  leave: 'M9 3H3v18h6m6-15 6 6-6 6m-7-6h13',
} as const;
export type IconName = keyof typeof paths;
type Props = Omit<ButtonHTMLAttributes<HTMLButtonElement>, 'children'> & { icon: IconName; label: string };

/** Shared mouse, keyboard and touch hints; a long press never activates the button. */
export function IconButton({ icon, label, onClick, className = '', ...props }: Props) {
  const ref = useRef<HTMLButtonElement>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const held = useRef(false);
  const touch = useRef(false);
  const origin = useRef({ x: 0, y: 0 });
  const [position, setPosition] = useState<{ left: number; top: number } | null>(null);
  const id = useId();
  const tooltip = useRef<HTMLSpanElement>(null);
  useLayoutEffect(() => {
    if (!position || !tooltip.current) return;
    const top = Math.max(8, Math.min(position.top, window.innerHeight - tooltip.current.getBoundingClientRect().height - 8));
    if (top !== position.top) setPosition({ ...position, top });
  }, [position]);
  const clearTimer = () => { clearTimeout(timer.current); timer.current = undefined; };
  const show = () => {
    const rect = ref.current?.getBoundingClientRect();
    if (rect) setPosition({ left: Math.max(8, Math.min(rect.left, window.innerWidth - 248)), top: Math.max(8, Math.min(rect.bottom + 7, window.innerHeight - 140)) });
  };
  useEffect(() => () => clearTimeout(timer.current), []);
  useEffect(() => {
    if (!position) return;
    const close = () => setPosition(null);
    const key = (event: KeyboardEvent) => { if (event.key === 'Escape') close(); };
    document.addEventListener('pointerdown', close);
    document.addEventListener('keydown', key);
    window.addEventListener('scroll', close, true);
    window.addEventListener('resize', close);
    return () => { document.removeEventListener('pointerdown', close); document.removeEventListener('keydown', key); window.removeEventListener('scroll', close, true); window.removeEventListener('resize', close); };
  }, [position]);
  return <>
    <button {...props} ref={ref} type="button" className={`icon-button ${className}`} aria-label={label} aria-describedby={position ? id : undefined}
      onPointerEnter={event => { if (event.pointerType === 'mouse') show(); }}
      onPointerLeave={() => { clearTimer(); if (!held.current) setPosition(null); }}
      onFocus={() => { if (!touch.current) show(); }} onBlur={() => setPosition(null)}
      onPointerDown={event => {
        held.current = false; touch.current = event.pointerType !== 'mouse';
        origin.current = { x: event.clientX, y: event.clientY }; clearTimer();
        if (touch.current) timer.current = setTimeout(() => { held.current = true; show(); }, 500);
      }}
      onPointerMove={event => { if (Math.hypot(event.clientX - origin.current.x, event.clientY - origin.current.y) > 10) clearTimer(); }}
      onPointerUp={() => { clearTimer(); touch.current = false; }} onPointerCancel={() => { clearTimer(); touch.current = false; setPosition(null); }}
      onContextMenu={event => { if (touch.current || held.current) event.preventDefault(); }}
      onKeyDown={event => { if (event.key === 'Enter' || event.key === ' ') { held.current = false; touch.current = false; } }}
      onClick={event => { if (held.current) { event.preventDefault(); return; } setPosition(null); onClick?.(event); }}>
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={paths[icon]} /></svg>
    </button>
    {position ? createPortal(<span ref={tooltip} className="icon-tooltip" id={id} role="tooltip" style={position}>{label}</span>, document.body) : null}
  </>;
}
