"""Operator-only resume of proven pre-side-effect Draft schema rejection."""
import json,time

def poll(intake):
 with intake.store.db() as db:
  if not db.execute("SELECT 1 FROM sqlite_master WHERE name='intake_operator_retry'").fetchone():return False
  q=db.execute("SELECT * FROM intake_operator_retry WHERE state='schema_queued' LIMIT 1").fetchone()
  if not q:return False
  r=db.execute('SELECT * FROM intake_runs WHERE id=?',(q['run_id'],)).fetchone()
  actions=db.execute('SELECT * FROM agent_actions WHERE run_id=?',(q['run_id'],)).fetchall()
  p=json.loads(r['payload']) if r else {}
  safe=bool(r and r['state']=='review' and not p.get('request_id') and not p.get('submitted_payload') and len(actions)==1 and actions[0]['tool']=='propose_order_draft' and actions[0]['state']=='uncertain' and json.loads(actions[0]['result'] or '{}').get('error')=='Schema AI: items.0.ghi_chu_mau_do: string_type; reason: extra_forbidden' and not db.execute('SELECT 1 FROM agent_proposals WHERE run_id=?',(r['id'],)).fetchone())
  if not safe:
   db.execute("UPDATE intake_operator_retry SET state='blocked',result='Not a proven pre-effect schema failure' WHERE run_id=?",(q['run_id'],));return True
  batch=[]
  from hub.intake_lifecycle import reusable
  for mid in p['messages']:
   src=db.execute('SELECT id,payload FROM captures WHERE account=? AND thread_id=? AND message_id=? ORDER BY revision DESC LIMIT 1',(r['account'],r['thread_id'],mid)).fetchone()
   if not src or not reusable(db,{'payload':src['payload'],'source_result':'{}'}):raise ValueError('Source already used or missing')
   batch.append((src['id'],json.loads(src['payload'])))
  if not db.execute("UPDATE intake_operator_retry SET state='running' WHERE run_id=? AND state='schema_queued'",(r['id'],)).rowcount:return False
  run=dict(r);action=dict(actions[0])
 try:
  context=intake.context_gate.build(run,[m for _,m in batch]);context['verification_images']=[im for _,m in batch for im in intake.store.images(m.get('images',[]))]
  result=intake.agent_loop.execute(run,'propose_order_draft',json.loads(action['args']),context)
  with intake.store.db() as db:
   db.execute("UPDATE agent_actions SET state='done',result=? WHERE id=?",(json.dumps(result),action['id']))
   db.execute("UPDATE agent_runs SET state='completed',trace=?,updated=? WHERE id=?",(json.dumps([{'tool':'propose_order_draft','result':result,'resume':'pre_effect_schema'}]),time.time(),run['id']))
   saved=db.execute('SELECT payload FROM agent_proposals WHERE run_id=?',(run['id'],)).fetchone()
  from hub.agent_loop import Draft
  from hub.models import IntakeDecision
  draft=Draft.model_validate_json(saved[0]);ids=[n for n,(_,m) in enumerate(batch,1) if m['message_id'] in draft.source_message_ids]
  intake.analyze(run,p,batch,agent_decision=IntakeDecision(action='draft_order',source_message_ids=ids,orders=draft.items))
  outcome='Resumed saved AI arguments through verifier; no new analysis'
 except Exception as exc:
  from hub.intake_errors import detail
  outcome=detail(exc);intake.state(run['id'],'review',{'reason':outcome})
 with intake.store.db() as db:db.execute("UPDATE intake_operator_retry SET state='done',result=? WHERE run_id=?",(outcome,run['id']))
 return True
