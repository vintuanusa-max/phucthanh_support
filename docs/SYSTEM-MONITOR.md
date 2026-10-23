# Giám sát hệ thống — 23/10/2026
- Trang chỉ đọc: http://127.0.0.1:8096/ trên máy chạy bot.
- Mã: %LOCALAPPDATA%\PhucThanh\SystemMonitor; shortcut Desktop Phuc Thanh - Trang thai he thong.
- Theo dõi tiến trình và heartbeat Zalo/WhatsApp/Viber/ArtworkInspector, trạng thái mở Adobe, HTTP Hub/Chatwoot/ERP, tổng hàng đợi và 20 hồ sơ gần nhất (lý do review).
- Cập nhật mỗi 20 giây; đỏ khi tiến trình mất, vàng khi heartbeat cũ trên 180 giây. HTTP 200 chỉ chứng minh trang truy cập được, không chứng minh toàn bộ nghiệp vụ. Adobe đang mở không đồng nghĩa hết hộp thoại.
- Scheduled Task PhucThanh Export and Monitor Watchdog, khi đăng nhập và mỗi phút: chỉ mở lại worker/monitor nếu thiếu tiến trình; không kill ứng dụng, không replay job. Cần Windows đăng nhập để dùng Adobe Desktop.
- Adobe readiness: COM tự mở app, thăm dò Version tối đa 120 giây, lệnh xuất chỉ gọi một lần. Không retry DoJavaScript. Timeout báo lỗi; không tự đóng tài liệu.
- Kiểm thử readiness giả lập 3 trường hợp đạt; dashboard API có 9 cards/20 jobs, JavaScript parse đạt; task LastTaskResult=0. Chưa kiểm chứng cold-start Adobe vì hai ứng dụng đang mở.
- Không thay ERP, RIP, gửi khách hay xóa dữ liệu. Dashboard bind loopback, không có API ghi hoặc đọc cấu hình/token.

## 23/10 — Bảng điều phối file in
- http://127.0.0.1:8096/ ưu tiên hồ sơ chưa hoàn thành, tìm kiếm/lọc, ảnh nguồn, file PDF/AI, yêu cầu và lịch sử lý do bị chặn. Hồ sơ hoàn tất/đã đóng được ẩn khỏi chi tiết mặc định.
- Nút Phân tích và xuất bản mới chọn file thuộc hồ sơ, yêu cầu chủ xưởng 5–3000 ký tự. Tạo job mới giữ lịch sử cũ, instruction gắn riêng vào payload lượt xử lý; không sửa đơn ERP.
- Chống trùng theo hồ sơ+hash nguồn+nội dung yêu cầu; khóa khi active/uncertain, kiểm tra nhóm được phép và phiên bản hiện tại. PDF/AI qua artwork pipeline; ảnh riêng qua raster PET. Mockup không xuất trực tiếp từ nút này.
- POST hub cần admin; proxy local giữ key trong container, không gửi xuống browser. POST local yêu cầu CSRF, Origin/Host loopback; không có API RIP/gửi khách.
- 7 kiểm thử DB tạm đạt: duplicate, active, uncertain, foreign source, mockup, hidden complete, instruction preservation. UI thật JOSEON có 2 ảnh/3 nguồn/4 bước; chưa bấm xuất thật khi kiểm thử.
- Giới hạn: nhập yêu cầu không có nghĩa mọi chỉnh màu/vẽ lại đã được hỗ trợ. Pipeline không làm được phải review. Chưa bổ sung editor đồ họa hoặc thay đổi file trực tiếp. Danh sách tối đa 1000 hồ sơ mới nhất.
