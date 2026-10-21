import json
from types import SimpleNamespace
import pytest
from hub.design_briefs import Brief, Extraction, validate, DesignBriefs
from hub.store import Store

def brief(**kw):
    return Brief(title='Đổi màu',kind='design_revision',source_message_ids=['m'],requirements=[{'text':'Chỉnh đỏ','message_id':'m','quote':'đỏ hơn'}],**kw)

def context():
    return {'batch':[{'message_id':'m','text':'chỉnh đỏ hơn','sender':'Khách','role':'customer','timestamp':1}], 'history':[],'previous':[]}

def test_unknown_source_and_invented_quote_rejected():
    c=context();validate(brief(),c)
    b=brief();b.source_message_ids=['foreign']
    with pytest.raises(ValueError):validate(b,c)
    b=brief();b.requirements[0].quote='xanh hơn'
    with pytest.raises(ValueError):validate(b,c)

def test_no_link_to_other_group_or_history_only():
    with pytest.raises(ValueError):validate(brief(proposed_previous_id='other'),context())
    c=context();c['history']=c['batch'];c['batch']=[]
    with pytest.raises(ValueError):validate(brief(),c)

def fixture(tmp_path,monkeypatch,result):
    store=Store(tmp_path/'hub.sqlite3');calls=[]
    raw={**context()['batch'][0],'account':'a','thread_id':'g1','images':[],'assets':[{'id':'x','name':'mau.cdr','state':'ready','relative_path':'KH/originals/mau.cdr','sha256':'abc'}]}
    with store.db() as db:db.execute('INSERT INTO captures VALUES(?,?,?,?,?,?)',('cap','a','g1','m',0,json.dumps(raw)))
    e=SimpleNamespace(store=store,settings=SimpleNamespace(gemini_key='fake',inboxes={'a':{'archive_root':'NAS'}}),note=lambda *a,**k:calls.append(('note',a,k)),effect=lambda *a,**k:calls.append(('effect',a,k)))
    intake=SimpleNamespace(engine=e,store=store,agent_loop=SimpleNamespace(scope=lambda r:True),context_gate=SimpleNamespace(build=lambda r,m:context()))
    monkeypatch.setattr('hub.design_briefs.extract',lambda *a:result)
    return DesignBriefs(intake),{'id':'run','account':'a','thread_id':'g1','conversation':9},[raw],calls

def test_persist_exact_assets_and_one_private_note_on_replay(tmp_path,monkeypatch):
    obj,r,ms,calls=fixture(tmp_path,monkeypatch,Extraction(briefs=[brief()]))
    obj.collect(r,ms);obj.collect(r,ms)
    with obj.store.db() as db:rows=db.execute('SELECT payload FROM design_briefs').fetchall()
    assert len(rows)==1
    p=json.loads(rows[0][0]);assert not p['execution_allowed'] and not p['customer_question_sent']
    assert p['sources'][0]['assets'][0]['relative_path']=='KH/originals/mau.cdr'
    assert len(list((tmp_path/'design-briefs').glob('*.json')))==1
    assert len([c for c in calls if c[0]=='note'])==1
    assert all(c[1][2]=='status' for c in calls if c[0]=='effect')

def test_no_design_silent_and_bad_extraction_goes_private_review(tmp_path,monkeypatch):
    obj,r,ms,calls=fixture(tmp_path,monkeypatch,Extraction())
    obj.collect(r,ms);assert not calls
    r['id']='r2';ms[0]['message_id']='new'
    monkeypatch.setattr('hub.design_briefs.extract',lambda *a:Extraction(briefs=[brief(proposed_previous_id='bogus')]))
    obj.collect(r,ms)
    assert 'CẦN NHÂN VIÊN' in calls[0][1][2]
    with obj.store.db() as db:assert db.execute('SELECT count(*) FROM design_briefs').fetchone()[0]==0

def test_serving_schema_keeps_title_property_and_required_fields():
    from hub.design_briefs import serving_schema
    schema=serving_schema(Extraction.model_json_schema())
    assert 'title' in schema['$defs']['Brief']['properties']
    assert 'maxItems' not in schema['properties']['briefs']
