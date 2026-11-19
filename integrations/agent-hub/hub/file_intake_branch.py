"""Durable print branch from the settled batch, before ERP intent/quantity gates."""
import json
import time

CANAVI = {'g1790239230897256718', 'g2671966061008128194'}

def has_print_source(messages, thread):
    for m in messages:
        if m.get('recalled') or m.get('revision') or m.get('role') == 'bot':
            continue
        if any(a.get('name', '').lower().endswith(('.ai', '.pdf', '.psd', '.cdr')) for a in m.get('assets', [])):
            return True
        # Primary sender image policy was applied before this function.
        if thread in CANAVI and m.get('images'):
            return True
    return False

def enqueue(intake, run, messages):
    from hub.dispatch_admission import allowed
    if not allowed(run,messages,intake.policy(run['account'])):return False
    from hub.order_policy import capture_allowed
    from hub.store import event_key
    policy = intake.policy(run['account'])
    mapping = intake.store.thread(account=run['account'], thread_id=run['thread_id'])
    channel = intake.engine.settings.inboxes[run['account']]['channel']
    if not policy or not mapping or not capture_allowed(policy, channel, run['thread_id'], mapping['display_name']):
        return None
    if not has_print_source(messages, run['thread_id']):
        return None
    sources = sorted((m['message_id'], m.get('revision', 0)) for m in messages)
    identity = event_key('independent-print-batch-v1', run['account'], run['thread_id'], sources)
    payload = {'run': dict(run), 'messages': messages}
    payload['run']['independent_print_batch'] = True
    # INSERT OR IGNORE preserves finished, uncertain and in-flight work.
    with intake.store.db() as db:
        db.execute('INSERT OR IGNORE INTO jobs(id,kind,payload,created) VALUES(?,?,?,?)',
                   (identity, 'design_brief', json.dumps(payload, ensure_ascii=False), time.time()))
    return identity
