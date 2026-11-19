"""Per-model handoff to existing design validation and Windows export workers."""
import json
import time
from pathlib import Path


def tick(engine):
    path=Path(engine.store.path).parent/'n8n-connector.json'
    if not path.exists(): return []
    cfg=json.loads(path.read_text())
    if cfg.get('print_dispatch_enabled') is not True:return []
    boundary=cfg.get('print_dispatch_enabled_after')
    if not isinstance(boundary,(int,float)) or boundary<=0:raise ValueError('PRINT_ACTIVATION_BOUNDARY_REQUIRED')
    return dispatch(engine,boundary)


def dispatch(engine,boundary=0):
    with engine.store.db() as db:
        tasks=db.execute("SELECT * FROM n8n_task_execution WHERE mode='production' AND kind IN ('export_pet','export_jpg') AND state='pending_binding' ORDER BY updated,id").fetchall()
    results=[]
    for row in tasks:
        task=dict(row);p=json.loads(task['payload'])
        if p.get('batch_cutoff',0)<boundary:continue
        try:results.append(start(engine,task,p))
        except Exception as exc:
            with engine.store.db() as db:
                db.execute("UPDATE n8n_task_execution SET state=CASE WHEN state='executing' THEN 'uncertain' ELSE 'waiting_information' END,result=?,updated=? WHERE id=? AND state IN ('pending_binding','executing')",(json.dumps({'reason':str(exc)[:250] if isinstance(exc,ValueError) else type(exc).__name__,'safe_to_retry':False}),time.time(),task['id']))
            results.append({'id':task['id'],'state':'needs_review'})
    return results


def start(engine,task,p):
    run_id='n8n-print:'+task['id']
    with engine.store.db() as db:
        db.execute('BEGIN IMMEDIATE')
        current=db.execute('SELECT state FROM n8n_task_execution WHERE id=?',(task['id'],)).fetchone()
        if not current or current[0]!='pending_binding':return {'id':task['id'],'state':'already_claimed'}
        mapping=db.execute('SELECT * FROM threads WHERE account=? AND thread_id=?',(task['account'],task['thread_id'])).fetchone()
        if not mapping:raise ValueError('PRINT_GROUP_NOT_BOUND')
        from hub.n8n_policy_gate import check
        if check(engine,task['account'],task['thread_id'],mapping['display_name']):raise ValueError('PRINT_GROUP_EXCLUDED_OR_POLICY_UNAVAILABLE')
        messages=[]
        for mid in p['message_ids']:
            r=db.execute('SELECT payload FROM captures WHERE account=? AND thread_id=? AND message_id=? ORDER BY revision DESC LIMIT 1',(task['account'],task['thread_id'],mid)).fetchone()
            if not r:raise ValueError('PRINT_SOURCE_MISSING')
            m=json.loads(r[0])
            if m.get('revision') or m.get('recalled'):raise ValueError('PRINT_SOURCE_CHANGED')
            messages.append(m)
        latest=db.execute("SELECT MAX(CAST(json_extract(payload,'$.timestamp') AS REAL)) FROM captures WHERE account=? AND thread_id=? AND json_extract(payload,'$.origin') IN ('customer','staff')",(task['account'],task['thread_id'])).fetchone()[0]
        if latest and latest>p['batch_cutoff']:raise ValueError('PRINT_BATCH_SUPERSEDED')
        if latest and time.time()-latest<engine.intake_management.seconds():return {'id':task['id'],'state':'collecting'}
        # Bind only files explicitly assigned by n8n, while retaining maket images.
        wanted=set(p.get('asset_ids',[]))
        expected={str(a['id']):a.get('sha256') for a in p.get('source_refs',[])}
        found=set()
        for m in messages:
            m['assets']=[a for a in m.get('assets',[]) if str(a.get('id')) in wanted]
            for a in m['assets']:
                aid=str(a['id']);found.add(aid)
                if a.get('state')!='ready' or not expected.get(aid) or a.get('sha256')!=expected[aid]:raise ValueError('PRINT_ASSET_CHANGED_OR_UNREADY')
        if found!=wanted:raise ValueError('PRINT_ASSET_MISSING')
        if not p.get('model_code'):raise ValueError('PRINT_MODEL_REQUIRED')
        existing=[]
        for row in db.execute('SELECT id,payload FROM design_briefs WHERE account=? AND thread_id=?',(task['account'],task['thread_id'])):
            b=json.loads(row['payload'])
            ids={str(s['message_id']) for s in b.get('sources',[])}
            codes=[b.get('brief',{}).get('title','')]+[f.get('value','') for f in b.get('brief',{}).get('bag_facts',[]) if f.get('field')=='design_code']
            if ids==set(p['message_ids']) and any(str(c).strip().casefold()==str(p['model_code']).strip().casefold() for c in codes):existing.append(row['id'])
        if len(existing)>1:raise ValueError('PRINT_EXISTING_BRIEF_AMBIGUOUS')
        if existing:
            db.execute("UPDATE n8n_task_execution SET state='submitted',result=?,updated=? WHERE id=?",(json.dumps({'brief_ids':existing,'safe_to_retry':False,'reused':True}),time.time(),task['id']))
            return {'id':task['id'],'state':'submitted','reused':True}
        db.execute("UPDATE n8n_task_execution SET state='executing',result=?,updated=? WHERE id=?",(json.dumps({'design_run_id':run_id,'safe_to_retry':False}),time.time(),task['id']))
    run=dict(id=run_id,account=task['account'],thread_id=task['thread_id'],conversation=mapping['conversation'],n8n_print=p)
    engine.order_intake.design_briefs.collect(run,messages)
    with engine.store.db() as db:
        briefs=[r['id'] for r in db.execute('SELECT id FROM design_briefs WHERE run_id=? AND account=? AND thread_id=?',(run_id,task['account'],task['thread_id']))]
        state='submitted' if briefs else 'waiting_information'
        result={'design_run_id':run_id,'brief_ids':briefs,'safe_to_retry':False,'reason':None if briefs else 'DESIGN_VALIDATION_NOT_COMPLETED'}
        db.execute('UPDATE n8n_task_execution SET state=?,result=?,updated=? WHERE id=? AND state=?',(state,json.dumps(result),time.time(),task['id'],'executing'))
    return {'id':task['id'],'state':state}
