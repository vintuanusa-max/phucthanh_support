# KPI năm — duyệt điểm lỗi (17/10/2026)

## Quy tắc hiện hành
- Cả nhóm File In Zalo và WhatsApp tiếp tục tạo phiếu chờ duyệt, đề xuất mặc định 1 điểm. AI không tự chọn nhân viên hoặc trừ điểm.
- Quản trị xem tin nguồn/ngữ cảnh, chọn nhân viên, sửa mức đề xuất 1–100 điểm và ghi lý do; chỉ nút Duyệt mới áp dụng điểm.
- Duyệt lại áp dụng chênh lệch. Đổi nhân viên hoàn người cũ và trừ người mới. Hủy/Không phải lỗi hoặc chuyển Chờ duyệt hoàn đúng số điểm đã áp dụng.
- Hủy là giữ phiếu và lịch sử, không xóa vật lý. Có lịch sử mức trừ, hoàn điểm, tài khoản duyệt và thời gian.
- KPI theo năm của tin báo, mặc định 100, không đặt lại theo tháng. Không chặn sàn điểm để bảo toàn số điểm hoàn chính xác.
- Giao dịch PostgreSQL khóa phiếu, kiểm tra version, khóa hàng KPI theo thứ tự cố định; cập nhật điểm/phiếu/audit nguyên khối. Gửi lại version cũ trả 409. Ingest giữ source_key chống trùng.
- Phiếu cũ: proposed_points=1, applied_points=0; không hồi tố trừ điểm, kể cả phiếu đã xác nhận trước nâng cấp.
- AI vẫn chỉ ghi chú nội bộ; không thay cấu hình đọc, không phát lại lịch sử và không thay đơn ERP.

## Mã nguồn và triển khai
- backend_v2/quality_incidents.py: migration hai cột, API review delta và GET /api/v1/quality/incidents/{id}/audit (quản trị).
- frontend_v2/src/pages/QualityReview.tsx: chi tiết, mức điểm, hủy/hoàn và lịch sử.
- 10 kiểm thử API giả lập gồm lifecycle, xác thực, chống trừ lặp, nhập sai, dữ liệu cũ; TypeScript/Vite và Chrome headless API giả lập đạt.
- Đã sao lưu và cập nhật mã trên NAS. Cần chủ hệ thống restart ERP để migration chạy/nạp API. Chưa duyệt hoặc trừ điểm thật để thử.


## Nhiều nhân viên trên một phiếu — 17/10/2026
- Chọn nhiều nhân viên; điểm đề xuất áp dụng CHO MỖI NGƯỜI, không chia đều. Giao diện hiển thị rõ điểm/người và số người trước khi duyệt.
- Bỏ người rồi lưu: hoàn đúng mức trước đó cho người bị bỏ. Người còn lại chỉ điều chỉnh chênh lệch. Hủy/chờ duyệt hoàn tất cả.
- UUID trùng được khử trùng; khóa phiếu/version và cập nhật nguyên giao dịch được giữ. Giao diện cũ không được ghi đè phiếu nhiều người.
- Migration employee_ids uuid[] sao chép người đã gán trước đó, giữ nguyên applied_points và KPI; không trừ hồi tố.
- Danh sách phiếu hiển thị mọi người được chọn. Lịch sử duyệt lưu danh sách trước/sau cùng chênh lệch điểm từng người.
- 11 kiểm thử API giả lập đạt; TypeScript/Vite và giao diện dữ liệu giả lập đạt. Không duyệt phiếu hay thay điểm thật.
- Đã cập nhật NAS; cần chủ hệ thống restart ERP để nạp migration/API mới.


## Mức trừ RIÊNG từng nhân viên — 17/10/2026 (thay quy tắc cùng mức)
- Mỗi nhân viên có ô điểm riêng 1–100, mặc định 1. Chỉ khi quản trị duyệt mới áp dụng. Chờ duyệt không trừ.
- proposed_allocations và applied_allocations JSONB lưu mức từng UUID. Điểm KPI thay đổi đúng chênh lệch giữa bản đã áp dụng và bản mới trong cùng transaction.
- Bỏ người: hoàn đúng mức cũ của người đó; hủy/chờ duyệt: hoàn toàn bộ applied_allocations. Chống version cũ và trừ/hoàn lặp. UI cũ bị từ chối khi phiếu đã dùng mức riêng.
- Dữ liệu cũ dùng employee_ids/applied_points để quy đổi khi đọc và duyệt lần tới. Migration chỉ thêm cột, không thay điểm thật.
- Giao diện bảng và chi tiết hiển thị mức riêng, lịch sử lưu bản trước/sau và delta từng người.
- 12 kiểm thử API cô lập, TypeScript/Vite và giao diện giả lập hai nhân viên 1/3 điểm đạt. Không duyệt phiếu thật.
- Đã cập nhật NAS và sao lưu; cần chủ hệ thống restart ERP để nạp API/cột mới.


## Xóa mềm phiếu lỗi — 17/10/2026
- Nút Xóa phiếu trong chi tiết; cần lý do và xác nhận. Máy chủ hoàn đúng applied_allocations từng nhân viên rồi đánh dấu deleted_at/deleted_by trong cùng transaction; phiếu cũ dùng applied_points tương ứng.
- Danh sách mặc định loại phiếu đã xóa. Chọn Phiếu đã xóa — xem lịch sử để đối chiếu nội dung, người liên quan và audit. Không xóa vật lý, không xóa source_key nên không tạo lại phiếu trùng từ tin cũ.
- Phiếu đã xóa không được duyệt lại; xóa lặp không hoàn thêm. Version cũ trả 409. Thống kê lỗi đã xác nhận không tính phiếu đã xóa.
- API POST /api/v1/quality/incidents/{identity}/delete (admin, version + note). GET incidents?archived=true chỉ lấy phiếu đã xóa; audit vẫn giữ đầy đủ.
- 14 kiểm thử API giả lập đạt; TypeScript/Vite và kiểm thử giao diện xác nhận xóa đạt. Không xóa phiếu thật hoặc thay KPI thật.
- Đã sao lưu/cập nhật NAS; cần chủ hệ thống restart ERP để thêm hai cột và nạp endpoint mới.
