"""Legacy group policy shared by Windows capture and the order worker."""

import re
import unicodedata


def key(value):
    return " ".join(unicodedata.normalize("NFC", value or "").split()).casefold()


def sanitize(config):
    result = {}
    for channel in ("zalo", "whatsapp", "viber"):
        for suffix in ("internal_members", "skip_groups", "skip_thread_ids", "disable_reply_groups"):
            name = f"{channel}_{suffix}"
            values = config.get(name, [])
            if not isinstance(values, list) or any(not isinstance(v, str) for v in values):
                raise ValueError("Invalid group policy list")
            result[name] = values
        for action in ("receive_messages", "auto_order", "read_private_messages"):
            name = f"{channel}_default_{action}"
            value = config.get(name, channel != 'viber')
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
    ids = config.get('viber_allowed_thread_ids', [])
    if not isinstance(ids, list) or any(x != 'viber:g1' for x in ids):
        raise ValueError('Only verified Viber CDG scope is supported')
    result['viber_allowed_thread_ids'] = ids
    scoped=config.get('group_intake_rules',{})
    if not isinstance(scoped,dict):raise ValueError('Invalid group intake rules')
    result['group_intake_rules']={}
    for account,groups in scoped.items():
        if not isinstance(account,str) or not isinstance(groups,dict):raise ValueError('Invalid group intake account')
        result['group_intake_rules'][account]={}
        for thread,row in groups.items():
            if not isinstance(thread,str) or not isinstance(row,dict) or row.get('mode')!='primary_slip_sender' or not isinstance(row.get('primary_sender_id'),str) or not row['primary_sender_id'].isdigit():raise ValueError('Invalid primary slip sender')
            result['group_intake_rules'][account][thread]={k:row[k] for k in ('mode','primary_sender_id')}
    return result


def quality_only(channel, thread_id):
    return (channel, thread_id) in {
        ('zalo', 'g3307527274697028144'),
        ('whatsapp', '120363407119559834@g.us'),
    }


def capture_allowed(config, channel, thread_id, name):
    if quality_only(channel, thread_id):
        return True
    if channel == 'viber':
        return thread_id in config.get('viber_allowed_thread_ids', [])
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
    if quality_only(channel, message.get('thread_id')):
        return False
    if channel == 'viber' and not capture_allowed(config,channel,message.get('thread_id'),message.get('display_name')):
        return False
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
