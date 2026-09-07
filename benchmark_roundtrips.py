"""Measure 20 starts/replays per game in a disposable schema; argument: JSON output path.

Blackjack uses deterministic natural settlement, so both games include the payout path.
Run against each code version separately to compare changes. No Discord requests.
"""
import asyncio,json,statistics,time,math
from pathlib import Path
from uuid import uuid4
from psycopg import sql
from database import CrystalStore,Account,read_database_url
from casino_store import CasinoStore
from runtime import configure_event_loop
import sys
async def run():
    schema='casino_test_'+uuid4().hex
    async with CrystalStore(read_database_url(),schema=schema) as crystals:
        async with crystals.connection() as conn:
            await conn.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(schema)))
        try:
            await crystals.initialize()
            casino=CasinoStore(crystals,roll=lambda:(6,6,6,1,2,3),deck=lambda:[0,8,12,20]+[c for c in range(52) if c not in (0,8,12,20)])
            await casino.initialize()
            await crystals.import_accounts([Account(123,100000)],dry_run=False)
            result={}
            for kind in ('dice','blackjack'):
                for action in ('start','replay'):
                    samples=[]
                    prefs=await casino.settings(123)
                    prior=await casino.start(123,prefs.token,game=kind)
                    for index in range(20):
                        if action=='start':
                            await casino.leave(123,game_id=prior.id)
                            prefs=await casino.settings(123)
                        start=time.perf_counter()
                        prior=await (casino.start(123,prefs.token,game=kind) if action=='start' else casino.replay(123,prior.id))
                        samples.append((time.perf_counter()-start)*1000)
                    result[kind+'.'+action]={'median_ms':round(statistics.median(samples),1),'p95_ms':round(sorted(samples)[18],1),'samples_ms':[round(v,1) for v in samples]}
                    await casino.leave(123,game_id=prior.id)
                    print(kind,action,result[kind+'.'+action]['median_ms'],flush=True)
            Path(sys.argv[1]).write_text(json.dumps(result,indent=2),encoding='utf-8')
        finally:
            async with crystals.connection() as conn:
                await conn.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(schema)))
configure_event_loop()
asyncio.run(run())