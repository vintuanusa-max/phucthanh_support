# Tiến trình file in trong đơn ERP — 22/10/2026

## Đã triển khai
- [x] Tab Tiến trình file in trong chi tiết đơn hàng: mẫu nguồn và bản xuất cạnh nhau, phóng to ảnh, trạng thái, nguyên nhân cần kiểm tra và đường dẫn NAS.
- [x] Nút Xuất PNG/TIFF cho quản trị: nhập chiều cao cm, chọn vị trí, giữ tỷ lệ, không lật gương. Không tạo/sửa đơn ERP; không RIP hoặc gửi khách.
- [x] Yêu cầu trùng đơn + hồ sơ + chiều cao + vị trí dùng cùng mã. Không chạy thêm khi công việc đang chạy hoặc chưa xác định kết quả.
- [x] Hub đẩy snapshot có ảnh thumbnail sang ERP, đọc yêu cầu mỗi vòng monitor ~30 giây; giao diện làm mới mỗi 15 giây khi đang hiển thị.
- [x] Dùng file artwork có sẵn. Xuất thủ công không cấp quyền gọi model vẽ lại trả phí. Với nền trắng chỉ tách phần nối với mép ảnh, giữ trắng bên trong; đối chiếu ảnh trước khi xuất TIFF.
- [x] API dùng phiên ERP cho người dùng, require_admin cho lệnh xuất; máy dùng token tích hợp hiện có. Snapshot chỉ nhận đúng order/customer đang còn tồn tại.
- [x] Thử CHÚ PHÁT DH-2610-323: cao 6,5cm, 768×768px/300dpi, PNG alpha và TIFF spot_1. Ghi chú riêng Chatwoot #4477 có 3 tệp; đơn vẫn 500 cái.
- [x] Bấm lại nút cùng thông số trên giao diện thật: chỉ một manual job, command done.
- [x] Docker giữ order-print-ui-final-20261022 (latest cùng image) và mockup-gate-20261022 dự phòng; không dọn volume/data.

## Vị trí mã
ERP: backend_v2/order_print_files.py, backend_v2/main.py; frontend_v2/src/components/OrderPrintFiles.tsx và DonHangDrawer.tsx.
Hub: hub/order_print_bridge.py, app.py, raster_pet.py, pet_exports.py, pet_render.py.
Bảng mới: order_print_files (snapshot), order_print_requests (lệnh xuất có mã chống trùng).
Backup ERP: data/releases/order-print-ui-20261022. Backup hub: backups/order-print-ui-20261022.

## Giới hạn hiện tại
- Chỉ tự liên kết hồ sơ có đúng một đơn ERP trong intake run; hồ sơ nhiều đơn cần liên kết rõ, không ghép đoán.
- Nút xuất một vị trí với một chiều cao; nhiều PDF/AI phải xác định phiên bản trước. Chưa có điều khiển sửa từng chi tiết/màu.
- Các lần kiểm tra cũ vẫn hiện trong lịch sử; xem lượt Đã xuất — chờ duyệt mới nhất.
- Đây là bản xuất để chủ xưởng duyệt; chưa xác minh chất lượng trên máy in vật lý.

## Kiểm chứng
Build TypeScript/Vite đạt; test API quyền và idempotency, test bridge chống trùng/chọn nhầm, test giữ trắng bên trong/alpha ngoài và 6,5cm đạt. Sau restart ERP: API200, tab thật hiện và có preview. CHÚ PHÁT job fcb4bd9f940c13ab2f0c726b75386e901bb04694e74e3536cb2419c80ea618fd done.

## Duyệt và copy TIFF — 22/10/2026
- [x] Nút Duyệt cạnh Làm mới, chọn rõ lượt TIFF đã xuất; chỉ quản trị có quyền duyệt.
- [x] API approve kiểm tra file thuộc đúng đơn và đã xuất xong. Lưu người duyệt/thời điểm trong order_print_requests; khóa theo đơn + danh sách job để tránh lặp.
- [x] Hub nhận lệnh approve vào erp_print_approvals; worker Windows copy từ archive phiên bản ra archive_root/<folder khách>/<tên TIFF>.
- [x] Giữ nguyên bản trong DESIGNER; kiểm tra SHA256 trước/sau, file đích giống thì bỏ qua, khác thì báo kiểm tra. Ghi file tạm .pending rồi rename không ghi đè trên Windows. Không RIP/gửi khách.
- [x] Test DB giả lập: quyền admin, sai job/đơn, duyệt lặp; test thư mục tạm: copy, lặp, collision, traversal/hash. Build giao diện đạt.
- [x] Hub print-approval-20261022 và worker đã cập nhật; giữ order-print-ui-final-20261022 làm dự phòng.
- [ ] Chờ chủ xưởng restart ERP để nạp endpoint approve; chưa duyệt/copy CHÚ PHÁT thật thay chủ xưởng.
- Backup ERP: data/releases/print-approval-20261022. Worker: worker.py.before-approval-20261022. Hub: backups/print-approval-20261022.
2026-10-22 post-restart verified: ERP OpenAPI exposes approve; unauthenticated request returns401; machine request poll200. Windows worker queries print-approvals successfully. No real approval/copy submitted; user will choose Duyet.

## Duyệt JPG CMYK CANAVI — 22/10/2026
- [x] Nút Duyệt liệt kê cả PET TIFF và JPG CMYK hoàn tất; chọn rõ job/version.
- [x] Hub chỉ lấy các panel JPG trong report đã đạt; kiểm tra native_ai_verified, verification.pass, CMYK/source ICC. Không copy AI ra ngoài.
- [x] Worker xác minh SHA256 JPG, mode CMYK và ICC gốc; AI cùng thư mục phải còn đúng hash. Copy nguyên byte ra folder khách, không chuyển màu/xuất lại. Giữ AI/JPG nguồn trong DESIGNER, tránh trùng và từ chối ghi đè bản khác.
- [x] Test tạm: JPG CMYK copy/lặp/AI giữ nguyên, từ chối RGB và AI bị đổi; API quyền/chống trùng và hub binding đều đạt. Build TypeScript/Vite đạt.
- [x] Hub jpg-approval-20261022 khỏe; worker cập nhật; giữ print-approval-20261022 dự phòng. Không RIP/gửi khách.
- [ ] Chờ chủ xưởng restart ERP nạp API cho phép jpg_exports; chưa duyệt/copy JPG thật thay chủ xưởng.
- Backup ERP data/releases/jpg-approval-20261022; hub backups/jpg-approval-20261022; worker approval_worker.py.before-jpg-20261022.

## 2026-10-22 — Automatic progress linkage
- [x] Conversation intake: project every confirmed ERP order; unmatched source shows a non-exportable waiting-match card.
- [x] Multi-order image clusters: persist source message IDs per uniquely verified order line; match each brief only to its disjoint source cluster and frozen submitted request/result order.
- [x] Production-slip intake: match source SHA256 within the same account/group/customer; repeated slips or mixed slips remain unassigned for review.
- [x] Explicit evidence links retained; repeated projection does not create duplicate cards/jobs/orders.
- [x] Regression checks: separation, replay, ambiguity, slip hashes, cross-group isolation, repeat-slip guard, explicit override.
- [x] Deployed auto-progress-20261022; CANAVI 329 and CHU DUNG 328 snapshots accepted by ERP.
- Limits: historical batches without per-line source lineage remain waiting-match. CAP VUONG 321/322 currently return ERP 404; no recreation. Externally created orders still require a verified linkage as for CANAVI 329, rather than name-only matching.
- Preview remains internal; this change does not submit exports, approve, copy, RIP, send customers or mutate order status/quantity.

## CANAVI — quy tắc kích thước chung (22/10/2026)
- [x] Đọc đủ phiếu, maket mới và AI/PDF đúng phiên bản.
- [x] Ưu tiên kích thước ghi trên maket; suy từ cữ chỉ khi rõ cùng mốc đo.
- [x] Dùng chiều có căn cứ làm chuẩn và giữ tỷ lệ artwork, không kéo méo cho khớp hai cữ.
- [x] Ghi chiều chuẩn, chiều theo tỷ lệ, chiều theo cữ, độ lệch cm để chủ xưởng duyệt.
- [x] Hai kích thước artwork khách ghi trực tiếp mâu thuẫn: chờ duyệt, không tự chọn.
- [x] PET không trừ co; JPG giữ quy tắc co vải/cữ may riêng; không lật gương.
- [x] Quy tắc chung đã nối vào prompt đối chiếu, lập kế hoạch và kiểm tra PET/JPG.
- Mẫu TDVKD-DINH.10 dùng 20 × 26,33 cm; không áp số này cho mẫu khác.
- Preview nội bộ, chưa tự duyệt/copy sản xuất/RIP/gửi khách. Không chạy lại đơn/file cũ.
- Kiểm tra cú pháp và đường truyền policy đã đạt; cần đối chiếu kết quả thực tế khi có đơn CANAVI mới, không bảo đảm LLM luôn đọc đúng số đo.

2026-10-22 CANAVI audit: all source images (no silent first-image/16-ref truncation), selection IDs constrained to inventory, nonblocking review_warnings separated from fatal issues and included in private PET/JPG previews. 8 offline regression checks passed; live health/import OK. Mixed live-text/vector/image PET still review; no historical replay or ERP writes. See docs/CANAVI-FLOW-AUDIT.md.

## 2026-10-22 — Các nhóm được phép đọc: TIFF/PET và JPG
- [x] Runtime all-export-20261022, health ok/review, 8 kiểm thử offline đạt.
- [x] Bỏ khóa tên nhóm ở JPG: comparison phải chứng minh sublimation bằng process_sources, cùng mẫu và file artwork. Không suy công nghệ từ tên nhóm.
- [x] Nhóm ngoài CANAVI xuất PDF/AI artwork theo artboard gốc, JPG CMYK; không áp co vải CANAVI, không dấu góc. Tên nguồn bỏ dấu. AI vẫn kiểm chứng native CMYK/artboard/font/link theo worker hiện có.
- [x] CANAVI giữ kế hoạch phiếu/maket riêng và AI đủ artboard. PET không chạy nếu comparison xác định sublimation/other; pet có bằng chứng được đi nhánh PET chung.
- [x] Giữ capture_allowed của cả Zalo/WhatsApp/Viber; không mở lại nhóm loại bỏ, nhóm nội bộ hoặc nhóm chưa được phép.
- [x] Giữ job/source claims, hash, uncertain publication, preview private, nút Duyệt thủ công; không RIP/gửi khách. Không replay hồ sơ cũ hoặc tạo đơn ERP.
- [ ] Chưa có đơn mới chạy thật xuyên suốt sau bản này. Nguồn thiếu/không rõ công nghệ, chỉ mockup hoặc cấu trúc chưa hỗ trợ vẫn cần review; không đồng nghĩa mọi file đều xuất tự động được.
