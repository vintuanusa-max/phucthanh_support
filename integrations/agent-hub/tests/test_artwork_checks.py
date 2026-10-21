import hashlib
import pytest
from hub.artwork_pdf import parse_info,inspect_document
from hub.artwork_checks import code_matches
from zalo_desktop.artwork_bridge import read_asset

def test_pdf_size_is_physical_page_not_pixel():
    p=parse_info('Pages: 2\nPage    1 size: 1303.94 x 1346.46 pts\nPage    2 size: 595.276 x 841.89 pts\n')
    assert p['page_count']==2
    assert p['pdf_pages'][0]['width_cm']==pytest.approx(46,abs=.01)
    assert p['pdf_pages'][0]['height_cm']==pytest.approx(47.5,abs=.01)

def test_ai_without_pdf_not_executed(tmp_path):
    path=tmp_path/'a.ai';path.write_bytes(b'%!PS-Adobe bogus executable commands')
    result=inspect_document(path,tmp_path/'out','a.ai')
    assert result['state']=='unsupported' and not result['previews']

def test_filename_code_only_candidate_not_loose_prefix():
    assert code_matches('TDVB-DB.10','TDVB-DB.10 (1).pdf')
    assert not code_matches('TDVB-DB.10','TDVB-DB.100.pdf')
    assert not code_matches('TDVB-DB.10','NEWTDVB-DB.10.ai')

def test_source_reader_path_hash_and_size(tmp_path):
    raw=b'%PDF-test';p=tmp_path/'x.pdf';p.write_bytes(raw)
    asset={'relative_path':'x.pdf','sha256':hashlib.sha256(raw).hexdigest()}
    assert read_asset(tmp_path,asset)
    for bad in [{**asset,'relative_path':'../secret'},{**asset,'sha256':'0'*64}]:
        with pytest.raises(ValueError):read_asset(tmp_path,bad)
    with pytest.raises(ValueError):read_asset(tmp_path,asset,2)
    assert p.read_bytes()==raw

def test_upload_hash_idempotency_and_review_only(intake,tmp_path,monkeypatch):
    import json,time,base64
    from hub.store import event_key
    _,store,engine=intake
    p={'id':'b','account':'a','thread_id':'g1','conversation_id':1,'sources':[],'brief':{'title':'test'},'execution_allowed':False}
    raw=b'%PDF-read-only';asset={'name':'test.pdf','sha256':hashlib.sha256(raw).hexdigest()}
    job={'brief_id':'b','conversation':1,'thread_id':'g1','source_message_id':'m','asset':asset,'relation':'brief_source','reference_assets':[]}
    with store.db() as d:
        d.execute('INSERT INTO design_briefs VALUES(?,?,?,?,?,?,?)',('b','r','a','g1',1,json.dumps(p),time.time()))
        d.execute('INSERT INTO artwork_checks VALUES(?,?,?,?,?,?,?)',('j','b','a','awaiting_upload',json.dumps(job),'{}',time.time()))
    with pytest.raises(ValueError):engine.artwork_checks.received('a','j',{'data':base64.b64encode(b'changed').decode()})
    data={'data':base64.b64encode(raw).decode()}
    engine.artwork_checks.received('a','j',data);engine.artwork_checks.received('a','j',data)
    with store.db() as d:assert d.execute("SELECT count(*) FROM jobs WHERE id='artwork:j'").fetchone()[0]==1
    monkeypatch.setattr('hub.artwork_checks.inspect_document',lambda *a:{'state':'unsupported','reason':'Needs compatible PDF','previews':[]})
    engine.artwork_checks.process('j')
    with store.db() as d:
        assert d.execute("SELECT state FROM artwork_checks WHERE id='j'").fetchone()[0]=='review'
        notes=[json.loads(r[0]) for r in d.execute("SELECT payload FROM effects WHERE kind='message' AND id LIKE 'artwork:%'")]
        assert notes and all(n['private'] for n in notes)
        value=json.loads(d.execute("SELECT payload FROM design_briefs WHERE id='b'").fetchone()[0])
        assert value['execution_allowed'] is False
    assert not engine.erp.calls

from test_order_intake import intake
