import { useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
import './style.css';

type Account = {
  user_id: string; available: string; table: string; in_flight: string; settled: string;
  subsidy: { eligible: boolean; amount: string; day: string; reason: string | null };
};
const format = (value: string) => BigInt(value).toLocaleString('zh-TW');
const reasons: Record<string, string> = {
  unsettled_hand: '尚有未結算手牌或待恢復籌碼，完成結算後再領取。',
  already_claimed: '本日已領取，明日 04:00 更新資格。',
  assets_at_least_5000: '可用與桌上籌碼合計達 5,000，目前無需補助。',
};

function App() {
  const [environment, setEnvironment] = useState('');
  const [account, setAccount] = useState<Account | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  async function refresh(signal?: AbortSignal) {
    try {
      const response = await fetch('/api/account', { signal, credentials: 'same-origin' });
      if (response.status === 401) { setAccount(null); return; }
      if (!response.ok) throw new Error('暫時無法讀取帳戶，請稍後再試。');
      setAccount(await response.json());
      setError('');
    } catch (cause) {
      if (cause instanceof Error && cause.name !== 'AbortError') setError(cause.message);
    } finally { if (!signal?.aborted) setLoading(false); }
  }
  useEffect(() => {
    const controller = new AbortController();
    void refresh(controller.signal);
    void fetch('/api/environment', { signal: controller.signal }).then(r => r.json()).then((data: { environment: string }) => setEnvironment(data.environment)).catch(() => {});
    const onFocus = () => { void refresh(controller.signal); };
    window.addEventListener('focus', onFocus);
    return () => { controller.abort(); window.removeEventListener('focus', onFocus); };
  }, []);
  async function claim() {
    if (busy) return;
    setBusy(true); setError(''); setNotice('');
    try {
      const response = await fetch('/api/subsidy', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ command_id: crypto.randomUUID() }) });
      if (response.status === 401) { setAccount(null); throw new Error('登入已撤銷，請重新登入。'); }
      if (!response.ok) { await refresh(); throw new Error('未能領取補助，請確認最新資格後重試。'); }
      setAccount(await response.json()); setNotice('補助已入帳。');
    } catch (cause) { setError(cause instanceof Error ? cause.message : '連線失敗，請稍後重試。'); }
    finally { setBusy(false); }
  }
  async function logout() {
    setBusy(true); setError('');
    try {
      const response = await fetch('/auth/logout', { method: 'POST' });
      if (!response.ok && response.status !== 401) throw new Error('登出失敗，請稍後重試。');
      setAccount(null); setNotice('已登出所有裝置。');
    } catch (cause) { setError(cause instanceof Error ? cause.message : '連線失敗。'); }
    finally { setBusy(false); }
  }
  return <main>
    <header><a className="brand" href="/" aria-label="ICEZ 德州撲克首頁"><span aria-hidden="true">♠</span> ICEZ <small>POKER CLUB</small></a><span className="tag">社群專屬</span></header>
    {environment === 'test' ? <p className="message" role="status">測試環境 · 模擬 Discord 身分，非真實 OAuth 驗收。</p> : null}
    <section className="intro"><p className="eyebrow">YOUR POKER ACCOUNT</p><h1>下一手，從這裡開始。</h1><p>你的德撲籌碼與每日補助，都在這裡。</p></section>
    {error ? <div className="message error" role="alert">{error} <button className="text" onClick={() => void refresh()}>重新整理</button></div> : null}
    {notice ? <p className="message" role="status">{notice}</p> : null}
    {loading ? <section className="panel" aria-busy="true">正在讀取帳戶…</section> : account ? <>
      <section className="panel balance"><div className="panel-top"><span>已結算總資產</span><span className="unit">德撲籌碼</span></div><strong className="total">{format(account.settled)}</strong><div className="balances"><div><span>可用籌碼</span><strong>{format(account.available)}</strong></div><div><span>桌上籌碼</span><strong>{format(account.table)}</strong></div><div><span>在途底池</span><strong>{format(account.in_flight)}</strong></div></div><p className="caption">下注中的籌碼會在牌局結算後反映至總資產。</p></section>
      <section className="panel subsidy"><div><p className="eyebrow">DAILY SUPPORT</p><h2>每日補助</h2><p>{account.subsidy.eligible ? `可領取 ${format(account.subsidy.amount)} 籌碼，補足至 5,000。` : reasons[account.subsidy.reason ?? ''] ?? '目前無法領取，請重新整理。'}</p><small>台灣時間每日 04:00 更新 · 未領不累積</small></div><button disabled={busy || !account.subsidy.eligible} onClick={() => void claim()}>{busy ? '處理中…' : account.subsidy.eligible ? '領取補助' : '目前不可領取'}</button></section>
      <div className="account-footer"><span>Discord ID <code>{account.user_id}</code></span><button className="text" disabled={busy} onClick={() => void logout()}>登出所有裝置</button></div>
    </> : <section className="panel login"><span className="suit" aria-hidden="true">♠</span><h2>歡迎回到牌桌旁</h2><p>使用 Discord 登入，確認社群資格後<br/>即可查看你的獨立德撲帳戶。</p><a className="button" href="/auth/login">使用 Discord 登入 <span aria-hidden="true">↗</span></a><small>首次建立帳戶獲得 50,000 德撲籌碼。</small></section>}
    <footer><span>ICEZ COMMUNITY · POKER</span><p>德撲籌碼與水晶分開計算。</p></footer>
  </main>;
}
createRoot(document.getElementById('root')!).render(<App />);