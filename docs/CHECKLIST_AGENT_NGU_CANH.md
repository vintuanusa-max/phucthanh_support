# Checklist hiện hành — 14/10/2026

## Giai đoạn 1

- [x] Agent gọi công cụ nhiều bước và dùng kết quả bước trước.
- [x] Tra tiến độ ERP theo khách ánh xạ; kiểm chứng đúng khách/khác khách.
- [x] Tham khảo báo cáo vải nhân viên cùng nhóm, không dùng tồn ERP.
- [x] Kiểm chứng đề xuất và nguồn trước khi chuyển vào luồng lên đơn.
- [x] Tự lên ERP trạng thái Lên mẫu qua luồng cũ: kiểm tra số lượng/khách, bằng chứng NAS, mã yêu cầu chống trùng.
- [x] Phản hồi/câu hỏi AI chỉ ghi chú private Chatwoot, chặn gửi công khai tại tầng giao tin.
- [x] Áp dụng toàn bộ nhóm được phép Zalo/WhatsApp; giữ loại trừ và tin riêng.
- [x] Chuyển Open khi cần nhân viên; phục hồi tác động không chắc chắn sau restart.
- [x] 33 kiểm thử agent + intake đạt sau nối lại lên đơn; ca mới xác nhận đề xuất vào awaiting_evidence và giữ request_id, không sinh delivery công khai.
- [x] Cấu hình đang chạy: erp_write=true; cả hai kênh auto_order=true, public_replies=false, internal_only=true.
- [x] Gemini thật đã đọc báo cáo vải rồi tạo ghi chú private #891 trong hội thoại AN NGUYÊN #27.
- [x] Phục hồi có đối chiếu nguồn: DH-2610-225 (Chú Dũng 120), DH-2610-226 (LIFT 50); API xác nhận Lên mẫu. Đây là lượt phục hồi đã duyệt, không phải bằng chứng mọi lượt AI đều tự xử lý đúng.
- [ ] Theo dõi chất lượng ghi chú trên tin mới trước khi chủ hệ thống cho phép trả lời nhóm thật.

## Giai đoạn 2

- [ ] Worker chỉnh sửa thiết kế.
- [ ] Quản lý phiên bản file và Gemini Vision kiểm chứng kết quả.
- [ ] Kiểm chứng gửi file đã sửa cho khách.

Không dùng các mô tả pilot hai nhóm hoặc chỉ lưu đề xuất của bản trước làm cấu hình hiện hành.

## Bổ sung in bù và đối chiếu ngày — 14/10/2026
- [x] Ngữ cảnh đề xuất cũ và kiểm tra đơn gần đây giới hạn cùng ngày UTC+7; mã nguồn/request_id vẫn chống phát lại xuyên ngày.
- [x] Yêu cầu in bù rõ số lượng tách khỏi tạo đơn mới; ảnh cùng người gửi trong cửa sổ 120 giây, nhóm được phép.
- [x] Tự lưu PNG NAS, gửi hai nhóm sản xuất qua hàng đợi độc lập từng kênh, không gửi lại kênh đã xác nhận.
- [x] Bù 60 cái màu rêu LÊ ĐỘ: đã gửi Zalo và WhatsApp, biên nhận confirmed cả hai.
- [x] Trường hợp LÊ ĐỘ có người khác xen ảnh và caption chưa xác minh: phục hồi theo chỉ định cụ thể của chủ hệ thống, kèm cảnh báo; không nới chặn chung.
- [x] Kiểm thử cuối: 36 agent/intake + 7 chuyển in đạt. Bộ đọc WhatsApp đã khởi động lại.
- [ ] TRAVEL Together: chờ số lượng riêng; không lấy 50 cái của LIFT.
- [ ] Theo dõi ca in bù mới đủ thông tin hoàn toàn tự động; ca mơ hồ vẫn cần nhân viên.


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
