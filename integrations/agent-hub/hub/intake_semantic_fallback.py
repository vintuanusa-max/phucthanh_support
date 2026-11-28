"""Admission to existing text Agent, never quantity extraction or ERP submission."""
import re
import unicodedata

POLICY = '''Nhánh dự phòng: bộ tách nhanh chưa hiểu chắc hội thoại, KHÔNG có nghĩa đã xác nhận đặt hàng.
Đọc toàn bộ cụm theo thứ tự, vai trò và reply để gắn đúng mẫu với lượng mới.
Hiểu lượng thập phân, số viết bằng chữ, đơn vị mét/tấm/cái, mỗi mẫu/mỗi file,
đặt thêm so với chốt tổng và khách đồng ý câu hỏi số lượng của nhân viên.
Phân biệt tiền, ngày giờ, số đo, tiến độ, hàng đã giao, hủy/hoãn và số lượng đặt mới.
Không lấy lượng từ ảnh cũ hoặc lời nhân viên nếu khách chưa xác nhận.
Không suy số lượng bằng regex hoặc tự gán số từ tên file. Không tự nhân mỗi file
khi chưa xác định đúng danh sách file. Giữ nguồn từng yêu cầu độc lập.
Đủ bằng chứng: dùng propose_order_draft hiện có, mã hàng chưa rõ dùng JSON null.
Không đủ bằng chứng: báo rõ mẫu/lượng/nguồn nào còn thiếu; không ép tạo đơn.
Mẫu sản phẩm yêu cầu lên mẫu không ghi lượng theo quy tắc chủ xưởng là2;
chỉ sửa/vẽ file không tự biến thành đặt sản phẩm. Giữ kiểm chứng/chống trùng hiện có.'''

def normalized(text):
    return ''.join(c for c in unicodedata.normalize('NFD', text.lower())
                   if unicodedata.category(c) != 'Mn').replace('đ','d')

def candidate(messages):
    """Broad uncertainty detector; AI determines intent, never this function."""
    from hub.intake_text_conversation import is_small_spare_ask
    active=[m for m in messages if not m.get('recalled') and not m.get('revision')]
    customers=[m for m in active if m.get('origin')=='customer' and m.get('direction','incoming')=='incoming']
    staff_quantity=any(m.get('origin')=='staff' and re.search(r'\d|bao nhieu|may\s+(?:cai|tam|met|non|bo|chiec)|so luong|\bsl\b',normalized(m.get('text',''))) for m in active)
    for m in customers:
        t=normalized(m.get('text','')).strip()
        if not t or t.startswith(('[anh zalo','[file zalo')):continue
        if not staff_quantity and is_small_spare_ask(t):continue
        if re.search(r'\d',t):return True
        if re.search(r'\b(in|dat|lam|lay|them|bu|ra pet|chot|so luong|sl)\b',t):return True
        if re.search(r'\b(mot|hai|ba|bon|nam|sau|bay|tam|chin|muoi|tram|nghin|ngan|chuc)\s+(cai|tam|met|non|bo|chiec)\b',t):return True
        if staff_quantity and re.search(r'\b(ok|oke|dong y|dung|chuan|duoc|vang|da|uh|u)\b',t):return True
    return False

def defer(payload, reason):
    """In-memory routing annotation only; no new queue or retry of old jobs."""
    payload['_semantic_fallback']={'reason':reason}
    return False
