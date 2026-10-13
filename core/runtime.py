"""Trạng thái dùng chung giữa các kênh (thay cho biến global trong main.py cũ).

Biến bị gán lại lúc chạy (SYSTEM_STATUS, screenshot_active, erp_bridge) phải đọc
qua module: ``from core import runtime as rt`` rồi dùng ``rt.SYSTEM_STATUS``.
Queue/lock/event không bao giờ bị gán lại nên import tên trực tiếp được.
"""
import collections
import os
import queue
import sys
import threading

from core.paths import ROOT

# Module Telegram Alert nằm ở thư mục cha (giữ như bản cũ).
sys.path.append(str(ROOT.parent))
try:
    import telegram_alert
except ImportError:
    telegram_alert = None

# --- CẤU HÌNH HỆ THỐNG ---
HISTORY_FILE = "processed_history.json"
WHATSAPP_HISTORY_FILE = "whatsapp_history.json"
N8N_WEBHOOK_URL = "https://n8n.vintuan2003apple.synology.me/webhook/nhan-tin"
OPENCLAW_LOCAL_URL = "http://127.0.0.1:18789/api/v1/messages"
WHATSAPP_CDP_PORT = 9223
LOG_FILE = os.path.join(str(ROOT), "zalo_bot.log")

SYSTEM_STATUS = "RUNNING"
screenshot_active = 0
erp_bridge = None  # core.intake.start_erp_bridge() gán khi khởi động

openclaw_queue = queue.Queue()
send_queue = queue.Queue()
wa_send_queue = queue.Queue()
zalo_lock = threading.Lock()
whatsapp_lock = threading.Lock()
_send_worker_busy = threading.Event()
_screenshot_lock = threading.Lock()

# Kết nối Playwright bền vững theo từng thread
_tls = threading.local()
_zalo_scan_event = threading.Event()
_wa_scan_event = threading.Event()

_log_buffer = collections.deque(maxlen=200)
_log_lock = threading.Lock()


def _send_status_to_nas_async(working: bool, activity: str):
    import requests
    urls_to_try = [
        "http://192.168.1.203:8000/api/v1/bot-sync/push-status/zalo",
        "http://192.168.1.203:8000/api/v1/bot-sync/status/zalo",
        "http://192.168.1.203:8000/push-status/zalo",
        "http://192.168.1.203:8000/status/zalo"
    ]
    logs_sample = []
    try:
        if '_log_buffer' in globals() and '_log_lock' in globals():
            with _log_lock:
                logs_sample = list(_log_buffer)[-20:]
    except Exception:
        pass
    payload = {
        "working": working,
        "status": "running",
        "activity": activity,
        "queue_size": 0,
        "logs": logs_sample
    }
    for url in urls_to_try:
        try:
            res = requests.post(url, json=payload, timeout=1.5)
            if res.status_code == 200:
                break
        except Exception:
            pass


def report_status_to_nas(working: bool, activity: str = ""):
    import threading
    threading.Thread(target=_send_status_to_nas_async, args=(working, activity), daemon=True).start()
