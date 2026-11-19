"""Read-only view of native Hub intake and print pipelines."""
import json,time
from hub.execution_models import get

def snapshot(e):
 from hub.dispatch_control import listing,jobs
 from hub.print_api import overview
 intake={}
 files={'pending':[],'history':[]}
 batches=[];details={};approvals=[]
 with e.store.db() as db:
  for r in db.execute('SELECT * FROM intake_runs WHERE created>=? ORDER BY created DESC LIMIT 20',(time.time()-7*86400,)):
   p=json.loads(r['payload']);result=json.loads(r['result'] or '{}');messages=[]
   for mi,mid in enumerate(p.get('messages',[])):
    src=db.execute('SELECT payload FROM captures WHERE account=? AND thread_id=? AND message_id=? ORDER BY revision DESC LIMIT 1',(r['account'],r['thread_id'],mid)).fetchone()
    if not src:continue
    m=json.loads(src[0]);messages.append({'id':mid,'quoted_file':m.get('quoted_file'),'sender':m.get('sender',''),'role':m.get('origin',''),'text':m.get('text',''),'time':m.get('timestamp'), 'image_urls':['/batch/'+r['id']+'/image/'+str(mi)+'/m/'+str(ii) for ii in range(len(m.get('images',[])))], 'images':len(m.get('images',[])),'files':[{'name':a.get('name',''),'state':a.get('state',''),'path':a.get('relative_path','')} for a in m.get('assets',[])]})
   audit=db.execute('SELECT result FROM intake_route_audit WHERE run_id=?',(r['id'],)).fetchone() if db.execute("SELECT 1 FROM sqlite_master WHERE name='intake_route_audit'").fetchone() else None
   trace=db.execute('SELECT state,trace FROM agent_runs WHERE id=?',(r['id'],)).fetchone() if db.execute("SELECT 1 FROM sqlite_master WHERE name='agent_runs'").fetchone() else None
   batches.append({'id':r['id'],'account':r['account'],'thread_id':r['thread_id'],'group':p.get('group_name',r['thread_id']),'state':r['state'],'created':r['created'],'messages':messages,'analysis':{k:v for k,v in result.items() if k in ('intent','reason','children','decision','missing_fields','image_read')},'classification':json.loads(audit[0]) if audit else {},'agent_trace':json.loads(trace['trace']) if trace else [],'source_ids':p.get('messages',[]),'reason':result.get('reason',''),'orders':[{'id':o.get('id'),'code':o.get('ma_don_hang','')} for o in result.get('orders',[])]})
  for r in db.execute('SELECT a.*,t.display_name FROM print_approvals a LEFT JOIN threads t ON t.account=a.account AND t.thread_id=a.thread_id WHERE a.created>=? ORDER BY a.created DESC LIMIT 30',(time.time()-7*86400,)):
   p=json.loads(r['payload']);deliveries=[]
   for d in db.execute('SELECT account,state,result FROM print_deliveries WHERE approval_id=?',(r['id'],)):
    result=json.loads(d['result'] or '{}');deliveries.append({'account':d['account'],'state':d['state'],'detail':{k:v for k,v in result.items() if k in ('state','error','error_type','client_id','delivery_id','reason')}})
   approvals.append({'id':r['id'],'account':r['account'],'thread_id':r['thread_id'],'group':r['display_name'] or r['thread_id'],'state':r['state'],'created':r['created'],'confirmation_id':r['confirmation_id'],'summary':p.get('notice',p.get('summary','')),'deliveries':deliveries})
  for row in db.execute('SELECT id,account,payload,created FROM design_briefs ORDER BY created DESC LIMIT 30'):
   p=json.loads(row['payload']);steps=jobs(db,row['id']);state=steps[0]['state'] if steps else 'waiting_sources'
   item={'id':row['id'],'title':p.get('brief',{}).get('title',row['id'][:12]),'state':state,'reason':steps[0]['reason'] if steps else 'Chưa có bước đọc/xuất; xem Điều phối file in để đối chiếu nguồn','created':row['created'],'source_ids':[x.get('message_id') for x in p.get('sources',[])],'account':row['account']}
   files['history' if state in ('done','archived','superseded') else 'pending'].append(item)
  for f in files['pending']+files['history'][:40]:
   details[f['id']]=jobs(db,f['id'])
   for step in details[f['id']]:
    if step['kind'] not in ('jpg_exports','pet_exports'):continue
    row=db.execute('SELECT payload FROM '+step['kind']+' WHERE id=?',(step['id'],)).fetchone()
    payload=json.loads(row[0]);step['catalog']=payload.get('catalog',{});step['plan']={k:v for k,v in payload.get('plan',{}).items() if k in ('order_code','renderer','panels','blocked_parts','source_artboard_count')}
    step['blocked_parts']=payload.get('blocked_parts',payload.get('plan',{}).get('blocked_parts',[]))

  if db.execute("SELECT 1 FROM sqlite_master WHERE name='psd_samples'").fetchone():
   for r in db.execute('SELECT * FROM psd_samples ORDER BY created DESC LIMIT 30'):
    p=json.loads(r['payload']);item={'id':r['id'],'title':p.get('title','Lên mẫu PSD'),'account':r['account'],'classification':json.loads(audit[0]) if audit else {},'agent_trace':json.loads(trace['trace']) if trace else [],'source_ids':p.get('messages',[]),'state':r['state'],'created':r['created'],'reason':p.get('reason','')}
    files['history' if r['state']=='done' else 'pending'].append(item)
    details[r['id']]=[{'id':r['id'],'kind':'psd_samples','created':r['created'],'state':r['state'],'reason':p.get('reason',''),'plan':{'request':p.get('request',''),'file':(p.get('asset') or {}).get('name',''),'output':(p.get('report') or {}).get('path','')}}]

 return {'pending_batches':__import__('hub.intake_run_now',fromlist=['pending']).pending(e),'ai_usage':__import__('hub.ai_usage',fromlist=['overview']).overview(e.settings.database,batches,files['pending']+files['history'],details),'prompts':__import__('hub.execution_prompts',fromlist=['overview']).overview(e.settings),'approvals':approvals,'updated':time.time(),'n8n_connected':False,'models':get(e.settings.database),'defaults':{'analysis':e.settings.gemini_model,'vision':e.settings.gemini_model,'redraw':__import__('hub.openai_redraw',fromlist=['MODEL']).MODEL},'wait_minutes':e.intake_management.config['wait_minutes'],'intake':intake,'batches':batches,'files':files,'steps':details,'print_api':overview(e.store)}
