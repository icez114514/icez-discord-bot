import { useEffect, useState } from 'react';
import { Modal } from './Modal';
import { Statistics } from './Statistics';
import { Management } from './Management';
import { SoundSettings } from './SoundSettings';
import { IconButton } from './IconButton';
import { ThemePicker } from './Theme';

type Profile = { id: string; display_name: string; avatar_url: string };
export function AccountTools({ user, compact = false, home = false, busy = false, onLogout }: { user: string; compact?: boolean; home?: boolean; busy?: boolean; onLogout?: () => void }) {
  const [panel, setPanel] = useState<'statistics' | 'management' | 'settings' | 'logout' | null>(null);
  const [manager, setManager] = useState(false);
  const [profile, setProfile] = useState<Profile | null>(null);
  const [avatarFailed, setAvatarFailed] = useState(false);
  useEffect(() => {
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout> | undefined;
    setManager(false); setPanel(null); setProfile(null); setAvatarFailed(false);
    void fetch('/api/roles', { signal: controller.signal }).then(r => r.ok ? r.json() : null).then((roles: { tables: boolean; funds: boolean } | null) => { if (!controller.signal.aborted) setManager(Boolean(roles?.tables || roles?.funds)); }).catch(() => {});
    async function refreshProfile() {
      let delay = 60000;
      try {
        const response = await fetch('/api/profile', { signal: controller.signal });
        if (response.status === 401) return;
        if (response.ok) {
          const data: { user_id: string; profile: Profile | null } = await response.json();
          if (!controller.signal.aborted && data.user_id === user) {
            setProfile(data.profile); setAvatarFailed(false);
            if (!data.profile) delay = 5000;
          }
        }
      } catch { /* Presentation failures never block account controls. */ }
      if (!controller.signal.aborted) timer = setTimeout(() => void refreshProfile(), delay);
    }
    if (home) void refreshProfile();
    return () => { controller.abort(); clearTimeout(timer); };
  }, [user, home]);
  const avatar = profile?.avatar_url && !avatarFailed ? <img src={profile.avatar_url} alt="" onError={() => setAvatarFailed(true)} /> : <span className="home-avatar-fallback" aria-hidden="true">♠</span>;
  return <nav className="account-tools" aria-label="帳戶功能">{home ? <button className="home-profile" aria-label="個人設定" onClick={() => setPanel('settings')}>{avatar}<span title={profile?.display_name}>{profile?.display_name ?? '個人設定'}</span><span aria-hidden="true">⌄</span></button> : compact ? <IconButton icon="person" label="個人設定" onClick={() => setPanel('settings')} /> : <button className="text" onClick={() => setPanel('settings')}>個人設定</button>}{compact || home ? null : <button className="text" onClick={() => setPanel('statistics')}>排行與我的統計</button>}{manager && !compact && !home ? <button className="text" onClick={() => setPanel('management')}>管理與查帳</button> : null}
    {panel ? <Modal title={panel === 'statistics' ? '排行與我的統計' : panel === 'settings' ? '個人設定' : panel === 'logout' ? '登出' : '管理與查帳'} onClose={() => setPanel(null)}>{panel === 'statistics' ? <Statistics /> : panel === 'logout' ? <><p>要登出所有裝置嗎？</p><button disabled={busy} onClick={() => { setPanel(null); onLogout?.(); }}>確認登出</button></> : panel === 'settings' ? <>{home ? <div className="home-profile-summary">{avatar}<strong>{profile?.display_name ?? '個人設定'}</strong></div> : null}<SoundSettings /><div className="account-secondary">{home ? <ThemePicker /> : null}<button onClick={() => setPanel('statistics')}>排行與我的統計</button>{manager ? <button onClick={() => setPanel('management')}>管理與查帳</button> : null}{onLogout ? <button disabled={busy} onClick={() => setPanel('logout')}>登出所有裝置</button> : null}</div></> : <Management user={user} />}</Modal> : null}
  </nav>;
}
