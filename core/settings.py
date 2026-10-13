"""Đọc config.json (tự nạp lại khi file đổi) và các danh sách cấu hình."""
import os

import communication_policy

CONFIG_FILE = str(communication_policy.CONFIG_FILE)

# --- CONFIG ĐỘNG ---
_config_cache = {}
_config_last_load = 0.0


def load_config() -> dict:
    global _config_cache, _config_last_load
    try:
        stat = os.stat(CONFIG_FILE)
        signature = (stat.st_mtime_ns, stat.st_size)
        if signature != _config_last_load:
            _config_cache = communication_policy.read_raw(CONFIG_FILE)
            _config_last_load = signature
    except Exception:
        print("[Config] Không đọc được config.json; giữ cấu hình đã nạp")
    return _config_cache


def zalo_allowed(name, action):
    # No first successful config read means no automatic external action.
    return bool(_config_cache or load_config()) and communication_policy.allowed(load_config(), name, action)


def get_zalo_internal() -> list:
    return load_config().get("zalo_internal_members", [])


def get_zalo_skip_groups() -> list:
    return load_config().get("zalo_skip_groups", [])


def get_wa_internal() -> list:
    return load_config().get("whatsapp_internal_members", [])


def get_wa_skip_groups() -> list:
    return load_config().get("whatsapp_skip_groups", [])


def get_design_extensions() -> list:
    return load_config().get("design_file_extensions", [".ai", ".pdf", ".psd", ".psb", ".cdr", ".eps", ".svg"])


def _is_design_file(filepath: str) -> bool:
    """True nếu file là file thiết kế — lưu về máy thôi, không forward n8n."""
    ext = os.path.splitext(filepath)[1].lower()
    return ext in get_design_extensions()


def is_skip_group(name: str, skip_list: list) -> bool:
    name_l = name.lower().strip()
    return any(s.lower().strip() == name_l for s in skip_list)


def _is_zalo_internal(sender: str, internal_members: list) -> bool:
    return communication_policy.contains(internal_members, sender)
