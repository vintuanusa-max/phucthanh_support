"""Lịch sử tin đã quét (file JSON tương đối theo thư mục chạy, như bản cũ)."""
import datetime
import json
import os

from core.runtime import HISTORY_FILE, WHATSAPP_HISTORY_FILE


def load_history():
    today = datetime.date.today().isoformat()
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if data.get("date") == today:
                return {"messages": set(data.get("messages", []))}
            # Sang ngày mới → tự xóa history cũ
            print(f"🗓️  Ngày mới ({today}), xóa history cũ (ngày {data.get('date', '?')})")
        except: pass
    return {"messages": set()}


def save_history(history):
    today = datetime.date.today().isoformat()
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump({"date": today, "messages": list(history["messages"])}, f, ensure_ascii=False, indent=4)


def load_whatsapp_history():
    if os.path.exists(WHATSAPP_HISTORY_FILE):
        try:
            with open(WHATSAPP_HISTORY_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return {"messages": set(data.get("messages", []))}
        except: pass
    return {"messages": set()}


def save_whatsapp_history(history):
    with open(WHATSAPP_HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump({"messages": list(history["messages"])}, f, ensure_ascii=False, indent=4)
