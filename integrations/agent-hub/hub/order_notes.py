"""Keep production instructions in ERP line notes; provenance stays in Hub/NAS."""
import re


def clean_order_note(value):
    lines = []
    for raw in (value or '').splitlines():
        line = raw.strip()
        if re.match(r'^(?:Tin\s+#?\d+\b|Bằng chứng NAS:|Nguồn Chatwoot\s*#|Chờ bổ sung mã hàng/giá trong ERP)', line, re.I):
            continue
        if re.fullmatch(r'\[Ảnh (?:Zalo|WhatsApp|Viber) lưu trong kho NAS\]', line, re.I):
            continue
        if line:
            lines.append(line)
    return '\n'.join(lines)[:4000]
