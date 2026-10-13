"""Quy tắc văn bản thuần (không GUI/mạng): nhận diện đơn, so tên, thư mục khách."""
import hashlib
import os
import re
import time
import unicodedata


def group_to_folder(group_name: str) -> str:
    """Lấy phần trước dấu '-' đầu tiên, bỏ dấu tiếng Việt, trả về tên thư mục ASCII HOA."""
    part = group_name.split('-')[0].strip()
    part = part.replace('\xa0', ' ') # Thay thế khoảng trắng đặc biệt (Non-breaking space) của Zalo thành khoảng trắng thường
    part = unicodedata.normalize('NFD', part)
    part = ''.join(c for c in part if unicodedata.category(c) != 'Mn')
    viet_map = str.maketrans('ĐđƯưƠơĂă', 'DDUUOOAa')
    part = part.translate(viet_map)
    return ''.join(c for c in part if c.isascii() and (c.isalnum() or c == ' ')).strip().upper()


def generate_stable_id(input_str):
    return hashlib.md5(input_str.encode('utf-8')).hexdigest()


def get_recent_files(save_dir: str, minutes=60) -> list:
    """Lấy danh sách các file trong thư mục được tạo/sửa trong vòng N phút qua."""
    recent = []
    if not os.path.exists(save_dir): return recent
    now = time.time()
    cutoff = now - (minutes * 60)
    for f in os.listdir(save_dir):
        path = os.path.join(save_dir, f)
        if os.path.isfile(path):
            file_time = max(os.path.getmtime(path), os.path.getctime(path))
            if file_time >= cutoff or file_time > now:
                recent.append(path)
    return recent


def _is_order_relevant(text: str) -> bool:
    """Chỉ True khi tin nhắn chứa số lượng đặt hàng, hỏi báo giá hoặc các lưu ý in ấn quan trọng."""
    if not text or not text.strip():
        return False
    t = unicodedata.normalize('NFC', text).lower()
    # Loại bỏ các cụm chỉ định in ấn 1 mặt / 2 mặt để tránh nhận diện nhầm là số lượng đơn hàng
    t = re.sub(r'\b(1|2|một|hai)\s*mặt\b', '', t)
    # 1. Hỏi báo giá
    if re.search(r'báo\s*giá|bao\s*giá|hỏi\s*giá|đơn\s*giá|giá\s+bao\s+nhi[eê]u|giá\s+m[aấ]y|giá\s+nh[uư]\s+th[eế]', t):
        return True
    # 2. Số + đơn vị (nón, két, mạc, áo, cặp, bộ, cái, c...)
    # Hỗ trợ nhận diện số dính liền chữ c (vd: 50c, 220c) hoặc cách ra (vd: 50 c)
    units = (r'(cá|cai|c\b|chiếc|chiec|cây|cay|kg\b|g\b|gram\b|'
             r'nón|non|két|ket|mạc|mac|áo|ao|mặt|mat|cặp|cap\b|đôi|doi|'
             r'thùng|thung|hộp|hop|bộ|bo|cuộn|cuon|tờ|to|bản|ban|tấm|tam|ly|chai|gói|goi|túi|tui|'
             r'set\b|pcs\b|pc\b|roll\b|sheet\b|box\b|carton\b|'
             r'pet\b|mét\b|met\b|m\b|yard\b|y\b|tem\b|nhãn\b|nhan\b|hình\b|hinh\b)')
    if re.search(r'\d+\s*' + units, t, re.IGNORECASE) or re.search(r'\d+c\b', t, re.IGNORECASE):
        return True
    # 3. Động từ đặt hàng + số (vd: "lấy 100", "in giùm e 12", "đặt cho e 50", "ra 260")
    # Cho phép m (mét) và mét đi với động từ (như "làm 5m", "in 10 mét"), loại trừ cm, mm, x
    # Thêm verb "ra" và sửa negative lookahead ngăn backtrack để tránh nhận nhầm kích thước (vd: 6.5cm, 260x30cm)
    verb_pattern = (r'(lấy|đặt|order|mua|cần|làm|in|ra)\s*'
                    r'(?:giùm|dùm|cho|hộ)?\s*'
                    r'(?:em|e|khách|ad|bot)?\s*'
                    r'(?<!\d)\d+([.,]\d+)?(?!\d)'
                    r'(?!\s*(?:cm\b|mm\b|x|\*))')
    if re.search(verb_pattern, t, re.IGNORECASE):
        return True
    # 3.5. Động từ/Đơn vị ở phía trước số lượng (ví dụ: "làm bộ này mỗi màu 200", "in mẫu này 200")
    forward_pattern = (r'\b(bộ|bo|áo|ao|nón|non|két|ket|mẫu|mau|màu|in|làm|lam|lấy|lay|đặt|dat|ra)\b'
                       r'[^0-9]{1,25}'
                       r'(?<!\d)\d+(?!\d)'
                       r'(?!\s*(?:[.,]\d+)?\s*(?:cm\b|mm\b|x|\*))')
    if re.search(forward_pattern, t, re.IGNORECASE):
        return True
    # 3.6. Liệt kê Màu/Mẫu/Phân loại + Số lượng (vd: "Đỏ 100", "Cam 100", "X lá 100", "X biển 100", "3D Số 50", "nhí 600")
    color_qty_pattern = (r'\b(đỏ|do|cam|vàng|vang|xanh|lá|la|biển|bien|bích|bich|đen|den|trắng|trang|tím|tim|hồng|hong|xám|xam|nâu|nau|'
                         r'nhí|nhi|lớn|lon|đại|dai|số|so|mẫu|mau|màu)\b'
                         r'[^0-9\n]{0,15}'
                         r'(?<!\d)\d+(?!\d)'
                         r'(?!\s*(?:[.,]\d+)?\s*(?:cm\b|mm\b|x|\*))')
    if re.search(color_qty_pattern, t, re.IGNORECASE):
        return True
    # 4. Hướng dẫn / lưu ý in ấn / yêu cầu màu sắc (không nhất thiết kèm số lượng)
    # Rất quan trọng khi khách phản hồi hoặc lưu ý về file vừa gửi (vd: "in đừng để ánh tím", "lưu ý in...")
    instruction_keywords = [
        r'in\s+(đừng|không|như|màu|đẹp|giùm|dùm|cho|em|e|này|nhá|nhé|gấp)',
        r'lưu\s*ý',
        r'đừng\s+để',
        r'không\s+để',
        r'sửa\s+(lại|file|mẫu|hình|ảnh)',
        r'chỉnh\s+(lại|file|mẫu|hình|ảnh)',
        r'in\s+giúp',
        r'in\s+hộ',
        r'in\s+cái\s+này',
        r'in\s+mẫu\s+này',
        r'in\s+hình\s+này'
    ]
    for pattern in instruction_keywords:
        if re.search(pattern, t, re.IGNORECASE):
            return True
    return False


def _is_order_forwardable(text: str) -> bool:
    """Trả về True chỉ khi tin nhắn thực sự chứa số lượng đặt hàng hoặc hỏi báo giá để gửi sang n8n."""
    if not text or not text.strip():
        return False
    t = unicodedata.normalize('NFC', text).lower()
    # Loại bỏ các cụm chỉ định in ấn 1 mặt / 2 mặt để tránh nhận diện nhầm là số lượng đơn hàng
    t = re.sub(r'\b(1|2|một|hai)\s*mặt\b', '', t)
    # 1. Hỏi báo giá
    if re.search(r'báo\s*giá|bao\s*giá|hỏi\s*giá|đơn\s*giá|giá\s+bao\s+nhi[eê]u|giá\s+m[aấ]y|giá\s+nh[uư]\s+th[eế]', t):
        return True
    # 2. Số + đơn vị (nón, két, mạc, áo, cặp, bộ, cái, c...)
    units = (r'(cái|cai|c\b|chiếc|chiec|cây|cay|kg\b|g\b|gram\b|'
             r'nón|non|két|ket|mạc|mac|áo|ao|mặt|mat|cặp|cap\b|đôi|doi|'
             r'thùng|thung|hộp|hop|bộ|bo|cuộn|cuon|tờ|to|bản|ban|tấm|tam|ly|chai|gói|goi|túi|tui|'
             r'set\b|pcs\b|pc\b|roll\b|sheet\b|box\b|carton\b|'
             r'pet\b|mét\b|met\b|m\b|yard\b|y\b|tem\b|nhãn\b|nhan\b|hình\b|hinh\b)')
    if re.search(r'\d+\s*' + units, t, re.IGNORECASE) or re.search(r'\d+c\b', t, re.IGNORECASE):
        return True
    # 3. Động từ đặt hàng + số (vd: "lấy 100", "in giùm e 12", "đặt cho e 50", "làm 5m", "ra 260")
    verb_pattern = (r'(lấy|đặt|order|mua|cần|làm|in|ra)\s*'
                    r'(?:giùm|dùm|cho|hộ)?\s*'
                    r'(?:em|e|khách|ad|bot)?\s*'
                    r'(?<!\d)\d+([.,]\d+)?(?!\d)'
                    r'(?!\s*(?:cm\b|mm\b|x|\*))')
    if re.search(verb_pattern, t, re.IGNORECASE):
        return True
    # 3.6. Liệt kê Màu/Mẫu/Phân loại + Số lượng (vd: "Đỏ 100", "Cam 100", "X lá 100", "X biển 100", "3D Số 50", "nhí 600")
    color_qty_pattern = (r'\b(đỏ|do|cam|vàng|vang|xanh|lá|la|biển|bien|bích|bich|đen|den|trắng|trang|tím|tim|hồng|hong|xám|xam|nâu|nau|'
                         r'nhí|nhi|lớn|lon|đại|dai|số|so|mẫu|mau|màu)\b'
                         r'[^0-9\n]{0,15}'
                         r'(?<!\d)\d+(?!\d)'
                         r'(?!\s*(?:[.,]\d+)?\s*(?:cm\b|mm\b|x|\*))')
    if re.search(color_qty_pattern, t, re.IGNORECASE):
        return True
    return False


def _has_zalo_internal_mention(text: str, internal_members: list) -> bool:
    """Skip customer messages tagging an exact configured internal display name."""
    value = " ".join(unicodedata.normalize("NFC", text or "").split()).casefold()
    for member in internal_members:
        name = " ".join(unicodedata.normalize("NFC", member or "").split()).casefold()
        if name and re.search(r"(?<![\w@])@\s*" + re.escape(name) + r"(?!\w)", value):
            return True
    return False


def _has_internal_mention(text: str, internal_members: list) -> bool:
    """True nếu tin nhắn có @tag nhân viên nội bộ — khách đang nhờ nội bộ xử lý, bỏ qua."""
    if not text or not internal_members:
        return False
    t = unicodedata.normalize('NFC', text)
    # Tìm tất cả @... trong text
    mentions = re.findall(r'@([\w\sÀ-ɏḀ-ỿ]+)', t)
    for mention in mentions:
        mention_norm = unicodedata.normalize('NFC', mention).lower().strip()
        for member in internal_members:
            m_norm = unicodedata.normalize('NFC', member).lower().strip()
            if m_norm in mention_norm or mention_norm in m_norm:
                return True
    return False


def normalize_name(s: str) -> str:
    import unicodedata
    s = str(s)
    s = unicodedata.normalize('NFC', s)
    s = s.lower()
    s = re.sub(r'[àáạảãâầấậẩẫăằắặẳẵ]', 'a', s)
    s = re.sub(r'[èéẹẻẽêềếệểễ]', 'e', s)
    s = re.sub(r'[ìíịỉĩ]', 'i', s)
    s = re.sub(r'[òóọỏõôồốộổỗơờớợởỡ]', 'o', s)
    s = re.sub(r'[ùúụủũưừứựửữ]', 'u', s)
    s = re.sub(r'[ỳýỵỷỹ]', 'y', s)
    s = s.replace('đ', 'd')
    # Xử lý cả dấu phụ nếu có sót (khi text chứa cả NFC và NFD)
    s = unicodedata.normalize('NFKD', s).encode('ascii', 'ignore').decode('utf-8')
    return re.sub(r'\s+', ' ', s).strip()


def name_match(req_name: str, actual_name: str) -> bool:
    # Chỉ lấy phần trước dấu gạch ngang "-" đầu tiên để so sánh chính xác, tránh nhầm lẫn do trùng phần đuôi tên công ty
    if "-" in actual_name:
        actual_name = actual_name.split("-")[0].strip()
    if "-" in req_name:
        req_name = req_name.split("-")[0].strip()
    a = normalize_name(req_name)
    b = normalize_name(actual_name)
    if not a or not b:
        return False
    if a in b or b in a:
        return True
    tokens_a = [t for t in re.split(r'[\s\-\(\)/,\.]+', a) if len(t) > 1]
    if not tokens_a:
        return False
    matched = sum(1 for t in tokens_a if t in b)
    return matched / len(tokens_a) >= 0.6


def build_search_keyword(customer_name: str) -> str:
    # Tách theo - _ ( để lấy phần đầu có nghĩa nhất
    base = re.split(r'[-_(]', customer_name)[0].strip()
    words = base.split()
    return ' '.join(words[:3]) if words else customer_name[:20]
