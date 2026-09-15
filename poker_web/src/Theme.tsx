import { createContext, useContext, useEffect, useRef, useState, type ReactNode } from 'react';
import { Modal } from './Modal';

export const themes = [
  { id: 'classic_walnut', name: '典藏胡桃', material: '胡桃木・深綠毛氈・古銅細圈' },
  { id: 'midnight_oak', name: '墨藍橡木', material: '橡木・墨藍毛氈・銀銅細節' },
  { id: 'burgundy_leather', name: '酒紅皮革', material: '深木・酒紅桌面・皮革縫線' },
] as const;
type Theme = typeof themes[number]['id'];
const normalize = (value: string): Theme => themes.find(t => t.id === value)?.id ?? 'classic_walnut';
const Context = createContext({ theme: 'classic_walnut' as Theme, select: (_theme: Theme) => {}, notice: '' });

export function ThemeProvider({ user, children }: { user?: string; children: ReactNode }) {
  const [theme, setTheme] = useState<Theme>('classic_walnut');
  const [notice, setNotice] = useState('');
  const revision = useRef(0);
  const queue = useRef(Promise.resolve());
  useEffect(() => {
    const controller = new AbortController();
    const initial = ++revision.current;
    setTheme('classic_walnut'); setNotice('');
    if (user) void fetch('/api/preferences', { signal: controller.signal }).then(async response => {
      if (!response.ok) throw new Error();
      const data = await response.json();
      if (revision.current === initial) setTheme(normalize(data.theme));
    }).catch(() => { if (!controller.signal.aborted && revision.current === initial) setNotice('無法讀取外觀偏好，暫用典藏胡桃。'); });
    return () => controller.abort();
  }, [user]);
  useEffect(() => { document.documentElement.dataset.theme = theme; }, [theme]);
  function select(next: Theme) {
    setTheme(next); setNotice('');
    const selected = ++revision.current;
    queue.current = queue.current.then(async () => {
      try {
        const response = await fetch('/api/preferences', { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ theme: next }) });
        if (!response.ok) throw new Error();
      } catch { if (selected === revision.current) setNotice('主題已套用，但未儲存；請再次選取以重試。'); }
    });
  }
  return <Context.Provider value={{ theme, select, notice }}>{children}</Context.Provider>;
}

export function ThemePicker() {
  const { theme, select, notice } = useContext(Context);
  const [open, setOpen] = useState(false);
  return <><button className="text" onClick={() => setOpen(true)}>外觀主題</button>
    {notice ? <p role="status" className="message">{notice}</p> : null}
    {open ? <Modal title="外觀主題" onClose={() => setOpen(false)}><p>只改變你的畫面，隨時可切換。</p>
      {notice ? <p role="status" className="message">{notice}</p> : null}
      <div className="theme-options">{themes.map(t => <button className="theme-option" key={t.id} aria-pressed={theme === t.id} onClick={() => select(t.id)}>
        <span className={`theme-preview ${t.id}`} aria-hidden="true"><span>♠</span></span><strong>{t.name}</strong><small>{t.material}</small><span>{theme === t.id ? '目前選取' : '選用主題'}</span>
      </button>)}</div></Modal> : null}
  </>;
}
