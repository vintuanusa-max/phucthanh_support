"""Read-only aggregate executed inside Hub. Input is the operational day's boundaries."""
import json, sqlite3, sys
from hub.config import Settings
start,end=map(float,sys.argv[1:3])
db=sqlite3.connect("file:"+Settings.environment().database+"?mode=ro",uri=True,timeout=3)
counts={}; active={}; events=[]
def collect(node,table,col="created",clause="1",unit="hồ sơ",expr="id"):
    q=f"select {expr},{col} from {table} where {col}>=? and {col}<? and ({clause})"
    rows=db.execute(q,(start,end)).fetchall()
    counts[node]={"n":len(rows),"unit":unit}
    for _,ts in rows:events.append([int(ts),node])
def running(node,table,state):
    active[node]=db.execute(f"select count(*) from {table} where state=?",(state,)).fetchone()[0]
collect("source","intake_runs",unit="hồ sơ tiếp nhận theo ngày tạo (gồm hồ sơ con)")
collect("agent","intake_ai_calls","started","state <> 'cache_hit'",unit="lượt gọi AI tiếp nhận theo giờ bắt đầu, gồm lượt lỗi")
vision=db.execute("""select id,min(ts) from (
 select id,created ts from intake_runs where created>=? and created<? and json_valid(result) and json_extract(result,'$.image_read')=1
 union all select parent_id,created from individual_slip_tasks where created>=? and created<? and state not in ('classifying','queued') and result is not null
) group by id""",(start,end,start,end)).fetchall()
counts['vision']=dict(n=len(vision),unit='hồ sơ có dấu vết đọc ảnh hoặc kết quả phân loại phiếu trong ngày')
events.extend([int(ts),'vision'] for _,ts in vision)
collect("pet_restore","jobs",clause="kind='raster_pet'",unit="việc xử lý ảnh PET tạo trong ngày")
orders=db.execute("""select json_extract(o.value,'$.id'),min(r.created) from intake_runs r,
 json_each(r.result,'$.orders') o where r.created>=? and r.created<? and json_extract(o.value,'$.id') is not null
 group by json_extract(o.value,'$.id')""",(start,end)).fetchall()
counts['erp']=dict(n=len(orders),unit="đơn ERP phân biệt có biên nhận trong hồ sơ tạo hôm nay")
events.extend([int(ts),'erp'] for _,ts in orders)
collect("no_action","intake_runs",clause="state='ignored'",unit="cụm kết thúc")
collect("match","artwork_checks",unit="hồ sơ kiểm nguồn")
for node,table in [('jpg','jpg_exports'),('psd','psd_samples'),('pet','pet_exports')]:
    collect(node,table,unit="hồ sơ xuất tạo hôm nay, mọi trạng thái");running(node,table,'exporting')
preview={}
for table,field in [('pet_exports','chatwoot_message_id'),('jpg_exports','message_id'),('psd_samples','message_id')]:
    for conv,mid,ts in db.execute(f"""select json_extract(payload,'$.conversation'),json_extract(payload,'$.{field}'),created from {table}
        where created>=? and created<? and json_extract(payload,'$.{field}')>0""",(start,end)):
        preview[mid]=ts
counts['preview']=dict(n=len(preview),unit="tin preview Chatwoot có ID của hồ sơ xuất tạo hôm nay")
events.extend([int(ts),'preview'] for ts in preview.values())
collect("approve","print_approvals",unit="hồ sơ duyệt")
running("agent","agent_runs","running")
# A work item may contain multiple units of the same construction; count the job once.
def terms(obj):
    if isinstance(obj,dict):
        for v in obj.values():yield from terms(v)
    elif isinstance(obj,list):
        for v in obj:yield from terms(v)
    elif isinstance(obj,str):yield obj
kinds=set('single_face separate_faces joined_faces solid_meter pattern_meter ready_layout unknown'.split())
for kind in kinds:counts[kind]=dict(n=0,unit="hồ sơ JPG có phân loại")
for ts,raw in db.execute("select created,payload from jpg_exports where created>=? and created<?",(start,end)):
    catalog=json.loads(raw).get("catalog") or {}
    for k in kinds.intersection(part.get('kind') for m in catalog.get('models',[]) for part in m.get('parts',[]) if isinstance(part,dict)):
        counts[k]['n']+=1;events.append([int(ts),k])
# Handoffs grouped by the timestamp of the linked approval; delivery has no clock.
for (ts,) in db.execute("select a.created from print_deliveries d join print_approvals a on a.id=d.approval_id where a.created>=? and a.created<? and d.state in ('submitted','confirmed','uncertain')",(start,end)):
    events.append([int(ts),'send'])
counts['send']=dict(n=sum(node=='send' for _,node in events),unit='lượt bàn giao theo ngày duyệt')
# Read stored result fields only; never schedule work from this view.
details=[]
for table in ('jpg_exports','pet_exports','psd_samples'):
    thread="x.thread_id" if table=="psd_samples" else "b.thread_id"
    refs="json_extract(x.payload,'$.messages')" if table=="psd_samples" else "(select json_group_array(json_extract(j.value,'$.message_id')) from json_each(b.payload,'$.sources') j)"
    query=f"""select x.id,x.account,{thread},b.run_id,{refs},x.state,
      coalesce(json_extract(x.payload,'$.review_reason'),json_extract(x.payload,'$.reason')),
      json_extract(x.payload,'$.archive_relative'),coalesce(json_extract(x.payload,'$.chatwoot_message_id'),json_extract(x.payload,'$.message_id')),
      coalesce(json_extract(x.payload,'$.conversation'),b.conversation),
      json_extract(x.payload,'$.report.ai_file'),
      (select json_group_array(json_extract(value,'$.file')) from json_each(x.payload,'$.report.panels')),
      (select json_group_array(json_extract(value,'$.name')) from json_each(x.payload,'$.files') where type='object'),
      (select json_group_array(json_extract(value,'$.name')) from json_each(x.payload,'$.reports') where type='object'),
      json_extract(x.payload,'$.brief_id') from {table} x left join design_briefs b on b.id=json_extract(x.payload,'$.brief_id')"""
    for ident,account,thread_id,run,refs,state,reason,folder,mid,conv,ai,jpg,png,tif,brief in db.execute(query):
        names=[n for n in [ai]+json.loads(jpg)+json.loads(png)+json.loads(tif) if n]
        details.append(dict(id=ident,kind=table,run=run,account=account,thread=thread_id,sources=json.loads(refs or '[]'),state=state,reason=reason,folder=folder,names=names,preview=mid,conversation=conv,brief=brief))
exported={entry['id'] for entry in details}
for ident,brief,account,thread,run,refs,state,errors in db.execute("""select a.id,b.id,b.account,b.thread_id,b.run_id,
 (select json_group_array(json_extract(value,'$.message_id')) from json_each(b.payload,'$.sources')),
 a.state,json_extract(a.result,'$.errors') from artwork_checks a join design_briefs b on b.id=a.brief_id where a.state='review'"""):
    if ident not in exported:
        details.append(dict(id=ident,brief=brief,account=account,thread=thread,run=run,sources=json.loads(refs or '[]'),kind='Kiểm tra nguồn',state=state,reason=' · '.join(map(str,json.loads(errors or '[]'))),names=[]))
children={}
for parent,state,reason,orders in db.execute("""select json_extract(payload,'$.proposal_parent'), state,json_extract(result,'$.reason'),json_extract(result,'$.orders')
 from intake_runs where json_extract(payload,'$.proposal_parent') is not null"""):
    children.setdefault(parent,[]).append(dict(state=state,reason=reason,orders=json.loads(orders or '[]')))
print(json.dumps(dict(counts=counts,active=active,events=events,details=details,children=children,cw_account=Settings.environment().cw_account)))
