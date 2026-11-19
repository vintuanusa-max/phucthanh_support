"""Durable source-change notifications and exact quiet-window deadlines."""
import json,time

def initialize(store,accounts):
 with store.db() as db:
  db.execute('CREATE TABLE IF NOT EXISTS source_work_events(account TEXT PRIMARY KEY,generation INTEGER NOT NULL,due REAL,reason TEXT)')
  tables={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
  for table in ('captures','design_briefs'):
   if table not in tables:continue
   for action in ('INSERT','UPDATE'):
    guard=' WHEN NEW.payload IS NOT OLD.payload' if action=='UPDATE' else ''
    db.execute(f'''CREATE TRIGGER IF NOT EXISTS source_event_{table}_{action.lower()}
     AFTER {action} ON {table}{guard} BEGIN
      INSERT INTO source_work_events VALUES(NEW.account,1,CAST(strftime('%s','now') AS REAL),'source_changed')
      ON CONFLICT(account) DO UPDATE SET generation=generation+1,due=excluded.due,reason=excluded.reason;
     END''')
  if 'print_settings' in tables:
   for action in ('INSERT','UPDATE','DELETE'):
    db.execute(f'''CREATE TRIGGER IF NOT EXISTS source_event_settings_{action.lower()} AFTER {action} ON print_settings BEGIN
      UPDATE source_work_events SET generation=generation+1,due=CAST(strftime('%s','now') AS REAL),reason='settings_changed'; END''')
  # One reconciliation at first installation only; restart does not reset the timer.
  for account in accounts:
   db.execute('INSERT OR IGNORE INTO source_work_events VALUES(?,1,?,?)',(account,time.time(),'initial_pending_reconciliation'))

def due_events(store,accounts,now=None):
 now=time.time() if now is None else now
 if not accounts:return []
 with store.db() as db:
  return [dict(r) for r in db.execute('SELECT * FROM source_work_events WHERE due<=? AND account IN ('+','.join('?' for _ in accounts)+') ORDER BY due',(now,*accounts))]

def next_deadline(engine,account,now=None):
 """Calculate once after a change/run; no scanning while the source is unchanged."""
 from hub.source_readiness import collection_window
 from hub.group_original_jpg import enabled
 from hub.file_previews import view_request
 now=time.time() if now is None else now
 deadlines=[]
 with engine.store.db() as db:
  minutes=15
  row=db.execute('SELECT payload FROM print_settings ORDER BY id DESC LIMIT 1').fetchone()
  if row:minutes=json.loads(row[0]).get('source_wait_minutes',15)
  # Same bounded set the existing discovery function considers.
  for row in db.execute('SELECT payload FROM design_briefs WHERE account=? ORDER BY created DESC LIMIT 300',(account,)).fetchall():
   payload=json.loads(row[0]);window=collection_window(db,payload,now=now)
   if window['waiting']:deadlines.append(window['ready_at'])
  # Direct-file groups may not have a brief yet; file preview requests wait 60 seconds.
  rows=db.execute("SELECT payload FROM captures WHERE account=? AND json_extract(payload,'$.timestamp')>?",(account,now-max(float(minutes)*60,60))).fetchall()
  direct_deadlines={}
  for row in rows:
   m=json.loads(row[0])
   if m.get('revision') or m.get('recalled'):continue
   stamp=float(m.get('timestamp',0))
   if enabled(m.get('thread_id')) and m.get('origin') not in ('legacy_bot','erp') and m.get('role')!='bot':
    if stamp+minutes*60>now:direct_deadlines[m['thread_id']]=max(direct_deadlines.get(m['thread_id'],0),stamp+minutes*60)
   if view_request(m.get('text','')) and stamp+60>now:deadlines.append(stamp+60)
  deadlines.extend(direct_deadlines.values())
 return min(deadlines) if deadlines else None

def finish(store,event,deadline,reason='waiting_change_or_deadline'):
 with store.db() as db:
  # A capture arriving during discovery must not be acknowledged or overwritten.
  return db.execute('UPDATE source_work_events SET due=?,reason=? WHERE account=? AND generation=?',
    (deadline,reason,event['account'],event['generation'])).rowcount
