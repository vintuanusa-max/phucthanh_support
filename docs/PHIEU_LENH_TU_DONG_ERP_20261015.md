# Phiếu lệnh sản xuất → ERP (15/10/2026)

## Quy tắc chủ xưởng đã xác nhận
- Áp dụng hai nhóm CANAVI theo ID nhóm và ID người gửi đang cấu hình.
- Ảnh có tiêu đề PHIẾU LỆNH SẢN XUẤT sau tin “lệnh/lệnh in” vẫn lưu NAS/DON HANG.
- Mỗi ảnh phiếu đọc độc lập, không chờ 30 phút và không gom nhiều phiếu thành một đơn.
- Mã mẫu đọc đúng ô Mã Sản phẩm. Không rõ hoặc thiếu: truyền ten_don_hang=None để ERP tự tạo tên Tháng-Số thứ tự theo bộ đếm hiện có (ví dụ 10-09). Tuyệt đối không đặt tên CHỜ MÃ MẪU.
- Số lượng bắt buộc nguyên dương. “3 (gửi lên vp 2c)” lấy 3. Không rõ số lượng thì Open cho nhân viên.
- Ngày giao lấy đúng ô Ngày giao hàng; chuyển DD/MM/YYYY sang ISO. Ngày có chữ nhưng không đọc được đầy đủ thì kiểm tra thủ công.
- Mã mẫu khác mã hàng ERP. Chuyển nhiệt/CN → TUI; PET/in màng → PETA4 hoặc khổ rõ trên phiếu (PETA3/PETA5/PET7X7...). Không xác định loại in → Chờ mã hàng; vẫn tạo Lên mẫu. Nhiều loại/khổ hoặc chưa xác định được mã hàng: vẫn tạo Lên mẫu với loai_san_pham_id=None (Chờ mã), giá 0; giữ nguyên loại in trong yêu cầu để nhân viên bổ sung.
- Chưa có giá: giữ mã hàng, giá 0 và ghi CHỜ GIÁ cho nhân viên. Không tự đặt giá.
- Lưu ảnh phiếu vào ảnh khách đặt ERP; nguồn NAS và tin gốc có trong ghi chú.
- Phản hồi AI chỉ ghi chú nội bộ Chatwoot.

## Chống trùng và lỗi
- request_id theo phiếu ổn định, receipt lưu cùng giao dịch ERP.
- Khách + ảnh giống nhau hoặc mã mẫu giống nhau: chỉ đối chiếu đơn cùng ngày Việt Nam. Phiếu thiếu tên không so trùng bằng tên rỗng; dùng nguồn/ảnh và bộ đếm tên của ERP.
- Giữ trạng thái uncertain khi mất phản hồi; không tự gửi lại.
- Nguồn đã gửi qua luồng lên đơn cũ phải đối chiếu, không tự phát lại.
- Bộ gửi này khóa theo khách khi tạo; không bảo đảm khóa đồng thời với chương trình cũ máy .88 nếu chương trình đó được sửa và tự tạo đơn qua API khác.

## Tệp và API
- Hub: hub/slip_orders.py, clients.py, engine.py, order_intake.py.
- ERP: backend_v2/slip_intake.py; đăng ký trong routers/zalo_router.py.
- GET /api/v1/integrations/zalo/production-slip/capabilities.
- POST /api/v1/integrations/zalo/production-slip/orders. Cả hai dùng X-Zalo-Token hiện có.
- Không thêm bảng ERP; dùng zalo_intake và zalo_order_source hiện có.

## Checklist triển khai
- [x] Cài quy tắc thiếu mã vẫn lên Lên mẫu.
- [x] Kiểm thử parser, mã hàng, receipt, thiếu mã/số lượng, ảnh, quyền API, chống phát lại và giữ mã hàng khi thiếu giá bằng dữ liệu giả.
- [x] 71 kiểm thử Hub/agent/phiếu đạt; thêm 4 kiểm thử quyền API, giữ nguồn, restart, không gộp placeholder đạt.
- [x] API đã đặt trên NAS, có bản sao lưu trong data/releases/production-slip-1792039991.
- [x] ERP đã khởi động lại; API capabilities v2 xác nhận auto_order_name và waiting_product_code.
- [x] Cả 5 phiếu CANAVI đã có receipt ERP: DH-2610-228, 229, 230, 231, 232. Hai phiếu bị chặn trước đó được xử lý lại đúng nguồn chưa từng gửi; không phát lại ba phiếu đã tạo.

Cấu hình: production_slips.auto_order, order_enabled_after, order_recovery_ids. Không quét lại tất cả phiếu lịch sử. Việc triển khai Hub/kiểm chứng thực tế được ghi tiếp dưới đây.


## Hiệu chỉnh theo chủ xưởng (cùng ngày)
- CHỜ MÃ chỉ áp dụng MÃ HÀNG ERP, không dùng làm tên đơn.
- Gemini đọc hai lượt độc lập, không cho lượt kiểm chứng nhìn kết quả OCR trước. Mã mẫu không trùng nhau → tên tự động; số lượng/ngày không trùng nhau → nhân viên kiểm tra; mã hàng không trùng nhau → Chờ mã hàng.
- Đơn DH-2610-228 được đối chiếu ảnh và sửa tên/ghi chú dòng thành TB2VB-ANI3.10 mẫu qua giao diện ERP; không tạo lại đơn. Receipt Hub giữ phản hồi ban đầu làm lịch sử, không đại diện tên hiện tại sau chỉnh sửa.
- 34 kiểm thử phiếu/API bằng dữ liệu giả đạt sau hiệu chỉnh. Kiểm chứng thật: 5 receipt tạo đơn, ảnh gắn trong ERP; đơn 232 sử dụng tên mặc định và mã hàng chờ bổ sung.
- Bản v1 có cách hiểu sai CHỜ MÃ MẪU đã được thay bằng v2. Backup v2: data/releases/production-slip-1792040870.


Kiểm chứng giao diện ERP: DH-2610-232 có tên **10-09**, mã hàng **Chờ mã**, trạng thái **Lên mẫu**, ngày giao 19/10/2026 và 1 ảnh. DH-2610-228 đã lưu đúng tên **TB2VB-ANI3.10 mẫu** và ghi chú dòng tương ứng.

Quy tắc đã được chủ xưởng xác nhận ngày 15/10/2026: bỏ mặc định loại in khác → PET7X7. Không xác định mã hàng → loai_san_pham_id=None (Chờ mã), vẫn tạo đơn Lên mẫu ngay khi đủ số lượng và nguồn hợp lệ. PET 7×7 xác định rõ vẫn dùng PET7X7. Tên đơn không đổi theo quy tắc này.
