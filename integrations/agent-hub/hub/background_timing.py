"""Bounded CPU timing diagnostics; no message contents, tokens or credentials."""
import functools,json,threading,time
from pathlib import Path
LOCK=threading.Lock()
STATS={}
START=time.time()
def wrap(name,fn):
 @functools.wraps(fn)
 def measured(*args,**kwargs):
  cpu=time.thread_time();wall=time.monotonic()
  try:return fn(*args,**kwargs)
  finally:
   with LOCK:
    stat=STATS.setdefault(name,{'calls':0,'cpu_seconds':0,'wall_seconds':0})
    stat['calls']+=1;stat['cpu_seconds']+=time.thread_time()-cpu;stat['wall_seconds']+=time.monotonic()-wall
 return measured
def install(engine,stop):
 for name in ('order_intake','quality_monitor','leave_monitor','print_approvals','pending_guard'):
  obj=getattr(engine,name,None)
  if obj and hasattr(obj,'poll'):obj.poll=wrap(name+'.poll',obj.poll)
 engine.artwork_checks.discover=wrap('artwork.discover',engine.artwork_checks.discover)
 engine.file_previews.scan=wrap('file_previews.scan',engine.file_previews.scan)
 def save():
  while not stop.wait(15):
   with LOCK:result={'started':START,'updated':time.time(),'functions':dict(STATS)};raw=json.dumps(result)
   Path('/tmp/hub-background-timing.json').write_text(raw)
 threading.Thread(target=save,daemon=True).start()
