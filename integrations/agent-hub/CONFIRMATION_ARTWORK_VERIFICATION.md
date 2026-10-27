
## 27/10/2026 — Nối “này in500 phải không” với ảnh
- [x] Ưu tiên ảnh quote đúng ID/client ID, ảnh kèm câu hỏi; không quote thì chỉ một ảnh ngay trước trong10phút, không chen tin người thật, không album/multiple mẫu.
- [x] Giữ nguồn cùng nhóm/account, bỏ hệ thống/thu hồi/sửa. Ghi image_source_id+SHA256 và question/confirmation IDs trong bằng chứng suy diễn.
- [x] Ưu tiên order_source_links cùng khách và snapshot ERP. Chưa có link thì đọc mã/tên logo rõ trên ảnh qua Gemini, cache theo hash+model+nhóm. Không chắc/multiple mẫu thì review, không suy tên chung.
- [x] Đối chiếu ERP trước phân tích và trước ghi; link ảnh và kết quả ERP mâu thuẫn thì dừng. Giữ tin gốc, khóa chống trùng hiện có.
- [x] 135 ca test cách ly đạt; AI/ERP mock, không tạo đơn thật. Chưa chứng minh độ chính xác OCR của ảnh thực tế; ảnh mơ hồ luôn cần kiểm tra nội bộ.
- Hub image confirmation-artwork-20261027; giữ image trước để rollback.
