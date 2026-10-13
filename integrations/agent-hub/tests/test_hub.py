import hashlib
import hmac
import json
import time
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from hub.app import create_app
from hub.config import Settings
from hub.engine import Engine
from hub.models import Capture, Decision
from hub.store import Store


class FakeCW:
    def __init__(self):
        self.sent = []
        self.state = "pending"
        self.assignee = None
        self.fail = False

    def conversation(self, conversation):
        return {"id": conversation, "status": self.state, "meta": {"assignee": self.assignee}}

    def history(self, conversation):
        return [
            {"id": 5, "content": "Xin chào", "message_type": 0, "private": False},
            {"id": 8, "content": "Private customer credentials", "message_type": 1, "private": True},
        ]

    def message(self, conversation, payload):
        self.sent.append(payload)
        if self.fail:
            raise TimeoutError("Simulated lost response")
        return {"id": len(self.sent)}

    def status(self, conversation, status):
        self.state = status
        return {"status": status}

    def create_thread(self, inbox, identifier, name):
        return 10, 20


class FakeAgent:
    def __init__(self):
        self.decision = Decision(action="reply", reply="Chào bạn!", evidence=["built-in:greeting"])
        self.callback = None
        self.context = None

    def decide(self, context):
        self.context = context
        if self.callback:
            self.callback()
        return self.decision


class FakeERP:
    def __init__(self):
        self.calls = []

    def create_order(self, payload):
        self.calls.append(payload)
        return {"orders": [{"ma_don_hang": "TEST-001"}]}


@pytest.fixture
def setup(tmp_path):
    settings = Settings(
        database=str(tmp_path / "hub.db"),
        admin_token="a" * 32,
        ingest_token="i" * 32,
        webhook_secret="s" * 32,
        cw_bot_id=1,
        inboxes={"wa-1": {"inbox_id": 1, "channel": "whatsapp", "delivery_enabled": True}},
    )
    store = Store(settings.database)
    engine = Engine(settings, store, FakeCW(), FakeAgent(), FakeERP())
    return settings, store, engine


def message(kind="incoming", **changes):
    payload = {
        "event": "message_created",
        "account": {"id": 1},
        "inbox": {"id": 1},
        "conversation": {"id": 10},
        "id": 5,
        "message_type": kind,
        "private": False,
        "content": "Xin chào",
        "content_attributes": {},
    }
    payload.update(changes)
    return payload


def signed(settings, payload, timestamp=None):
    body = json.dumps(payload).encode()
    timestamp = str(int(time.time()) if timestamp is None else timestamp)
    digest = hmac.new(
        settings.webhook_secret.encode(), timestamp.encode() + b"." + body, hashlib.sha256
    ).hexdigest()
    return body, {"X-Chatwoot-Timestamp": timestamp, "X-Chatwoot-Signature": "sha256=" + digest}


def test_duplicate_webhook_one_reply(setup):
    settings, store, engine = setup
    for _ in range(3):
        engine.accept_webhook(message())
    engine.process_one()
    assert not engine.process_one()
    assert len(store.recent("effects")) == 1
    assert not engine.cw.sent


def test_concurrent_duplicate_claim(setup):
    settings, store, engine = setup
    engine.accept_webhook(message())
    with ThreadPoolExecutor(max_workers=5) as pool:
        results = list(pool.map(lambda _: store.claim(), range(5)))
    assert len([r for r in results if r]) == 1


def test_human_takeover_during_generation(setup):
    settings, store, engine = setup
    engine.agent.callback = lambda: store.set_owner(10, "human")
    engine.accept_webhook(message())
    engine.process_one()
    assert not store.recent("effects")


def test_chatwoot_takeover_without_webhook(setup):
    settings, store, engine = setup
    engine.agent.callback = lambda: setattr(engine.cw, "assignee", {"id": 3})
    engine.accept_webhook(message())
    engine.process_one()
    assert not store.recent("effects")
    assert store.ownership(10)[0] == "human"


def test_private_and_echo_never_sent(setup):
    settings, store, engine = setup
    assert not engine.accept_webhook(message("outgoing", private=True))
    assert not engine.accept_webhook(
        message("outgoing", content_attributes={"phucthanh": {"origin": "external_echo"}})
    )
    assert not store.recent("jobs")


def test_staff_message_stops_ai_immediately(setup):
    settings, store, engine = setup
    engine.accept_webhook(message("outgoing"))
    assert store.ownership(10)[0] == "human"


def test_missing_provider_handoff(setup):
    settings, store, engine = setup
    engine.agent.decision = Decision(action="handoff", reason="Cần nhân viên")
    engine.accept_webhook(message())
    engine.process_one()
    assert store.ownership(10)[0] == "human"
    assert len(store.recent("effects")) == 2


def test_private_history_excluded(setup):
    settings, store, engine = setup
    engine.accept_webhook(message())
    engine.process_one()
    assert len(engine.agent.context["messages"]) == 1


def test_media_handoff(setup):
    settings, store, engine = setup
    engine.accept_webhook(message(attachments=[{"id": 1}]))
    engine.process_one()
    assert engine.agent.context is None
    assert store.ownership(10)[0] == "human"


def test_lost_response_not_replayed(setup):
    settings, store, engine = setup
    settings.mode = "live"
    engine.cw.fail = True
    engine.accept_webhook(message())
    engine.process_one()
    engine.accept_webhook(message())
    assert not engine.process_one()
    assert len(engine.cw.sent) == 1
    assert store.recent("effects")[0]["state"] == "uncertain"


def test_restart_marks_processing_uncertain(setup):
    settings, store, engine = setup
    engine.accept_webhook(message())
    store.claim()
    store.recover()
    assert not store.claim()
    assert store.recent("jobs")[0]["state"] == "uncertain"


def test_signature_and_auth(setup):
    settings, store, engine = setup
    with TestClient(create_app(settings, engine, start_worker=False)) as client:
        body, headers = signed(settings, message())
        assert client.post("/webhooks/chatwoot", content=body, headers=headers).status_code == 200
        assert client.post("/webhooks/chatwoot", content=body + b" ", headers=headers).status_code == 401
        body, headers = signed(settings, message(), timestamp=1)
        assert client.post("/webhooks/chatwoot", content=body, headers=headers).status_code == 401
        assert client.get("/admin/status").status_code == 401
        assert (
            client.get(
                "/admin/status", headers={"Authorization": "Bearer " + settings.admin_token}
            ).status_code
            == 200
        )


def test_wrong_account_or_inbox(setup):
    settings, store, engine = setup
    with pytest.raises(ValueError):
        engine.accept_webhook(message(account={"id": 2}))
    with pytest.raises(ValueError):
        engine.accept_webhook(message(inbox={"id": 2}))


def test_captures_account_scoped_and_revisions(setup):
    settings, store, engine = setup
    capture = Capture(
        account="wa-1", thread_id="123@c.us", message_id="m1", display_name="A", text="ok", timestamp=1
    )
    first = store.capture(capture)
    assert store.capture(capture) == first
    store.capture(capture.model_copy(update={"account": "wa-2"}))
    store.capture(capture.model_copy(update={"revision": 1, "text": "edited"}))
    assert store.status()["captures"] == 3
    with pytest.raises(ValueError):
        store.capture(capture.model_copy(update={"text": "changed without revision"}))


def test_erp_draft_never_auto_submitted(setup):
    settings, store, engine = setup
    engine.agent.decision = Decision(action="draft_order", orders=[{"ma_san_pham": "TEST", "so_luong": 2}])
    engine.accept_webhook(message())
    engine.process_one()
    assert len(store.recent("drafts")) == 1
    assert not engine.erp.calls
    with pytest.raises(ValueError):
        engine.approve_order(store.recent("drafts")[0]["id"])


def test_erp_requires_mapping_and_one_approval(setup):
    settings, store, engine = setup
    engine.agent.decision = Decision(action="draft_order", orders=[{"ma_san_pham": "TEST", "so_luong": 2}])
    engine.accept_webhook(message())
    engine.process_one()
    key = store.recent("drafts")[0]["id"]
    settings.mode, settings.erp_write = "live", True
    with pytest.raises(ValueError):
        engine.approve_order(key)
    store.bind("wa-1", "123@c.us", "A", 10, 20)
    with store.db() as db:
        db.execute("UPDATE threads SET erp_group='Human verified' WHERE conversation=10")
    engine.approve_order(key)
    with pytest.raises(ValueError):
        engine.approve_order(key)
    assert len(engine.erp.calls) == 1
    assert engine.erp.calls[0]["request_id"] == "chatwoot:" + key


def test_outgoing_exact_thread_and_duplicate(setup):
    settings, store, engine = setup
    settings.mode = "live"
    store.bind("wa-1", "123@c.us", "Same name", 10, 20)
    for _ in range(3):
        engine.accept_webhook(message("outgoing", content="` ${x} \\ xin chào"))
    engine.process_one()
    assert len(store.recent("deliveries")) == 1
    assert store.recent("deliveries")[0]["thread_id"] == "123@c.us"


def test_delivery_claim_never_reissued(setup):
    settings, store, engine = setup
    settings.mode, settings.cw_url, settings.cw_token = "live", "http://localhost", "test"
    store.bind("wa-1", "123@c.us", "A", 10, 20)
    with TestClient(create_app(settings, engine, start_worker=False)) as client:
        engine.accept_webhook(message("outgoing"))
        engine.process_one()
        headers = {"Authorization": "Bearer " + settings.ingest_token}
        assert client.post("/adapters/wa-1/claim", headers=headers).json()["item"]
        assert client.post("/adapters/wa-1/claim", headers=headers).json()["item"] is None
        store.recover()
        assert store.recent("deliveries")[0]["state"] == "uncertain"


def test_ai_delivery_cancelled_after_takeover(setup):
    settings, store, engine = setup
    settings.mode, settings.cw_url, settings.cw_token = "live", "http://localhost", "test"
    store.bind("wa-1", "123@c.us", "A", 10, 20)
    with TestClient(create_app(settings, engine, start_worker=False)) as client:
        engine.accept_webhook(
            message("outgoing", content_attributes={"phucthanh": {"origin": "ai", "generation": 0}})
        )
        engine.process_one()
        store.set_owner(10, "human")
        headers = {"Authorization": "Bearer " + settings.ingest_token}
        assert client.post("/adapters/wa-1/claim", headers=headers).json()["item"] is None
        assert store.recent("deliveries")[0]["state"] == "blocked"


def test_newer_customer_message_suppresses_stale_reply(setup):
    settings, store, engine = setup
    engine.cw.history = lambda cid: [{"id": 99, "content": "Updated request", "message_type": 0}]
    engine.accept_webhook(message())
    engine.process_one()
    assert not store.recent("effects")


def test_assigned_agent_bot_is_not_a_human(setup):
    settings, store, engine = setup
    engine.cw.assignee = {"id": 1, "type": "agent_bot"}
    engine.accept_webhook(message())
    engine.process_one()
    assert len(store.recent("effects")) == 1


def test_repeated_capture_timestamp_does_not_conflict(setup):
    settings, store, engine = setup
    capture = Capture(
        account="wa-1", thread_id="1@c.us", message_id="1", display_name="A", text="ok", timestamp=1
    )
    assert store.capture(capture) == store.capture(capture.model_copy(update={"timestamp": 2}))


def test_gemini_rejects_unapproved_evidence(setup, monkeypatch):
    import httpx

    from hub.clients import Gemini

    settings, store, engine = setup
    settings.gemini_key = "test-key-not-real"

    def respond(request):
        assert request.headers["x-goog-api-key"] == "test-key-not-real"
        assert "test-key-not-real" not in str(request.url)
        return httpx.Response(
            200,
            json={
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {
                                    "text": json.dumps(
                                        {
                                            "action": "reply",
                                            "reply": "Invented price",
                                            "evidence": ["unknown-source"],
                                        }
                                    )
                                }
                            ]
                        }
                    }
                ]
            },
        )

    original = httpx.Client
    monkeypatch.setattr(httpx, "Client", lambda **kw: original(transport=httpx.MockTransport(respond), **kw))
    assert Gemini(settings).decide({"messages": []}).action == "handoff"


def test_gemini_invalid_json_becomes_handoff(setup):
    settings, store, engine = setup

    def fail(context):
        raise ValueError("Invalid model output")

    engine.agent.decide = fail
    engine.accept_webhook(message())
    engine.process_one()
    assert store.ownership(10)[0] == "human"


def test_relay_spools_without_network(tmp_path):
    from types import SimpleNamespace

    from support_adapter.chatwoot_relay import Relay

    relay = Relay({"database": str(tmp_path / "relay.db"), "channel_accounts": {"whatsapp": "wa-1"}})
    msg = SimpleNamespace(
        channel="whatsapp",
        chat_id="123@c.us",
        message_id="m1",
        chat_name="A",
        sender="Customer",
        text="ok",
        attachments=(),
        ts=1,
    )
    relay.capture(msg)
    relay.capture(msg)
    with relay.db() as db:
        assert db.execute("SELECT count(*) FROM spool").fetchone()[0] == 1


def test_relay_send_passes_text_as_argument(tmp_path, monkeypatch):
    import sys
    from threading import Lock
    from types import ModuleType, SimpleNamespace

    from support_adapter.chatwoot_relay import Relay

    calls = []

    def evaluate(script, argument):
        calls.append((script, argument))
        if len(calls) == 1:
            return {"id": "123@c.us", "name": "A"}
        return {"id": "platform-1", "ack": 1}

    channel = ModuleType("channels.whatsapp_wpp")
    channel._get_wa_page = lambda: SimpleNamespace(evaluate=evaluate)
    core = ModuleType("core")
    core.runtime = SimpleNamespace(SYSTEM_STATUS="RUNNING", whatsapp_lock=Lock())
    policy = ModuleType("core.policy")
    policy.allowed = lambda *args: True
    monkeypatch.setitem(sys.modules, "channels", ModuleType("channels"))
    monkeypatch.setitem(sys.modules, "channels.whatsapp_wpp", channel)
    monkeypatch.setitem(sys.modules, "core", core)
    monkeypatch.setitem(sys.modules, "core.policy", policy)
    relay = Relay({"database": str(tmp_path / "relay.db")})
    content = "` ${danger} tiếng Việt \\ newline\n"
    state, platform, detail = relay.send_whatsapp({"thread_id": "123@c.us", "message": {"content": content}})
    assert state == "confirmed"
    assert calls[1][1]["text"] == content
    assert content not in calls[1][0]


def test_live_capture_does_not_enable_ai_writes(setup):
    settings, store, engine = setup
    settings.inboxes["wa-1"]["capture_enabled"] = True
    payload = {
        "account": "wa-1",
        "thread_id": "desktop-thread",
        "message_id": "new-1",
        "display_name": "Trial",
        "sender": "Customer",
        "direction": "incoming",
        "origin": "customer",
        "text": "Xin chào",
        "attachments": [],
        "timestamp": 2000,
        "revision": 0,
        "recalled": False,
    }
    engine.process_capture("capture-only", payload)
    assert len(engine.cw.sent) == 1
    assert engine.cw.sent[0]["message_type"] == "incoming"
    assert store.thread(account="wa-1", thread_id="desktop-thread")["conversation"] == 10
    engine.process_incoming("ai-review-only", message())
    assert len(engine.cw.sent) == 1
    assert any(e["state"] == "review" for e in store.recent("effects"))
    assert settings.mode == "review"


def test_group_names_sync_existing_only_and_retry(setup):
    settings, store, engine = setup
    settings.inboxes["wa-1"]["capture_enabled"] = True
    store.bind("wa-1", "g123", "old", 10, 20)
    store.bind("wa-1", "g456", "old", 11, 21)
    calls = []
    engine.cw.rename_contact = lambda contact, name: calls.append((contact, name))
    client = TestClient(create_app(settings, engine, start_worker=False))
    url = "/adapters/wa-1/thread-names"
    payload = {"names": {"g123": "Nhóm trùng tên", "g456": "Nhóm trùng tên", "g789": "Unseen"}}
    assert client.post(url, json=payload).status_code == 401
    headers = {"Authorization": "Bearer " + settings.ingest_token}
    assert client.post(url, json=payload, headers=headers).json() == {"updated": 2}
    assert calls == [(20, "Nhóm trùng tên"), (21, "Nhóm trùng tên")]
    assert client.post(url, json=payload, headers=headers).json() == {"updated": 0}
    assert store.thread(account="wa-1", thread_id="g789") is None
    assert engine.cw.sent == []
    settings.inboxes["wa-1"]["capture_enabled"] = False
    assert client.post(url, json=payload, headers=headers).status_code == 409
