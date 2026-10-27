import json,time
import pytest
from hub.models import Capture
from hub.intake_requests import request_groups,split_requests
from hub.intake_quiet import human_activity
from test_hub import setup

def engine(tmp_path):
 _,s,e=setup.__wrapped__(tmp_path)
 e.settings.inboxes['wa-1'].update(channel='zalo',capture_enabled=True,archive_root='/tmp/nas',order_intake={'enabled_after':time.time()-5000})
 e.intake_management.config={'revision':1,'wait_minutes':10,'channels':{'zalo':True}}
 e.intake_management.confirmed=time.time()
 e.order_intake.sync_policy('wa-1',{})
 s.bind('wa-1','g123','Test group',10,20)
 return s,e

def add(s,mid,age,origin='customer'):
 c=Capture(account='wa-1',thread_id='g123',message_id=mid,display_name='Test group',sender='Staff' if origin=='staff' else 'Customer',origin=origin,text='In giúp em 100 cái',timestamp=time.time()-age)
 i=s.capture(c);s.finish(i,'done');return i,c.model_dump(mode='json')

@pytest.mark.parametrize('origin',['staff','customer'])
def test_last_human_blocks_initial_analysis(tmp_path,origin):
 s,e=engine(tmp_path);add(s,'first',700);add(s,'last',200,origin)
 e.order_intake.poll()
 assert not s.recent('intake_runs') and not e.erp.calls

@pytest.mark.parametrize('origin,expected',[('staff',False),('legacy_bot',True),('erp',True)])
def test_submit_quiet_ignores_system_not_staff(tmp_path,origin,expected):
 s,e=engine(tmp_path);add(s,'last',200,origin)
 assert e.order_intake.quiet_now({'account':'wa-1','thread_id':'g123'},{'last_timestamp':time.time()-700})==expected
 assert not e.erp.calls

def test_staff_bridge_and_no_staff_in_evidence(tmp_path):
 s,e=engine(tmp_path);add(s,'a',1600);add(s,'staff',1100,'staff');add(s,'b',650)
 seen=[];e.order_intake.analyze=lambda run,p,batch,**kw:seen.extend(m['message_id'] for _,m in batch)
 e.order_intake.poll()
 assert seen==['a','b'] and not e.erp.calls

def test_expired_staff_no_permanent_wait(tmp_path):
 s,e=engine(tmp_path);add(s,'staff',650,'staff')
 assert e.order_intake.quiet_now({'account':'wa-1','thread_id':'g123'},{'last_timestamp':time.time()-900})

def test_split_claims_are_exclusive_and_durable(tmp_path):
 s,e=engine(tmp_path)
 batch=[]
 for mid,text in [('s','in test mẫu n258'),('o','Lô 0975 in cho c hàng 5 mét trên vải shamy + 9 mét trên lưới')]:
  i,m=add(s,mid,800);m['text']=text
  with s.db() as d:d.execute('UPDATE captures SET payload=? WHERE id=?',(json.dumps(m),i))
  batch.append((i,m))
 p=dict(group_name='Test group',sender='Customer',sender_key='customer',first_timestamp=time.time()-800,last_timestamp=time.time()-800,messages=['s','o'])
 run=dict(id='parent',account='wa-1',thread_id='g123',conversation=10)
 with s.db() as d:
  d.execute('INSERT INTO intake_runs VALUES(?,?,?,?,?,?,?,?)',('parent','wa-1','g123',10,'analyzing',json.dumps(p),'{}',time.time()))
  d.executemany('INSERT INTO intake_sources VALUES(?,?)',[(i,'parent') for i,_ in batch])
 assert split_requests(e.order_intake,run,p,batch)
 with s.db() as d:
  children=d.execute("SELECT payload FROM intake_runs WHERE state='model_pending'").fetchall()
  assert sorted(json.loads(r[0])['messages'] for r in children)==[['o'],['s']]
  assert d.execute('SELECT COUNT(DISTINCT run_id) FROM intake_sources').fetchone()[0]==2
 assert not e.erp.calls
 with pytest.raises(ValueError):split_requests(e.order_intake,run,p,batch)

def test_matching_sample_file_only():
 batch=[('s',{'text':'in test mẫu n258'}),('f',{'text':'','assets':[{'name':'n258 co.psd'}]}),('o',{'text':'in 5 mét lô0975'}),('g',{'text':'','assets':[{'name':'other.psd'}]})]
 groups=request_groups(batch)
 assert [i for i,_ in groups[0]]==['s','f']
 assert [i for i,_ in groups[1]]==['o','g']

def test_generic_sample_adjacent_psd_same_author():
 groups=request_groups([('s',{'sender':'A','text':'in test cho c trên vải shamy'}),('f',{'sender':'A','text':'n258 co.psd','assets':[{'name':'n258 co.psd'}]}),('o',{'sender':'A','text':'Lô0975 in cho c 5 mét + 9 mét'})])
 assert [i for i,_ in groups[0]]==['s','f']
 assert [i for i,_ in groups[1]]==['o']

def test_same_message_two_intents_does_not_discard_quantity():
 with pytest.raises(ValueError):
  split_requests(None,{}, {}, [('m',{'text':'in test n258; đặt hàng 5 mét lô0975'})])
