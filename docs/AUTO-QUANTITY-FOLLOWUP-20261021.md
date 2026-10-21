# Tự động tiếp nhận bổ sung số lượng — 21/10/2026

- Đã triển khai hub image `phucthanh-chatwoot-hub:quantity-auto-20261021`; health HTTP 200.
- Tin bổ sung nối lại nguồn cùng người gửi, nhóm và ngày (giờ Việt Nam), tối đa 12 tin nguồn cũ. Bao gồm hồ sơ chờ thông tin đã hết 30 phút; phân tích lại trước khi tạo đơn, không chỉ lấy con số rồi tạo ngay.
- Không lấy lại run có request_id/submitted_payload hoặc đã created/sending/uncertain. Giữ khóa nguồn, request id và claim trước ghi ERP; kết quả mạng không rõ không tự gửi lại.
- Ưu tiên ánh xạ ID khách hiện có. Nhóm chưa ánh xạ vẫn thử quy tắc tên ERP; nếu ERP trả 409/422 không khớp tên, tạo ánh xạ ID KHACH LE và ghi chú nội bộ. Đây là fallback khi chưa xác định được khách, không khẳng định khách không tồn tại dưới tên khác. Lỗi xác thực/kết nối hoặc khách đã ánh xạ bị xóa không được đổi thành khách lẻ.
- Giữ quy tắc thiếu mã hàng = Chờ mã, tên thiếu do ERP tự đặt; trạng thái tạo Lên mẫu. Không suy mã từ tên file.
- AI vẫn chỉ ghi chú riêng Chatwoot; không thêm gửi khách.
- 15 kiểm thử cô lập đạt (SQL phục hồi, timeout, đã gửi, khách đã ánh xạ, tên khớp, fallback, lỗi mạng/xác thực). Không tạo đơn ERP thử.
- Mã: hub/order_intake.py. Sao lưu `.before-quantity-auto-20261021.bak`; image trước `quantity-auto-base-20261021`. Không sửa/restart ERP.
- Không tự phát lại lịch sử. Những yêu cầu nhiều mẫu hoặc lượng còn mâu thuẫn vẫn cần kiểm tra nội bộ.
