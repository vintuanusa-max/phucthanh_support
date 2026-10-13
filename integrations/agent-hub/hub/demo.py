"""Local review server with synthetic data only; never calls Gemini/Chatwoot/ERP."""

import tempfile
from pathlib import Path

import uvicorn

from hub.app import create_app
from hub.config import Settings
from hub.engine import Engine
from hub.models import Decision
from hub.store import Store

TOKEN = "local-review-only-synthetic-data-123456"


class DemoChatwoot:
    def conversation(self, conversation):
        return {"id": conversation, "status": "pending", "meta": {}}

    def history(self, conversation):
        text = {101: "Xin chào", 102: "Tôi muốn gặp nhân viên", 103: "Đặt 20 sản phẩm mẫu"}[conversation]
        return [{"id": conversation, "content": text, "message_type": 0, "private": False}]


class DemoAgent:
    def decide(self, context):
        cid = context["conversation_id"]
        if cid == 101:
            return Decision(
                action="reply",
                reply="Chào bạn, Phúc Thành có thể hỗ trợ gì cho bạn?",
                evidence=["built-in:greeting"],
            )
        if cid == 102:
            return Decision(action="handoff", reason="Khách yêu cầu gặp nhân viên")
        return Decision(action="draft_order", orders=[{"ma_san_pham": "DEMO-ONLY", "so_luong": 20}])


def main():
    directory = tempfile.mkdtemp(prefix="phucthanh-review-")
    settings = Settings(
        database=str(Path(directory) / "review.db"),
        admin_token=TOKEN,
        ingest_token=TOKEN,
        webhook_secret=TOKEN,
        inboxes={"demo": {"inbox_id": 1, "channel": "native"}},
    )
    store = Store(settings.database)
    engine = Engine(settings, store, DemoChatwoot(), DemoAgent(), None)
    for cid in (101, 102, 103):
        engine.accept_webhook(
            {
                "event": "message_created",
                "account": {"id": 1},
                "inbox": {"id": 1},
                "conversation": {"id": cid},
                "id": cid,
                "message_type": "incoming",
                "private": False,
                "content": DemoChatwoot().history(cid)[0]["content"],
            }
        )
        engine.process_one()
    uvicorn.run(create_app(settings, engine, start_worker=False), host="127.0.0.1", port=8096)


if __name__ == "__main__":
    main()
