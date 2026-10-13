import json
import time

import pytest
from fastapi.testclient import TestClient
from test_hub import message
from test_hub import setup as hub_setup

from hub.app import create_app
from hub.models import Capture
from zalo_desktop.sender import Journal, Sender


@pytest.fixture(name="setup")
def sender_setup(tmp_path):
    return hub_setup.__wrapped__(tmp_path)


def configure(settings, store):
    settings.inboxes["wa-1"].update(
        channel="zalo",
        human_delivery_enabled=True,
        desktop_sender=True,
        delivery_after=time.time() - 5,
        excluded_sender_ids=[2],
    )
    store.bind("wa-1", "g123", "Same name", 10, 20)
    store.bind("wa-1", "g456", "Same name", 11, 21)


def staff(**changes):
    return message("outgoing", sender={"id": 1, "type": "user"}, created_at=time.time(), **changes)


def test_human_live_ai_review_private_and_old_blocked(setup):
    settings, store, engine = setup
    configure(settings, store)
    assert not engine.accept_webhook(staff(private=True))
    engine.accept_webhook(staff())
    engine.process_one()
    assert store.recent("deliveries")[0]["state"] == "queued"
    for payload in [staff(id=6, sender_override=None)]:
        payload.pop("sender_override")
        payload["sender"] = {"id": 2, "type": "user"}
        engine.accept_webhook(payload)
    engine.process_one()
    assert store.recent("deliveries")[0]["state"] == "review"
    old = staff(id=7)
    old["created_at"] = 1
    engine.accept_webhook(old)
    engine.process_one()
    assert store.recent("deliveries")[0]["state"] == "blocked"
    assert engine.cw.sent[-1]["private"] is True
    ai = staff(id=8, content_attributes={"phucthanh": {"origin": "ai", "generation": 0}})
    store.set_owner(10, "ai")
    ai["content_attributes"]["phucthanh"]["generation"] = store.ownership(10)[1]
    engine.accept_webhook(ai)
    engine.process_one()
    assert store.recent("deliveries")[0]["state"] == "review"


def test_prepare_echo_race_dedup_and_same_name_routing(setup):
    settings, store, engine = setup
    configure(settings, store)
    client = TestClient(create_app(settings, engine, start_worker=False))
    headers = {"Authorization": "Bearer " + settings.ingest_token}
    payload = staff(conversation={"id": 11})
    for _ in range(3):
        engine.accept_webhook(payload)
    engine.process_one()
    item = client.post("/adapters/wa-1/claim", headers=headers).json()["item"]
    assert item["thread_id"] == "g456"
    cid = str(int(time.time() * 1000))
    assert (
        client.post(
            "/adapters/wa-1/prepare/" + item["id"], headers=headers, json={"client_id": cid}
        ).status_code
        == 200
    )
    cap = Capture(
        account="wa-1",
        thread_id="g456",
        display_name="Same name",
        message_id="server-1",
        client_message_id=cid,
        direction="outgoing",
        text=payload["content"],
        timestamp=time.time(),
    )
    store.capture(cap)
    engine.process_one()
    assert store.recent("deliveries")[0]["state"] == "confirmed"
    assert not engine.cw.sent  # no duplicate public echo
    assert (
        client.post(
            "/adapters/wa-1/results/" + item["id"], headers=headers, json={"state": "submitted"}
        ).status_code
        == 200
    )
    assert store.recent("deliveries")[0]["state"] == "confirmed"
    assert client.post("/adapters/wa-1/claim", headers=headers).json()["item"] is None
    assert not store.reconcile_echo(cap.model_copy(update={"thread_id": "g123"}).model_dump())


def test_claim_rechecks_disabled_and_expired(setup):
    settings, store, engine = setup
    configure(settings, store)
    engine.accept_webhook(staff())
    engine.process_one()
    settings.inboxes["wa-1"]["human_delivery_enabled"] = False
    client = TestClient(create_app(settings, engine, start_worker=False))
    assert (
        client.post(
            "/adapters/wa-1/claim", headers={"Authorization": "Bearer " + settings.ingest_token}
        ).status_code
        == 409
    )


def test_sender_crash_journal_never_resends(tmp_path):
    journal = Journal(tmp_path / "sender.db")
    assert journal.reserve("x")
    journal.db.close()
    journal = Journal(tmp_path / "sender.db")
    assert not journal.reserve("x")
    assert json.loads(journal.pending()[0][1])["state"] == "uncertain"
    journal.db.close()


def test_sender_lost_result_only_retries_report(tmp_path):
    class Response:
        def raise_for_status(self):
            pass

    class HTTP:
        def __init__(self):
            self.calls = []

        def post(self, url, **kw):
            self.calls.append(url)
            return Response()

    sender = object.__new__(Sender)
    sender.journal = Journal(tmp_path / "s.db")
    sender.http = HTTP()
    sender.base = "/adapter"
    sender.halted = False
    calls = []

    def transport(item, action, client_id=""):
        calls.append(action)
        return (
            {"state": "ready", "client_id": "1791810332064"}
            if action == "prepare"
            else {"state": "uncertain", "detail": "Lost response"}
        )

    sender.transport = transport
    item = {"id": "same"}
    sender.dispatch(item)
    sender.dispatch(item)
    assert calls == ["prepare", "send"]
    sender.report()
    sender.report()
    assert len([x for x in sender.http.calls if "/results/" in x]) == 1
