"""Bounded, fenced failover for file work only. Never replays final publishing."""
import hashlib
import json
import time
import uuid

TABLES={'native-selections':'native_selections','jpg-exports':'jpg_exports',
        'pet-exports':'pet_exports','psd-samples':'psd_samples','artwork-checks':'artwork_checks'}
RUNNING={'native-selections':('scan_running','render_running'), 'jpg-exports':('exporting',),
         'pet-exports':('exporting',), 'psd-samples':('exporting',), 'artwork-checks':('awaiting_upload',)}

def initialize(db):
    db.executescript('''CREATE TABLE IF NOT EXISTS worker_fleet_attempts(
      id TEXT PRIMARY KEY, account TEXT NOT NULL, lane TEXT NOT NULL, job TEXT NOT NULL,
      worker TEXT NOT NULL, brief TEXT NOT NULL, payload TEXT NOT NULL, state TEXT NOT NULL,
      ordinal INTEGER NOT NULL, created REAL NOT NULL, progress REAL NOT NULL,
      signature TEXT NOT NULL, budget REAL NOT NULL, reason TEXT NOT NULL DEFAULT '',
      UNIQUE(account,lane,job,ordinal));
    CREATE INDEX IF NOT EXISTS fleet_attempt_worker ON worker_fleet_attempts(worker,state);
    CREATE TABLE IF NOT EXISTS worker_fleet_protocol(worker TEXT PRIMARY KEY,version INTEGER NOT NULL);''')

def budget(lane,payload):
    # Adobe calls already allow 360-600 seconds per file, sometimes two passes.
    count=max(1,len(payload.get('files',[])),len(payload.get('editable_faces',[])))
    base={'artwork-checks':1200,'native-selections':1500,'jpg-exports':1800,
          'pet-exports':max(1200,count*420+180),'psd-samples':2400}[lane]
    return min(7200,base)

def brief(payload,lane):
    return payload.get('brief_id') or ('psd:'+payload['id'] if lane=='psd-samples' else '')

def decorate(row):
    payload=json.loads(row['payload'])
    payload['fleet_attempt']={'id':row['id'],'worker':row['worker'],'ordinal':row['ordinal'],
                              'output_suffix':'worker-results/'+row['worker']}
    return payload

def create(db,account,lane,payload,worker,ordinal=1,now=None):
    now=time.time() if now is None else now
    aid=uuid.uuid4().hex
    db.execute('INSERT INTO worker_fleet_attempts VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
       (aid,account,lane,payload['id'],worker,brief(payload,lane),json.dumps(payload),
        'running',ordinal,now,now,'',budget(lane,payload),''))
    return db.execute('SELECT * FROM worker_fleet_attempts WHERE id=?',(aid,)).fetchone()

def current(db,account,lane,job):
    return db.execute('SELECT * FROM worker_fleet_attempts WHERE account=? AND lane=? AND job=? ORDER BY ordinal DESC LIMIT 1',
                      (account,lane,job)).fetchone()

def canonical_state(db,row):
    found=db.execute('SELECT state FROM '+TABLES[row['lane']]+' WHERE account=? AND id=?',
                     (row['account'],row['job'])).fetchone()
    return found[0] if found else None

def eligible(db,row,now=None):
    now=time.time() if now is None else now
    if row['ordinal']>=2 or row['state'] not in ('running','retry_pending'):return False
    # A receipt/publishing state is stronger evidence than stale heartbeat.
    if canonical_state(db,row) not in RUNNING[row['lane']]:return False
    if row['state']=='retry_pending':return True
    hb=db.execute('SELECT updated FROM worker_fleet_status WHERE worker=?',(row['worker'],)).fetchone()
    last=max(row['created'],hb[0] if hb else 0)
    return now-last>=120 or now-row['progress']>=row['budget'] or now-row['created']>=row['budget']*2

def failover(db,account,lane,worker,cfg,now=None):
    if not cfg.get('failover_enabled'):return None
    now=time.time() if now is None else now
    if db.execute("SELECT 1 FROM worker_fleet_attempts WHERE worker=? AND state IN ('running','delivering')",(worker,)).fetchone():return None
    # Do not abandon another dossier already owned by the available machine.
    if db.execute('SELECT 1 FROM worker_fleet_dossiers WHERE worker=?',(worker,)).fetchone():return None
    rows=db.execute("SELECT * FROM worker_fleet_attempts WHERE account=? AND lane=? AND worker!=? AND state IN ('running','retry_pending') ORDER BY created",(account,lane,worker)).fetchall()
    for old in rows:
        if not eligible(db,old,now):continue
        payload=json.loads(old['payload'])
        asset=payload.get('asset',payload.get('source',{}).get('asset',{}))
        if asset.get('name','').lower().endswith('.cdr') and not cfg['workers'][worker].get('corel'):continue
        db.execute("UPDATE worker_fleet_attempts SET state='superseded',reason='Transferred to backup worker' WHERE id=?",(old['id'],))
        new=create(db,account,lane,payload,worker,2,now)
        db.execute("UPDATE worker_fleet_jobs SET worker=?,state='claimed',created=?,result=NULL WHERE account=? AND lane=? AND job=?",
                   (worker,now,account,lane,old['job']))
        db.execute('UPDATE worker_fleet_dossiers SET worker=?,created=? WHERE account=? AND brief=?',
                   (worker,now,account,old['brief']))
        return new
    return None

def progress(db,worker,info,now=None):
    if not isinstance(info,dict):return
    row=db.execute("SELECT * FROM worker_fleet_attempts WHERE id=? AND worker=? AND state='running'",(str(info.get('attempt','')),worker)).fetchone()
    if not row:return
    sig=str(info.get('signature',''))[:100]
    if sig and sig!=row['signature']:
        db.execute('UPDATE worker_fleet_attempts SET signature=?,progress=? WHERE id=?',(sig,time.time() if now is None else now,row['id']))

def technical_error(data):
    message=str(data.get('error','')).lower()
    return bool(message) and any(s in message for s in ('timeout','timeoutexpired','quá thời gian','operationalerror',
       'connectionerror','filenotfounderror','com_error','rpc_e','rpc server','ứng dụng đang bận','photoshop chưa hoàn tất','illustrator chưa hoàn tất'))

def output_relative(payload,lane,worker):
    # Use the existing renderer's naming rules, only append an isolated folder.
    if lane=='jpg-exports':base=payload['archive_relative']
    elif lane=='pet-exports':
        from hub.pet_render import designer_folder_name
        version=payload.get('source',{}).get('editable_version_id') or payload['id']
        base=payload['archive_folder']+'/DESIGNER/'+designer_folder_name(payload.get('archive_model') or payload['plan']['order_code'])+'/versions/'+version
    else:return None
    return base.rstrip('/')+'/worker-results/'+worker

def recover_delivery(db,attempt_id=None):
    tables={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    for row in db.execute("SELECT * FROM worker_fleet_attempts WHERE state='delivering'"+(' AND id=?' if attempt_id else ''),
                          (attempt_id,) if attempt_id else ()).fetchall():
        if TABLES[row['lane']] not in tables:continue
        state=canonical_state(db,row)
        if state in RUNNING[row['lane']]:
            # Business handler has not committed publishing; resend only its result.
            db.execute("UPDATE worker_fleet_attempts SET state='running',reason='Hub restarted: awaiting saved result' WHERE id=?",(row['id'],))
        else:
            result=json.dumps({'state':state or 'uncertain','reason':'Recovered persisted business state; no re-export'})
            db.execute("UPDATE worker_fleet_attempts SET state='completed' WHERE id=?",(row['id'],))
            db.execute("UPDATE worker_fleet_jobs SET state='completed',result=? WHERE account=? AND lane=? AND job=?",(result,row['account'],row['lane'],row['job']))
