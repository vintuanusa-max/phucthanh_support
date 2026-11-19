"""New-task-only adapters. Reuse PSD worker; draft replies remain internal.

No ERP calls, outbound customer messages, or image generation here.
"""
import hashlib
import json
import time
from pathlib import Path


def tick(engine):
    marker = Path(engine.store.path).parent / 'n8n-aux-enabled-after'
    if not marker.exists():
        return []
    boundary = float(marker.read_text())
    if boundary <= 0:
        raise ValueError('AUX_BOUNDARY_REQUIRED')
    with engine.store.db() as db:
        rows = db.execute("SELECT * FROM n8n_task_execution WHERE mode='production' AND kind IN ('sample_design','reply') AND state='pending_binding'").fetchall()
    results = []
    for row in rows:
        p = json.loads(row['payload'])
        if p.get('batch_cutoff', 0) < boundary:
            continue
        try:
            results.append(start(engine, dict(row), p))
        except Exception as exc:
            # Transaction rolls back before any worker claim; do not retry blind.
            with engine.store.db() as db:
                db.execute("UPDATE n8n_task_execution SET state='waiting_information',result=?,updated=? WHERE id=? AND state='pending_binding'", (json.dumps({'reason':str(exc)[:300] if isinstance(exc,ValueError) else type(exc).__name__,'safe_to_retry':False}),time.time(),row['id']))
    return results


def start(engine, task, p):
    from hub.psd_samples import init, sample_only
    if task['kind'] == 'sample_design':
        init(engine)
    with engine.store.db() as db:
        db.execute('BEGIN IMMEDIATE')
        row = db.execute('SELECT state FROM n8n_task_execution WHERE id=?',(task['id'],)).fetchone()
        if not row or row[0] != 'pending_binding':
            return {'state':'already_claimed'}
        mapping = db.execute('SELECT * FROM threads WHERE account=? AND thread_id=?',(task['account'],task['thread_id'])).fetchone()
        if not mapping:
            raise ValueError('AUX_GROUP_NOT_BOUND')
        messages = []
        for mid in p['message_ids']:
            row = db.execute('SELECT payload FROM captures WHERE account=? AND thread_id=? AND message_id=? ORDER BY revision DESC LIMIT 1',(task['account'],task['thread_id'],mid)).fetchone()
            if not row:
                raise ValueError('AUX_SOURCE_MISSING')
            m = json.loads(row[0])
            if m.get('revision') or m.get('recalled'):
                raise ValueError('AUX_SOURCE_CHANGED')
            messages.append(m)
        from hub.n8n_policy_gate import check
        policy = engine.order_intake.policy(task['account'])
        channel = engine.settings.inboxes[task['account']]['channel']
        if check(engine,task['account'],task['thread_id'],mapping['display_name']):
            raise ValueError('AUX_GROUP_EXCLUDED')
        latest = db.execute("SELECT MAX(CAST(json_extract(payload,'$.timestamp') AS REAL)) FROM captures WHERE account=? AND thread_id=? AND json_extract(payload,'$.origin') IN ('customer','staff')",(task['account'],task['thread_id'])).fetchone()[0]
        if latest and latest > p['batch_cutoff']:
            raise ValueError('AUX_BATCH_SUPERSEDED')
        if latest and time.time()-latest < engine.intake_management.seconds():
            return {'state':'collecting'}
        if task['kind'] == 'reply':
            draft = p.get('reply_draft')
            if not isinstance(draft,str) or not draft.strip():
                raise ValueError('REPLY_DRAFT_MISSING')
            # Save locally only. Approval summaries use the existing approval ledger,
            # never send arbitrary model text through bot101.
            state = 'waiting_information'
            result = {'reason':'Bản trả lời đã soạn, chờ duyệt nội bộ; chưa gửi khách.', 'reply_draft':draft[:8000], 'safe_to_retry':False}
        else:
            if not sample_only(messages):
                raise ValueError('SAMPLE_ONLY_CONTEXT_NOT_VERIFIED')
            assigned = set(p.get('asset_ids') or [])
            expected = {str(a['id']):a.get('sha256') for a in p.get('source_refs',[])}
            candidates = {str(a['id']):a for m in messages for a in m.get('assets',[]) if str(a.get('id')) in assigned and a.get('name','').lower().endswith('.psd')}
            if len(candidates) != 1:
                raise ValueError('Lên mẫu cần đúng một PSD đã gắn nguồn; raster/AI dùng nhánh xuất tương ứng.')
            asset = next(iter(candidates.values()))
            if asset.get('state') != 'ready' or not asset.get('sha256') or expected.get(str(asset['id'])) != asset['sha256']:
                raise ValueError('PSD_SOURCE_NOT_READY_OR_CHANGED')
            # Match legacy sample jobs by exact source partition and file hash.
            existing = []
            for old in db.execute('SELECT * FROM psd_samples WHERE account=? AND thread_id=?',(task['account'],task['thread_id'])):
                op = json.loads(old['payload'])
                if set(op.get('messages',[])) == set(p['message_ids']):
                    if (op.get('asset') or {}).get('sha256') != asset['sha256']:
                        raise ValueError('PSD_EXISTING_SOURCE_CONFLICT')
                    existing.append(old['id'])
            if len(existing)>1:
                raise ValueError('PSD_EXISTING_JOB_AMBIGUOUS')
            identity = existing[0] if existing else hashlib.sha256(('psd-sample:'+task['account']+task['thread_id']+':'.join(sorted(m['message_id'] for m in messages))).encode()).hexdigest()
            payload = dict(title='Lên mẫu — '+asset['name'],request=' '.join(m.get('text','') for m in messages),messages=p['message_ids'],asset=asset,sample_only=True,policy='original_psd_size',source_timestamp=p['batch_cutoff'],reason='',n8n_task_id=task['id'])
            db.execute('INSERT OR IGNORE INTO psd_samples VALUES(?,?,?,?,?,?,?)',(identity,task['account'],task['thread_id'],mapping['conversation'],'queued',json.dumps(payload,ensure_ascii=False),time.time()))
            state = 'submitted'
            result = {'receipt_id':identity,'receipt_table':'psd_samples','safe_to_retry':False,'reused':bool(existing)}
        db.execute('UPDATE n8n_task_execution SET state=?,result=?,attempts=attempts+1,updated=? WHERE id=? AND state=?',(state,json.dumps(result,ensure_ascii=False),time.time(),task['id'],'pending_binding'))
    return {'id':task['id'],'state':state}
