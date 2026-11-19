"""Validate n8n plans and persist review tasks. No business side effects."""
import hashlib
import json
import time

OPERATIONS={'A':'inspect_sources','B':'prepare_erp','C':'prepare_sample',
            'D':'match_slip_design','E':'prepare_reply'}
TASK_ROUTES={'inspect_sources':'A','erp_order':'B','export_pet':'C',
             'sample_design':'C','export_jpg':'D','reply':'E'}

def accept(store,batch,reply):
    version=reply.get('protocol')
    if version not in (1,2) or reply.get('batch_id')!=batch['batch_id'] or reply.get('revision')!=batch['revision']:
        raise ValueError('N8N_PLAN_BATCH_MISMATCH')
    if reply.get('effects_allowed') is not False:raise ValueError('N8N_PLAN_EXECUTION_FORBIDDEN')
    messages={str(m['message_id']):m for m in batch['messages']}
    assets={str(a['id']) for m in batch['messages'] for a in m.get('assets',[])}
    images={str(i) for m in batch['messages'] for i in m.get('image_ids',[])}
    tasks=[]
    if version==2 and (reply.get('account')!=batch['account'] or reply.get('thread_id')!=batch['thread_id']):
        raise ValueError('N8N_TASK_GROUP_MISMATCH')
    incoming=reply.get('tasks' if version==2 else 'requests')
    if not isinstance(incoming,list):raise ValueError('N8N_TASKS_REQUIRED')
    for request in incoming:
        if version==2:
            kind=request.get('task_kind')
            if kind not in TASK_ROUTES or request.get('branches')!=[TASK_ROUTES[kind]]:
                raise ValueError('N8N_TASK_ROUTE_MISMATCH')
            if request.get('account')!=batch['account'] or request.get('thread_id')!=batch['thread_id']:
                raise ValueError('N8N_TASK_GROUP_MISMATCH')
            if request.get('effects_allowed') is not False:raise ValueError('N8N_TASK_EXECUTION_FORBIDDEN')
        ids=set(map(str,request.get('message_ids',[])))
        if not ids or not ids<=messages.keys():raise ValueError('N8N_PLAN_WRONG_SOURCE')
        if not set(map(str,request.get('asset_ids',[])))<=assets or not set(map(str,request.get('image_ids',[])))<=images:
            raise ValueError('N8N_PLAN_WRONG_FILE')
        owned_assets={str(a['id']) for mid in ids for a in messages[mid].get('assets',[])}
        owned_images={str(i) for mid in ids for i in messages[mid].get('image_ids',[])}
        if not set(map(str,request.get('asset_ids',[])))<=owned_assets or not set(map(str,request.get('image_ids',[])))<=owned_images:
            raise ValueError('N8N_PLAN_FILE_NOT_IN_REQUEST_MESSAGES')
        for branch in set(request.get('branches',[])):
            if branch not in OPERATIONS:raise ValueError('N8N_PLAN_UNKNOWN_BRANCH')
            identity=hashlib.sha256(json.dumps([batch['account'],batch['thread_id'],sorted(ids),
                request.get('model_code'),request.get('quantity'),request.get('quantity_mode'),
                request.get('print_positions'),branch,request.get('task_kind'),
                sorted(map(str,request.get('asset_ids',[]))),sorted(map(str,request.get('image_ids',[]))),
                request.get('spec',{})],ensure_ascii=False,sort_keys=True).encode()).hexdigest()
            # Resolve paths only from original trusted batch, never from model output.
            request=dict(request)
            wanted=set(map(str,request.get('asset_ids',[])))
            request['source_refs']=[a for mid in sorted(ids) for a in messages[mid].get('assets',[]) if str(a['id']) in wanted]
            tasks.append((identity,branch,request))
    with store.db() as db:
        db.execute('''CREATE TABLE IF NOT EXISTS n8n_review_tasks(
          id TEXT PRIMARY KEY,batch_id TEXT,branch TEXT,operation TEXT,account TEXT,
          thread_id TEXT,payload TEXT,state TEXT,created REAL)''')
        db.execute('BEGIN IMMEDIATE')
        latest=db.execute("SELECT MAX(CAST(json_extract(payload,'$.timestamp') AS REAL)) FROM captures WHERE account=? AND thread_id=? AND json_extract(payload,'$.origin') IN ('customer','staff')",
                          (batch['account'],batch['thread_id'])).fetchone()[0]
        cutoff=max(m['timestamp'] for m in batch['messages'])
        if latest and latest>cutoff and latest-cutoff<=batch['wait_minutes']*60:
            return {'state':'superseded','task_ids':[],'effects_allowed':False}
        for identity,branch,request in tasks:
            db.execute("INSERT OR IGNORE INTO n8n_review_tasks VALUES(?,?,?,?,?,?,?,'pending_review',?)",
                (identity,batch['batch_id'],branch,request.get('task_kind') if version==2 else OPERATIONS[branch],batch['account'],batch['thread_id'],
                 json.dumps(request,ensure_ascii=False),time.time()))
    return {'state':'pending_review','task_ids':sorted({t[0] for t in tasks}),'effects_allowed':False}
