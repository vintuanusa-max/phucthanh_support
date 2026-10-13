import pytest
from hub.print_approval import is_confirmation,select_approval

def msg(id,t,text='',images=None,author='customer',origin='customer',thread='g123',**kw):
 return dict(account='zalo',thread_id=thread,message_id=id,timestamp=t,text=text,images=images or [],sender_id=author,origin=origin,attachments=[],**kw)

def test_album_then_approval_preserves_both_images():
 a=msg('a',100,images=['image-a']);b=msg('b',101,images=['image-b']);c=msg('c',110,'Ok in nhe')
 assert [m['message_id'] for m in select_approval(c,[a,b,c])]==['a','b','c']

def test_staff_sample_and_customer_quote():
 staff=msg('a',100,images=['image-a'],author='staff',origin='staff');c=msg('c',110,'ok in')
 assert select_approval(c,[staff,c])==[staff,c]
 c.update(quoted_image={'resolved':True},images=['exact-quoted-image'])
 assert select_approval(c,[staff,c])==[c]
 c['quoted_image']['resolved']=False
 with pytest.raises(ValueError):select_approval(c,[staff,c])

def test_ambiguous_customer_cross_group_and_negative():
 c=msg('c',110,'ok in')
 with pytest.raises(ValueError):select_approval(c,[msg('a',100,images=['x'],author='other'),c])
 with pytest.raises(ValueError):select_approval(c,[msg('a',100,images=['x'],thread='g456'),c])
 for text in ('ok','chưa ok in','khoan in nhé','ok in thử','Ok in nhé?','sửa rồi in nhé'):
  assert not is_confirmation(text)
 assert is_confirmation('Ok in nhe')

def test_queue_repeated_approval_and_irreversible_claim(tmp_path):
 import json,time
 from test_hub import setup
 from test_trial_images import IMAGE
 from hub.models import Capture
 settings,store,engine=setup.__wrapped__(tmp_path)
 settings.inboxes['wa-1'].update(channel='zalo',print_forward={'enabled_after':time.time()-600,'thread_id':'123@g.us','delivery_enabled':True})
 engine.order_intake.sync_policy('wa-1',{})
 store.bind('wa-1','g123','Khách',10,20)
 def add(mid,stamp,text='',images=None):
  store.capture(Capture(account='wa-1',thread_id='g123',message_id=mid,display_name='Khách',sender='Khách',sender_id='customer',timestamp=stamp,text=text,images=images or []))
 add('photo',time.time()-400,images=[IMAGE]);add('ok',time.time()-300,'ok in')
 assert engine.print_approvals.poll()
 assert not engine.print_approvals.poll()
 job=engine.print_approvals.evidence_request('wa-1');assert job and len(job['messages'])==2
 engine.print_approvals.evidence_saved('wa-1',job['id'],{'source_message_ids':['photo','ok'],'image_base64':IMAGE['data']})
 claimed=engine.print_approvals.claim('wa-1');assert claimed and claimed['approval_id']==job['id']
 assert engine.print_approvals.claim('wa-1') is None
 engine.print_approvals.delivered('wa-1',claimed['id'],{'state':'confirmed','message_id':'delivered','ack':2})
 add('ok2',time.time()-200,'ok in nhé')
 assert engine.print_approvals.poll()
 with store.db() as db:
  rows=db.execute('SELECT state,payload FROM print_approvals ORDER BY created').fetchall()
 assert [r['state'] for r in rows]==['confirmed','review']
 assert 'đã có hồ sơ' in json.loads(rows[-1]['payload'])['reason']


def test_contextual_ok_needs_recent_matching_photo():
 c=msg('ok',500,'Ok nhé')
 assert is_confirmation(c['text'])
 assert len(select_approval(c,[msg('a',490,images=['x']),c]))==2
 for history in ([c],[msg('a',100,images=['x']),c],[msg('a',490,images=['x'],author='other'),c]):
  with pytest.raises(ValueError):select_approval(c,history)
 for text in ('chưa ok nhé','ok nhé?','ok nhé nhưng sửa màu','ok nhé giá này'):
  assert not is_confirmation(text)

def test_two_channels_never_resend_success_when_other_uncertain(tmp_path):
 import json,time
 from test_hub import setup
 from test_trial_images import IMAGE
 from hub.models import Capture
 settings,store,engine=setup.__wrapped__(tmp_path)
 targets=[{'account':'wa-1','thread_id':'123@g.us'},{'account':'zalo-1','thread_id':'g999'}]
 settings.inboxes['wa-1'].update(channel='zalo',print_forward={'enabled_after':time.time()-600,'thread_id':'123@g.us','delivery_enabled':True,'destinations':targets})
 engine.order_intake.sync_policy('wa-1',{})
 store.bind('wa-1','g123','Khách',10,20)
 for mid,text,images,offset in [('photo','',[IMAGE],400),('ok','Ok nhe',[],300)]:
  store.capture(Capture(account='wa-1',thread_id='g123',message_id=mid,display_name='Khách',sender='Khách',sender_id='customer',timestamp=time.time()-offset,text=text,images=images))
 assert engine.print_approvals.poll()
 job=engine.print_approvals.evidence_request('wa-1')
 engine.print_approvals.evidence_saved('wa-1',job['id'],{'source_message_ids':['photo','ok'],'image_base64':IMAGE['data']})
 assert set(engine.print_approvals.pending_destinations('wa-1'))=={'wa-1','zalo-1'}
 first=engine.print_approvals.claim('wa-1','wa-1')
 engine.print_approvals.delivered('wa-1',first['id'],{'state':'confirmed','message_id':'wa-sent'})
 assert engine.print_approvals.claim('wa-1','wa-1') is None
 second=engine.print_approvals.claim('wa-1','zalo-1')
 assert first['id']!=second['id'] and second['approval_id']==first['approval_id']
 assert engine.print_approvals.claim('wa-1','zalo-1') is None
 from hub.print_approval import PrintApprovals
 restarted=PrintApprovals(engine)
 assert restarted.pending_destinations('wa-1')==[]
 with store.db() as db:
  assert dict(db.execute('SELECT account,state FROM print_deliveries').fetchall())=={'wa-1':'confirmed','zalo-1':'uncertain'}
