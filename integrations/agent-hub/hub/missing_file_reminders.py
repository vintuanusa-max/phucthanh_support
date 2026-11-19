"""Explicit CANAVI missing-design reminders. No ERP writes or AI calls."""
import hashlib
import json
import time
from hub.source_readiness import readiness

PREFIX = 'missing-file:'
DESTINATION = 'g600695897323562880'
NAME = 'THIẾT KẾ - IN PHÚC THANH'
ACCOUNT = 'zalo-personal-1'

def initialize(store):
 with store.db() as db:
  from hub.source_coverage import initialize as init_coverage
  init_coverage(db)
  db.executescript('''
  CREATE TABLE IF NOT EXISTS missing_file_config(id INTEGER PRIMARY KEY,payload TEXT NOT NULL);
  CREATE TABLE IF NOT EXISTS missing_file_reminders(id TEXT PRIMARY KEY,items TEXT NOT NULL,state TEXT NOT NULL,created REAL NOT NULL,client_id TEXT NOT NULL DEFAULT '',result TEXT NOT NULL DEFAULT '{}');
  CREATE TABLE IF NOT EXISTS missing_file_keys(id TEXT PRIMARY KEY,delivery TEXT NOT NULL);
  ''')

def config(db):
 r=db.execute('SELECT payload FROM missing_file_config WHERE id=1').fetchone()
 return json.loads(r[0]) if r else {}

def candidate(e,db,row,cfg,now):
 p=json.loads(row['payload'])
 if row['created']<cfg['source_since'] or p.get('dispatch_archived_at') or not e.artwork_checks.pet.workflow.current(row['id']):return None
 gate=readiness(db,p)
 if not gate or gate.get('status')!='missing':return None
 # Terminal jobs must never be resurrected by a reminder.
 from hub.dispatch_control import jobs
 js=jobs(db,row['id'])
 if js and js[0]['state'] in ('done','archived','superseded','not_jpg'):return None
 sources=[s for s in p.get('sources',[]) if s.get('assets') or s.get('images')]
 stamps=[float(s.get('timestamp',0)) for s in sources if s.get('timestamp')]
 if not stamps:return None
 received=min(stamps)
 if received<cfg['source_since']:return None
 # Stable per group/model/slip receipt; revisions retain the same source timestamp.
 key=hashlib.sha256(json.dumps([row['account'],row['thread_id'],gate['code'],received]).encode()).hexdigest()
 return {'key':key,'brief_id':row['id'],'code':gate['code'],'account':row['account'],'thread_id':row['thread_id'],'due':received+12*3600}

def slip_rows(e,db,cfg):
 if not db.execute("SELECT 1 FROM sqlite_master WHERE name='production_slip_orders'").fetchone():return []
 out=[]
 for r in db.execute("SELECT id,json_remove(payload,'$.body.image_base64') AS payload FROM production_slip_orders").fetchall():
  body=json.loads(r['payload']).get('body') or {}
  code=body.get('design_code')
  if not isinstance(code,str) or not code.strip():continue
  code=code.strip()
  account=body.get('source_account');thread=body.get('group_id');mid=body.get('source_message_id')
  cap=db.execute('SELECT payload FROM captures WHERE account=? AND thread_id=? AND message_id=? AND revision=0',(account,thread,mid)).fetchone()
  if not cap:continue
  source=json.loads(cap[0]);created=float(source.get('timestamp',0))
  if created<cfg['source_since'] or source.get('recalled'):continue
  parents=db.execute("SELECT id FROM design_briefs WHERE account=? AND thread_id=? AND EXISTS (SELECT 1 FROM json_each(json_extract(design_briefs.payload,'$.sources')) WHERE json_extract(value,'$.message_id')=?)",(account,thread,mid)).fetchall()
  if parents and not any(e.artwork_checks.pet.workflow.current(x['id']) for x in parents):continue
  payload={'account':account,'thread_id':thread,'sources':[source],'brief':{'title':'Phiếu lệnh '+code,'image_context':'production_slip'},'bag_print':{'design_code':code}}
  out.append({'id':'slip:'+r['id'],'account':account,'thread_id':thread,'created':created,'payload':json.dumps(payload)})
 return out

def candidates(e,db,cfg,now):
 out=[];seen=set()
 rows=db.execute('SELECT * FROM design_briefs WHERE created>=? ORDER BY created',(cfg['source_since'],)).fetchall()+slip_rows(e,db,cfg)
 for r in rows:
  item=candidate(e,db,r,cfg,now)
  if item and item['key'] not in seen:out.append(item);seen.add(item['key'])
 return out

def content(items):
 return 'XÁC NHẬN MẪU IN\n\nMẫu:\n'+'\n'.join('- '+i['code'] for i in items)+'\n\nBên em đã nhận phiếu lệnh in của các mẫu trên. Nếu là mẫu cũ, nhờ anh/chị xác nhận dùng lại file đã in trước đó. Nếu là mẫu mới, nhờ anh/chị gửi giúp file thiết kế AI/PDF nhé. Cảm ơn anh/chị!'

def claim(e,account,now=None):
 if account!=ACCOUNT:return None
 now=time.time() if now is None else now
 if now<getattr(e,'_missing_reminder_poll',0):return None
 e._missing_reminder_poll=now+60
 with e.lock,e.store.db() as db:
  db.execute('BEGIN IMMEDIATE')
  cfg=config(db)
  if not cfg.get('enabled'):return None
  items=[i for i in candidates(e,db,cfg,now) if i['due']<=now and not db.execute('SELECT 1 FROM missing_file_keys WHERE id=?',(i['key'],)).fetchone()]
  if not items:return None
  # Keep one source conversation per summary, up to ten models.
  items=[i for i in items if (i['account'],i['thread_id'])==(items[0]['account'],items[0]['thread_id'])][:10]
  key=PREFIX+hashlib.sha256(json.dumps([i['key'] for i in items]).encode()).hexdigest()
  db.execute("INSERT INTO missing_file_reminders(id,items,state,created) VALUES(?,?,'sending',?)",(key,json.dumps(items),now))
  for i in items:db.execute('INSERT INTO missing_file_keys VALUES(?,?)',(i['key'],key))
  return {'id':key,'thread_id':DESTINATION,'display_name':NAME,'message':{'content':content(items)}}

def prepare(e,account,key,client_id):
 if account!=ACCOUNT:raise ValueError('Wrong reminder account')
 with e.lock,e.store.db() as db:
  db.execute('BEGIN IMMEDIATE')
  row=db.execute('SELECT * FROM missing_file_reminders WHERE id=?',(key,)).fetchone();cfg=config(db)
  if not row or row['state']!='sending' or not cfg.get('enabled'):raise ValueError('Reminder unavailable')
  items=json.loads(row['items'])
  eligible={i['key'] for i in candidates(e,db,cfg,time.time())}
  if any(item['key'] not in eligible for item in items):raise ValueError('Source changed; reminder cancelled before send')
  if row['client_id'] and row['client_id']!=client_id:raise ValueError('Client ID already reserved')
  db.execute('UPDATE missing_file_reminders SET client_id=? WHERE id=?',(client_id,key))
 return {'prepared':True}

def result(e,account,key,data):
 if account!=ACCOUNT:raise ValueError('Wrong reminder account')
 with e.store.db() as db:
  row=db.execute('SELECT state FROM missing_file_reminders WHERE id=?',(key,)).fetchone()
  if not row:raise ValueError('Unknown reminder')
  if row['state'] not in ('confirmed','submitted'):
   db.execute('UPDATE missing_file_reminders SET state=?,result=? WHERE id=?',(data['state'],json.dumps(data),key))
 return {'stored':True}
