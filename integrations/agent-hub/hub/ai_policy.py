"""Explicit per-thread trial scope, separate from global review/live mode."""

import time
import unicodedata


def trial(cfg, thread):
    return (cfg.get("ai_trials") or {}).get(thread)


def fresh_trial_message(cfg, thread, message):
    scope = trial(cfg, thread)
    marker = (message.get("content_attributes") or {}).get("phucthanh") or {}
    if not scope or marker.get("origin") != "capture":
        return False
    try:
        stamp = float(marker["source_timestamp"])
        return stamp >= float(scope["enabled_after"]) and 0 <= time.time() - stamp <= 300
    except (KeyError, TypeError, ValueError):
        return False


def ai_delivery(settings, cfg, message, thread):
    scope = trial(cfg, thread)
    agentic = cfg.get("agentic", {})
    scope = scope or (agentic.get("enabled") and agentic.get("public_replies") and thread in agentic.get("allowed_groups", []))
    marker = (message.get("content_attributes") or {}).get("phucthanh") or {}
    sender = message.get("sender") or {}
    return bool(
        scope
        and marker.get("origin") == "ai"
        and sender.get("type") == "agent_bot"
        and sender.get("id") == settings.cw_bot_id
        and message.get("private") is False
    )


def requests_human(text):
    text = "".join(c for c in unicodedata.normalize("NFD", text.lower()) if not unicodedata.combining(c))
    return any(p in text for p in ("nhan vien", "nguoi that", "gap nguoi", "khieu nai", "human agent"))
