"""Owner policy: CANAVI maket dimensions, proportional artwork, internal review."""
CANAVI_ARTWORK_POLICY = '''
QUY TẮC CANAVI CHUNG — chủ xưởng xác nhận 22/10/2026:
Chỉ áp dụng khi nguồn xác định CANAVI/CANAVI HCM2. Đọc đủ phiếu, maket mới nhất và AI/PDF đúng phiên bản. Kích thước artwork ưu tiên số đo khách ghi trên maket; có thể suy ngang từ ngang mặt túi trừ cữ trái/phải khi cùng mốc, ghi rõ phép tính và nguồn. Dùng một chiều có căn cứ làm chuẩn, chiều còn lại tính đúng tỷ lệ artwork đã tách; không kéo méo để đồng thời khớp hai cữ. Không coi việc thiếu xác nhận chiều còn lại là lý do hỏi lại nếu tỷ lệ nguồn đã rõ.
Nếu chiều suy theo tỷ lệ khác chiều tính từ cữ trên/dưới: ghi rõ chiều chuẩn, chiều tính theo tỷ lệ, chiều theo cữ, độ lệch cm và mốc đo vào review_warnings và dimension_explanation (hoặc findings nếu schema không có review_warnings). Đây là sai lệch cữ cần chủ xưởng duyệt, không tự kéo méo. Không mặc định 20x26.33cm cho mẫu khác: đó chỉ là TDVKD-DINH.10. Nếu hai số đo kích thước artwork khách chỉ định trực tiếp mâu thuẫn nhau, không tự chọn ưu tiên: ghi thiếu/mâu thuẫn để duyệt.
PET PNG/TIFF không trừ co vải. JPG giữ quy tắc khổ vải sau co và cữ may đã lưu; không dùng co vải để thay đổi tỷ lệ artwork. Giữ màu nguồn, chi tiết trắng, không lật gương. Chỉ bản mẫu/preview nội bộ, không tự duyệt, RIP hoặc gửi khách. Vẫn chặn khi sai/thiếu artwork, nguồn mờ, không rõ phiên bản hoặc mốc đo.
'''


def review_schema(schema):
    """Add nonblocking review observations without mutating shared schemas."""
    import copy
    result = copy.deepcopy(schema)
    result['properties']['review_warnings'] = {'type': 'array', 'items': {'type': 'string'}}
    return result


def review_note(plan, verification):
    lines = []
    for data in (plan, verification):
        for value in data.get('review_warnings', []):
            if isinstance(value, str) and value.strip() and value not in lines:
                lines.append(value)
    for face in plan.get('faces', []):
        explanation = face.get('dimension_explanation')
        if explanation:
            lines.append(str(face.get('side', '')) + ': ' + explanation)
    if not lines:
        return ''
    return '\nĐỐI CHIẾU KÍCH THƯỚC / CỮ — CHỜ CHỦ XƯỞNG DUYỆT:\n' + '\n'.join(lines)
