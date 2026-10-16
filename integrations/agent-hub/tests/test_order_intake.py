import base64
import json
import time

import pytest
from test_hub import setup as hub_setup
from test_trial_images import IMAGE, PNG

from hub.models import Capture, Decision, IntakeDecision
from hub.order_intake import piece_quantities
from hub.order_policy import allowed, eligible, sanitize


def test_legacy_config_semantics():
    policy = sanitize(
        {
            "zalo_internal_members": ["Phương Uyên"],
            "zalo_skip_groups": ["Bỏ qua"],
            "zalo_disable_reply_groups": ["Khách - A"],
            "zalo_contact_rules": [{"name": "Khách - B", "auto_order": False, "receive_messages": True}],
        }
    )
    assert allowed(policy, "zalo", "Khách - A")
    assert not allowed(policy, "zalo", "Khách - A", "receive_messages")
    assert not allowed(policy, "zalo", "Khách - B")
    assert not allowed(policy, "zalo", " Bỏ   qua ")
    m = dict(
        thread_id="g123", display_name="Khách - A", sender="Khách", direction="incoming", origin="customer"
    )
    assert eligible(policy, "zalo", m)
    assert not eligible(policy, "zalo", {**m, "sender": "PHƯƠNG UYÊN"})
    assert eligible(policy, "zalo", {**m, "text": "@Phương Uyên đặt 5 MET"})
    assert not eligible(policy, "zalo", {**m, "sender": "Phương Uyên", "text": "@Khách mẫu in"})
    assert not eligible(policy, "zalo", {**m, "direction": "outgoing"})
    assert not eligible(policy, "zalo", {**m, "thread_id": "123"})
    assert "secret" not in sanitize({"secret": "never sync this"})


def test_vietnamese_piece_quantities():
    assert piece_quantities("1.000c") == {1000}
    assert piece_quantities("8c") == {8}
    assert piece_quantities("1.000.000 cái") == {1000000}


def test_missing_product_creates_pending_code_not_a_guess(intake):
    _, store, engine = intake
    capture(store, text="In mẫu vừa gửi 8c")
    engine.agent.decision = IntakeDecision(
        action="draft_order", source_message_ids=[1], orders=[{"ma_san_pham": None, "so_luong": 8}]
    )
    engine.order_intake.poll()
    assert rows(store)[0]["state"] == "awaiting_evidence"
    assert json.loads(rows(store)[0]["payload"])["orders"][0]["ma_san_pham"] is None


def test_thousand_pieces_cannot_become_one_even_with_image(intake):
    _, store, engine = intake
    capture(store, text="1.000c", images=[IMAGE])
    engine.agent.decision = IntakeDecision(
        action="draft_order", source_message_ids=[1], orders=[{"ma_san_pham": None, "so_luong": 1}]
    )
    engine.order_intake.poll()
    assert rows(store)[0]["state"] == "review" and not engine.erp.calls


@pytest.fixture
def intake(tmp_path):
    settings, store, engine = hub_setup.__wrapped__(tmp_path)
    cfg = settings.inboxes["wa-1"]
    cfg.update(
        channel="zalo",
        capture_enabled=True,
        archive_root=r"\\nas\files",
        order_intake={"enabled_after": time.time() - 300},
    )
    settings.erp_write = True
    store.bind("wa-1", "g123", "Khách - A", 10, 20)
    engine.erp.observe_group = lambda name: None
    engine.order_intake.sync_policy("wa-1", {"zalo_internal_members": ["Nhân viên"]})
    engine.agent.decision = Decision(
        action="draft_order", source_message_ids=[1], orders=[{"ma_san_pham": "MET", "so_luong": 5}]
    )
    return settings, store, engine


def capture(store, identity="1", **changes):
    payload = dict(
        account="wa-1",
        thread_id="g123",
        message_id=identity,
        sender="Khách",
        display_name="Khách - A",
        text="Đặt MET số lượng 5",
        timestamp=time.time() - 160,
    )
    payload.update(changes)
    result = store.capture(Capture(**payload))
    store.finish(result, "done")
    return result


def rows(store):
    return store.recent("intake_runs")


def acknowledge(engine, identity):
    engine.order_intake.evidence_saved(
        "wa-1",
        identity,
        {
            "image_base64": base64.b64encode(PNG).decode(),
            "source_message_ids": ["1"],
            "directory": r"\\nas\files\Khách - A\orders\INTAKE-test",
        },
    )


def test_new_only_nas_first_then_exactly_one_erp_write(intake):
    settings, store, engine = intake
    capture(store, "old", timestamp=time.time() - 1000)
    capture(store)
    assert engine.order_intake.poll()
    run = rows(store)[0]
    assert run["state"] == "awaiting_evidence" and not engine.erp.calls
    job = engine.order_intake.evidence_request("wa-1")
    assert [m["message_id"] for m in job["messages"]] == ["1"]
    acknowledge(engine, run["id"])
    engine.order_intake.poll()
    assert rows(store)[0]["state"] == "created"
    assert engine.erp.calls[0]["source"] == "zalo"
    assert engine.erp.calls[0]["group_name"] == "Khách - A"
    assert engine.erp.calls[0]["image_base64"]
    engine.order_intake.poll()
    assert len(engine.erp.calls) == 1
    assert all(m["private"] for m in engine.cw.sent)


def test_staff_and_no_reply_policy_still_allow_orders(intake):
    _, store, engine = intake
    engine.order_intake.sync_policy(
        "wa-1", {"zalo_internal_members": ["Nhân viên"], "zalo_disable_reply_groups": ["Khách - A"]}
    )
    capture(store, "staff", sender="Nhân viên")
    capture(store)
    engine.order_intake.poll()
    assert json.loads(rows(store)[0]["payload"])["messages"] == ["1"]


def test_image_caption_and_followup_same_sender_not_other_member(intake):
    _, store, engine = intake
    capture(store, "1", text="Ảnh đặt hàng", images=[IMAGE], timestamp=time.time() - 190)
    capture(store, "2", sender="Người khác", text="Ảnh khác", images=[IMAGE], timestamp=time.time() - 180)
    capture(store, "3", text="Đặt MET số lượng 5, dùng ảnh vừa gửi")
    engine.agent.decision.source_message_ids = [1, 2]
    engine.order_intake.poll()
    assert json.loads(rows(store)[0]["payload"])["messages"] == ["1", "3"]
    assert len(engine.agent.context["images"]) == 1


def test_policy_refresh_and_recheck_before_submit(intake):
    _, store, engine = intake
    capture(store)
    engine.order_intake.poll()
    acknowledge(engine, rows(store)[0]["id"])
    engine.order_intake.sync_policy("wa-1", {"zalo_skip_groups": ["Khách - A"]})
    engine.order_intake.poll()
    assert rows(store)[0]["state"] == "review" and not engine.erp.calls
    with store.db() as db:
        db.execute("UPDATE intake_policy SET updated=0")
    assert engine.order_intake.policy("wa-1") is None


def test_later_text_can_use_previously_ignored_image(intake):
    _, store, engine = intake
    capture(store, "1", text="Ảnh", images=[IMAGE], timestamp=time.time() - 220)
    engine.agent.decision = Decision(action="reply")
    engine.order_intake.poll()
    assert rows(store)[0]["state"] == "waiting_details"
    capture(store, "2")
    engine.agent.decision = Decision(
        action="draft_order", source_message_ids=[1, 2], orders=[{"ma_san_pham": "MET", "so_luong": 5}]
    )
    engine.order_intake.poll()
    assert rows(store)[0]["state"] == "awaiting_evidence"
    assert json.loads(rows(store)[0]["payload"])["messages"] == ["1", "2"]
    assert len(engine.agent.context["images"]) == 1


def test_missing_customer_never_uses_erp_pending_fallback(intake):
    _, store, engine = intake

    def reject(name):
        raise ValueError("No customer")

    engine.erp.observe_group = reject
    capture(store)
    engine.order_intake.poll()
    assert rows(store)[0]["state"] == "review" and not engine.erp.calls


def test_quiet_window_resets_on_new_message(intake):
    _, store, engine = intake
    capture(store, '1')
    capture(store, '2', text='Lấy 120 cái nhé', timestamp=time.time()-30)
    assert not engine.order_intake.poll()
    assert not rows(store) and not engine.erp.calls


def test_late_quantity_after_ten_minutes_keeps_exact_image(intake):
    settings, store, engine = intake
    settings.inboxes['wa-1']['order_intake']['enabled_after']=time.time()-2000
    capture(store,'1',text='Ảnh mẫu',images=[IMAGE],timestamp=time.time()-800)
    engine.order_intake.poll()
    assert rows(store)[0]['state']=='waiting_details'
    capture(store,'2',text='Đặt MET số lượng 5')
    engine.agent.decision.source_message_ids=[1,2]
    engine.order_intake.poll()
    latest=rows(store)[0]
    assert latest['state']=='awaiting_evidence'
    assert json.loads(latest['payload'])['messages']==['1','2']
    assert len(engine.agent.context['images'])==1


def test_waiting_request_expires_to_human_without_order(intake):
    settings, store, engine=intake
    settings.inboxes['wa-1']['order_intake']['enabled_after']=time.time()-3000
    capture(store,'1',text='Ảnh mẫu',images=[IMAGE],timestamp=time.time()-1900)
    engine.order_intake.poll()
    engine.order_intake.poll()
    assert rows(store)[0]['state']=='review'
    assert not engine.erp.calls


def test_supplement_before_deadline_is_not_lost_during_quiet_wait(intake):
    settings,store,engine=intake
    settings.inboxes['wa-1']['order_intake']['enabled_after']=time.time()-3000
    capture(store,'1',text='Ảnh mẫu',images=[IMAGE],timestamp=time.time()-1810)
    engine.order_intake.poll()
    capture(store,'2',timestamp=time.time()-130)
    engine.agent.decision.source_message_ids=[1,2]
    engine.order_intake.poll()
    assert rows(store)[0]['state']=='awaiting_evidence'


def test_new_quantity_during_evidence_prevents_old_order(intake):
    _,store,engine=intake
    capture(store)
    engine.order_intake.poll()
    run=rows(store)[0]
    acknowledge(engine,run['id'])
    capture(store,'2',text='Sửa lại 120 cái',timestamp=time.time()-10)
    engine.order_intake.poll()
    assert rows(store)[0]['state']=='waiting_details'
    assert not engine.erp.calls


def test_uncertain_never_retries(intake):
    _, store, engine = intake
    capture(store)
    engine.order_intake.poll()
    acknowledge(engine, rows(store)[0]["id"])
    calls = []

    def uncertain(payload):
        calls.append(payload)
        raise TimeoutError()

    engine.erp.create_order = uncertain
    engine.order_intake.poll()
    assert rows(store)[0]["state"] == "uncertain"
    engine.order_intake.poll()
    assert len(calls) == 1


@pytest.mark.parametrize("code,qty", [("OTHER", 5), ("MET", 999)])
def test_ai_cannot_invent_code_or_text_quantity(intake, code, qty):
    _, store, engine = intake
    capture(store)
    engine.agent.decision = Decision(
        action="draft_order", source_message_ids=[1], orders=[{"ma_san_pham": code, "so_luong": qty}]
    )
    engine.order_intake.poll()
    assert rows(store)[0]["state"] == "review" and not engine.erp.calls


def test_timeout_reads_image_once_and_keeps_original_request(intake):
    settings,store,engine=intake
    settings.inboxes['wa-1']['order_intake']['enabled_after']=time.time()-3000
    capture(store,'image-qty',text='Ảnh mẫu',images=[IMAGE],timestamp=time.time()-1900)
    engine.order_intake.poll()
    original=rows(store)[0]['id']
    engine.agent.decision=IntakeDecision(action='draft_order',source_message_ids=[1],orders=[{'ma_san_pham':None,'so_luong':100,'ghi_chu_mau_do':'Ảnh tin 1 ghi SL 100 cái'}])
    assert engine.order_intake.poll()
    run=rows(store)[0]
    assert run['id']==original and run['state']=='awaiting_evidence'
    assert json.loads(run['payload'])['image_timeout_attempted'] is True
    assert engine.agent.context['image_quantity_after_wait'] is True
    assert len(engine.agent.context['images'])==1
    assert not engine.erp.calls


def test_timeout_unreadable_image_handoff_no_repeat(intake):
    settings,store,engine=intake
    settings.inboxes['wa-1']['order_intake']['enabled_after']=time.time()-3000
    capture(store,'image-qty',text='Ảnh mẫu',images=[IMAGE],timestamp=time.time()-1900)
    engine.order_intake.poll()
    engine.agent.decision=IntakeDecision(action='handoff',reason='Không đọc rõ số lượng')
    assert engine.order_intake.poll()
    assert rows(store)[0]['state']=='review'
    assert not engine.order_intake.poll()
    assert not engine.erp.calls

@pytest.mark.parametrize('old_state,frozen,reply,joined',[
 ('review',False,'Ok làm giúp em',True),
 ('review',False,'giá bao nhiêu?',False),
 ('review',False,'chưa ok',False),
 ('created',False,'Ok',False),
 ('uncertain',True,'Ok',False),
 ('review',True,'Ok',False),
])
def test_confirmation_recovers_only_uncommitted_review(intake,old_state,frozen,reply,joined):
 from unittest.mock import patch
 settings,store,engine=intake
 capture(store,'quote',text='Logo này 120 cái giá bn',timestamp=time.time()-250)
 engine.order_intake.poll()
 old=rows(store)[0]
 with store.db() as db:
  payload=json.loads(old['payload'])
  payload.pop('request_id',None)
  if frozen:payload['submitted_payload']={'request_id':'already-sent'}
  db.execute('UPDATE intake_runs SET state=?,payload=? WHERE id=?',(old_state,json.dumps(payload),old['id']))
 capture(store,'confirm',text=reply,timestamp=time.time()-130)
 with patch.object(engine.order_intake,'analyze') as analyze:
  engine.order_intake.poll()
  batch=analyze.call_args.args[2]
  assert ('quote' in [m['message_id'] for _,m in batch])==joined
 assert not engine.erp.calls

def test_quote_then_confirmation_creates_one_order_with_evidence(intake):
 settings,store,engine=intake
 capture(store,'photo',text='Logo này 120 cái giá bn',images=[IMAGE],timestamp=time.time()-250)
 engine.order_intake.poll()
 old=rows(store)[0]
 with store.db() as db:
  payload=json.loads(old['payload']);payload.pop('request_id',None)
  db.execute("UPDATE intake_runs SET state='review',payload=? WHERE id=?",(json.dumps(payload),old['id']))
 capture(store,'ok',text='Ok in 120 cái mẫu này',timestamp=time.time()-130)
 engine.agent.decision=IntakeDecision(action='draft_order',source_message_ids=[1,2],orders=[{'ma_san_pham':None,'so_luong':120,'ten_mau':'Logo đã xác nhận'}])
 engine.order_intake.poll()
 run=next(r for r in rows(store) if r['state']=='awaiting_evidence')
 assert json.loads(run['payload'])['messages']==['photo','ok']
 engine.order_intake.evidence_saved('wa-1',run['id'],{'image_base64':base64.b64encode(PNG).decode(),'source_message_ids':['photo','ok'],'directory':r'\\nas\files\confirmed'})
 engine.order_intake.poll();engine.order_intake.poll()
 assert len(engine.erp.calls)==1
 assert float(engine.erp.calls[0]['orders'][0]['so_luong'])==120
 assert all(m['private'] for m in engine.cw.sent)

def test_quantity_followup_after_private_question_reuses_photo(intake):
 from unittest.mock import patch
 settings,store,engine=intake
 capture(store,'photo',text='In mẫu này',images=[IMAGE],timestamp=time.time()-250)
 engine.order_intake.poll();old=rows(store)[0]
 with store.db() as db:
  p=json.loads(old['payload']);p.pop('request_id',None)
  db.execute("UPDATE intake_runs SET state='review',payload=? WHERE id=?",(json.dumps(p),old['id']))
  db.execute('INSERT INTO agent_actions VALUES(?,?,?,?,?,?)',('asked',old['id'],'request_customer_clarification',json.dumps({'missing_fields':['quantity']}),'done',json.dumps({'state':'internal_preview'})))
 capture(store,'qty',text='120 cái',timestamp=time.time()-130)
 with patch.object(engine.order_intake,'analyze') as a:
  engine.order_intake.poll()
  assert [m['message_id'] for _,m in a.call_args.args[2]]==['photo','qty']
