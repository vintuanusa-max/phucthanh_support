# Lên mẫu PSD — 27/10/2026

- [x] Tách yêu cầu in test/làm mẫu PSD khỏi ERP; lưu sample_job_id để không tái sử dụng làm đơn.
- [x] Điều phối có loại Lên mẫu, chi tiết nguồn/yêu cầu/trạng thái/đường dẫn. Hồ sơ xong vào lịch sử.
- [x] Ghép mã mẫu trong lời nhắn với tên PSD cùng nhóm. Thiếu/nhiều nguồn: chờ nguồn, không chọn file gần nhất tùy tiện.
- [x] Photoshop mở bản sao, giữ nguyên pixel và DPI trong PSD; xuất JPG CMYK chất lượng 12, giữ PSD gốc và ICC nếu có. Không dàn co vải/cữ túi.
- [x] Đọc PSD ResolutionInfo để kiểm chứng DPI độc lập; kiểm tra JPG CMYK, pixel/DPI và SHA256 khi lưu NAS.
- [x] Job và marker chống xuất trùng. Nếu JPG đã có: xác minh và hoàn tất lưu, không xuất lại. Thiếu output sau gián đoạn: cần kiểm tra.
- [x] Preview private Chatwoot, không ERP/RIP/gửi khách. Publishing không tự gửi lại nếu chưa rõ kết quả.
- [x] Giới hạn tải riêng PSD 1 GiB; nguồn khác giữ 256 MiB.
- [x] Kiểm thử SQLite giả lập: sample-only, trùng yêu cầu, file đến sau, mixed production, lỗi không tự retry.
- [x] n259: 18884×2094 px, 300 DPI, 159.8845×17.7292 cm, CMYK; Chatwoot private note 6243.

Output: INJAE/DESIGNER/n259_rung_cay/sample_5be0c322b649/n259_rung_cay.jpg; kèm PSD gốc và preview.png.

Giới hạn: hiện xuất toàn canvas/layer đang hiển thị của PSD. Không tự diễn giải từng artboard/layer PSD thành nhiều sản phẩm; yêu cầu thay kích thước hoặc chọn layer cần bổ sung xử lý. PSD không có DPI rõ ràng dừng kiểm tra. Kết quả mã hóa RGB sang CMYK dùng Photoshop hiện hành; cần duyệt màu nội bộ.

Quy tắc đường dẫn: {thư mục khách}/DESIGNER/{tên mẫu}/sample_{job}. n259 đã chuyển và kiểm SHA256 3 file về INJAE/DESIGNER/n259_rung_cay/sample_5be0c322b649; giữ khóa job, không xuất lại.

- [x] Lưu theo `{Khách hàng}/DESIGNER/{Tên mẫu}/sample_{job}`; không lưu tại DESIGNER chung.
- [x] Đã chuyển n259 và kiểm hash JPG, PSD, preview; cập nhật đường dẫn điều phối/cache, không xuất lại.
