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

## Xác minh sau restart — 17/10/2026
API đang chạy đã có ReviewIn.points mặc định 1 (1–100) và route lịch sử audit. SHA256 module NAS khớp bản kiểm thử. Chạy lại 10 test API cô lập và kiểm thử giao diện giả lập: đạt. Đã kiểm tra duyệt, chỉnh mức, hủy/hoàn, đổi nhân viên và gửi lặp. Trên ERP sản xuất chỉ GET; không POST duyệt hoặc thay điểm thật. Chưa kiểm thử ghi giao dịch vào PostgreSQL sản xuất. Trình duyệt IAB báo lỗi kết nối, nhưng GET OpenAPI từ máy trả 200.


## Nhiều nhân viên trên một phiếu — 17/10/2026
- Chọn nhiều nhân viên; điểm đề xuất áp dụng CHO MỖI NGƯỜI, không chia đều. Giao diện hiển thị rõ điểm/người và số người trước khi duyệt.
- Bỏ người rồi lưu: hoàn đúng mức trước đó cho người bị bỏ. Người còn lại chỉ điều chỉnh chênh lệch. Hủy/chờ duyệt hoàn tất cả.
- UUID trùng được khử trùng; khóa phiếu/version và cập nhật nguyên giao dịch được giữ. Giao diện cũ không được ghi đè phiếu nhiều người.
- Migration employee_ids uuid[] sao chép người đã gán trước đó, giữ nguyên applied_points và KPI; không trừ hồi tố.
- Danh sách phiếu hiển thị mọi người được chọn. Lịch sử duyệt lưu danh sách trước/sau cùng chênh lệch điểm từng người.
- 11 kiểm thử API giả lập đạt; TypeScript/Vite và giao diện dữ liệu giả lập đạt. Không duyệt phiếu hay thay điểm thật.
- Đã cập nhật NAS; cần chủ hệ thống restart ERP để nạp migration/API mới.

### Kiểm tra sau restart bản nhiều nhân viên
GET OpenAPI ERP xác nhận employee_ids và points mặc định 1; SHA256 module NAS khớp bản kiểm thử. 11 kiểm thử API cô lập đạt (hai người, đổi mức, bỏ người, hủy, chống trùng). Giao diện giả lập gửi đúng 2 ID và mức 3 điểm/người khi hủy. Trên ERP thật chỉ GET, không POST duyệt, không thay đổi KPI. Kiểm thử nghiệp vụ sử dụng DB giả lập, chưa ghi giao dịch vào PostgreSQL sản xuất.


## Mức trừ RIÊNG từng nhân viên — 17/10/2026 (thay quy tắc cùng mức)
- Mỗi nhân viên có ô điểm riêng 1–100, mặc định 1. Chỉ khi quản trị duyệt mới áp dụng. Chờ duyệt không trừ.
- proposed_allocations và applied_allocations JSONB lưu mức từng UUID. Điểm KPI thay đổi đúng chênh lệch giữa bản đã áp dụng và bản mới trong cùng transaction.
- Bỏ người: hoàn đúng mức cũ của người đó; hủy/chờ duyệt: hoàn toàn bộ applied_allocations. Chống version cũ và trừ/hoàn lặp. UI cũ bị từ chối khi phiếu đã dùng mức riêng.
- Dữ liệu cũ dùng employee_ids/applied_points để quy đổi khi đọc và duyệt lần tới. Migration chỉ thêm cột, không thay điểm thật.
- Giao diện bảng và chi tiết hiển thị mức riêng, lịch sử lưu bản trước/sau và delta từng người.
- 12 kiểm thử API cô lập, TypeScript/Vite và giao diện giả lập hai nhân viên 1/3 điểm đạt. Không duyệt phiếu thật.
- Đã cập nhật NAS và sao lưu; cần chủ hệ thống restart ERP để nạp API/cột mới.

### Xác minh sau restart mức trừ riêng
GET OpenAPI xác nhận employee_points theo UUID, mỗi mức 1–100. SHA256 module NAS khớp bản kiểm thử C36E23EB074A68AA04D61F510E8404FF091493A548845DAB8F2E337F1E96EEF3. 12 kiểm thử API cô lập và giao diện giả lập 2 người với mức 1/3 điểm đạt. Bao gồm chờ duyệt, duyệt lặp, đổi mức, bỏ người, hủy hoàn điểm. Trên ERP sản xuất chỉ đọc, không POST duyệt hoặc thay KPI. Chưa thử ghi giao dịch vào PostgreSQL sản xuất.


## Xóa mềm phiếu lỗi — 17/10/2026
- Nút Xóa phiếu trong chi tiết; cần lý do và xác nhận. Máy chủ hoàn đúng applied_allocations từng nhân viên rồi đánh dấu deleted_at/deleted_by trong cùng transaction; phiếu cũ dùng applied_points tương ứng.
- Danh sách mặc định loại phiếu đã xóa. Chọn Phiếu đã xóa — xem lịch sử để đối chiếu nội dung, người liên quan và audit. Không xóa vật lý, không xóa source_key nên không tạo lại phiếu trùng từ tin cũ.
- Phiếu đã xóa không được duyệt lại; xóa lặp không hoàn thêm. Version cũ trả 409. Thống kê lỗi đã xác nhận không tính phiếu đã xóa.
- API POST /api/v1/quality/incidents/{identity}/delete (admin, version + note). GET incidents?archived=true chỉ lấy phiếu đã xóa; audit vẫn giữ đầy đủ.
- 14 kiểm thử API giả lập đạt; TypeScript/Vite và kiểm thử giao diện xác nhận xóa đạt. Không xóa phiếu thật hoặc thay KPI thật.
- Đã sao lưu/cập nhật NAS; cần chủ hệ thống restart ERP để thêm hai cột và nạp endpoint mới.


## Xóa phiếu trực tiếp từ danh sách — 17/10/2026
- Nút Xóa ở từng dòng phiếu hiện tại; yêu cầu lý do và xác nhận. Dùng API xóa mềm hiện có với version; máy chủ hoàn điểm từng người và giữ lịch sử. Phiếu đã xóa không có nút xóa.
- Build TypeScript/Vite và kiểm thử giao diện với API giả lập đạt: hủy xác nhận không gửi POST; xác nhận gửi đúng version/lý do. Không thay KPI thật. Frontend-only, không cần restart.
- Kiểm tra sổ tiếp nhận bot: 28 khóa người/tháng, 28 ID ERP khác nhau, không có lần ingest tự trừ điểm. Chưa đối chiếu đầy đủ trùng người thực tế/phiếu đã duyệt trong ERP vì trình duyệt bị chặn truy cập.


## Bổ sung chứng cứ nghỉ phép — 17/10/2026
- Trong chi tiết phiếu, hiển thị lịch sử bổ sung theo ngày, tổng trước/sau và cam kết không tự thay KPI. Dùng audit leave_evidence_update đang có, không thay API.
- Đã kiểm thử giả lập 4 trạng thái pending/confirmed/dismissed/deleted: cập nhật cùng ID người/tháng giữ nguyên quyết định và điểm; lặp dữ liệu không tăng version/audit; tháng khác có phiếu riêng. Khóa là ID chủ thể ổn định, không phải tên hiển thị; khi đổi tài khoản cần đối chiếu ánh xạ người.
- Không thay dữ liệu hay KPI thật. Frontend-only, không cần restart ERP.
