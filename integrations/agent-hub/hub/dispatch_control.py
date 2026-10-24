"""Explicit owner export requests. No order writes, RIP or public delivery."""
import json,time
from hub.store import event_key
ACTIVE={'scheduled','planning','awaiting_upload','queued','reading','exporting','publishing','uncertain'}
def jobs(db,bid):
 out=[]
 for table in ('artwork_checks','pet_exports','jpg_exports'):
  condition='brief_id=?' if table=='artwork_checks' else "json_extract(payload,'$.brief_id')=?"
  for r in db.execute('SELECT * FROM '+table+' WHERE '+condition+' ORDER BY created DESC',(bid,)):
   p=json.loads(r['payload']);result=json.loads(r['result']) if table=='artwork_checks' else {}
   out.append({'id':r['id'],'kind':table,'state':r['state'],'created':r['created'],'reason':p.get('review_reason') or '; '.join(result.get('errors',[])),'path':p.get('archive_relative','')})
 return sorted(out,key=lambda x:(x['created'],x['kind']!='artwork_checks'),reverse=True)
def listing(e):
 pending=[];history=[]
 with e.store.db() as d:
  for r in d.execute('SELECT * FROM design_briefs ORDER BY created DESC LIMIT 1000').fetchall():
   p=json.loads(r['payload']);js=jobs(d,r['id'])
   current=e.artwork_checks.pet.workflow.current(r['id'])
   latest=js[0] if js else {}
   native_busy=None
   if d.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='native_selections'").fetchone():
    native_busy=d.execute("SELECT state,payload FROM native_selections WHERE brief_id=? AND (state IN ('scan_queued','scan_running','render_queued','render_running','png_check_queued','uncertain') OR json_extract(payload,'$.auto_status') IN ('planning','verifying','waiting_verify','waiting_scan')) ORDER BY created DESC LIMIT 1",(r['id'],)).fetchone()
   finished=not current or (latest.get('state') in ('done','archived','superseded','not_jpg') and not native_busy)
   if native_busy:latest={'state':native_busy['state'],'reason':json.loads(native_busy['payload']).get('error','')}
   if not p.get('sources'):continue
   (history if finished else pending).append({'id':r['id'],'title':p.get('brief',{}).get('title',r['id'][:12]),'state':latest.get('state','not_started'),'reason':latest.get('reason',''),'account':r['account'],'created':r['created']})
 return {'pending':pending,'completed':len(history),'history':history,'limit':1000}
def detail(e,bid):
 with e.store.db() as d:
  r=d.execute('SELECT * FROM design_briefs WHERE id=?',(bid,)).fetchone()
  if not r:raise ValueError('Không tìm thấy hồ sơ')
  p=json.loads(r['payload']);js=jobs(d,bid)
  assets=[];images=[];seen=set()
  for src in p.get('sources',[]):
   for a in src.get('assets',[]):
    if a.get('state')=='ready' and a.get('sha256') not in seen:
     seen.add(a.get('sha256'));assets.append({'name':a.get('name'),'sha256':a.get('sha256'),'exportable':a.get('name','').lower().endswith(('.pdf','.ai'))})
   for image in src.get('images',[]):
    if len(images)<8:
     try:
      im=e.store.images([image])[0]
      if len(im['data'])<4000000:images.append(im)
     except Exception:pass
 checks=[]
 with e.store.db() as d:
  for row in d.execute('SELECT payload,result,state FROM artwork_checks WHERE brief_id=?',(bid,)):
   payload=json.loads(row['payload']);result=json.loads(row['result'] or '{}')
   checks.append({'file':payload.get('asset',{}).get('name'),'state':row['state'],'comparison':result.get('comparison',{}),'errors':result.get('errors',[]),'proposal':result.get('designer_proposal',{}).get('selections',[])})
 from hub.native_selection import detail as native_detail
 return {'source_checks':checks,'native':native_detail(e,bid),'id':bid,'title':p.get('brief',{}).get('title',''),'requirements':p.get('brief',{}).get('requirements',[]),'missing':p.get('brief',{}).get('missing_fields',[]),'assets':assets,'images':images,'jobs':js,'image_context':p.get('brief',{}).get('image_context'),'current':e.artwork_checks.pet.workflow.current(bid)}
def submit(e,bid,data):
 if data.get('action','').startswith('native_'):
  from hub.native_selection import submit as native_submit
  return native_submit(e,bid,data)
 note=str(data.get('note','')).strip();sha=str(data.get('sha256',''))
 if not 5<=len(note)<=3000:raise ValueError('Nhập yêu cầu cụ thể từ 5–3000 ký tự')
 from hub.order_policy import capture_allowed
 with e.store.db() as d:
  r=d.execute('SELECT * FROM design_briefs WHERE id=?',(bid,)).fetchone()
 if not r:raise ValueError('Không tìm thấy hồ sơ')
 p=json.loads(r['payload']);mapping=e.store.thread(account=r['account'],thread_id=r['thread_id']);policy=e.order_intake.policy(r['account'])
 if not mapping or not policy or not capture_allowed(policy,e.settings.inboxes[r['account']]['channel'],r['thread_id'],mapping['display_name']):raise ValueError('Nhóm không được phép xử lý')
 if not e.artwork_checks.pet.workflow.current(bid):raise ValueError('Hồ sơ đã có phiên bản mới')
 candidates=[(s,a) for s in p.get('sources',[]) for a in s.get('assets',[]) if a.get('state')=='ready' and a.get('sha256')==sha and a.get('name','').lower().endswith(('.pdf','.ai'))]
 raster=not sha
 if not candidates and not raster:raise ValueError('File chọn không thuộc hồ sơ hoặc chưa sẵn sàng')
 if raster and p.get('brief',{}).get('image_context')!='standalone_artwork':raise ValueError('Ảnh sản phẩm/maket chưa hỗ trợ xuất trực tiếp ở nút này; chọn PDF/AI gốc hoặc cần chuẩn bị artwork trước')
 identity=event_key('owner-dispatch-v1',bid,sha,note)
 with e.store.db() as d:
  d.execute('BEGIN IMMEDIATE')
  d.execute('CREATE TABLE IF NOT EXISTS owner_export_requests(id TEXT PRIMARY KEY,brief_id TEXT,note TEXT,source_sha256 TEXT,created REAL)')
  if d.execute('SELECT 1 FROM owner_export_requests WHERE id=?',(identity,)).fetchone():return {'id':identity,'duplicate':True,'message':'Yêu cầu này đã được ghi nhận; không tạo thêm lượt'}
  native_busy=d.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='native_selections'").fetchone() and d.execute("SELECT 1 FROM native_selections WHERE brief_id=? AND (state IN ('scan_queued','scan_running','render_queued','render_running','png_check_queued','uncertain') OR json_extract(payload,'$.auto_status') IN ('planning','verifying','waiting_verify','waiting_scan'))",(bid,)).fetchone()
  if native_busy or any(j['state'] in ACTIVE for j in jobs(d,bid)):raise ValueError('Có lượt đang chạy hoặc chưa rõ kết quả. Chưa cho chạy thêm để tránh trùng')
  now=time.time()
  common={'brief_id':bid,'conversation':r['conversation'],'thread_id':r['thread_id'],'owner_instruction':note,'private':True,'auto_rip':False,'mirror':False}
  if raster:
   d.execute("INSERT INTO pet_exports VALUES(?,?,'scheduled',?,?)",(identity,r['account'],json.dumps(common),now))
   d.execute("INSERT INTO jobs(id,kind,payload,created) VALUES(?,'raster_pet',?,?)",('raster:'+identity,json.dumps({'id':identity}),now))
  else:
   src,a=candidates[0];common.update(source_message_id=src['message_id'],asset=a,relation='brief_source',reference_assets=[])
   d.execute("INSERT INTO artwork_checks(id,brief_id,account,state,payload,created) VALUES(?,?,?,'awaiting_upload',?,?)",(identity,bid,r['account'],json.dumps(common),now))
  d.execute('INSERT INTO owner_export_requests VALUES(?,?,?,?,?)',(identity,bid,note,sha,now))
 return {'id':identity,'duplicate':False,'message':'Đã xếp hàng đọc và xuất bản mới để duyệt nội bộ. Yêu cầu sửa sẽ được đối chiếu; phần chưa hỗ trợ vẫn báo kiểm tra.'}
