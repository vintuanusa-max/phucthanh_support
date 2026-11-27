"""Opt-in final-output copy. No old-job scan, no export or ERP side effects."""
import json,time,hashlib,re
from pathlib import PurePosixPath

def init(store):
 with store.db() as d:
  d.execute('CREATE TABLE IF NOT EXISTS llm_copy_config(id INTEGER PRIMARY KEY, revision INTEGER, enabled INTEGER)')
  d.execute('INSERT OR IGNORE INTO llm_copy_config VALUES(1,0,0)')
  d.execute('CREATE TABLE IF NOT EXISTS llm_copy_audit(revision INTEGER PRIMARY KEY,created REAL,payload TEXT)')
  d.execute('CREATE TABLE IF NOT EXISTS llm_copy_jobs(id TEXT PRIMARY KEY,account TEXT,state TEXT,payload TEXT,created REAL)')

def config(d):
 r=d.execute('SELECT revision,enabled FROM llm_copy_config WHERE id=1').fetchone()
 return dict(revision=r[0],enabled=bool(r[1]))

def update(store,v):
 if set(v)!={'kind','revision','enabled','actor'} or type(v['revision']) is not int or type(v['enabled']) is not bool or not isinstance(v['actor'],str):raise ValueError('Invalid LLM copy setting')
 with store.db() as d:
  old=config(d)
  if old['revision']!=v['revision']:raise ValueError('Cấu hình đã đổi; tải lại')
  n=old['revision']+1
  d.execute('UPDATE llm_copy_config SET revision=?,enabled=? WHERE id=1',(n,int(v['enabled'])))
  d.execute('INSERT INTO llm_copy_audit VALUES(?,?,?)',(n,time.time(),json.dumps(dict(actor=v['actor'],before=old['enabled'],after=v['enabled']))))
  if not v['enabled']:d.execute("UPDATE llm_copy_jobs SET state='cancelled' WHERE state='queued'")

def files_for(kind,p):
 if kind=='psd_samples':
  group=p['asset']['relative_path'].replace('\\','/').split('/')[0]
  entries=[]
  for f in p['report'].get('panels',[p['report']]):
   path=f['path'].replace('\\','/');marker='/'+group+'/DESIGNER/'
   if marker not in path:raise ValueError('PSD output outside customer DESIGNER')
   entries.append((group+'/DESIGNER/'+path.split(marker,1)[1],f['sha256']))
 else:
  archive=p['archive_relative'].replace('\\','/');group=archive.split('/')[0]
  entries=[(archive+'/'+f['file'],f['sha256']) for f in p['report']['panels']] if kind=='jpg_exports' else [(archive+'/'+f['name'],f['sha256']) for f in p['reports']]
 def out_entries():
  out=[]
  used_names=set()
  thread_id=p.get('thread_id') or (p.get('source') or {}).get('thread_id') or ''
  source_name=((p.get('asset') or (p.get('source') or {}).get('asset') or {}).get('name')) or ''
  from hub.output_names import llm_copy_filename
  for source,sha in entries:
   path=PurePosixPath(source)
   if path.is_absolute() or '..' in path.parts or len(path.parts)<3 or path.parts[0]!=group or path.parts[1]!='DESIGNER' or ':' in source or '\\' in source:raise ValueError('Invalid DESIGNER source')
   if path.suffix.lower() not in ('.jpg','.jpeg','.tif','.tiff'):raise ValueError('Not final JPG/TIFF')
   if not re.fullmatch('[a-f0-9]{64}',sha):raise ValueError('Invalid output checksum')
   name=llm_copy_filename(path.stem,path.suffix,group=group,thread_id=thread_id,source_name=source_name)
   if name.lower() in used_names:
    base=PurePosixPath(name)
    idx=2
    while f'{base.stem[:-4]}_{idx}_LLM{base.suffix}'.lower() in used_names:idx+=1
    name=f'{base.stem[:-4]}_{idx}_LLM{base.suffix}'
   used_names.add(name.lower())
   out.append(dict(group=group,name=name,source=source,sha256=sha))
  return out
 out=out_entries()
 if not out:raise ValueError('No final outputs')
 return out

def enqueue(d,kind,id,p):
 # Called inside export completion transaction; completed jobs can never replay.
 if p.get('brief_id'):
  b=d.execute('SELECT payload FROM design_briefs WHERE id=?',(p['brief_id'],)).fetchone()
  if b and json.loads(b[0]).get('internal_only'):return
 if not d.execute("SELECT 1 FROM sqlite_master WHERE name='llm_copy_config'").fetchone():return
 row=d.execute('SELECT account,state FROM '+kind+' WHERE id=?',(id,)).fetchone()
 if not row or row['state']=='done' or not config(d)['enabled']:return
 identity=hashlib.sha256((kind+':'+id).encode()).hexdigest()
 payload=dict(export_kind=kind,export_id=id,name=p.get('plan',{}).get('order_code') or p.get('title',id))
 try:payload['files']=files_for(kind,p);state='queued'
 except (KeyError,ValueError,TypeError) as exc:payload['error']=str(exc);state='review'
 d.execute('INSERT OR IGNORE INTO llm_copy_jobs VALUES(?,?,?,?,?)',(identity,row['account'],state,json.dumps(payload,ensure_ascii=False),time.time()))

def install(app,e,guard):
 from fastapi import Depends,HTTPException
 init(e.store)
 @app.get('/adapters/{account}/llm-copies',dependencies=[Depends(guard)])
 def pending(account:str):
  with e.store.db() as d:
   if not config(d)['enabled']:return {'job':None}
   r=d.execute("SELECT * FROM llm_copy_jobs WHERE account=? AND state IN ('queued','copying') ORDER BY created LIMIT 1",(account,)).fetchone()
   if not r:return {'job':None}
   d.execute("UPDATE llm_copy_jobs SET state='copying' WHERE id=?",(r['id'],))
   return {'job':dict(id=r['id'],**json.loads(r['payload']))}
 @app.post('/adapters/{account}/llm-copies/{id}',dependencies=[Depends(guard)])
 def complete(account:str,id:str,data:dict):
  with e.store.db() as d:
   r=d.execute('SELECT * FROM llm_copy_jobs WHERE id=? AND account=?',(id,account)).fetchone()
   if not r:raise HTTPException(404)
   if r['state']!='copying':return {'state':r['state']}
   p=json.loads(r['payload']);expected=[f['group']+'/'+f['name'] for f in p['files']]
   if not data.get('error') and not valid_paths(p['files'],data.get('paths')):raise HTTPException(422,'Wrong copy receipt')
   state='review' if data.get('error') else 'done';p['result']=data;p['finished']=time.time()
   d.execute('UPDATE llm_copy_jobs SET state=?,payload=? WHERE id=?',(state,json.dumps(p,ensure_ascii=False),id))
   return {'state':state}


def valid_paths(files,paths):
 if not isinstance(paths,list) or len(files)!=len(paths):return False
 for f,path in zip(files,paths):
  base=PurePosixPath(f['name'])
  pattern=re.escape(f['group']+'/'+base.stem)+r'(?:[2-9][0-9]*|1[0-9]+)?'+re.escape(base.suffix)
  if not isinstance(path,str) or not re.fullmatch(pattern,path):return False
 return True
