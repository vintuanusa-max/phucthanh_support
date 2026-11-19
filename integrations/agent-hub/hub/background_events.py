"""Run unchanged business pollers only after source changes or known deadlines."""
import time

WATCH={
 'intake':('captures','jobs','intake_runs','intake_sources','intake_operator_retry','intake_run_now','order_additions','intake_management','intake_policy','threads','agent_proposals','execution_models'),
 'approval':('captures','print_approvals','print_deliveries','print_change_sources','agent_approval_handoffs','intake_policy','threads','order_additions'),
}

def initialize(store):
 with store.db() as db:
  db.execute('CREATE TABLE IF NOT EXISTS background_work_events(name TEXT PRIMARY KEY,generation INTEGER NOT NULL,due REAL)')
  tables={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
  for name,watched in WATCH.items():
   db.execute('INSERT OR IGNORE INTO background_work_events VALUES(?,1,?)',(name,time.time()))
   for table in watched:
    if table not in tables:continue
    columns=[r[1] for r in db.execute('PRAGMA table_info('+table+')')]
    for action in ('INSERT','UPDATE','DELETE'):
     guard=' WHEN '+' OR '.join('NEW."'+c+'" IS NOT OLD."'+c+'"' for c in columns) if action=='UPDATE' else ''
     db.execute(f'''CREATE TRIGGER IF NOT EXISTS bg_event_{name}_{table}_{action.lower()} AFTER {action} ON {table}{guard} BEGIN
      UPDATE background_work_events SET generation=generation+1,due=CAST(strftime('%s','now') AS REAL) WHERE name='{name}'; END''')

def deadline(engine,name,now):
 seconds=float(engine.intake_management.seconds()) if name=='intake' else 120
 times=[]
 with engine.store.db() as db:
  # Only recent timestamps are read, once per event, not the complete conversation.
  latest=db.execute("SELECT max(CAST(json_extract(payload,'$.timestamp') AS REAL)) FROM captures WHERE CAST(json_extract(payload,'$.timestamp') AS REAL)>? GROUP BY account,thread_id",(now-seconds,)).fetchall()
  for row in latest:
   for delay in ((seconds,) if name=='intake' else (30,120)):
    if row[0]+delay>now:times.append(row[0]+delay)
  if name=='intake':
   # Ready evidence must not depend on new chat traffic to wake submission.
   ready=db.execute("SELECT DISTINCT account FROM intake_runs WHERE state='evidence_ready'").fetchall()
   if any(engine.intake_management.enabled(row[0]) for row in ready):times.append(now+30)
   for row in db.execute("SELECT COALESCE(json_extract(payload,'$.last_timestamp'),json_extract(payload,'$.first_timestamp'),created) FROM intake_runs WHERE state='waiting_details'"):
    if row[0]+seconds>now:times.append(row[0]+seconds)
 return min(times) if times else None

def gated(engine,name,fn):
 def run():
  now=time.time()
  with engine.store.db() as db:
   row=db.execute('SELECT generation,due FROM background_work_events WHERE name=?',(name,)).fetchone()
  if row is None or row['due'] is None or row['due']>now:return False
  try:
   worked=fn()
   due=time.time()+1 if worked else deadline(engine,name,time.time())
  except Exception:
   with engine.store.db() as db:db.execute('UPDATE background_work_events SET due=? WHERE name=? AND generation=?',(time.time()+30,name,row['generation']))
   raise
  with engine.store.db() as db:
   # Never consume a concurrent event or a state transition made by the poller itself.
   db.execute('UPDATE background_work_events SET due=? WHERE name=? AND generation=?',(due,name,row['generation']))
  return worked
 return run

def install(engine):
 initialize(engine.store)
 engine.order_intake.poll=gated(engine,'intake',engine.order_intake.poll)
 engine.print_approvals.poll=gated(engine,'approval',engine.print_approvals.poll)
