# Bản đồ mô-đun

Desktop readers → capture/outbox → Hub SQLite → Chatwoot và kho NAS.
Hub order_intake gom tin → xác minh khách bằng ID → đề xuất/ghi ERP theo quyền cấu hình.
Hub print_approval → PNG/source manifest → print_deliveries riêng cho từng kênh.
Hub print_changes → phiên bản thông báo thay đổi → cùng hàng đợi gửi, không sửa đơn ERP.

- Khóa chống trùng gồm tài khoản, nhóm, ID tin và phiên bản nguồn.
- print_change_sources đặt chỗ các tin bổ sung đã thông báo.
- Gửi không chắc chắn hoặc tiến trình bị ngắt không tự gửi lại.
- Quyền AI/nhân viên, danh sách nhóm nội bộ và mốc bắt đầu đọc được lưu ở cấu hình/trạng thái riêng.
- Thay đổi sau duyệt cảnh báo dừng bản cũ, giữ nguyên lời khách, không tự coi ảnh mới là đã duyệt.
- Dữ liệu runtime, ánh xạ khách thật, khóa và nhật ký vận hành không thuộc bản mã nguồn này.

Xem README và các mô-đun tương ứng để thiết lập. Không xem bản đồ này là bản sao dữ liệu có thể khôi phục toàn bộ hệ thống.
