import base64
import time

import httpx
import pytest
from fastapi.testclient import TestClient
from test_hub import message
from test_hub import setup as hub_setup

from hub.app import create_app
from hub.clients import Chatwoot, Gemini
from hub.models import Capture, Decision
from zalo_desktop.media import fetch_image, validate_url

PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jf1sAAAAASUVORK5CYII="
)
IMAGE = {"mime_type": "image/png", "data": base64.b64encode(PNG).decode()}


@pytest.fixture
def trial_setup(tmp_path):
    settings, store, engine = hub_setup.__wrapped__(tmp_path)
    settings.cw_url = "http://fake"
    settings.cw_token = "fake"
    settings.gemini_key = "fake"
    cfg = settings.inboxes["wa-1"]
    cfg.update(ai_trials={"g123": {"enabled_after": time.time() - 10}})
    store.bind("wa-1", "g123", "Trial", 10, 20)
    return settings, store, engine


def incoming(**changes):
    return message(
        content_attributes={"phucthanh": {"origin": "capture", "source_timestamp": time.time()}}, **changes
    )


def test_scope_only_and_no_old_trigger(trial_setup):
    settings, store, engine = trial_setup
    engine.process_incoming("outside", incoming(conversation={"id": 11}))
    old = incoming()
    old["content_attributes"]["phucthanh"]["source_timestamp"] -= 60
    engine.process_incoming("old", old)
    assert engine.agent.context is None
    engine.process_incoming("inside", incoming())
    assert len(engine.cw.sent) == 1
    assert engine.cw.sent[0]["content_attributes"]["phucthanh"]["origin"] == "ai"
    assert not engine.erp.calls


def test_handoff_real_in_review_and_stays_human(trial_setup):
    settings, store, engine = trial_setup
    engine.process_incoming("human", incoming(content="Cho tôi gặp nhân viên"))
    assert engine.cw.state == "open"
    assert engine.cw.sent[-1]["private"] is True
    assert store.ownership(10)[0] == "human"
    engine.process_incoming("later", incoming())
    assert engine.agent.context is None


def test_media_capture_bound_to_own_message(trial_setup):
    settings, store, engine = trial_setup
    settings.inboxes["wa-1"]["capture_enabled"] = True
    cap = Capture(
        account="wa-1",
        thread_id="g123",
        message_id="photo",
        display_name="Trial",
        timestamp=time.time(),
        images=[IMAGE],
    )
    key = store.capture(cap)
    assert store.capture(cap) == key
    engine.process_one()
    sent = engine.cw.sent[0]
    assert sent["_images"] == [IMAGE]
    msg = message(id=1, attachments=[{"file_type": "image"}], content_attributes=sent["content_attributes"])
    engine.cw.history = lambda conv: []
    engine.process_incoming("photo-in", msg)
    assert engine.agent.context["images"] == [IMAGE]
    assert len(engine.cw.sent) == 2
    assert engine.captured_images(11, msg) == []
    assert engine.captured_images(10, {**msg, "id": 99}) == []


def test_missing_image_and_provider_error_handoff(trial_setup):
    settings, store, engine = trial_setup
    engine.process_incoming("missing", incoming(attachments=[{"file_type": "image"}]))
    assert store.ownership(10)[0] == "human"
    assert engine.agent.context is None
    store.set_owner(10, "ai")
    engine.cw.state = "pending"

    def fail(ctx):
        raise TimeoutError()

    engine.agent.decide = fail
    engine.process_incoming("failed", incoming())
    assert store.ownership(10)[0] == "human"
    assert engine.cw.state == "open"


def test_ingest_rejects_image_outside_trial(trial_setup):
    settings, store, engine = trial_setup
    client = TestClient(create_app(settings, engine, start_worker=False))
    cap = Capture(
        account="wa-1",
        thread_id="g999",
        message_id="x",
        display_name="Other",
        timestamp=time.time(),
        images=[IMAGE],
    )
    response = client.post(
        "/ingest", json=cap.model_dump(), headers={"Authorization": "Bearer " + settings.ingest_token}
    )
    assert response.status_code == 422
    assert not store.recent("jobs")


def test_human_takes_over_during_image_decision(trial_setup):
    settings, store, engine = trial_setup
    engine.agent.callback = lambda: store.set_owner(10, "human")
    engine.process_incoming("race", incoming())
    assert not engine.cw.sent


def test_scoped_ai_delivery_and_prepare_takeover(trial_setup):
    settings, store, engine = trial_setup
    engine.process_incoming("reply", incoming())
    msg = message(
        "outgoing",
        content_attributes=engine.cw.sent[0]["content_attributes"],
        sender={"type": "agent_bot", "id": 1},
    )
    engine.process_outgoing("send", msg)
    assert store.recent("deliveries")[0]["state"] == "queued"
    client = TestClient(create_app(settings, engine, start_worker=False))
    headers = {"Authorization": "Bearer " + settings.ingest_token}
    assert client.post("/adapters/wa-1/claim", headers=headers).json()["item"]
    store.set_owner(10, "human")
    assert (
        client.post(
            "/adapters/wa-1/prepare/send", headers=headers, json={"client_id": "1791812352132"}
        ).status_code
        == 409
    )


@pytest.mark.parametrize(
    "url",
    [
        "http://photo-stal-1.zdn.vn/a",
        "https://localhost/a",
        "https://photo-stal-1.zdn.vn.evil.test/a",
        "https://user:pass@photo-stal-1.zdn.vn/a",
    ],
)
def test_media_rejects_untrusted_urls(url):
    with pytest.raises(ValueError):
        validate_url(url)


def test_chatwoot_multipart_keeps_marker_and_image(trial_setup):
    settings, _, _ = trial_setup
    cw = Chatwoot(settings)

    def respond(request):
        body = request.read()
        assert b"attachments[]" in body and PNG in body
        assert b'"origin": "capture"' in body
        assert request.headers["content-type"].startswith("multipart/form-data")
        return httpx.Response(200, json={"id": 1})

    cw.http = httpx.Client(base_url="http://fake/", transport=httpx.MockTransport(respond))
    cw.message(
        10,
        {
            "content": "[Image]",
            "private": False,
            "message_type": "incoming",
            "content_attributes": {"phucthanh": {"origin": "capture"}},
            "_images": [IMAGE],
        },
    )


def test_gemini_receives_inline_image_not_base64_in_text(trial_setup, monkeypatch):
    settings, _, _ = trial_setup
    real_client = httpx.Client

    def respond(request):
        import json

        data = json.loads(request.content)
        parts = data["contents"][0]["parts"]
        assert parts[1]["inline_data"] == IMAGE
        assert IMAGE["data"] not in parts[0]["text"]
        decision = Decision(action="reply", reply="Ảnh thử", evidence=["image:current"])
        return httpx.Response(
            200, json={"candidates": [{"content": {"parts": [{"text": decision.model_dump_json()}]}}]}
        )

    monkeypatch.setattr(httpx, "Client", lambda **kw: real_client(transport=httpx.MockTransport(respond)))
    assert Gemini(settings).decide({"images": [IMAGE], "latest_message": "Đọc ảnh"}).action == "reply"


def test_download_validated_cdn_redirect_and_no_auth(monkeypatch):
    real_client = httpx.Client
    calls = []

    def respond(request):
        calls.append(request)
        assert "cookie" not in request.headers and "authorization" not in request.headers
        if len(calls) == 1:
            return httpx.Response(301, headers={"location": "https://photo-stal-1.zadn.vn/test.png"})
        return httpx.Response(200, content=PNG)

    monkeypatch.setattr(httpx, "Client", lambda **kw: real_client(transport=httpx.MockTransport(respond)))
    assert fetch_image({"oriUrl": "https://photo-stal-1.zdn.vn/test.png"}) == IMAGE
    assert len(calls) == 2


def test_download_rejects_redirect_to_local_and_html(monkeypatch):
    real_client = httpx.Client
    calls = []

    def respond(request):
        calls.append(request)
        return httpx.Response(302, headers={"location": "http://127.0.0.1/private"})

    monkeypatch.setattr(httpx, "Client", lambda **kw: real_client(transport=httpx.MockTransport(respond)))
    with pytest.raises(ValueError):
        fetch_image({"oriUrl": "https://photo-stal-1.zdn.vn/test.png"})
    assert len(calls) == 1


def test_recent_incoming_image_followed_by_text(trial_setup):
    settings, store, engine = trial_setup
    settings.inboxes["wa-1"]["capture_enabled"] = True
    key = store.capture(
        Capture(
            account="wa-1",
            thread_id="g123",
            message_id="photo",
            display_name="Trial",
            timestamp=time.time(),
            images=[IMAGE],
        )
    )
    assert key
    engine.process_one()
    prior = message(
        id=1, attachments=[{"file_type": "image"}], content_attributes=engine.cw.sent[0]["content_attributes"]
    )
    engine.cw.history = lambda conv: [prior]
    engine.process_incoming("followup", incoming(id=5, content="Đọc ảnh trên"))
    assert engine.agent.context["images"] == [IMAGE]
    assert engine.agent.context["image_message_ids"] == [1]


def test_handoff_assigns_real_staff_after_note(trial_setup):
    settings, store, engine = trial_setup
    settings.inboxes["wa-1"]["ai_trials"]["g123"]["handoff_user_id"] = 1
    assigned = []
    engine.cw.assign = lambda conv, uid: assigned.append((conv, uid)) or {"id": uid}
    engine.process_incoming("assign-handoff", incoming(content="Cho tôi gặp nhân viên"))
    assert assigned == [(10, 1)]
    assert engine.cw.state == "open" and store.ownership(10)[0] == "human"


def test_jpeg_xl_from_zalo_is_decoded_before_upload():
    from io import BytesIO

    import pillow_jxl  # noqa: F401
    from PIL import Image

    from zalo_desktop.media import normalize_image

    buf = BytesIO()
    Image.new("RGB", (8, 6), (200, 30, 10)).save(buf, format="JXL", lossless=True)
    converted = normalize_image(buf.getvalue())
    assert converted["mime_type"] == "image/jpeg"
    with Image.open(BytesIO(base64.b64decode(converted["data"]))) as image:
        assert image.size == (8, 6)
        assert abs(image.getpixel((0, 0))[0] - 200) < 3


def test_trial_creates_real_order_once_and_hands_to_staff(trial_setup):
    settings, store, engine = trial_setup
    settings.erp_write = True
    settings.inboxes["wa-1"]["ai_trials"]["g123"]["erp_orders_enabled"] = True
    with store.db() as db:
        db.execute("UPDATE threads SET erp_group='Trial' WHERE conversation=10")
    engine.agent.decision = Decision(
        action="draft_order", orders=[{"ma_san_pham": "SKU1", "so_luong": 2}], source_message_ids=[5]
    )
    engine.process_incoming("order1", incoming(content="Đặt SKU1 số lượng 2"))
    assert len(engine.erp.calls) == 1
    assert engine.erp.calls[0]["request_id"] == "chatwoot:order1"
    assert "Đặt SKU1 số lượng 2" in engine.erp.calls[0]["orders"][0]["ghi_chu_mau_do"]
    assert store.recent("drafts")[0]["state"] == "created"
    assert store.ownership(10)[0] == "human"
    store.set_owner(10, "ai")
    engine.cw.state = "pending"
    engine.agent.decision = Decision(
        action="draft_order", orders=[{"ma_san_pham": "SKU1", "so_luong": 2}], source_message_ids=[5, 6]
    )
    engine.process_incoming("order2", incoming(id=6, content="Đơn đó nhé"))
    assert len(engine.erp.calls) == 1


def test_order_timeout_never_retries_creation(trial_setup):
    settings, store, engine = trial_setup
    settings.erp_write = True
    settings.inboxes["wa-1"]["ai_trials"]["g123"]["erp_orders_enabled"] = True
    with store.db() as db:
        db.execute("UPDATE threads SET erp_group='Trial' WHERE conversation=10")
    calls = []

    def fail(payload):
        calls.append(payload)
        raise TimeoutError()

    engine.erp.create_order = fail
    engine.agent.decision = Decision(
        action="draft_order", orders=[{"ma_san_pham": "SKU1", "so_luong": 2}], source_message_ids=[5]
    )
    engine.process_incoming("uncertain-order", incoming())
    assert store.recent("drafts")[0]["state"] == "uncertain"
    with pytest.raises(ValueError):
        engine.approve_order("uncertain-order")
    assert len(calls) == 1
    assert store.ownership(10)[0] == "human"


def test_order_evidence_is_png_and_text_sources_are_required(trial_setup):
    from io import BytesIO

    from PIL import Image

    from hub.order_evidence import evidence_png

    with Image.open(BytesIO(base64.b64decode(evidence_png([IMAGE], 10, [5])))) as image:
        assert image.format == "PNG"
    settings, store, engine = trial_setup
    engine.agent.decision = Decision(
        action="draft_order", orders=[{"ma_san_pham": "SKU1", "so_luong": 2}], source_message_ids=[8]
    )
    engine.process_incoming("bad-source", incoming())
    assert not store.recent("drafts") and not engine.erp.calls


def test_nas_image_not_uploaded_to_chatwoot_but_gemini_can_read(trial_setup):
    settings, store, engine = trial_setup
    settings.inboxes["wa-1"]["capture_enabled"] = True
    cap = Capture(
        account="wa-1",
        thread_id="g123",
        message_id="NASphoto",
        display_name="Trial",
        timestamp=time.time(),
        images=[IMAGE],
        assets=[
            {
                "id": "a" * 64,
                "name": "a.png",
                "kind": "image",
                "state": "ready",
                "relative_path": "Trial/2026-10/originals/a.png",
            }
        ],
    )
    store.capture(cap)
    engine.process_one()
    sent = engine.cw.sent[0]
    assert sent["_media_ids"] and sent["_images"]
    assert "Trial" in sent["content"]
    msg = message(id=1, content_attributes=sent["content_attributes"])
    assert engine.captured_images(10, msg) == [IMAGE]
