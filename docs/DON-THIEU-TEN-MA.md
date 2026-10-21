

## Đơn có ảnh/số lượng nhưng thiếu tên hoặc mã — 17/10/2026
- Agent không hỏi tên mẫu/mã ERP khi đã có mẫu trong ảnh và số lượng đặt rõ. ma_san_pham=null để ERP dùng Chờ mã; ten_mau rỗng để ERP tự đặt tên.
- Nếu agent vẫn gọi hỏi hai trường này, tool trả reconsider_order để vòng lặp chọn lại công cụ; không silent rồi bỏ sót. Các câu hỏi ngoài phạm vi khác vẫn bị chặn.
- 19 kiểm thử agent loop đạt, gồm câu hỏi trường tùy chọn và chính sách trả lời nội bộ. Không thay cơ chế nguồn/request_id chống lặp; không replay lịch sử hàng loạt.
