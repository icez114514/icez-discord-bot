import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { Modal } from './Modal';
import { chatLength, type ChatUpdate } from './chatState';
import './TableChat.css';
type Pending = { client_message_id: string; text: string };
export function TableChat({ tableId, user, connected, update }: { tableId: string; user: string; connected: boolean; update: ChatUpdate | null }) {
  const [expanded,setExpanded] = useState(false);
  const [draft,setDraft] = useState(''), [pending,setPending] = useState<Pending | null>(null), [busy,setBusy] = useState(false), [error,setError] = useState('');
  const acknowledged = useRef<string | null>(null);
  const sending = useRef(false), alive = useRef(true), bottom = useRef(true), list = useRef<HTMLDivElement>(null), initialized = useRef(false);
  const [seen,setSeen] = useState(0), [newBelow,setNewBelow] = useState(false);
  const messages = update?.messages ?? [], visible = expanded;
  const unread = messages.filter(m => m.sequence > seen && m.author.id !== user).length;
  const disabled = !connected || !update || update.closed || busy;
  useEffect(() => { alive.current = true; return () => { alive.current = false; }; }, []);
  useEffect(() => {
    if (!update) return;
    if (!initialized.current || update.initial) { initialized.current = true; setSeen(update.sequence); }
    if (pending && messages.some(m => m.author.id === user && m.client_message_id === pending.client_message_id)) {
      acknowledged.current = pending.client_message_id;
      setPending(null); setDraft(value => value.trim() === pending.text ? '' : value); setError('');
    }
  }, [update, pending, messages, user]);
  useLayoutEffect(() => {
    if (!visible || !list.current) return;
    if (bottom.current) { list.current.scrollTop = list.current.scrollHeight; setSeen(update?.sequence ?? 0); setNewBelow(false); }
    else if ((update?.sequence ?? 0) > seen) setNewBelow(true);
  }, [update, visible, expanded]);
  function latest() { bottom.current = true; if(list.current) list.current.scrollTop = list.current.scrollHeight; setSeen(update?.sequence ?? 0); setNewBelow(false); }
  async function send() {
    if (disabled || sending.current || (!pending && (!chatLength(draft) || chatLength(draft)>200))) return;
    const item = pending ?? { client_message_id: crypto.randomUUID(), text: draft.trim() };
    sending.current = true; setBusy(true); setPending(item); setError('');
    const controller = new AbortController(), timeout = setTimeout(() => controller.abort(),10000);
    try {
      const response = await fetch('/api/table/chat', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ table_id: tableId, ...item }), signal: controller.signal });
      const result = await response.json();
      if (!alive.current || acknowledged.current === item.client_message_id) return;
      if (!response.ok) {
        if (response.status < 500) { setPending(null); setError(response.status === 409 && result.error === 'chat_rate_limited' ? '稍等一下，每分鐘最多 10 則。' : '無法送出，請確認連線、發言資格與字數。'); }
        else setError('尚未確認送出，可重試。');
      } else { setPending(null); setDraft(value => value.trim() === item.text ? '' : value); bottom.current = true; }
    } catch { if (alive.current && acknowledged.current !== item.client_message_id) setError('尚未確認送出，可重試。'); }
    finally { clearTimeout(timeout); sending.current = false; if (alive.current) setBusy(false); }
  }
  const body = <>
    <div className="chat-messages" ref={list} role="log" aria-label="同桌聊天紀錄" onScroll={() => { if (!list.current) return; bottom.current = list.current.scrollHeight-list.current.scrollTop-list.current.clientHeight < 12; if (bottom.current) { setSeen(update?.sequence ?? 0); setNewBelow(false); } }}>
      {messages.length ? messages.map(m => <p key={m.id}><strong title={m.author.display_name}>{m.author.display_name}</strong><span>{m.text}</span></p>) : <p className="chat-empty">{update?.closed ? '牌桌已關閉' : '與同桌玩家聊聊'}</p>}
    </div>
    {newBelow && <button className="chat-new" onClick={latest}>查看新訊息 ↓</button>}
    {error && <p className="chat-error" role="status">{error}</p>}
    <form className="chat-compose" onSubmit={event => { event.preventDefault(); void send(); }}>
      <input aria-label="聊天訊息" placeholder={!connected ? '連線中…' : '輸入訊息'} value={draft} disabled={!!pending || update?.closed} onChange={event => setDraft(event.target.value)} onKeyDown={event => { if (event.key==='Enter' && (event.nativeEvent.isComposing || event.keyCode===229)) event.preventDefault(); }} />
      <button type="submit" disabled={disabled || (!pending && (chatLength(draft)===0 || chatLength(draft)>200))}>{busy ? '送出中' : pending ? '重試' : '送出'}</button>
    </form>
    {chatLength(draft)>200 && <p className="chat-error">最多 200 字（目前 {chatLength(draft)} 字）</p>}
  </>;
  return <>
    <button className="table-chat-preview" aria-label={`開啟聊天${unread ? `，${unread} 則未讀` : ''}`} onClick={() => setExpanded(true)}><span className="chat-preview-heading">聊天 {unread>0 && <b>{unread}</b>}<span aria-hidden="true">↗</span></span><span className="chat-preview-lines">{messages.length ? messages.slice(-3).map(m=><span key={m.id}><strong>{m.author.display_name}</strong> {m.text}</span>) : <span>{update?.closed ? '牌桌已關閉' : '尚無訊息'}</span>}</span></button>
    {expanded && <Modal title="同桌聊天" className="table-chat-dialog" fitVisualViewport onClose={() => setExpanded(false)}>{body}</Modal>}
  </>;
}
