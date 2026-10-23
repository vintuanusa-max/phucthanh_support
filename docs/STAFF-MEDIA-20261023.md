# Ảnh nhân viên làm bằng chứng duyệt in — 23/10/2026

- Nguyên nhân: reader dùng eligible(ERP) để kích hoạt tải media, nên ảnh nhân viên bị loại thành unsupported type2.
- Sửa capture: ảnh type2 của nhân viên trong config hoặc chính tài khoản, ở nhóm được phép đọc, được lưu media độc lập với eligible ERP. origin=staff; skip_groups giữ ưu tiên. Mốc bắt đầu 00:00 23/10/2026 (+07), không mở tải lịch sử trước mốc.
- Backfill đúng ngày 23/10: 57 placeholder, khôi phục55 ảnh, jobs Chatwoot done55. Hai tin còn lại ở File In có ID cục bộ dạng *_0001, không tìm được ảnh qua đường đọc này; không suy đoán hoặc nhập trùng.
- Hub giữ bảng staff_media_repairs với payload cũ và khóa capture_id, thêm ảnh vào đúng capture ID/revision, job bổ sung khóa riêng :staff-media-20261023. Không sửa ERP. Ảnh mới origin=staff luôn không eligible tạo đơn.
- BÍCH VÂN ảnh gốc8407763343941 → Chatwoot5270/hội thoại78. Hồ sơ95a2b9a6fad8cf83d0739c4659303e22474cf3d3ad9ce2f621d23d884e0d1fe0 đã chọn ảnh này + tin chốt8407996469291, đưa lại awaiting_evidence sau kiểm tra chưa gửi kênh nào.
- Giữ mốc gửi duyệt >=18:00 hôm nay; không reset các hồ sơ hoặc delivery cũ khác.
- Test mock: ảnh nhân viên hôm nay tải được, ảnh trước mốc không mở mới, nhóm bỏ qua giữ nguyên, nhân viên không eligible ERP. Reader reload giữ checkpoint.
`n- Kết quả cuối: BÍCH VÂN confirmed; cả zalo-personal-1 và whatsapp-personal-1 confirmed. Reader running PID40680, không có lỗi trạng thái.
