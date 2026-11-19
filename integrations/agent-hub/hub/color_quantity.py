"""A named model, declared total and color allocation form one order line."""
import re
import unicodedata


def parse(message):
    if message.get('origin') != 'customer' or message.get('revision') or message.get('recalled'):
        return None
    lines = [' '.join(s.split()) for s in unicodedata.normalize('NFC', message.get('text', '')).splitlines() if s.strip()]
    if len(lines) < 3 or not re.fullmatch(r'(?:3d\s+)?số\s+[\w-]+', lines[0], re.I):
        return None
    if re.search(r'[?!]|\b(không|ko|chưa|hủy|huỷ|nếu|đừng|khoan|thêm|bù)\b', '\n'.join(lines), re.I):
        return {'invalid': 'Chưa phải xác nhận phân màu rõ ràng'}
    total = re.fullmatch(r'(hàng(?:\s+[^\d?!]+)?)\s+([1-9]\d*(?:\.\d{3})*)\s*(cái|chiếc|c)', lines[1], re.I)
    if not total:
        return None
    amount = int(total[2].replace('.', ''))
    colors = []
    for line in lines[2:]:
        match = re.fullmatch(r'((?:đỏ|cam|vàng|xanh|x|trắng|đen|hồng|tím|nâu|kem|be|ghi|xám)(?:\s+[^\W\d_]+){0,2})\s*:?\s*([1-9]\d*(?:\.\d{3})*)(?:\s*(?:cái|chiếc|c))?', line, re.I)
        if not match:
            return {'invalid': 'Dòng phân màu chưa rõ'}
        colors.append((match[1].casefold(), int(match[2].replace('.', ''))))
    if amount > 1000000 or sum(n for _, n in colors) != amount or len({c for c, _ in colors}) != len(colors):
        return {'invalid': 'Tổng phân màu không khớp số lượng hoặc lặp màu'}
    return {'quantity': str(amount), 'unit': 'cái', 'model_name': lines[0],
            'line_note': total[1] + '\n' + '\n'.join(lines[2:])}


def submission_note(marker, line):
    if (marker.get('model_name') and marker.get('line_note') and
            line.get('ten_mau') == marker['model_name'] and
            str(line.get('so_luong')) == marker['quantity']):
        return marker['line_note']
    return ''


def pending_media(message):
    return not message.get('images') and any('pending-media' in a for a in message.get('attachments', []))


def groups(messages):
    """Keep the preceding photo/placeholder with its named total-and-colors block."""
    result, current = [], []
    has_quantity = False
    for m in messages:
        quantity = parse(m)
        media = bool(m.get('images')) or pending_media(m)
        if has_quantity and (media or quantity):
            result.append(current); current = []; has_quantity = False
        current.append(m)
        has_quantity |= bool(quantity and not quantity.get('invalid'))
    if current:
        result.append(current)
    return result
