import os
import json
import threading

CONFIG_FILE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bot_config.json")
_config_lock = threading.Lock()

DEFAULT_CONFIG = {
    "steps": {
        "auto_reply_quote": True,
        "auto_extract_order_info": True,
        "enable_gemini_ai": True,
        "notify_admin_on_error": True
    },
    "settings": {
        "max_retry_attempts": 3,
        "ai_model": "gemini-2.5-flash",
        "chat_poll_interval_seconds": 2
    }
}

def load_config():
    with _config_lock:
        if not os.path.exists(CONFIG_FILE_PATH):
            save_config_internal(DEFAULT_CONFIG)
            return DEFAULT_CONFIG
        try:
            with open(CONFIG_FILE_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                updated = False
                for key in DEFAULT_CONFIG:
                    if key not in data:
                        data[key] = DEFAULT_CONFIG[key]
                        updated = True
                if updated:
                    save_config_internal(data)
                return data
        except Exception as e:
            print(f"[CONFIG ERROR] Không thể đọc config, sử dụng mặc định: {e}")
            return DEFAULT_CONFIG

def save_config_internal(config_data):
    try:
        with open(CONFIG_FILE_PATH, "w", encoding="utf-8") as f:
            json.dump(config_data, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print(f"[CONFIG ERROR] Lỗi khi lưu config: {e}")
        return False

def save_config(config_data):
    with _config_lock:
        return save_config_internal(config_data)
