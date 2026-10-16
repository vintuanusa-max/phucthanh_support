import json
import time
from unittest.mock import patch
import pytest
from hub.context_gate import IntentDecision, validate_decision
from test_order_intake import intake, capture, rows


def context():
    return {'batch':[{'message_id':'b','text':'em giao thêm vải'}],
            'history':[{'message_id':'a','text':'hết vải rồi'}], 'candidates':[]}


def decision(intent='material_replenishment', **kw):
    return IntentDecision(intent=intent, source_message_ids=['a','b'],
                          reason='Giao nguyên liệu, không đặt mới', evidence=['hết vải rồi','em giao thêm vải'], **kw)


def test_material_not_order():
    assert not validate_decision(decision(), context())


def test_unproven_quote_and_unknown_order_rejected():
    d=decision();d.evidence=['Đặt 1000 cái']
    with pytest.raises(ValueError):validate_decision(d,context())
    d=decision(existing_run_id='another-account-order')
    with pytest.raises(ValueError):validate_decision(d,context())


def test_conflict_missing_existing_cannot_create():
    for extra in [{'conflicts':['two quantities']},{'missing_fields':['quantity']}]:
        assert not validate_decision(decision('new_order',**extra),context())


def enable(settings, mode='review'):
    settings.inboxes['wa-1']['context_agent']={'enabled':True,'mode':mode,'allowed_groups':['g123']}


def test_gate_blocks_material_and_retains_staff_context(intake):
    settings,store,engine=intake;enable(settings)
    capture(store,'staff',text='hết vải rồi',sender='Nhân viên',timestamp=time.time()-200)
    capture(store,'customer',text='em giao thêm vải 100 mét',timestamp=time.time()-150)
    def classify(settings,ctx,images):
        assert any(m['role']=='staff' for m in ctx['history'])
        return IntentDecision(intent='material_replenishment',source_message_ids=['staff','customer'],
                              reason='Bổ sung nguyên liệu',evidence=['hết vải rồi','em giao thêm vải 100 mét'])
    with patch('hub.context_gate.classify',classify):engine.order_intake.poll()
    assert rows(store)[0]['state']=='review' and not engine.erp.calls


def test_new_order_continues_existing_pipeline(intake):
    settings,store,engine=intake;enable(settings)
    capture(store,'new',text='Đặt MET số lượng 5')
    d=IntentDecision(intent='new_order',source_message_ids=['new'],reason='Đặt mới rõ',evidence=['Đặt MET số lượng 5'])
    with patch('hub.context_gate.classify',return_value=d):engine.order_intake.poll()
    assert rows(store)[0]['state']=='awaiting_evidence'
    assert not engine.erp.calls


def test_failure_is_closed_and_shadow_does_not_change_flow(intake):
    settings,store,engine=intake;enable(settings)
    capture(store,'new',text='Đặt MET số lượng 5')
    with patch('hub.context_gate.classify',side_effect=ValueError):engine.order_intake.poll()
    assert rows(store)[0]['state']=='review'


def test_context_excludes_other_groups_and_future_messages(intake):
    settings,store,engine=intake;enable(settings)
    capture(store,'one',text='Đặt MET 5')
    capture(store,'secret',text='Other group',thread_id='g456')
    with store.db() as db:
        m=json.loads(db.execute("SELECT payload FROM captures WHERE message_id='one'").fetchone()[0])
    ctx=engine.order_intake.context_gate.build({'id':'x','account':'wa-1','thread_id':'g123'},[m])
    assert all(x['message_id']!='secret' for x in ctx['history'])


def test_shadow_records_without_blocking(intake):
    settings,store,engine=intake;enable(settings,'shadow')
    capture(store,'new',text='Đặt MET số lượng 5')
    d=IntentDecision(intent='unclear',source_message_ids=['new'],reason='Shadow test',evidence=['Đặt MET số lượng 5'])
    with patch('hub.context_gate.classify',return_value=d):engine.order_intake.poll()
    assert rows(store)[0]['state']=='awaiting_evidence'
    with store.db() as db:assert db.execute('SELECT count(*) FROM context_decisions').fetchone()[0]==1


def test_timeout_image_also_passes_context_gate(intake):
    from test_trial_images import IMAGE
    settings,store,engine=intake;enable(settings)
    settings.inboxes['wa-1']['order_intake']['enabled_after']=time.time()-3000
    capture(store,'photo',text='Ảnh vải',images=[IMAGE],timestamp=time.time()-1900)
    engine.order_intake.poll()
    d=IntentDecision(intent='material_replenishment',source_message_ids=['photo'],reason='Vải giao bổ sung',evidence=['Ảnh vải'])
    with patch('hub.context_gate.classify',return_value=d):engine.order_intake.poll()
    assert rows(store)[0]['state']=='review' and not engine.erp.calls


def test_unknown_sources_fail_closed(intake):
    settings,store,engine=intake;enable(settings)
    capture(store,'new',text='Đặt MET số lượng 5')
    d=IntentDecision(intent='new_order',source_message_ids=['invented'],reason='bad',evidence=['invented'])
    with patch('hub.context_gate.classify',return_value=d):engine.order_intake.poll()
    assert rows(store)[0]['state']=='review'

def test_status_requires_admin_and_reports_only_summary(intake):
    from fastapi.testclient import TestClient
    from hub.app import create_app
    settings,store,engine=intake
    settings.admin_token='local-test-admin-0123456789-0123456789'
    client=TestClient(create_app(settings,engine,start_worker=False))
    assert client.get('/context-agent/status').status_code==401
    r=client.get('/context-agent/status',headers={'Authorization':'Bearer local-test-admin-0123456789-0123456789'})
    assert r.status_code==200 and r.json()['decisions']==[]
