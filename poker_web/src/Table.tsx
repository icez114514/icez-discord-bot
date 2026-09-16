import { useEffect, useRef, useState } from 'react';
import { Modal } from './Modal';
import { ThemePicker } from './Theme';

type Player = { id: string; stack: string; bet: string; paid: string; cards: string[]; folded: boolean };
type Member = { id: string; seat: number; mode: string; sitout: boolean; connected: boolean; expires: number | null; stack: string; leaving: boolean; topup: string | null; notice: string | null; npc_failures: number };
type Hand = { id: string; button: number; players: Player[]; board: string[]; street: string; actor: number | null; turn: number; pot: string; deadline: number | null; extensions: number; payouts: Record<string, string> | null; legal: { check?: boolean; fold?: boolean; call?: string; raise?: boolean; min_raise_to?: string; max_raise_to?: string } };
type State = { id: string; name?: string; private?: boolean; version: number; joined: boolean; closed: boolean; frozen?: boolean; control?: boolean; owner?: string; members?: Member[]; hand?: Hand | null; countdown?: number | null; time_bank?: number };
type Payload = { command_id: string; table_id: string; version: number; kind: string; control: string | null; hand_id?: string; turn?: number; action?: string; amount?: string; npc_id?: string };
const chips = (value: string) => BigInt(value).toLocaleString('zh-TW');
const suits: Record<string, string> = { c: '♣', d: '♦', h: '♥', s: '♠' };
const labels: Record<string, string> = { preflop: '翻牌前', flop: '翻牌', turn: '轉牌', river: '河牌', active: '在座', pending: '下手加入', sitout: '坐出' };
const errors: Record<string, string> = {
  topup_required: '桌上籌碼不足，請先補碼再重新坐入。',
  already_seated: '你已有座位，請返回目前牌桌。',
  table_unavailable: '牌桌不存在或邀請已失效。',
  topup_must_be_positive: '補碼請輸入大於零的整數。',
  login_required: '登入已撤銷，請重新登入。',
  stale_table_version: '桌況已更新，請依最新狀態重新操作。',
  stale_turn: '此行動機會已結束。', not_control_endpoint: '目前由另一個視窗操作。',
  action_deadline_passed: '行動時間已到，請等待伺服器處理。',
  funds_or_state_conflict: '籌碼不足或狀態已改變。', table_full: '牌桌已滿。',
  raise_below_minimum: '加注不足最低金額。', raise_not_allowed: '目前尚未重開加注權。',
  raise_out_of_range: '加注超過可用籌碼或低於目前下注。',
  topup_already_queued: '已有一筆待處理補碼。', buy_in_range: '帶入後桌上籌碼需為 2,000～10,000。',
};
function Cards({ cards, slots = 2, hidden = false }: { cards: string[]; slots?: number; hidden?: boolean }) {
  return <span className="cards">{Array.from({ length: slots }, (_, index) => {
    const card = cards[index];
    if (!card) return <span key={index} aria-label={hidden ? '未公開底牌' : '尚未發牌'} className={hidden ? 'card back' : 'card blank'}>{hidden ? '♠' : '·'}</span>;
    const value = card[0] === 'T' ? '10' : card[0];
    return <span key={index} aria-label={`${value}${suits[card[1]]}`} className={card.endsWith('h') || card.endsWith('d') ? 'card red' : 'card'}><b>{value}<small>{suits[card[1]]}</small></b><span>{suits[card[1]]}</span></span>;
  })}</span>;
}

export function Table({ user, onClose }: { user: string; onClose: () => void }) {
  const [state, setState] = useState<State | null>(null);
  const [connected, setConnected] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [confirm, setConfirm] = useState<Payload | null>(null);
  const [invite, setInvite] = useState('');
  const [inviteBusy, setInviteBusy] = useState(false);
  const rotation = useRef<object | null>(null);
  const [amount, setAmount] = useState('2000');
  const [raise, setRaise] = useState('200');
  const [now, setNow] = useState(Date.now() / 1000);
  const socketRef = useRef<WebSocket | null>(null);
  const control = useRef<string | null>(null);
  const pending = useRef<Payload | null>(null);
  useEffect(() => {
    let stopped = false;
    let retry: ReturnType<typeof setTimeout> | undefined;
    const attach = () => {
      const socket = new WebSocket(`${location.protocol === 'https:' ? 'wss:' : 'ws:'}//${location.host}/ws/table`);
      socketRef.current = socket;
      socket.onmessage = event => {
        const message = JSON.parse(event.data);
        if (message.connection) control.current = message.connection;
        if (message.state) setState(previous => !previous || previous.id !== message.state.id || message.state.version >= previous.version ? message.state : previous);
        setConnected(true);
      };
      socket.onclose = event => {
        control.current = null;
        setConnected(false);
        if (!stopped && event.code !== 4401) retry = setTimeout(attach, 1000);
        if (event.code === 4401) setError('登入已撤銷，請重新登入。');
      };
    };
    attach();
    const heartbeat = setInterval(() => {
      if (socketRef.current?.readyState === WebSocket.OPEN) socketRef.current.send(JSON.stringify({ type: 'heartbeat' }));
    }, 15000);
    const clock = setInterval(() => setNow(Date.now() / 1000), 250);
    const leave = () => {
      if (socketRef.current?.readyState === WebSocket.OPEN) socketRef.current.send(JSON.stringify({ type: 'leave' }));
    };
    window.addEventListener('pagehide', leave);
    return () => {
      stopped = true; clearTimeout(retry); clearInterval(heartbeat); clearInterval(clock);
      window.removeEventListener('pagehide', leave); leave(); socketRef.current?.close();
    };
  }, []);
  async function send(payload: Payload) {
    if (busy) return;
    setBusy(true); setError(''); pending.current = payload;
    try {
      const response = await fetch('/api/table/commands', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
      const outcome = await response.json();
      if (response.status >= 500) throw new Error();
      if (outcome.state) setState(previous => !previous || previous.id !== outcome.state.id || outcome.state.version >= previous.version ? outcome.state : previous);
      const failure = outcome.result?.error ?? outcome.error;
      if (failure) setError(errors[failure] ?? failure);
      else if (!response.ok) setError('指令無法處理，請檢查輸入。');
      pending.current = null;
      if (socketRef.current?.readyState === WebSocket.OPEN) socketRef.current.send(JSON.stringify({ type: 'heartbeat' }));
    } catch {
      setError('連線中斷，結果尚未確認；請重送同一指令。');
    } finally { setBusy(false); }
  }
  function command(kind: string, extra: Partial<Payload> = {}) {
    if (!state || pending.current) return;
    void send({ command_id: crypto.randomUUID(), table_id: state.id, version: state.version, kind, control: control.current, ...extra });
  }
  const hand = state?.hand;
  const active = hand && !hand.payouts;
  const mine = state?.members?.find(m => m.id === user);
  const disabled = busy || !connected || !state?.control || !!pending.current || state.frozen;
  const act = (action: string, amount?: string) => {
    if (!state || !hand) return;
    const payload: Payload = { command_id: crypto.randomUUID(), table_id: state.id, version: state.version, kind: 'act', control: control.current, hand_id: hand.id, turn: hand.turn, action, ...(amount === undefined ? {} : { amount }) };
    const player = hand.players.find(p => p.id === user);
    const allIn = action === 'all_in' || action === 'call' && player && BigInt(hand.legal.call ?? '0') >= BigInt(player.stack) || action === 'raise' && amount === hand.legal.max_raise_to;
    if (allIn) setConfirm(payload); else void send(payload);
  };
  async function invitation(reset = false) {
    if (inviteBusy) return;
    setInviteBusy(true); setError('');
    try {
      if (reset && !rotation.current) rotation.current = { command_id: crypto.randomUUID(), control: control.current };
      const response = await fetch('/api/table/invitation', reset ? { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(rotation.current) } : {});
      if (!response.ok) { if (response.status < 500) rotation.current = null; throw new Error(); }
      const data = await response.json();
      setInvite(`${location.origin}/#invite=${data.table_id}:${data.invitation}`); rotation.current = null;
    } catch { setError('邀請操作未完成，請重試同一操作。'); }
    finally { setInviteBusy(false); }
  }
  const playerName = (id: string) => id === user ? '你' : id.startsWith('npc:') ? '固定 NPC' : `玩家 ${id.slice(-4)}`;
  const seated = state?.members ?? [];
  const mySeat = mine?.seat ?? 0;
  const position = (seat: number) => ['s', 'sw', 'nw', 'n', 'ne', 'se'][(seat - mySeat + 6) % 6];
  return <section className="game" aria-label="德州撲克牌桌">
    <div className="panel-top"><div><h1>{state?.name ?? '牌桌'}</h1><p>50 / 100 · 無限注德州撲克{state?.private ? ' · 私人桌' : ''}</p></div><div className="table-tools"><ThemePicker /><button className="text" onClick={onClose}>返回大廳</button></div></div>
    <p role="status" className="connection">{connected ? state?.joined ? state.control ? '● 已連線 · 此視窗可操作' : '已連線 · 另一個視窗持有操作權' : '已離桌，請回大廳選擇牌桌。' : '連線中斷，正在恢復同桌…'}</p>
    {error ? <p role="alert" className="message error">{error}</p> : null}
    {pending.current && !busy ? <button onClick={() => pending.current && void send(pending.current)}>重送同一指令</button> : null}
    {state?.frozen ? <p role="alert">牌桌資金待恢復核對，暫停所有操作。</p> : null}
    {state?.closed ? <p>牌桌已關閉；當手完成後退回剩餘籌碼。</p> : null}
    {state?.joined ? <>
      <div className="table-scene"><div className="felt" aria-hidden="true" />
        <div className="board"><span className="pot-label">底池</span><strong className="pot">{chips(hand?.pot ?? '0')}</strong><Cards cards={hand?.board ?? []} slots={5} /><p>{state.countdown ? `下一手倒數 ${Math.max(0, Math.ceil(state.countdown - now))} 秒` : active ? labels[hand.street] : '等待下一手'}</p></div>
        {Array.from({ length: 6 }, (_, seat) => {
          const occupants = seated.filter(m => m.seat === seat);
          const m = occupants.find(m => hand?.players.some(p => p.id === m.id)) ?? occupants[0];
          if (!m) return <article key={seat} className={`seat empty ${position(seat)}`}>空位 {seat + 1}</article>;
          const player = hand?.players.find(p => p.id === m.id);
          const acting = active && hand.actor !== null && hand.players[hand.actor]?.id === m.id;
          const dealer = hand?.players[hand.button]?.id === m.id;
          return <article className={`seat ${position(seat)} ${acting ? 'acting' : ''} ${m.id === user ? 'hero-seat' : ''}`} key={seat}>
            <div className="seat-name"><span className="avatar" aria-hidden="true">{m.id === user ? '♠' : m.id.startsWith('npc:') ? '♟' : m.id.slice(-2)}</span><strong title={m.id}>{playerName(m.id)}</strong>{dealer ? <span className="dealer" aria-label="莊位">D</span> : null}</div>
            <b className="seat-stack">{chips(m.stack)}</b><small>{m.leaving ? '手後離桌' : m.sitout ? '手後坐出' : labels[m.mode] ?? m.mode}</small>
            {player ? <><Cards cards={player.cards} hidden={player.cards.length === 0} /><small>{player.folded ? '已棄牌' : player.stack === '0' && active ? '全下' : acting ? '正在行動' : `本街投入 ${chips(player.bet)}`}</small></> : null}
            {occupants.length > 1 ? <small>真人等待接替</small> : null}
          </article>;
        })}
      </div>
      {hand?.payouts ? <p role="status" className="settlement">本手結算：{Object.entries(hand.payouts).filter(([, value]) => BigInt(value) > 0n).map(([id, value]) => `${playerName(id)} 獲得 ${chips(value)}`).join(' · ')}</p> : null}
      <section className="action-panel" aria-label="牌桌操作">
        <div className="turn-line"><strong>{active && hand.legal.fold ? '輪到你行動' : active ? '等待其他玩家' : '等待至少兩位參與者，其中一位真人'}</strong><span>{active && hand.deadline ? `${Math.max(0, Math.ceil(hand.deadline - now))} 秒` : '—'}</span></div>
        {active && hand.legal.fold ? <div className="action-buttons">
          <button disabled={disabled} onClick={() => act('fold')}>棄牌</button>
          {hand.legal.check ? <button disabled={disabled} onClick={() => act('check')}>過牌</button> : <button disabled={disabled} onClick={() => act('call')}>跟注 {chips(hand.legal.call ?? '0')}</button>}
          {hand.legal.raise ? <><label>加注至<input aria-label="加注至" inputMode="numeric" value={raise} onChange={e => setRaise(e.target.value)} /></label><button disabled={disabled || !/^[1-9][0-9]*$/.test(raise)} onClick={() => act('raise', raise)}>加注</button><button disabled={disabled} onClick={() => act('all_in')}>全下</button><small className="raise-range">最低 {chips(hand.legal.min_raise_to ?? '0')} · 最高 {chips(hand.legal.max_raise_to ?? '0')}</small></> : null}
        </div> : null}
        <p className="bank">補時池 {state.time_bank} / 60 秒 · 每次 +5 秒，最多 4 次</p>
        <div className="table-controls"><label>補碼金額<input inputMode="numeric" value={amount} onChange={e => setAmount(e.target.value)} /></label><button disabled={disabled || !!mine?.topup || mine?.leaving} onClick={() => command('topup', { amount })}>申請手後補碼</button><button disabled={disabled || mine?.leaving || mine?.sitout} onClick={() => command(mine?.mode === 'sitout' ? 'sit_in' : 'sitout')}>{mine?.mode === 'sitout' ? '重新坐入' : mine?.sitout ? '已排隊坐出' : '手後坐出'}</button><button disabled={disabled || mine?.leaving} onClick={() => command('leave')}>手後離桌</button></div>
        {mine?.expires ? <p>座位保留 {Math.max(0, Math.ceil(mine.expires - now))} 秒</p> : null}
      </section>
      <section className="table-notices" aria-label="手間異動">{seated.filter(m => m.topup || m.notice || m.leaving || m.sitout || m.mode === 'pending').map(m => <p key={m.id}>{playerName(m.id)}：{m.topup ? `待補碼 ${chips(m.topup)}。` : ''}{m.leaving ? '已排隊手後離桌。' : m.sitout ? '已排隊手後坐出。' : m.mode === 'pending' ? '等待下一手加入。' : ''}{m.notice ? m.notice === 'topup_complete' ? '補碼完成。' : m.notice === 'topup_rejected' ? '補碼失敗：請確認可用餘額與上限。' : `NPC 暫時異常（連續 ${m.npc_failures} 次）。` : ''}</p>)}</section>
      {state.owner === user ? <details className="host-tools"><summary>房主選項</summary><div className="table-controls"><button disabled={disabled || state.closed} onClick={() => command('add_npc')}>新增固定 NPC</button>{seated.filter(m => m.id.startsWith('npc:')).map(m => <button key={m.id} disabled={disabled || m.leaving} onClick={() => command('remove_npc', { npc_id: m.id })}>移除座位 {m.seat + 1} NPC（手後）</button>)}{state.private ? <button disabled={inviteBusy} onClick={() => void invitation()}>私人桌邀請</button> : null}</div></details> : null}
    </> : <button onClick={onClose}>回到大廳</button>}
    {confirm ? <Modal title="確認全下" onClose={() => setConfirm(null)}><p>將投入本手所有剩餘籌碼。確認後無法收回。</p><div className="table-controls"><button onClick={() => setConfirm(null)}>取消</button><button disabled={disabled || hand?.id !== confirm.hand_id || hand?.turn !== confirm.turn} onClick={() => { const payload = confirm; setConfirm(null); void send(payload); }}>確認全下</button></div></Modal> : null}
    {invite ? <Modal title="私人桌邀請" onClose={() => setInvite('')}><p>持有效邀請的已登入成員可入座；重設後舊連結立即失效。</p><label>邀請連結<input readOnly value={invite} onFocus={event => event.target.select()} /></label><div className="table-controls"><button onClick={() => void navigator.clipboard.writeText(invite).catch(() => setError('請選取邀請連結並手動複製。'))}>複製邀請</button><button disabled={disabled || inviteBusy} onClick={() => void invitation(true)}>重設邀請</button></div></Modal> : null}
  </section>;
}
