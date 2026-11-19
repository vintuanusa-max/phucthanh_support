import pytest,sqlite3,json
from hub.intake_quiet import settled_batch
from hub.source_coverage import codes
from hub.workflow_rules import jpg_size,pet_profile
from hub.native_auto import region_box
from hub.psd_samples import sample_only
from hub.intake_lifecycle import reusable,explicit_addition

def rows():return [('a',{'timestamp':100,'sender':'A'},'done'),('b',{'timestamp':650,'sender':'B'},'done')]
@pytest.mark.parametrize('now,expected',[(700,0),(1249.99,0),(1250,2),(1300,2)])
def test_group_quiet(now,expected):assert len(settled_batch(rows(),now,600))==expected

def test_incomplete_download_blocks():
 r=rows();r[-1]=('b',r[-1][1],'pending');assert not settled_batch(r,2000,600)
def test_separate_batches():
 r=rows()+[('c',{'timestamp':1300},'done')];assert len(settled_batch(r,1900,600))==2
@pytest.mark.parametrize('box',[[0,0,2000,2000],[-1,0,500,500],[0,0,float('nan'),1],[0,0,0,500]])
def test_invalid_region_rejected(box):
 with pytest.raises(ValueError):region_box({'box_2d':box})
def test_region_axes():assert region_box({'box_2d':[100,200,600,800]})==[.2,.1,.8,.6]
def test_three_models_one_file():assert codes('FILE TDVB-IELTS1984-1+2+3.10.ai')==[{'base':'TDVB-IELTS1984-'+str(n),'month':10} for n in (1,2,3)]
def test_month_not_variant():assert codes('TDVB-PAD.10.pdf')==[{'base':'TDVB-PAD','month':10}]
@pytest.mark.parametrize('w,h,b,k,expected',[(42,92,'raw_fabric','bag_panel',(40,87)),(38,46,'raw_fabric','bag_panel',(36,43.5)),(160,31.2,'explicit_output','meter_fabric',(160,31.2))])
def test_output_dimensions(w,h,b,k,expected):assert jpg_size(w,h,b,k)==expected
def test_pet_no_shrink_white_no_contract():
 p=pet_profile({'brief':{'requirements':[{'quote':'in túi PET'}]}});assert p['shrink_cm']==[0,0] and p['white_contract_px']==0 and p['color_contract_px']==1
@pytest.mark.parametrize('text,expected',[('in test mẫu n259',True),('in thử n258',True),('đặt hàng in thêm 100 cái',False),('in test rồi sản xuất hàng loạt',False)])
def test_psd_sample_intent(text,expected):assert bool(sample_only([{'text':text}]))==expected
@pytest.mark.parametrize('state',['created','duplicate','sending','uncertain'])
def test_consumed_or_uncertain_never_reused(state):
 d=sqlite3.connect(':memory:');d.execute('create table order_source_links(account,thread_id,message_id)');d.execute('create table intake_runs(account,thread_id,state,payload,result)');d.execute('insert into intake_runs values(?,?,?,?,?)',('a','g',state,json.dumps({'messages':['m']}),'{}'));assert not reusable(d,{'payload':json.dumps(dict(account='a',thread_id='g',message_id='m')),'source_result':'{}'})
def test_payment_not_reused():
 assert not reusable(None,{'source_result':'{"intent":"payment"}'})
def test_addition():assert explicit_addition([{'text':'in thêm 200 cái'}])

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
