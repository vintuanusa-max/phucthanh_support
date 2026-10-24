"""Owner-approved MET mapping from explicit fabric printing quantities."""
import re
import unicodedata
from decimal import Decimal


def meter_quantity(text):
    text = ''.join(c for c in unicodedata.normalize('NFD', text.lower()) if not unicodedata.combining(c)).replace('đ', 'd')
    if not re.search(r'\bvai\b', text):
        return None
    if re.search(r'\b(gia|bao gia|bao nhieu tien|khong in|ko in|chua in|dung in|huy|kho|ngang|cao|rong|dai|kich thuoc)\b|\d\s*[x×]\s*\d', text):
        return None
    # Quantity must follow an explicit print request, not a delivery statement.
    matches = list(re.finditer(r'\bin\b[^.!?;\n\d]{0,50}(\d+(?:[.,]\d+)?)\s*(?:met|m)(?![\w²2])', text))
    if len(matches) != 1:
        return None
    value = Decimal(matches[0].group(1).replace(',', '.'))
    return value if value > 0 else None


def apply_meter_product(orders, messages):
    # Multiple designs require per-line evidence; never spread one quantity across them.
    if len(orders) != 1:
        return False
    line = orders[0]
    if line.ma_san_pham not in (None, 'MET'):
        return False
    quantities = {q for m in messages if m.get('origin', 'customer') == 'customer'
                  and m.get('direction', 'incoming') == 'incoming' and not m.get('recalled')
                  if (q := meter_quantity(m.get('text', ''))) is not None}
    if quantities != {line.so_luong}:
        return False
    line.ma_san_pham = 'MET'
    return True

def apply_meter_lines(orders, messages):
    """Authorize MET per named quantity line, not across an entire batch."""
    if apply_meter_product(orders, messages):
        return {id(orders[0])}
    def norm(value):
        return ''.join(c for c in unicodedata.normalize('NFD', value.lower()) if not unicodedata.combining(c)).replace('đ', 'd')
    matched=set()
    for m in messages:
        if m.get('origin','customer')!='customer' or m.get('direction','incoming')!='incoming' or m.get('recalled'):continue
        text=norm(m.get('text',''))
        if not re.search(r'\bin\b',text) or not re.search(r'\bvai\b',text):continue
        if re.search(r'\b(gia|khong in|ko in|chua in|dung in|huy|kho|ngang|cao|rong|dai|kich thuoc)\b',text):continue
        used=set()
        for row in text.splitlines():
            hit=re.fullmatch(r'\s*(.+?)\s*[-:]\s*(\d+(?:[.,]\d+)?)\s*(?:met|m)\s*',row)
            if not hit:continue
            label,qty=hit.group(1),Decimal(hit.group(2).replace(',','.'))
            candidates=[o for o in orders if o.ma_san_pham in (None,'MET') and o.so_luong==qty and label in norm(o.ten_mau or '')]
            if len(candidates)!=1 or id(candidates[0]) in used:continue
            line=candidates[0];line.ma_san_pham='MET';matched.add(id(line));used.add(id(line))
    return matched


def apply_an_nguyen_sheets(orders, messages, thread_id):
    # Explicit owner policy 22/10: MET is product code; retain sheet count.
    if thread_id != 'g5402324928935037742': return set()
    customer=[m for m in messages if m.get('origin','customer')=='customer' and m.get('direction','incoming')=='incoming' and not m.get('recalled')]
    counts=set()
    for m in customer:
        text=''.join(c for c in unicodedata.normalize('NFD',m.get('text','').lower()) if not unicodedata.combining(c)).replace('đ','d')
        if re.search(r'\b(giao vai|het vai|khong in|ko in|chua in|huy|gia)\b',text):continue
        counts.update(Decimal(x) for x in re.findall(r'(?<![\w.])(\d+)\s*tam\b',text))
    matched=set()
    for line in orders:
        if line.ma_san_pham in (None,'MET') and line.so_luong>0 and line.so_luong in counts:
            line.ma_san_pham='MET';matched.add(id(line))
    return matched
