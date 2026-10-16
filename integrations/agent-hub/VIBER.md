# Viber Desktop — trạng thái 15/10/2026

## Lên đơn CDG — đã kích hoạt ngày 15/10/2026
- [x] Xác minh khách ERP `CHI DUNG CDG`, ID `58ca8cd4-1183-4a01-88b1-2e8a81378e98` qua API thật.
- [x] Hub hỗ trợ policy Viber chỉ `viber:g1`, chỉ tin khách; yêu cầu ánh xạ ID trước tạo đơn. Reader đã có mã đồng bộ policy và bằng chứng PNG/NAS dùng chung luồng lên đơn.
- [x] API ERP đã sao lưu và đặt bản sửa: source=viber, bắt buộc CDG + tài khoản viber-personal-1 + customer_id; giữ nguyên quy trình Lên mẫu/idempotency/đối chiếu trùng. Chưa restart ERP.
- [x] 12 kiểm thử Viber/API guard và 46 kiểm thử luồng intake/agent đạt.
- [x] Chủ hệ thống đã restart ERP; API capability Viber được xác nhận trước kích hoạt. Ánh xạ CDG → CHI DUNG CDG, agent nội bộ và auto_order đã bật; reader đã reload.
- [x] Xác minh policy heartbeat, ánh xạ và agent scope chỉ viber:g1. Mốc tin mới: Unix 1792070386.6971679; không phát lại lịch sử/tin thử. AI internal_only=true, public_replies=false. Đơn hợp lệ đi qua luồng chung tạo Lên mẫu, kiểm tra trùng trong ngày và request_id bền vững.
- [ ] Xác minh đơn khách thật đầu tiên sau kích hoạt. Chưa tạo đơn thử ERP trong đợt này.

Các mục bên dưới ghi lại lịch sử triển khai; trạng thái kích hoạt tại mục đầu này được ưu tiên. Nhãn reader status `capture_only` là nhãn cũ, không phản ánh order_sync đã bật qua order_policy_file.

## Đang vận hành liên tục — cập nhật sau thử thành công
- [x] Đã chuyển sender từ `--one` sang chạy liên tục; status mới errors=[].
- [x] Startup người dùng Admin: `PhucThanh-ViberSender.vbs` gọi ẩn `%LOCALAPPDATA%/PhucThanh/ViberDesktopReader/Start-Sender.ps1` khi đăng nhập Windows.
- [x] Gọi launcher hai lần giữ nguyên các PID; khóa sender.lock và sổ chống trùng sender.sqlite3 hiện hữu không bị xóa/reset.
- [x] Chỉ public text nhân viên, đúng CDG/viber:g1, tin mới trong 5 phút; kết quả chưa rõ không tự gửi lại. AI Viber chưa bật, cấu hình internal_only=true/public_replies=false và guard chặn gửi AI.
- [ ] Chưa kiểm chứng bằng một lần khởi động lại Windows thật. Docker/Chatwoot và phiên Viber đã đăng nhập cần sẵn sàng để gửi; không tự đăng nhập tài khoản. Khi Viber đổi phiên bản, kiểm tra hash sẽ chặn gửi để tránh dùng địa chỉ hàm cũ.
Dừng có chủ ý: tạo `state/sender-stop.flag`; launcher tôn trọng cờ này. Các mục “chưa bật liên tục/startup” phía dưới là lịch sử trước lần triển khai này.

## Kết quả thử toàn tuyến
Người dùng đã nhập `test` trên Chatwoot. Adapter gửi một lần, đối chiếu nguồn thành `viber:552`, và báo Hub `submitted` thành công. Bộ đọc độc lập cũng nhập đúng event 552, outgoing, thread viber:g1, nội dung `test`; chỉ thấy một event khớp trong cửa sổ thử. Đây là xác nhận Viber Desktop ghi nhận tin đúng nhóm, không phải bằng chứng người nhận đã đọc. Bộ chờ --one đã kết thúc sau báo kết quả. Chưa bật worker liên tục/startup. AI vẫn internal-only, public replies bị chặn.

## Trạng thái mới nhất — chờ đúng một thử nghiệm toàn tuyến
Đầu gửi một lần đã chạy nền từ module `viber_desktop.sender --one`, cấu hình riêng `sender.local.json` trong runtime. Hub đã reload `delivery_enabled=true`, chỉ CDG/viber:g1, chỉ public text của nhân viên tạo sau mốc kích hoạt mới; inbox 3 đã nối AgentBot đang dùng. AI Viber vẫn chưa bật và bị chặn gửi công khai. Kiểm tra `--check` xác minh profile/nhóm bằng bản sao nguồn rồi dry-run đầu gửi đạt (`clean=true`, `context_verified=true`, `invoked=false`). Bộ chờ báo errors=[] và chỉ gắn chẩn đoán ngắn khi nhận tin. Chưa có tin thực tế qua đầu gửi; chưa cài startup sender hoặc bật chế độ gửi liên tục. Những ghi nhận delivery_enabled=false phía dưới là trạng thái nghiên cứu trước đó.

## Đã kiểm chứng
- [x] Đọc bản sao SQLite SEE bằng thư viện Qt đi kèm Viber, chỉ đọc; khóa phiên giữ trong RAM.
- [x] Phạm vi đúng nhóm CDG-Chị Dung Nón 3D, ChatID 1, tài khoản Viber hiện tại.
- [x] Tin chữ và ảnh thử vào Chatwoot inbox 3, hội thoại 60. Ảnh có preview.
- [x] Bản gốc ảnh lưu NAS n8n_upload/CDG/YYYY-MM/originals, kiểm tra SHA256.
- [x] Chỉ lấy tin từ mốc kích hoạt; outbox bền vững chống nhập trùng.
- [x] Bộ đọc chạy nền mỗi 15 giây, tự chạy khi người dùng Admin đăng nhập Windows.
- [x] Hội thoại chưa bật AI được chuyển Open qua pending guard.
- [x] Kiểm thử chuyển đổi caption, phân biệt nhân viên, bỏ tin hệ thống, giới hạn nhóm: 3 passed.

## Chưa hoàn tất — không coi là khả năng đã triển khai
- [x] Tự kiểm tra không cần tin mẫu: `verify_bundle_lifetime.py` đạt; `verify_synthetic_dispatch.py` xử lý và tháo sạch trên luồng Qt.
- [x] Tự tra CDG bằng hàm đọc cache ChatStorage có QReadLocker, ID 1/flags 4; bản sao hủy an toàn. Không còn cần tin gửi thủ công để lấy ngữ cảnh.
- [x] `native_sender.py/js`: mỗi lần một yêu cầu, tự lấy ngữ cảnh mới, tạo Quote/MessageInfo đúng loại, giải phóng trên luồng Qt; dry-run đạt, không phát tin.
- [x] `sender.py`: chỉ nhận public text nhân viên từ hàng đợi Hub, khóa một tiến trình, sổ gửi bền vững, đối chiếu duy nhất một EventID mới trong Viber; kết quả chưa rõ không gửi lại. Kết quả báo Hub được lưu để gửi lại thông báo mà không gửi lại tin. Tổng 10 kiểm thử đạt.
- [ ] Một lần thử toàn tuyến bằng tin nhân viên nhập ở Chatwoot, xác nhận nhận trong nhóm Viber. Chưa xác minh giao tin thực tế.
- [x] Mã cục bộ `send_ledger.py`: giữ dấu lần thử trước khi gọi gửi; không tự thử lại khi kết quả chưa rõ, kể cả sau restart. Ba kiểm thử ledger và bốn kiểm thử Viber đạt (7 passed). Chưa nối ledger vào transport sản xuất.
- [x] Chẩn đoán BAN SAO bắt đúng tin thủ công, sao chép/giải phóng 9 đối tượng Qt và tự tháo. Chưa chứng minh gửi tự động.
- [ ] Harness `../viber-research/bounded_sender.js`: đã sửa hai trường MessageInfo bị nhận nhầm thành QVariantMap. Phép thử riêng đối tượng rỗng đạt cả giải phóng chủ sở hữu cuối; cần chạy lại dry-run với ngữ cảnh CDG thực tế. Gửi thật vẫn chặn cứng, chưa triển khai startup.
- [ ] Gửi từ Chatwoot về phiên Viber Desktop: chưa có transport được kiểm chứng; delivery_enabled=false.
- [ ] AI phân tích/ghi chú nội bộ và tích hợp ERP cho Viber: chưa bật; không tạo đơn từ tin thử.
- [ ] File ngoài ảnh, trích dẫn ảnh, sửa/thu hồi, account switch và đổi tên nhóm: cần bổ sung kiểm chứng.
- [ ] Kiểm chứng tự chạy sau một lần Windows khởi động thực tế.

## Vận hành
### Kiểm tra đường gửi tiếp theo — 15/10/2026
- Đã mở lại Viber với quyền người dùng cho phép, cùng phiên đăng nhập; bộ đọc vẫn hoạt động.
- Có chuỗi cấu hình VIBER_REMOTE_WEBENGINE_DEBUG_PORT trong binary, nhưng lần thử không có listener HTTP/CDP ở 127.0.0.1:9229. Chưa tìm thấy transport gửi tin được kiểm chứng.
- Thêm guard riêng Viber: chỉ user nhân viên, public text, đúng allowlist, sau mốc kích hoạt và không quá 5 phút; chặn AI/ghi chú nội bộ kể cả hub live. Kiểm thử 4 passed.
- delivery_enabled vẫn false. Chưa triển khai sender, không tuyên bố tin đã gửi; chưa gửi tin thử nào.
- AI riêng Viber chưa kích hoạt, cấu hình internal_only=true/public_replies=false được lưu để giữ yêu cầu của chủ hệ thống.

Nguồn: viber_desktop/source.py, qt_readonly.py, reader.py.
Runtime: %LOCALAPPDATA%/PhucThanh/ViberDesktopReader; reader.local.json chứa token, không đưa lên Git.
Trạng thái: state/status.json. Dừng bằng tạo state/stop.flag; cần xóa cờ trước khi chạy lại.
Startup: %APPDATA%/Microsoft/Windows/Start Menu/Programs/Startup/PhucThanh-ViberReader.vbs.
Không sửa database Viber. Chỉ mở bản sao mã hóa kèm WAL. Không lưu khóa hoặc dump RAM.
Nếu đổi tên nhóm/tài khoản: dừng xác minh lại ánh xạ, không tự lấy tin nhóm khác.
Ảnh chưa tải vào thư mục Viber được thử lại; không ghi nhận lưu thành công khi chưa có file.
Phiên hiện tại chỉ hỗ trợ text type 1 và image type 2; loại khác bỏ qua, cần mở rộng có kiểm thử.
