"""Explicit owner export requests. No order writes, RIP or public delivery."""
import json,time
from hub.store import event_key
ACTIVE={'preparing','scheduled','planning','awaiting_upload','queued','reading','exporting','publishing','uncertain'}
EXPORTABLE_EXT=('.pdf','.ai','.psd','.png','.jpg','.jpeg','.tif','.tiff')
def jobs(db,bid):
 from hub.dispatch_stage import shared_done_exports
 shared,covered_shas=shared_done_exports(db,bid)
 out=[]
 for table in ('artwork_checks','pet_exports','jpg_exports'):
  condition='brief_id=?' if table=='artwork_checks' else "json_extract(payload,'$.brief_id')=?"
  for r in db.execute('SELECT * FROM '+table+' WHERE '+condition+' ORDER BY created DESC',(bid,)):
   p=json.loads(r['payload']);result=json.loads(r['result']) if table=='artwork_checks' else {}
   sha=((p.get('source') or {}).get('asset') or {}).get('sha256')
   if shared and table in ('pet_exports','jpg_exports') and r['state']!='done' and sha in covered_shas:continue
   out.append({'id':r['id'],'kind':table,'state':r['state'],'created':r['created'],'reason':p.get('review_reason') or '; '.join(result.get('errors',[])),'path':p.get('archive_relative','')})
 if shared:
  for r in shared:
   out.append({'id':r['id'],'kind':r['kind'],'state':'done','created':r['created'],'reason':'','path':r['payload_obj'].get('archive_relative','')})
 return sorted(out,key=lambda x:(x['created'],x['kind']!='artwork_checks'),reverse=True)
def listing(e):
 pending=[];history=[]
 with e.store.db() as d:
  for r in d.execute('SELECT * FROM design_briefs ORDER BY created DESC LIMIT 1000').fetchall():
   p=json.loads(r['payload'])
   if p.get('dispatch_removed_at'):continue
   js=jobs(d,r['id'])
   current=e.artwork_checks.pet.workflow.current(r['id'])
   latest=js[0] if js else {}
   from hub.slip_reference import reference_only
   if reference_only(d,p):
    latest={'state':'archived','reason':'Phiếu lệnh: chỉ lên ERP và làm nguồn tham chiếu; xuất từ hồ sơ file thiết kế.'}
    current=False
   native_busy=None
   if d.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='native_selections'").fetchone():
    native_busy=d.execute("SELECT state,payload FROM native_selections WHERE brief_id=? AND (state IN ('scan_queued','scan_running','render_queued','render_running','png_check_queued','uncertain') OR json_extract(payload,'$.auto_status') IN ('planning','verifying','waiting_verify','waiting_scan')) ORDER BY created DESC LIMIT 1",(r['id'],)).fetchone()
   finished=not current or (latest.get('state') in ('done','archived','superseded','not_jpg') and not native_busy)
   if native_busy:latest={'state':native_busy['state'],'reason':json.loads(native_busy['payload']).get('error','')}
   if not p.get('sources'):continue
   if current and not finished:
    from hub.source_readiness import readiness,collection_window
    gate=readiness(d,p);window=collection_window(d,p)
    explicit=d.execute('SELECT payload FROM artwork_checks WHERE brief_id=? ORDER BY created DESC LIMIT 1',(r['id'],)).fetchone()
    if explicit and (json.loads(explicit[0]).get('owner_context') or json.loads(explicit[0]).get('owner_instruction')):gate=None
    if gate and not gate['ready']:latest={'state':('reuse_existing' if gate.get('status')=='reuse_existing' else 'waiting_sources'),'reason':gate['reason']+(' · '+window['reason'] if window['waiting'] else '')}
    elif window['waiting'] and latest.get('state','not_started') in ('not_started','waiting_sources','awaiting_upload'):latest={'state':'collecting_sources','reason':window['reason']}
   from hub.dispatch_stage import status
   progress=status(d,p,r['id'],current,latest.get('state',''),latest.get('reason',''))
   finished=progress['stage'] in ('complete','cancelled')
   (history if finished else pending).append({**progress,'id':r['id'],'title':p.get('brief',{}).get('title',r['id'][:12]),'state':latest.get('state','not_started'),'reason':progress['reason'],'account':r['account'],'created':r['created']})
 from hub.psd_samples import listing as sample_listing
 for sample in sample_listing(e):
  state=sample['state'];stage='complete' if state=='done' else 'export' if state in ('exporting','queued','running') else 'sources' if state in ('waiting_sources','waiting_details') else 'plan'
  from hub.dispatch_stage import STAGES,ACTIVITY
  activity='done' if state=='done' else 'running' if state in ('exporting','running') else 'queued' if state=='queued' else 'waiting_sources' if stage=='sources' else 'waiting_staff'
  sample.update(stage=stage,stage_label=dict(STAGES)[stage],activity=activity,activity_label=ACTIVITY[activity])
  (history if state=='done' else pending).append(sample)
 pending.sort(key=lambda x:x['created'],reverse=True)
 return {'pending':pending,'completed':len(history),'history':history,'limit':1000}
def detail(e,bid):
 from hub.psd_samples import detail as sample_detail
 sample=sample_detail(e,bid)
 if sample:return sample
 with e.store.db() as d:
  r=d.execute('SELECT * FROM design_briefs WHERE id=?',(bid,)).fetchone()
  if not r:raise ValueError('Không tìm thấy hồ sơ')
  p=json.loads(r['payload']);js=jobs(d,bid)
  assets=[];images=[];seen=set()
  for src in p.get('sources',[]):
   for a in src.get('assets',[]):
    if a.get('state')=='ready' and a.get('sha256') not in seen:
     seen.add(a.get('sha256'));assets.append({'name':a.get('name'),'sha256':a.get('sha256'),'exportable':a.get('name','').lower().endswith(EXPORTABLE_EXT)})
   for image in src.get('images',[]):
    if len(images)<8:
     try:
      im=e.store.images([image])[0]
      if len(im['data'])<4000000:images.append(im)
     except Exception:pass
 checks=[]
 with e.store.db() as d:
  for row in d.execute('SELECT id,payload,result,state FROM artwork_checks WHERE brief_id=? ORDER BY created DESC',(bid,)):
   payload=json.loads(row['payload']);result=json.loads(row['result'] or '{}')
   tech=result.get('technical') or {}
   ng=tech.get('native_groups') or {}
   ai_info=tech.get('illustrator') or {}
   raw_boards=ng.get('artboards') or ai_info.get('artboards') or []
   artboards=[]
   for idx,b in enumerate(raw_boards[:30]):
    bounds=b.get('bounds_pt')
    w_cm=round(abs(bounds[2]-bounds[0])/28.346456692913385,2) if isinstance(bounds,list) and len(bounds)==4 else b.get('width_cm')
    h_cm=round(abs(bounds[1]-bounds[3])/28.346456692913385,2) if isinstance(bounds,list) and len(bounds)==4 else b.get('height_cm')
    artboards.append({'index':b.get('index',idx),'page':idx+1,'name':b.get('name') or f'Artboard {idx+1}','width_cm':w_cm,'height_cm':h_cm})
   candidates=[{'id':c.get('id'),'kind':c.get('kind'),'name':c.get('name',''),'width_cm':c.get('width_cm'),'height_cm':c.get('height_cm'),'live_text_count':c.get('live_text_count',0),'solid_cmyk_fill':c.get('solid_cmyk_fill'),'preview':c.get('preview','')} for c in (ng.get('candidates') or [])[:60]]
   tech_summary={'state':tech.get('state',''),'page_count':tech.get('page_count') or len(tech.get('pdf_pages') or []),
    'pdf_pages':[{'page':pg.get('page'),'width_cm':pg.get('width_cm'),'height_cm':pg.get('height_cm')} for pg in (tech.get('pdf_pages') or [])[:20]],
    'artboards':artboards,'missing_fonts':tech.get('missing_fonts') or ai_info.get('missing_fonts') or [],
    'linked_items':tech.get('linked_items') or ai_info.get('linked_items') or [],
    'native_group_error':tech.get('native_group_error',''),'candidates':candidates} if tech else {}
   checks.append({'id':row['id'],'file':payload.get('asset',{}).get('name'),'state':row['state'],'comparison':result.get('comparison',{}),'errors':result.get('errors',[]),'proposal':result.get('designer_proposal',{}).get('selections',[]),'technical':tech_summary})
 catalogs=[]
 with e.store.db() as db:
  for row in db.execute("SELECT id,payload,state FROM jpg_exports WHERE json_extract(payload,'$.brief_id')=? ORDER BY created DESC",(bid,)):
   payload=json.loads(row['payload'])
   if payload.get('catalog'):catalogs.append({'job_id':row['id'],'state':row['state'],'file':payload.get('source',{}).get('asset',{}).get('name',''),'catalog':payload['catalog']})
 from pathlib import Path
 report=Path(e.store.path).parent/'jpg-exports'/'catalog-reports'/(bid+'.json')
 if report.is_file():
  saved=json.loads(report.read_text(encoding='utf-8'))
  catalogs.append({'job_id':'classification-trial','state':'classified_only','file':saved.get('file',''),'catalog':saved['catalog']})
 from hub.native_selection import detail as native_detail
 from hub.print_governance import detail as management_detail
 from hub.dispatch_workspace import workspace
 native=native_detail(e,bid)
 view=workspace(e,p,bid,js,native)
 for src in view['sources']:
  if src['link_basis']=='nearby_unconfirmed':continue
  for a in src.get('assets') or []:
   if a.get('state')=='ready' and a.get('sha256') not in seen:
    seen.add(a.get('sha256'));assets.append({'name':a.get('name'),'sha256':a.get('sha256'),'exportable':a.get('name','').lower().endswith(EXPORTABLE_EXT)})
 from hub.manual_export import review_data
 return {'manual':review_data(e,bid),'workspace':view,'management':management_detail(e,bid),'print_catalogs':catalogs,'source_checks':checks,'native':native,'id':bid,'title':p.get('brief',{}).get('title',''),'requirements':p.get('brief',{}).get('requirements',[]),'missing':p.get('brief',{}).get('missing_fields',[]),'assets':assets,'images':images,'jobs':js,'image_context':p.get('brief',{}).get('image_context'),'current':e.artwork_checks.pet.workflow.current(bid)}
def unarchive_brief(store,bid):
 with store.db() as d:
  r=d.execute('SELECT payload FROM design_briefs WHERE id=?',(bid,)).fetchone()
  if not r:return
  p=json.loads(r['payload'])
  if 'dispatch_archived_at' in p or 'dispatch_archive_reason' in p:
   history=p.setdefault('dispatch_reopened_history',[])
   history.append({'archived_at':p.pop('dispatch_archived_at',None),'reason':p.pop('dispatch_archive_reason',None),'reopened_at':time.time()})
   d.execute('UPDATE design_briefs SET payload=? WHERE id=?',(json.dumps(p,ensure_ascii=False),bid))
def submit(e,bid,data):
 if data.get('action')=='manual_approve':
  from hub.manual_export import approve
  return approve(e,bid,data)
 if data.get('action')=='manual_discard':
  from hub.manual_export import discard
  return discard(e,bid,data)
 from hub.manual_export import review_data
 pending_owner=review_data(e,bid)
 if pending_owner and pending_owner['jobs']:
  raise ValueError('Duyệt hoặc bỏ các phương án đang chờ trước khi lập lượt mới')
 owner_context=None
 if data.get('action')=='resume_workspace':
  from hub.dispatch_workspace import prepare_request
  if data.get('export_spec',{}).get('mode')=='auto':
   from hub.manual_export import is_manual
   if is_manual(e.store,bid):raise ValueError('Hồ sơ chạy tay: chọn rõ loại xuất thay vì Tự xác định')
  data=prepare_request(e,bid,data)
  owner_context=data['_owner_context']
 if data.get('action')=='retry_export':
  unarchive_brief(e.store,bid)
  from hub.print_governance import retry
  return retry(e,bid,data)
 if data.get('action')=='approve_plan':
  from hub.print_governance import approve_plan
  return approve_plan(e,bid,data)
 if data.get('action')=='approve_verified_output':
  from hub.print_governance import approve_verified_output
  return approve_verified_output(e,bid,data)
 if data.get('action','').startswith('native_'):
  unarchive_brief(e.store,bid)
  from hub.native_selection import submit as native_submit
  return native_submit(e,bid,data)
 note=str(data.get('note','')).strip();sha=str(data.get('sha256',''))
 if not 5<=len(note)<=3000:raise ValueError('Nhập yêu cầu cụ thể từ 5–3000 ký tự')
 from hub.order_policy import capture_allowed
 unarchive_brief(e.store,bid)
 with e.store.db() as d:
  r=d.execute('SELECT * FROM design_briefs WHERE id=?',(bid,)).fetchone()
 if not r:raise ValueError('Không tìm thấy hồ sơ')
 p=json.loads(r['payload'])
 sources=owner_context['sources'] if owner_context else p.get('sources',[])
 candidates=[(s,a) for s in sources for a in s.get('assets',[]) if a.get('state')=='ready' and a.get('sha256')==sha and a.get('name','').lower().endswith(EXPORTABLE_EXT)]
 raster=not sha
 if not candidates and not raster:raise ValueError('File chọn không thuộc hồ sơ hoặc chưa sẵn sàng')
 if raster and p.get('brief',{}).get('image_context')!='standalone_artwork':raise ValueError('Ảnh sản phẩm/maket chưa hỗ trợ xuất trực tiếp ở nút này; chọn PDF/AI gốc hoặc cần chuẩn bị artwork trước')
 identity=event_key('owner-dispatch-v1',bid,sha,note)
 with e.store.db() as d:
  d.execute('BEGIN IMMEDIATE')
  d.execute('CREATE TABLE IF NOT EXISTS owner_export_requests(id TEXT PRIMARY KEY,brief_id TEXT,note TEXT,source_sha256 TEXT,created REAL)')
  native_busy=d.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='native_selections'").fetchone() and d.execute("SELECT 1 FROM native_selections WHERE brief_id=? AND (state IN ('scan_queued','scan_running','render_queued','render_running','png_check_queued','uncertain') OR json_extract(payload,'$.auto_status') IN ('planning','verifying','waiting_verify','waiting_scan'))",(bid,)).fetchone()
  if native_busy or any(j['state'] in ACTIVE for j in jobs(d,bid)):raise ValueError('Có lượt đang chạy hoặc chưa rõ kết quả. Chưa cho chạy thêm để tránh trùng')
  now=time.time()
  if d.execute('SELECT 1 FROM owner_export_requests WHERE id=?',(identity,)).fetchone():
   identity=event_key('owner-dispatch-v1',bid,sha,note,str(now))
  common={'brief_id':bid,'conversation':r['conversation'],'thread_id':r['thread_id'],'owner_instruction':note,'private':True,'auto_rip':False,'mirror':False}
  if p.get('manual_export'):common['manual_export']=True
  if owner_context:
   common.update(owner_context=owner_context,owner_export_spec=owner_context['spec'])
  if data.get('authorize_restoration') is True:
   if not raster:raise ValueError('Phục hồi ảnh chỉ áp dụng nguồn raster đã chọn')
   from hub.raster_consent import owner_restoration_consent
   approval={'authorized':True,'brief_id':bid,'image_id':data.get('source_image_id'),'enhance_only':data.get('enhance_only') is True}
   owner_restoration_consent(dict(p,id=bid),approval,identity)
   common['owner_restoration']=approval
  if raster:
   d.execute("INSERT INTO pet_exports VALUES(?,?,'scheduled',?,?)",(identity,r['account'],json.dumps(common),now))
   d.execute("INSERT INTO jobs(id,kind,payload,created) VALUES(?,'raster_pet',?,?)",('raster:'+identity,json.dumps({'id':identity}),now))
  else:
   src,a=candidates[0];common.update(source_message_id=src['message_id'],asset=a,relation='brief_source',reference_assets=[])
   d.execute("INSERT INTO artwork_checks(id,brief_id,account,state,payload,created) VALUES(?,?,?,'awaiting_upload',?,?)",(identity,bid,r['account'],json.dumps(common),now))
  d.execute('INSERT INTO owner_export_requests VALUES(?,?,?,?,?)',(identity,bid,note,sha,now))
 return {'id':identity,'duplicate':False,'message':'Đã xếp hàng đọc và xuất bản mới để duyệt nội bộ. Yêu cầu sửa sẽ được đối chiếu; phần chưa hỗ trợ vẫn báo kiểm tra.'}
