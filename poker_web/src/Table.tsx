import { useEffect, useRef, useState } from 'react';

type Player = { id: string; stack: string; bet: string; paid: string; cards: string[]; folded: boolean };
type Member = { id: string; seat: number; mode: string; stack: string; leaving: boolean; topup: string | null; notice: string | null; npc_failures: number };
type Hand = { id: string; players: Player[]; board: string[]; street: string; actor: number | null; turn: number; pot: string; deadline: number | null; extensions: number; payouts: Record<string, string> | null; legal: { check?: boolean; fold?: boolean; call?: string; raise?: boolean; min_raise_to?: string; max_raise_to?: string } };
type State = { id: string; version: number; joined: boolean; closed: boolean; frozen?: boolean; control?: boolean; owner?: string; members?: Member[]; hand?: Hand | null; countdown?: number | null; time_bank?: number };
type Payload = { command_id: string; table_id: string; version: number; kind: string; control: string | null; hand_id?: string; turn?: number; action?: string; amount?: string; npc_id?: string };
const chips = (value: string) => BigInt(value).toLocaleString('zh-TW');
const suits: Record<string, string> = { c: '♣', d: '♦', h: '♥', s: '♠' };
const labels: Record<string, string> = { preflop: '翻牌前', flop: '翻牌', turn: '轉牌', river: '河牌', active: '在座', pending: '下手加入', sitout: '坐出' };
const errors: Record<string, string> = {
  stale_table_version: '桌況已更新，請依最新狀態重新操作。',
  stale_turn: '此行動機會已結束。', not_control_endpoint: '目前由另一個視窗操作。',
  action_deadline_passed: '行動時間已到，請等待伺服器處理。',
  funds_or_state_conflict: '籌碼不足或狀態已改變。', table_full: '牌桌已滿。',
  raise_below_minimum: '加注不足最低金額。', raise_not_allowed: '目前尚未重開加注權。',
  raise_out_of_range: '加注超過可用籌碼或低於目前下注。',
  topup_already_queued: '已有一筆待處理補碼。', buy_in_range: '帶入後桌上籌碼需為 2,000～10,000。',
};
function Cards({ cards }: { cards: string[] }) {
  return <span className="cards">{cards.length ? cards.map(card => <span key={card} className={card.endsWith('h') || card.endsWith('d') ? 'card red' : 'card'}>{card[0]}{suits[card[1]]}</span>) : <span className="card back">?</span>}</span>;
}

export function Table({ user, onClose }: { user: string; onClose: () => void }) {
  const [state, setState] = useState<State | null>(null);
  const [connected, setConnected] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
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
        if (message.state) setState(message.state);
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
      if (outcome.state) setState(outcome.state);
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
    void send({ command_id: crypto.randomUUID(), table_id: 'main', version: state.version, kind, control: control.current, ...extra });
  }
  const hand = state?.hand;
  const active = hand && !hand.payouts;
  const mine = state?.members?.find(m => m.id === user);
  const disabled = busy || !connected || !state?.control || !!pending.current || state.frozen;
  const act = (action: string, amount?: string) => command('act', { hand_id: hand?.id, turn: hand?.turn, action, ...(amount === undefined ? {} : { amount }) });
  return <section className="panel game" aria-label="德州撲克牌桌">
    <div className="panel-top"><h2>50 / 100 · 無限注德州撲克</h2><button className="text" onClick={onClose}>返回帳戶</button></div>
    <p role="status">{connected ? state?.joined ? state.control ? '已連線 · 此視窗可操作' : '已連線 · 另一個視窗持有操作權' : '已連線 · 等待入座' : '正在連線…'}</p>
    {error ? <p role="alert" className="message error">{error}</p> : null}
    {pending.current && !busy ? <button disabled={busy} onClick={() => pending.current && void send(pending.current)}>重送同一指令</button> : null}
    {state?.frozen ? <p role="alert">牌桌資金待恢復核對，暫停所有操作。</p> : null}
    {state?.closed ? <p>牌桌已關閉。</p> : null}
    {!state?.joined ? <div className="table-controls"><label>帶入籌碼 <input inputMode="numeric" value={amount} onChange={e => setAmount(e.target.value)} /></label><button disabled={busy || !connected || state?.closed || !!pending.current} onClick={() => command('join', { amount })}>入座（滿桌時接替 NPC）</button></div> : <>
      <p>{state.countdown ? `下一手倒數 ${Math.max(0, Math.ceil(state.countdown - now))} 秒` : active ? labels[hand.street] : '等待至少兩位參與者，其中一位真人'}</p>
      {hand ? <div className="board"><p>底池 {chips(hand.pot)}</p><Cards cards={hand.board} />
        {active && hand.deadline ? <p>行動剩餘 {Math.max(0, Math.ceil(hand.deadline - now))} 秒 · 已使用 {hand.extensions} 段補時</p> : null}
        {hand.payouts ? <p role="status">本手結算：{Object.entries(hand.payouts).filter(([, value]) => BigInt(value) > 0n).map(([id, value]) => `${id === user ? '你' : id.startsWith('npc:') ? 'NPC' : id} +${chips(value)}`).join(' · ')}</p> : null}
      </div> : null}
      <div className="seats">{state.members?.map(m => {
        const player = hand?.players.find(p => p.id === m.id);
        const acting = active && hand.actor !== null && hand.players[hand.actor]?.id === m.id;
        return <article className={acting ? 'seat acting' : 'seat'} key={m.id}>
          <strong>座位 {m.seat + 1} · {m.id === user ? '你' : m.id.startsWith('npc:') ? '固定 NPC' : m.id}</strong>
          <p>{chips(m.stack)} 籌碼 · {m.leaving ? '手後離桌' : labels[m.mode] ?? m.mode}</p>
          {player ? <><Cards cards={player.cards} /><p>{player.folded ? '已棄牌' : player.stack === '0' && active ? '全下' : acting ? '正在行動' : ''}</p></> : null}
          {m.topup ? <p>待補碼 {chips(m.topup)}</p> : null}
          {m.notice ? <p>{m.notice === 'topup_complete' ? '補碼完成' : m.notice === 'topup_rejected' ? '補碼失敗：請確認餘額與上限' : `NPC 異常：${m.notice}（連續 ${m.npc_failures} 次）`}</p> : null}
          {state.owner === user && m.id.startsWith('npc:') ? <button disabled={disabled || m.leaving} onClick={() => command('remove_npc', { npc_id: m.id })}>下手移除</button> : null}
        </article>;
      })}</div>
      {active && hand.legal.fold ? <div className="table-controls">
        <button disabled={disabled} onClick={() => act('fold')}>棄牌</button>
        {hand.legal.check ? <button disabled={disabled} onClick={() => act('check')}>過牌</button> : <button disabled={disabled} onClick={() => act('call')}>跟注 {chips(hand.legal.call ?? '0')}</button>}
        {hand.legal.raise ? <><label>加注至 <input inputMode="numeric" value={raise} onChange={e => setRaise(e.target.value)} /></label><button disabled={disabled} onClick={() => act('raise', raise)}>加注</button><button disabled={disabled} onClick={() => act('all_in')}>全下</button><small>最低 {hand.legal.min_raise_to} · 最高 {hand.legal.max_raise_to}</small></> : null}
      </div> : null}
      <p>你的補時池：{state.time_bank} 秒 · 每次最多自動使用四段，每段 5 秒</p>
      <div className="table-controls"><label>補碼金額 <input inputMode="numeric" value={amount} onChange={e => setAmount(e.target.value)} /></label><button disabled={disabled || !!mine?.topup || mine?.leaving} onClick={() => command('topup', { amount })}>補碼（手後生效）</button><button disabled={disabled || mine?.leaving} onClick={() => command(mine?.mode === 'sitout' ? 'sit_in' : 'sitout')}>{mine?.mode === 'sitout' ? '重新坐入' : '手後坐出'}</button><button disabled={disabled || mine?.leaving} onClick={() => command('leave')}>離桌並退回剩餘籌碼</button></div>
      {state.owner === user ? <div className="table-controls"><button disabled={disabled || state.closed} onClick={() => command('add_npc')}>新增固定 NPC</button><button disabled={disabled || state.closed} onClick={() => command('close')}>手後關桌</button></div> : null}
    </>}
  </section>;
}