"""Giao diện chung mà mỗi module kênh trong channels/ phải có.

Module kênh (zalo_web, whatsapp_wpp, sau này zalo_oa, messenger...) cung cấp:

    NAME: str                         tên kênh, trùng khóa trong core.policy
    start() -> None                   khởi động luồng quét + luồng gửi
    trigger_scan() -> None            quét ngay (thay vì chờ chu kỳ)
    capture_chat_screenshot(customer_name, f_path) -> (bool, str)

Nhận tin: bộ quét gọi core.messages.publish(IncomingMessage(...)) cho mỗi tin mới.
Gửi tin: đưa task {"customer_name", "message", ...} vào hàng đợi của kênh
(core.runtime.send_queue cho Zalo, wa_send_queue cho WhatsApp); worker của kênh
kiểm tra core.policy trước khi gửi.
"""
from typing import Protocol


class Channel(Protocol):
    NAME: str

    def start(self) -> None: ...

    def trigger_scan(self) -> None: ...

    def capture_chat_screenshot(self, customer_name: str, f_path: str) -> tuple: ...
