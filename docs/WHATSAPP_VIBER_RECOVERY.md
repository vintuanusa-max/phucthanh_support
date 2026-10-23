# Tự khôi phục bộ đọc WhatsApp và Viber — 22/10/2026

- Scheduled Tasks: PhucThanh WhatsApp Reader Watchdog; PhucThanh Viber Reader Watchdog. Chạy lúc đăng nhập và mỗi phút bằng user hiện tại, không mở cửa sổ.
- Launcher có mutex, kiểm tra đúng module/config; byte-lock trong reader ngăn hai writer. Không reset DB, cutoff, enabled_after, outbox hay session_identity.
- Stop-Reader.ps1 tại thư mục runtime tạo state/stop.flag, cả Startup và watchdog đều tôn trọng. Chạy Start-Reader.ps1 thủ công để tiếp tục sau khi đã dừng.
- WhatsApp dùng LocalState theo package family 5319275A.WhatsAppDesktop_cv1g1gvanyjgm: cập nhật phiên bản cài đặt không đổi đường dẫn dữ liệu này. Vẫn kiểm tra session_identity; không tự ghim tài khoản khác. Không tự chuyển sang beta/package family khác.
- Viber chọn Viber.exe đang chạy trong LOCALAPPDATA/Viber, kể cả thư mục con phiên bản; nhiều đường dẫn đồng thời thì chờ kiểm tra. Qt DLL lấy từ thư mục app thực tế. Đổi đường dẫn hoặc fingerprint EXE/Qt/plugin thì reader thoát để watchdog khởi động nạp DLL mới. Không hot-swap DLL trong tiến trình.
- Thay đổi định dạng DB/ABI Qt không được coi là chỉ đổi đường dẫn: khi không tương thích phải kiểm tra, không bỏ kiểm chứng để đọc tiếp.
- Chỉ giám sát reader, không thay đổi sender/AI/ERP. Không tự gửi tin thử. Viber vẫn chỉ nhóm đã ghim; WhatsApp theo chính sách nhóm hiện có.
- 5 tests nhận diện Viber: phiên bản thư mục con, loại đường dẫn ngoài app, nhiều phiên mơ hồ, app đóng, DLL đổi fingerprint.
- Watchdog hồi phục tiến trình đã thoát; không kill tiến trình còn sống do tác vụ đọc lâu. App cần đồng bộ dữ liệu về máy; không bảo đảm khôi phục tin chưa có trong kho cục bộ.
- Xác nhận sau triển khai: watchdog mở reader mới WhatsApp PID34272, Viber PID1352; errors rỗng; cutoff WhatsApp không đổi; counts accepted 34/13 không tăng do replay. Gọi watchdog lặp giữ nguyên PID. Đã sửa lỗi chữ hoa tên module trong launcher phát hiện lúc thử.
