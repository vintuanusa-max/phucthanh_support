# KTTHAO: số lượng trên ảnh WhatsApp — 2026-10-19

- Sửa hub thiếu quote_recovery và các module đã có trên NAS nhưng thiếu trong image chạy.
- Giữ nguyên chặn media thiếu/hỏng. Riêng marker caption-unverified trên ảnh đã tải đủ được xử lý khi có lời đặt/chạy hàng rõ và đề xuất đơn được Gemini kiểm chứng lại bằng ảnh nguồn. Tin phủ định, hỏi chưa rõ, thiếu ảnh hoặc attachment khác vẫn chuyển kiểm tra.
- Không xóa marker/caption nguồn. Không gửi phản hồi công khai.
- Giữ request_id và trạng thái gửi bền vững để chống gửi lại; tra cứu đơn KTTHAO trước khi phục hồi.
- Hai mẫu đã tạo: DH-2610-269 Người Nhện 600; DH-2610-270 Halloween 500. Khách KTTHAO, Lên mẫu, mã hàng chưa rõ để Chờ mã.
- Run: 4106393f87ee0ebcff181d8625702659715b3bcf0b0711621cf1cdb447c5908b.
- Kiểm thử: 8 trường hợp guard, import image Docker, kiểm chứng ảnh Gemini, đọc lại ERP xác nhận len_mau 600/500.

## 2026-10-21 — KTTHAO 1500, “Cho in luôn dùm nha Tuấn ơi”
- Gemini đã đề xuất đúng 1500 từ ảnh, nhưng guard caption-unverified không nhận “in luôn”, làm intake chuyển review/ValueError.
- Mở rộng xác nhận ở guard thành in luôn / in dùm / in giùm. Vẫn yêu cầu ảnh có asset ready, hash/path, không thiếu media, không phủ định/hỏi; vẫn qua Gemini verification và idempotency trước ghi ERP.
- 15 kiểm thử guard đạt. Đã triển khai image ktthao-1500-20261021, đồng bộ nguồn live và integrations/agent-hub.
- Khôi phục đúng đề xuất đã lưu của run 8e1f2ed934598c0291a7820e82b9189811ef243979780497dd376e34d4055760 qua luồng analyze/evidence hiện hành; không reset toàn bộ hàng đợi.
- Kết quả DH-2610-304, UUID d6f26609-79de-4214-9b75-ce12a5c5edca, khách KTTHAO, Mặt nạ Halloween 1500, Lên mẫu, Chờ mã. Đối chiếu đơn Halloween500/NgườiNhện600 trước đó; không sửa hay tạo lại đơn cũ. Ghi chú chỉ nội bộ Chatwoot.

## Mã mặt nạ — 21/10/2026
- Theo chủ hệ thống: mặt nạ dùng MATNA (ERP ID e66a530e-37a6-4f3d-b068-3d6efc4e9deb).
- mask_product.apply_mask_product ánh xạ từng dòng đã được phân tích/xác minh, tên mẫu có “mặt nạ”, thiếu mã hoặc đã là MATNA. Không ghi đè mã khác, không áp sang dòng nón chung, không suy số lượng.
- DH-2610-304 đã đổi từ Chờ mã sang MATNA bằng giao diện ERP, vẫn 1500, Lên mẫu, giá 0 như trước. Không tạo lại đơn.
- 7 kiểm thử mapping đạt; triển khai hub matna-20261021. Phản hồi AI vẫn nội bộ.
