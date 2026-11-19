"""Hub waits for queued work; Windows holds one request instead of polling every lane."""
import threading,time,logging

QUEUES={
 'psd_samples':('queued','exporting'),
 'native_selections':('scan_queued','render_queued','scan_running','render_running'),
 'file_previews':('queued',),'jpg_exports':('queued','exporting'),
 'erp_print_approvals':('queued',),'pet_exports':('queued','exporting'),
 'artwork_checks':('awaiting_upload',),
}

def ready_accounts(store,accounts):
 ready=[]
 with store.db() as db:
  tables={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
  for account in accounts:
   for table,states in QUEUES.items():
    if table not in tables:continue
    sql='SELECT 1 FROM '+table+' WHERE account=? AND state IN ('+','.join('?' for _ in states)+') LIMIT 1'
    if db.execute(sql,(account,*states)).fetchone():ready.append(account);break
 return ready

class Dispatcher:
 def __init__(self,engine,stop):
  self.engine=engine;self.stop=stop
  from hub.source_events import initialize
  initialize(engine.store,[a for a,c in engine.settings.inboxes.items() if c.get('capture_enabled')])
 def discover(self,accounts):
  from hub.source_events import due_events,next_deadline,finish
  for event in due_events(self.engine.store,accounts):
   account=event['account']
   try:
    self.engine.artwork_checks.discover(account)
    self.engine.file_previews.scan(account)
    from hub.psd_samples import refresh_sources
    refresh_sources(self.engine,account)
    finish(self.engine.store,event,next_deadline(self.engine,account))
   except Exception:
    logging.getLogger(__name__).exception('Worker source discovery failed for %s',account)
    finish(self.engine.store,event,time.time()+60,'discovery_error_retry')
 def wait(self,accounts):
  deadline=time.monotonic()+50
  while not self.stop.is_set():
   ready=ready_accounts(self.engine.store,accounts)
   if ready:return {'accounts':ready}
   if time.monotonic()>=deadline:return {'accounts':[]}
   self.stop.wait(2)
  return {'accounts':[]}
