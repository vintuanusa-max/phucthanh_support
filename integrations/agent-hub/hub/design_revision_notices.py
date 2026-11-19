"""Source-bound design revision notices, independent of ERP and bot101 code."""
import hashlib,json,time
from pathlib import PurePosixPath,PureWindowsPath
from datetime import datetime,timezone,timedelta
import httpx
from hub.bot101_forward import config,record_status

GUIDANCE='''\nYêu cầu khách chỉnh mẫu đã có (thu nhỏ/phóng lớn/đổi chữ/màu/vị trí) dùng submit_design_revision với request_message_ids chỉ tin khách yêu cầu, image_message_ids đúng ảnh mẫu trong batch, customer_quote nguyên văn toàn tin, change_spec tóm tắt không suy thêm thông số. Không cần order_id/target_file. Đây là gửi công việc nội bộ File In qua máy101, không chỉnh file tự động và không phải duyệt in. Có đặt hàng thì propose_order_draft riêng, không để chỉnh mẫu chặn đơn. Không rõ ảnh nào: escalate_to_human; không lấy ảnh gần nhất. Một yêu cầu có nhiều ảnh cần giữ đủ. Không tự gán 10cm là ngang/cao nếu khách chưa nói. Không dùng ảnh nhân viên cho chỉnh mẫu nếu khách chưa chỉ rõ đó là mẫu cần sửa.\n'''

def initialize(store):
 with store.db() as db:
  db.execute('CREATE TABLE IF NOT EXISTS design_revision_policy(id INTEGER PRIMARY KEY,enabled_after REAL NOT NULL)')
  db.execute('INSERT OR IGNORE INTO design_revision_policy VALUES(1,?)',(time.time(),))
  db.execute('CREATE TABLE IF NOT EXISTS design_revision_notices(id TEXT PRIMARY KEY,run_id TEXT NOT NULL,account TEXT NOT NULL,thread_id TEXT NOT NULL,payload TEXT NOT NULL,state TEXT NOT NULL,result TEXT NOT NULL,created REAL NOT NULL,updated REAL NOT NULL)')


def validate(args,context):
 req=args.get('request_message_ids');imgs=args.get('image_message_ids')
 if not isinstance(req,list) or not 1<=len(req)<=10 or not isinstance(imgs,list) or not 1<=len(imgs)<=10:raise ValueError('Cần chỉ rõ tin yêu cầu và ảnh mẫu cần sửa')
 if any(not isinstance(x,str) for x in req+imgs):raise ValueError('ID nguồn không hợp lệ')
 batch={m['message_id']:m for m in context['batch']}
 if not set(req+imgs)<=batch.keys():raise ValueError('Nguồn chỉnh mẫu phải thuộc cụm đã gom, không đoán ảnh lịch sử')
 if any(batch[i].get('role')!='customer' for i in req):raise ValueError('Chưa có yêu cầu chỉnh mẫu từ khách')
 if args.get('customer_quote') not in [batch[i].get('text') for i in req] or not str(args.get('customer_quote','')).strip():raise ValueError('Câu khách yêu cầu không khớp nguyên văn')
 if any(not batch[i].get('has_image') for i in imgs):raise ValueError('Tin ảnh mẫu chưa có ảnh')
 if not isinstance(args.get('change_spec'),str) or not 1<=len(args['change_spec'].strip())<=2000:raise ValueError('Thiếu nội dung chỉnh mẫu')
 return sorted(set(req)),sorted(set(imgs))


def stage(agent,run,args,context):
 req,imgs=validate(args,context)
 initialize(agent.store)
 with agent.store.db() as db:
  cutoff=db.execute('SELECT enabled_after FROM design_revision_policy WHERE id=1').fetchone()[0]
  sources={}
  for mid in set(req+imgs):
   row=db.execute('SELECT payload FROM captures WHERE account=? AND thread_id=? AND message_id=? ORDER BY revision DESC LIMIT 1',(run['account'],run['thread_id'],mid)).fetchone()
   if not row:raise ValueError('Không có nguồn đúng nhóm')
   m=json.loads(row[0])
   if m.get('recalled') or m.get('revision'):raise ValueError('Nguồn bị thu hồi/chỉnh sửa; kiểm tra lại')
   sources[mid]=m
 if max(sources[i]['timestamp'] for i in req)<cutoff:return {'state':'revision_review','reason':'Nguồn trước thời điểm bật; không gửi lại thông báo cũ'}
 # Independent semantic verification checks image correspondence and requested edits.
 from hub.agent_loop import verify_action
 verify_action(agent.e.settings,context,'submit_design_revision',args)
 root=agent.e.settings.inboxes[run['account']].get('archive_root','').rstrip('\\/')
 if not root:raise ValueError('Chưa cấu hình thư mục NAS ảnh nguồn')
 links=[];proofs=[]
 for mid in imgs:
  m=sources[mid];assets=[a for a in m.get('assets',[]) if a.get('kind')=='image' and a.get('state')=='ready']
  if not m.get('images') or not assets:raise ValueError('Ảnh mẫu chưa có file NAS; giữ kiểm tra, không gửi thiếu ảnh')
  for a in assets:
   rel=PurePosixPath(a.get('relative_path',''))
   if not a.get('relative_path') or rel.is_absolute() or '..' in rel.parts or ':' in str(rel) or not a.get('sha256'):raise ValueError('Đường dẫn/bằng chứng ảnh không hợp lệ')
   path=str(PureWindowsPath(root,*rel.parts));links.append(path);proofs.append({'message_id':mid,'path':path,'sha256':a['sha256'],'image_ids':m['images']})
 identity=hashlib.sha256(json.dumps([run['account'],run['thread_id'],req],ensure_ascii=False).encode()).hexdigest()
 stamp=datetime.fromtimestamp(max(sources[i]['timestamp'] for i in req),timezone(timedelta(hours=7))).strftime('%H:%M %d/%m/%Y')
 caption='YÊU CẦU CHỈNH MẪU — '+sources[req[0]].get('display_name',run['thread_id'])+'\nKhách nhắn '+stamp+': '+args['customer_quote']+'\nNội dung cần chỉnh: '+args['change_spec']+'\nẢnh mẫu đúng yêu cầu (NAS):\n'+'\n'.join(dict.fromkeys(links))+'\nHội thoại Chatwoot #'+str(run['conversation'])+' · Tin ảnh: '+', '.join(imgs)+'\nNhờ kiểm tra và gửi lại mẫu sau chỉnh. Chưa phải lệnh duyệt in.'
 if len(caption)>11000:raise ValueError('Bản tổng hợp quá dài; cần tách rõ từng mẫu')
 payload={'request_id':'hub-design-revision-'+identity,'customer_name':'File In - Giấy In - Màng Pet','message':caption,'source_ids':req,'image_sources':proofs,'conversation':run['conversation']}
 encoded=json.dumps(payload,ensure_ascii=False,sort_keys=True)
 with agent.store.db() as db:
  db.execute('BEGIN IMMEDIATE')
  old=db.execute('SELECT payload,state FROM design_revision_notices WHERE id=?',(identity,)).fetchone()
  if old:
   if old['payload']!=encoded:raise ValueError('Yêu cầu đã có nhưng nội dung/ảnh thay đổi; không gửi trùng')
   return {'state':'revision_queued','notice_id':identity,'delivery_state':old['state'],'sent':False}
  db.execute("INSERT INTO design_revision_notices VALUES(?,?,?,?,?,'queued','{}',?,?)",(identity,run['id'],run['account'],run['thread_id'],encoded,time.time(),time.time()))
 return {'state':'revision_queued','notice_id':identity,'sent':False,'image_delivery':'exact_nas_links','erp_committed':False}


def tick(engine):
 initialize(engine.store)
 cfg=config(engine.store)
 if cfg.get('enabled') is not True or cfg.get('thread_id')!='g3307527274697028144' or cfg.get('destination_account')!='zalo-personal-1':return
 with engine.store.db() as db:
  row=db.execute("SELECT * FROM design_revision_notices WHERE state='queued' ORDER BY created LIMIT 1").fetchone()
 if not row:return
 with httpx.Client(timeout=15,trust_env=False) as client:
  with engine.store.db() as db:
   if not db.execute("UPDATE design_revision_notices SET state='sending',updated=? WHERE id=? AND state='queued'",(time.time(),row['id'])).rowcount:return
  payload=json.loads(row['payload']);state='uncertain';receipt={}
  try:
   response=client.post('http://192.168.1.101:8000/api/send-zalo',json={k:payload[k] for k in ('request_id','customer_name','message')});response.raise_for_status();receipt=response.json()
   if receipt.get('delivery_id')!='zalo:'+payload['request_id']:raise ValueError('Biên nhận sai request_id')
   state={'queued':'accepted','submitted':'submitted','confirmed':'confirmed','blocked':'blocked','failed':'blocked'}.get(receipt.get('state'),'uncertain')
   record_status(engine.store,state,'API máy 101 trả kết quả: '+state,payload['request_id'])
  except Exception as exc:
   receipt={'error':type(exc).__name__,'do_not_resend':True}
   record_status(engine.store,'error',type(exc).__name__+': Chưa rõ kết quả gửi; không tự gửi lại.',payload['request_id'])
  with engine.store.db() as db:db.execute('UPDATE design_revision_notices SET state=?,result=?,updated=? WHERE id=?',(state,json.dumps(receipt,ensure_ascii=False),time.time(),row['id']))
  engine.note('design-revision:'+row['id']+':receipt',payload['conversation'],'CHỈNH MẪU — NỘI BỘ: '+state+'; máy101 / File In. Mã '+payload['request_id']+'. Ảnh gửi dưới dạng đường dẫn NAS đúng nguồn; accepted chỉ là nhận hàng đợi, chưa xác nhận đã gửi. Không tự gửi lại.',apply_capture=True)
