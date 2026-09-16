import { useEffect, useRef, useState } from 'react';

type Roles = { tables: boolean; funds: boolean };
type State = { roles: Roles; tables: { table_id: string; name: string; status: string; members: { user_id: string; leaving: boolean }[] }[]; accounts: { user_id: string; disabled: boolean; available: string; settled: string }[] };
type Command = { command_id: string; action: string; target: string; amount?: string; reason: string };
const actions: Record<string, string> = { close: '手後關桌', disable: '停用帳戶', remove: '手後移除玩家', adjust: '調整籌碼', rebuild: '重建手牌統計' };
const statuses: Record<string, string> = { open: '開放', closing: '等待當手結算', closed: '已關閉', frozen: '凍結待恢復' };
async function get<T>(url: string): Promise<T> {
  const response = await fetch(url);
  if (!response.ok) throw new Error('讀取失敗或未具備管理權限。');
  return response.json() as Promise<T>;
}

const auditLabels: Record<string, string> = { id: '流水編號', command_id: '命令編號', actor: '操作者', action: '操作', target: '對象', reason: '原因', created_at: '時間', user_id: '玩家', source: '來源', available_delta: '可用籌碼增減', table_delta: '桌上籌碼增減', flight_delta: '在途籌碼增減', settled_delta: '總資產增減', available: '可用籌碼', settled: '已結算資產', table: '桌上籌碼', in_flight: '在途籌碼', disabled: '停用', status: '執行狀態' };
function AuditRecord({ record }: { record: Record<string, unknown> }) {
  function fields(data: Record<string, unknown>) {
    return Object.entries(data).filter(([key]) => key in auditLabels).map(([key, value]) => <div key={key}><dt>{auditLabels[key]}</dt><dd>{key === 'created_at' && typeof value === 'number' ? new Date(value * 1000).toLocaleString('zh-TW', { timeZone: 'Asia/Taipei' }) : key === 'action' ? actions[String(value)] ?? String(value) : typeof value === 'boolean' ? value ? '是' : '否' : String(value)}</dd></div>);
  }
  return <article className="audit-record"><dl>{fields(record)}</dl>{['before_state', 'after_state'].map(key => {
    const value = record[key];
    return value && typeof value === 'object' ? <div key={key}><h4>{key === 'before_state' ? '操作前' : '操作後'}</h4>{'redacted' in value ? <p>私人統計證據已留存，管理介面不顯示。</p> : <dl>{fields(value as Record<string, unknown>)}</dl>}</div> : null;
  })}</article>;
}

export function Management({ user }: { user: string }) {
  const [state, setState] = useState<State | null>(null);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [action, setAction] = useState('');
  const [target, setTarget] = useState('');
  const [amount, setAmount] = useState('');
  const [reason, setReason] = useState('');
  const [busy, setBusy] = useState(false);
  const storageKey = `poker-management-pending:${user}`;
  const pending = useRef<Command | null>(null);
  const [retry, setRetry] = useState(() => {
    try { const saved = sessionStorage.getItem(storageKey); pending.current = saved ? JSON.parse(saved) as Command : null; } catch { pending.current = null; }
    return pending.current !== null;
  });
  const [records, setRecords] = useState<Record<string, unknown>[]>([]);
  const [recordKind, setRecordKind] = useState<'audit' | 'ledger'>('audit');
  const [cursor, setCursor] = useState(0);
  const [ledgerUser, setLedgerUser] = useState('');
  async function refresh() {
    const data = await get<State>('/api/management'); setState(data);
    setAction(current => current || (data.roles.tables ? 'close' : 'adjust'));
  }
  useEffect(() => { void refresh().catch(cause => setError(cause.message)); }, []);
  async function submit() {
    if (busy) return;
    const command = pending.current ?? { command_id: crypto.randomUUID(), action, target: target.trim(), reason: reason.trim(), ...(action === 'adjust' ? { amount } : {}) };
    try { sessionStorage.setItem(storageKey, JSON.stringify(command)); } catch { setError('無法保留命令以供安全重試，請啟用瀏覽器儲存後再試。'); return; }
    pending.current = command; setBusy(true); setError(''); setNotice('');
    try {
      const response = await fetch('/api/management/commands', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(command) });
      // Preserve the exact intent until a definite response, including lost ACKs.
      if (response.status >= 500) throw new Error('結果尚未確認，請用同一命令重試。');
      const result = await response.json();
      pending.current = null; sessionStorage.removeItem(storageKey); setRetry(false);
      if (!response.ok) throw new Error(`操作未完成：${result.error ?? '請檢查輸入與權限'}`);
      setNotice(`${actions[command.action]}已受理（${command.command_id}）。請更新管理狀態確認手後結果。`);
      setReason(''); await refresh();
    } catch (cause) {
      setRetry(pending.current !== null); setError(cause instanceof Error ? cause.message : '連線失敗，請重試原命令。');
    } finally { setBusy(false); }
  }
  async function loadRecords(kind: 'audit' | 'ledger', next = false) {
    setError('');
    const after = next ? cursor : 0;
    try {
      const url = kind === 'audit' ? `/api/management/audit?after=${after}` : `/api/management/ledger/${encodeURIComponent(ledgerUser.trim())}?after=${after}`;
      const data = await get<{ audit?: Record<string, unknown>[]; entries?: Record<string, unknown>[]; next: number }>(url);
      setRecords(current => next ? [...current, ...(data.audit ?? data.entries ?? [])] : data.audit ?? data.entries ?? []);
      setCursor(data.next); setRecordKind(kind);
    } catch (cause) { setError(cause instanceof Error ? cause.message : '查帳失敗。'); }
  }
  return <div className="management">
    {error ? <p role="alert" className="message error">{error}</p> : null}{notice ? <p role="status" className="message">{notice}</p> : null}
    {retry && pending.current ? <p role="status">待確認命令：{actions[pending.current.action]} · {pending.current.target} · {pending.current.amount ?? ''} · {pending.current.reason}。重試將使用原命令。</p> : null}
    <button onClick={() => void refresh().catch(cause => setError(cause.message))}>更新管理狀態</button>
    {state ? <>
      {state.roles.tables ? <section><h3>牌桌狀態</h3>{state.tables.map(table => <p key={table.table_id}><strong>{table.name}</strong> · {statuses[table.status]}<br/><code>{table.table_id}</code><br/>{table.members.map(m => `${m.user_id}${m.leaving ? '（待離桌）' : ''}`).join('、')}</p>)}</section> : null}
      <section><h3>帳戶</h3><div className="report-scroll" tabIndex={0} role="region" aria-label="管理帳戶"><table><thead><tr><th>玩家 ID</th><th>狀態</th><th>可用籌碼</th><th>已結算資產</th></tr></thead><tbody>{state.accounts.map(a => <tr key={a.user_id}><td>{a.user_id}</td><td>{a.disabled ? '停用' : '正常'}</td><td>{BigInt(a.available).toLocaleString()}</td><td>{BigInt(a.settled).toLocaleString()}</td></tr>)}</tbody></table></div></section>
      <form onSubmit={e => { e.preventDefault(); void submit(); }}><h3>管理操作</h3><fieldset disabled={busy || retry}><label>操作<select value={action} onChange={e => setAction(e.target.value)}>{Object.entries(actions).filter(([key]) => key === 'adjust' ? state.roles.funds : state.roles.tables).map(([key, name]) => <option key={key} value={key}>{name}</option>)}</select></label><label>{action === 'close' ? '牌桌 ID' : action === 'rebuild' ? '手牌 ID' : '玩家 Discord ID'}<input required maxLength={80} value={target} onChange={e => setTarget(e.target.value)} /></label>{action === 'adjust' ? <label>籌碼增減（負數為扣除）<input required inputMode="text" pattern="-?(0|[1-9][0-9]*)" value={amount} onChange={e => setAmount(e.target.value)} /></label> : null}<label>原因<input required maxLength={500} value={reason} onChange={e => setReason(e.target.value)} /></label></fieldset><p>關桌、移除與停用保留當手權益，結算後退回剩餘籌碼。停用立即撤銷登入。</p><button disabled={busy}>{busy ? '處理中…' : retry ? '重試原命令' : '確認執行'}</button></form>
      <section><h3>查帳與稽核</h3><div className="report-filters"><button onClick={() => void loadRecords('audit')}>管理稽核</button>{state.roles.funds ? <><label>流水玩家 ID<input value={ledgerUser} onChange={e => { setLedgerUser(e.target.value); setRecords([]); setCursor(0); }} /></label><button disabled={!ledgerUser.trim()} onClick={() => void loadRecords('ledger')}>查詢流水</button></> : null}</div><div className="audit-records">{records.map((record, index) => <AuditRecord key={index} record={record} />)}</div>{records.length ? <button onClick={() => void loadRecords(recordKind, true)}>載入後續紀錄</button> : <p>尚無已載入紀錄。</p>}</section>
    </> : <p>讀取管理權限中…</p>}
  </div>;
}
