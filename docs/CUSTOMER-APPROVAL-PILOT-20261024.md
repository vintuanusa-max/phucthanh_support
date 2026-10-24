# Thử nối ảnh khách duyệt vào ERP — 24/10/2026
- Phạm vi: CHÚ PHÁT và Chú Dũng, chỉ đơn Mẫu có sẵn.
- Không tạo bảng/giao diện duyệt mới. Dùng ảnh khách đặt + ghi chú hiện có.
- API mới chuẩn bị: danh sách đơn/ảnh theo đúng khách + trạng thái, đọc ảnh bảo vệ token; bổ sung ảnh tổng hợp và ghi chú trong cùng giao dịch.
- Chống trùng bằng mã bằng chứng trong ghi chú, advisory lock theo bằng chứng; chặn gán bằng chứng sang đơn khác; giữ ghi chú và ảnh cũ. Tối đa 10 ảnh: báo kiểm tra, không xóa ảnh.
- Đối chiếu trực quan: CHÚ PHÁT DH-2610-323 cùng huy hiệu Trường Tân Hạnh. Chú Dũng DH-2610-328 Pieter van Gent không khớp ảnh mẫu SI SÓC / WÁTH PÍCH. Đã ghi chú nội bộ Chatwoot 5482, chưa gán đơn Dũng.
- Kiểm thử giả đạt: thêm ảnh một lần, giữ ghi chú cũ, khóa trạng thái khác Mẫu có sẵn, không gán trùng khác đơn, gửi lại không thêm ảnh/ghi chú.
- CHƯA HOÀN TẤT: cần chủ xưởng restart ERP nạp API rồi đọc danh sách ảnh từ DB để xác nhận đúng bản hiện hành, rà toàn bộ ứng viên Mẫu có sẵn đúng khách và thực hiện pilot. Chưa sửa đơn thật.
- Mã trong work/customer-approval là bản chuẩn bị; image customer-proof/customer-note chưa triển khai. Observer tự động so nội dung ảnh chưa bật. Không coi mã băm khác nhau là nội dung khác nhau; ảnh chụp mẫu phải đối chiếu trực quan với ảnh ERP.

## Tự động cho các nhóm — 2026-10-24
- [x] Hub chạy approval-all-20261024; chỉ áp dụng tin duyệt mới từ mốc ENABLED_AFTER lưu trong source, không quét lại lịch sử.
- [x] Tôn trọng nhóm bỏ qua; lấy khách theo ID nhóm. Chưa ánh xạ hoặc KHACH LE: ghi chú nội bộ, không tìm chéo nhóm.
- [x] Xét toàn bộ đơn đúng khách ở Mẫu có sẵn; so sánh từng ảnh đặt hàng với ảnh mẫu nhân viên. Đơn đầu không khớp thì tiếp tục đơn sau.
- [x] Chỉ một đơn khớp rõ, không còn ứng viên chưa rõ: thêm ảnh tổng hợp và nối ghi chú ERP; giữ ảnh/ghi chú cũ và trạng thái đơn.
- [x] Khóa giao dịch và mã bằng chứng chống trùng; Hub lưu kết quả so sánh để tránh gọi AI lại.
- [x] Không khớp, nhiều đơn khớp, ảnh chưa rõ hoặc API từ chối: báo nội bộ Chatwoot có khóa chống báo trùng.
- [x] Pilot CHÚ PHÁT DH-2610-323 và Chú Dũng DH-2610-225 đã thêm bằng chứng; đơn 328 khác artwork không bị gán. Gửi lại cùng ID trả duplicate=true, số ảnh không đổi.
- [x] Chỉ restart Hub; không restart ERP, không dọn Docker, không gửi lại File In.
- [ ] Theo dõi tin duyệt mới thực tế sau triển khai mở rộng. Mỗi lượt tối đa 2 phép đọc ảnh mới, vòng kiểm tra 30 giây; thời gian hoàn tất tùy số ứng viên và API ảnh.
