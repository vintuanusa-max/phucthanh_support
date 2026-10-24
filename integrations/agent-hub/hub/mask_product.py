"""Owner-approved mapping for a verified face-mask order line; no quantity inference."""
import re
import unicodedata

def apply_mask_product(lines):
    mapped = set()
    for line in lines:
        name = unicodedata.normalize("NFC", line.ten_mau or "").casefold()
        if re.search(r"\bmặt\s+nạ\b", name) and not re.search(r"\b(không|chưa|khẩu trang)\b", name):
            if not line.ma_san_pham or line.ma_san_pham == "MATNA":
                line.ma_san_pham = "MATNA"
                mapped.add(id(line))
    return mapped
