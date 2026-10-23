# Drive → hồ sơ thiết kế → PNG/TIFF (21/10/2026)

- [x] Mở snapshot Drive đã tải xong, kiểm tra hash và đúng account/nhóm/message_id.
- [x] Đọc file con có hoặc không có phần mở rộng bằng chữ ký PDF/PNG/JPEG; giới hạn 32MB/file; giữ nguyên nguồn NAS.
- [x] Chặn đường dẫn ra ngoài snapshot, nguồn sai, hash sai. File chưa hỗ trợ không tự chuyển đổi tùy tiện.
- [x] Lượt đặt hàng đã phân tích đủ thông tin có file Drive được nối sang hồ sơ thiết kế riêng; không phụ thuộc có từ “làm mẫu”.
- [x] ArtworkChecks/PetExports tiếp tục đối chiếu maket, chọn object, xác minh kích thước và tạo tác vụ cho Photoshop. Thiếu/mâu thuẫn chuyển review, chỉ ghi chú nội bộ.
- [x] Lên ERP và xuất mẫu độc lập; không tạo lại đơn khi xuất file. Không RIP/gửi khách.
- [x] Thử A Thức: DH-2610-305, 300 cái, Lên mẫu. Có 3 file Drive; PDF và file thiết kế cùng sáu trang gồm logo nón và nhiều chi tiết áo.
- [x] Bản thử UEISPORT/UELSPORT: lấy trang 1 path1–26, bỏ nền0 và chữ LOGO. PNG 2938×430 300dpi; TIFF có alpha + spot_1. Chatwoot hội thoại7 ghi chú3858 (private), ba tệp đính kèm.
- [ ] Nhân viên duyệt ngang in: bbox vector khoảng24,86×3,63cm; raster24,875×3,641cm. Khác tỷ lệ thể hiện trên nón. Không tự thu về9cm hay áp kích thước đơn khác.

Nguồn code: integrations/agent-hub/zalo_desktop/drive_assets.py + vault.py; hub/drive_order_brief.py + order_intake.py + pet_exports.py. Bộ đọc Windows đã nạp mới. Hub image drive-design-20261021. Hồ sơ tự động có ID chống lặp theo run; file theo hash của nguồn. Bản thử được lưu A THUC/DESIGNER/UEISPORT/review-20261021. Không đổi số lượng/khách/giá ERP trong lượt xuất.

Giới hạn: không thể cam kết mọi Drive tự xuất thành công; file quá lớn, không phải PDF/AI tương thích, artwork lẫn mockup hoặc kích thước mâu thuẫn cần duyệt. Hồ sơ tự động của các file Drive vẫn chạy kiểm tra riêng; bản thử lượt này đã đối chiếu trực tiếp và phát hành nội bộ, chưa được phê duyệt sản xuất.

## Sửa sai UEISPORT: ưu tiên maket khách (21/10/2026)
Ảnh khách8399706661384 ghi rõ ngang7.5cm MẶT TRƯỚC; bản trước chỉ đọc DEMO trong Drive và bbox PDF nên kết luận thiếu mốc là sai. Không dùng bản24,86cm/ghi chú3858. Bản thay thế review-7p5cm-20261021: PNG886×130px300dpi (~7,5×1,10cm), TIFF alpha+spot_1 đã kiểm; ghi chú nội bộ3869 có3tệp. Đơn305 giữ300c.
Quy tắc: tổng hợp maket tin khách + maket Drive + PDF/AI; số đo rõ trên ảnh ưu tiên bbox file. “Kích thước như file” không được bỏ qua nhãn đo trong maket cùng đơn. Chỉ dùng source_layout khi thực sự không có số đo/mốc khác; tỷ lệ phối cảnh không có mốc cm phải ghi thiếu. Không áp7,5cm sang đơn khác. Đã triển khai prompt maket-priority-20261021; chưa RIP/gửi khách.
