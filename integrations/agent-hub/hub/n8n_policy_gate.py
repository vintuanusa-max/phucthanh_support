"""Fresh group policy at collection, dispatch and result boundaries."""
import json
import time
from hub.order_policy import capture_allowed, key


def check(engine, account, thread_id, name):
    policy = engine.order_intake.policy(account)
    if not policy:
        return 'policy_unavailable'
    cfg = engine.settings.inboxes.get(account, {})
    # Internal notification destinations are never customer intake sources.
    for destination in engine.settings.inboxes.values():
        route = destination.get('print_forward', {})
        if route.get('thread_id') == thread_id and destination.get('channel') == cfg.get('channel'):
            return 'internal_destination'
    if not capture_allowed(policy, cfg.get('channel',''), thread_id, name):
        return 'excluded_group'
    return None


def normalize(message, policy, channel):
    internal = {key(v) for v in policy.get(channel+'_internal_members',[])}
    if key(message.get('sender','')) in internal:
        return {**message, 'origin':'staff'}
    return message


def quarantine(engine):
    """Only cancel unstarted tasks. Sent/uncertain/completed work is preserved."""
    with engine.store.db() as db:
        if not db.execute("SELECT 1 FROM sqlite_master WHERE name='n8n_task_execution'").fetchone():
            return
        rows = db.execute("SELECT t.id,t.account,t.thread_id,g.display_name FROM n8n_task_execution t LEFT JOIN threads g ON g.account=t.account AND g.thread_id=t.thread_id WHERE t.mode='production' AND t.state IN ('pending_binding','waiting_information')").fetchall()
    for r in rows:
        reason=check(engine,r['account'],r['thread_id'],r['display_name'] or '')
        if reason not in ('excluded_group','internal_destination'):
            continue
        with engine.store.db() as db:
            db.execute("UPDATE n8n_task_execution SET state='excluded',result=?,updated=? WHERE id=? AND state IN ('pending_binding','waiting_information')",(json.dumps({'reason':'Nhóm nội bộ/bỏ qua theo cấu hình hiện tại; không thực thi.','safe_to_retry':False}),time.time(),r['id']))
