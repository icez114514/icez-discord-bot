import { useState } from 'react';
import { ratio, type Preferences } from './personalization';
export function TablePreferences({ value, onChange, saved }: { value: Preferences; onChange: (value: Preferences) => void; saved: boolean }) {
  const [pre, setPre] = useState(value.preflop.join(', '));
  const [post, setPost] = useState(value.postflop.join(', '));
  const parse = (text: string) => text.split(/[,，]/).map(s => s.trim());
  const valid = (text: string) => parse(text).length === 5 && parse(text).every(s => ratio(s));
  return <fieldset className="personal-settings"><legend>個人牌桌偏好</legend>
    <label><input type="checkbox" checked={value.fourColor} onChange={e => onChange({ ...value, fourColor: e.target.checked })} />四色牌（♣ 綠、♦ 藍、♥ 紅、♠ 黑）</label>
    <label><input type="checkbox" checked={value.large} onChange={e => onChange({ ...value, large: e.target.checked })} />大字牌面與操作</label>
    <label>翻牌前 BB 倍數<input aria-label="翻牌前 BB 倍數" value={pre} onChange={e => setPre(e.target.value)} aria-invalid={!valid(pre)} /></label>
    <label>翻牌後底池比例<input aria-label="翻牌後底池比例" value={post} onChange={e => setPost(e.target.value)} aria-invalid={!valid(post)} /></label>
    <p>各填五個正數，以逗號分隔；可用分數或最多兩位小數。快捷按鈕只填入草稿，按下注才送出。不足一籌碼向下取整，再限制於合法加注至範圍。</p>
    <button disabled={!valid(pre) || !valid(post)} onClick={() => onChange({ ...value, preflop: parse(pre), postflop: parse(post) })}>儲存下注按鈕</button>
    {!saved ? <p role="status">偏好已套用；此裝置無法保存，重新開啟後可能恢復預設。</p> : null}
  </fieldset>;
}
