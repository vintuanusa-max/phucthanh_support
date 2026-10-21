import json,time
from unittest.mock import patch
from test_order_intake import intake,capture,rows


def enable(settings):
    settings.inboxes['wa-1']['agentic']={'enabled':True,'allowed_groups':['g123'],'enabled_after':time.time()-1000,'public_replies':False}


def test_multistep_results_feed_next_step_draft_never_commits(intake):
    settings,store,engine=intake;enable(settings)
    capture(store,'1',text='Đặt MET số lượng 5')
    calls=[]
    def step(settings,contents):
        calls.append(contents[-1])
        if len(calls)==1:return {'role':'model','parts':[{'functionCall':{'name':'propose_order_draft','args':{'items':[{'ma_san_pham':'MET','so_luong':5}],'source_message_ids':['1']}}}]}
        assert contents[-1]['parts'][0]['functionResponse']['response']['erp_committed'] is False
        return {'role':'model','parts':[{'text':'Đã lưu đề xuất nội bộ.'}]}
    with patch('hub.agent_loop.model_step',step),patch('hub.agent_loop.verify_action'):
        engine.order_intake.poll()
    assert len(calls)==2 and not engine.erp.calls
    with store.db() as db:
        assert db.execute('SELECT count(*) FROM agent_proposals').fetchone()[0]==1
        assert db.execute('SELECT state FROM agent_runs').fetchone()[0]=='completed'
    assert rows(store)[0]['state']=='review'


def test_repeated_tool_is_idempotent(intake):
    settings,store,engine=intake;enable(settings);capture(store,'1',text='Đặt MET 5')
    call={'role':'model','parts':[{'functionCall':{'name':'propose_order_draft','args':{'items':[{'ma_san_pham':'MET','so_luong':5}],'source_message_ids':['1']}}}]}
    with patch('hub.agent_loop.model_step',side_effect=[call,call,{'role':'model','parts':[{'text':'Done'}]}]),patch('hub.agent_loop.verify_action'):
        engine.order_intake.poll()
    with store.db() as db:assert db.execute('SELECT count(*) FROM agent_proposals').fetchone()[0]==1
    assert not engine.erp.calls


def test_human_ownership_keeps_question_private(intake):
    settings,store,engine=intake;enable(settings);capture(store,'1',text='Cho hỏi mẫu này')
    call={'role':'model','parts':[{'functionCall':{'name':'request_customer_clarification','args':{'missing_fields':['quantity'],'friendly_question':'Anh cần bao nhiêu cái?'}}}]}
    with patch('hub.agent_loop.model_step',side_effect=[call,{'role':'model','parts':[{'text':'Nhờ nhân viên hỏi.'}]}]),patch('hub.agent_loop.verify_action'):
        engine.order_intake.poll()
    with store.db() as db:
        result=json.loads(db.execute('SELECT result FROM agent_actions').fetchone()[0])
        assert result['sent_to_customer'] is False
    assert not engine.erp.calls


def test_verifier_rejection_and_unknown_tool_escalate(intake):
    settings,store,engine=intake;enable(settings);capture(store,'1',text='Đặt MET 5')
    call={'role':'model','parts':[{'functionCall':{'name':'delete_orders','args':{}}}]}
    with patch('hub.agent_loop.model_step',return_value=call):engine.order_intake.poll()
    assert not engine.erp.calls
    with store.db() as db:assert db.execute('SELECT state FROM agent_runs').fetchone()[0]=='review'


def test_restart_marks_unfinished_actions_uncertain(intake):
    settings,store,engine=intake
    with store.db() as db:
        db.execute("INSERT INTO agent_runs VALUES('interrupted','running','[]',0)")
        db.execute("INSERT INTO agent_actions VALUES('action','interrupted','request_customer_clarification','{}','executing',NULL)")
    engine.order_intake.recover()
    with store.db() as db:
        assert db.execute("SELECT state FROM agent_runs WHERE id='interrupted'").fetchone()[0]=='review'
        assert db.execute("SELECT state FROM agent_actions WHERE id='action'").fetchone()[0]=='uncertain'


def test_unavailable_design_then_handoff(intake):
    settings,store,engine=intake;enable(settings);capture(store,'1',text='Sửa logo mẫu này sang xanh')
    calls=[{'role':'model','parts':[{'functionCall':{'name':'submit_design_revision','args':{'order_id':'DH-TEST','target_file':'logo','change_spec':'xanh'}}}]},
           {'role':'model','parts':[{'functionCall':{'name':'escalate_to_human','args':{'reason':'Cần nhân viên sửa logo; worker chưa có','priority':'normal'}}}]},
           {'role':'model','parts':[{'text':'Đã chuyển nhân viên, chưa sửa file.'}]}]
    with patch('hub.agent_loop.model_step',side_effect=calls):engine.order_intake.poll()
    with store.db() as db:
        trace=json.loads(db.execute('SELECT trace FROM agent_runs').fetchone()[0])
        assert trace[0]['result']['state']=='unavailable'
        assert trace[1]['result']['state']=='human_review'
    assert not engine.erp.calls


def test_verifier_blocks_unsupported_quantity(intake):
    settings,store,engine=intake;enable(settings);capture(store,'1',text='Mẫu ngang 10 cm')
    call={'role':'model','parts':[{'functionCall':{'name':'propose_order_draft','args':{'items':[{'ma_san_pham':'MET','so_luong':10}],'source_message_ids':['1']}}}]}
    with patch('hub.agent_loop.model_step',return_value=call),patch('hub.agent_loop.verify_action',side_effect=ValueError('Unsupported quantity')):
        engine.order_intake.poll()
    with store.db() as db:
        assert db.execute('SELECT count(*) FROM agent_proposals').fetchone()[0]==0
        assert db.execute('SELECT state FROM agent_runs').fetchone()[0]=='review'
    assert not engine.erp.calls


def test_internal_preview_never_sends_public(intake):
    settings,store,engine=intake;enable(settings);capture(store,'1',text='Đơn này tới đâu rồi?')
    call={'role':'model','parts':[{'functionCall':{'name':'request_customer_clarification','args':{'missing_fields':['order_id'],'friendly_question':'Anh cho em mã đơn nhé?'}}}]}
    with patch('hub.agent_loop.model_step',side_effect=[call,{'role':'model','parts':[{'text':'Đã lưu câu hỏi nội bộ, chưa hỏi khách.'}]}]),patch('hub.agent_loop.verify_action'):
        engine.order_intake.poll()
    with store.db() as db:
        result=json.loads(db.execute('SELECT result FROM agent_actions').fetchone()[0])
        assert result['state']=='internal_preview' and result['sent_to_customer'] is False
        assert db.execute('SELECT count(*) FROM deliveries').fetchone()[0]==0


def test_all_groups_preserves_exclusions(intake):
    settings,store,engine=intake
    settings.inboxes['wa-1']['agentic']={'enabled':True,'all_allowed_groups':True,'public_replies':False}
    assert engine.order_intake.agent_loop.scope({'account':'wa-1','thread_id':'g123'})
    engine.order_intake.sync_policy('wa-1',{'zalo_skip_thread_ids':['g123']})
    assert not engine.order_intake.agent_loop.scope({'account':'wa-1','thread_id':'g123'})
    assert not engine.order_intake.agent_loop.scope({'account':'wa-1','thread_id':'123'})


def test_material_reports_use_staff_and_same_group(intake):
    settings,store,engine=intake;enable(settings)
    capture(store,'staff',text='Hết vải xanh rồi',sender='Nhân viên')
    capture(store,'customer',text='Em giao thêm vải rồi',sender='Khách')
    run={'account':'wa-1','thread_id':'g123','conversation':10,'id':'test'}
    reports=engine.order_intake.agent_loop.material_reports(run,[{'timestamp':time.time()}])
    assert [m['message_id'] for m in reports]==['staff']
    result=engine.order_intake.agent_loop.execute(run,'inspect_material',{'material_type':'vải'},{'material_reports':reports})
    assert result['state']=='reported' and result['current_balance_verified'] is False
    assert not engine.erp.calls


def test_internal_only_blocks_transport_even_in_live_mode(intake):
    settings,store,engine=intake;enable(settings)
    settings.mode='live';settings.inboxes['wa-1']['agentic']['internal_only']=True
    owner,generation=store.ownership(10)
    message={'conversation':{'id':10},'inbox':{'id':int(settings.inboxes['wa-1']['inbox_id'])},'content_attributes':{'phucthanh':{'origin':'ai','generation':generation}},'private':False,'content':'Do not deliver'}
    engine.process_outgoing('transport-test',message)
    with store.db() as db:
        assert db.execute('SELECT count(*) FROM deliveries').fetchone()[0]==0
        payload=json.loads(db.execute("SELECT payload FROM effects WHERE id='transport-test:internal-only'").fetchone()[0])
        assert payload['private'] is True


def test_agent_reviews_receive_only_group_without_enabling_orders(intake):
    settings,store,engine=intake
    settings.inboxes['wa-1']['agentic']={'enabled':True,'all_allowed_groups':True,'public_replies':False,'enabled_after':time.time()-1000}
    engine.order_intake.sync_policy('wa-1',{'zalo_contact_rules':[{'name':'Khách - A','receive_messages':True,'auto_order':False}]})
    capture(store,'1',text='Đặt MET 5')
    call={'role':'model','parts':[{'functionCall':{'name':'propose_order_draft','args':{'items':[{'ma_san_pham':'MET','so_luong':5}],'source_message_ids':['1']}}}]}
    with patch('hub.agent_loop.model_step',side_effect=[call,{'role':'model','parts':[{'text':'Đề xuất nội bộ'}]}]),patch('hub.agent_loop.verify_action'):
        engine.order_intake.poll()
    with store.db() as db:assert db.execute('SELECT count(*) FROM agent_proposals').fetchone()[0]==1
    assert not engine.erp.calls


def test_auto_order_reuses_existing_evidence_pipeline(intake):
    settings,store,engine=intake;enable(settings)
    settings.inboxes['wa-1']['agentic']['auto_order']=True
    capture(store,'1',text='Đặt MET số lượng 5')
    call={'role':'model','parts':[{'functionCall':{'name':'propose_order_draft','args':{'items':[{'ma_san_pham':'MET','so_luong':5}],'source_message_ids':['1']}}}]}
    with patch('hub.agent_loop.model_step',side_effect=[call,{'role':'model','parts':[{'text':'Đề xuất đã kiểm chứng'}]}]),patch('hub.agent_loop.verify_action'):
        engine.order_intake.poll()
    run=rows(store)[0]
    assert run['state']=='awaiting_evidence'
    payload=json.loads(run['payload'])
    assert str(payload['orders'][0]['so_luong'])=='5'
    assert payload['request_id'].endswith(run['id'])
    assert not engine.erp.calls
    with store.db() as db:assert db.execute('SELECT count(*) FROM deliveries').fetchone()[0]==0



def test_multiple_calls_in_one_model_turn_return_all_results(intake):
    settings,store,engine=intake;enable(settings);capture(store,'1',text='Kiểm tra vải và sửa logo')
    content={'role':'model','parts':[{'functionCall':{'name':'inspect_material','args':{'material_type':'vải'}}},{'functionCall':{'name':'escalate_to_human','args':{'reason':'Cần sửa file','priority':'normal'}}}]}
    def second(settings,contents):
        if len(contents)==1:return content
        assert len(contents[-1]['parts'])==2
        return {'role':'model','parts':[{'text':'Đã tham khảo và chuyển người.'}]}
    with patch('hub.agent_loop.model_step',side_effect=second):engine.order_intake.poll()
    with store.db() as db:
        assert db.execute('SELECT count(*) FROM agent_actions').fetchone()[0]==2
        assert db.execute('SELECT state FROM agent_runs').fetchone()[0]=='completed'


def test_supplier_invoice_cannot_become_order(intake):
    settings,store,engine=intake;enable(settings);capture(store,'1',text='Em gửi hóa đơn 150 giấy')
    call={'role':'model','parts':[{'functionCall':{'name':'propose_order_draft','args':{'items':[{'ma_san_pham':None,'so_luong':150}],'source_message_ids':['1']}}}]}
    with patch('hub.agent_loop.model_step',return_value=call),patch('hub.agent_loop.verify_action') as verifier:engine.order_intake.poll()
    verifier.assert_not_called()
    with store.db() as db:assert db.execute('SELECT count(*) FROM agent_proposals').fetchone()[0]==0


def test_reprint_routes_to_production_not_erp(intake):
    settings,store,engine=intake;enable(settings)
    settings.inboxes['wa-1']['agentic']['auto_order']=True
    capture(store,'1',text='In bù 60 cái màu rêu')
    with patch('hub.agent_loop.model_step') as model:
        engine.order_intake.poll()
    model.assert_not_called()
    assert not engine.erp.calls
    assert rows(store)[0]['state']=='review'

def test_pricing_preview_uses_table_without_erp(intake):
 settings,store,engine=intake;enable(settings)
 engine.customer_mappings.get=lambda *a:{'customer_name':'Khách thường','customer_id':'test'}
 capture(store,'1',text='Báo giá PET 20 mét, ngang 20cm cao 30cm')
 call={'role':'model','parts':[{'functionCall':{'name':'prepare_print_quote','args':{'rule':'pet_meter','width_cm':20,'height_cm':30,'quantity':20,'quantity_unit':'meter','source_message_ids':['1']}}}]}
 with patch('hub.agent_loop.model_step',side_effect=[call,{'role':'model','parts':[{'text':'Đã lưu báo giá nội bộ'}]}]),patch('hub.agent_loop.verify_action'):
  engine.order_intake.poll()
 assert not engine.erp.calls
 assert any('65,000' in m.get('content','') for m in engine.cw.sent)
 assert all(m['private'] for m in engine.cw.sent)

def test_outside_business_scope_question_silent(intake):
 settings,store,engine=intake;enable(settings)
 settings.inboxes['wa-1']['agentic']['business_reply_scope']=True
 result=engine.order_intake.agent_loop.execute({'account':'wa-1','thread_id':'g123','conversation':20,'id':'test'},'request_customer_clarification',{'missing_fields':['order_id'],'friendly_question':'Mã đơn nào?'},{})
 assert result['state']=='silent_by_policy'
 assert not engine.cw.sent

def test_missing_optional_name_returns_reconsider_not_silent(intake):
    settings,store,engine=intake;enable(settings)
    settings.inboxes['wa-1']['agentic']['business_reply_scope']=True
    run={'id':'optional-test','account':'wa-1','thread_id':'g123','conversation':1}
    value=engine.order_intake.agent_loop.execute(run,'request_customer_clarification',{'missing_fields':['tên mẫu/mã sản phẩm'],'friendly_question':'Tên mẫu?'},{})
    assert value['state']=='reconsider_order'
    assert not engine.erp.calls
