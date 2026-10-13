"""Legacy group policy shared by Windows capture and the order worker."""

import re
import unicodedata


def key(value):
    return " ".join(unicodedata.normalize("NFC", value or "").split()).casefold()


def sanitize(config):
    result = {}
    for channel in ("zalo", "whatsapp"):
        for suffix in ("internal_members", "skip_groups", "skip_thread_ids", "disable_reply_groups"):
            name = f"{channel}_{suffix}"
            values = config.get(name, [])
            if not isinstance(values, list) or any(not isinstance(v, str) for v in values):
                raise ValueError("Invalid group policy list")
            result[name] = values
        for action in ("receive_messages", "auto_order", "read_private_messages"):
            name = f"{channel}_default_{action}"
            value = config.get(name, True)
            if not isinstance(value, bool):
                raise ValueError("Invalid group policy default")
            result[name] = value
        rules = config.get(f"{channel}_contact_rules", [])
        if not isinstance(rules, list) or any(
            not isinstance(row, dict) or not isinstance(row.get("name"), str) for row in rules
        ):
            raise ValueError("Invalid contact rules")
        result[f"{channel}_contact_rules"] = [
            {
                "name": row["name"],
                **{action: row.get(action) is True for action in ("receive_messages", "auto_order")},
            }
            for row in rules
        ]
    return result


def capture_allowed(config, channel, thread_id, name):
    if channel == "whatsapp" and not re.fullmatch(r"[0-9]+(?:-[0-9]+)?@g\.us", thread_id):
        return False  # Desktop integration is explicitly groups-only.
    if channel == "zalo" and not re.fullmatch(r"g\d+", thread_id):
        return config.get("zalo_default_read_private_messages", True) is True
    return thread_id not in config.get(f"{channel}_skip_thread_ids", []) and key(name) not in {
        key(n) for n in config.get(f"{channel}_skip_groups", [])
    }


def allowed(config, channel, group, action="auto_order"):
    name = key(group)
    if not name:
        return False
    for suffix in ("skip_groups", "internal_members"):
        if name in {key(n) for n in config.get(f"{channel}_{suffix}", [])}:
            return False
    if action == "receive_messages" and name in {
        key(n) for n in config.get(f"{channel}_disable_reply_groups", [])
    }:
        return False
    for rule in config.get(f"{channel}_contact_rules", []):
        if key(rule["name"]) == name:
            return rule.get(action) is True
    return config.get(f"{channel}_default_{action}", True) is True


def eligible(config, channel, message):
    if channel == 'whatsapp' and message.get('sender') == 'Thành viên chưa xác định tên':
        return False
    if (
        not capture_allowed(config, channel, message["thread_id"], message["display_name"])
        or message.get("direction") != "incoming"
        or message.get("origin") != "customer"
        or message.get("revision")
        or message.get("recalled")
        or not message.get("sender", "").strip()
        or (channel == "zalo" and not re.fullmatch(r"g\d+", message["thread_id"]))
        or not allowed(config, channel, message["display_name"])
    ):
        return False
    internal = [key(n) for n in config.get(f"{channel}_internal_members", [])]
    # A mention identifies the recipient, not the author of the request.
    return key(message["sender"]) not in internal
