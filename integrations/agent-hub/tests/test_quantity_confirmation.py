from types import SimpleNamespace
import pytest
from hub.quantity_confirmation import pair,reconcile

def msg(text,origin='staff',stamp=10,mid='q'):
 return dict(text=text,origin=origin,timestamp=stamp,message_id=mid,sender=origin)

def test_exact_pair():
 p=pair(msg('ok','customer',20,'a'),[msg('Mẫu TDVB-SEE.10 in 500 phải ko?')])
 assert p['quantity']=='500' and p['model']=='TDVB-SEE.10' and p['question_id']=='q'

@pytest.mark.parametrize('text',['ok nhưng 300 thôi','chưa ok','không','ok in thêm 200'])
def test_not_plain_assent(text):assert pair(msg(text,'customer',20),[msg('TDVB-SEE.10 in 500 phải ko?')]) is None

@pytest.mark.parametrize('text',['này in 500 phải ko?','TDVB-SEE.10 TDVB-PAD.10 in 500 phải ko?','TDVB-SEE.10 in thêm 500 phải ko?','TDVB-SEE.10 in 500 cái và 200 cái phải ko?'])
def test_ambiguous_review(text):
 with pytest.raises(ValueError):pair(msg('ok','customer',20),[msg(text)])

def test_intervening_human_does_not_guess():
 assert pair(msg('ok','customer',30),[msg('TDVB-SEE.10 in 500 phải ko?'),msg('giao sáng mai','customer',20,'other')]) is None

def test_system_ignored_and_quote_exact():
 p=pair({**msg('ok','customer',30),'quoted_image':{'message_id':'q'}},[msg('TDVB-SEE.10 in 500 phải ko?'),msg('giao hàng','customer',20,'other')])
 assert p['question_id']=='q'
 assert pair(msg('ok','customer',30),[msg('TDVB-SEE.10 in 500 phải ko?'),msg('system','erp',20,'sys')])

def test_staff_ack_not_customer_order():
 assert pair(msg('ok','staff',20),[msg('TDVB-SEE.10 in 500 phải ko?')]) is None

def erp(matches,qty=500,name='TDVB-SEE.10',truncated=False):
 return SimpleNamespace(match_order=lambda cid,term:dict(matches=matches,truncated=truncated),quantity_snapshot=lambda cid,oid:dict(lines=[dict(ten_mau=name,so_luong=qty)],order_ref='DH-TEST'))

P=dict(model='TDVB-SEE.10',quantity='500')
def test_existing_same_quantity_no_create():assert reconcile(erp([{'order_id':'old'}]),'customer',P)['id']=='old'
def test_no_match_retains_new_order_path():assert reconcile(erp([]),'customer',P) is None
@pytest.mark.parametrize('e',[erp([{'order_id':'a'},{'order_id':'b'}]),erp([{'order_id':'a'}],qty=300),erp([{'order_id':'a'}],name='OTHER'),erp([],truncated=True)])
def test_uncertain_match_never_creates(e):
 with pytest.raises(ValueError):reconcile(e,'customer',P)

def test_apply_keeps_raw_and_rechecks_existing(tmp_path):
 import json
 from hub.quantity_confirmation import apply
 from test_human_batch_requests import engine,add
 s,e=engine(tmp_path)
 for mid,text,role,age in [('q','Mẫu TDVB-SEE.10 in 500 phải ko?','staff',900),('a','ok','customer',800)]:
  i,m=add(s,mid,age,role);m['text']=text
  with s.db() as d:d.execute('UPDATE captures SET payload=? WHERE id=?',(json.dumps(m),i))
  if mid=='a':raw=m
 e.customer_mappings=SimpleNamespace(get=lambda *a:{'customer_id':'c'})
 e.erp=erp([])
 run=dict(id='r',account='wa-1',thread_id='g123')
 enriched=dict(raw)
 assert apply(e.order_intake,run,[enriched]) is False
 assert '500' in enriched['text'] and raw['text']=='ok'
 with s.db() as d:assert json.loads(d.execute("SELECT payload FROM captures WHERE message_id='a'").fetchone()[0])['text']=='ok'
 states=[];e.order_intake.state=lambda *args:states.append(args)
 e.erp=erp([{'order_id':'old'}])
 assert apply(e.order_intake,run,[dict(raw)]) is True
 assert states[0][1]=='duplicate'
