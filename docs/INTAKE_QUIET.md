# Chờ đủ thời gian từ tin cuối — 27/10/2026
- Luồng ERP: cùng tài khoản, cùng nhóm, cùng người khách gửi. Mọi đợt đều chờ đủ wait_minutes từ tin cuối, kể cả có số lượng. Không còn ngưỡng 2 phút cho đơn đủ số lượng.
- Nối chuỗi tin có khoảng cách không quá thời gian cấu hình; đợt có thể dài hơn một cửa sổ 30 phút.
- Đọc đủ nguồn chưa nhận của cùng luồng, không chỉ 200 hàng toàn cục; nguồn chưa đồng bộ xong thì giữ chờ, không bỏ qua phần đầu/giữa để lên phần đuôi.
- Nhân viên, nguồn bị chính sách loại và nhóm/người khác không kéo dài bộ đếm.
- Kiểm tra trước phân tích và trước gửi ERP. Tin bổ sung tới trước gửi thì bỏ phần nháp/bằng chứng dẫn xuất chưa gửi, giữ nguồn để gom lại; không đụng submitted_payload hoặc hồ sơ đã gửi.
- Giữ khóa capture/run/request_id và cơ chế uncertain; không replay đơn cũ. Có thể tiếp tục chờ nếu nguồn lỗi chưa đồng bộ xong.
- Đã kiểm thử 11 ca thời gian/phạm vi/backlog; compile đạt; triển khai Hub, NAS/mirror đồng bộ. Không restart ERP, không dọn Docker.
- Phần gom file xuất 15 phút là cấu hình riêng, không thay đổi ở đây.
