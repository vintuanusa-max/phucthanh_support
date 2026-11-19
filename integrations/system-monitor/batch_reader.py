"""Read-only snapshot reader run inside the existing Hub container."""
import json,sqlite3,sys,re
from hub.config import Settings
q=json.load(sys.stdin)
if not re.fullmatch('[a-f0-9]{64}',q.get('batch','')):raise ValueError('Invalid batch')
c=sqlite3.connect('file:'+str(Settings.environment().database)+'?mode=ro',uri=True);c.row_factory=sqlite3.Row
r=c.execute('SELECT payload,state,created FROM n8n_batch_outbox WHERE id=?',(q['batch'],)).fetchone()
if r:
 g=json.loads(r['payload'])['groups'][0]
else:
 r=c.execute('SELECT * FROM intake_runs WHERE id=?',(q['batch'],)).fetchone()
 if not r:raise ValueError('Batch not found')
 p=json.loads(r['payload']);messages=[]
 for mid in p.get('messages',[]):
  src=c.execute('SELECT payload FROM captures WHERE account=? AND thread_id=? AND message_id=? ORDER BY revision DESC LIMIT 1',(r['account'],r['thread_id'],mid)).fetchone()
  if not src:messages.append({'message_id':mid,'text':'Nguồn không còn trong kho','image_ids':[]});continue
  m=json.loads(src[0]);messages.append({**m,'image_ids':m.get('images',[]),'role':m.get('origin','')})
 g={'account':r['account'],'thread_id':r['thread_id'],'group':p.get('group_name',r['thread_id']),'messages':messages}

if q['op']=='view':
 out=[]
 for m in g['messages']:
  row=c.execute('SELECT payload FROM captures WHERE account=? AND thread_id=? AND message_id=? ORDER BY revision LIMIT 1',(g['account'],g['thread_id'],m['message_id'])).fetchone()
  source=json.loads(row[0]) if row else {}
  out.append({**m,'sender':m.get('sender') or source.get('sender') or m.get('role',''),'quoted_text':source.get('quoted_text') if isinstance(source.get('quoted_text'),str) else None})
 print(json.dumps({'id':q['batch'],'group':g.get('group',g['thread_id']),'account':g['account'],'messages':out,'created':r['created'],'state':r['state'],'wait_minutes':g.get('wait_minutes')},ensure_ascii=False))
elif q['op']=='image':
 m=g['messages'][q['message']];mid=m['image_ids'][q['image']]
 r=c.execute('SELECT data FROM media WHERE id=? AND length(data)<=33554432',(mid,)).fetchone()
 if not r:raise ValueError('Image unavailable')
 sys.stdout.buffer.write(r[0])
else:raise ValueError('Unsupported')
