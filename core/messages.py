"""Tin nhắn chuẩn hoá dùng chung cho mọi kênh.

Bộ quét của từng kênh gọi ``publish()`` cho mỗi tin MỚI của khách (đã lọc nội bộ,
chưa có trong lịch sử). Mặc định chưa có ai đăng ký nên không có tác dụng phụ;
giai đoạn sau, cầu nối Chatwoot sẽ ``subscribe()`` vào đây.

Subscriber chạy ngay trong luồng quét, đang giữ khoá trình duyệt: chỉ được ghi
vào hàng đợi bền (SQLite) rồi trả về, không gọi mạng, không chặn.
"""
from dataclasses import dataclass, field
import threading
import time


@dataclass(frozen=True)
class IncomingMessage:
    channel: str            # "zalo" | "whatsapp" | ...
    chat_id: str            # định danh ổn định nhất kênh có (Zalo Web: tên nhóm; WA: id chat)
    chat_name: str          # tên hiển thị của chat/nhóm
    sender: str             # tên người gửi trong chat
    message_id: str         # id tin trong kênh (Zalo: bb_msg_id_..., WA: id serialized)
    text: str = ""
    attachments: tuple = field(default_factory=tuple)  # đường dẫn file đã lưu
    ts: float = field(default_factory=time.time)


_subscribers = []
_lock = threading.Lock()


def subscribe(callback):
    with _lock:
        _subscribers.append(callback)
    return callback


def unsubscribe(callback):
    with _lock:
        if callback in _subscribers:
            _subscribers.remove(callback)


def publish(message):
    """Không bao giờ ném lỗi về luồng quét."""
    with _lock:
        targets = list(_subscribers)
    for callback in targets:
        try:
            callback(message)
        except Exception as exc:
            print(f"⚠️ [Messages] Subscriber {getattr(callback, '__name__', callback)} lỗi: {type(exc).__name__}: {exc}")
