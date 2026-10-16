> **Vận hành hiện tại (14/10/2026):** bản triển khai đã bật agent cho các nhóm được phép, tự lên đơn ERP Lên mẫu qua luồng kiểm tra/bằng chứng/chống trùng. Chỉ câu trả lời AI là ghi chú private Chatwoot. `agentic.auto_order=true`, `public_replies=false`, `internal_only=true`. Các mặc định cài mới và hướng dẫn CLI bên dưới không phải cấu hình production. Xem `../../docs/CHUC_NANG_VA_VAN_HANH.md` và checklist để biết trạng thái hiện hành.

# Phúc Thành Agent Hub

Bản tích hợp thử nghiệm cho Chatwoot v4.18.0, chạy trên Windows bằng Docker Desktop.
AI chính: Gemini, giữ model đang có trong bot (`gemini-2.5-flash`), thay được bằng biến môi trường.

## Trạng thái thực tế

- Đã có: dịch vụ Gemini/Chatwoot, webhook HMAC, hàng đợi SQLite, chống webhook lặp,
  phân biệt tin phản chiếu và tin cần gửi, quyền AI/nhân viên, đề xuất đơn và duyệt ERP.
- Đã có: đầu nối tùy chọn với `phucthanh_support`, lưu tin được bot publish vào hàng đợi cục bộ;
  nhánh gửi WhatsApp theo ID và truyền nội dung bằng tham số JavaScript.
- Mặc định khi cài mới (không phản ánh bản production đã kiểm chứng): `HUB_MODE=review`, gửi kênh tắt, ghi ERP tắt.
- Chưa có đầu gửi Zalo theo ID ổn định; không cho tự động gửi Zalo ở bản này.
- Chưa thay bộ quét Zalo/WhatsApp cũ bằng thu thập sự kiện và đối soát đầy đủ.
  Vì vậy chưa đảm bảo lấy hết tin từ điện thoại, lịch sử bỏ sót, sửa/thu hồi.
- Chưa hỗ trợ chuyển media/trích dẫn xuyên kênh. Có media thì chuyển nhân viên, không bịa nội dung ảnh.
- Chưa có kho tri thức nghiệp vụ đã duyệt. `knowledge.json` để trống có chủ ý.
- ERP dùng hợp đồng hiện có `/api/v1/integrations/zalo/orders` ở backend_v2; chưa xác nhận máy ERP đang chạy phiên bản này.

Đây chưa phải hệ thống vận hành hoàn chỉnh. Các kiểm thử là giả lập, không thay thế kiểm tra Docker, Gemini, ERP và tài khoản thật.

## Kiến trúc

- `hub/config.py`: cấu hình/khóa ngoài mã nguồn, tài khoản kênh và inbox.
- `hub/models.py`: hợp đồng tin nhắn, quyết định AI, đề xuất đơn.
- `hub/store.py`: sự kiện bền, quyền xử lý, liên kết hội thoại, kết quả ngoài hệ thống.
- `hub/clients.py`: Chatwoot API, Gemini REST và ERP adapter.
- `hub/engine.py`: điều phối, phản chiếu, xử lý AI, chuyển nhân viên, đơn nháp.
- `hub/app.py`: xác thực, API, worker một tiến trình và giao diện quản trị.
- `support_adapter/chatwoot_relay.py`: cầu nối trên máy bot, SQLite cục bộ, dùng khóa trình duyệt hiện có.
- `deploy/`: Compose, cấu hình và script khởi động Windows.

Không sửa lõi upstream Chatwoot. Mỗi tài khoản một inbox. Khóa nhận tin gồm tài khoản + thread + ID tin + revision.
Không suy luận khách ERP từ nội dung khách gửi. Liên kết ERP phải do quản trị xác nhận.

## Chạy sau khi Windows khởi động lại

1. Mở Docker Desktop, đợi engine Linux sẵn sàng.
2. Trong PowerShell, vào thư mục `deploy`, chạy `./Start-Stack.ps1`.
3. Chạy `./Configure-Chatwoot.ps1` để tạo tài khoản local, hai inbox và Gemini Agent Bot.
4. Mở `http://localhost:3000`. Thông tin đăng nhập mới nằm trong `deploy/admin-login.local.json`.
5. Mở `http://localhost:8095`. Dùng `HUB_ADMIN_TOKEN` trong `deploy/.env` để xem trạng thái.

Dữ liệu PostgreSQL/Redis/Chatwoot/hub ở Docker named volumes trên Windows, không dùng SQLite trên ổ mạng U:.
Compose chỉ mở cổng ở 127.0.0.1. Bot ở MAY1 khác máy sẽ chưa gọi được hub; cần triển khai HTTPS nội bộ và cấu hình tường lửa theo địa chỉ máy cụ thể trước khi kết nối. Không đổi sang 0.0.0.0 một cách tự động.
Không chạy `docker compose down -v` vì thao tác này xóa dữ liệu.

`SAFE_FETCH_ALLOW_PRIVATE_NETWORK=true` chỉ nằm trong bộ Compose thử nghiệm được chủ hệ thống chấp thuận,
để Chatwoot gọi `http://hub:8095`. Không áp dụng cấu hình này vào ERP hoặc cài đặt Chatwoot khác.

## Chế độ review và live

`review`: mặc định ghi kết quả dự kiến vào `effects`. Các luồng được bật riêng với `apply_capture`, `erp_write` và `agentic.auto_order` có quyền thực thi độc lập; không dùng riêng HUB_MODE để kết luận production ngừng ghi ERP.
Có thể gọi Gemini nếu có khóa và có webhook test được cấp quyền; demo riêng thì không gọi Gemini.
Không tái sử dụng cơ sở dữ liệu review để chuyển live: review có ID hội thoại giả. Tạo volume/database live riêng.

`live`: worker gọi Chatwoot thật. Vẫn phải bật `delivery_enabled` riêng từng inbox và
`whatsapp_delivery_enabled` trên relay mới gửi WhatsApp. Zalo delivery bị giữ tắt đến khi có adapter ID đã nghiệm thu.
Không bật bot cũ trả lời tự động đồng thời với Gemini cho cùng hội thoại.

Gắn Agent Bot vào inbox làm hội thoại mới ở trạng thái pending. Hub chỉ trả lời khi pending và không có nhân viên tiếp quản.
Khi nhân viên gửi tin, hoặc conversation chuyển open/được giao nhân viên, hub dừng AI.
Muốn giao lại AI: bỏ gán nhân viên trong Chatwoot rồi dùng nút/API giao lại AI.
Chuyển người: ghi quyền human, mở conversation, ghi private note lý do để hiện trong danh sách xử lý.
Chưa cấu hình cảnh báo Telegram/email; chưa gửi thông báo cho bên ngoài.

## Tri thức Gemini

`knowledge.json` là mảng các bản ghi `{ "id": "...", "approved": true, "text": "..." }`.
Chỉ đưa nội dung đã duyệt. Không ghi khóa, mật khẩu hoặc thông tin khách khác vào tri thức.
AI phải trả quyết định JSON; schema được kiểm tra bằng Pydantic. Nguồn không hợp lệ hoặc Gemini lỗi thì chuyển người.
Việc kiểm tra ID nguồn không chứng minh từng phát biểu đúng; cần kiểm thử chất lượng trả lời trên bộ hội thoại mẫu.
Giá, tồn kho và trạng thái đơn chưa có công cụ tra cứu trực tiếp ở bản này; AI được yêu cầu chuyển người khi thiếu dữ liệu.

## ERP

AI chỉ tạo draft. Quản trị liên kết conversation với group_name ERP tại
`POST /admin/conversations/{id}/erp-mapping`, sau đó duyệt draft qua giao diện/API.
Chỉ khi `HUB_MODE=live`, `ERP_WRITE_ENABLED=true`, có URL/token và mapping thì mới gọi ERP.
Request ID cố định `chatwoot:<draft-id>`; bấm duyệt lại không tạo đơn thứ hai.
Lỗi mạng sau khi gọi ERP đưa draft thành uncertain; chưa có nút tự retry. Đối soát ERP theo request_id trước.
Không chuyển luồng thông báo hoàn thành đơn hiện có; bridge ERP cũ vẫn giữ nguyên.

## Đầu nối bot

`main.py` của phucthanh_support có móc `start_if_configured()` trước khi khởi động kênh.
Không có `PHUCTHANH_HUB_CONFIG` thì không có hành vi mới.
Copy `hub_config.example.json` thành file riêng ở máy bot, cấu hình token ingest, tài khoản và đường DB local.
Đặt `PHUCTHANH_HUB_CONFIG` tới file đó; bật từng bước trên tài khoản thử.
Đầu nối hiện thu những tin mà bộ quét cũ publish; không làm đủ các mục Z1–Z9/W1–W4 của kế hoạch cũ.
Nhánh WhatsApp gửi theo ID và khóa dùng chung; không mở phiên browser mới, không tìm gần đúng tên.

## Kiểm thử

`uv sync --frozen`
`uv run pytest -q`
`uv run ruff check hub support_adapter tests`

`uv run python -m hub.demo` mở bản minh họa tại `http://localhost:8096`.
Token demo: `local-review-only-synthetic-data-123456` (chỉ dữ liệu giả, không phải khóa hệ thống).
Ba tình huống: AI chào khách, chuyển nhân viên, tạo đề xuất đơn. Đây không phải màn hình Chatwoot hoặc phản hồi Gemini thật.

## Nghiệm thu còn lại

- Khởi động Docker/Chatwoot sau restart, chạy migration/bootstrap và kiểm tra webhook thật.
- Xác minh model/khóa Gemini hoạt động, bổ sung tri thức và đánh giá câu trả lời.
- Xác nhận vị trí máy bot, đường mạng, phiên WhatsApp và ID hội thoại Zalo.
- Bổ sung capture toàn bộ hai chiều, đối soát lịch sử và media theo kế hoạch.
- Thử tài khoản phụ: mất mạng, đóng browser, đọc trước trên điện thoại, gửi dồn, trùng tên nhóm, tiếp quản khi đang trả lời.
- Xác minh ERP backend/protocol rồi thử tạo đơn trên ERP staging.
- Chỉ mở gửi thật từng nhóm sau khi các điều kiện trên đạt.

## Bằng chứng tin nhắn và ảnh (thử nhóm Gia đình vintuan)

Mô đun Windows `zalo_desktop.evidence` xuất PNG từ các ID tin nguồn được chọn rõ ràng. Nó đọc Hub ở chế độ chỉ đọc, kiểm tra hash ảnh gốc trên NAS, giữ nguyên chữ/người gửi/thời gian, và ghi nhãn “Bản tổng hợp tin nhắn”. Chú thích gửi cùng ảnh được đọc từ `message.title`; ảnh và chữ gửi riêng vẫn có ID riêng, không tự ghép chỉ vì gửi gần nhau.

Chạy tại thư mục runtime `C:\Users\Admin\AppData\Local\PhucThanh\ZaloDesktopReader\code`:

```powershell
.\.venv\Scripts\python.exe -X utf8 -m zalo_desktop.evidence --order DH-2610-197 --message-ids 8368215292933 --local-output C:\Users\Admin\Documents\Codex\evidence
```

PNG và `source.json` lưu tại `\\192.168.1.203\n8n_upload\Gia đình vintuan\orders\{mã đơn}\evidence-{hash}\`. Truyền nhiều ID sau `--message-ids` để tổng hợp các tin riêng đã được xác nhận thuộc cùng đơn. Đầu vào giống nhau cho cùng bộ file; file hiện có bị thay đổi sẽ bị từ chối ghi đè.

Mẫu DH-2610-197 đã tải **một lần** vào Ảnh khách đặt bằng phiên ERP người dùng đăng nhập. Không tải lại mẫu này. CLI chỉ tạo hồ sơ PNG/NAS, không tự đăng nhập ERP hay tải ảnh lên, không tạo đơn, không gửi Zalo. Trong phép thử CLI lịch sử này, tự động chọn tin và đẩy ERP chưa bật (luồng intake production hiện đã tự động); người vận hành chọn đúng tin và dùng mục tải ảnh có sẵn trong ERP. Không chạy gói sửa ERP đã chuẩn bị trước đây: người dùng đã yêu cầu giữ nguyên ERP NAS.
# Lên đơn theo cấu hình nhóm (2026-10-13)

Nguồn quy tắc: `U:\phucthanh_support\config.json`, được đọc qua đường UNC tương ứng trên NAS.
Sửa danh sách nhân viên, nhóm bỏ qua hoặc `zalo_contact_rules` trong file đó; bộ đọc đồng bộ mỗi 30 giây.
`auto_order` và `receive_messages` độc lập. Nhóm tắt trả lời vẫn được lên đơn nếu không tắt auto_order.
Chỉ tin khách mới sau mốc bật được xử lý; không quét lịch sử. AI trả lời vẫn giữ phạm vi thử riêng.

Đơn rõ mã sản phẩm/số lượng -> Gemini kiểm tra -> PNG bằng chứng lưu NAS -> API ERP tạo trạng thái
**Lên mẫu**, đính kèm **Ảnh khách đặt**. ERP tính giá. Nhóm chưa khớp khách, nội dung thiếu/mâu thuẫn,
sửa đơn cũ, ảnh/file không đọc được hoặc PNG nhiều trang sẽ có ghi chú riêng trong Chatwoot để nhân viên xử lý.
Ảnh có caption và ảnh rồi nhắn chữ được ghép cùng người gửi trong 3 phút, chờ yên 45 giây trước phân tích.
Sau khi gửi ERP mà mất xác nhận, phải đối chiếu thủ công; không gửi lại tự động.

API ERP hiện tại yêu cầu nhóm **Tên khách - phần còn lại**. Nhóm **Gia đình vintuan** chưa đáp ứng
quy tắc này, nên chưa tự tạo bằng API; đơn thử DH-2610-197 đã có được giữ nguyên. Không sửa ERP.
Nhật ký ở Hub `/admin/intake_runs` (cần admin token), trạng thái cấu hình ở `/admin/status`.
Windows có thể dừng tự lên đơn bằng `zalo_default_auto_order: false` (các rule cụ thể vẫn ưu tiên),
hoặc tắt toàn bộ ở Hub bằng `ERP_WRITE_ENABLED=false` rồi chỉ khởi động lại Hub.
