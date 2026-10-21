# Theo dõi xin nghỉ — Cty In Phúc Thanh
- Nhóm Zalo g7345600934484454438 được mở đọc, chặn AI trả lời công khai/lên đơn/chuyển duyệt in theo ID. Nhóm khác giữ nguyên.
- Theo ID người gửi và tháng nghỉ, gộp ngày trùng; sáng/chiều 0,5, cả ngày 1. Tổng vượt 1 đề xuất tổng 1 điểm/tháng. Không tự trừ hoặc tự gán nhân viên ERP.
- Chỉ cộng tin tự xin nghỉ rõ người/ngày. Tin xin hộ, hủy/đổi, khoảng ngày, ngày không rõ tạo ghi chú nội bộ kiểm tra. Xin cho nhiều người chỉ cộng phần rõ của người gửi, đánh dấu phần xin hộ chưa xác định.
- Đây là số ngày XIN nghỉ, không phải xác nhận đã nghỉ. Quản trị kiểm tra thực tế và ngoại lệ trước duyệt.
- Một source_key/ID người/tháng; bổ sung tin cập nhật chứng cứ cùng phiếu, không thêm phiếu mới hoặc tự trừ thêm. Phiếu đã hủy/xóa/duyệt giữ quyết định và điểm; cập nhật nguồn tăng version, lưu audit.
- API /api/v1/quality/leave-ingest dùng khóa máy, không nhận employee_id/điểm. Cần chủ hệ thống restart ERP để nạp API mới.
- Lịch sử khả dụng tháng 10 có 9 tin; chỉ nhập đúng nhóm này. Không gửi dữ liệu này tới Gemini.
- 19 kiểm thử parser/API KPI cô lập đạt; chưa trừ KPI thật.

## Sau restart ERP — 17/10/2026
API leave-ingest đã nạp. Đã nhận đủ 12 biên nhận ERP với 12 ID khác nhau, đối chiếu khóa người/tháng. Tất cả points_deducted=0; không gọi API review. Hồ sơ tháng 4–10 dựa trên ngày xin nghỉ rõ nội dung, không phải chấm công thực tế; tin chưa rõ giữ trong báo cáo riêng để đối chiếu.

## Rà soát bổ sung — 17/10/2026
Chủ hệ thống xác nhận Bác/B Phương, khác em Phương. leave_reviewed.json lưu đối chiếu 68 tin theo từng người/ngày/ca, gồm tin bổ sung/sửa rõ. Tổng 28 hồ sơ vượt ngưỡng đã nhận biên nhận ERP, 28 ID riêng theo người/tháng; không trừ KPI. Bác Phương: tháng 6=2 ngày, tháng 8=4 ngày, tháng 10=1,5 ngày. Còn 24 tin chưa chắc giữ để kiểm tra; báo cáo data/reports/leave-review-20261017/bo-sung-bac-phuong.html. Giao diện chọn nhân viên chỉ hiện dang_lam; lịch sử vẫn giữ người cũ.
