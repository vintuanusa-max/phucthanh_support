"""Đưa đơn phát hiện từ chat vào hàng đợi ERP (erp_bridge, SQLite bền)."""
from core import runtime as rt
from core.extraction import _analyze_for_erp
from core.paths import ROOT
from core.policy import erp_source_allowed
from core.runtime import send_queue
from core.settings import zalo_allowed


def start_erp_bridge(app):
    from erp_bridge import Bridge
    from erp_bridge_api import build_router as build_erp_router
    rt.erp_bridge = Bridge(str(ROOT), send_queue, zalo_allowed, _analyze_for_erp, erp_source_allowed)
    app.include_router(build_erp_router(rt.erp_bridge))
    rt.erp_bridge.start()
    return rt.erp_bridge


def process_extracted_screenshot_async(customer_name: str, image_path: str, source: str = "zalo", source_id=None, target_text=""):
    if source == "whatsapp":
        if not erp_source_allowed(source, customer_name, "auto_order"):
            raise ValueError("Chat WhatsApp đang bị bỏ qua")
        return rt.erp_bridge.capture(customer_name, source_id, image_path, target_text, source="whatsapp")
    if source == "zalo":
        if zalo_allowed(customer_name, "auto_order"):
            rt.erp_bridge.capture(customer_name, source_id, image_path, target_text)
        return
    # Nguồn khác: không xử lý. Luồng AppSheet cũ (chỉ chạy được với nguồn khác
    # zalo/whatsapp, tức không bao giờ) đã bỏ cùng khoá AppSheet/Gemini viết cứng.
