import json,time
import pytest
from test_hub import setup
from test_trial_images import IMAGE
from hub.models import Capture
from hub.intake_preflight import repeated_order_media,observations,can_skip,route

@pytest.fixture
def env(tmp_path):
 settings,store,e=setup.__wrapped__(tmp_path)
 settings.inboxes['wa-1'].update(channel='zalo',capture_enabled=True,order_intake={'enabled_after':time.time()-10000},archive_root='/tmp/nas')
 store.bind('wa-1','g123','Test',10,20);e.order_intake.sync_policy('wa-1',{'zalo_internal_members':['Nhân viên']})
 def capture(mid,text='',thread='g123',origin='customer',sender='Khách',images=True):
  i=store.capture(Capture(account='wa-1',thread_id=thread,message_id=mid,display_name='Test',sender=sender,origin=origin,text=text,timestamp=time.time()-1200,images=[IMAGE] if images else []));store.finish(i,'done')
  with store.db() as d:return json.loads(d.execute('select payload from captures where id=?',(i,)).fetchone()[0])
 old=capture('old','in 100 cái')
 with store.db() as d:d.execute('insert into intake_runs values(?,?,?,?,?,?,?,?)',('old-run','wa-1','g123',20,'created',json.dumps({'messages':['old']}),json.dumps({'orders':[{'id':'erp-old'}]}),time.time()-1000))
 return e,capture,old,dict(id='new-run',account='wa-1',thread_id='g123',conversation=20)

@pytest.mark.parametrize('text,state',[('[Ảnh Zalo lưu trong kho NAS]','review'),('gửi lại hình','review'),('ok','ignored'),('ok in đi nhé','ignored')])
def test_forward_committed_no_vision(env,text,state):
 e,c,old,run=env;r=repeated_order_media(e.order_intake,run,[c('new',text)]);assert r['state']==state and r['result']['image_read'] is False and not e.erp.calls
@pytest.mark.parametrize('text',['in thêm 200 cái','đặt thêm 50','in lại 100 cái','200','in mẫu này 300 cái','thanh toán rồi, in thêm 200 cái'])
def test_forward_new_quantity_not_discarded(env,text):
 e,c,old,run=env;assert repeated_order_media(e.order_intake,run,[c('new',text)]) is None

def test_other_group_never_inherits_order(env):
 e,c,old,run=env;run['thread_id']='g999';assert repeated_order_media(e.order_intake,run,[c('new','ok',thread='g999')]) is None
@pytest.mark.parametrize('state',['review','uncertain','sending','ignored'])
def test_only_confirmed_orders_qualify(env,state):
 e,c,old,run=env
 with e.store.db() as d:d.execute('update intake_runs set state=?',(state,))
 assert repeated_order_media(e.order_intake,run,[c('new','ok')]) is None

def test_staff_images_never_order(env,monkeypatch):
 e,c,old,run=env;staff=c('staff','in 1000 cái',origin='staff',sender='Nhân viên');assert not e.order_intake.accepts(staff)
 monkeypatch.setattr('hub.intake_preflight.ask',lambda *a:pytest.fail('staff image sent to AI'))
 assert observations(e,run,[staff])==[]

def test_repeated_media_cache_same_group(env,monkeypatch):
 e,c,old,run=env;calls=[]
 def ask(*a):calls.append(a);return dict(text='100 cái',description='Logo A',uncertain=False)
 monkeypatch.setattr('hub.intake_preflight.ask',ask)
 a=observations(e,run,[old]);b=observations(e,run,[c('new','in thêm 200 cái')]);assert len(calls)==1 and b[0]['cache_hit'] and b[0]['message_id']=='new'
 observations(e,{**run,'thread_id':'g999'},[c('other',thread='g999')]);assert len(calls)==2

def test_cache_only_no_paid_call(env,monkeypatch):
 e,c,old,run=env;monkeypatch.setattr('hub.intake_preflight.ask',lambda *a:pytest.fail('unexpected AI'))
 assert observations(e,run,[old],cache_only=True)==[]
@pytest.mark.parametrize('text',['in thêm 200 cái','in test mẫu n259','đặt hàng 600 nón','số lượng 1100','300'])
def test_bad_text_classifier_cannot_skip_order(text):
 m=[{'message_id':'new','text':text}];v=dict(intent='payment',certain=True,has_order_or_sample_request=False,source_message_ids=['new'],reason='bad AI')
 assert not can_skip(v,m)

def test_no_global_image_blacklist(env,monkeypatch):
 e,c,old,run=env;calls=[];monkeypatch.setattr('hub.intake_preflight.ask',lambda *a:(calls.append(1) or dict(text='100',description='logo',uncertain=False)))
 observed=observations(e,run,[c('new','in thêm 200 cái')]);assert observed and len(calls)==1 and not e.erp.calls

def test_context_gate_uses_cached_image_without_resending(env,monkeypatch):
 from hub.context_gate import IntentDecision
 e,c,old,run=env
 e.settings.inboxes['wa-1']['context_agent']={'enabled':True,'mode':'review','allowed_groups':['g123']}
 m=c('new','in thêm 200 cái')
 monkeypatch.setattr('hub.intake_preflight.ask',lambda *a:dict(text='100 cái',description='Logo A',uncertain=False))
 observations(e,run,[m]);seen=[]
 def classify(settings,context,images):
  seen.append(images);assert context['image_observations'][0]['message_id']=='new'
  return IntentDecision(intent='new_order',source_message_ids=['new'],reason='fresh quantity',evidence=['in thêm 200 cái'])
 monkeypatch.setattr('hub.context_gate.classify',classify)
 assert e.order_intake.context_gate.check(run,[m]);assert seen==[[]];assert not e.erp.calls

def test_context_gate_uncertain_image_still_visible(env,monkeypatch):
 from hub.context_gate import IntentDecision
 e,c,old,run=env;e.settings.inboxes['wa-1']['context_agent']={'enabled':True,'mode':'review','allowed_groups':['g123']}
 m=c('new','in thêm 200 cái');monkeypatch.setattr('hub.intake_preflight.ask',lambda *a:dict(text='',description='blurred',uncertain=True));observations(e,run,[m]);seen=[]
 def classify(settings,context,images):
  seen.append(len(images));return IntentDecision(intent='unclear',source_message_ids=['new'],reason='blurred',evidence=['in thêm 200 cái'])
 monkeypatch.setattr('hub.context_gate.classify',classify)
 assert not e.order_intake.context_gate.check(run,[m]);assert seen==[1] and not e.erp.calls


def test_no_early_analysis_for_new_sender(tmp_path):
 import time
 from test_hub import setup
 from hub.models import Capture
 _,store,e=setup.__wrapped__(tmp_path)
 e.settings.inboxes['wa-1'].update(channel='zalo',capture_enabled=True,archive_root='/tmp/nas',order_intake={'enabled_after':time.time()-5000})
 e.intake_management.config={'revision':1,'wait_minutes':10,'channels':{'zalo':True,'whatsapp':True,'viber':True}}
 e.order_intake.sync_policy('wa-1',{})
 store.bind('wa-1','g123','Test group',10,20)
 for mid,sender,age in [('m1','A',700),('m2','B',200)]:
  key=store.capture(Capture(account='wa-1',thread_id='g123',message_id=mid,display_name='Test group',sender=sender,text='In thêm 100 cái',timestamp=time.time()-age));store.finish(key,'done')
 e.order_intake.poll()
 assert not store.recent('intake_runs') and not e.erp.calls and e.agent.context is None
