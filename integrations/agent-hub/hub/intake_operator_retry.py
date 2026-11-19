"""Explicit operator retry of untouched pre-Agent failures; durable single claim."""
import json,time

def poll(intake):
 from hub.intake_schema_resume import poll as schema_resume
 if schema_resume(intake):return True
 with intake.store.db() as db:
  db.execute('CREATE TABLE IF NOT EXISTS intake_operator_retry(run_id TEXT PRIMARY KEY,state TEXT,requested REAL,result TEXT)')
  q=db.execute("SELECT * FROM intake_operator_retry WHERE state='queued' ORDER BY requested LIMIT 1").fetchone()
  if not q:return False
  r=db.execute('SELECT * FROM intake_runs WHERE id=?',(q['run_id'],)).fetchone()
  if not r:return False
  run=dict(r);payload=json.loads(r['payload']);reason=''
  if r['state']!='review' or payload.get('submitted_payload'):reason='Đã có trạng thái/khóa ERP; cần đối soát, không retry'
  from hub.execution_models import get
  revision=get(intake.engine.settings.database)['revision']
  db.execute('CREATE TABLE IF NOT EXISTS agent_revision_attempts(run_id TEXT,revision INTEGER,payload TEXT,created REAL,PRIMARY KEY(run_id,revision))')
  old=db.execute('SELECT * FROM agent_runs WHERE id=?',(r['id'],)).fetchone()
  archive=False
  resume=None
  if payload.get('proposal_parent') and payload.get('verified_proposal_id'):
   from hub.agent_order_tasks import saved_proposal
   parent=db.execute('SELECT account,thread_id FROM intake_runs WHERE id=?',(payload['proposal_parent'],)).fetchone()
   candidate=saved_proposal(db,payload['proposal_parent'],payload['verified_proposal_id'])
   if parent and parent['account']==r['account'] and parent['thread_id']==r['thread_id'] and candidate and set(candidate['source_message_ids'])==set(payload['messages']):
    actions=db.execute('SELECT tool,state,result FROM agent_actions WHERE run_id=?',(r['id'],)).fetchall()
    if all(a['tool']=='request_customer_clarification' and a['state']=='done' and json.loads(a['result'] or '{}').get('state')=='silent_by_policy' for a in actions):resume=candidate
  if old and resume is None:
   actions=db.execute('SELECT tool,state,result FROM agent_actions WHERE run_id=?',(r['id'],)).fetchall()
   safe=(old['state']=='completed' or (old['state']=='review' and all(set(t)=={'error'} and (t['error']=='KeyError; kiểm tra log nội bộ' or t['error'].startswith('ValueError: GEMINI_EMPTY_CONTENT:')) for t in json.loads(old['trace'] or '[]')))) and bool(actions) and all(a['tool']=='request_customer_clarification' and a['state']=='done' and json.loads(a['result'] or '{}').get('state')=='silent_by_policy' for a in actions)
   # An operator may retry a newly recovered exact file reference, never a prior write.
   recovered=any(json.loads(x[0]).get('quoted_file',{}).get('resolved') for mid in payload.get('messages',[]) for x in db.execute('SELECT payload FROM captures WHERE account=? AND thread_id=? AND message_id=?',(r['account'],r['thread_id'],mid)) if json.loads(x[0]).get('quoted_file'))
   if recovered and old['state']=='completed' and actions and all(a['state']=='done' and a['tool'] in ('request_customer_clarification','escalate_to_human') and json.loads(a['result'] or '{}').get('state') in ('silent_by_policy','reconsider_order','human_review') for a in actions):safe=True
   db.execute('CREATE TABLE IF NOT EXISTS agent_attempt_archive(run_id TEXT PRIMARY KEY,payload TEXT,created REAL)')
   proposal=db.execute('SELECT payload FROM agent_proposals WHERE run_id=?',(r['id'],)).fetchall()
   if old['state']=='completed' and len(proposal)==1 and all(a['state']=='done' and (a['tool']=='propose_order_draft' and json.loads(a['result'] or '{}').get('state')=='proposed' or a['tool'] in ('request_customer_clarification','escalate_to_human') and json.loads(a['result'] or '{}').get('state') in ('silent_by_policy','reconsider_order','human_review')) for a in actions):
    resume=json.loads(proposal[0]['payload'])
   elif not safe or db.execute('SELECT 1 FROM agent_proposals WHERE run_id=?',(r['id'],)).fetchone() or db.execute('SELECT 1 FROM agent_revision_attempts WHERE run_id=? AND revision=?',(r['id'],revision)).fetchone():reason='Agent đã chạy; cần đối soát, không replay tác động'
   else:archive=True
  if payload.get('request_id') and (resume is None or payload['request_id'] not in ('chatwoot-id:'+r['id'],'chatwoot-intake:'+r['id'])):reason='Khóa ERP không thuộc đề xuất đã kiểm chứng; không retry'
  batch=[]
  from hub.intake_lifecycle import reusable
  for mid in payload['messages']:
   src=db.execute('SELECT id,payload FROM captures WHERE account=? AND thread_id=? AND message_id=? ORDER BY revision DESC LIMIT 1',(r['account'],r['thread_id'],mid)).fetchone()
   if not src:reason='Thiếu nguồn';break
   if not reusable(db,{'payload':src['payload'],'source_result':'{}'}):reason='Nguồn đã xử lý ERP/chưa rõ kết quả';break
   batch.append((src['id'],json.loads(src['payload'])))
  if reason:
   db.execute("UPDATE intake_operator_retry SET state='blocked',result=? WHERE run_id=?",(reason,r['id']));return True
  if not db.execute("UPDATE intake_operator_retry SET state='running' WHERE run_id=? AND state='queued'",(r['id'],)).rowcount:return False
  if archive:
   db.execute('INSERT INTO agent_revision_attempts VALUES(?,?,?,?)',(r['id'],revision,json.dumps(dict(old),ensure_ascii=False),time.time()))
   db.execute('DELETE FROM agent_runs WHERE id=?',(r['id'],))  # Action idempotency ledger remains untouched.
  payload['unified_intake']=True
  db.execute('UPDATE intake_runs SET payload=? WHERE id=?',(json.dumps(payload,ensure_ascii=False),r['id']))
 try:
  if resume is not None:
   from hub.agent_loop import Draft
   from hub.models import IntakeDecision
   draft=Draft.model_validate(resume)
   ids=[n for n,(_,msg) in enumerate(batch,1) if msg['message_id'] in draft.source_message_ids]
   intake.analyze(run,payload,batch,agent_decision=IntakeDecision(action='draft_order',source_message_ids=ids,orders=draft.items))
  else:
   intake.analyze(run,payload,batch)
  result='Đã chạy qua luồng intake; xem kết quả hồ sơ'
 except Exception as exc:
  from hub.intake_errors import detail
  result=detail(exc);intake.state(r['id'],'review',{'reason':result});intake.notify(run,result)
 with intake.store.db() as db:db.execute("UPDATE intake_operator_retry SET state='done',result=? WHERE run_id=?",(result,r['id']))
 return True
