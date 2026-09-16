import { useEffect, useState } from 'react';

type Metric = { numerator: number; denominator: number; percent: string; low_sample: boolean };
type Summary = { user_id: string; hands: number; low_sample: boolean; metrics: Record<string, Metric> };
type Report = { as_of: string; start: string | null; personal: Summary; leaderboard: (Summary & { rank: number; settled: string })[] };
const labels: Record<string, string> = { net_win: '淨贏牌率', vpip: 'VPIP', pfr: 'PFR', three_bet: '3-Bet', fold_three_bet: 'Fold to 3-Bet', cbet: 'Flop C-Bet', wsd: '攤牌分池率' };
function Rate({ value }: { value: Metric }) {
  return <><strong>{value.percent}</strong> <small>{value.numerator}/{value.denominator}{value.low_sample ? ' · 樣本不足' : ''}</small></>;
}

export function Statistics() {
  const [period, setPeriod] = useState('all');
  const [opponents, setOpponents] = useState('all');
  const [revision, setRevision] = useState(0);
  const [report, setReport] = useState<Report | null>(null);
  const [error, setError] = useState('');
  useEffect(() => {
    const controller = new AbortController();
    setReport(null); setError('');
    void fetch(`/api/statistics?period=${period}&opponents=${opponents}`, { signal: controller.signal }).then(async response => {
      if (!response.ok) throw new Error('無法讀取統計，請確認登入後重試。');
      const data: Report = await response.json();
      if (!controller.signal.aborted) setReport(data);
    }).catch(cause => { if (!controller.signal.aborted) setError(String(cause.message)); });
    return () => controller.abort();
  }, [period, opponents, revision]);
  return <div className="statistics">
    <div className="report-filters"><label>結算期間<select value={period} onChange={e => setPeriod(e.target.value)}><option value="all">累計</option><option value="30">近 30 天</option><option value="7">近 7 天</option></select></label><label>對手分類<select value={opponents} onChange={e => setOpponents(e.target.value)}><option value="all">全部</option><option value="human">純真人</option><option value="mixed">含 NPC</option></select></label><button onClick={() => setRevision(v => v + 1)}>更新統計</button></div>
    <p>篩選只影響手數與比例；排名按目前已結算總資產。</p>
    {error ? <p role="alert" className="message error">{error}</p> : !report ? <p role="status">讀取完整結算資料中…</p> : <>
      <section><h3>我的打法 <small>僅本人可見</small></h3><p>有效手數：{report.personal.hands}{report.personal.low_sample ? ' · 樣本不足' : ''}</p><div className="metric-grid">{Object.entries(report.personal.metrics).map(([key, value]) => <div className="metric" key={key}><span>{labels[key]}</span><Rate value={value} /></div>)}</div><p className="caption">攤牌分池率包含分池但整手淨輸的情況；與淨贏牌率不同。各比率以合併計數計算，未達樣本門檻請謹慎解讀。</p></section>
      <section><h3>已結算總資產榜</h3><div className="report-scroll" tabIndex={0} role="region" aria-label="資產排行榜"><table><thead><tr><th>名次</th><th>玩家 ID</th><th>德撲籌碼</th><th>有效手數</th><th>淨贏牌率</th></tr></thead><tbody>{report.leaderboard.map(row => <tr key={row.user_id}><td>{row.rank}</td><td>{row.user_id}{row.user_id === report.personal.user_id ? '（我）' : ''}</td><td>{BigInt(row.settled).toLocaleString('zh-TW')}</td><td>{row.hands}{row.low_sample ? ' · 樣本不足' : ''}</td><td><Rate value={row.metrics.net_win} /></td></tr>)}</tbody></table></div></section>
      <p className="caption">Asia/Taipei · {report.start ? `自 ${report.start}（含）` : '累計'} 至 {report.as_of}（不含）。近 7／30 天為滾動 24 小時，不採補助日切。</p>
    </>}
  </div>;
}
