# Checklist hiện hành — 23/10/2026
[x] = đã triển khai/có bằng chứng đã nêu; không có nghĩa mọi trường hợp đầu vào đã được kiểm chứng. [ ] = còn hạn chế hoặc cần kiểm chứng tiếp. Lần này cập nhật tài liệu, không thử ghi ERP/xuất file mới.

## Thu nhận và ánh xạ
- [x] Đọc Zalo/WhatsApp/Viber có checkpoint; watchdog và nhận đường dẫn phiên bản được triển khai theo tài liệu phục hồi.
- [x] Ánh xạ IDnhóm trong config.json, fallback KHACH LE; nhóm bỏ qua ưu tiên; không đổi đơn cũ.
- [x] Ảnh nhân viên Zalo tách khỏi quyền lên đơn; backfill55 ảnh đúng hôm nay, khóa nhập trùng.
- [ ] Hai tin ảnh cục bộ File In chưa khôi phục; không đoán.
- [ ] Không bảo đảm mọi cập nhật app đều tương thích bộ gửi/giải mã.

## Lên đơn ERP
- [x] Tách luồng ERP khỏi thiết kế; lượng từ chữ/ảnh, phiếu lệnh, Lên mẫu/Chờ mã/tên mặc định.
- [x] Ảnh chờ30phút không bổ sung đi phân tích/kiểm chứng, không chỉ lưu đề xuất.
- [x] Chống trùng ID nguồn/request; đối chiếu ngày; tìm đặt thêm3ngày; khóa trạng thái.
- [x] Tin nhân viên không tạo đơn; AI ghi chú riêng.
- [ ] Chưa coi có quét hồi tố toàn bộ mỗi giờ; chưa hỗ trợ tự động mọi yêu cầu hủy/giảm.

## Xuất file
- [x] Có tài liệu2luồng, PDF/AI/Drive, chọn cụm Illustrator, điều phối8096, nối tiến trình ERP.
- [x] PET artwork-only/alpha/spot; JPG CMYK/quy tắc túi; không lật gương.
- [x] Có lưu phiên bản, chống yêu cầu xuất lặp, preview riêng và Duyệt/copy file.
- [x] OpenAI có cổng xác nhận không có file +receipt/cache chống phí trùng.
- [ ] Theo dõi ca OpenAI tự động từ hội thoại mới; không xem test mock là kiểm chứng end-to-end.
- [ ] Canva, font thiếu, mockup khó, sửa từng chi tiết tự do và nguồn mơ hồ chưa được coi tự xử lý hoàn chỉnh.
- [ ] Các checklist cũ ghi chờ restart/copy phải đọc cùng phần cập nhật sau; không tự đánh dấu lại bằng suy đoán trong lượt làm tài liệu.

## Duyệt in
- [x] Tự nhận câu chốt, ghép ảnh nhân viên, chờ yên120s; sender khoảng15s.
- [x] Tự gửi File In cả Zalo/WhatsApp; mốc18h23/10 cố định.
- [x] BÍCH VÂN và Chú Dũng confirmed hai kênh; không tạo lại ERP.
- [x] Giữ khóa theo hồ sơ/kênh; không reset uncertain; loại hồ sơ trước mốc.
- [ ] Hồng Ánh cần đối chiếu ảnh sau OK; Chị Yến còn chỉnh màu. Không tự gửi lại các review cũ.
- [ ] Câu tự nhiên ngoài quy tắc, nhiều mẫu, ảnh chưa về vẫn cần đối chiếu; chưa tự phục hồi mọi review sau khi ảnh tới.

## Khi vận hành hằng ngày
- [ ] Xem heartbeat bộ đọc/worker và hàng đợi lỗi tại8096.
- [ ] Đối chiếu review/uncertain trong Chatwoot, kiểm tra nguồn trước retry.
- [ ] Kiểm tra file mới bằng preview và duyệt rõ phiên bản trước copy.
- [ ] Sau cập nhật: kiểm tra một ca thật phù hợp, ghi bằng chứng, giữ1image dự phòng; không dọn volume.

Tra cứu: [Tổng quan](../TONG_QUAN_HE_THONG.md).

## Cảnh báo xuất file nội bộ — 23/10/2026
- [x] Hub monitor kiểm tra mỗi 30 giây: artwork_checks, native_selections, pet_exports, jpg_exports.
- [x] Lỗi/review mới: ghi chú riêng tư gồm mã lỗi, nguồn, ID job, bước kẹt, lý do và việc cần kiểm tra.
- [x] Heartbeat ArtworkInspector quá 20 phút: cảnh báo mất tín hiệu; không khẳng định worker chết vì có thể mất mạng hoặc Adobe bận.
- [x] Trạng thái file không đổi quá 30 phút từ lúc observer ghi nhận: cảnh báo kẹt bước.
- [x] Chống trùng bền vững theo job/trạng thái/lý do/loại cảnh báo bằng Engine.effect; kết quả gửi không rõ không tự gửi lại.
- [x] Hồ sơ review cũ được lấy làm mốc, không phát lại hàng loạt khi bật tính năng. Thay đổi lỗi mới sẽ báo lại.
- [x] Kiểm thử DB giả: lịch sử, lỗi mới, dedup, che khóa, worker offline, trạng thái hoàn thành, giữ nguyên intake. Hub thật health200, observer khởi tạo 217 hồ sơ.
- [x] Không sửa/tạo đơn ERP, không tự chạy lại xuất file, không RIP hoặc gửi khách.
- Giới hạn: Hub hoặc Chatwoot ngừng hoạt động thì không gửi được cảnh báo tức thì. Khi hoạt động lại sẽ đối chiếu trạng thái còn kẹt. Không phải dịch vụ giám sát độc lập ngoài Hub.
- Mã: integrations/agent-hub/hub/file_notices.py; được gọi độc lập trong monitor_workflow của app.py. Bảng file_notice_watch và file_notice_meta chỉ phục vụ cảnh báo.


## 27/10/2026 — Gom tin, câu hỏi và ảnh ERP
- [x] Gom theo nhóm, chờ từ tin hợp lệ cuối; người gửi khác cũng reset thời gian.
- [x] Câu hỏi rõ: fast path chữ, không tạo ERP/đọc ảnh; mixed order không bị loại.
- [x] Ảnh forward trùng nguồn đơn có ID ERP không tạo lại; ảnh mới không tự bỏ.
- [x] Cache observation được dùng ở ContextGate; ảnh chưa chắc giữ kiểm chứng.
- [x] Phân biệt số lượng hàng cũ trong phản ánh và số lượng đặt thêm mới.
- [x] 82 ca giả lập đã đạt; không tạo đơn thật khi thử. Test mới: test_intake_media_routing.py, test_nonorder_questions.py.
- [x] Hub question-routing-20261027 đã áp dụng; API 8096 OK, gom 10 phút.
- [ ] Theo dõi độ chính xác ngôn ngữ/ảnh thực tế và số lần đọc ảnh; chưa cam kết 100%.

## 27/10/2026 — Gom tin người thật và AI hiểu câu chốt
- [x] Đồng hồ gom tin theo nhóm tính cả khách và nhân viên, theo số phút cấu hình kể từ hoạt động cuối trong đợt. Tin bot/hệ thống không kéo dài thời gian. Tin nhân viên chỉ là ngữ cảnh, không tự thành lệnh đặt hàng.
- [x] Tách yêu cầu lên mẫu và đặt hàng trong cùng đợt thành hồ sơ con với nguồn độc quyền; không để in test làm mất phần đặt sản lượng.
- [x] Gemini 2.5 Flash đọc hội thoại có vai trò để xác định mẫu, tổng hay đặt thêm, dẫn đúng ID và nguyên văn câu hỏi/câu khách xác nhận. Không còn bắt buộc khách phải dùng một danh sách từ ok/ừ.
- [x] Nối ảnh theo trích dẫn hoặc một ảnh duy nhất không bị xen trao đổi; đọc/cached định danh ảnh khi cần. Nhiều mẫu, ảnh mơ hồ, lời xác nhận chưa rõ hoặc API lỗi: kiểm tra nội bộ.
- [x] Code kiểm tra tác giả, nguồn, số lượng, ánh xạ khách và ERP; đối chiếu lại trước ghi. Tổng đã có không tạo thêm; đặt thêm vẫn qua khóa nguồn và quy tắc trạng thái hiện có. Không phát lại nguồn đã tạo/đang gửi/chưa rõ kết quả.
- [x] Bản triển khai: semantic-confirmation-20261027. 151 ca kiểm thử cách ly đạt; thử8 hội thoại giả qua Gemini thật, chỉnh quy tắc total/new và thử lại2ca đạt. Có1ReadTimeout đã thử lại. Không tạo đơn thật khi thử.
- [ ] Theo dõi thực tế — Giới hạn: nhiều yêu cầu chưa tách chắc vẫn review; kết quả thử không chứng minh hiểu mọi hội thoại ngoài thực tế.
