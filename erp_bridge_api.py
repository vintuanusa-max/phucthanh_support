"""Scoped status/retry API. Does not expose bridge configuration or credentials."""
import hmac
import json
import os
import threading

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field


class ProductSelection(BaseModel):
    product_codes: list[str] = Field(min_length=1,max_length=30)


class Control(BaseModel):
    enabled: bool


def build_router(bridge):
    config_lock = threading.Lock()
    def authorized(x_zalo_token: str = Header(default="")):
        token = bridge.settings().get("token", "")
        if len(token) < 32 or not hmac.compare_digest(token, x_zalo_token):
            raise HTTPException(401, "Sai mã xác thực tích hợp")

    router = APIRouter(prefix="/api/erp-integration", dependencies=[Depends(authorized)])

    @router.post("/control")
    def control(req: Control):
        with config_lock:
            cfg = bridge.settings()
            cfg["enabled"] = req.enabled
            path = bridge.root / "erp_config.json"
            temporary = path.with_suffix(".tmp")
            temporary.write_text(json.dumps(cfg,ensure_ascii=False),encoding="utf-8")
            os.replace(temporary,path)
        return {"enabled":req.enabled}

    @router.get("/intake")
    def intake():
        with bridge.store.db() as db:
            rows = db.execute("SELECT id,group_name,source,state,detail,attempts,payload FROM intake WHERE state != 'discarded' ORDER BY rowid DESC LIMIT 100").fetchall()
        items = []
        for row in rows:
            item = dict(row)
            payload = item.pop("payload")
            item["lines"] = (json.loads(payload).get("orders", []) if payload else [])
            items.append(item)
        return {"enabled": bool(bridge.settings().get("enabled")), "protocol": 1,
                "items": items, "capabilities": {"discard_failed": True, "intake_sources": ["zalo", "whatsapp"]}}

    @router.post("/intake/{request_id}/discard")
    def discard(request_id: str):
        if len(request_id) != 64 or any(c not in "0123456789abcdef" for c in request_id):
            raise HTTPException(422, "Mã yêu cầu không hợp lệ")
        with bridge.store.db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT state FROM intake WHERE id=?", (request_id,)).fetchone()
            if not row or row["state"] not in ("failed", "discarded"):
                raise HTTPException(409, "Chỉ xóa đơn nhận sai đang chờ xử lý")
            db.execute("UPDATE intake SET state='discarded',detail='Đã bỏ qua theo yêu cầu quản trị' WHERE id=?", (request_id,))
        # Retain original ID so rescanning cannot recreate the discarded intake.
        return {"status": "discarded"}

    @router.post("/intake/{request_id}/products")
    def select_products(request_id: str, req: ProductSelection):
        with bridge.store.db() as db:
            # Reserve writer before reading so the background transport cannot race a correction.
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT state,payload FROM intake WHERE id=?", (request_id,)).fetchone()
            if not row or row["state"] != "failed" or not row["payload"]:
                raise HTTPException(409,"Chỉ chọn mã hàng cho đơn chờ chưa tạo được trên ERP")
            payload = json.loads(row["payload"])
            lines = payload["orders"]
            if len(lines) != len(req.product_codes) or any(not code.strip() or len(code)>200 for code in req.product_codes):
                raise HTTPException(422,"Cần chọn đúng một mã hàng cho mỗi dòng")
            for line, code in zip(lines,req.product_codes):
                line.setdefault("ten_mau", line.get("ma_san_pham"))
                line["ma_san_pham"] = code
            db.execute("UPDATE intake SET payload=?,state='ready',detail='',next_try=0 WHERE id=?",
                       (json.dumps(payload,ensure_ascii=False),request_id))
        # Keep the SAME request_id: if ERP already accepted it, a changed payload is rejected,
        # never turned into a second order. Only failed validation is correctable here.
        return {"status":"queued"}

    @router.post("/intake/{request_id}/retry")
    def retry(request_id: str):
        with bridge.store.db() as db:
            changed = db.execute("""UPDATE intake SET state=CASE WHEN payload IS NULL THEN 'captured' ELSE 'ready' END,
                detail='',next_try=0 WHERE id=? AND state='failed'""", (request_id,)).rowcount
        if not changed:
            raise HTTPException(409, "Chỉ thử lại đơn đang lỗi")
        return {"status": "queued"}

    return router
