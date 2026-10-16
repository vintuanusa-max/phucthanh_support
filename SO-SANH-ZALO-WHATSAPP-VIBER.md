# So sánh công nghệ tích hợp Zalo, WhatsApp và Viber Desktop

Cập nhật: 16/10/2026. Phạm vi: mã tích hợp Phúc Thanh đã triển khai trên Windows; không phải mô tả API chính thức của các hãng. Tài liệu đối chiếu mã nguồn, không phải một lần kiểm thử vận hành mới.

## Bảng so sánh

| Hạng mục | Zalo Desktop | WhatsApp Desktop | Viber Desktop |
|---|---|---|---|
| Nguyên tắc | Dùng tài khoản Desktop đã đăng nhập | Dùng tài khoản Desktop đã đăng nhập | Dùng tài khoản Desktop đã đăng nhập |
| Kiến trúc ứng dụng được tích hợp | Electron / Node.js / renderer JavaScript | WebView2 chứa WhatsApp Web, kèm kho dữ liệu Windows | Ứng dụng native C++ / Qt6 |
| Nguồn đọc tin | CSDL Message/*.db và WAL; Core/Index.db cho tên nhóm | IndexedDB/LevelDB trong EBWebView cho nhóm, liên hệ, metadata; CSDL cục bộ cho nội dung chữ | CSDL SQLite SEE cục bộ và WAL |
| Kỹ thuật đọc | Đọc snapshot ổn định; xác thực, giải mã trang SQLCipher v4 rồi xử lý SQLite trong RAM | Sao chép cache ổn định; ccl_chromium_reader giải mã cấu trúc IndexedDB; kết hợp SQLite giải mã trong RAM | Đọc bản sao kho mã hóa bằng Qt6Core/Qt6Sql đi kèm Viber |
| Vật liệu giải mã | Tìm trong RAM đúng tiến trình Zalo bằng quyền đọc bộ nhớ Windows; không ghi khóa ra file | Windows NCrypt với phạm vi LOCAL=user; bộ giải mã trang AES-OFB cho kho native | Tìm khóa trong RAM đúng tiến trình Viber; giữ khóa trong RAM và dùng trên bản sao |
| Đọc ảnh/file | Metadata tin + cache/tải tài nguyên được hỗ trợ; có xử lý caption, ảnh trích dẫn, file và link tải | Metadata media từ cache; tải dữ liệu, kiểm tra hash/HMAC, HKDF và AES-CBC; hỗ trợ ảnh/document trong bộ giải mã | Đã kiểm chứng chữ và ảnh từ kho/cache Desktop; file khác và ảnh trích dẫn chưa được xác nhận đầy đủ |
| Cách gửi | Bật tạm Node Inspector của đúng tiến trình; gọi JavaScript trong Electron renderer để dùng hàm gửi nội bộ | CDP qua WebView2; gọi module WAWeb nội bộ trong chính phiên đăng nhập | Frida gắn tạm vào tiến trình; gọi hàm native nội bộ trên đúng luồng Qt |
| Cổng phục vụ gửi | Inspector 127.0.0.1:9229, mở tạm và đóng sau lượt; có watchdog | CDP 127.0.0.1:54329; cần bật cùng WhatsApp để gửi tự động | Không dùng cổng CDP/Inspector thường trực; attach ngắn theo lượt gửi |
| Gửi đã kiểm chứng | Tin chữ nhân viên từ Chatwoot và ảnh tổng hợp chốt in | Ảnh PNG + caption tổng hợp chốt in vào nhóm File In - Giấy In - Màng Pet | Tin chữ public do nhân viên nhập Chatwoot vào nhóm CDG |
| Giới hạn đường gửi | Phụ thuộc phiên bản Electron và renderer đã nhận diện | Đường send_print hiện khóa vào ID nhóm đích; không coi đây là đầu gửi mọi loại tin tới mọi nhóm | Khóa theo hash bản Viber và nhóm viber:g1; chưa xác nhận gửi ảnh/file |
| Điều khiển giao diện | Không click/gõ cửa sổ để gửi | Không mở Chrome riêng, không click/gõ để gửi | Không click/gõ cửa sổ để gửi |
| Định danh nhóm | ID nhóm g…; tên là nhãn hiển thị | JID nhóm …@g.us; tên là nhãn hiển thị | CDG có ChatID 1, thread viber:g1 |
| Chống nhập trùng | ID tin nguồn, outbox và trạng thái bền vững | ID tin nguồn, outbox và trạng thái bền vững | ID sự kiện nguồn, outbox và trạng thái bền vững |
| Chống gửi trùng | Nhật ký SQLite, kiểm tra kết quả; trạng thái không rõ không gửi lại mù | Hàng đợi tổng hợp và trạng thái từng lần gửi; lỗi CDP không đồng nghĩa chưa gửi | Sổ SQLite commit trước gọi native; đối chiếu đúng một sự kiện outgoing mới; không tự gửi lại nếu chưa rõ |
| Phạm vi đọc | Nhóm được cấu hình; loại trừ nhóm nội bộ và tin riêng theo chính sách | Nhóm được cấu hình; không truy vấn nội dung chat riêng | Riêng CDG-Chị Dung Nón 3D |
| Tích hợp ERP | Luồng chung tạo Lên mẫu, ánh xạ ID khách, bằng chứng và chống trùng | Luồng chung tạo Lên mẫu, ánh xạ ID khách, bằng chứng và chống trùng | Đã bật CDG → CHI DUNG CDG; chưa xác nhận đơn khách thật đầu tiên sau kích hoạt trong lần ghi nhận trước |
| AI phản hồi khách | Ghi chú nội bộ Chatwoot | Ghi chú nội bộ Chatwoot | Ghi chú nội bộ Chatwoot; public staff reply là đường riêng |
| Rủi ro bảo trì | Đổi schema/mã hóa hoặc bundle renderer có thể cần sửa adapter | Đổi cache, WebView2 hoặc module WAWeb có thể cần sửa adapter | Nhạy nhất với thay đổi binary/ABI; hash không đúng phải dừng gửi và kiểm chứng lại |

## Luồng dữ liệu chung

1. Desktop đồng bộ tin về máy Windows.
2. Reader đọc dữ liệu cục bộ, kiểm tra tài khoản/nhóm/người gửi và mốc tin mới.
3. Tin được chuyển qua outbox tới Hub và Chatwoot; ảnh/file được hỗ trợ lưu NAS, ảnh có preview khi phù hợp.
4. Gemini phân tích cụm tin và ảnh; phản hồi AI chỉ thành ghi chú nội bộ Chatwoot.
5. Khi đủ thông tin đặt hàng, Hub tạo bằng chứng và gọi API ERP tạo đơn Lên mẫu theo ánh xạ khách; kiểm tra trùng trong ngày và request_id.
6. Nhân viên trả lời public trên Chatwoot được chuyển qua đầu gửi tương ứng nếu kênh/loại tin đã hỗ trợ. Luồng tổng hợp chốt in gửi nhóm nội bộ là tác vụ riêng, không phải bật AI trả lời công khai cho khách.

Desktop chưa đồng bộ được tin thì reader không thể đọc tin chỉ mới có trên điện thoại. Các adapter không phải dịch vụ cloud độc lập với ứng dụng Desktop.

## Các điểm cần hiểu đúng

- Đây là đầu nối tùy chỉnh vào dữ liệu và hàm nội bộ của ứng dụng, không phải API chính thức Zalo OA, WhatsApp Business Cloud hay Viber Bot.
- Không có một DLL chung đọc/gửi được cả ba nền tảng. Viber dùng thư viện Qt để đọc, nhưng gửi phải xử lý đối tượng native; Zalo/WhatsApp gửi qua runtime JavaScript.
- Đường đọc và đường gửi tách riêng. Quy tắc không ghi vào CSDL nguồn áp dụng cho reader; sender chủ động gọi hàm ứng dụng để gửi tin, vì vậy không thể mô tả toàn hệ thống là chỉ đọc.
- Đã ghi nhận tin trong nguồn Desktop hoặc trạng thái submitted chưa đồng nghĩa người nhận đã đọc. WhatsApp send_print có quan sát ack; mức xác nhận giữa các kênh khác nhau.
- Đổi tài khoản không được coi là tự tương thích: cần xác minh profile, account ID, nhóm được phép và ánh xạ khách ERP. Không xóa state để khởi động lại vì sẽ làm mất dấu chống trùng.
- Khóa/cookie/token không được đưa vào tài liệu hoặc Git. Cổng điều khiển chỉ giới hạn loopback; đây vẫn là quyền điều khiển phiên cục bộ.
- Viber từng lỗi do nhận nhầm kiểu dữ liệu Qt; bản hiện tại dùng đúng MessageInfo/Quote và quản lý vòng đời đối tượng. Khi ứng dụng nâng cấp, không bỏ kiểm tra hash để cố gửi.

## Mã nguồn tham chiếu trên máy

Thư mục làm việc: `C:\Users\Admin\Documents\Codex\2026-10-12\hi-n-m-y-t-nh\work\agent-hub`.

| Phần | File/mô-đun |
|---|---|
| Zalo đọc, giải mã, tên nhóm | zalo_desktop/reader.py, codec.py, memory.py, groups.py |
| Zalo gửi | zalo_desktop/sender.py, desktop_transport.cjs, renderer_sender.cjs; desktop_photo_transport.cjs và renderer_photo.cjs cho ảnh |
| WhatsApp đọc | whatsapp_desktop/source.py, native.py, reader.py |
| WhatsApp media | whatsapp_desktop/media.py |
| WhatsApp gửi chốt in | whatsapp_desktop/cdp.mjs, send_print.mjs, print_sync.py |
| Viber đọc | viber_desktop/source.py, qt_readonly.py, reader.py |
| Viber gửi | viber_desktop/native_sender.py, native_sender.js, sender.py, send_ledger.py |
| Chính sách và ERP | hub/order_policy.py, order_intake.py, agent_loop.py; zalo_desktop/order_sync.py dùng chung |

Hub triển khai nằm tại `U:\chatwoot\.worktrees\phucthanh\phucthanh`. Reader/sender Windows có launcher và trạng thái riêng; việc sửa bản sao mã nguồn chưa tự chứng minh tiến trình đang chạy đã nạp bản sửa.

## Checklist bảo trì

- [ ] Sau khi cập nhật ứng dụng: kiểm tra tương thích bộ đọc và đầu gửi riêng biệt.
- [ ] Sau khi đổi tài khoản: xác minh profile và allowlist trước bật lại luồng ERP/gửi.
- [ ] Kiểm tra heartbeat reader, sender, Hub và quyền ghi NAS.
- [ ] Giữ nguyên outbox, sổ gửi và request_id khi restart.
- [ ] Đối chiếu lượt uncertain trước khi quyết định gửi lại.
- [ ] Chỉ tuyên bố hỗ trợ loại tin đã kiểm chứng; đặc biệt file/ảnh gửi Viber và trả lời WhatsApp tổng quát.

Tài liệu này ưu tiên mã nguồn và ghi nhận triển khai mới nhất; các README có ghi chú capture-only hoặc chưa bật gửi từ giai đoạn đầu chỉ là lịch sử.
