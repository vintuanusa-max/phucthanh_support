import contextlib,json,sqlite3,sys
from pathlib import Path
from types import SimpleNamespace
import pytest,httpx
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from hub import print_governance as g, print_api as api

class Store:
 def __init__(self,path):self.path=path
 @contextlib.contextmanager
 def db(self):
  db=sqlite3.connect(self.path,timeout=2);db.row_factory=sqlite3.Row
  try:yield db;db.commit()
  except:db.rollback();raise
  finally:db.close()

@pytest.fixture
def store(tmp_path):
 s=Store(str(tmp_path/'test.db'));g.init(s)
 with s.db() as d:
  d.executescript('CREATE TABLE design_briefs(id TEXT,account TEXT,thread_id TEXT,payload TEXT); CREATE TABLE workflow_versions(kind TEXT,export_id TEXT,state TEXT);')
  for bid,group in [('one','group1'),('two','group1'),('other','group2')]:
   d.execute('INSERT INTO design_briefs VALUES(?,?,?,?)',(bid,'account',group,json.dumps({'brief':{'requirements':[{'text':'cue12cm'}]},'sources':[{'assets':[{'sha256':'source1'}]}]})))
 return s

def payload(bid):return {'brief_id':bid,'source':{'asset':{'sha256':'source1'}},'plan':{'panels':[{'components':[{'mouth_allowance_source':'blank','mouth_allowance_cm':5,'y_cm':12}]}]}}

def test_reuse_requires_approval_scope_sources_and_rules(store):
 p=payload('one');g.bind_rules(store,p);g.record(store,'jpg_exports','job1',p,'done')
 assert g.reusable(store,'two','source1','jpg_exports') is None
 with store.db() as d:d.execute("INSERT INTO workflow_versions VALUES('jpg_exports','job1','approved')")
 assert g.reusable(store,'two','source1','jpg_exports')['derived_from']=='job1'
 assert g.reusable(store,'other','source1','jpg_exports') is None
 assert g.reusable(store,'two','different','jpg_exports') is None
 conf=g.settings(store);g.update_settings(store,{'expected_revision':conf['revision'],'rules':{'mouth_blank_cm':4}})
 assert g.reusable(store,'two','source1','jpg_exports') is None

def test_legacy_never_claims_current_rules(store):
 g.record(store,'jpg_exports','legacy',payload('one'),'done')
 with store.db() as d:d.execute("INSERT INTO workflow_versions VALUES('jpg_exports','legacy','approved')")
 assert g.reusable(store,'two','source1','jpg_exports') is None

def test_settings_conflict_and_rollback(store):
 c=g.settings(store);new=g.update_settings(store,{'expected_revision':c['revision'],'rules':{'white_backing_extra_stripes':.5}})
 with pytest.raises(ValueError):g.update_settings(store,{'expected_revision':c['revision'],'enabled':False})
 restored=g.update_settings(store,{'expected_revision':new['revision'],'restore_revision':c['revision']})
 assert restored['rules']['white_backing_extra_stripes']==1
 with pytest.raises(ValueError):g.update_settings(store,{'expected_revision':restored['revision'],'rules':{'pet_bag_offsets':True}})

def test_rules_apply_once(store):
 c=g.settings(store);g.update_settings(store,{'expected_revision':c['revision'],'rules':{'mouth_blank_cm':6}})
 p=payload('one');g.bind_rules(store,p);g.bind_rules(store,p)
 assert p['plan']['panels'][0]['components'][0]['y_cm']==13

class Client:
 calls=0;fail=False
 def __init__(self,**kw):pass
 def __enter__(self):return self
 def __exit__(self,*args):pass
 def post(self,*args,**kwargs):
  Client.calls+=1
  if Client.fail and Client.calls==1:raise httpx.ConnectError('private credential must not appear')
  return httpx.Response(200,request=httpx.Request('POST','https://example.test'),json={'candidates':[{'content':{'parts':[{'text':'{"ok":true}'}]}}],'usageMetadata':{'totalTokenCount':10}})

def test_cache_and_bounded_fallback(store,monkeypatch):
 Client.calls=0;Client.fail=True;monkeypatch.setattr(api.httpx,'Client',Client)
 e=SimpleNamespace(store=store,settings=SimpleNamespace(gemini_key='secret'))
 result=api.ask(e,'JPG_LAYOUT_ONLY',[],{},'gemini-2.5-pro')
 assert result=={'ok':True} and Client.calls==2
 assert api.ask(e,'JPG_LAYOUT_ONLY',[],{},'gemini-2.5-pro')==result and Client.calls==2
 out=api.overview(store);assert 'secret' not in json.dumps(out) and 'private credential' not in json.dumps(out)

def test_budget_before_network(store,monkeypatch):
 Client.calls=0;Client.fail=False;monkeypatch.setattr(api.httpx,'Client',Client)
 c=g.settings(store);g.update_settings(store,{'expected_revision':c['revision'],'daily_call_limit':1})
 e=SimpleNamespace(store=store,settings=SimpleNamespace(gemini_key='secret'))
 api.ask(e,'one',[],{},'gemini-2.5-pro')
 with pytest.raises(ValueError):api.ask(e,'two',[],{},'gemini-2.5-pro')
 assert Client.calls==1

def test_router_schema_precedes_jpg_prefix():
 assert api.stage('JPG_LAYOUT_ONLY',{'properties':{'boards':{},'parts':{}}})=='classify'
 assert api.stage('JPG_LAYOUT_ONLY',{'properties':{'pass':{}}})=='verify'
 assert api.stage('',{},[{'text':'NATIVE_CANDIDATE id1'}])=='select'

def test_timeout_does_not_repeat_paid_request(store,monkeypatch):
 class Timeout(Client):
  def post(self,*a,**kw):
   Client.calls+=1
   raise httpx.ReadTimeout('secret remote response')
 Client.calls=0;monkeypatch.setattr(api.httpx,'Client',Timeout)
 e=SimpleNamespace(store=store,settings=SimpleNamespace(gemini_key='secret'))
 with pytest.raises(ValueError):api.ask(e,'timeout',[],{},'gemini-2.5-pro')
 assert Client.calls==1 and api.overview(store)['calls'][0]['state']=='uncertain'

def test_schema_invalid_not_cached(store,monkeypatch):
 Client.calls=0;Client.fail=False;monkeypatch.setattr(api.httpx,'Client',Client)
 e=SimpleNamespace(store=store,settings=SimpleNamespace(gemini_key='secret'))
 with pytest.raises(ValueError):api.ask(e,'invalid',[],{'type':'object','required':['faces']},'gemini-2.5-pro')
 with store.db() as d:assert d.execute('SELECT count(*) FROM print_api_cache').fetchone()[0]==0
 assert Client.calls==1

def test_job_context_and_cache_does_not_consume_budget(store,monkeypatch):
 Client.calls=0;Client.fail=False;monkeypatch.setattr(api.httpx,'Client',Client)
 c=g.settings(store);g.update_settings(store,{'expected_revision':c['revision'],'daily_call_limit':1})
 e=SimpleNamespace(store=store,settings=SimpleNamespace(gemini_key='secret'))
 with api.job_scope('jobA'):
  api.ask(e,'same',[],{},'gemini-2.5-pro');api.ask(e,'same',[],{},'gemini-2.5-pro')
 assert Client.calls==1
 assert {x['job_id'] for x in api.overview(store)['calls']}=={'jobA'}
 assert {x['state'] for x in api.overview(store)['calls']}=={'done','cache_hit'}

def test_new_message_prevents_exact_reuse(store):
 p=payload('one');g.bind_rules(store,p);g.record(store,'jpg_exports','job1',p,'done')
 with store.db() as d:
  d.execute("INSERT INTO workflow_versions VALUES('jpg_exports','job1','approved')")
  b=json.loads(d.execute("SELECT payload FROM design_briefs WHERE id='two'").fetchone()[0]);b['sources'][0]['text']='change logo position'
  d.execute("UPDATE design_briefs SET payload=? WHERE id='two'",(json.dumps(b),))
 assert g.reusable(store,'two','source1','jpg_exports') is None

def test_similarity_lists_actual_parameter_changes():
 a={'panels':[{'construction':'joined','output_cm':[45,83],'components':[{'side':'front','y_cm':12}]}]}
 b=json.loads(json.dumps(a));b['panels'][0]['components'][0]['y_cm']=14
 assert g.layout_signature(a)==g.layout_signature(b)
 assert g.diff_plan(a,b)==['panels[0].components[0].y_cm']

@pytest.fixture
def retry_env(store,tmp_path,monkeypatch):
 import types
 # Isolate queue tests from production engine/modules/network.
 dispatch=types.ModuleType('hub.dispatch_control');dispatch.ACTIVE=g.ACTIVE
 def jobs(db,bid):return [dict(x) for x in db.execute('SELECT id,state FROM jpg_exports')]
 dispatch.jobs=jobs;monkeypatch.setitem(sys.modules,'hub.dispatch_control',dispatch)
 policy=types.ModuleType('hub.order_policy');policy.capture_allowed=lambda *a:True;monkeypatch.setitem(sys.modules,'hub.order_policy',policy)
 exports=types.ModuleType('hub.jpg_exports');exports.output_directory=lambda folder,code,identity,created:folder+'/DESIGNER/'+code+'/'+identity;monkeypatch.setitem(sys.modules,'hub.jpg_exports',exports)
 store.thread=lambda **kw:{'display_name':'group'}
 p=payload('one');p.update(archive_folder='CANAVI',conversation=1,export_plan_ready=True,rule_version='old-approved')
 p['plan']={'order_code':'TEST','panels':[{'output_cm':[45,83],'components':[{'side':'front','width_cm':19.5,'height_cm':9.9,'x_cm':12.75,'y_cm':12,'horizontal_alignment':'center'}]}]}
 with store.db() as d:
  d.execute('CREATE TABLE jpg_exports(id TEXT PRIMARY KEY,account TEXT,state TEXT,payload TEXT,created REAL)')
  d.execute('CREATE TABLE native_selections(id TEXT,brief_id TEXT,state TEXT,payload TEXT)')
  d.execute("INSERT INTO jpg_exports VALUES('old','account','done',?,1)",(json.dumps(p),))
 root=tmp_path/'exports';(root/'old').mkdir(parents=True);(root/'old'/'context.json').write_text('[]')
 e=SimpleNamespace(store=store,settings=SimpleNamespace(inboxes={'account':{'channel':'zalo'}}),order_intake=SimpleNamespace(policy=lambda a:{}),artwork_checks=SimpleNamespace(jpg=SimpleNamespace(root=root),pet=SimpleNamespace(workflow=SimpleNamespace(current=lambda b:True))))
 e.order_intake.policy=lambda a:{'enabled':True}
 data={'kind':'jpg_exports','job_id':'old','note':'canh theo maket','expected_plan':g.digest(p['plan']),'adjustments':[{'panel':0,'component':0,'y_cm':14}]}
 return e,data,p

def test_retry_immutable_idempotent_and_no_analysis(retry_env):
 e,data,p=retry_env
 result=g.retry(e,'one',data);again=g.retry(e,'one',data)
 assert result['id']==again['id']
 with e.store.db() as d:
  assert d.execute('SELECT count(*) FROM jpg_exports').fetchone()[0]==2
  assert json.loads(d.execute("SELECT payload FROM jpg_exports WHERE id='old'").fetchone()[0])==p
  row=d.execute('SELECT payload,state FROM jpg_exports WHERE id=?',(result['id'],)).fetchone();q=json.loads(row['payload'])
 assert row['state']=='queued' and q['rule_version']=='old-approved'
 assert q['plan']['panels'][0]['components'][0]['y_cm']==14
 assert q['plan']['panels'][0]['components'][0]['width_cm']==19.5
 assert q['private'] and q['auto_rip'] is False

def test_retry_busy_native_and_stale_plan(retry_env):
 e,data,p=retry_env
 with e.store.db() as d:d.execute("INSERT INTO native_selections VALUES('n','one','scan_running','{}')")
 with pytest.raises(ValueError,match='đang chạy'):g.retry(e,'one',data)
 with e.store.db() as d:d.execute('DELETE FROM native_selections')
 data['expected_plan']='outdated'
 with pytest.raises(ValueError,match='đã đổi'):g.retry(e,'one',data)

def test_retry_missing_context_never_queues(retry_env):
 e,data,p=retry_env;(e.artwork_checks.jpg.root/'old'/'context.json').unlink()
 with pytest.raises(ValueError,match='ngữ cảnh'):g.retry(e,'one',data)
 with e.store.db() as d:
  assert d.execute("SELECT count(*) FROM jpg_exports WHERE state IN ('queued','preparing')").fetchone()[0]==0
  assert d.execute('SELECT count(*) FROM print_plan_actions').fetchone()[0]==1

def test_retry_rejects_resize_and_unvalidated_plan(retry_env):
 e,data,p=retry_env;data['adjustments'][0]['width_cm']=30
 with pytest.raises(ValueError,match='Chỉ chỉnh cữ'):g.retry(e,'one',data)
 p['export_plan_ready']=False
 with e.store.db() as d:d.execute("UPDATE jpg_exports SET payload=?,state='review' WHERE id='old'",(json.dumps(p),))
 with pytest.raises(ValueError,match='chưa qua'):g.retry(e,'one',data)

def test_pet_reuse_requires_every_position_approved(store):
 context={'parts':[{'text':'source photo'}],'refs':['file:one']}
 recipe={'batch_id':'batch','context_hash':g.digest(context),'plan':{'is_pet':True,'same_design':True,'issues':[],'faces':[{'side':'front'},{'side':'back'}]}}
 with store.db() as d:d.execute('CREATE TABLE native_selections(id TEXT,payload TEXT)');d.execute('INSERT INTO native_selections VALUES(?,?)',('batch',json.dumps({'children':['j1','j2']})))
 for jid in ['j1','j2']:
  p=payload('one');p['plan']={'faces':[{'side':jid}],'selection_recipe':recipe};g.bind_rules(store,p);g.record(store,'pet_exports',jid,p,'done')
 with store.db() as d:d.execute("INSERT INTO workflow_versions VALUES('pet_exports','j1','approved')")
 assert g.reusable_pet(store,'two','source1',context) is None
 with store.db() as d:d.execute("INSERT INTO workflow_versions VALUES('pet_exports','j2','approved')")
 assert g.reusable_pet(store,'two','source1',context)==recipe['plan']
 assert g.reusable_pet(store,'two','source1',{'parts':[]}) is None
