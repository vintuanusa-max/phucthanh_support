"""Forward new internal Zalo notices through existing bot101 API, at most once."""
import json,time
from pathlib import Path
import httpx

def config(store):
 p=Path(store.path).parent/'bot101-forward.json'
 return json.loads(p.read_text()) if p.exists() else {}

def record_status(store,state,detail,request_id=''):
 with store.db() as db:
  db.execute('CREATE TABLE IF NOT EXISTS bot101_runtime(id INTEGER PRIMARY KEY,state TEXT,detail TEXT,request_id TEXT,updated REAL)')
  db.execute('INSERT OR REPLACE INTO bot101_runtime VALUES(1,?,?,?,?)',(state,detail,request_id,time.time()))

def owner(store,account):
 c=config(store)
 return 'bot101' if c.get('enabled') is True and c.get('destination_account')==account else 'local'

def tick(engine):
 c=config(engine.store)
 if c.get('enabled') is not True:return
 if c.get('destination_account')!='zalo-personal-1' or c.get('thread_id')!='g3307527274697028144':raise ValueError('UNEXPECTED_INTERNAL_DESTINATION')
 boundary=c.get('enabled_after',0)
 if not isinstance(boundary,(float,int)) or boundary<=0:raise ValueError('ACTIVATION_BOUNDARY_REQUIRED')
 route=engine.print_approvals.route()
 if not route:return
 # No network activity until an actual notification has been durably claimed.
 job=engine.print_approvals.claim(route['account'],c['destination_account'],owner='bot101',min_created=boundary)
 if not job:return
 with httpx.Client(timeout=10,trust_env=False) as client:
  # Claim is durable in print_deliveries BEFORE POST. Never automatically POST again.
  result={'state':'uncertain'}
  try:
   if job['thread_id']!=c['thread_id']:raise ValueError('DESTINATION_CHANGED')
   message=job['caption']
   evidence=job.get('evidence') or {}
   if evidence.get('directory'):message+='\nẢnh/bằng chứng tổng hợp trên NAS: '+str(evidence['directory'])
   else:message+='\nẢnh mẫu: đối chiếu tại hội thoại nguồn và hồ sơ nêu trên.'
   response=client.post('http://192.168.1.101:8000/api/send-zalo',json={'customer_name':'File In - Giấy In - Màng Pet','message':message,'request_id':'hub-print-'+job['id']})
   response.raise_for_status()
   receipt=response.json()
   state=receipt.get('state') or receipt.get('status')
   result={'state':{'queued':'submitted','submitted':'submitted','confirmed':'confirmed','skipped':'blocked','blocked':'blocked','failed':'blocked'}.get(state,'uncertain'),'client_id':receipt.get('delivery_id') or 'zalo:hub-print-'+job['id']}
   # Queue acceptance is not confirmation of delivery; never resend uncertain results.
   record_status(engine.store,result['state'],'API máy 101 đã nhận phản hồi; '+str(state),'hub-print-'+job['id'])
  except Exception as exc:
   record_status(engine.store,'error',type(exc).__name__+': Không xác nhận được kết quả gửi; không tự gửi lại.','hub-print-'+job['id'])
   raise
  finally:
   engine.print_approvals.delivered(route['account'],job['id'],result)
