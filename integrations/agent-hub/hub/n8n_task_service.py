"""Live task ledger and receipt reconciliation. No outbound business calls.

Legacy business schedulers retain ownership. A task can only be linked to an
existing exact source partition; ambiguous bindings require internal review.
"""
import json
import time
from decimal import Decimal, InvalidOperation
from hub.n8n_task_runner import TaskRunner, receive_plan


def runner(store):
    return TaskRunner(store, {}, mode='production')


def receive(store, batch, envelope):
    with store.db() as db:
        latest=db.execute("SELECT MAX(CAST(json_extract(payload,'$.timestamp') AS REAL)) FROM captures WHERE account=? AND thread_id=? AND json_extract(payload,'$.origin') IN ('customer','staff')",(batch['account'],batch['thread_id'])).fetchone()[0]
    cutoff=max(m['timestamp'] for m in batch['messages'])
    if latest and cutoff < latest <= cutoff+batch['wait_minutes']*60:
        return {'state':'superseded','tasks':[], 'effects_allowed':False}
    tasks=receive_plan(runner(store), batch, envelope)
    return {'state':'tasks_recorded','tasks':tasks,'effects_allowed':False}


def source_ids(payload):
    sources = payload.get('sources', payload.get('messages', []))
    return {str(m['message_id']) if isinstance(m, dict) else str(m)
            for m in sources if (isinstance(m, dict) and m.get('message_id')) or isinstance(m, (str, int))}


def same_quantity(left, right):
    try:
        a,b=Decimal(str(left)),Decimal(str(right))
        return a.is_finite() and b.is_finite() and a == b
    except InvalidOperation:
        return False


def reconcile(store):
    ledger = runner(store)
    results = []
    with store.db() as db:
        tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        tasks = db.execute("SELECT * FROM n8n_task_execution WHERE mode='production' AND state IN ('pending_binding','submitted','uncertain')").fetchall()
    for task in tasks:
        try:
            result = reconcile_one(store, task, tables)
            results.append(result)
        except Exception as exc:
            # One bad record must not prevent siblings from reconciliation.
            results.append({'id':task['id'], 'state':'reconcile_error', 'error':type(exc).__name__})
    return results


def reconcile_one(store, task, tables):
    payload = json.loads(task['payload'])
    wanted = set(payload['message_ids'])
    kind = task['kind']
    previous = json.loads(task['result'])
    candidates = []
    with store.db() as db:
        if kind=='print_approval' and previous.get('receipt_table')=='print_approvals' and 'print_approvals' in tables:
            row=db.execute('SELECT * FROM print_approvals WHERE id=? AND account=? AND thread_id=?',(previous.get('receipt_id'),task['account'],task['thread_id'])).fetchone()
            if row and row['confirmation_id'] in wanted:
                p=json.loads(row['payload']);state='done' if row['state']=='confirmed' else 'submitted'
                deliveries=[dict(r) for r in db.execute('SELECT account,state FROM print_deliveries WHERE approval_id=?',(row['id'],))] if 'print_deliveries' in tables else []
                result={**previous,'business_state':row['state'],'reason':p.get('reason',''),'details':{'deliveries':deliveries},'safe_to_retry':False}
                db.execute('UPDATE n8n_task_execution SET state=?,result=?,updated=? WHERE id=? AND state=?',(state,json.dumps(result,ensure_ascii=False),time.time(),task['id'],task['state']))
                return {'id':task['id'],'state':state,'result':result}
        if kind == 'sample_design' and previous.get('receipt_table') == 'psd_samples' and 'psd_samples' in tables:
            row = db.execute('SELECT * FROM psd_samples WHERE id=? AND account=? AND thread_id=?',(previous.get('receipt_id'),task['account'],task['thread_id'])).fetchone()
            if row:
                job=json.loads(row['payload'])
                hashes={a.get('sha256') for a in payload.get('source_refs',[]) if a.get('sha256')}
                if set(job.get('messages',[]))==wanted and (job.get('asset') or {}).get('sha256') in hashes:
                    report=job.get('report') or {}
                    state='done' if row['state']=='done' and report.get('path') else 'submitted'
                    result={**previous,'business_state':row['state'],'details':{'archive_relative':report.get('path')},'reason':job.get('reason',''),'safe_to_retry':False}
                    db.execute('UPDATE n8n_task_execution SET state=?,result=?,updated=? WHERE id=? AND state=?',(state,json.dumps(result,ensure_ascii=False),time.time(),task['id'],task['state']))
                    return {'id':task['id'],'state':state,'result':result}
        if kind == 'erp_order' and 'intake_runs' in tables:
            for r in db.execute('SELECT * FROM intake_runs WHERE account=? AND thread_id=?', (task['account'],task['thread_id'])):
                p = json.loads(r['payload'])
                if source_ids(p) != wanted: continue
                if p.get('n8n_task_id') == task['id'] and r['id'] == previous.get('receipt_id'):
                    candidates.append((dict(r),json.loads(r['result'] or '{}')))
                    continue
                # A whole-batch receipt cannot be assigned to each split order.
                lines=p.get('orders', [])
                names={str(o.get('ten_mau','')).strip().casefold() for o in lines}
                if names != {str(payload.get('model_code','')).strip().casefold()}: continue
                if any(not same_quantity(o.get('so_luong'),payload.get('quantity')) for o in lines): continue
                candidates.append((dict(r),json.loads(r['result'] or '{}')))
        elif kind in ('export_pet','export_jpg') and 'design_briefs' in tables:
            table = 'pet_exports' if kind == 'export_pet' else 'jpg_exports'
            if table in tables:
                for brief in db.execute('SELECT * FROM design_briefs WHERE account=? AND thread_id=?',(task['account'],task['thread_id'])):
                    p=json.loads(brief['payload'])
                    if source_ids(p) != wanted: continue
                    codes=[p.get('brief',{}).get('title','')]+[f.get('value','') for f in p.get('brief',{}).get('bag_facts',[]) if f.get('field')=='design_code']
                    if not any(str(c).strip().casefold()==str(payload.get('model_code','')).strip().casefold() for c in codes):continue
                    if previous.get('brief_ids') and brief['id'] not in previous['brief_ids']:continue
                    for r in db.execute('SELECT * FROM '+table+" WHERE account=? AND json_extract(payload,'$.brief_id')=?",(task['account'],brief['id'])):
                        job=json.loads(r['payload'])
                        # Exact source hash prevents attaching another file/version.
                        hashes={a.get('sha256') for a in payload.get('source_refs',[]) if a.get('sha256')}
                        job_hash=(job.get('asset') or {}).get('sha256') or (job.get('source',{}).get('asset') or {}).get('sha256') or job.get('source_sha256')
                        if not job_hash or job_hash not in hashes: continue
                        candidates.append((dict(r),{'archive_relative':job.get('archive_relative'), 'brief_id':brief['id']}))
        if previous.get('receipt_id'):
            candidates=[c for c in candidates if c[0]['id']==previous['receipt_id']]
        if len(candidates)!=1:
            reason='AMBIGUOUS_BUSINESS_RECEIPT' if candidates else 'WAITING_VERIFIED_BUSINESS_BINDING'
            result={'reason':reason, 'candidate_count':len(candidates), 'safe_to_retry':False}
            result.update({k:previous[k] for k in ('design_run_id','brief_ids','receipt_id') if k in previous})
            state=task['state']
        else:
            row, details=candidates[0]
            business_state=row['state']
            complete=(kind=='erp_order' and business_state=='created' and bool(details.get('orders'))) or (kind!='erp_order' and business_state=='done' and bool(details.get('archive_relative')))
            state='done' if complete else 'uncertain' if business_state in ('uncertain','sending') else 'submitted'
            result={'receipt_id':row['id'],'business_state':business_state,'details':details,'safe_to_retry':False}
            result.update({k:previous[k] for k in ('design_run_id','brief_ids') if k in previous})
        db.execute("UPDATE n8n_task_execution SET state=?,result=?,updated=? WHERE id=? AND state=?",(state,json.dumps(result,ensure_ascii=False),time.time(),task['id'],task['state']))
    return {'id':task['id'],'state':state,'result':result}
