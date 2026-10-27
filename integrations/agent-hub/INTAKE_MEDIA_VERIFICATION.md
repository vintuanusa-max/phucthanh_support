# ERP intake: ảnh chuyển tiếp / ảnh nhân viên — 27/10/2026

- [x] 54 ca mô phỏng đạt (26 ca ảnh/ngữ cảnh mới + 28 ca quy tắc hiện tại), container network none, không DB/API key thật; kết quả intake-media-final.xml.
- [x] Ảnh origin staff/outgoing không được observations() đọc cho lên đơn; OrderIntake.eligible giữ kiểm tra cấu hình tên nhân viên và nhóm bỏ qua.
- [x] Preflight không được bỏ yêu cầu đặt thêm, số lượng hoặc lên mẫu dù text classifier trả nhầm payment/delivery.
- [x] Ảnh có byte giống nguồn đơn created/duplicate có ID ERP, cùng account/thread: nếu khách chỉ duyệt thì ignored; nếu chỉ forward/nhắc chưa rõ thì review không đọc ảnh và không tạo lại. Giữ nguồn để tin mới có thể bổ sung.
- [x] Có số lượng/yêu cầu mới thì không dùng ảnh trùng để loại yêu cầu; vẫn qua xác minh và chống trùng hiện có. Không lấy lượng cũ làm lượng đặt thêm.
- [x] ContextGate dùng observation cache chắc chắn nếu có đủ ảnh; cache thiếu/uncertain vẫn giữ ảnh cho kiểm tra. Cache chỉ là thông tin ảnh, không phải quyết định đặt hàng.
- [x] So trùng theo từng ảnh, tối đa 200 nguồn gần nhất, không nạp toàn bộ ảnh lịch sử vào RAM. Không khớp thì tiếp tục luồng thông thường.
- [x] Không sửa quyết định cũ, không replay đơn, không gọi API ERP thật trong test. Image intake-media-20261027; cập nhật Hub/NAS/mirror.

Giới hạn: chỉ nhận trùng byte chính xác; ảnh chụp lại/cắt/nén khác chưa dùng fuzzy match để tránh bỏ nhầm đơn. Verifier cuối vẫn có thể đọc ảnh gốc khi xác minh đề xuất; không loại bỏ bước kiểm chứng số lượng để tiết kiệm token. Chưa đo chi phí AI thực tế hoặc xác nhận mọi biến thể ngôn ngữ; kết quả là kiểm thử giả lập có kiểm soát, không cam kết 100% đơn thực tế.
