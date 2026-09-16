import { useEffect, useState } from 'react';

type Profile = { id: string; display_name: string; avatar_url: string };
const emptyProfiles: Record<string, Profile> = {};
export function usePlayerProfiles(tableId: string | undefined, members: string) {
  const [data, setData] = useState<{ table: string; profiles: Record<string, Profile> }>({ table: '', profiles: {} });
  useEffect(() => {
    if (!tableId) return;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    const users = members ? members.split(',') : [];
    async function refresh() {
      let missing = true;
      try {
        const response = await fetch('/api/table/profiles', { signal: controller.signal });
        if (!response.ok) throw new Error('profiles');
        const result: { table_id: string; profiles: Profile[] } = await response.json();
        if (result.table_id !== tableId || controller.signal.aborted) return;
        const profiles = Object.fromEntries(result.profiles.filter(p => users.includes(p.id)).map(p => [p.id, p]));
        missing = users.some(id => !profiles[id]);
        setData({ table: tableId!, profiles });
      } catch { /* Keep the last presentation; gameplay never waits for Discord. */ }
      finally { if (!controller.signal.aborted) timer = setTimeout(() => void refresh(), missing ? 5000 : 30000); }
    }
    void refresh();
    return () => { controller.abort(); clearTimeout(timer); };
  }, [tableId, members]);
  return data.table === tableId ? data.profiles : emptyProfiles;
}

export function PlayerAvatar({ url, npc, countdown }: { url?: string; npc: boolean; countdown: number | null }) {
  const [failed, setFailed] = useState<string | null>(null);
  return <span className="avatar">
    {url && failed !== url ? <img src={url} alt="" referrerPolicy="no-referrer" draggable={false} onError={() => setFailed(url)} /> : <span aria-hidden="true">{npc ? '♟' : '♠'}</span>}
    {countdown !== null ? <span className="avatar-countdown" aria-hidden="true">{countdown}</span> : null}
  </span>;
}
