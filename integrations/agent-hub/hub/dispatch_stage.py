"""One workflow stage per dossier; independent from ERP and list filters."""
import json
STAGES=[('sources','Nhận nguồn'),('read','Đọc file'),('artwork','Chọn artwork'),('plan','Lập phương án'),('export','Xuất file'),('verify','Kiểm tra bản xuất'),('complete','Hoàn thành')]
ACTIVITY={'ready':'Sẵn sàng','running':'Đang chạy','queued':'Chờ chạy','waiting_sources':'Chờ bổ sung','waiting_staff':'Chờ nhân viên','error':'Lỗi','done':'Đã xong','cancelled':'Đã hủy'}
def decide(p,records,current=True,source_state='',source_reason=''):
 def out(stage,activity,reason=''):
  return dict(stage=stage,stage_label=dict(STAGES).get(stage,'Đã hủy'),activity=activity,activity_label=ACTIVITY[activity],reason=reason)
 if not current or p.get('dispatch_archived_at'):return out('cancelled','cancelled',p.get('dispatch_archive_reason') or 'Hồ sơ đã đóng hoặc được thay thế')
 records=sorted(records,key=lambda x:x.get('created',0),reverse=True)
 checks=[x for x in records if x['kind']=='artwork_checks']
 cutoff=checks[0].get('created',0) if checks else 0
 exports=[x for x in records if x['kind'] in ('pet_exports','jpg_exports') and x.get('created',0)>=cutoff and x['state'] not in ('superseded','archived')]
 if exports:
  parents={x['payload'].get('parent_job_id') for x in exports}|{x['payload'].get('derived_from') for x in exports}
  leaves=[x for x in exports if x['id'] not in parents]
  if leaves and all(x['state']=='done' and x['payload'].get('archive_relative') for x in leaves):return out('complete','done','Đủ các phần xuất, đã kiểm tra và lưu kết quả')
  if leaves and all(x['state']=='done' for x in leaves):return out('verify','error','Tác vụ báo xong nhưng thiếu đường dẫn lưu; cần kiểm tra kết quả')
  x=next((x for x in leaves if x['state']!='done'),leaves[0]);v=x['payload'];state=x['state'];reason=v.get('review_reason') or v.get('error','')
  if state in ('publishing','verifying','png_check_queued'):return out('verify','running',reason or 'Kiểm tra và lưu bản xuất')
  if state in ('exporting','queued'):return out('export','running' if state=='exporting' else 'queued',reason)
  if state in ('review','failed','error','uncertain'):
   target='verify' if (v.get('awaiting_verify_approval') or (v.get('technical_verified') and v.get('report'))) else ('export' if v.get('export_plan_ready') and not v.get('is_draft_plan') else 'plan')
   return out(target,'error' if reason or state!='review' else 'waiting_staff',reason or 'Cần nhân viên chọn phương án')
  if state=='awaiting_owner':return out('plan','waiting_staff','Đã lưu artwork; phương án sẵn sàng, chờ duyệt xuất')
  if state=='awaiting_upload':return out('sources','waiting_sources',reason or 'Chờ nhận file nguồn')
  if state not in ('delegated','done'):return out('plan','running' if state in ('planning','preparing') else 'waiting_staff',reason)
 native=[x for x in records if x['kind']=='native_selections' and x['state'] not in ('superseded','archived')]
 if native:
  x=native[0];v=x['payload'];state=x['state'];auto=v.get('auto_status');err=v.get('error','')
  stage='export' if state.startswith('render') else 'verify' if state in ('png_ready','png_check_queued') or auto in ('verifying','waiting_verify','verified') else 'read' if state.startswith('scan') else 'artwork'
  if state=='awaiting_owner':return out('plan','waiting_staff','Đã lưu artwork; phương án sẵn sàng, chờ duyệt xuất')
  if state=='review' or auto=='review':return out(stage,'error' if err else 'waiting_staff',err or 'Cần chọn cụm artwork')
  if auto=='selected':return out('plan','ready','Đã chọn artwork; chờ phương án xuất')
  return out(stage,'queued' if state.endswith('_queued') else 'running' if state.endswith('_running') or auto in ('planning','verifying') else 'waiting_staff',err)
 if checks:
  x=checks[0];state=x['state'];errors=x.get('result',{}).get('errors',[])
  if state=='awaiting_upload':return out('sources','waiting_sources','Chờ nhận file nguồn')
  if errors:return out('read','error','; '.join(errors))
  if state in ('queued','reading'):return out('read','queued' if state=='queued' else 'running')
  return out('artwork','waiting_staff','Đã đọc file; cần chọn artwork hoặc phương án tiếp theo')
 if source_state in ('waiting_sources','collecting_sources'):return out('sources','waiting_sources',source_reason)
 ready=any(a.get('state')=='ready' and a.get('name','').lower().endswith(('.ai','.pdf','.psd','.cdr','.eps','.svg','.tif','.tiff','.png','.jpg','.jpeg')) for m in p.get('sources',[]) for a in m.get('assets',[]))
 return out('read','ready','Đã có file; chưa bắt đầu đọc') if ready else out('sources','waiting_sources',source_reason or 'Chưa gắn file thiết kế sẵn sàng')
def _export_covers_code(code, rp):
 if not code:return True
 from hub.source_coverage import _base_match,codes,norm
 target=codes(code)
 if not target:return norm(code) in norm(rp.get('archive_relative',''))
 t_base,t_month=target[0]['base'],target[0]['month']
 plan=rp.get('plan') or {}
 texts=[plan.get('order_code',''),rp.get('archive_relative','')]
 texts+=[str(pan.get('name','')).replace('_',' ') for pan in plan.get('panels',[])]
 for c in codes(' '.join(str(t) for t in texts)):
  if _base_match(c['base'],t_base) and (not c['month'] or not t_month or c['month']==t_month):return True
 return False

def shared_done_exports(db,bid,p=None):
 try:
  if p is None:
   brow=db.execute('SELECT account,thread_id,payload FROM design_briefs WHERE id=?',(bid,)).fetchone()
   if not brow:return [],set()
   p=json.loads(brow['payload']);account=p.get('account') or brow['account'];thread_id=p.get('thread_id') or brow['thread_id']
  else:
   account=p.get('account');thread_id=p.get('thread_id')
   if not account or not thread_id:
    brow=db.execute('SELECT account,thread_id FROM design_briefs WHERE id=?',(bid,)).fetchone()
    if brow:account=account or brow['account'];thread_id=thread_id or brow['thread_id']
  if not account or not thread_id:return [],set()
  tables={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name IN ('artwork_checks','pet_exports','jpg_exports')").fetchall()}
  for table in ('pet_exports','jpg_exports'):
   if table in tables and db.execute("SELECT 1 FROM "+table+" WHERE json_extract(payload,'$.brief_id')=? AND state='done'",(bid,)).fetchone():
    return [],set()
  shas={a.get('sha256') for s in p.get('sources',[]) for a in s.get('assets',[]) if a.get('state')=='ready' and a.get('name','').lower().endswith(('.ai','.pdf')) and a.get('sha256')}
  cutoff=0
  if 'artwork_checks' in tables:
   for r in db.execute("SELECT json_extract(payload,'$.asset.sha256'),json_extract(payload,'$.asset.name'),created FROM artwork_checks WHERE brief_id=?",(bid,)):
    cutoff=max(cutoff,float(r[2] or 0))
    if r[0] and str(r[1] or '').lower().endswith(('.ai','.pdf')):shas.add(r[0])
  if not shas:return [],set()
  from hub.source_readiness import code_of
  code=code_of(p)
  out=[];covered_shas=set()
  for table in ('pet_exports','jpg_exports'):
   if table not in tables:continue
   for r in db.execute("SELECT * FROM "+table+" WHERE account=? AND state='done' AND json_extract(payload,'$.source.thread_id')=? ORDER BY created DESC",(account,thread_id)):
    rp=json.loads(r['payload']);sha=((rp.get('source') or {}).get('asset') or {}).get('sha256')
    if sha in shas and rp.get('archive_relative') and _export_covers_code(code,rp):
     d=dict(r);d['kind']=table;d['payload_obj']=rp;d['created']=max(float(r['created'] or 0),cutoff+1);out.append(d);covered_shas.add(sha)
  return out,covered_shas
 except Exception:
  return [],set()

def status(db,p,bid,current=True,source_state='',source_reason=''):
 records=[]
 for table in ('artwork_checks','native_selections','pet_exports','jpg_exports'):
  clause='brief_id=?' if table in ('artwork_checks','native_selections') else "json_extract(payload,'$.brief_id')=?"
  for r in db.execute('SELECT * FROM '+table+' WHERE '+clause,(bid,)):
   d=dict(r);d['kind']=table;d['payload']=json.loads(d['payload']);d['result']=json.loads(d.get('result') or '{}');records.append(d)
 shared,covered_shas=shared_done_exports(db,bid,p)
 if shared:
  records=[r for r in records if not (r['kind'] in ('pet_exports','jpg_exports') and r['state']!='done' and ((r['payload'].get('source') or {}).get('asset') or {}).get('sha256') in covered_shas)]
  for r in shared:
   records.append({k:v for k,v in r.items() if k!='payload_obj'}|{'payload':r['payload_obj'],'result':{}})
 return decide(p,records,current,source_state,source_reason)
def timeline(value):
 idx=next((i for i,(k,_) in enumerate(STAGES) if k==value['stage']),-1)
 return [dict(id=k,label=label,state=('done' if i<idx or value['stage']=='complete' else 'pending' if i!=idx else {'running':'running','queued':'waiting','waiting_sources':'waiting','waiting_staff':'blocked','error':'blocked','ready':'pending'}.get(value['activity'],'pending')),reason=value['reason'] if i==idx else '') for i,(k,label) in enumerate(STAGES)]
