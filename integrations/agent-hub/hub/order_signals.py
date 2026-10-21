"""Routing hints only; never authorize ERP writes or infer order quantities."""
import re
import unicodedata


def normalized(text):
    text = unicodedata.normalize("NFD", text.casefold()).replace("đ", "d")
    return " ".join("".join(c for c in text if unicodedata.category(c) != "Mn").split())


def production_request(text):
    text = normalized(text)
    if re.search(r"\b(?:huy|hoan)\s+(?:don|lenh)|\b(?:chua|khong|ko)\s+(?:dat|gui don|san xuat|sx)\b", text):
        return False
    if re.search(r"\b(?:hoi gia|bao gia|xin gia)\b", text):
        return False
    return bool(re.search(r"\b(?:thong tin don hang|gui don hang|dat hang|don hang sx|san xuat lai|sx lai)\b", text))


def unhandled_order(messages, trace):
    if any(step.get("tool") == "propose_order_draft" for step in trace):
        return False
    # Reminder only: the existing independent verification must still approve any draft.
    return any(
        m.get("direction") == "incoming" and m.get("origin") == "customer"
        and not m.get("recalled") and not m.get("revision")
        and production_request(m.get("text", ""))
        and re.search(r"\b\d[\d.,]*\s*(?:tui|cai|bo|non|ao|chiec)\b", normalized(m.get("text", "")))
        for m in messages
    )
