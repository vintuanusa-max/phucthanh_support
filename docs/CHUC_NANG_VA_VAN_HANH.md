# Chức năng và vận hành — hiện hành 14/10/2026

**Tự tạo đơn ERP trạng thái Lên mẫu khi đủ điều kiện. Chỉ phản hồi AI cho khách nằm trong ghi chú private Chatwoot.**

agentic.auto_order=true, public_replies=false, internal_only=true trên cả hai kênh. Agent tạo đề xuất đã kiểm chứng, chuyển vào luồng kiểm tra nguồn/số lượng/khách/bằng chứng trước khi ghi ERP. Không tạo lại đề xuất cũ khi bật cấu hình. Quy tắc không tự lên đơn của từng nhóm vẫn được giữ.

Để kiểm tra AI, mở hội thoại Chatwoot, xem “AI — DỰ KIẾN TRẢ LỜI” và ghi chú kết quả lên đơn. Ghi chú “đề xuất/chưa ghi ERP” là trạng thái tại thời điểm đề xuất; chỉ ghi chú có mã đơn ERP mới xác nhận đã tạo. Không tự gửi câu trả lời ra Zalo/WhatsApp. Luồng thông báo duyệt in File In vẫn hoạt động riêng như trước.

inspect_material tìm tối đa 20 báo cáo nhân viên trong 30 ngày/1.000 tin cùng nhóm. Giữ người báo, thời điểm và nguyên văn; không tự tính tồn hiện tại. ID/tên nhân viên phải cấu hình đúng. GET /agentic/status yêu cầu Bearer quản trị, hiển thị lượt chạy/đề xuất; kiểm tra intake_runs để biết trạng thái bằng chứng và ghi ERP thực tế.

## 1. Vai trò từng hệ thống

| Thành phần | Vai trò |
|---|---|
| Zalo/WhatsApp Desktop trên Windows | Phiên đăng nhập cá nhân và nguồn tin nhắn; cần đồng bộ được tin về máy |
| Bộ đọc Windows | Nhận tin theo nhóm được phép, lưu trạng thái, chuyển tới Hub |
| Hub | Điều phối nhập tin, Gemini, lưu bằng chứng, đối chiếu khách, tạo đơn và gửi thông báo |
| Chatwoot | Xem hội thoại tập trung, tiếp nhận việc cần nhân viên, trả lời qua đầu nối được hỗ trợ |
| Gemini | Phân tích chữ/ảnh theo từng luồng hiện có; chưa quản lý toàn bộ vòng đời công việc |
| NAS | Lưu ảnh/file gốc, file tải từ link và bằng chứng PNG |
| ERP | Đơn hàng thật, trạng thái sản xuất và dữ liệu khách hàng |

## 2. Chức năng hiện tại

| Chức năng | Trạng thái và giới hạn |
|---|---|
| Nhận tin nhóm Zalo vào Chatwoot | Đã chạy; gồm tag nhân viên, caption ảnh và một số trường hợp ảnh trích dẫn đã đối chiếu ID |
| Nhận tin WhatsApp | Đã chạy, đã thử tin chữ/ảnh; chưa có kiểm chứng toàn bộ các kiểu tin/đơn thực tế |
| Lưu ảnh, file và link | Đã có; link Google Drive có quyền tải được lấy tại thời điểm nhận, gồm thư mục con; không theo dõi file thêm về sau |
| Xem ảnh trong Chatwoot | Có luồng ảnh xem trước khi đọc được; bản gốc lưu NAS. Định dạng/file không đọc được vẫn cần kiểm tra nguồn |
| Ánh xạ nhóm với khách ERP | Dùng account + group ID và customer ID; đổi tên nhóm không đổi khách đã liên kết |
| Nhóm chưa xác định khách | Có ánh xạ KHACH LE theo yêu cầu trước; phải kiểm tra trước khi chuyển khách |
| Gom ảnh và tin chữ để lên đơn | Có thời gian gom; số lượng khách sửa sau được ưu tiên khi xác định cùng yêu cầu |
| Đọc số lượng trong ảnh sau 30 phút | Đã triển khai: thử Gemini một lần trước khi chuyển nhân viên; chưa chứng minh xử lý đúng mọi ngữ cảnh giao vải/ảnh tham khảo |
| Tạo đơn ERP | Có, qua API hiện có, đơn thật ban đầu Lên mẫu; thiếu mã hàng có thể để Chờ mã. Không đoán giá/mã hàng |
| Bằng chứng đặt hàng | Tổng hợp tin nguồn và ảnh thành PNG, lưu NAS, gắn ảnh khách đặt trong ERP; là bản tổng hợp, không phải ảnh chụp cửa sổ Zalo |
| Duyệt in tới hai nhóm File In | Có gửi Zalo và WhatsApp; cần phiên Desktop và bộ gửi sẵn sàng |
| Thay đổi sau duyệt | Đã siết lại: cần ý định sửa và liên hệ rõ với hồ sơ cũ. Ảnh/file/số lượng mới đơn lẻ không tự là thay đổi |
| Phiếu lệnh CANAVI | Có quy tắc riêng theo group ID + sender ID; nhận “lệnh/lệnh in”, Gemini xác định tiêu đề phiếu, sao chép vào DON HANG |
| Chuyển Pending sang Open | Có kiểm tra định kỳ: chưa bật AI trả lời, quyền xử lý thuộc người, hoặc AI quá 5 phút chưa trả lời theo kiểm tra hiện tại |
| Agent trả lời công khai mọi nhóm | Tắt cho tất cả nhóm; phản hồi AI chỉ ghi chú private, lên đơn tự động độc lập |
| Hiểu giao thêm vải | Agent tham khảo báo cáo nhân viên cùng nhóm; bổ sung vải không tự là đơn mới |
| Tự liên kết và quản lý vòng đời đơn | Chưa đầy đủ; có tra tiến độ ERP theo đúng khách, chưa tự sửa/hủy đơn cũ |
| Tự chỉnh file thiết kế, duyệt phiên bản | Chưa triển khai |

Giới hạn quan trọng: bộ giám sát Pending hiện kiểm tra lần lượt hội thoại; 5 phút là ngưỡng xét, còn có độ trễ quét. Một tin trả lời công khai không đồng nghĩa công việc đã hoàn tất. Bộ điều phối mới phải theo dõi kết quả công việc thực tế.

## 3. Quy tắc đang áp dụng

- Chỉ nhóm được phép; không thu thập tin riêng hay lưu file tin riêng.
- Các nhóm nội bộ bị loại gồm File In - Giấy In - Màng Pet, IN PHÚC THANH - GỬI FILE IN + VẢI IN MẪU, Cty In Phúc Thanh, Gia đình vintuan. Nhóm nhận thông báo không được quay lại kích hoạt tạo đơn.
- Tên thư mục mới lấy tiền tố trước dấu gạch ngang, bỏ dấu và viết hoa; ví dụ CANAVI, CANAVI HCM2, A THUC. Liên kết được giữ theo ID; không di chuyển dữ liệu lịch sử chỉ vì đổi tên.
- W: tương ứng \\192.168.1.203\n8n_upload. File gốc được giữ; DON HANG dùng cho quy tắc phiếu lệnh, orders dùng cho bằng chứng tổng hợp.
- Phiên tài khoản được gắn cố định; đổi tài khoản Desktop cần kiểm tra/liên kết lại, không tự chuyển sang tài khoản khác.
- Không tự phát lại toàn bộ lịch sử khi sửa lỗi. Tạo đơn/gửi tin dùng dấu nguồn và trạng thái chống trùng; kết quả không chắc chắn phải đối chiếu trước khi thử lại.
- Không dùng số trên tên file, ngày tháng, kích thước hoặc số vị trí in làm số lượng đặt hàng.
- Chuyển Open không có nghĩa đơn đã tạo. Nhân viên cần đọc ghi chú kết quả.

## 4. Khởi động và xử lý sự cố

1. Đăng nhập tài khoản Admin trên Windows: Docker Desktop, bộ đọc Zalo và WhatsApp đã có mục tự chạy.
2. Mở Zalo/WhatsApp, kiểm tra đúng tài khoản và tin mới đã đồng bộ vào ứng dụng.
3. Đợi Docker sẵn sàng; vào http://localhost:3000. Chọn trạng thái All để xem cả Pending/Open/Resolved.
4. Kiểm tra truy cập NAS. NAS mất kết nối có thể khiến lưu file/bằng chứng chưa hoàn tất.
5. Nếu thiếu tin: đối chiếu nhóm + thời gian + người gửi, kiểm tra Desktop trước rồi trạng thái bộ đọc và Hub. Không xóa checkpoint hoặc database để “chạy lại”.
6. Nếu có cảnh báo tạo đơn không chắc chắn: tìm mã yêu cầu/đơn trên ERP trước khi tạo lại.

WhatsApp gửi tự động dùng cổng điều khiển chỉ trên 127.0.0.1 đã được người dùng cho phép. Không mở cổng này ra LAN. Tự khởi động hiện là khi đăng nhập Windows, không phải dịch vụ chạy trước màn hình đăng nhập.

## 5. Mã nguồn và dữ liệu ở đâu

| Đường dẫn | Nội dung |
|---|---|
| U:\phucthanh_support | Repo tổng và config.json vận hành riêng |
| U:\phucthanh_support\integrations\agent-hub | Bản mã tích hợp quản lý bằng Git |
| U:\phucthanh_support\docs | Tài liệu chức năng/kế hoạch và báo cáo ánh xạ |
| U:\chatwoot\.worktrees\phucthanh\phucthanh | Nguồn triển khai Hub/Compose |
| %LOCALAPPDATA%\PhucThanh\ZaloDesktopReader | Bộ đọc/gửi Zalo chạy trên Windows, trạng thái riêng |
| %LOCALAPPDATA%\PhucThanh\WhatsAppDesktopReader | Bộ đọc/gửi WhatsApp chạy trên Windows, trạng thái riêng |
| W:\ | Kho file NAS |

U: tương ứng \\192.168.1.203\docker. Sửa bản Git không tự động đổi runtime. Phải kiểm thử, triển khai đúng nơi và xác nhận phiên bản đang chạy. Không đưa .env, khóa phiên, cookie, database, ảnh khách hay config bí mật lên GitHub.



## Cập nhật 14/10: in bù
Đã triển khai quy tắc in bù và đối chiếu cùng ngày. Xem DOI_CHIEU_DON_VA_IN_BU_20261014.md và checklist để biết phạm vi tự động, biên nhận thật và phần chờ nhân viên.


## Xác nhận sau hỏi giá — cập nhật 14/10/2026
- [x] Lời OK/chốt/đặt/làm giúp của cùng khách lấy lại cụm review chưa gửi ERP trong cùng nhóm, cùng ngày, tối đa 30 phút và 12 tin nguồn.
- [x] Chờ yên 120 giây để gom bổ sung. Gemini và bước kiểm chứng độc lập đọc cả cụm; OK chỉ mở bước xem xét, không tự đủ điều kiện tạo đơn.
- [x] Hỏi giá đơn thuần hoặc phủ định không mở lại review; lượt created/uncertain hoặc có request_id/submitted_payload không được phục hồi theo cơ chế này.
- [x] Mẫu khác, số lượng mâu thuẫn hoặc thiếu dữ liệu vẫn chuyển nhân viên; không lấy số lượng của mẫu khác.
- [x] Đề xuất hợp lệ tiếp tục lưu bằng chứng NAS rồi tạo ERP Lên mẫu; phản hồi private Chatwoot.
- [x] 42 kiểm thử hồi quy + 1 kiểm thử nối hỏi giá/xác nhận tới đúng một ERP write giả lập đạt.
- [ ] Kiểm chứng lượt khách thật tiếp theo không cần phục hồi thủ công. Không phát lại đơn Chú Dũng đã tạo.


## 15/10/2026 — 5 tình huống và báo giá
- [x] Công cụ tra bảng giá Excel snapshot có nguồn ô/hash; tính giá độc lập Gemini.
- [x] PET 1000×ngang×cao/49, một chiều ≤29cm; laser chữ nhật 2×(dài+rộng), theo xác nhận chủ.
- [x] Hỏi thiếu lượng/kích thước và báo giá chỉ private; ngoài phạm vi không soạn trả lời khách.
- [x] Nối lượng/kích thước bổ sung vào câu hỏi đang chờ, cùng khách/nhóm/ngày, chưa gửi ERP.
- [x] Duyệt in tiếp tục chuyển nhóm sản xuất; sửa thiết kế/địa chỉ chuyển nhân viên.
- [ ] Nhân viên xác nhận khoảng giá mơ hồ và giá riêng CANAVI.
- [ ] Kiểm chứng ca báo giá thật tiếp theo trước khi cho phép trả lời nhóm khách.
Chi tiết: NAM_TINH_HUONG_VA_BAO_GIA_20261015.md.
