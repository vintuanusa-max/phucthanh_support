"""HTTP API của bot (cổng 8000). Đường dẫn và dữ liệu trả về giữ nguyên bản cũ."""
import os
import threading
import time

from fastapi import APIRouter
from fastapi.responses import FileResponse
from pydantic import BaseModel

import config_manager
from channels import whatsapp_wpp, zalo_web
from core import runtime as rt
from core.policy import whatsapp_reply_disabled
from core.runtime import LOG_FILE, _log_buffer, _log_lock, _screenshot_lock, openclaw_queue, send_queue, wa_send_queue
from core.settings import zalo_allowed

router = APIRouter()


@router.get("/config")
def get_bot_config():
    return config_manager.load_config()


@router.post("/config")
def update_bot_config(cfg: dict):
    success = config_manager.save_config(cfg)
    if success:
        return {"status": "success", "message": "Đã cập nhật cấu hình Zalo Bot thành công!", "config": config_manager.load_config()}
    return {"status": "error", "message": "Không thể lưu cấu hình!"}


class SendMessageReq(BaseModel):
    customer_name: str
    message: str


class OpenClawTaskReq(BaseModel):
    customer_name: str
    file_path: str
    action: str


class BroadcastReq(BaseModel):
    message: str
    limit: int = 15


@router.post("/api/scan-now")
def api_scan_now(source: str = "all"):
    if source in ("zalo", "all"):
        zalo_web.trigger_scan()
    if source in ("whatsapp", "all"):
        whatsapp_wpp.trigger_scan()
    return {"status": "ok", "source": source}


@router.get("/api/screenshot")
def api_get_screenshot(customer_name: str, source: str = "zalo"):
    prev = rt.SYSTEM_STATUS
    rt.SYSTEM_STATUS = "PAUSED"
    with _screenshot_lock:
        rt.screenshot_active += 1
    f_path = f"screenshot_{int(time.time())}.png"
    src_lower = source.lower().strip() if source else "zalo"
    if src_lower in ("whatsapp", "wa"):
        success, error_msg = whatsapp_wpp.capture_chat_screenshot(customer_name, f_path)
    else:
        success, error_msg = zalo_web.capture_chat_screenshot(customer_name, f_path)
    with _screenshot_lock:
        rt.screenshot_active -= 1
    rt.SYSTEM_STATUS = prev
    if success:
        return FileResponse(f_path)
    return {"status": "error", "msg": error_msg}


@router.post("/api/send-zalo")
def api_send_zalo(req: SendMessageReq):
    is_disabled = not zalo_allowed(req.customer_name, "receive_messages")
    if is_disabled:
        print(f"⏭️  [Zalo-Send] Bỏ qua gửi tin nhắn vì nhóm nằm trong zalo_disable_reply_groups (Khách: {req.customer_name})")
        return {"status": "skipped", "msg": f"Bỏ qua gửi tin nhắn cho {req.customer_name} do cấu hình chặn phản hồi."}
    send_queue.put({"customer_name": req.customer_name, "message": req.message})
    return {"status": "queued", "msg": "Đã đưa tin nhắn Zalo vào hàng đợi."}


@router.post("/api/send-whatsapp")
def api_send_whatsapp(req: SendMessageReq):
    is_disabled = whatsapp_reply_disabled(req.customer_name, "WA-Send API")
    if is_disabled:
        print(f"⏭️  [WA-Send] Bỏ qua gửi tin nhắn vì nhóm nằm trong whatsapp_disable_reply_groups (Khách: {req.customer_name})")
        return {"status": "skipped", "msg": f"Bỏ qua gửi tin nhắn cho {req.customer_name} do cấu hình chặn phản hồi."}
    wa_send_queue.put({"customer_name": req.customer_name, "message": req.message})
    return {"status": "queued", "msg": "Đã đưa tin nhắn WhatsApp vào hàng đợi."}


@router.post("/api/exit-chat")
def api_exit_chat():
    return zalo_web.exit_chat()


@router.post("/api/broadcast-zalo")
def api_broadcast_zalo(req: BroadcastReq):
    return zalo_web.broadcast(req.message, req.limit)


@router.post("/api/run-openclaw")
def api_run_openclaw(req: OpenClawTaskReq):
    openclaw_queue.put({"customer_name": req.customer_name, "file_path": req.file_path, "action": req.action})
    return {"status": "queued"}


@router.get("/api/status")
def get_status():
    return {
        "status": rt.SYSTEM_STATUS.lower(),
        "queue_size": openclaw_queue.qsize() + send_queue.qsize(),
        "openclaw_queue_size": openclaw_queue.qsize(),
        "send_queue_size": send_queue.qsize()
    }


@router.get("/api/logs")
def api_get_logs(n: int = 100):
    try:
        log_file_path = LOG_FILE
        if os.path.exists(log_file_path):
            with open(log_file_path, "r", encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()
            return {"logs": [line.strip() for line in lines[-n:]]}
    except Exception as e:
        print("Lỗi đọc file log:", e)
    with _log_lock:
        return {"logs": list(_log_buffer)[-n:]}


@router.post("/api/pause")
def pause_system():
    rt.SYSTEM_STATUS = "PAUSED"
    return {"status": "success", "msg": "Đã khóa tay Cô Tiếp Tân. Bạn có thể dùng chuột!"}


@router.post("/api/resume")
def resume_system():
    rt.SYSTEM_STATUS = "RUNNING"
    return {"status": "success", "msg": "Cô Tiếp Tân đã làm việc trở lại!"}


@router.post("/api/stop")
def stop_system():
    rt.SYSTEM_STATUS = "STOPPED"
    print("\n[SYSTEM] STOPPED: Đã dừng Zalo Bot hoàn toàn.")
    threading.Timer(1.0, lambda: os._exit(0)).start()
    return {"status": "stopped", "message": "Zalo Bot is shutting down..."}


# Chẩn đoán WhatsApp Web (logic nằm trong kênh)
router.get("/api/whatsapp-status")(whatsapp_wpp.whatsapp_status)
router.get("/api/whatsapp-debug")(whatsapp_wpp.whatsapp_debug)
router.get("/api/wa-sidebar")(whatsapp_wpp.wa_sidebar_diagnose)
