import hashlib
import json
import time

import pytest

from hub.models import Capture
from hub.production_slips import trigger,normalized
from zalo_desktop.slip_sync import copy_slip
from zalo_desktop.vault import Vault,customer_folder
from test_hub import setup
from test_trial_images import IMAGE


def test_prefix_paths_and_existing_data_untouched(tmp_path):
    assert customer_folder('CANAVI - IN PHUC THANH - In Pet')=='CANAVI'
    assert customer_folder('CANAVI HCM2 - In Phúc Thanh')=='CANAVI HCM2'
    assert customer_folder('A HUY–PHƯƠNG NAM')=='A HUY'
    v=Vault(tmp_path/'state',tmp_path/'nas')
    with v.db() as d:d.execute('INSERT INTO groups VALUES(?,?)',('z:g1','CANAVI - OLD FULL NAME'))
    old=tmp_path/'nas/CANAVI - OLD FULL NAME/x.png';old.parent.mkdir(parents=True);old.write_bytes(b'old')
    assert v.folder({'account':'z','thread_id':'g1','display_name':'CANAVI - IN'})=='CANAVI'
    assert old.read_bytes()==b'old'
    assert v.folder({'account':'z','thread_id':'g1','display_name':'RENAMED - IN'})=='CANAVI'


def test_copy_hash_idempotence_and_path_safety(tmp_path):
    source=tmp_path/'CANAVI - OLD/a.png';source.parent.mkdir();source.write_bytes(b'test-image')
    digest=hashlib.sha256(source.read_bytes()).hexdigest()
    job={'asset':{'relative_path':'CANAVI - OLD/a.png','sha256':digest,'name':'a.png'},
         'folder':'CANAVI','account':'z','thread_id':'g1','source_message_id':'image','trigger_message_id':'text','heading':'PHIẾU LỆNH SẢN XUẤT'}
    a=copy_slip(job,tmp_path);b=copy_slip(job,tmp_path)
    assert a==b and source.read_bytes()==b'test-image'
    target=tmp_path/a['relative_path'];assert target.parent.name=='DON HANG'
    target.write_bytes(b'do not replace')
    with pytest.raises(ValueError):copy_slip(job,tmp_path)
    assert target.read_bytes()==b'do not replace'
    job['asset']['relative_path']='../outside.png'
    with pytest.raises(ValueError):copy_slip(job,tmp_path)


def test_scoped_trigger_image_classification_and_dedup(tmp_path,monkeypatch):
    settings,store,engine=setup.__wrapped__(tmp_path)
    settings.inboxes['wa-1'].update(channel='zalo',production_slips={'enabled_after':time.time()-600,'groups':{'g123':{'sender_id':'person','folder':'CANAVI'}}})
    engine.order_intake.sync_policy('wa-1',{})
    store.bind('wa-1','g123','CANAVI - IN',10,20)
    def add(mid,text,images=None,sender='person',offset=300):
        store.capture(Capture(account='wa-1',thread_id='g123',message_id=mid,display_name='CANAVI - IN',sender='Name',sender_id=sender,timestamp=time.time()-offset,text=text,images=images or [],assets=[{'id':'a'*64,'kind':'image','state':'ready','sha256':'a'*64,'relative_path':'CANAVI/a.png','name':'a.png'}] if images else []))
    add('before','',[IMAGE],offset=500)
    add('text','Anh gửi lệnh in',offset=400)
    add('wrong-sender','',[IMAGE],sender='other')
    add('image','',[IMAGE])
    calls=[]
    monkeypatch.setattr('hub.production_slips.classify',lambda s,i:(calls.append(i) or {'accepted':True,'heading':'PHIẾU LỆNH SẢN XUẤT'}))
    assert engine.production_slips.poll()  # The pre-trigger image is marked once, not sent to Gemini.
    assert engine.production_slips.poll()
    assert not engine.production_slips.poll()
    assert len(calls)==1
    job=engine.production_slips.pending('wa-1')
    assert job['source_message_id']=='image' and job['trigger_message_id']=='text'
    engine.production_slips.saved('wa-1',job['id'],{'sha256':'a'*64,'name':'saved.png'})
    assert engine.production_slips.pending('wa-1') is None


def test_title_requires_actual_top_heading(monkeypatch):
    from types import SimpleNamespace
    from hub.production_slips import classify
    result={'heading':'PHIẾU LỆNH SẢN XUẤT','heading_at_top':True,'is_production_slip':True}
    class Response:
        def raise_for_status(self):pass
        def json(self):return {'candidates':[{'content':{'parts':[{'text':json.dumps(result)}]}}]}
    monkeypatch.setattr('hub.production_slips.httpx.post',lambda *a,**k:Response())
    settings=SimpleNamespace(gemini_key='test',gemini_model='test')
    assert classify(settings,IMAGE)['accepted']
    result['heading_at_top']=False
    assert not classify(settings,IMAGE)['accepted']
    result.update(heading_at_top=True,heading='Ảnh mẫu túi')
    assert not classify(settings,IMAGE)['accepted']
    assert trigger('Anh gửi lệnh in') and not trigger('Chưa gửi lệnh in')
