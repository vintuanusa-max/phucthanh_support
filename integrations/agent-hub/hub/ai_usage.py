"""Best-effort observational telemetry. Never retries business or API work."""
import sqlite3,json,time,uuid,hashlib,logging
from contextlib import closing
from contextvars import ContextVar
from functools import wraps
from inspect import signature
from urllib.parse import unquote
RUN=ContextVar('ai_usage_run',default='')
DATABASE=ContextVar('ai_usage_database',default=None)
PRICE_SOURCE='https://ai.google.dev/gemini-api/docs/pricing'
PRICE_DATE='2026-10-31'
def connect(database):
 c=sqlite3.connect(str(database),timeout=.3);c.row_factory=sqlite3.Row
 c.execute('CREATE TABLE IF NOT EXISTS intake_ai_calls(id TEXT PRIMARY KEY,run_id TEXT,stage TEXT,model TEXT,state TEXT,started REAL,elapsed REAL,input_hash TEXT,usage TEXT,error TEXT)')
 c.execute('CREATE INDEX IF NOT EXISTS intake_ai_calls_run ON intake_ai_calls(run_id)')
 c.execute('CREATE TABLE IF NOT EXISTS intake_ai_coverage(run_id TEXT PRIMARY KEY,started REAL)')
 return c
def write(database,sql,args):
 try:
  with closing(connect(database)) as c:
   with c:c.execute(sql,args)
 except Exception as e:logging.warning('AI usage write failed: %s',type(e).__name__)
def tracked_run(fn):
 sig=signature(fn)
 @wraps(fn)
 def inner(*args,**kwargs):
  b=sig.bind(*args,**kwargs).arguments;run=b.get('run');obj=b.get('self')
  if not run:return fn(*args,**kwargs)
  identity=run['id'];settings=obj.engine.settings
  write(settings.database,'INSERT OR IGNORE INTO intake_ai_coverage VALUES(?,?)',(identity,time.time()))
  token=RUN.set(identity);dbtoken=DATABASE.set(settings.database)
  try:return fn(*args,**kwargs)
  finally:RUN.reset(token);DATABASE.reset(dbtoken)
 return inner

def post(client,settings,stage,url,**kwargs):
 model=unquote(str(url).split('/models/')[-1].split(':')[0]);rid=RUN.get();cid=uuid.uuid4().hex;start=time.time()
 payload=kwargs.get('json',{});digest=hashlib.sha256(json.dumps(payload,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
 write(settings.database,'INSERT INTO intake_ai_calls VALUES(?,?,?,?,?,?,?,?,?,?)',(cid,rid,stage,model,'running',start,0,digest,'{}',''))
 try:
  response=client.post(url,**kwargs)
  try:body=response.json();usage=body.get('usageMetadata',{}) if isinstance(body,dict) else {};model=body.get('modelVersion',model) if isinstance(body,dict) else model
  except Exception:usage={}
  write(settings.database,'UPDATE intake_ai_calls SET model=?,state=?,elapsed=?,usage=?,error=? WHERE id=?',(model,'response' if response.is_success else 'http_error',time.time()-start,json.dumps(usage),'HTTP '+str(response.status_code) if not response.is_success else '',cid))
  return response
 except Exception as exc:
  write(settings.database,'UPDATE intake_ai_calls SET state=?,elapsed=?,error=? WHERE id=?',('transport_error',time.time()-start,type(exc).__name__,cid));raise

def tokens(usage):
 return {'input':usage.get('promptTokenCount'),'output':usage.get('candidatesTokenCount'),'thinking':usage.get('thoughtsTokenCount',0),'cached':usage.get('cachedContentTokenCount',0),'total':usage.get('totalTokenCount')}
def estimate(model,u):
 t=tokens(u)
 if t['input'] is None or t['output'] is None:return None
 # Exact model IDs only; new/preview models are unknown until their price is verified.
 rates={'gemini-2.5-flash':(.30,2.50,.03),'gemini-2.5-flash-lite':(.10,.40,.01),'gemini-2.5-pro':(1.25,10,.125) if t['input']<=200000 else (2.50,15,.25)}
 if model not in rates:return None
 if any(x.get('modality')=='AUDIO' for x in u.get('promptTokensDetails',[])):return None
 a,b,c=rates[model];return round((max(0,t['input']-t['cached'])*a+t['cached']*c+(t['output']+t['thinking'])*b)/1000000,9)
def describe(row):
 r=dict(row);u=json.loads(r.pop('usage') or '{}');r['tokens']=tokens(u);r['estimated_usd']=0 if r['state']=='cache_hit' else estimate(r['model'],u);return r

def overview(database,batches,files,steps):
 result={};
 with closing(sqlite3.connect(str(database))) as c:
  c.row_factory=sqlite3.Row;tables={r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
  for b in batches:
   rows=[];covered=False
   if 'intake_ai_calls' in tables:rows=[describe(r) for r in c.execute('SELECT * FROM intake_ai_calls WHERE run_id=? ORDER BY started',(b['id'],))]
   if 'intake_ai_coverage' in tables:covered=bool(c.execute('SELECT 1 FROM intake_ai_coverage WHERE run_id=?',(b['id'],)).fetchone())
   matched=[f for f in files if f['account']==b['account'] and set(f.get('source_ids',[]))&set(b['source_ids'])]
   jobids={f['id'] for f in matched}|{s['id'] for f in matched for s in steps.get(f['id'],[])}
   if jobids and {'print_api_calls','print_api_context'}<=tables:
    q=','.join('?' for _ in jobids)
    for r in c.execute('SELECT a.*,x.job_id FROM print_api_calls a JOIN print_api_context x ON x.call_id=a.id WHERE x.job_id IN ('+q+') ORDER BY started',tuple(jobids)):
     rr=dict(r);rr['input_hash']=rr.pop('cache_key','');rr['stage']='file:'+rr['stage'];rr['shared_file']=True;rows.append(describe(rr))
   seen={}
   for r in rows:
    k=(r['stage'],r['model'],r.get('input_hash',''));r['same_input_repeat']=r['state']!='cache_hit' and k in seen
    if r['state']!='cache_hit':seen[k]=True
   api=[r for r in rows if r['state']!='cache_hit'];known=[r['estimated_usd'] for r in api if r['estimated_usd'] is not None]
   result[b['id']]={'covered':covered,'calls':len(api),'cache_hits':len(rows)-len(api),'unknown_usage':sum(r['tokens']['input'] is None for r in api),'unknown_cost':len(api)-len(known),'estimated_usd':round(sum(known),9) if known else None,'tokens':{k:sum(r['tokens'][k] or 0 for r in api) for k in ('input','output','thinking','cached')},'rows':rows}
 return {'batches':result,'price_source':PRICE_SOURCE,'price_date':PRICE_DATE,'note':'Ước tính Standard paid-tier; không phải hóa đơn. Chưa gồm phí công cụ/cache storage/miễn phí tài khoản. File liên quan có thể dùng chung nhiều cụm; không cộng chéo. Lượt cũ thiếu dữ liệu không tính là 0.'}

def cache_hit(identity,stage):
 database=DATABASE.get()
 if database is None:return
 write(database,'INSERT INTO intake_ai_calls VALUES(?,?,?,?,?,?,?,?,?,?)',(uuid.uuid4().hex,RUN.get(),stage,'cache','cache_hit',time.time(),0,identity,'{}',''))
