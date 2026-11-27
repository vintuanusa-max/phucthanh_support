"""Durable machine ownership. Loss of heartbeat never replays an uncertain job."""
import contextvars
import json
import time
from pathlib import Path

owner = contextvars.ContextVar('print_worker_owner', default=None)
TABLES = {'native-selections':'native_selections', 'jpg-exports':'jpg_exports',
          'pet-exports':'pet_exports', 'psd-samples':'psd_samples',
          'artwork-checks':'artwork_checks'}

def config(store):
    path=Path(store.path).parent/'worker-fleet.json'
    return json.loads(path.read_text()) if path.exists() else {}

def initialize(db):
    db.executescript('''CREATE TABLE IF NOT EXISTS worker_fleet_status(
      worker TEXT PRIMARY KEY, status TEXT NOT NULL, updated REAL NOT NULL);
    CREATE TABLE IF NOT EXISTS worker_fleet_dossiers(
      account TEXT NOT NULL, brief TEXT NOT NULL, worker TEXT NOT NULL,
      created REAL NOT NULL, PRIMARY KEY(account,brief), UNIQUE(worker));
    CREATE TABLE IF NOT EXISTS worker_fleet_jobs(
      account TEXT NOT NULL, lane TEXT NOT NULL, job TEXT NOT NULL,
      worker TEXT NOT NULL, state TEXT NOT NULL, created REAL NOT NULL,
      result TEXT, PRIMARY KEY(account,lane,job));''')
    from hub.fleet_attempts import initialize as init_attempts
    init_attempts(db)
    from hub.fleet_control import initialize as init_control
    init_control(db)

def heartbeat(store, worker, status, protocol=1, progress_info=None, details=None):
    cfg=config(store)
    if worker not in cfg.get('workers',{}):raise ValueError('Unknown worker')
    if status not in ('ready','busy','paused','error'):raise ValueError('Unknown worker status')
    with store.db() as db:
        db.execute('INSERT OR REPLACE INTO worker_fleet_status VALUES(?,?,?)',(worker,status,time.time()))
        from hub import fleet_attempts
        db.execute('INSERT OR REPLACE INTO worker_fleet_protocol VALUES(?,?)',(worker,int(protocol)))
        fleet_attempts.progress(db,worker,progress_info)
        from hub.fleet_control import telemetry,desired
        telemetry(db,worker,details)
        control=desired(db,worker)
    return {'worker':worker,'status':status,'enabled':bool(cfg.get('enabled')),'control':control}

def may_take(db, worker, cfg, now=None, *, need_pet=False):
    now=time.time() if now is None else now
    rank=cfg['workers'][worker]['priority']
    for row in db.execute('SELECT worker,status,updated FROM worker_fleet_status'):
        if row[0]==worker or row[0] not in cfg['workers']:continue
        if need_pet and not cfg['workers'][row[0]].get('pet_exports', True):continue
        from hub.fleet_control import desired
        if not desired(db,row[0])['enabled']:continue
        busy=db.execute("SELECT 1 FROM worker_fleet_jobs WHERE worker=? AND state='claimed'",(row[0],)).fetchone()
        occupied=db.execute('SELECT 1 FROM worker_fleet_dossiers WHERE worker=?',(row[0],)).fetchone()
        if row[1]=='ready' and now-row[2]<90 and not busy and not occupied and cfg['workers'][row[0]]['priority']<rank:
            return False
    return True

def _owner_unavailable(db, owner_worker, dossier_created, now):
    try:
        from hub.fleet_control import desired
        if not desired(db, owner_worker)['enabled']:
            return True
    except Exception:
        pass
    st = db.execute('SELECT status, updated FROM worker_fleet_status WHERE worker=?', (owner_worker,)).fetchone()
    if not st or (now - st[1]) >= 90:
        return True
    if st[0] in ('paused', 'error'):
        return True
    if st[0] != 'busy':
        return False
    tel_state = ''
    try:
        tr = db.execute('SELECT payload FROM worker_fleet_telemetry WHERE worker=?', (owner_worker,)).fetchone()
        if tr and tr[0]:
            tel_state = str((json.loads(tr[0]) or {}).get('state') or '')
    except Exception:
        pass
    if tel_state in ('staff_or_adobe_busy', 'paused', 'paused_by_hub', 'monitor_busy', 'monitor_update_required', 'error'):
        return True
    return tel_state != 'processing' and (now - dossier_created) >= 60

def prune_dossiers(db, live, busy=None, requester=None, now=None):
    now = time.time() if now is None else now
    busy = busy or set()
    for row in db.execute('SELECT account,brief,worker,created FROM worker_fleet_dossiers').fetchall():
        uncertain = db.execute("SELECT 1 FROM worker_fleet_jobs WHERE worker=? AND state='claimed'", (row[2],)).fetchone()
        try:
            in_flight = db.execute("SELECT 1 FROM worker_fleet_attempts WHERE worker=? AND state IN ('running','delivering')", (row[2],)).fetchone()
        except Exception:
            in_flight = None
        if uncertain or in_flight:
            continue
        if (row[0], row[1]) not in live:
            db.execute('DELETE FROM worker_fleet_dossiers WHERE account=? AND brief=?', (row[0], row[1]))
        elif requester is not None and row[2] != requester and (row[0], row[1]) not in busy and _owner_unavailable(db, row[2], row[3], now):
            db.execute('DELETE FROM worker_fleet_dossiers WHERE account=? AND brief=?', (row[0], row[1]))

def claim_dossier(db, account, brief, live, busy):
    ctx=owner.get()
    if ctx is None:return None
    worker,cfg=ctx
    tables={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if not cfg['workers'][worker].get('corel',False):
        if 'artwork_checks' in tables:
            for source in db.execute("SELECT payload FROM artwork_checks WHERE account=? AND brief_id=? AND state='awaiting_upload'",(account,brief)):
                if json.loads(source[0]).get('asset',{}).get('name','').lower().endswith('.cdr'):return False
    has_pet = False
    if 'pet_exports' in tables:
        has_pet = bool(db.execute(
            "SELECT 1 FROM pet_exports WHERE account=? AND json_extract(payload,'$.brief_id')=? AND state IN ('queued','exporting') LIMIT 1",
            (account, brief),
        ).fetchone())
    if has_pet and not cfg['workers'][worker].get('pet_exports', True):
        return False
    # Caller holds BEGIN IMMEDIATE. No expires/reclaim for in-flight operations.
    prune_dossiers(db, live, busy=busy, requester=worker)
    current=db.execute('SELECT worker FROM worker_fleet_dossiers WHERE account=? AND brief=?',(account,brief)).fetchone()
    if current and current[0] != worker and has_pet and not cfg['workers'].get(current[0], {}).get('pet_exports', True):
        uncertain = db.execute("SELECT 1 FROM worker_fleet_jobs WHERE worker=? AND state='claimed'", (current[0],)).fetchone()
        try:
            in_flight = db.execute("SELECT 1 FROM worker_fleet_attempts WHERE worker=? AND state IN ('running','delivering')", (current[0],)).fetchone()
        except Exception:
            in_flight = None
        if not uncertain and not in_flight and (account, brief) not in busy:
            db.execute('DELETE FROM worker_fleet_dossiers WHERE account=? AND brief=?', (account, brief))
            current = None
    if current:return current[0]==worker
    if db.execute('SELECT 1 FROM worker_fleet_dossiers WHERE worker=?',(worker,)).fetchone():return False
    # Adopt an already-running legacy dossier only on the original machine.
    if (account,brief) in busy and worker!=cfg['legacy_worker']:return False
    if not may_take(db,worker,cfg,need_pet=has_pet):return False
    db.execute('INSERT INTO worker_fleet_dossiers VALUES(?,?,?,?)',(account,brief,worker,time.time()))
    return True

def install(app, store, authorize=None):
    from hub.fleet_http import install as setup
    setup(app,store,authorize)
