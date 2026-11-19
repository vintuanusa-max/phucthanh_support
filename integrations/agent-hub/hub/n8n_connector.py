"""Opt-in metadata outbox for n8n. Never executes returned business actions."""
import hashlib
import json
import time
from pathlib import Path

import httpx

from hub.n8n_nas_contract import envelope


def initialize(store):
    with store.db() as db:
        db.executescript('''
        CREATE TABLE IF NOT EXISTS n8n_batch_outbox(
          id TEXT PRIMARY KEY,account TEXT,thread_id TEXT,revision TEXT,
          payload TEXT,state TEXT,result TEXT,created REAL,updated REAL);
        CREATE TABLE IF NOT EXISTS n8n_batch_sources(
          capture_id TEXT PRIMARY KEY,batch_id TEXT NOT NULL);
        ''')


def tick(engine):
    config_path=Path(engine.store.path).parent/'n8n-connector.json'
    if not config_path.exists():return
    config=json.loads(config_path.read_text())
    if not config.get('enabled'):return
    if not config.get('enabled_after') or config.get('mode')!='analysis_only':
        raise ValueError('Explicit activation boundary and analysis-only mode required')
    url=config.get('webhook_url','')
    if not url.startswith('https://n8n.vintuan.com/webhook/'):
        raise ValueError('Unapproved n8n destination')
    initialize(engine.store)
    now=time.time();seconds=engine.intake_management.seconds()
    with engine.store.db() as db:
        threads=db.execute('SELECT * FROM threads').fetchall()
    from hub.order_policy import capture_allowed
    from hub.n8n_policy_gate import check, normalize
    for thread in threads:
        policy=engine.order_intake.policy(thread['account'])
        channel=engine.settings.inboxes.get(thread['account'],{}).get('channel','')
        if check(engine,thread['account'],thread['thread_id'],thread['display_name']):continue
        with engine.store.db() as db:
            rows=db.execute("SELECT c.id,c.payload FROM captures c WHERE c.account=? AND c.thread_id=? AND CAST(json_extract(c.payload,'$.timestamp') AS REAL)>=? AND NOT EXISTS(SELECT 1 FROM n8n_batch_sources s WHERE s.capture_id=c.id) ORDER BY CAST(json_extract(c.payload,'$.timestamp') AS REAL),c.id",
                (thread['account'],thread['thread_id'],config['enabled_after'])).fetchall()
        rows=[(r['id'],json.loads(r['payload'])) for r in rows]
        rows=[(i,normalize(m,policy,channel)) for i,m in rows]
        rows=[(i,m) for i,m in rows if m.get('origin') in ('customer','staff') and not m.get('recalled')]
        if not rows or now-max(m['timestamp'] for _,m in rows)<seconds:continue
        # Split sessions by silence, never by sender; keep every source in a session.
        sessions=[]
        for item in rows:
            if not sessions or item[1]['timestamp']-sessions[-1][-1][1]['timestamp']>seconds:sessions.append([])
            sessions[-1].append(item)
        for session in sessions:
            ids=[i for i,_ in session]
            revision=hashlib.sha256(json.dumps(session,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
            payload=envelope(thread['account'],thread['thread_id'],thread['conversation'],[m for _,m in session],int(seconds/60),revision)
            group=payload['groups'][0];group['group']=thread['display_name']
            group['capture_ids']=ids
            # Captures alone cannot prove Chatwoot import completion.
            with engine.store.db() as db:
                receipts=[db.execute("SELECT response FROM effects WHERE id=? AND state='done'",(i,)).fetchone() for i in ids]
            if any(not r or not json.loads(r[0] or '{}').get('id') for r in receipts):continue
            group['chatwoot_message_ids']=[json.loads(r[0])['id'] for r in receipts]
            identity=group['batch_id']
            with engine.store.db() as db:
                db.execute('BEGIN IMMEDIATE')
                if db.execute('SELECT 1 FROM n8n_batch_outbox WHERE id=?',(identity,)).fetchone():continue
                db.execute('INSERT INTO n8n_batch_outbox VALUES(?,?,?,?,?,\'queued\',NULL,?,?)',
                    (identity,thread['account'],thread['thread_id'],revision,json.dumps(payload,ensure_ascii=False),now,now))
                for i in ids:db.execute('INSERT INTO n8n_batch_sources VALUES(?,?)',(i,identity))
    # Transport is at-most-once after submission: timeout requires reconciliation,
    # never automatically replay an AI call of unknown outcome.
    with engine.store.db() as db:
        db.execute('BEGIN IMMEDIATE')
        row=db.execute("SELECT * FROM n8n_batch_outbox WHERE state='queued' ORDER BY created LIMIT 1").fetchone()
        if not row:return
        group=json.loads(row['payload'])['groups'][0]
        blocked=check(engine,row['account'],row['thread_id'],group.get('group',''))
        if blocked:
            if blocked!='policy_unavailable':
                db.execute("UPDATE n8n_batch_outbox SET state='excluded',result=?,updated=? WHERE id=?",(json.dumps({'error':blocked,'action':'Nhóm bỏ qua; không gửi n8n.'}),time.time(),row['id']))
            return
        latest=db.execute("SELECT MAX(CAST(json_extract(payload,'$.timestamp') AS REAL)) FROM captures WHERE account=? AND thread_id=? AND json_extract(payload,'$.origin') IN ('customer','staff')",
                          (row['account'],row['thread_id'])).fetchone()[0]
        cutoff=max(m['timestamp'] for m in group['messages'])
        if latest and latest>cutoff and latest-cutoff<=seconds:
            db.execute("UPDATE n8n_batch_outbox SET state='superseded',updated=? WHERE id=?",(time.time(),row['id']))
            db.execute('DELETE FROM n8n_batch_sources WHERE batch_id=?',(row['id'],))
            return
        db.execute("UPDATE n8n_batch_outbox SET state='submitting',updated=? WHERE id=?",(time.time(),row['id']))
    try:
        with httpx.Client(timeout=120,follow_redirects=False,trust_env=False) as client:
            response=client.post(url,json=json.loads(row['payload']),headers={'Idempotency-Key':row['id']})
            response.raise_for_status()
            result=response.json()
        # ACK is transport receipt, never ERP/file/message completion.
        from hub.n8n_plan_inbox import accept
        if result.get('protocol') == 2:
            from hub.n8n_task_service import receive
            blocked=check(engine,row['account'],row['thread_id'],group.get('group',''))
            if blocked:
                saved={'state':'excluded','reason':blocked,'tasks':[]}
            else:
                saved=receive(engine.store,group,result)
        else:
            saved=accept(engine.store,group,result)
        state=saved['state']
    except Exception as exc:
        state='uncertain';saved={'error':type(exc).__name__,'action':'Đối soát execution n8n theo batch_id trước khi gửi lại; không tự retry.'}
    with engine.store.db() as db:
        db.execute('UPDATE n8n_batch_outbox SET state=?,result=?,updated=? WHERE id=?',
                   (state,json.dumps(saved,ensure_ascii=False),time.time(),row['id']))
