"""Close ordinary text conversations before any paid AI call."""
import re

from hub.intake_logistics import norm

_ORDER_ACTION_RE = re.compile(
    r'\b(?:in|dat|lam|len mau|lam mau|ve mau|ve lai|sua mau|duyet|cu in|cho in|'
    r'in giup|in dum|in them|dat them|lam them|in bu|lam bu|chot|so luong|sl|'
    r'dat hang|ra pet|ra phim|bao gia|hoi gia|san xuat|them|bu)\b'
)
_SMALL_WORD_NUM = r'(?:mot|hai|ba|bon|nam|sau|bay|tam|chin|muoi)'
_SMALL_SPARE_ASK_RE = re.compile(
    r'\bxin\b[^\n!?]{0,40}?\b(?:[1-9]|10|' + _SMALL_WORD_NUM + r')\s*(?:cai|tam|mieng|chiec|bo|pet|non|tui)\b'
)


def is_small_spare_ask(text):
    """True when a customer only asks for a small spare/favor count (e.g. 'cho chú xin 2 cái về ép cho khách') without any order verb."""
    t = norm(text).strip()
    if not t or _ORDER_ACTION_RE.search(t):
        return False
    if not _SMALL_SPARE_ASK_RE.search(t):
        return False
    nums = re.findall(r'\d+(?:[.,]\d+)?', t)
    if len(nums) > 1:
        return False
    for n in nums:
        try:
            if float(n.replace(',', '.')) > 10:
                return False
        except ValueError:
            return False
    if re.search(r'\b(?:tram|nghin|ngan|chuc)\b', t):
        return False
    return True


def chat_display_state(messages):
    """Return 'Nhân viên gửi' (staff-only), 'Trò Chuyện' (both staff and customer in any order), or 'Khách hỏi' (customer-only)."""
    active = [m for m in messages if not m.get('recalled') and not m.get('revision')]
    has_staff = any(m.get('origin') == 'staff' or m.get('direction') == 'outgoing' for m in active)
    has_customer = any(m.get('origin') == 'customer' and m.get('direction', 'incoming') == 'incoming' for m in active)
    if has_staff and has_customer:
        return 'Trò Chuyện'
    if active and all(m.get('origin') == 'staff' or m.get('direction') == 'outgoing' for m in active):
        return 'Nhân viên gửi'
    return 'Khách hỏi'


def conversation_state(messages):
    active = [m for m in messages if not m.get('recalled') and not m.get('revision')]
    customers = [m for m in active if m.get('origin') == 'customer']
    if not customers:
        return None
    staff_qty_prompt = any(
        m.get('origin') == 'staff'
        and re.search(r'\d|bao nhieu|may\s+(?:cai|tam|met|non|bo|chiec)|so luong|\bsl\b', norm(m.get('text', '')))
        for m in active
    )
    # Keep source/reply handling and order confirmations in their existing flow.
    for m in active:
        if any(m.get(k) for k in ('images', 'assets', 'attachments', 'quoted_image', 'quoted_file')):
            return None
        t = norm(m.get('text', ''))
        if re.search(r'https?://|\[anh zalo|\[file zalo', t):
            return None
        has_num = bool(
            re.search(r'\d', t)
            or re.search(r'\b(?:mot|hai|ba|bon|nam|sau|bay|tam|chin|muoi|tram|nghin|ngan|chuc)\s+(?:cai|tam|met|non|bo|chiec)\b', t)
        )
        if has_num:
            if m.get('origin') == 'customer' and not staff_qty_prompt and is_small_spare_ask(t):
                continue
            return None
    for m in customers:
        t = norm(m.get('text', ''))
        if re.search(r'\b(?:in|dat|len mau|lam mau|ve mau|ve lai|sua mau|duyet|cu in|cho in|in giup|in dum|in them|dat them|lam them|in bu|chot|so luong|sl|dat hang)\b', t):
            return None
        # An isolated acknowledgment may confirm an order from an earlier batch.
        if re.fullmatch(r'\s*(?:ok|oke|okay|dong y|dung|chuan|duoc|vang|da|uh|u)[\s!.]*', t):
            return None
    return chat_display_state(active)

