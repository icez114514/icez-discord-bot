import { useEffect, useRef, useState, useSyncExternalStore } from 'react';
import { Modal } from './Modal';
import { ThemePicker } from './Theme';
import { clamp, potPreset, sliderAmount } from './betting';
import { sound } from './sound';
import { actionLabel, useTablePresentation } from './tablePresentation';
import { ChipFlights, SettlementDetails, type Settlement } from './TableEffects';
import { SoundSettings } from './SoundSettings';
import { PlayerAvatar, usePlayerProfiles } from './PlayerProfiles';
import './table.css';

type Player = { id: string; stack: string; bet: string; paid: string; cards: string[]; folded: boolean };
type Member = { id: string; seat: number; mode: string; sitout: boolean; connected: boolean; expires: number | null; stack: string; leaving: boolean; topup: string | null; notice: string | null; npc_failures: number };
type Hand = { settlement?: Settlement | null; id: string; button: number; players: Player[]; board: string[]; street: string; actor: number | null; turn: number; pot: string; deadline: number | null; extensions: number; payouts: Record<string, string> | null; legal: { check?: boolean; fold?: boolean; call?: string; raise?: boolean; min_raise_to?: string; max_raise_to?: string } };
type State = import('./tableAudio').EventState & { id: string; name?: string; private?: boolean; version: number; joined: boolean; closed: boolean; frozen?: boolean; control?: boolean; owner?: string; members?: Member[]; hand?: Hand | null; countdown?: number | null; time_bank?: number };
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
  const [raiseDraft, setRaiseDraft] = useState({ turn: '', value: '' });
  const [options, setOptions] = useState(false);
  const [info, setInfo] = useState<'hand' | 'log' | null>(null);
  const [log, setLog] = useState<string[]>([]);
  const prefs = useSyncExternalStore(sound.subscribe, sound.preferences);
  const muted = prefs.muted;
  const presentation = useTablePresentation(user);
  const latest = useRef<State | null>(null);
  const scene = useRef<HTMLDivElement | null>(null);
  const tick = useRef('');
  const [now, setNow] = useState(Date.now() / 1000);
  const socketRef = useRef<WebSocket | null>(null);
  const control = useRef<string | null>(null);
  const pending = useRef<Payload | null>(null);
  function accept(next: State, baseline = false) {
    const prior = latest.current;
    if (prior?.id === next.id && next.version < prior.version) return;
    latest.current = next;
    const events = presentation.receive(next, baseline);
    const lines = events.flatMap(event => {
      if (event.kind === 'action') return [(event.user === user ? '你' : '座上玩家') + ' · ' + actionLabel(event)];
      if (event.kind === 'payout' || event.kind === 'refund') return [(event.user === user ? '你' : '座上玩家') + (event.kind === 'refund' ? ' 退款 ' : ' 派彩 ') + chips(event.amount ?? '0')];
      if (event.kind === 'board') return [labels[(event as { street?: string }).street ?? ''] ?? '公共牌已發出'];
      return [];
    });
    if (prior && prior.id !== next.id) setLog(lines);
    else if (lines.length) setLog(old => [...old, ...lines].slice(-80));
    setState(next);
  }
  useEffect(() => {
    let stopped = false;
    let retry: ReturnType<typeof setTimeout> | undefined;
    const attach = () => {
      const socket = new WebSocket(`${location.protocol === 'https:' ? 'wss:' : 'ws:'}//${location.host}/ws/table`);
      socketRef.current = socket;
      socket.onmessage = event => {
        const message = JSON.parse(event.data);
        if (message.connection) control.current = message.connection;
        if (message.state) accept(message.state, message.type === 'ready');
        setConnected(true);
      };
      socket.onclose = event => {
        control.current = null;
        presentation.reset();
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
      if (outcome.state) accept(outcome.state, socketRef.current?.readyState !== WebSocket.OPEN);
      const failure = outcome.result?.error ?? outcome.error;
      presentation.result(payload.command_id, !!failure || !response.ok);
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
  const memberIds = (state?.members ?? []).filter(m => !m.id.startsWith('npc:')).map(m => m.id).sort().join(',');
  const profiles = usePlayerProfiles(state?.joined ? state.id : undefined, memberIds);
  const hand = state?.hand;
  const active = hand && !hand.payouts;
  const settlement = hand?.settlement;
  const refundTotal = Object.values(settlement?.refunds ?? {}).reduce((n, a) => n + BigInt(a), 0n);
  const awardTotal = (settlement?.pots ?? []).reduce((n, pot) => n + BigInt(pot.amount), 0n);
  const mine = state?.members?.find(m => m.id === user);
  const disabled = busy || !connected || !state?.control || !!pending.current || state.frozen;
  const turnKey = hand ? `${hand.id}:${hand.turn}` : '';
  const maximum = BigInt(hand?.legal.max_raise_to ?? '0');
  const minimum = clamp(BigInt(hand?.legal.min_raise_to ?? '0'), 0n, maximum);
  const raise = raiseDraft.turn === turnKey ? raiseDraft.value : minimum.toString();
  const raiseValid = /^[0-9]+$/.test(raise) && BigInt(raise) >= minimum && BigInt(raise) <= maximum;
  const raiseValue = raiseValid ? BigInt(raise) : minimum;
  const setRaise = (value: string) => setRaiseDraft({ turn: turnKey, value });
  const ownTurn = !!(active && hand.legal.fold && (!hand.deadline || hand.deadline > now));
  const canRaise = ownTurn && !!hand?.legal.raise && !disabled;
  const seconds = active && hand.deadline ? Math.max(0, Math.ceil(hand.deadline - now)) : 0;
  const ownPlayer = hand?.players.find(p => p.id === user);
  const betLabel = hand?.players.some(p => BigInt(p.bet) > 0n) ? '加注至' : '下注';
  useEffect(() => {
    const key = `${turnKey}:${hand?.extensions}:${seconds}`;
    if (tick.current === key) return;
    tick.current = key;
    if (ownTurn && connected && state?.control && !state.frozen && seconds > 0 && seconds <= 5) void sound.play('tick');
  }, [seconds, turnKey, hand?.extensions, ownTurn, connected, state?.control, state?.frozen]);
  useEffect(() => () => sound.stop(), []);
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
  const playerName = (id: string) => id.startsWith('npc:') ? '固定 NPC' : profiles[id]?.display_name ?? '玩家';
  const seated = state?.members ?? [];
  const mySeat = mine?.seat ?? 0;
  const position = (seat: number) => ['s', 'sw', 'nw', 'n', 'ne', 'se'][(seat - mySeat + 6) % 6];
  return <section className={prefs.reduced ? 'game reduced-motion' : 'game'} aria-label="德州撲克牌桌">
    <div className="game-toolbar"><button className="back-button" onClick={onClose} aria-label="返回大廳" title="返回大廳（保留座位）">↶</button><div className="table-title"><h1>{state?.name ?? '牌桌'}</h1><small>50 / 100 · 無限注德州撲克{state?.private ? ' · 私人桌' : ''}</small></div><div className="table-tools"><button className="text" aria-pressed={!muted} onClick={() => sound.mute(!muted)} aria-label={muted ? '開啟音效' : '關閉音效'}>{muted ? '音效：關' : '音效：開'}</button><button className="text" onClick={() => setOptions(true)}>牌桌選項</button></div></div>
    <p role="status" className="connection">{connected ? state?.joined ? state.control ? '● 已連線 · 此視窗可操作' : '已連線 · 另一個視窗持有操作權' : '已離桌，請回大廳選擇牌桌。' : '連線中斷，正在恢復同桌…'}</p>
    {error ? <p role="alert" className="message error">{error}</p> : null}
    {pending.current && !busy ? <button onClick={() => pending.current && void send(pending.current)}>重送同一指令</button> : null}
    {state?.frozen ? <p role="alert">牌桌資金待恢復核對，暫停所有操作。</p> : null}
    {state?.closed ? <p>牌桌已關閉；當手完成後退回剩餘籌碼。</p> : null}
    {state?.joined ? <>
      <div className="table-scene" ref={scene}><ChipFlights events={presentation.view.flights} scene={scene} /><div className="felt" aria-hidden="true" />
        <div className="board"><span className="table-wordmark" aria-hidden="true">♠ ICEZ POKER</span><strong className="pot"><span>總底池</span> {chips(hand?.pot ?? '0')}</strong><Cards cards={hand?.board ?? []} slots={5} /><p>{state.countdown ? `下一手倒數 ${Math.max(0, Math.ceil(state.countdown - now))} 秒` : active ? labels[hand.street] : '等待下一手'}</p></div>
        {Array.from({ length: 6 }, (_, seat) => {
          const occupants = seated.filter(m => m.seat === seat);
          const m = occupants.find(m => hand?.players.some(p => p.id === m.id)) ?? occupants[0];
          if (!m) return <article key={seat} className={`seat empty ${position(seat)}`}>空位 {seat + 1}</article>;
          const player = hand?.players.find(p => p.id === m.id);
          const acting = active && hand.actor !== null && hand.players[hand.actor]?.id === m.id;
          const dealer = hand?.players[hand.button]?.id === m.id;
          return <article data-player={m.id} className={`seat ${position(seat)} ${acting ? 'acting' : ''} ${player?.folded ? 'folded' : ''} ${m.id === user ? 'hero-seat' : ''}`} key={seat} aria-label={`${playerName(m.id)}，${chips(m.stack)} 籌碼`}>
            {player ? <div className="seat-cards"><Cards cards={player.cards} hidden={player.cards.length === 0} /></div> : null}
            <div className="seat-plaque"><div className="portrait">{presentation.view.wins[m.id] ? <span className="winner-badge" role="status">WIN<small>派彩 {chips(presentation.view.wins[m.id].amount ?? '0')}</small></span> : null}<PlayerAvatar url={profiles[m.id]?.avatar_url} npc={m.id.startsWith('npc:')} countdown={acting ? seconds : null} />{acting ? <svg className="countdown-ring" viewBox="0 0 100 100" aria-label={`剩餘 ${seconds} 秒`}><circle cx="50" cy="50" r="46" pathLength="100" /><circle cx="50" cy="50" r="46" pathLength="100" strokeDasharray={`${Math.min(100, seconds / (m.id.startsWith('npc:') ? 2 : hand?.extensions ? 5 : 20) * 100)} 100`} /></svg> : null}</div><div className="seat-info"><strong title={playerName(m.id)}>{playerName(m.id)}</strong><b className="seat-stack">{chips(m.stack)}</b></div></div>
            {presentation.view.actions[m.id] ? <span className="action-label" role="status">{actionLabel(presentation.view.actions[m.id])}</span> : <span className="action-label empty-label" aria-hidden="true">·</span>}
            <small className="seat-status">{!m.connected && !m.id.startsWith('npc:') ? '離線 · ' : ''}{player?.folded ? '已棄牌' : player?.stack === '0' && active ? '全下' : m.leaving ? '手後離桌' : m.sitout ? '手後坐出' : acting ? '正在行動' : labels[m.mode] ?? m.mode}{occupants.length > 1 ? ' · 真人等待接替' : ''}</small>
            {dealer ? <span className="dealer" aria-label="莊位">D</span> : null}
            {active && player && BigInt(player.bet) > 0n ? <span className="seat-bet"><span aria-hidden="true">◉</span> {chips(player.bet)}</span> : null}
          </article>;
        })}
      </div>
      {hand?.payouts ? <p role="status" className="settlement">{settlement ? `${settlement.void ? '作廢' : `派彩 ${chips(awardTotal.toString())}`} · 退款 ${chips(refundTotal.toString())}` : '本手已結算'}</p> : null}
      <section className="action-panel" aria-label="牌桌操作">
        <div className="turn-line"><strong>{ownTurn ? '輪到你行動' : active ? '等待其他玩家' : '等待下一手'}</strong><span className="timebank" title="行動時間用盡時自動補時，每次 5 秒，每手最多 4 次">◷ 補時池 {state.time_bank ?? 0}s{active && hand.extensions > 0 ? ` · 已用 ${hand.extensions}/4` : ''}</span></div>
        <div className="bet-sizing"><div className="pot-presets" aria-label="底池比例下注">{[[1, 3], [1, 2], [2, 3], [1, 1], [2, 1]].map(([n, d]) => <button key={`${n}/${d}`} disabled={!canRaise} title={`跟注後底池的 ${n}/${d}，限制於合法加注範圍`} onClick={() => { setRaise(potPreset(hand?.pot ?? '0', hand?.legal.call ?? '0', ownPlayer?.bet ?? '0', n, d, minimum, maximum)); void sound.play('click'); }}>{d === 1 ? `${n}x` : `${n}/${d}`}</button>)}</div>
        <div className="bet-slider"><button aria-label="減少下注" disabled={!canRaise || raiseValue <= minimum} onClick={() => { setRaise(clamp(raiseValue - 100n, minimum, maximum).toString()); void sound.play('click'); }}>−</button><input aria-label="下注金額滑桿" type="range" min="0" max="1000" disabled={!canRaise || minimum === maximum} value={maximum > minimum ? Number((raiseValue - minimum) * 1000n / (maximum - minimum)) : 0} onChange={e => setRaise(sliderAmount(Number(e.target.value), minimum, maximum).toString())} /><button aria-label="增加下注" disabled={!canRaise || raiseValue >= maximum} onClick={() => { setRaise(clamp(raiseValue + 100n, minimum, maximum).toString()); void sound.play('click'); }}>＋</button><input aria-label="加注至" inputMode="numeric" autoComplete="off" disabled={!canRaise} value={raise} aria-invalid={canRaise && !raiseValid} onChange={e => setRaise(e.target.value)} /></div>
        <small className="raise-range">{canRaise ? `最低 ${chips(minimum.toString())} · 最高 ${chips(maximum.toString())}` : '等待可下注時調整金額'}</small></div>
        <div className="action-buttons"><button disabled={disabled || !ownTurn} onClick={() => act('fold')}>棄牌</button><button disabled={disabled || !ownTurn} onClick={() => act(hand?.legal.check ? 'check' : 'call')}>{hand?.legal.check ? '過牌' : <>跟注<span>{chips(hand?.legal.call ?? '0')}</span></>}</button><button disabled={!canRaise || !raiseValid} onClick={() => act('raise', raise)}>{raiseValue === maximum && canRaise ? '全下' : betLabel}<span>{chips(raiseValue.toString())}</span></button></div>
      </section>
      <nav className="table-links" aria-label="牌局資訊"><button onClick={() => setInfo('hand')}>{hand?.settlement ? '結算明細' : '本手牌局'}</button><button onClick={() => setInfo('log')}>牌局紀錄</button></nav>
      {info ? <Modal title={info === 'hand' ? '本手牌局' : '牌局紀錄'} onClose={() => setInfo(null)}>{info === 'hand' ? <div className="hand-info"><p>{hand ? `手牌 ${hand.id} · ${labels[hand.street] ?? hand.street}` : '尚未開始'} · 底池 {chips(hand?.pot ?? '0')}</p><span>你的底牌</span><Cards cards={ownPlayer?.cards ?? []} /><span>公共牌</span><Cards cards={hand?.board ?? []} slots={5} />{hand?.settlement ? <SettlementDetails settlement={hand.settlement} name={playerName} /> : null}</div> : <><p>本次連線觀察到的公開異動，最多保留 80 筆；重連期間可能不完整。</p>{log.length ? <ol className="game-log">{log.map((entry, index) => <li key={index}>{entry}</li>)}</ol> : <p>尚無新的牌局異動。</p>}</>}</Modal> : null}
      {options ? <Modal title="牌桌選項" onClose={() => setOptions(false)}><ThemePicker /><SoundSettings /><p className="bank">補時池 {state.time_bank} / 60 秒 · 自動補時每次 +5 秒，最多 4 次</p>
        <div className="table-controls"><label>補碼金額<input inputMode="numeric" value={amount} onChange={e => setAmount(e.target.value)} /></label><button disabled={disabled || !!mine?.topup || mine?.leaving} onClick={() => command('topup', { amount })}>申請手後補碼</button><button disabled={disabled || mine?.leaving || mine?.sitout} onClick={() => command(mine?.mode === 'sitout' ? 'sit_in' : 'sitout')}>{mine?.mode === 'sitout' ? '重新坐入' : mine?.sitout ? '已排隊坐出' : '手後坐出'}</button><button disabled={disabled || mine?.leaving} onClick={() => command('leave')}>手後離桌</button></div>
        {mine?.expires ? <p>座位保留 {Math.max(0, Math.ceil(mine.expires - now))} 秒</p> : null}
      <section className="table-notices" aria-label="手間異動">{seated.filter(m => m.topup || m.notice || m.leaving || m.sitout || m.mode === 'pending').map(m => <p key={m.id}>{playerName(m.id)}：{m.topup ? `待補碼 ${chips(m.topup)}。` : ''}{m.leaving ? '已排隊手後離桌。' : m.sitout ? '已排隊手後坐出。' : m.mode === 'pending' ? '等待下一手加入。' : ''}{m.notice ? m.notice === 'topup_complete' ? '補碼完成。' : m.notice === 'topup_rejected' ? '補碼失敗：請確認可用餘額與上限。' : `NPC 暫時異常（連續 ${m.npc_failures} 次）。` : ''}</p>)}</section>
      {state.owner === user ? <details className="host-tools"><summary>房主選項</summary><div className="table-controls"><button disabled={disabled || state.closed} onClick={() => command('add_npc')}>新增固定 NPC</button>{seated.filter(m => m.id.startsWith('npc:')).map(m => <button key={m.id} disabled={disabled || m.leaving} onClick={() => command('remove_npc', { npc_id: m.id })}>移除座位 {m.seat + 1} NPC（手後）</button>)}{state.private ? <button disabled={inviteBusy} onClick={() => void invitation()}>私人桌邀請</button> : null}</div></details> : null}
      </Modal> : null}
    </> : <button onClick={onClose}>回到大廳</button>}
    {confirm ? <Modal title="確認全下" onClose={() => setConfirm(null)}><p>將投入本手所有剩餘籌碼。確認後無法收回。</p><div className="table-controls"><button onClick={() => setConfirm(null)}>取消</button><button disabled={disabled || hand?.id !== confirm.hand_id || hand?.turn !== confirm.turn} onClick={() => { const payload = confirm; setConfirm(null); void send(payload); }}>確認全下</button></div></Modal> : null}
    {invite ? <Modal title="私人桌邀請" onClose={() => setInvite('')}><p>持有效邀請的已登入成員可入座；重設後舊連結立即失效。</p><label>邀請連結<input readOnly value={invite} onFocus={event => event.target.select()} /></label><div className="table-controls"><button onClick={() => void navigator.clipboard.writeText(invite).catch(() => setError('請選取邀請連結並手動複製。'))}>複製邀請</button><button disabled={disabled || inviteBusy} onClick={() => void invitation(true)}>重設邀請</button></div></Modal> : null}
  </section>;
}
