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
