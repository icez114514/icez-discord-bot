"""Atomic commands used by the future table engine and account HTTP endpoints."""
import json
import re
from datetime import datetime, timedelta, timezone

LIMIT = 9_000_000_000_000_000
TAIPEI = timezone(timedelta(hours=8))


def day_key(now):
    return (datetime.fromtimestamp(now, TAIPEI) - timedelta(hours=4)).date().isoformat()


def amount(value, signed=False):
    from .store import Conflict
    if not isinstance(value, str) or not re.fullmatch(r'-?(0|[1-9][0-9]{0,15})' if signed else r'(0|[1-9][0-9]{0,15})', value):
        raise Conflict('amount_must_be_decimal_string')
    result = int(value)
    if abs(result) > LIMIT:
        raise Conflict('amount_out_of_range')
    return result


def change(db, command_id, user, source, reason, available=0, table=0, flight=0, settled=0):
    from .store import Conflict
    if not db.execute('UPDATE accounts SET available=available+?,table_chips=table_chips+?,in_flight=in_flight+?,settled=settled+? WHERE user_id=?', (available, table, flight, settled, user)).rowcount:
        raise Conflict('unknown_account')
    db.execute('INSERT INTO ledger(command_id,user_id,source,reason,available_delta,table_delta,flight_delta,settled_delta) VALUES(?,?,?,?,?,?,?,?)', (command_id, user, source, reason, available, table, flight, settled))


def active_hand(db, user):
    return db.execute("SELECT 1 FROM participants p JOIN hands h USING(hand_id) WHERE p.user_id=? AND h.status='active'", (user,)).fetchone() is not None


def subsidy_status(db, user, now):
    row = db.execute('SELECT * FROM accounts WHERE user_id=?', (user,)).fetchone()
    day = day_key(now)
    if active_hand(db, user) or row['in_flight']:
        reason = 'unsettled_hand'
    elif db.execute('SELECT 1 FROM subsidies WHERE user_id=? AND day=?', (user, day)).fetchone():
        reason = 'already_claimed'
    elif row['available'] + row['table_chips'] >= 5000:
        reason = 'assets_at_least_5000'
    else:
        reason = None
    return {'eligible': reason is None, 'reason': reason, 'day': day, 'amount': str(max(0, 5000 - row['available'] - row['table_chips'])) if reason is None else '0'}


def execute(db, cid, kind, data, now):
    from .store import Conflict, account_view
    user = data.get('user_id')
    if kind in ('buy_in', 'leave', 'subsidy', 'adjust', 'npc_supply', 'npc_reclaim'):
        if kind == 'npc_supply' and isinstance(user, str) and user.startswith('npc:'):
            db.execute('INSERT OR IGNORE INTO accounts(user_id) VALUES(?)', (user,))
        row = db.execute('SELECT * FROM accounts WHERE user_id=?', (user,)).fetchone()
        if row is None:
            raise Conflict('unknown_account')
        if kind in ('buy_in', 'leave'):
            if active_hand(db, user) or row['in_flight']:
                raise Conflict('unsettled_hand')
            seat = db.execute('SELECT table_id FROM seats WHERE user_id=?', (user,)).fetchone()
            if kind == 'buy_in':
                chips = amount(data['amount'])
                if chips <= 0 or not 2000 <= row['table_chips'] + chips <= 10000:
                    raise Conflict('buy_in_range')
                if seat and seat['table_id'] != data['table_id']:
                    raise Conflict('already_at_table')
                db.execute('INSERT OR IGNORE INTO seats(user_id,table_id) VALUES(?,?)', (user, data['table_id']))
                change(db, cid, user, 'transfer', 'Table buy in', available=-chips, table=chips)
            else:
                change(db, cid, user, 'transfer', 'Leave table', available=row['table_chips'], table=-row['table_chips'])
                db.execute('DELETE FROM seats WHERE user_id=?', (user,))
        elif kind == 'subsidy':
            status = subsidy_status(db, user, now)
            if not status['eligible']:
                raise Conflict(status['reason'])
            chips = int(status['amount'])
            db.execute('INSERT INTO subsidies VALUES(?,?,?)', (user, status['day'], cid))
            change(db, cid, user, 'daily_subsidy', status['day'], available=chips, settled=chips)
        else:
            reason = data.get('reason')
            actor = data.get('actor')
            if not isinstance(reason, str) or not reason.strip() or len(reason) > 500 or not actor:
                raise Conflict('audit_reason_and_actor_required')
            chips = amount(data['amount'], signed=kind == 'adjust')
            if kind.startswith('npc_'):
                if not user.startswith('npc:') or active_hand(db, user):
                    raise Conflict('npc_funding_requires_idle_npc')
                chips = -chips if kind == 'npc_reclaim' else chips
                change(db, cid, user, kind, reason, table=chips, settled=chips)
            else:
                change(db, cid, user, 'admin_adjustment', reason, available=chips, settled=chips)
            db.execute('INSERT INTO admin_audit(command_id,actor,action,reason) VALUES(?,?,?,?)', (cid, actor, kind, reason))
        return account_view(db, user)
    if kind == 'start_hand':
        players = data['players']
        if not 2 <= len(players) <= 6 or len(set(players)) != len(players) or all(p.startswith('npc:') for p in players):
            raise Conflict('invalid_participants')
        if db.execute("SELECT 1 FROM hands WHERE table_id=? AND status='active'", (data['table_id'],)).fetchone():
            raise Conflict('table_hand_active')
        db.execute('INSERT INTO hands(hand_id,table_id,snapshot,status) VALUES(?,?,?,?)', (data['hand_id'], data['table_id'], json.dumps(data['snapshot']), 'active'))
        for player in players:
            row = db.execute('SELECT table_chips FROM accounts WHERE user_id=?', (player,)).fetchone()
            seat = db.execute('SELECT 1 FROM seats WHERE user_id=? AND table_id=?', (player, data['table_id'])).fetchone()
            if not row or row[0] <= 0 or active_hand(db, player) or (not player.startswith('npc:') and (not seat or not db.execute('SELECT 1 FROM sessions WHERE user_id=? AND revoked=0', (player,)).fetchone())):
                raise Conflict('participant_unavailable')
            db.execute('INSERT INTO participants(hand_id,user_id) VALUES(?,?)', (data['hand_id'], player))
        return {'hand_id': data['hand_id'], 'status': 'active'}
    hand = db.execute('SELECT * FROM hands WHERE hand_id=?', (data.get('hand_id'),)).fetchone()
    if not hand or hand['status'] != 'active':
        raise Conflict('hand_not_active')
    if kind == 'bet':
        chips = amount(data['amount'])
        if chips <= 0 or not db.execute('UPDATE participants SET contribution=contribution+? WHERE hand_id=? AND user_id=?', (chips, data['hand_id'], user)).rowcount:
            raise Conflict('invalid_bet')
        change(db, cid, user, 'pot_transfer', data['hand_id'], table=-chips, flight=chips)
    elif kind in ('settle', 'void'):
        participants = db.execute('SELECT * FROM participants WHERE hand_id=?', (data['hand_id'],)).fetchall()
        contributions = {p['user_id']: p['contribution'] for p in participants}
        payouts = contributions if kind == 'void' else {p: amount(v) for p, v in data['payouts'].items()}
        if not set(payouts) <= set(contributions) or sum(payouts.values()) != sum(contributions.values()):
            raise Conflict('payout_not_conserved')
        for player, paid in contributions.items():
            prize = payouts.get(player, 0)
            change(db, cid, player, 'void_refund' if kind == 'void' else 'hand_settlement', data['hand_id'], table=prize, flight=-paid, settled=prize-paid)
            if kind == 'settle' and not player.startswith('npc:'):
                db.execute('UPDATE accounts SET time_bank=MIN(60,time_bank+CASE WHEN hand_progress=9 THEN 5 ELSE 0 END),hand_progress=(hand_progress+1)%10 WHERE user_id=?', (player,))
                db.execute('INSERT INTO statistics(hand_id,user_id,net,opportunities) VALUES(?,?,?,?)', (data['hand_id'], player, prize-paid, json.dumps(data.get('opportunities', {}).get(player, {}))))
        db.execute('UPDATE hands SET status=?,snapshot=? WHERE hand_id=?', ('void' if kind == 'void' else 'settled', json.dumps(data.get('snapshot', json.loads(hand['snapshot']))), data['hand_id']))
        db.execute('INSERT INTO settlements(hand_id,command_id,kind) VALUES(?,?,?)', (data['hand_id'], cid, kind))
    elif kind == 'event':
        if data['expected_version'] != hand['version']:
            raise Conflict('stale_hand_version')
        db.execute('UPDATE hands SET snapshot=?,version=version+1 WHERE hand_id=?', (json.dumps(data['snapshot']), data['hand_id']))
    else:
        raise Conflict('unknown_command')
    db.execute('INSERT INTO hand_events(hand_id,command_id,event) VALUES(?,?,?)', (data['hand_id'], cid, json.dumps({'kind': kind, 'data': data})))
    return {'hand_id': data['hand_id'], 'status': 'void' if kind == 'void' else 'settled' if kind == 'settle' else 'active'}