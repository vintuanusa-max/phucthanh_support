import json
import time

from hub.models import Capture
from hub.print_changes import describe, relevant
from test_hub import setup
from test_trial_images import IMAGE


def system(tmp_path):
    settings,store,engine=setup.__wrapped__(tmp_path)
    route={'enabled_after':time.time()-1000,'changes_enabled_after':time.time()-300,
           'thread_id':'123@g.us','delivery_enabled':True,
           'destinations':[{'account':'wa-1','thread_id':'123@g.us'},{'account':'zalo-1','thread_id':'g999'}]}
    settings.inboxes['wa-1'].update(channel='zalo',print_forward=route)
    engine.order_intake.sync_policy('wa-1',{})
    store.bind('wa-1','g123','Khách',10,20)
    def add(mid,text='',images=None,offset=100,thread='g123',sender='customer'):
        store.capture(Capture(account='wa-1',thread_id=thread,message_id=mid,display_name='Khách',sender=sender,
                              sender_id=sender,timestamp=time.time()-offset,text=text,images=images or []))
    add('photo','100 cái',[IMAGE],600);add('ok','ok in',offset=500)
    assert engine.print_approvals.poll()
    job=engine.print_approvals.evidence_request('wa-1')
    engine.print_approvals.evidence_saved('wa-1',job['id'],{'source_message_ids':['photo','ok'],'image_base64':IMAGE['data']})
    for target in ('wa-1','zalo-1'):
        claimed=engine.print_approvals.claim('wa-1',target)
        engine.print_approvals.delivered('wa-1',claimed['id'],{'state':'confirmed','message_id':target})
    return store,engine,add


def test_quantity_change_notifies_two_channels_once(tmp_path):
    store,engine,add=system(tmp_path)
    add('change','Sửa số lượng đơn vừa chốt thành 150 cái nhé')
    assert engine.print_approvals.poll()
    assert not engine.print_approvals.poll()
    job=engine.print_approvals.evidence_request('wa-1')
    assert '100 cái' in job['notice'] and '150 cái' in job['notice']
    assert 'TẠM DỪNG' in job['notice'] and job['new_message_ids']==['change']
    ids=[m['message_id'] for m in job['messages']]
    engine.print_approvals.evidence_saved('wa-1',job['id'],{'source_message_ids':ids,'image_base64':IMAGE['data']})
    first=engine.print_approvals.claim('wa-1','wa-1')
    assert 'THAY ĐỔI SAU DUYỆT' in first['caption']
    engine.print_approvals.delivered('wa-1',first['id'],{'state':'confirmed','message_id':'change-wa'})
    assert engine.print_approvals.claim('wa-1','wa-1') is None
    assert engine.print_approvals.claim('wa-1','zalo-1')['approval_id']==job['id']


def test_photo_change_then_second_change_preserves_versions(tmp_path):
    store,engine,add=system(tmp_path)
    add('new-photo','Đổi mẫu vừa duyệt này nhé',[IMAGE])
    assert engine.print_approvals.poll()
    first=engine.print_approvals.evidence_request('wa-1')
    assert 'CHƯA TỰ COI LÀ ĐÃ DUYỆT' in first['notice']
    assert len([m for m in first['messages'] if m['images']])==2
    add('quantity','Giảm đơn vừa chốt còn 80 cái',offset=50)
    assert engine.print_approvals.poll()
    with store.db() as db:
        rows=[json.loads(r[0]) for r in db.execute("SELECT payload FROM print_approvals WHERE json_extract(payload,'$.kind')='amendment' ORDER BY created")]
        assert [r['change_version'] for r in rows]==[1,2]
        assert '80 cái' in rows[-1]['notice']
        assert db.execute('SELECT count(*) FROM print_change_sources').fetchone()[0]==2


def test_no_change_for_thanks_cross_group_or_prebaseline(tmp_path):
    store,engine,add=system(tmp_path)
    add('thanks','Cảm ơn');add('other','Đổi 200 cái',thread='g456')
    add('old','Sửa còn 10 cái',offset=400)
    assert not engine.print_approvals.poll()


def test_new_photo_alone_and_other_customer_are_not_changes(tmp_path):
    store,engine,add=system(tmp_path)
    add('new','',[IMAGE],sender='another-customer')
    assert not engine.print_approvals.poll()
    assert engine.print_approvals.evidence_request('wa-1') is None



def test_change_notice_rendered_and_kept_separate_from_customer_text(tmp_path):
    from hub.evidence_document import render_document
    store,engine,add=system(tmp_path)
    add('change','Sửa số lượng đơn vừa chốt thành 150 cái nhé')
    assert engine.print_approvals.poll()
    job=engine.print_approvals.evidence_request('wa-1')
    _,manifest,pages=render_document(job['messages'],job['reference'],job['notice'],job['new_message_ids'])
    assert manifest['system_notice']==job['notice']
    assert manifest['messages'][-1]['text']=='Sửa số lượng đơn vừa chốt thành 150 cái nhé'
    assert pages[0].startswith(b'\x89PNG')
    (tmp_path/'change-preview.png').write_bytes(pages[0])

def test_large_picture_falls_back_to_explicit_text_warning(monkeypatch,tmp_path):
    from types import SimpleNamespace
    from whatsapp_desktop import print_sync
    calls=[];posted=[]
    job={'id':'example','reference':'CHOT-IN-EXAMPLE','notice':'TẠM DỪNG','new_message_ids':['new'],
         'messages':[{'message_id':'new','text':'Đổi mẫu','images':[IMAGE]}]}
    def save(messages,reference,root,**kwargs):
        calls.append((messages,kwargs))
        if len(calls)==1:raise ValueError('Too many pixels')
        return {'source_message_ids':['new']}
    class Response:
        def raise_for_status(self):pass
        def json(self):return {'job':job}
    reader=SimpleNamespace(cfg={'account':'wa-1','archive':{'root':str(tmp_path)}},
                           http=SimpleNamespace(get=lambda url:Response(),post=lambda url,json:(posted.append(json) or Response())))
    monkeypatch.setattr(print_sync,'save_document',save)
    monkeypatch.setattr(print_sync,'erp_evidence_png',lambda result:b'png-test')
    print_sync.synchronize(reader)
    assert len(calls)==2 and calls[-1][0][0]['images']==[]
    assert 'ẢNH KHÔNG ĐÍNH KÈM' in calls[-1][1]['notice']
    assert posted[0]['source_message_ids']==['new'] and posted[0]['image_base64']

def test_number_without_order_reference_is_not_change(tmp_path):
    store,engine,add=system(tmp_path)
    add('number','150',offset=40)
    assert not engine.print_approvals.poll()


def test_a_thuc_new_order_not_attached_to_previous_approval(tmp_path):
    store,engine,add=system(tmp_path)
    add('file','[File Zalo: in nón x6.cdr]',offset=200)
    add('new','Lm mẫu nón kết in 2 vt @Thôngg',[IMAGE],offset=180)
    add('next','Làm mẫu này @Thôngg',offset=160)
    add('size','Ngang 10cm',offset=150)
    add('qty','1.000c',offset=140)
    assert not engine.print_approvals.poll()
    with store.db() as db:
        assert db.execute('SELECT count(*) FROM print_change_sources').fetchone()[0]==0


def test_unanchored_correction_not_guessed(tmp_path):
    store,engine,add=system(tmp_path)
    add('change','Sửa số lượng thành 150 cái')
    assert not engine.print_approvals.poll()
