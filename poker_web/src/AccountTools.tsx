import { useEffect, useState } from 'react';
import { Modal } from './Modal';
import { Statistics } from './Statistics';
import { Management } from './Management';
import { SoundSettings } from './SoundSettings';
import { IconButton } from './IconButton';

export function AccountTools({ user, compact = false }: { user: string; compact?: boolean }) {
  const [panel, setPanel] = useState<'statistics' | 'management' | 'settings' | null>(null);
  const [manager, setManager] = useState(false);
  useEffect(() => {
    const controller = new AbortController();
    setManager(false); setPanel(null);
    void fetch('/api/roles', { signal: controller.signal }).then(r => r.ok ? r.json() : null).then((roles: { tables: boolean; funds: boolean } | null) => { if (!controller.signal.aborted) setManager(Boolean(roles?.tables || roles?.funds)); }).catch(() => {});
    return () => controller.abort();
  }, [user]);
  return <nav className="account-tools" aria-label="帳戶功能">{compact ? <IconButton icon="person" label="個人設定" onClick={() => setPanel('settings')} /> : <button className="text" onClick={() => setPanel('settings')}>個人設定</button>}{compact ? null : <button className="text" onClick={() => setPanel('statistics')}>排行與我的統計</button>}{manager && !compact ? <button className="text" onClick={() => setPanel('management')}>管理與查帳</button> : null}
    {panel ? <Modal title={panel === 'statistics' ? '排行與我的統計' : panel === 'settings' ? '個人設定' : '管理與查帳'} onClose={() => setPanel(null)}>{panel === 'statistics' ? <Statistics /> : panel === 'settings' ? <><SoundSettings /><div className="account-secondary"><button onClick={() => setPanel('statistics')}>排行與我的統計</button>{manager ? <button onClick={() => setPanel('management')}>管理與查帳</button> : null}</div></> : <Management user={user} />}</Modal> : null}
  </nav>;
}
