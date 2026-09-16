import { useEffect, useState, useSyncExternalStore } from 'react';
import { sound, type Group, type Sound } from './sound';

const groups: { id: Group; label: string; preview: Sound }[] = [
  { id: 'reminders', label: '回合提醒', preview: 'turn' },
  { id: 'chips', label: '牌局籌碼', preview: 'chips' },
  { id: 'settlement', label: '結算勝利', preview: 'settle' },
  { id: 'interface', label: '介面提示', preview: 'click' },
];
const reasons: Record<string, string> = {
  ready: '音效已就緒', playing: '已播放', locked: '請點擊試聽以解鎖瀏覽器音效',
  muted: '總靜音已開啟', volume_zero: '此類別或總音量為零', hidden: '背景分頁暫停音效',
  expired: '音效載入過慢，已略過過期提示', limited: '同時發聲已達上限',
  load_failed: '音效載入失敗，可再次試聽', unavailable: '此瀏覽器無法啟用音效',
};
export function SoundSettings() {
  const prefs = useSyncExternalStore(sound.subscribe, sound.preferences);
  const [status, setStatus] = useState(sound.diagnosis);
  useEffect(() => { const timer = setInterval(() => setStatus(sound.diagnosis()), 500); return () => clearInterval(timer); }, []);
  return <fieldset className="sound-settings"><legend>音效與動態效果</legend>
    <label><input type="checkbox" checked={prefs.muted} onChange={e => sound.mute(e.target.checked)} />總靜音</label>
    <label>總音量 {Math.round(prefs.master * 100)}%<input aria-label="總音量" type="range" min="0" max="1" step="0.05" value={prefs.master} onChange={e => sound.configure({ master: Number(e.target.value) })} /></label>
    {groups.map(group => <div className="sound-group" key={group.id}><label>{group.label} {Math.round(prefs.groups[group.id] * 100)}%<input aria-label={group.label + '音量'} type="range" min="0" max="1" step="0.05" value={prefs.groups[group.id]} onChange={e => sound.configure({ groups: { ...prefs.groups, [group.id]: Number(e.target.value) } })} /></label><button type="button" aria-label={'試聽' + group.label} onClick={() => { sound.unlock(); void sound.play(group.preview).then(() => setStatus(sound.diagnosis())); }}>試聽</button></div>)}
    <label><input type="checkbox" checked={prefs.reduced} onChange={e => sound.configure({ reduced: e.target.checked })} />減少動態效果（也遵循系統設定）</label>
    <p role="status">{reasons[status] ?? status}{sound.storageFailed() ? ' · 無法儲存，偏好僅在本次會話保留。' : ''}</p>
  </fieldset>;
}
