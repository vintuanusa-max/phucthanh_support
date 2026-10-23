# Zalo reader: tự nhận phiên bản và tự khôi phục (22/10/2026)

- Runtime: C:\Users\Admin\AppData\Local\PhucThanh\ZaloDesktopReader.
- runtime.py chỉ nhận Zalo.exe đang chạy trong thư mục cài Zalo đã cấu hình, dưới Zalo-{version}. Không chọn tiến trình cùng tên ở nơi khác. Hai phiên chính đồng thời: chờ thay vì chọn đoán.
- reader.py kiểm tra phiên ở mỗi vòng; đổi đường dẫn/PID thì xóa khóa trong RAM và dò lại, không reset DB, cutoff, fingerprint hay outbox.
- Task Scheduler: PhucThanh Zalo Reader Watchdog, lúc đăng nhập và mỗi 1 phút, cùng user đang đăng nhập, không cần mật khẩu. Chỉ khởi chạy khi không có reader; mutex launcher và byte-lock reader ngăn chạy hai bản.
- Stop-Reader.ps1 tạo state/stop.flag: watchdog và Startup tôn trọng cờ, không tự bật lại. Chạy Start-Reader.ps1 thủ công để tiếp tục khi reader đã dừng.
- Không đóng/mở Zalo, không đổi tài khoản, không đụng dữ liệu Zalo. Nếu app chưa đăng nhập/sync thì reader chờ. Không bảo đảm khôi phục tin mà Zalo Desktop chưa đồng bộ hoặc nhóm đã bị loại trừ.
- Chống trùng giữ nguyên: outbox bền vững, chỉ đánh accepted sau Hub xác nhận; identity message/account/thread tại Hub. Không initialize lại lịch sử.
- 6 tests: đổi phiên bản, bỏ qua renderer, app đóng, exe ngoài thư mục, hai phiên mơ hồ, đổi PID. Kiểm tra thực tế chọn đúng 26.10.20.
- Đã kiểm tra watchdog không khởi chạy khi stop.flag tồn tại; sau gỡ cờ chạy qua Scheduled Task. Xem status.json: phase, updated_at, errors, outbox.
- Phạm vi tự hồi phục: tiến trình đã thoát. Không tự kill tiến trình còn sống vì đọc/tải lâu để tránh ngắt công việc đang chạy; heartbeat đứng yên cần kiểm tra riêng.
