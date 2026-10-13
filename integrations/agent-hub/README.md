# Phúc Thành Agent Hub

Mô-đun tích hợp Chatwoot, Gemini, Zalo Desktop, WhatsApp Desktop, kho NAS và ERP.
Bản sao mã nguồn ngày 2026-10-13; không chứa dữ liệu triển khai hoặc khóa truy cập.

## Chức năng
- Nhận tin nhóm được cho phép, ánh xạ ID nhóm → ID khách ERP; bỏ qua nhóm nội bộ và tin riêng theo chính sách.
- Lưu ảnh/tệp/đường dẫn tải trên NAS, xem ảnh trong Chatwoot; thu thập ảnh khách trích dẫn khi xác minh được nguồn.
- Gemini hỗ trợ phân tích, chuyển nhân viên khi thiếu thông tin. Gom tin trước khi đề xuất/lên đơn trạng thái Lên mẫu.
- Tổng hợp ảnh và lời duyệt thành PNG; gửi riêng từng kênh tới nhóm sản xuất, có nhật ký chống gửi trùng.
- Theo dõi tin sửa số lượng/ảnh sau duyệt; gửi bản cập nhật có nhãn cũ/mới, mã hồ sơ và cảnh báo tạm dừng in bản cũ.

## Thành phần
- `hub/`: API, hàng đợi, chính sách, Gemini/Chatwoot/ERP, bằng chứng và thông báo duyệt in.
- `zalo_desktop/`, `whatsapp_desktop/`: các đầu nối Windows theo phiên Desktop hiện có.
- `support_adapter/`: cầu nối với bot web cũ ở thư mục gốc repo.
- `deploy/`: Docker Compose và script thiết lập; `tests/`: kiểm thử giả lập.

## Thiết lập
1. Cần Python 3.11+, uv, Node.js và Docker Desktop chạy Linux containers trên Windows.
2. Trong thư mục này chạy `uv sync --group desktop --group whatsapp --group dev`.
3. Sao chép `deploy/.env.example` thành `deploy/.env`, cấu hình khóa riêng của hệ thống. Không commit `.env`.
4. Xem `deploy/Initialize-Config.ps1`, `Start-Stack.ps1`, `Configure-Chatwoot.ps1` trước khi chạy trên máy mới.
5. Đầu nối Desktop cần `reader.local.json`, baseline và trạng thái tài khoản riêng. Chuyển tài khoản cần xác minh/ánh xạ lại; không dùng mốc lịch sử rỗng để chạy lại toàn bộ tin.
6. Các launcher trong `deploy/windows/` là mẫu vận hành: launcher WhatsApp phải đặt tại thư mục runtime có `code/`, `state/`, `reader.local.json`. Script bật cổng WebView2 cần quyền quản trị và chỉ áp dụng riêng WhatsApp trên localhost.

Mặc định cấu hình mẫu giữ gửi tin/ghi ERP ở trạng thái tắt. Không chạy lại bootstrap trên bộ dữ liệu đang vận hành nếu chưa xem xét. Không dùng `docker compose down -v` trên hệ thống có dữ liệu cần giữ.

## Giới hạn
Đầu nối Desktop phụ thuộc phiên bản ứng dụng và phiên tài khoản đã kiểm chứng, không phải API công khai ổn định của Zalo/WhatsApp. ID nhóm sản xuất và phiên bản build có chốt kiểm tra trong mã gửi; cần điều chỉnh/xác minh cho môi trường khác. Không đảm bảo đầy đủ lịch sử hoặc sự kiện sửa/thu hồi chưa được bộ đọc thu nhận. Kết quả gửi không chắc chắn phải đối soát, không tự thử lại.

Chatwoot upstream không được chép vào repo; Compose dùng image Chatwoot v4.18.0. ERP backend nằm trong repo triển khai riêng; cần API hỗ trợ ID nhóm Zalo/WhatsApp và ID khách hàng.

## Kiểm thử
`uv run --group dev pytest tests -q`

Các kiểm thử giả lập không thay thế kiểm tra tài khoản thật. Hai đường gửi duyệt in đã được kiểm chứng trên môi trường của chủ hệ thống; luồng thay đổi sau duyệt đã kiểm thử và bật nhưng chưa có lượt thay đổi thật để đối chiếu tại thời điểm chụp bản này.
