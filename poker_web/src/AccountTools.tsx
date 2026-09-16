import { useEffect, useState } from 'react';
import { Modal } from './Modal';
import { Statistics } from './Statistics';
import { Management } from './Management';

export function AccountTools({ user }: { user: string }) {
  const [panel, setPanel] = useState<'statistics' | 'management' | null>(null);
  const [manager, setManager] = useState(false);
  useEffect(() => {
    const controller = new AbortController();
    setManager(false); setPanel(null);
    void fetch('/api/roles', { signal: controller.signal }).then(r => r.ok ? r.json() : null).then((roles: { tables: boolean; funds: boolean } | null) => { if (!controller.signal.aborted) setManager(Boolean(roles?.tables || roles?.funds)); }).catch(() => {});
    return () => controller.abort();
  }, [user]);
  return <nav className="account-tools" aria-label="帳戶功能"><button className="text" onClick={() => setPanel('statistics')}>排行與我的統計</button>{manager ? <button className="text" onClick={() => setPanel('management')}>管理與查帳</button> : null}
    {panel ? <Modal title={panel === 'statistics' ? '排行與我的統計' : '管理與查帳'} onClose={() => setPanel(null)}>{panel === 'statistics' ? <Statistics /> : <Management user={user} />}</Modal> : null}
  </nav>;
}
