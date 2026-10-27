# Quản lý tự lên đơn Hub trong ERP — 2026-10-26
Trang: /api/v1/integrations/zalo/manage, mục Nguyên tắc tự lên đơn ERP · Hub.
- Admin cấu hình bật/tắt Zalo/WhatsApp/Viber và thời gian gom tin 1–120 phút (mặc định30).
- ERP lưu revision và audit. Hub kéo qua machine API mỗi20giây; không mở cổng quản trị Hub ra Internet.
- UI hiển thị revision đã lưu và revision Hub xác nhận, cảnh báo snapshot quá120giây.
- Tắt kênh giữ nguyên nguồn/hồ sơ. Khi bật tiếp tục hồ sơ chưa hoàn thành, không reset hồ sơ done/uncertain/archived. Hàng chờ kênh tắt không chặn các kênh khác.
- Khi đã áp dụng cấu hình ERP, quá120giây không lấy được cấu hình mới thì tạm ngừng tự tạo đơn. Trước lần ERP nâng cấp đầu tiên vẫn giữ hoạt động cũ.
- Bảng tối đa200 hồ sơ gồm intake_runs và production_slip_orders, giờ Việt Nam, lọc chờ/đã lên/lỗi; chỉ mã đơn, trạng thái, lý do, không đưa ảnh base64 hoặc token vào snapshot.
- Nhánh tin/ảnh và phiếu lệnh có guard trước submit. Thời gian gom thay cửa sổ tin/ảnh; phiếu lệnh đầy đủ vẫn xử lý ngay.
- Quy tắc bỏ qua nhóm/nhân viên, ánh xạ, chống trùng và giới hạn sửa đơn giữ nguyên. Không cấu hình xuất file/duyệt in ở đây.

Checklist:
[x] Module ERP và UI, admin-only mutations, optimistic revision, audit.
[x] Module Hub sync/cache, stale guard, per-channel gates, snapshot.
[x] Kiểm thử SQLite giả, transport giả, kênh tắt không chặn kênh khác, không đổi đơn.
[x] Kiểm thử snapshot trên schema production chỉ đọc:151hồ sơ.
[x] Python/JavaScript syntax, build Hub, triển khai source có backup.
[ ] Người dùng restart ERP để khởi tạo bảng/routes mới.
[ ] Xác minh API live và Hub xác nhận revision sau restart; không thử tạo đơn thật.

Backup: Hub backups/intake-manage-20261026. Image: phucthanh-chatwoot-hub:intake-manage-20261026; trước đó nas-source-20261026. Không restart ERP tự động, không dọn Docker.
