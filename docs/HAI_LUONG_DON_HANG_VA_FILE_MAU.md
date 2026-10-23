> Cập nhật tài liệu 23/10/2026: xem [Tổng quan hệ thống](../TONG_QUAN_HE_THONG.md) và checklist hiện hành được liên kết tại đó. Các mục bên dưới giữ làm lịch sử; ghi chú “chờ triển khai” cũ phải đối chiếu bản cập nhật hiện hành. Lượt này chỉ cập nhật tài liệu, không thay đổi dịch vụ hay dữ liệu ERP.

# Hai luồng nghiệp vụ — cập nhật 21/10/2026

Tài liệu này là hướng nghiệp vụ hiện hành, thay cách trình bày sáu phần kỹ thuật. Chống trùng, heartbeat, phiên bản và nhật ký vẫn chạy phía sau, không biến thành các bước người dùng phải làm.

## Luồng 1 — Đơn hàng ERP
1. Gom đúng cụm tin, ảnh, trích dẫn theo từng mẫu và người gửi.
2. Xác định khách đặt hàng; số lượng lấy từ tin nhắn hoặc chữ trên ảnh, đối chiếu lời đính chính sau đó. Không biến số đo, giá, giao vải hay nhắc lại thành đơn mới.
3. Đủ mẫu và số lượng: tự tạo Lên mẫu. Chưa xác định khách: KHACH LE; thiếu mã hàng: Chờ mã; thiếu tên: ERP tự đặt. Không chờ file thiết kế hoặc TIFF mới lên đơn.
4. Chống phát lại theo ID nguồn, đối chiếu đơn mới trong ngày; tìm đơn đặt thêm theo file/ghi chú trong 3 ngày gần nhất.
5. Tăng lượng khi ERP là len_mau, mau_co_san hoặc dang_chay_giay. Giảm lượng, hủy/xóa chỉ khi len_mau hoặc mau_co_san. Đọc trạng thái ngay trước ghi và khóa lại điều kiện trong giao dịch ERP. Không giảm lượng hoặc hủy/xóa từ Đang chạy giấy trở đi.
6. Khách in thêm khi đơn đã qua Đang chạy giấy: tạo đơn Lên mẫu riêng với đúng lượng thêm, lưu liên kết đơn cũ; không cộng vào đơn đã in. Trạng thái không rõ: ghi nội bộ kiểm tra.

Hiện công cụ tự động chỉ có nhánh cộng thêm; không có công cụ tự hủy/giảm đơn. Các yêu cầu hủy/giảm vẫn chuyển nhân viên, không coi tài liệu này là đã triển khai tự hủy.

## Luồng 2 — File mẫu
1. Nguồn gồm ảnh maket, tệp đính kèm, link Google Drive/OneDrive/Dropbox/file trực tiếp và các dịch vụ chia sẻ khác (ví dụ Canva).
2. Link tải được: lưu NAS, giữ ID tin nguồn, tên file và hash; đọc file đã tải cùng maket và tin khách. Không coi tên miền hoặc tên file là đủ để xác định artwork.
3. Link yêu cầu đăng nhập/quyền tải/hết hạn hoặc chỉ là trang xem: ghi nội bộ thiếu quyền/thiếu file. Không lưu trang HTML thành file thiết kế. Đầu nối Canva xuất thiết kế chưa được kiểm chứng; cần file export hoặc quyền tích hợp phù hợp.
4. Có file gốc: chọn artwork từng vị trí, đối chiếu kích thước maket/tin khách. Nhiều vị trí xuất riêng. Mâu thuẫn chưa được giải quyết thì ghi rõ.
5. Chỉ có maket: kiểm tra độ nét ở kích thước in, phối cảnh và khả năng tách artwork. Đủ chất lượng mới đề xuất mẫu. Không đủ thì soạn yêu cầu file gốc trong ghi chú nội bộ. Khách không có file: tạo yêu cầu vẽ lại để kiểm tra, chưa mặc định bộ vẽ lại tự động đã có.
6. PET: PNG alpha + TIFF spot_1, không trừ co; trắng không contract, phần màu contract 1 pixel. Giới hạn cao 6,5 cm chỉ áp dụng hồ sơ nón có căn cứ.
7. Chuyển nhiệt túi: JPG CMYK gốc và AI đủ artboard. Khổ vải cao <70 cm trừ ngang 2/cao 2,5; >=70 trừ ngang 2/cao 5. Khổ đã xác nhận sau co không trừ lần nữa. Túi liền hai mặt: sau xoay 180°, cữ maket +0,5 cm theo quy tắc đã duyệt. Vải mét không định vị.
8. Xuất xong: NAS + preview/ghi chú nội bộ Chatwoot, chờ chủ xưởng duyệt. Không gửi khách, không RIP; duyệt trên bảng theo dõi cũng không tự phát hành.

## Giao diện
`http://localhost:8095/workflow`: hai cột Luồng 1 · Đơn ERP và Luồng 2 · File mẫu. Cảnh báo kỹ thuật nằm trong mục thu gọn. Dùng token quản trị hiện có, chỉ giữ trong bộ nhớ trang, không lưu trình duyệt.

## Checklist có bằng chứng
- [x] Rút giao diện và tài liệu về hai luồng độc lập.
- [x] Giữ tự tạo Lên mẫu, KHACH LE/Chờ mã và chống trùng; 6 kiểm tra hồi quy gửi ERP giả lập đạt.
- [x] Nhánh in thêm kiểm tra trạng thái: qua Đang chạy giấy → đơn mới chỉ lượng thêm, có tham chiếu đơn cũ; thử bằng mock.
- [x] Khi API ERP chưa báo hỗ trợ khóa trạng thái, hub không tự sửa đơn cũ.
- [x] Viết và kiểm thử ma trận tăng/giảm/xóa/hủy trong giao dịch API ERP, trước khi cập nhật dòng hàng.
- [x] Chủ xưởng đã restart ERP; GET chỉ đọc ngày 21/10 xác nhận mutation_policy=quantity-states-v2 và đúng hai danh sách trạng thái. Không thử sửa đơn thật.
- [x] File PDF/AI tải thành công từ link hoặc đính kèm được nối vào hồ sơ mẫu; không tạo lại hồ sơ nếu run đã có.
- [x] Google Drive (kể cả cây thư mục hiện có), OneDrive, Dropbox và URL file HTTPS dùng bộ tải hiện có, kiểm tra quyền và giới hạn tải.
- [ ] Tích hợp xuất từ trang chia sẻ Canva; chưa coi link xem Canva là file tải trực tiếp.
- [ ] Luồng tự tách từ ảnh maket không có file gốc và tự vẽ lại cần triển khai/kiểm chứng riêng; hiện ghi yêu cầu nội bộ.
- [x] Giữ xuất file và phản hồi AI nội bộ, không RIP/gửi khách.

## Phần kỹ thuật phía sau
Đã chạy: API/bảng tổng hợp, heartbeat từ order-policy của bộ đọc và artwork-checks của worker, cảnh báo kẹt/khôi phục, nối phiên bản hồ sơ với nguồn chung và đúng sender ID, sổ phiên bản/hash và duyệt, tách quy tắc PET/JPG, thông báo lỗi có mã và hướng xử lý. Các ca mơ hồ vẫn giữ để kiểm tra; chưa khẳng định mọi ca thật đã tự xử lý đúng. File xuất thủ công ngoài hàng đợi không tự được nhập đủ vào sổ phiên bản. Giao diện duyệt đã qua API giả lập; kiểm tra thao tác browser tự động chưa hoàn thành (thiếu Chromium, lần thử Edge bị ngắt).

## Điều chỉnh theo chủ xưởng — 21/10/2026
| Thao tác | Lên mẫu | Mẫu có sẵn | Đang chạy giấy | Ra giấy/các bước sau |
|---|---|---|---|---|
| Tăng số lượng trên đơn cũ | Có | Có | Có | Không, tạo đơn in thêm riêng |
| Giảm số lượng | Có | Có | Không | Không |
| Hủy hoặc xóa mềm | Có | Có | Không | Không |

- [x] Bot và API cộng lượng dùng cùng ma trận mới, khóa đơn trước khi ghi.
- [x] API sửa từng dòng/nhiều dòng, xóa dòng, xóa mềm đơn và chuyển Hủy kiểm tra cùng quy tắc. Không nới quyền vai trò hay bỏ kiểm tra phiếu thu.
- [x] 32 trường hợp trạng thái/thao tác, giảm xen tăng, bỏ dòng, khóa bản ghi và 6 kiểm tra gửi ERP chống trùng đạt bằng dữ liệu giả.
- [x] Runtime ERP đã xác nhận policy quantity-states-v2; chạy lại 32 ca giả lập đạt, không sửa/xóa đơn thật. Xem BAO_CAO_KIEM_TRA_2026-10-21_TU_18H.md.



## 21/10/2026 — Tách điều kiện thiết kế khỏi nhận đơn
- [x] context_gate: thiếu product_details/design_confirmation/file/kích thước không chặn new_order đã xác định; thiếu số lượng/phân bổ, ý định chưa rõ, xung đột và sai nguồn vẫn chặn. Dùng danh sách rõ ràng, không bỏ qua mọi missing_fields.
- [x] collect_drive_order nhận cả yêu cầu chỉ có ảnh; nối toàn bộ nguồn vào hồ sơ mẫu, chống tạo hồ sơ/note trùng theo run. Không tự gửi khách/RIP.
- [x] Kiểm thử giả lập: thiết kế thiếu vẫn qua; số lượng/unknown/conflict/sai source không qua; hai ảnh cùng hồ sơ; gọi lại không tạo hồ sơ/note lần hai.
- [x] Deploy image two-flow-separation-20261021; source live và mirror đã sao lưu/cập nhật.
- [x] A THỨC 400c: giải phóng đúng run 57407ca6d349c9e90acb6dd463bd817c657e812beb22189842182d04d87a34d5 sau đối chiếu ERP/source, giữ request ID. Bộ đọc tự lưu bằng chứng và hub tự submit. GET xác nhận DH-2610-310 / 7894bdd1-9a71-497d-ac90-c92c5cbb6ce3, đúng khách A THỨC, 400, len_mau. Không replay run khác.
- [x] Đã xem hai ảnh: maket nón mặt trước và logo CẦN THƠ riêng. Hồ sơ 3c0d8c47afa0b249be4cec2d7f978150092a106056ecfce951ef472cd70f36e0 gồm cả ba tin nguồn. Notes #4033/#4034 private=true.
- [ ] File CẦN THƠ: đã xác nhận mặc định cao 6,5cm; còn tách artwork raster và xuất PNG/TIFF. Không còn chờ kích thước, không chặn ERP.

## 21/10/2026 — Kích thước mặc định từng vị trí nón
- [x] Khách không ghi kích thước: mạc/logo mặt trước cao 6,5cm; hông trái/phải ngang 7cm (mức tối đa mặc định), giữ tỷ lệ artwork thật sau trim.
- [x] Kích thước khách ghi hoặc tỷ lệ đã xác nhận được ưu tiên; không ép về mặc định. Vị trí chưa rõ/sau/vành hoặc túi không tự áp mặc định nón.
- [x] Planner đọc ảnh/maket cùng PDF/AI, dẫn nguồn xác định nón và vị trí; owner_hat_default ghi rõ đây là quy tắc chủ xưởng, không giả làm số đo khách.
- [x] Renderer áp kích thước và giữ tỷ lệ; kiểm thử front/label/left/right, khách ghi riêng, vị trí mơ hồ và túi đạt. Image hat-defaults-20261021 đã triển khai.
- [x] ERP độc lập; file chỉ nội bộ, chưa RIP/gửi khách. PET không trừ co; trắng không contract, màu contract 1px giữ quy tắc hiện có.
- Giới hạn: tuyến tự tách đối tượng đang dùng PDF/AI; trường hợp chỉ có ảnh raster vẫn cần bộ tách nền/artwork phù hợp, không coi thêm mặc định kích thước là đã hoàn thành tự tách mọi ảnh.


21/10/2026: Theo lựa chọn chủ xưởng, chỉ đóng/ẩn đúng 6 PET review (archived); giữ bản ghi chặn prepare/replay, backup DB before-archive-six-pet-20261021.sqlite3. Không xóa ERP, Chatwoot, NAS hay intake khác. PET pending=0 sau kiểm tra. Không lật gương; đơn/file mới tiếp tục hai luồng, file chỉ nội bộ chưa RIP/gửi khách.

22/10/2026: Đã nối nhánh ảnh raster riêng đủ rõ → PNG/TIFF, chi tiết và giới hạn tại U:\DESIGNER\pet\RASTER-WORKFLOW.md. Không tự tách mọi ảnh sản phẩm/nền phức tạp. Giữ sáu PET archived và không tạo lại đơn.

## 22/10/2026 — Phục hồi có xác nhận và thư mục DESIGNER
- [x] Bản CẦN THƠ v2: chủ xưởng yêu cầu trực tiếp, phục hồi bằng image_gen, giữ nguyên chữ và số; đối chiếu trực tiếp. Không gửi thêm Gemini sau khi auto-review chặn phép kiểm tra mạng.
- [x] File mới lưu {khách}/DESIGNER/{tên mẫu}/versions/{job_id}; nguồn ở sources khi phục hồi thủ công. Giữ phiên bản cũ.
- [x] raster_consent.py: bước cải thiện biên chỉ khi nhân viên hỏi file thiết kế rồi chính khách trong batch xác nhận không có/chỉ có vậy, trong30phút, không có khách khác chen giữa; không kích hoạt từ chất lượng thấp hoặc lời nhân viên.
- [x] Test người gửi/thứ tự/thời gian/khách khác/khách hẹn gửi file đạt. Luồng thông thường tách nền vẫn độc lập, không tự vẽ lại.
- Giới hạn: cổng tự động hiện cho phép làm sạch biên pixel rồi VLM kiểm tra; vẽ lại sinh ảnh giống lần phục hồi CẦN THƠ chưa có worker nền tự động. Không mô tả bước làm sạch biên như đã dựng lại vector/chữ. Trường hợp cần vẽ lại phức tạp vẫn cần duyệt riêng.
