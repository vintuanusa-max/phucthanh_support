"""Owner-selected Illustrator artwork. Reuses the verified PET delivery pipeline."""
import base64, hashlib, io, json, math, re, threading, time
from PIL import Image
from hub.store import event_key
LOCK=threading.RLock()

def trim_artwork(im,width_cm):
 box=im.getchannel('A').getbbox()
 if not box:raise ValueError('Artwork rỗng')
 crop=im.crop(box)
 pixels=max(1,round(width_cm/2.54*300));height=max(1,round(pixels*crop.height/crop.width))
 if max(pixels,height)>20000:raise ValueError('Artwork sau cắt vượt giới hạn raster')
 if crop.size!=(pixels,height):crop=crop.resize((pixels,height),Image.Resampling.LANCZOS)
 return crop,{'source_pixels':list(im.size),'alpha_bbox':list(box),'output_pixels':[pixels,height],'width_cm':width_cm,'height_cm':width_cm*(box[3]-box[1])/(box[2]-box[0])}


def init(e):
 with e.store.db() as d:
  d.execute('CREATE TABLE IF NOT EXISTS native_selections(id TEXT PRIMARY KEY,brief_id TEXT,account TEXT,state TEXT,payload TEXT,created REAL)')

def detail(e,bid):
 init(e)
 with e.store.db() as d:
  rows=d.execute('SELECT * FROM native_selections WHERE brief_id=? ORDER BY created DESC',(bid,)).fetchall()
 return [dict(id=r['id'],state=r['state'],**{k:v for k,v in json.loads(r['payload']).items() if k!='pending_pet'}) for r in rows]

def submit(e,bid,data):
 from hub.order_policy import capture_allowed
 from hub.dispatch_control import jobs,ACTIVE
 init(e)
 with LOCK,e.store.db() as d:
  d.execute('BEGIN IMMEDIATE')
  r=d.execute('SELECT * FROM design_briefs WHERE id=?',(bid,)).fetchone()
  if not r:raise ValueError('Không có hồ sơ')
  b=json.loads(r['payload']);mapping=e.store.thread(account=r['account'],thread_id=r['thread_id']);policy=e.order_intake.policy(r['account'])
  if not mapping or not policy or not capture_allowed(policy,e.settings.inboxes[r['account']]['channel'],r['thread_id'],mapping['display_name']):raise ValueError('Nhóm không được phép')
  if not e.artwork_checks.pet.workflow.current(bid):raise ValueError('Hồ sơ đã được thay thế')
  sha=str(data.get('sha256',''));sources=[(s,a) for s in b.get('sources',[]) for a in s.get('assets',[]) if a.get('state')=='ready' and a.get('sha256')==sha and a.get('name','').lower().endswith(('.pdf','.ai'))]
  if not sources:raise ValueError('Nguồn không thuộc hồ sơ')
  src,asset=sources[0];action=data.get('action');p={'asset':asset,'source_message_id':src['message_id'],'brief_id':bid,'conversation':r['conversation'],'thread_id':r['thread_id'],'private':True,'mirror':False,'auto_rip':False}
  if action=='native_scan':
   identity=event_key('native-scan-v1',bid,sha);state='scan_queued'
  elif action=='native_export':
   scan=d.execute("SELECT * FROM native_selections WHERE id=? AND brief_id=? AND state='candidates_ready'",(str(data.get('scan_id','')),bid)).fetchone()
   if not scan:raise ValueError('Chưa đọc xong các cụm')
   sp=json.loads(scan['payload'])
   if sp['asset']['sha256']!=sha:raise ValueError('Cụm khác file nguồn')
   ids=sorted(set(data.get('candidate_ids',[])))
   chosen=[c for c in sp['scan']['candidates'] if c['id'] in ids]
   if not ids or len(ids)!=len(chosen):raise ValueError('Chọn cụm hợp lệ')
   if any(a!=b and b.startswith(a+'.') for a in ids for b in ids):raise ValueError('Không chọn đồng thời cụm cha và cụm con')
   if any(c.get('live_text_count',1)>0 for c in chosen) and sp['scan'].get('missing_fonts'):raise ValueError('Cụm có chữ sống và font thiếu: cần khôi phục font hoặc outline từ file gốc trước khi xuất')
   width=float(data.get('width_cm',0));note=str(data.get('note','')).strip()
   if not math.isfinite(width) or not .1<=width<=160 or not 5<=len(note)<=3000:raise ValueError('Cần chiều ngang 0,1–160cm và ghi chú đối chiếu')
   side=str(data.get('side','front'))
   if side not in ['front','back','left','right','brim','label']+['position_'+str(i) for i in range(1,9)]:raise ValueError('Vị trí in không hợp lệ')
   p.update(side=side,scan_id=scan['id'],candidates=chosen,candidate_ids=ids,width_cm=width,note=note,font_warnings=sp['scan'].get('missing_fonts',[]))
   identity=event_key('native-export-v2',bid,sha,json.dumps(ids),str(width),side,note);state='render_queued'
  else:raise ValueError('Lệnh không hợp lệ')
  if d.execute('SELECT 1 FROM native_selections WHERE id=?',(identity,)).fetchone():return {'id':identity,'duplicate':True,'message':'Lượt này đã có, không xuất trùng'}
  if d.execute("SELECT 1 FROM native_selections WHERE brief_id=? AND (state IN ('scan_queued','scan_running','render_queued','render_running','png_check_queued','uncertain') OR json_extract(payload,'$.auto_status') IN ('planning','verifying','waiting_verify','waiting_scan'))",(bid,)).fetchone() or any(j['state'] in ACTIVE for j in jobs(d,bid)):raise ValueError('Hồ sơ đang chạy/chưa rõ kết quả, không chạy chồng')
  d.execute('INSERT INTO native_selections VALUES(?,?,?,?,?,?)',(identity,bid,r['account'],state,json.dumps(p),time.time()))
 return {'id':identity,'message':'Đã xếp hàng Illustrator; chỉ xuất mẫu nội bộ, không sửa đơn ERP'}

def pending(e,account):
 init(e)
 with LOCK,e.store.db() as d:
  d.execute('BEGIN IMMEDIATE')
  r=d.execute("SELECT * FROM native_selections WHERE account=? AND state IN ('scan_queued','render_queued','scan_running','render_running') ORDER BY created LIMIT 1",(account,)).fetchone()
  if not r:return None
  if not e.artwork_checks.pet.workflow.current(r['brief_id']):
   d.execute("UPDATE native_selections SET state='superseded' WHERE id=?",(r['id'],));return None
  state='scan_running' if r['state'].startswith('scan') else 'render_running'
  d.execute('UPDATE native_selections SET state=? WHERE id=?',(state,r['id']))
  return dict(id=r['id'],state=state,**json.loads(r['payload']))

def result(e,account,identity,data):
 init(e)
 with LOCK,e.store.db() as d:
  r=d.execute('SELECT * FROM native_selections WHERE id=? AND account=?',(identity,account)).fetchone()
  if not r:raise ValueError('Không có lượt Illustrator')
  p=json.loads(r['payload'])
  if r['state'] not in ('scan_running','render_running'):return {'state':r['state']}
  if not e.artwork_checks.pet.workflow.current(r['brief_id']):
   d.execute("UPDATE native_selections SET state='superseded' WHERE id=?",(identity,));return {'state':'superseded'}
  if data.get('error'):
   p['error']=str(data['error'])[:1200];state='review'
   if p.get('auto_context'):p['auto_status']='review'
  elif r['state']=='scan_running':
   scan=data['scan']
   if scan.get('source_sha256')!=p['asset']['sha256'] or not 0<len(scan.get('candidates',[])):raise ValueError('Danh sách cụm sai nguồn')
   ids=set()
   for c in scan['candidates']:
    if not re.fullmatch(r'\d+(?:\.\d+)+',c['id']) or c['id'] in ids:raise ValueError('ID cụm không hợp lệ')
    ids.add(c['id']);raw=base64.b64decode(c['preview'],validate=True)
    if len(raw)>2000000:raise ValueError('Preview quá lớn')
    with Image.open(io.BytesIO(raw)) as im:
     if im.format!='PNG' or max(im.size)>1600:raise ValueError('Preview không hợp lệ')
   p['scan']=scan;state='candidates_ready'
  else:
   raw=base64.b64decode(data['png'],validate=True)
   if len(raw)>32_000_000:raise ValueError('PNG quá lớn')
   with Image.open(io.BytesIO(raw)) as im:
    if im.format!='PNG' or im.mode!='RGBA' or max(im.size)>20000:raise ValueError('PNG phải trong suốt')
    if any(abs(v-300)>.1 for v in im.info.get('dpi',(0,0))):raise ValueError('PNG sai DPI')
    a=im.getchannel('A')
    if not a.getbbox() or a.getextrema()[0]==255:raise ValueError('Chưa có nền trong suốt')
    width=im.width/300*2.54;height=im.height/300*2.54
    if abs(width-p['width_cm'])>.04:raise ValueError('PNG sai kích thước đã chọn')
    c=p['candidates'];left=min(x['bounds'][0] for x in c);right=max(x['bounds'][2] for x in c);top=max(x['bounds'][1] for x in c);bottom=min(x['bounds'][3] for x in c)
    if abs(height-width*(top-bottom)/(right-left))>.04:raise ValueError('PNG sai tỷ lệ')
    im,geometry=trim_artwork(im,p['width_cm'])
    p['export_geometry']=geometry
    if p.get('auto_face'):
     p['auto_face']=dict(p['auto_face'],width_cm=geometry['width_cm'],height_cm=geometry['height_cm'])
    width=im.width/300*2.54;height=im.height/300*2.54
    p['note']='Artwork '+p.get('side','front')+'; cụm '+', '.join(p['candidate_ids'])+'; đã cắt sát alpha, ngang '+format(width,'.3f')+' × cao '+format(height,'.3f')+' cm; giữ khoảng cách các chi tiết bên trong, nền trong suốt và mực trắng. Không lật gương.'
    buf=io.BytesIO();im.save(buf,format='PNG',dpi=(300,300));raw=buf.getvalue()
    from hub.pet_render import code_name
    code=code_name(p['asset']['name'].rsplit('.',1)[0]);name=code+'_'+p.get('side','front')+'.png';folder=e.artwork_checks.pet.root/identity;folder.mkdir(exist_ok=True)
    target=folder/name
    if target.exists() and target.read_bytes()!=raw:raise ValueError('Không ghi đè kết quả khác')
    target.write_bytes(raw)
    preview=im.copy();preview.thumbnail((1000,1000));bg=Image.new('RGBA',preview.size,'#666666');bg.alpha_composite(preview);bg.convert('RGB').save(target.with_suffix('.preview.png'))
    info=dict(name=name,sha256=hashlib.sha256(raw).hexdigest(),pixels=list(im.size),width_cm=round(width,3),height_cm=round(height,3))
   warnings=[p['note']]+(['Font nguồn chưa có trên máy: '+', '.join(p['font_warnings'])+'. Cụm chọn không có chữ sống; giữ vector/ảnh gốc.'] if p['font_warnings'] else [])
   plan={'order_code':code,'faces':[{'side':p.get('side','front'),'object_ids':p['candidate_ids'],'width_cm':width,'height_cm':height}],'review_warnings':warnings}
   pp={'source':dict(p),'brief_id':p['brief_id'],'archive_folder':p['asset']['relative_path'].replace('\\','/').split('/')[0],'conversation':p['conversation'],'private':True,'auto_rip':False,'plan':plan,'files':[info],'native_selection':identity,'verification':{'review_warnings':warnings}}
   if p.get('auto_selected'):
    p['pending_pet']=pp;p['auto_status']='waiting_verify';state='png_check_queued'
   else:
    d.execute("INSERT OR IGNORE INTO pet_exports VALUES(?,?,'queued',?,?)",(identity,account,json.dumps(pp),time.time()))
    p['pet_job_id']=identity;state='png_ready'
  d.execute('UPDATE native_selections SET state=?,payload=? WHERE id=?',(state,json.dumps(p),identity))
 return {'state':state}
