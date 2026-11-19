"""Claim each n8n ERP task into the existing verified intake pipeline.

Does not call ERP or send messages. Disabled unless explicitly configured.
The intake pipeline remains responsible for evidence, customer binding and writes.
"""
import json
import time
from pathlib import Path
from decimal import Decimal


def validate_expected(expected, orders):
    if not expected.get('model_code') or not orders:
        raise ValueError('N8N_ORDER_MODEL_REQUIRED')
    positions=expected.get('print_positions') or []
    if len(orders) != max(1,len(positions)):
        raise ValueError('N8N_ORDER_LINE_COUNT_MISMATCH')
    for line in orders:
        if str(line.get('ten_mau','')).strip().casefold() != str(expected['model_code']).strip().casefold():
            raise ValueError('N8N_ORDER_MODEL_MISMATCH')
        if Decimal(str(line.get('so_luong'))) != Decimal(str(expected['quantity'])):
            raise ValueError('N8N_ORDER_QUANTITY_MISMATCH')


def tick(engine):
    path=Path(engine.store.path).parent/'n8n-connector.json'
    if not path.exists(): return []
    config=json.loads(path.read_text())
    if config.get('erp_dispatch_enabled') is not True: return []
    boundary=config.get('erp_dispatch_enabled_after')
    if not isinstance(boundary,(int,float)) or boundary<=0:
        raise ValueError('N8N_ERP_ACTIVATION_BOUNDARY_REQUIRED')
    return dispatch(engine, enabled_after=boundary)


def dispatch(engine, *, enabled_after=0):
    with engine.store.db() as db:
        tasks=db.execute("SELECT * FROM n8n_task_execution WHERE mode='production' AND kind='erp_order' AND state='pending_binding' ORDER BY updated,id").fetchall()
    results=[]
    for task in tasks:
        if json.loads(task['payload']).get('batch_cutoff',0) < enabled_after: continue
        try:
            results.append(enqueue(engine,dict(task)))
        except Exception as exc:
            reason=str(exc)[:250] if isinstance(exc,ValueError) else type(exc).__name__
            with engine.store.db() as db:
                db.execute("UPDATE n8n_task_execution SET state='waiting_information',result=?,updated=? WHERE id=? AND state='pending_binding'",(json.dumps({'reason':reason,'safe_to_retry':False}),time.time(),task['id']))
            results.append({'id':task['id'],'state':'waiting_information','reason':reason})
    return results


def enqueue(engine, task):
    p=json.loads(task['payload'])
    if p.get('intent')!='order' or p.get('quantity_mode')!='total' or not p.get('model_code'):
        raise ValueError('N8N_ERP_REQUIRES_VERIFIED_NEW_ORDER; additional/total amendment needs reconciliation')
    intake=engine.order_intake
    if not engine.intake_management.enabled(task['account']):
        raise ValueError('ERP_INTAKE_DISABLED')
    mids=p['message_ids']
    run_id='n8n-erp:'+task['id']
    with engine.store.db() as db:
        db.execute('BEGIN IMMEDIATE')
        current=db.execute('SELECT state FROM n8n_task_execution WHERE id=?',(task['id'],)).fetchone()
        if not current or current[0]!='pending_binding': return {'id':task['id'],'state':'already_claimed'}
        mapping=db.execute('SELECT * FROM threads WHERE account=? AND thread_id=?',(task['account'],task['thread_id'])).fetchone()
        from hub.n8n_policy_gate import check
        if not mapping or check(engine,task['account'],task['thread_id'],mapping['display_name']):
            raise ValueError('N8N_GROUP_POLICY_BLOCKED')
        # Never take sources from the old scheduler, including already-created orders.
        sources=[]
        for mid in mids:
            row=db.execute('SELECT id,payload FROM captures WHERE account=? AND thread_id=? AND message_id=? ORDER BY revision DESC LIMIT 1',(task['account'],task['thread_id'],mid)).fetchone()
            if not row: raise ValueError('N8N_ERP_SOURCE_MISSING')
            message=json.loads(row['payload'])
            # Staff source is context for a customer's confirmation, not an order
            # author. Keep it so quantity/position questions remain understandable.
            if message.get('revision') or message.get('recalled') or (message.get('origin')!='staff' and not intake.accepts(message)):
                raise ValueError('N8N_ERP_SOURCE_CHANGED_OR_NOT_ORDER_SOURCE')
            claim=db.execute('SELECT run_id FROM intake_sources WHERE capture_id=?',(row['id'],)).fetchone()
            if claim and claim[0]!=run_id:
                db.execute("UPDATE n8n_task_execution SET state='submitted',result=?,updated=? WHERE id=?",(json.dumps({'receipt_id':claim[0],'reason':'EXISTING_INTAKE_REQUIRES_RECONCILIATION','safe_to_retry':False}),time.time(),task['id']))
                return {'id':task['id'],'state':'submitted','existing_intake':True}
            sources.append((row['id'],message))
        mapping=db.execute('SELECT * FROM threads WHERE account=? AND thread_id=?',(task['account'],task['thread_id'])).fetchone()
        if not mapping: raise ValueError('N8N_ERP_GROUP_NOT_BOUND')
        latest=db.execute("SELECT MAX(CAST(json_extract(payload,'$.timestamp') AS REAL)) FROM captures WHERE account=? AND thread_id=? AND json_extract(payload,'$.origin') IN ('customer','staff')",(task['account'],task['thread_id'])).fetchone()[0]
        if latest and time.time()-latest < engine.intake_management.seconds():
            return {'id':task['id'],'state':'collecting'}
        if latest and latest > p.get('batch_cutoff',0):
            raise ValueError('N8N_ERP_BATCH_SUPERSEDED')
        # Detect source overlap between proposed orders before creating either one.
        for sibling in db.execute("SELECT id,payload FROM n8n_task_execution WHERE batch_id=? AND kind='erp_order' AND id<>? AND state NOT IN ('unsupported','invalid')",(task['batch_id'],task['id'])):
            if set(mids)&set(json.loads(sibling['payload'])['message_ids']):
                raise ValueError('N8N_ERP_SHARED_ORDER_SOURCE_NEEDS_PARTITION')
        messages=[m for _,m in sources]
        if not any(intake.accepts(m) for m in messages):
            raise ValueError('N8N_ORDER_CUSTOMER_CONFIRMATION_REQUIRED')
        payload=dict(messages=mids,group_name=mapping['display_name'],sender=messages[-1].get('sender',''),
            sender_key=messages[-1].get('sender_id') or messages[-1].get('sender',''),
            first_timestamp=min(m['timestamp'] for m in messages),last_timestamp=p['batch_cutoff'],
            collection_scope='group',model_parent='n8n:'+task['batch_id'],n8n_expected=p,n8n_task_id=task['id'])
        db.execute("INSERT OR IGNORE INTO intake_runs(id,account,thread_id,conversation,state,payload,result,created) VALUES(?,?,?,?,'model_pending',?,'{}',?)",
            (run_id,task['account'],task['thread_id'],mapping['conversation'],json.dumps(payload,ensure_ascii=False),time.time()))
        for cid,_ in sources: db.execute('INSERT OR IGNORE INTO intake_sources VALUES(?,?)',(cid,run_id))
        db.execute("UPDATE n8n_task_execution SET state='submitted',result=?,updated=? WHERE id=?",(json.dumps({'receipt_id':run_id,'business_state':'model_pending','safe_to_retry':False}),time.time(),task['id']))
    return {'id':task['id'],'state':'submitted','receipt_id':run_id}
