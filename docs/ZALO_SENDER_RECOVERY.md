# Bộ gửi Zalo: giám sát và tự khởi động lại

Cập nhật 27/10/2026.

- Sender cập nhật heartbeat mỗi 3 giây, kể cả không có tin.
- Lỗi ghi status.json do Windows khóa file: thử 3 lần, ghi stderr nếu vẫn lỗi, không thoát vòng gửi.
- Scheduled Task `PhucThanh Zalo Sender Watchdog`: mỗi phút và khi đăng nhập, chạy ẩn qua WScript. Chỉ khởi động bộ gửi đã dừng; khoảng cách thử mở lại tối thiểu 180 giây.
- `stop.flag`: dừng chủ động. `halt.flag`: khóa an toàn. Không tự xóa hai cờ.
- Không cưỡng bức kill tiến trình sống nhưng heartbeat cũ; báo kiểm tra.
- Sao lưu stderr.log vào stderr.previous.log trước mở lại. Giữ sender.sqlite3 và khóa sender.lock; không reset journal, không replay tin uncertain.
- Không thao tác bộ đọc Zalo hoặc ERP.

## Điều phối
- Đang chạy: có tiến trình và heartbeat mới, không có lỗi tồn.
- Đang tự phục hồi: watchdog vừa yêu cầu mở lại trong 90 giây và chưa có tiến trình; hoặc đang thử preflight theo cơ chế hiện có.
- Bị khóa — cần kiểm tra: halt.flag/phase halted; ưu tiên hơn cảnh báo tiến trình đã dừng.
- Đã dừng chủ động: stop.flag.
- Cần kiểm tra: heartbeat cũ, không hồi phục, lỗi kết nối hoặc tin chưa rõ kết quả. Giữ chi tiết lỗi và ID tin. Không có nút gửi lại.

## Checklist
- [x] Xác định crash WinError 5 khi thay status.json.
- [x] Kiểm thử heartbeat bình thường, khóa tạm, khóa kéo dài bằng giả lập.
- [x] Tác vụ giám sát riêng bộ gửi, chạy ẩn, giữ stop/halt.
- [x] Kiểm thử 5 trạng thái điều phối bằng thư mục/SQLite tạm.
- [x] Không gửi tin thử, không reset khóa chống trùng.
- [ ] Khi lỗi API Zalo không tương thích: nhân viên kiểm tra; không tự sửa module bằng phỏng đoán.
