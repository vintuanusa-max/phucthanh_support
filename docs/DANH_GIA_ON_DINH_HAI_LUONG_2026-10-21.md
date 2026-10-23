# Đánh giá thực tế hai luồng — 21/10/2026

Kết luận: dịch vụ đang hoạt động, nhưng chưa đủ bằng chứng gọi cả hệ thống tự động ổn định hoàn toàn.

## Đã kiểm chứng
- Redis/PostgreSQL healthy; Rails/Sidekiq chạy. Heartbeat reader/artwork của Zalo, WhatsApp, Viber mới; active alerts=0 tại lần đọc.
- A Thức DH-2610-310 đã lên 400 cái Lên mẫu qua luồng chứng từ NAS và submit ERP; giữ request ID.
- 6 kiểm thử giả lập submit: policy cũ chờ, mới tiếp tục, created không replay, timeout uncertain, uncertain không replay, nhóm loại bỏ bị chặn.
- Kiểm thử định tuyến in thêm và 32 ca trạng thái/thao tác ERP đạt trên image hiện tại; không sửa đơn thật để thử.
- Quy tắc vị trí nón 6,5cm/7cm, giữ tỷ lệ và ưu tiên kích thước khách đã được kiểm thử. Không áp sang túi/vị trí chưa rõ.

## Tồn đọng thực tế, không được coi là hoàn tất
- Bảng intake_runs: 52 created, 1 amended, 423 review, 61 ignored, 43 superseded. Đây là toàn lịch sử, có tin không phải đơn và hồ sơ cũ; KHÔNG đồng nghĩa 423 đơn bỏ sót và KHÔNG replay hàng loạt.
- Bảng pet_exports: 6 review, chưa có done; jpg_exports: 1 done. File từng xuất thủ công có thể nằm ngoài bảng này, không chứng minh tự động xuyên suốt.
- 88 artwork_checks review: cần phân loại đúng lỗi/ngữ cảnh, không tự bỏ qua mọi guard.
- Tuyến PDF/AI có bóc đối tượng/đối chiếu/thẩm định nhưng chưa chứng minh thành công cho đủ các loại nguồn. Raster chỉ có ảnh, nền ảnh phức tạp/chữ trắng cần tách và kiểm tra riêng. CẦN THƠ đã có mặc định cao 6,5cm, không còn thiếu kích thước; còn bước tách/xuất raster.
- Link Canva chưa có tuyến xuất thành file nguồn; Drive/direct file dùng tuyến hiện có.

## Áp dụng lần này
- [x] Thêm OWNER_OUTPUT_POLICY vào PET planner và verifier: mirror=false đã được duyệt, không đòi xác nhận lật gương; một chiều có căn cứ thì tính chiều kia theo tỷ lệ, không hỏi thừa.
- [x] Build output-policy-20261021 và kiểm thử policy/syntax đạt; source live/mirror có sao lưu; restart riêng hub.
- [x] Không replay hàng loạt hồ sơ cũ; không tạo đơn thử, không RIP/gửi khách.
- [ ] Kiểm chứng toàn bộ PNG → TIFF → preview nội bộ trên các trường hợp tự động thực tế, gồm ảnh raster.
- [ ] Phân loại 6 PET review từng hồ sơ, đối chiếu file/phiên bản trước khôi phục. Không tự coi nhận định AI cũ là lỗi kỹ thuật.

Không dùng trạng thái container Up hoặc kiểm thử giả lập thay cho bằng chứng đúng artwork, màu và file in thực tế.
