"""Chính sách gửi/nhận theo kênh.

Zalo dùng communication_policy (giao diện ERP cấu hình). WhatsApp dùng các khóa
whatsapp_* cũ trong config.json. Kênh mới phải đi qua ``allowed()``.
"""
import unicodedata

from core.settings import get_wa_internal, get_wa_skip_groups, get_zalo_internal, get_zalo_skip_groups, is_skip_group, load_config, zalo_allowed
from core.text_rules import name_match


def erp_source_allowed(source, name, action):
    if source == "zalo":
        return zalo_allowed(name, action)
    if source == "whatsapp":
        return bool(load_config()) and not is_skip_group(name, get_wa_skip_groups())
    return False


def whatsapp_reply_disabled(customer_name, log_tag="WA"):
    """True nếu chat nằm trong whatsapp_disable_reply_groups (khớp chính xác hoặc name_match)."""
    wa_disable_list = load_config().get("whatsapp_disable_reply_groups", [])
    def clean_name(s):
        if not s: return ""
        s = s.replace('\xa0', ' ')
        return unicodedata.normalize('NFC', s).strip().lower()
    req_name_clean = clean_name(customer_name)
    for c in wa_disable_list:
        c_clean = clean_name(c)
        if c_clean:
            if c_clean == req_name_clean:
                return True
            try:
                if name_match(c, customer_name):
                    return True
            except Exception as match_err:
                print(f"⚠️ [{log_tag}] Lỗi so khớp name_match: {match_err}")
    return False


def allowed(channel, name, action):
    """action: 'receive_messages' (được gửi tin cho chat này) hoặc 'auto_order'."""
    if channel == "zalo":
        return zalo_allowed(name, action)
    if channel == "whatsapp":
        if action == "receive_messages":
            return not whatsapp_reply_disabled(name)
        if action == "auto_order":
            return erp_source_allowed("whatsapp", name, action)
    return False


def internal_members(channel):
    return {"zalo": get_zalo_internal, "whatsapp": get_wa_internal}[channel]()


def skip_groups(channel):
    return {"zalo": get_zalo_skip_groups, "whatsapp": get_wa_skip_groups}[channel]()
