"""The only membership recheck job: one durable snapshot per Taipei day."""
import logging
import time
from .money import day_key
from .sessions import present

log = logging.getLogger('poker.eligibility')


class Eligibility:
    def __init__(self, store, discord):
        self.store = store
        self.discord = discord

    async def run(self, now=None):
        realtime = now is None
        now = time.time() if realtime else now
        day = day_key(now)
        def snapshot(db):
            created = db.execute('INSERT OR IGNORE INTO scans(day,started_at) VALUES(?,?)', (day, now)).rowcount
            if created:
                for row in db.execute('SELECT DISTINCT a.user_id,a.presence_revision,a.login_revision FROM accounts a JOIN sessions s USING(user_id) WHERE s.revoked=0').fetchall():
                    status = 'skipped' if present(db, row['user_id'], now) else 'pending'
                    db.execute('INSERT INTO scan_members(day,user_id,status,presence_revision,login_revision) VALUES(?,?,?,?,?)', (day, row['user_id'], status, row['presence_revision'], row['login_revision']))
            return [dict(row) for row in db.execute("SELECT * FROM scan_members WHERE day=? AND status IN ('pending','retry') AND next_attempt<=?", (day, now))]
        for item in await self.store.run(snapshot):
            def claim(db):
                row = db.execute('SELECT * FROM accounts WHERE user_id=?', (item['user_id'],)).fetchone()
                if present(db, item['user_id'], now) or row['presence_revision'] != item['presence_revision'] or row['login_revision'] != item['login_revision']:
                    db.execute("UPDATE scan_members SET status='skipped' WHERE day=? AND user_id=?", (day, item['user_id']))
                    return False
                return bool(db.execute("UPDATE scan_members SET status='checking' WHERE day=? AND user_id=? AND status IN ('pending','retry')", (day, item['user_id'])).rowcount)
            if not await self.store.run(claim):
                continue
            result = await self.discord.member(item['user_id'])
            commit_now = time.time() if realtime else now
            def commit(db):
                row = db.execute('SELECT * FROM accounts WHERE user_id=?', (item['user_id'],)).fetchone()
                if present(db, item['user_id'], commit_now) or row['presence_revision'] != item['presence_revision'] or row['login_revision'] != item['login_revision']:
                    status = 'skipped'
                elif result == 'absent':
                    db.execute('UPDATE sessions SET revoked=1 WHERE user_id=?', (item['user_id'],))
                    status = 'revoked'
                elif result == 'member':
                    status = 'verified'
                else:
                    status = 'retry'
                delay = min(3600, 60 * 2 ** min(item['attempts'], 6))
                db.execute('UPDATE scan_members SET status=?,attempts=attempts+1,next_attempt=? WHERE day=? AND user_id=?', (status, commit_now+delay, day, item['user_id']))
                return status
            status = await self.store.run(commit)
            log.info('membership_scan day=%s status=%s attempt=%s', day, status, item['attempts']+1)

    async def recover(self):
        await self.store.run(lambda db: db.execute("UPDATE scan_members SET status='retry' WHERE status='checking'"))

    async def status(self):
        return await self.store.run(lambda db: [dict(row) for row in db.execute('SELECT day,status,COUNT(*) AS accounts FROM scan_members GROUP BY day,status ORDER BY day DESC LIMIT 30')])