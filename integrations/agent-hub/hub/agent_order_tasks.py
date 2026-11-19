"""Dispatch verified ERP proposals independently; never replay an existing child."""
import hashlib,json,time


def saved_proposal(db,parent,pid):
 row=db.execute('SELECT payload FROM agent_proposals WHERE id=? AND run_id=?',(pid,parent)).fetchone()
 if not row:return None
 actions=db.execute("SELECT result FROM agent_actions WHERE run_id=? AND tool='propose_order_draft' AND state='done'",(parent,)).fetchall()
 if not any(json.loads(a[0]).get('proposal_id')==pid and json.loads(a[0]).get('state')=='proposed' for a in actions):return None
 return json.loads(row[0])


def verified_child(db,run,payload,messages,orders):
 parent=payload.get('proposal_parent');pid=payload.get('verified_proposal_id')
 if not parent or not pid:return False
 original=db.execute('SELECT account,thread_id,payload FROM intake_runs WHERE id=?',(parent,)).fetchone()
 if not original or (original['account'],original['thread_id'])!=(run['account'],run['thread_id']):return False
 draft=saved_proposal(db,parent,pid)
 if not draft:return False
 ids=[m['message_id'] for m in messages]
 parent_payload=json.loads(original['payload'])
 expected=[dict(x) for x in draft['items']]
 actual=[dict(x) for x in orders]
 if parent_payload.get('individual_slip_rules')==2:
  from types import SimpleNamespace
  from hub.single_slip_policy import normalize_product
  for item in expected+actual:
   line=SimpleNamespace(**item)
   normalize_product(line)
   item.update(vars(line))
 return (set(ids)==set(draft['source_message_ids']) and set(ids)<=set(parent_payload['messages']) and [{**x,'ten_don_hang':x.get('ten_don_hang')} for x in actual]==[{**x,'ten_don_hang':x.get('ten_don_hang')} for x in expected])


def dispatch(intake,run,messages):
 from hub.agent_loop import Draft
 from hub.models import IntakeDecision
 from hub.intake_lifecycle import reusable
 from hub.order_policy import allowed
 with intake.store.db() as db:
  parent=db.execute('SELECT * FROM intake_runs WHERE id=?',(run['id'],)).fetchone()
  payload=json.loads(parent['payload'])
  rows=db.execute('SELECT id,payload FROM agent_proposals WHERE run_id=? ORDER BY created,id',(run['id'],)).fetchall()
 if not (intake.agent_loop.scope(run) or {}).get('auto_order'):return []
 if not allowed(intake.policy(run['account']),intake.engine.settings.inboxes[run['account']]['channel'],payload['group_name']):return []
 proposals=[(r['id'],Draft.model_validate_json(r['payload'])) for r in rows]
 results=[]
 for pid,draft in proposals:
  identity=hashlib.sha256(('verified-proposal-intake:'+run['id']+':'+pid).encode()).hexdigest()
  selected=[m for m in messages if m['message_id'] in draft.source_message_ids]
  child=dict(run,id=identity)
  with intake.store.db() as db:
   db.execute('BEGIN IMMEDIATE')
   existing=db.execute('SELECT state FROM intake_runs WHERE id=?',(identity,)).fetchone()
   if existing:
    results.append({'run_id':identity,'state':existing['state']});continue
   if not saved_proposal(db,run['id'],pid):continue
   if set(m['message_id'] for m in selected)!=set(draft.source_message_ids):continue
   if any(set(draft.source_message_ids)&set(other.source_message_ids) for oid,other in proposals if oid!=pid):
    results.append({'proposal_id':pid,'state':'review','reason':'Các đề xuất dùng chung nguồn; cần đối chiếu trước khi tách đơn'});continue
   if any(not reusable(db,{'payload':json.dumps(m),'source_result':'{}'}) for m in selected):
    results.append({'proposal_id':pid,'state':'blocked','reason':'Nguồn đã ghi ERP/đang gửi/chưa rõ kết quả'});continue
   cp={k:payload[k] for k in ('group_name','sender','sender_key','collection_scope','last_timestamp','manual_quiet_until') if k in payload}
   cp.update(messages=[m['message_id'] for m in selected],first_timestamp=min(m['timestamp'] for m in selected),unified_intake=True,model_parent=payload.get('model_parent',run['id']),proposal_parent=run['id'],verified_proposal_id=pid)
   db.execute("INSERT INTO intake_runs(id,account,thread_id,conversation,state,payload,created) VALUES(?,?,?,?,'analyzing',?,?)",(identity,run['account'],run['thread_id'],run['conversation'],json.dumps(cp,ensure_ascii=False),time.time()))
  try:
   intake.analyze(child,cp,[(m['message_id'],m) for m in selected],agent_decision=IntakeDecision(action='draft_order',source_message_ids=list(range(1,len(selected)+1)),orders=draft.items))
  except Exception as exc:
   from hub.intake_errors import detail
   intake.state(identity,'review',{'reason':detail(exc),'proposal_parent':run['id']})
  with intake.store.db() as db:
   state=db.execute('SELECT state FROM intake_runs WHERE id=?',(identity,)).fetchone()['state']
  results.append({'run_id':identity,'proposal_id':pid,'state':state})
 with intake.store.db() as db:
  row=db.execute('SELECT result FROM intake_runs WHERE id=?',(run['id'],)).fetchone()
  result=json.loads(row[0] or '{}');result['independent_orders']=results
  db.execute('UPDATE intake_runs SET result=? WHERE id=?',(json.dumps(result,ensure_ascii=False),run['id']))
 return results
