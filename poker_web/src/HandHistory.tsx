import { useEffect, useRef, useState } from 'react';
import { Modal } from './Modal';
import { Cards } from './Cards';
import { SettlementDetails, type Settlement } from './TableEffects';
import { actionLabel, chips } from './tablePresentation';
import type { PublicEvent } from './tableAudio';
import './replay.css';

type Frame = {
  step: number; event: PublicEvent & { automatic?: boolean }; street: string; board: string[]; pot: string;
  players: { id: string; cards: string[]; stack: string; bet: string; paid: string; folded: boolean }[];
  settlement: Settlement | null;
};
type Policy = { support: string; retention: string };
type Hand = { hand_id: string; table_id: string; status: string };
type History = { hands: Hand[]; next_cursor: number | null; policy: Policy };
type Replay = { hand_id: string; complete: boolean; reason: string | null; frames: Frame[]; policy: Policy };
const streets: Record<string, string> = { preflop: '翻牌前', flop: '翻牌', turn: '轉牌', river: '河牌' };

function description(frame: Frame, name: (id: string) => string) {
  const event = frame.event;
  if (event.kind === 'action') return `${name(event.user!)} · ${actionLabel(event)}${event.automatic ? '（自動）' : ''}`;
  if (event.kind === 'payout' || event.kind === 'refund') return `${name(event.user!)} · ${event.kind === 'refund' ? '退款' : '實領'} ${chips(event.amount!)}`;
  return ({ deal: '發牌', board: '發出公共牌', collect: '下注收池', showdown: '攤牌公開', complete: '最終結算' } as Record<string, string>)[event.kind] ?? event.kind;
}

export function HandHistory({ user, ownTurn, seconds, connected, onClose }: {
  user: string; ownTurn: boolean; seconds: number; connected: boolean; onClose: () => void;
}) {
  const [history, setHistory] = useState<History | null>(null);
  const [replay, setReplay] = useState<Replay | null>(null);
  const [selection, setSelection] = useState('');
  const [before, setBefore] = useState<number | null>(null);
  const [page, setPage] = useState<number[]>([]);
  const [revision, setRevision] = useState(0);
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState('');
  const [step, setStep] = useState(0);
  const [summary, setSummary] = useState(true);
  const [playing, setPlaying] = useState(false);
  const request = useRef<AbortController | null>(null);
  const name = (id: string) => id === user ? '你' : id.startsWith('npc:') ? `NPC ${id.slice(-6)}` : `玩家 ${id}`;

  useEffect(() => {
    const controller = new AbortController();
    setBusy(true); setError(''); setReplay(null); setPlaying(false); setHistory(null); setSelection('');
    request.current?.abort();
    void fetch('/api/hands' + (before === null ? '' : `?before=${before}`), { signal: controller.signal, cache: 'no-store' })
      .then(async response => {
        if (!response.ok) throw Error(response.status === 401 ? '登入已撤銷，請重新登入。' : '無法讀取歷史，請重試。');
        const data: History = await response.json();
        if (!controller.signal.aborted) { setHistory(data); setSelection(data.hands[0]?.hand_id ?? ''); }
      }).catch(cause => { if (!controller.signal.aborted) setError(String(cause.message)); })
      .finally(() => { if (!controller.signal.aborted) setBusy(false); });
    return () => controller.abort();
  }, [before, revision, user]);

  useEffect(() => {
    if (!selection) return;
    const controller = new AbortController(); request.current = controller;
    setBusy(true); setReplay(null); setPlaying(false); setError(''); setSummary(true); setStep(0);
    void fetch('/api/hands/' + encodeURIComponent(selection), { signal: controller.signal, cache: 'no-store' })
      .then(async response => {
        if (!response.ok) throw Error(response.status === 401 ? '登入已撤銷，請重新登入。' : '此手牌不存在或你沒有查看權。');
        const data: Replay = await response.json();
        if (!controller.signal.aborted) setReplay(data);
      }).catch(cause => { if (!controller.signal.aborted) setError(String(cause.message)); })
      .finally(() => { if (!controller.signal.aborted) setBusy(false); });
    return () => controller.abort();
  }, [selection, user]);

  const last = (replay?.frames.length ?? 1) - 1;
  useEffect(() => {
    if (!playing) return;
    if (step >= last) { setPlaying(false); return; }
    const timer = setTimeout(() => setStep(s => s + 1), 900);
    return () => clearTimeout(timer);
  }, [playing, step, last]);
  useEffect(() => {
    const pause = () => { if (document.hidden) setPlaying(false); };
    document.addEventListener('visibilitychange', pause);
    return () => document.removeEventListener('visibilitychange', pause);
  }, []);
  function seek(index: number) { setPlaying(false); setSummary(false); setStep(index); }
  const frame = replay?.frames[summary ? last : step];

  return <Modal title="上一手摘要與手牌回放" onClose={onClose}>
    <div className="hand-history">
      <div className="replay-live" role="status">
        <span>{!connected ? '即時連線中斷，桌況可能已變更。' : ownTurn ? `輪到你行動 · 剩餘 ${seconds} 秒` : '正在查看歷史手牌'} · 回放不會暫停行動期限。</span>
        <button onClick={onClose}>返回即時牌桌</button>
      </div>
      <div className="replay-controls">
        <button disabled={busy} onClick={() => { setBefore(null); setPage([]); setRevision(r => r + 1); }}>重新整理上一手</button>
        <button disabled={busy || !page.length} onClick={() => { setBefore(page.length === 1 ? null : page[page.length - 2]); setPage(p => p.slice(0, -1)); }}>較新一頁</button>
        <button disabled={busy || !history?.next_cursor} onClick={() => { const cursor = history!.next_cursor!; setBefore(cursor); setPage(p => [...p, cursor]); }}>較舊一頁</button>
      </div>
      {history?.hands.length ? <label>已結束手牌<select aria-label="已結束手牌" disabled={busy} value={selection} onChange={e => setSelection(e.target.value)}>{history.hands.map((h, i) => <option key={h.hand_id} value={h.hand_id}>{before === null && i === 0 ? '上一手 · ' : ''}{h.hand_id} · {h.status === 'void' ? '作廢' : '已結算'}</option>)}</select></label> : !busy && !error ? <p>尚無已參與且已結束的手牌。</p> : null}
      {busy ? <p role="status">正在讀取伺服器歷史…</p> : null}
      {error ? <p role="alert">{error}</p> : null}
      {replay && !replay.complete ? <p role="status">{replay.reason}</p> : null}
      {frame && replay?.complete ? <>
        <div className="replay-controls" aria-label="回放控制">
          <button onClick={() => { setPlaying(false); setSummary(true); }}>上一手摘要</button>
          <button onClick={() => seek(0)}>從頭回放</button>
          <button disabled={summary || step === 0} onClick={() => seek(step - 1)}>上一步</button>
          <button disabled={summary || step === last} onClick={() => seek(step + 1)}>下一步</button>
          <button aria-pressed={playing} onClick={() => { if (summary || step === last) setStep(0); setSummary(false); setPlaying(p => !p); }}>{playing ? '暫停' : '播放'}</button>
          {Object.entries(streets).map(([street, label]) => {
            const index = replay.frames.findIndex(f => f.street === street);
            return <button key={street} disabled={index < 0} onClick={() => seek(index)}>{label}</button>;
          })}
          <button onClick={() => seek(last)}>最終結算</button>
        </div>
        <p className="replay-step" role="status">{summary ? '上一手摘要' : `步驟 ${step + 1} / ${last + 1}`} · {streets[frame.street]} · {description(frame, name)}</p>
        <div className="replay-board"><Cards cards={frame.board} slots={5} /><p>未派發底池 {chips(frame.pot)}</p></div>
        <div className="replay-players">{frame.players.map(p => <article key={p.id} data-replay-player={p.id}><strong>{name(p.id)}{p.folded ? ' · 已棄牌' : ''}</strong><Cards cards={p.cards} hidden={!p.cards.length} /><small>籌碼 {chips(p.stack)} · 本街 {chips(p.bet)} · 總投入 {chips(p.paid)}</small></article>)}</div>
        {frame.settlement ? <SettlementDetails settlement={frame.settlement} name={name} /> : null}
        {summary ? <div className="replay-summary">{Object.entries(streets).map(([street, label]) => {
          const entries = replay.frames.filter(f => f.street === street);
          if (!entries.length) return null;
          const board = entries.find(f => f.event.kind === 'board')?.board;
          return <section key={street}><h3>{label}</h3>{board ? <Cards cards={board} slots={5} /> : null}<ol>{entries.filter(f => ['action', 'showdown', 'payout', 'refund'].includes(f.event.kind)).map(f => <li key={f.step}>{description(f, name)}</li>)}</ol></section>;
        })}</div> : null}
      </> : null}
      {history ? <small className="replay-policy">{history.policy.support} {history.policy.retention} 每頁 20 手，包含離桌或斷線期間已保存的紀錄。</small> : null}
    </div>
  </Modal>;
}
