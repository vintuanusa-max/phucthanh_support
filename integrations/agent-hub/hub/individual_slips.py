"""Primary-sender slips: one image per independent, idempotent ERP task."""
import hashlib,json,time

def run(intake,parent,messages):
 policy=intake.policy(parent['account']) or {}
 from hub.canavi_slip_policy import selected as select_slips
 selected=[m for m in select_slips(policy,parent,messages) if intake.accepts(m)]
 if not selected:return False
 if sum(len(m["images"]) for m in selected)>30:
  intake.state(parent["id"],"review",{"reason":"Cụm vượt 30 ảnh; cần tách cụm"});return True
 from hub.production_slips import classify
 from hub.intake_lifecycle import reusable
 results=[]
 with intake.store.db() as db:
  db.execute('CREATE TABLE IF NOT EXISTS individual_slip_tasks(id TEXT PRIMARY KEY,parent_id TEXT,message_id TEXT,state TEXT,result TEXT,created REAL)')
  payload=json.loads(db.execute('SELECT payload FROM intake_runs WHERE id=?',(parent['id'],)).fetchone()[0])
 for m in selected:
  identity=hashlib.sha256(json.dumps(['individual-slip-v1',parent['account'],parent['thread_id'],m['message_id'],m.get('revision',0)]).encode()).hexdigest()
  with intake.store.db() as db:
   old=db.execute('SELECT state,result FROM individual_slip_tasks WHERE id=?',(identity,)).fetchone()
   if old:
    results.append({'run_id':identity,'message_id':m['message_id'],'state':old['state']});continue
   if not reusable(db,{'payload':json.dumps(m),'source_result':'{}'}):
    results.append({'message_id':m['message_id'],'state':'source_consumed'});continue
   db.execute("INSERT INTO individual_slip_tasks VALUES(?,?,?,'classifying','{}',?)",(identity,parent['id'],m['message_id'],time.time()))
  try:
   images=intake.store.images(m['images'])
   if len(images)!=1:raise ValueError('Một tin chứa nhiều ảnh; cần tách nguồn trước khi lập phiếu')
   verdict=classify(intake.engine.settings,images[0])
   if not verdict['accepted']:
    state='not_slip';detail=verdict
   else:
    cp={k:payload[k] for k in ('group_name','sender','sender_key','collection_scope','last_timestamp') if k in payload}
    cp.update(messages=[m['message_id']],first_timestamp=m['timestamp'],unified_intake=True,model_parent=parent['id'],individual_slip=True,individual_slip_rules=2)
    with intake.store.db() as db:
     db.execute("INSERT OR IGNORE INTO intake_runs(id,account,thread_id,conversation,state,payload,created) VALUES(?,?,?,?,'analyzing',?,?)",(identity,parent['account'],parent['thread_id'],parent['conversation'],json.dumps(cp,ensure_ascii=False),time.time()))
    child=dict(parent,id=identity)
    # Only this slip is supplied to the order agent; no maket/file prerequisite.
    intake.agent_loop.run(child,[m],staff_images_checked=True)
    with intake.store.db() as db:
     r=db.execute('SELECT state,result FROM intake_runs WHERE id=?',(identity,)).fetchone()
    detail=json.loads(r['result']);state=r['state']
  except Exception as exc:
   from hub.intake_errors import detail as error_detail
   state='review';detail={'reason':error_detail(exc)}
  with intake.store.db() as db:
   db.execute('UPDATE individual_slip_tasks SET state=?,result=? WHERE id=?',(state,json.dumps(detail,ensure_ascii=False),identity))
  results.append({'run_id':identity,'message_id':m['message_id'],'state':state,'result':detail})
 intake.state(parent['id'],'review',{'reason':'Đã tách từng ảnh: phiếu lên ERP độc lập; maket giữ cho luồng file','individual_slips':results})
 return True
