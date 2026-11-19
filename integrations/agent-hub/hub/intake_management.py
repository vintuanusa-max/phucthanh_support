"""Read-only status + versioned ERP controls. Never creates/replays orders."""
import json,time,httpx
DEFAULT={'revision':0,'wait_minutes':30,'channels':{'zalo':True,'whatsapp':True,'viber':True}}
class IntakeManagement:
 def __init__(self,e):
  self.e=e;self.last=0;self.confirmed=0
  with e.store.db() as d:
   d.execute('CREATE TABLE IF NOT EXISTS intake_management(id INTEGER PRIMARY KEY,payload TEXT NOT NULL)')
   r=d.execute('SELECT payload FROM intake_management WHERE id=1').fetchone()
  self.config=json.loads(r[0]) if r else dict(DEFAULT)
 def enabled(self,account):
  channel=self.e.settings.inboxes.get(account,{}).get('channel','')
  # Before ERP feature installation retain existing behavior; afterwards fail closed on stale config.
  # Hub local configuration is authoritative; no ERP session dependency.
  return self.config['channels'].get(channel,False)
 def seconds(self):return self.config['wait_minutes']*60
 def poll(self):
  return
 def update(self,v):
  if set(v)!={'revision','wait_minutes','channels'} or type(v['revision']) is not int or type(v['wait_minutes']) is not int or not 1<=v['wait_minutes']<=120 or set(v['channels'])!=set(DEFAULT['channels']) or any(type(x) is not bool for x in v['channels'].values()):raise ValueError('Cấu hình không hợp lệ')
  with self.e.lock,self.e.store.db() as d:
   d.execute('BEGIN IMMEDIATE')
   row=d.execute('SELECT payload FROM intake_management WHERE id=1').fetchone()
   old=json.loads(row[0]) if row else dict(DEFAULT)
   if v['revision']!=old['revision']:raise ValueError('Cấu hình đã thay đổi; tải lại trước khi lưu')
   data=dict(v,revision=old['revision']+1)
   d.execute('CREATE TABLE IF NOT EXISTS intake_management_audit(created REAL,payload TEXT)')
   d.execute('INSERT INTO intake_management_audit VALUES(?,?)',(time.time(),json.dumps(data)))
   d.execute('INSERT OR REPLACE INTO intake_management VALUES(1,?)',(json.dumps(data),))
   self.config=data
  return {'settings':data}
 def snapshot(self):
  from datetime import datetime,timedelta,timezone
  cutoff=(datetime.now(timezone(timedelta(hours=7))).replace(hour=0,minute=0,second=0,microsecond=0)-timedelta(days=6)).timestamp()
  items=[];counts={}
  with self.e.store.db() as d:
   for row in d.execute('SELECT state,count(*) AS n FROM intake_runs WHERE created>=? GROUP BY state',(cutoff,)):counts[row['state']]=row['n']
   for r in d.execute('SELECT * FROM intake_runs WHERE created>=? ORDER BY created DESC',(cutoff,)):
    p=json.loads(r['payload']);res=json.loads(r['result'] or '{}')
    from hub.intake_intent import presentation, evidence
    display,explanation=presentation(d,r,p,res)
    source=evidence(d,r,p); has_image=any(m.get('images') for m in source)
    from hub.intake_diagnostics import describe
    diagnostics=describe(r,p,res,source,self.seconds())
    items.append({'display_group':display,'classification_reason':explanation,'id':r['id'],'thread_id':r['thread_id'],'first_timestamp':p.get('first_timestamp',r['created']),'last_timestamp':p.get('last_timestamp',r['created']),'kind':'Tin + ảnh' if has_image else 'Tin chữ','account':r['account'],'group':p.get('group_name',r['thread_id']),'state':r['state'],'created':r['created'],'reason':str(res.get('reason',''))[:600],'orders':[{'id':o.get('id'),'code':o.get('ma_don_hang','')} for o in res.get('orders',[])],'paused':not self.enabled(r['account']),'diagnostics':diagnostics})
   for r in d.execute("SELECT o.*,s.account,s.thread_id,COALESCE((SELECT json_extract(c.payload,'$.timestamp') FROM captures c WHERE c.account=s.account AND c.thread_id=s.thread_id AND c.message_id=s.message_id LIMIT 1),0) AS created FROM production_slip_orders o JOIN production_slips s ON s.id=o.id WHERE COALESCE((SELECT json_extract(c.payload,'$.timestamp') FROM captures c WHERE c.account=s.account AND c.thread_id=s.thread_id AND c.message_id=s.message_id LIMIT 1),0)>=? ORDER BY s.rowid DESC",(cutoff,)):
    p=json.loads(r['payload']);res=json.loads(r['result'] or '{}');counts['slip:'+r['state']]=counts.get('slip:'+r['state'],0)+1
    items.append({'id':r['id'],'kind':'Phiếu lệnh','account':r['account'],'group':p.get('body',{}).get('group_name',r['thread_id']),'state':r['state'],'created':r['created'],'reason':str(res.get('reason',p.get('reason','')))[:600],'orders':[{'id':o.get('id'),'code':o.get('ma_don_hang','')} for o in res.get('orders',[])],'paused':not self.enabled(r['account'])})
  from hub.intake_batches import grouped
  return {'revision':self.config['revision'],'items':grouped(items,self.seconds()),'counts':counts}
