"""Safe actionable notices: raw exception text never goes to staff."""
from hub.workflow_rules import normalize

def issue(reason, stage='design'):
    text = normalize(str(reason))
    code, title, action = 'REVIEW_REQUIRED', 'Chưa đủ căn cứ để hoàn tất bước xử lý', 'Đối chiếu tin nguồn, file và thông số trong hồ sơ; ghi rõ thông tin bổ sung.'
    rules = [
        (('openai','router can nhan vien','ban ve lai chua khop'), 'RASTER_VERIFY_REVIEW', 'Ảnh phục hồi chưa vượt qua kiểm tra chất lượng', 'Đối chiếu chữ, dấu, hình và chi tiết trắng với ảnh gốc. Giữ kết quả đã có; không tự gọi lại lượt vẽ chưa đạt.'),
        (('hoi file','confirmed_no_design_file','cho phep phuc hoi'), 'RESTORATION_PERMISSION', 'Ảnh cần phục hồi; đang chờ cho phép xử lý', 'Nhân viên hỏi file và khách xác nhận không có, hoặc chủ xưởng cho phép phục hồi đúng ảnh nguồn. Không cần yêu cầu PDF/AI nếu đã duyệt dùng ảnh này.'),
        (('uncertain','reconciliation','publishing'), 'RESULT_UNCERTAIN', 'Chưa xác minh kết quả gửi trước', 'Kiểm tra ghi chú đã có trước khi thực hiện lại; không tự phát lại.'),
        (('busy','rejected by callee','phan mem ban'), 'DESIGN_APP_BUSY', 'Phần mềm thiết kế đang bận', 'Kiểm tra hộp thoại hoặc tác vụ Illustrator/Photoshop, giữ nguyên tài liệu đang mở.'),
        (('hash','source changed','thay doi','khong con khop'), 'SOURCE_CHANGED', 'File nguồn đã thay đổi', 'Đối chiếu phiên bản và tải lại đúng file nguồn trước khi xuất.'),
        (('file','pdf','ai tuong thich','inventory','doi tuong'), 'SOURCE_REVIEW', 'Chưa đọc hoặc tách được đầy đủ file nguồn', 'Kiểm tra PDF/AI gốc, đối tượng bị che, font và clipping; bổ sung file phù hợp.'),
        (('kich thuoc','kho','dimension','cu ','meo','mau thuan'), 'DIMENSION_REVIEW', 'Kích thước hoặc cữ in chưa thống nhất', 'Đối chiếu số đo trên maket với tin khách và PDF/AI; xác nhận chiều ngang, cao và mép tính cữ.'),
        (('product_ambiguous',), 'PRODUCT_AMBIGUOUS', 'Một hồ sơ chứa nhiều loại sản phẩm', 'Tách mẫu nón và túi, xác định quy tắc xuất riêng từng mẫu.'),
        (('alpha','spot','muc trang'), 'WHITE_CHANNEL_REVIEW', 'Chưa xác minh nền trong suốt hoặc mực trắng', 'Kiểm tra alpha, giữ phần trắng nguyên vẹn và chỉ contract phần màu 1 pixel.'),
    ]
    for needles, c, t, a in rules:
        if any(n in text for n in needles):
            code, title, action = c, t, a
            break
    return {'code': code, 'stage': stage, 'title': title, 'action': action}

def describe(reason, stage='design'):
    item = issue(reason, stage)
    return f"[{item['code']}] {item['title']}\nBước: {stage}\nCần làm: {item['action']}"
