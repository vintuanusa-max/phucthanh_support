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
  if self.config['revision'] and time.time()-self.confirmed>120:return False
  return self.config['channels'].get(channel,False)
 def seconds(self):return self.config['wait_minutes']*60
 def poll(self):
  if time.time()-self.last<20:return
  self.last=time.time();s=self.e.settings
  if not s.erp_url or not s.erp_token:return
  try:
   with httpx.Client(timeout=5,trust_env=False,follow_redirects=False,headers={'X-Zalo-Token':s.erp_token}) as c:
    url=s.erp_url.rstrip('/')+'/api/v1/integrations/zalo/hub-intake'
    r=c.get(url+'/settings');r.raise_for_status();v=r.json()
    if type(v['revision']) is not int or v['revision']<1 or type(v['wait_minutes']) is not int or not 1<=v['wait_minutes']<=120 or set(v['channels'])!=set(DEFAULT['channels']) or any(type(x) is not bool for x in v['channels'].values()):raise ValueError('Invalid intake settings')
    if v['revision']<self.config['revision']:raise ValueError('Stale revision')
    with self.e.store.db() as d:d.execute('INSERT OR REPLACE INTO intake_management VALUES(1,?)',(json.dumps(v),))
    self.config=v;self.confirmed=time.time()
    c.post(url+'/snapshot',json=self.snapshot()).raise_for_status()
  except (httpx.HTTPError,ValueError,KeyError,TypeError):pass
 def snapshot(self):
  items=[];counts={}
  with self.e.store.db() as d:
   for row in d.execute('SELECT state,count(*) AS n FROM intake_runs GROUP BY state'):counts[row['state']]=row['n']
   for r in d.execute('SELECT * FROM intake_runs ORDER BY created DESC LIMIT 120'):
    p=json.loads(r['payload']);res=json.loads(r['result'] or '{}')
    from hub.intake_intent import presentation, evidence
    display,explanation=presentation(d,r,p,res)
    source=evidence(d,r,p); has_image=any(m.get('images') for m in source)
    items.append({'display_group':display,'classification_reason':explanation,'id':r['id'],'kind':'Tin + ảnh' if has_image else 'Tin chữ','account':r['account'],'group':p.get('group_name',r['thread_id']),'state':r['state'],'created':r['created'],'reason':str(res.get('reason',''))[:600],'orders':[{'id':o.get('id'),'code':o.get('ma_don_hang','')} for o in res.get('orders',[])],'paused':not self.enabled(r['account'])})
   for r in d.execute("SELECT o.*,s.account,s.thread_id,COALESCE((SELECT json_extract(c.payload,'$.timestamp') FROM captures c WHERE c.account=s.account AND c.thread_id=s.thread_id AND c.message_id=s.message_id LIMIT 1),0) AS created FROM production_slip_orders o JOIN production_slips s ON s.id=o.id ORDER BY s.rowid DESC LIMIT 80"):
    p=json.loads(r['payload']);res=json.loads(r['result'] or '{}');counts['slip:'+r['state']]=counts.get('slip:'+r['state'],0)+1
    items.append({'id':r['id'],'kind':'Phiếu lệnh','account':r['account'],'group':p.get('body',{}).get('group_name',r['thread_id']),'state':r['state'],'created':r['created'],'reason':str(res.get('reason',p.get('reason','')))[:600],'orders':[{'id':o.get('id'),'code':o.get('ma_don_hang','')} for o in res.get('orders',[])],'paused':not self.enabled(r['account'])})
  return {'revision':self.config['revision'],'items':sorted(items,key=lambda x:x['created'],reverse=True)[:200],'counts':counts}
