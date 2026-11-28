import json,time
import pytest
from test_order_intake import intake,capture
from test_trial_images import IMAGE
from hub.quote_recovery import recover_quotes
from hub.order_groups import image_groups
@pytest.mark.parametrize('wrong_sender',[False,True])
def test_exact_quote_recovery(intake,wrong_sender):
 _,store,_=intake
 capture(store,'1',client_message_id='client1',sender_id='customer',images=[IMAGE],timestamp=time.time()-200)
 capture(store,'2',sender_id='customer',text='25 bộ',timestamp=time.time()-180)
 capture(store,'3',sender_id='customer',text='theo ảnh',timestamp=time.time()-160,attachments=['zalo-desktop:quoted-image-unresolved'],quoted_image={'message_id':'0','sender':'','timestamp':0,'client_message_id':'client1','sender_id':'wrong' if wrong_sender else 'customer','resolved':False})
 with store.db() as d:ms=[json.loads(r[0]) for r in d.execute('select payload from captures order by rowid')]
 recover_quotes(store,ms)
 assert ms[-1]['quoted_image']['resolved'] is (not wrong_sender)
 if not wrong_sender:
  assert ms[-1]['images'] and not ms[-1]['attachments'] and len(image_groups(ms))==1
  with store.db() as d:count=d.execute('select count(*) from media').fetchone()[0]
  recover_quotes(store,ms)
  with store.db() as d:assert d.execute('select count(*) from media').fetchone()[0]==count


@pytest.mark.parametrize('wrong_sender',[False,True])
def test_exact_quoted_file_recovery(intake,wrong_sender):
 _,store,_=intake
 asset={'id':'a'*64,'name':'File in PET non 88.ai','kind':'file','state':'ready','relative_path':'QUYEN/2026-11/originals/a.ai','sha256':'b'*64,'size':2026619,'mime_type':'application/octet-stream','error':''}
 capture(store,'f1',client_message_id='client_f1',sender_id='customer',text='[File Zalo: File in PET non 88.ai]',assets=[asset],timestamp=time.time()-200)
 capture(store,'f2',sender_id='customer',text='Cho làm giúp q mẫu này nhé Tuấn',timestamp=time.time()-160,attachments=['zalo-desktop:quoted-file-unresolved'],quoted_file={'message_id':'0','sender':'Như Quyền','timestamp':0.0,'client_message_id':'client_f1','sender_id':'wrong' if wrong_sender else 'customer','resolved':False,'name':'','error':'quote_file_source_missing'})
 with store.db() as d:ms=[json.loads(r[0]) for r in d.execute('select payload from captures order by rowid')]
 recover_quotes(store,ms)
 assert ms[-1]['quoted_file']['resolved'] is (not wrong_sender)
 if not wrong_sender:
  assert ms[-1]['quoted_file']['message_id']=='f1'
  assert ms[-1]['quoted_file']['name']=='File in PET non 88.ai'
  assert ms[-1]['quoted_file']['error']==''
  assert not ms[-1]['attachments']
  assert ms[-1]['assets']==[asset]
 else:
  assert ms[-1]['attachments']==['zalo-desktop:quoted-file-unresolved']
  assert not ms[-1]['assets']


def test_order_intake_recovers_quoted_file_instead_of_incomplete_media(intake):
 from hub.models import IntakeDecision
 settings,store,engine=intake
 settings.inboxes['wa-1']['order_intake']['enabled_after']=time.time()-3600
 asset={'id':'a'*64,'name':'File in PET non 88.ai','kind':'file','state':'ready','relative_path':'QUYEN/2026-11/originals/a.ai','sha256':'b'*64,'size':2026619,'mime_type':'application/octet-stream','error':''}
 c1=capture(store,'f1',client_message_id='client_f1',sender_id='customer',text='[File Zalo: File in PET non 88.ai]',assets=[asset],timestamp=time.time()-2500)
 c2=capture(store,'f2',sender_id='customer',text='Cho làm giúp q 2 mẫu này nhé Tuấn',timestamp=time.time()-2460,attachments=['zalo-desktop:quoted-file-unresolved'],quoted_file={'message_id':'0','sender':'Như Quyền','timestamp':0.0,'client_message_id':'client_f1','sender_id':'customer','resolved':False,'name':'','error':'quote_file_source_missing'})
 with store.db() as d:
  rows=[dict(r) for r in d.execute('SELECT id,payload FROM captures ORDER BY rowid')]
  payload={'messages':['f1','f2'],'group_name':'Khách - A','sender':'Như Quyền','sender_key':'customer','unified_intake':True,'first_timestamp':time.time()-2500,'last_timestamp':time.time()-2460}
  d.execute("INSERT INTO intake_runs(id,account,thread_id,conversation,state,payload,result,created) VALUES(?,?,?,?,?,?,?,?)",('run_qf','wa-1','g123',10,'analyzing',json.dumps(payload),'{}',time.time()))
 batch=[(r['id'],json.loads(r['payload'])) for r in rows]
 run={'id':'run_qf','account':'wa-1','thread_id':'g123','conversation':10,'payload':json.dumps(payload)}
 engine.order_intake.analyze(run,payload,batch,agent_decision=IntakeDecision(action='draft_order',source_message_ids=[1,2],orders=[{'ma_san_pham':'VEMAU','ten_mau':'PET nón 88','so_luong':2}]))
 with store.db() as d:
  r=d.execute("SELECT state,result FROM intake_runs WHERE id='run_qf'").fetchone()
 assert r and r['state'] in ('awaiting_evidence','created'), dict(r)

