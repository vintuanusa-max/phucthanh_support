# KTTHAO: số lượng trên ảnh WhatsApp — 2026-10-19

- Sửa hub thiếu quote_recovery và các module đã có trên NAS nhưng thiếu trong image chạy.
- Giữ nguyên chặn media thiếu/hỏng. Riêng marker caption-unverified trên ảnh đã tải đủ được xử lý khi có lời đặt/chạy hàng rõ và đề xuất đơn được Gemini kiểm chứng lại bằng ảnh nguồn. Tin phủ định, hỏi chưa rõ, thiếu ảnh hoặc attachment khác vẫn chuyển kiểm tra.
- Không xóa marker/caption nguồn. Không gửi phản hồi công khai.
- Giữ request_id và trạng thái gửi bền vững để chống gửi lại; tra cứu đơn KTTHAO trước khi phục hồi.
- Hai mẫu đã tạo: DH-2610-269 Người Nhện 600; DH-2610-270 Halloween 500. Khách KTTHAO, Lên mẫu, mã hàng chưa rõ để Chờ mã.
- Run: 4106393f87ee0ebcff181d8625702659715b3bcf0b0711621cf1cdb447c5908b.
- Kiểm thử: 8 trường hợp guard, import image Docker, kiểm chứng ảnh Gemini, đọc lại ERP xác nhận len_mau 600/500.
