import { useEffect, useRef, useState } from 'react';
import { Modal } from './Modal';

type Room = { id: string; name: string; version: number; seats: number; limit: number };
type LobbyState = { tables: Room[]; current_table: string | null };
const errors: Record<string, string> = {
  table_capacity: '目前兩張活動桌皆已使用，請加入公開桌或稍後開桌。', already_seated: '你已有座位，請返回目前牌桌。',
  table_full: '牌桌已滿，請選擇其他牌桌。', table_unavailable: '邀請已失效或牌桌不存在，請向房主取得新連結。',
  stale_table_version: '桌況已更新，請重新確認入座。', buy_in_range: '帶入須為 2,000～10,000。',
  funds_or_state_conflict: '籌碼不足或桌況已變更，請重新確認。', login_required: '請重新登入。',
};
export function Lobby({ onEnter }: { onEnter: () => void }) {
  const [lobby, setLobby] = useState<LobbyState | null>(null);
  const [dialog, setDialog] = useState<Room | 'create' | 'invite' | null>(null);
  const [name, setName] = useState('朋友小聚');
  const [privateTable, setPrivate] = useState(false);
  const [amount, setAmount] = useState('2000');
  const [link, setLink] = useState(() => location.hash.startsWith('#invite=') ? location.href : '');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [uncertain, setUncertain] = useState(false);
  const pending = useRef<{ url: string; body: object } | null>(null);
  async function refresh() {
    try { const response = await fetch('/api/tables'); if (!response.ok) throw new Error(); setLobby(await response.json()); }
    catch { setError('無法更新大廳，請稍後重試。'); }
  }
  useEffect(() => {
    void refresh(); const interval = setInterval(() => void refresh(), 5000);
    if (location.hash.startsWith('#invite=')) setDialog('invite');
    return () => clearInterval(interval);
  }, []);
  async function submit() {
    if (busy) return;
    setBusy(true); setError('');
    try {
      if (!pending.current) {
        if (!/^[1-9][0-9]*$/.test(amount) || BigInt(amount) < 2000n || BigInt(amount) > 10000n) throw new Error('帶入須為 2,000～10,000 的整數。');
        if (dialog === 'create') pending.current = { url: '/api/tables', body: { command_id: crypto.randomUUID(), name, private: privateTable, amount } };
        else {
          let room = dialog as Room;
          let invitation: string | undefined;
          if (dialog === 'invite') {
            const url = new URL(link);
            const parts = new URLSearchParams(url.hash.slice(1)).get('invite')?.split(':');
            if (!parts || parts.length !== 2) throw new Error('請貼上完整私人桌邀請連結。');
            const [id, secret] = parts; invitation = secret;
            const preview = await fetch(`/api/table?table_id=${encodeURIComponent(id)}`, { headers: { 'x-table-invitation': secret } });
            if (!preview.ok) throw new Error(errors.table_unavailable);
            room = await preview.json();
          }
          pending.current = { url: '/api/table/commands', body: { command_id: crypto.randomUUID(), table_id: room.id, version: room.version, kind: 'join', amount, ...(invitation ? { invitation } : {}) } };
        }
      }
      const response = await fetch(pending.current.url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(pending.current.body) });
      const result = await response.json();
      if (response.status >= 500) { setUncertain(true); throw new Error('結果尚未確認，請重送同一申請。'); }
      pending.current = null; setUncertain(false);
      if (!response.ok) throw new Error(errors[result.result?.error ?? result.error] ?? '無法入座，請重新整理大廳後重試。');
      history.replaceState(null, '', location.pathname); setDialog(null); onEnter();
    } catch (cause) { if (pending.current) setUncertain(true); setError(cause instanceof Error ? cause.message : '連線中斷，請重送同一申請。'); }
    finally { setBusy(false); void refresh(); }
  }
  return <section className="lobby" aria-label="牌桌大廳"><div className="panel-top"><div><h1>今晚，留一個位置。</h1><p>50 / 100 盲注 · 每桌最多六位</p></div><button onClick={() => { setError(''); setDialog('create'); }}>開新桌</button></div>
    {error && !dialog ? <p className="message error" role="alert">{error}</p> : null}
    {lobby?.current_table ? <div className="message">你已有保留座位。<button onClick={onEnter}>返回目前牌桌</button></div> : null}
    <div className="room-list">{lobby?.tables.map(room => <article className="room" key={room.id}><div className="room-table" aria-hidden="true">♠</div><h2>{room.name}</h2><p>{room.seats} / {room.limit} 席 · 公開桌</p><button disabled={!!lobby.current_table} onClick={() => { setError(''); setDialog(room); }}>帶入並入座</button></article>)}</div>
    {lobby && !lobby.tables.length ? <p className="empty-lobby">目前沒有公開桌，開一桌邀朋友一起玩。</p> : null}
    <button className="text" onClick={() => { setError(''); setDialog('invite'); }}>使用私人桌邀請</button>
    {dialog ? <Modal title={dialog === 'create' ? '開桌並入座' : dialog === 'invite' ? '私人桌邀請' : dialog.name} onClose={() => { if (!busy && !uncertain) setDialog(null); }}>
      <form onSubmit={event => { event.preventDefault(); void submit(); }}>
        {dialog === 'create' ? <><label>牌桌名稱<input maxLength={40} required value={name} disabled={busy || uncertain} onChange={event => setName(event.target.value)} /></label><label className="check"><input type="checkbox" checked={privateTable} disabled={busy || uncertain} onChange={event => setPrivate(event.target.checked)} />私人桌（只接受邀請）</label></> : null}
        {dialog === 'invite' ? <label>邀請連結<input type="url" required value={link} disabled={busy || uncertain} onChange={event => setLink(event.target.value)} /></label> : null}
        <label>帶入籌碼<input inputMode="numeric" required value={amount} disabled={busy || uncertain} onChange={event => setAmount(event.target.value)} /></label><p>帶入 2,000～10,000，從可用籌碼扣除。</p>
        {error ? <p role="alert" className="message error">{error}</p> : null}
        <button type="submit" disabled={busy}>{busy ? '正在確認…' : uncertain ? '重送同一申請' : '確認帶入'}</button>
      </form></Modal> : null}
  </section>;
}
