"""PSD sample-only jobs. Never writes ERP or publishes customer messages."""
import json,re,time,hashlib

def init(e):
 with e.store.db() as d:d.execute("CREATE TABLE IF NOT EXISTS psd_samples(id TEXT PRIMARY KEY,account TEXT,thread_id TEXT,conversation INTEGER,state TEXT,payload TEXT,created REAL)")

def production_request(text):
 text=text.casefold()
 return bool(re.search(r'\b(đặt thêm|in thêm|hàng loạt|sản xuất|đặt hàng)\b',text) or
             (re.search(r'\b(in|đặt|lấy|làm)\b',text) and
              re.search(r'\d+(?:[.,]\d+)?\s*(?:mét|met|tấm|cái|chiếc|bộ|áo)\b',text)
              and not re.search(r'\b(in test|test mẫu|in thử|làm mẫu)\b',text)))

def sample_only(messages):
 text=' '.join(m.get('text','') for m in messages).casefold()
 return bool(re.search(r'\b(in test|test mẫu|in thử|làm mẫu)\b',text)) and not any(production_request(m.get('text','')) for m in messages)

def collect(intake,run,messages):
 if not sample_only(messages):return False
 e=intake.engine;init(e)
 text=' '.join(m.get('text','') for m in messages)
 codes=re.findall(r'\b[a-zA-Z]+\d+[a-zA-Z0-9_-]*\b',text.casefold())
 with e.store.db() as d:
  rows=d.execute("SELECT payload FROM captures WHERE account=? AND thread_id=? AND json_extract(payload,'$.timestamp') BETWEEN ? AND ? ORDER BY rowid DESC LIMIT 80",(run['account'],run['thread_id'],max(m['timestamp'] for m in messages)-21600,max(m['timestamp'] for m in messages))).fetchall()
 candidates={}
 for row in rows:
  m=json.loads(row[0])
  if m.get('recalled') or m.get('revision'):continue
  for a in m.get('assets',[]):
   if a.get('name','').lower().endswith('.psd') and any(re.search(r'(?<![a-z0-9])'+re.escape(code)+r'(?![a-z0-9])',a['name'].casefold()) for code in codes):candidates[a['id']]=a
 # Non-PSD sample requests keep the existing design handling; no arbitrary nearest file.
 # Sample-only requests stay outside ERP even while the PSD is missing.
 identity=hashlib.sha256(('psd-sample:'+run['account']+run['thread_id']+':'.join(m['message_id'] for m in messages)).encode()).hexdigest()
 asset=next(iter(candidates.values())) if len(candidates)==1 else None
 payload={'title':'Lên mẫu — '+(asset['name'] if asset else 'PSD cần chọn nguồn'),'request':text,'messages':[m['message_id'] for m in messages],'asset':asset,'sample_only':True,'policy':'original_psd_size','source_timestamp':max(m['timestamp'] for m in messages),'reason':''}
 state='queued' if asset and asset.get('state')=='ready' else 'waiting_sources'
 if state!='queued':payload['reason']='PSD chưa tải đủ hoặc có nhiều nguồn phù hợp; không xuất nhầm file.'
 with e.store.db() as d:d.execute('INSERT OR IGNORE INTO psd_samples VALUES(?,?,?,?,?,?,?)',(identity,run['account'],run['thread_id'],run['conversation'],state,json.dumps(payload,ensure_ascii=False),time.time()))
 intake.state(run['id'],'ignored',{'intent':'sample_request','reason':'Lên mẫu PSD: chỉ xuất nội bộ, không tạo đơn ERP','sample_job_id':identity})
 return True

def pending(e,account):
 init(e)
 with e.store.db() as d:
  waiting=d.execute("SELECT * FROM psd_samples WHERE account=? AND state='waiting_sources'",(account,)).fetchall()
  for wait in waiting:
   p=json.loads(wait['payload']);codes=re.findall(r'\b[a-zA-Z]+\d+[a-zA-Z0-9_-]*\b',p['request'].casefold());found={}
   since=p.get('source_timestamp',wait['created'])
   for row in d.execute("SELECT payload FROM captures WHERE account=? AND thread_id=? AND json_extract(payload,'$.timestamp') BETWEEN ? AND ? ORDER BY rowid DESC LIMIT 100",(account,wait['thread_id'],since-21600,since+43200)):
    m=json.loads(row[0])
    if m.get('recalled') or m.get('revision'):continue
    for a in m.get('assets',[]):
     if a.get('state')=='ready' and a.get('name','').lower().endswith('.psd') and any(re.search(r'(?<![a-z0-9])'+re.escape(code)+r'(?![a-z0-9])',a['name'].casefold()) for code in codes):found[a['sha256']]=a
   if len(found)==1:
    p['asset']=next(iter(found.values()));p['title']='Lên mẫu — '+p['asset']['name'];p['reason']=''
    d.execute("UPDATE psd_samples SET state='queued',payload=? WHERE id=?",(json.dumps(p,ensure_ascii=False),wait['id']))
  r=d.execute("SELECT * FROM psd_samples WHERE account=? AND state IN ('queued','exporting') ORDER BY created LIMIT 1",(account,)).fetchone()
  if not r:return None
  d.execute("UPDATE psd_samples SET state='exporting' WHERE id=?",(r['id'],))
 return {'id':r['id'],**json.loads(r['payload'])}

def complete(e,account,id,data):
 init(e)
 with e.store.db() as d:r=d.execute('SELECT * FROM psd_samples WHERE account=? AND id=?',(account,id)).fetchone()
 if not r:raise ValueError('Unknown sample')
 if r['state']!='exporting':return {'state':r['state']}
 p=json.loads(r['payload'])
 if data.get('error'):
  p['reason']=str(data['error'])[:1000];state='review'
 else:
  report=data['report'];preview=data['preview']
  if report['source_sha256']!=p['asset']['sha256'] or report['mode']!='CMYK' or report['pixels']!=report['source_pixels'] or report['dpi']!=report['source_dpi']:raise ValueError('PSD size/color mismatch')
  if preview.get('mime_type')!='image/png' or len(preview['data'])>6000000:raise ValueError('Invalid preview')
  p['report']=report
  with e.store.db() as d:d.execute("UPDATE psd_samples SET state='publishing',payload=? WHERE id=?",(json.dumps(p,ensure_ascii=False),id))
  try:
   result=e.effect('psd-preview:'+id,r['conversation'],'message',{'private':True,'message_type':'outgoing','content':p['title']+'\n'+p['request']+'\nJPG CMYK nguyên khổ PSD: '+str(report['size_cm'])+' cm; '+str(report['dpi'])+' DPI.\n'+report['path']+'\nGiữ PSD gốc. Chờ duyệt nội bộ; chưa RIP/gửi khách, không tạo đơn ERP.','_images':[preview]},apply_capture=True)
   p['message_id']=result.get('id');p['reason']='Đã xuất JPG CMYK, chờ duyệt nội bộ';state='done'
  except Exception:
   state='uncertain';p['reason']='Chưa rõ kết quả đăng preview; không tự gửi lại.'
 with e.store.db() as d:d.execute('UPDATE psd_samples SET state=?,payload=? WHERE id=?',(state,json.dumps(p,ensure_ascii=False),id))
 return {'state':state}

def listing(e):
 init(e)
 with e.store.db() as d:rows=d.execute('SELECT * FROM psd_samples ORDER BY created DESC LIMIT 200').fetchall()
 return [{'id':r['id'],'title':json.loads(r['payload'])['title'],'state':r['state'],'reason':json.loads(r['payload']).get('reason',''),'created':r['created'],'kind':'sample','account':r['account']} for r in rows]

def detail(e,id):
 init(e)
 with e.store.db() as d:r=d.execute('SELECT * FROM psd_samples WHERE id=?',(id,)).fetchone()
 if not r:return None
 p=json.loads(r['payload'])
 return {'id':id,'title':p['title'],'sample_only':True,'requirements':[p['request']],'missing':[p.get('reason','')],'assets':[],'images':[],'jobs':[{'id':id,'kind':'Lên mẫu PSD','state':r['state'],'path':p.get('report',{}).get('path',''),'reason':p.get('reason','')}],'current':False,'source_checks':[],'print_catalogs':[],'native':{},'management':{}}
