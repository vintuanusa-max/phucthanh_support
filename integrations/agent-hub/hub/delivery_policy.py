"""Per-account human delivery may be live while AI remains in review."""

import time
from datetime import datetime

from hub.ai_policy import ai_delivery


def human_delivery(settings, cfg, message):
    if cfg.get("human_delivery_enabled") is not True:
        return False
    sender = message.get("sender") or {}
    marker = (message.get("content_attributes") or {}).get("phucthanh") or {}
    return (
        sender.get("type") == "user"
        and isinstance(sender.get("id"), int)
        and sender["id"] not in cfg.get("excluded_sender_ids", [])
        and not marker.get("origin")
        and message.get("private") is False
    )


def delivery_block(settings, cfg, message, thread):
    if not cfg.get("delivery_enabled"):
        return "Đầu gửi đang tắt"
    if cfg.get('channel') == 'viber':
        # Viber rollout is staff-only even when the shared hub runs in live mode.
        if not human_delivery(settings, cfg, message):
            return "Viber chỉ gửi câu trả lời công khai của nhân viên; AI giữ ghi chú nội bộ"
        if thread not in cfg.get('delivery_allowed_threads', []):
            return "Nhóm Viber chưa được phép gửi"
        if message.get('content_type', 'text') != 'text':
            return "Viber chỉ hỗ trợ văn bản"
        try:
            value = message['created_at']
            stamp = float(value) if isinstance(value, (int, float)) else datetime.fromisoformat(value.replace('Z', '+00:00')).timestamp()
            if stamp < float(cfg['delivery_after']) or not 0 <= time.time() - stamp <= 300:
                return "Tin Viber cũ hoặc quá hạn; chưa gửi"
        except (KeyError, TypeError, ValueError):
            return "Không xác minh được thời điểm tin Viber"
    if settings.mode != "live" and not (
        human_delivery(settings, cfg, message) or ai_delivery(settings, cfg, message, thread)
    ):
        return "Tin không thuộc nhân viên được phép gửi"
    if message.get("private") or message.get("attachments"):
        return "Chỉ hỗ trợ trả lời công khai bằng văn bản"
    text = message.get("content")
    if not isinstance(text, str) or not text.strip() or len(text) > 8000:
        return "Nội dung trống hoặc quá dài"
    if cfg.get("desktop_sender"):
        if not thread.startswith("g") or not thread[1:].isdigit():
            return "Đầu gửi này chỉ hỗ trợ nhóm Zalo"
        if message.get("content_type", "text") != "text":
            return "Loại nội dung chưa hỗ trợ"
        try:
            value = message["created_at"]
            stamp = (
                float(value)
                if isinstance(value, (int, float))
                else datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
            )
            if stamp < float(cfg["delivery_after"]) or not 0 <= time.time() - stamp <= 300:
                return "Tin cũ hoặc quá hạn 5 phút; chưa gửi"
        except (KeyError, ValueError, TypeError):
            return "Không xác minh được thời điểm tạo tin"
    return ""
