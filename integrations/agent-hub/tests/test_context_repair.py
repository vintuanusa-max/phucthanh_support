import pytest
from hub.context_gate import IntentDecision,classify_validated
from hub.intake_errors import detail

def decision(evidence):return IntentDecision(intent='new_order',source_message_ids=['m'],reason='50 sản phẩm 2 vị trí',evidence=evidence)
CTX={'batch':[{'message_id':'m','text':'50 in 2 vt'}],'history':[],'candidates':[]}
def test_visual_quote_repaired_once(monkeypatch):
 import hub.context_gate as gate
 responses=iter([decision(['50 in 2 vt','TỔNG 50']),decision(['50 in 2 vt'])]);calls=[]
 monkeypatch.setattr(gate,'classify',lambda s,c,i:(calls.append(c) or next(responses)))
 assert classify_validated(None,CTX,[]).evidence==['50 in 2 vt']
 assert len(calls)==2 and 'validation_feedback' in calls[1] and 'validation_feedback' not in CTX
def test_repair_cannot_bypass_validation(monkeypatch):
 import hub.context_gate as gate
 calls=[];monkeypatch.setattr(gate,'classify',lambda *a:(calls.append(1) or decision(['TỔNG 50'])))
 with pytest.raises(ValueError):classify_validated(None,CTX,[])
 assert len(calls)==2
def test_error_redacts_credentials():
 assert 'abc123' not in detail(ValueError('token=abc123'))
 assert 'Context quote' in detail(ValueError('Context quote does not match source'))

def test_supplement_other_sender_keeps_uncommitted_sources(tmp_path):
 import time,json
 from test_human_batch_requests import engine,add
 s,e=engine(tmp_path);old_id,old=add(s,'old',1000);new_id,new=add(s,'new',650)
 new['sender']='Another customer';new['sender_id']='another'
 p=dict(messages=['old'],group_name='Test group',sender=old['sender'],sender_key=old.get('sender_id'),first_timestamp=old['timestamp'],last_timestamp=old['timestamp'])
 with s.db() as d:
  d.execute('UPDATE captures SET payload=? WHERE id=?',(json.dumps(new),new_id))
  d.execute('INSERT INTO intake_runs VALUES(?,?,?,?,?,?,?,?)',('oldrun','wa-1','g123',10,'waiting_details',json.dumps(p),'{}',time.time()-1000))
  d.execute('INSERT INTO intake_sources VALUES(?,?)',(old_id,'oldrun'))
 seen=[];e.order_intake.analyze=lambda r,p,b,**kw:seen.extend(m['message_id'] for _,m in b)
 e.order_intake.poll()
 assert seen==['old','new'] and not e.erp.calls
