"""Đẩy dữ liệu sang n8n / OpenClaw (giữ nguyên hành vi cũ)."""
import requests

from core.runtime import N8N_WEBHOOK_URL, OPENCLAW_LOCAL_URL, openclaw_queue
from core.settings import zalo_allowed


def forward_to_n8n(customer_name: str, msg_type: str, content: str, files_list: list = None, source: str = "zalo"):
    if source == "zalo" and not zalo_allowed(customer_name, "auto_order"):
        return
    if files_list is None: files_list = []
    payload = {"source": source, "customer_name": customer_name, "type": msg_type, "content": content, "files": files_list}
    try:
        requests.post(N8N_WEBHOOK_URL, json=payload, timeout=5)
        print(f"🚀 [n8n/{source}] Đã đẩy [{msg_type}] của: {customer_name}")
    except: print(f"❌ [n8n/{source}] Lỗi kết nối")


def openclaw_worker():
    while True:
        task = openclaw_queue.get()
        payload = {"content": f"Khách '{task['customer_name']}' gửi: {task['file_path']}. Nhiệm vụ: {task['action']}", "channel": "api", "user_id": task['customer_name']}
        try: requests.post(OPENCLAW_LOCAL_URL, json=payload, timeout=600)
        except: pass
        openclaw_queue.task_done()
