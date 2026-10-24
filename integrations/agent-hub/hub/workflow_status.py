"""Read-only per-brief projection. Never infers approval from file creation."""
import json


def snapshot(db, limit=100):
    limit = max(1, min(int(limit), 500))
    tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if 'design_briefs' not in tables:
        return []
    output = []
    for row in db.execute('SELECT * FROM design_briefs ORDER BY created DESC LIMIT ?', (limit,)):
        brief = dict(row)
        detail = json.loads(brief['payload']) if 'payload' in brief else {}
        group = db.execute('SELECT display_name FROM threads WHERE account=? AND thread_id=?',(brief['account'],brief['thread_id'])).fetchone() if 'threads' in tables else None
        run = None
        if 'intake_runs' in tables:
            found = db.execute('SELECT id,state,result FROM intake_runs WHERE id=?', (brief['run_id'],)).fetchone()
            run = dict(found) if found else None
        exports = []
        for table in ('pet_exports', 'jpg_exports'):
            if table not in tables:
                continue
            for item in db.execute('SELECT id,state,payload FROM ' + table + " WHERE account=? AND state<>'archived'", (brief['account'],)):
                try:
                    payload = json.loads(item['payload'])
                except (TypeError, ValueError):
                    continue
                if payload.get('brief_id') != brief['id']:
                    continue
                exports.append({'id': item['id'], 'kind': table, 'state': item['state'],
                                'review_reason': payload.get('review_reason', ''),
                                'approval': 'not_recorded'})
        output.append({'brief_id': brief['id'], 'account': brief['account'],
                       'thread_id': brief['thread_id'], 'group': group[0] if group else brief['thread_id'], 'title': detail.get('brief',{}).get('title',''), 'conversation': brief['conversation'],
                       'intake': run, 'exports': exports,
                       'customer_send_allowed': False, 'rip_allowed': False})
    return output

