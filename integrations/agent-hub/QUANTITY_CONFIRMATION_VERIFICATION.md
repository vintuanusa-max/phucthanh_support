
## 27/10/2026 — Khách xác nhận câu hỏi số lượng của nhân viên
- [x] Nhận lời đồng ý ngắn của customer với câu hỏi staff ngay trước hoặc quote đúng ID, cùng nhóm và trong1giờ. Loại bot, thu hồi/sửa và không đoán xuyên tin người khác.
- [x] Chỉ tự suy số lượng khi câu hỏi có một mã/tên mẫu rõ và một số lượng. Câu “này” chưa xác định mẫu, nhiều nguồn, thêm/bù/test/điều kiện thì kiểm tra nội bộ; chưa có đối chiếu ảnh tự động cho đại từ.
- [x] Đọc API ERP theo customer_id+mẫu trước phân tích và trước gửi. Một dòng khớp tên mẫu+số lượng: duplicate, không tạo mới. Nhiều đơn/khác số lượng/thiếu phản hồi: review. Không khớp: tiếp tục các gate hiện có, không bỏ verifier.
- [x] Tin gốc không thay đổi; thông tin xác nhận chỉ bổ sung trong bộ nhớ, có ID và nguyên văn câu hỏi.
- [x] 124 ca kiểm thử cách ly đạt; mock ERP, không tạo đơn thật hoặc gửi khách. Hub image quantity-confirmation-20261027; giữ image cũ rollback.
