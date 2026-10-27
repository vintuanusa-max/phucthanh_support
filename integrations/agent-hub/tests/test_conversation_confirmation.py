import copy,json
from types import SimpleNamespace
import pytest
from hub.conversation_confirmation import validate,apply
from test_human_batch_requests import engine,add
from test_quantity_confirmation import erp

def fixture(question='Mẫu ABC mình chạy năm trăm nha chị?',answer='Ừ em làm giúp chị',mode='total'):
 q=dict(message_id='q',role='staff',timestamp=10,text=question)
 a=dict(message_id='a',role='customer',timestamp=20,text=answer)
 p=dict(question_id='q',confirmation_id='a',model='ABC',mode=mode,quantity='500',unit='cái',evidence=[dict(message_id='q',quote=question),dict(message_id='a',quote=answer)])
 return dict(history=[q],batch=[a]),dict(status='confirmed',covered_batch_ids=['a'],confirmations=[p])

@pytest.mark.parametrize('answer',['Ừ em làm giúp chị','Chuẩn rồi em nhé','Đúng số đó anh','Chị lấy số đó','Tiến hành giúp anh'])
def test_no_literal_ack_gate(answer):
 c,v=fixture(answer=answer);assert validate(v,c)[0]['quantity']=='500'

@pytest.mark.parametrize('field,value',[('quantity','NaN'),('quantity','-500'),('quantity','1.5'),('mode','guess'),('model','OTHER'),('confirmation_id','fake')])
def test_bad_ai_result_rejected(field,value):
 c,v=fixture();v['confirmations'][0][field]=value
 with pytest.raises(ValueError):validate(v,c)

def test_missing_customer_quote_rejected():
 c,v=fixture();v['confirmations'][0]['evidence'].pop()
 with pytest.raises(ValueError):validate(v,c)

def test_staff_cannot_confirm_own_question():
 c,v=fixture();c['batch'][0]['role']='staff'
 with pytest.raises(ValueError):validate(v,c)

def test_unknown_does_not_drop_source():
 with pytest.raises(ValueError):validate({'status':'unclear','reason':'500 hay600, khách chỉ trả lời ừ'}, {})

@pytest.mark.parametrize('mode',['total','additional'])
def test_semantic_pipeline_cache_and_no_write(tmp_path,monkeypatch,mode):
 import hub.conversation_confirmation as module
 s,e=engine(tmp_path);question='Mẫu ABC mình chạy năm trăm nha chị?';answer='Ừ em làm giúp chị'
 for mid,text,origin,age in [('q',question,'staff',900),('a',answer,'customer',800)]:
  i,m=add(s,mid,age,origin);m['text']=text
  with s.db() as d:d.execute('UPDATE captures SET payload=? WHERE id=?',(json.dumps(m),i))
  if mid=='a':raw=m
 _,v=fixture(question,answer,mode);calls=[]
 monkeypatch.setattr(module,'ask',lambda *args:(calls.append(1) or copy.deepcopy(v)))
 e.customer_mappings=SimpleNamespace(get=lambda *a:{'customer_id':'c'});e.erp=erp([])
 run=dict(id='r',account='wa-1',thread_id='g123')
 for _ in range(2):
  derived=dict(raw);assert apply(e.order_intake,run,[derived]) is False
  assert ('In thêm 500' if mode=='additional' else 'tổng số lượng in 500') in derived['text']
 assert len(calls)==1 and raw['text']==answer
