# Đối chiếu đơn và chuyển in bù — 14/10/2026

## Kết quả thực tế
- DH-2610-225: Chú Dũng, logo SI SÓC, 120 cái, mạc nón 5 múi. API ERP xác nhận Len mau.
- DH-2610-226: CHỊ ÉN NHỎ, LIFT, 50 cái, in 3 vị trí. API ERP xác nhận Len mau.
- Hai nhóm trên giữ ánh xạ KHACH LE đang có. Không tự đổi khách ERP trong đợt phục hồi.
- TRAVEL Together là mẫu riêng chưa có số lượng; chưa tạo đơn.
- LÊ ĐỘ bù 60 cái kết màu rêu: chuyển hồ sơ sản xuất, chưa tạo ERP. Không cộng số lượng ảnh chụp hội thoại cũ 06/10 của Nguyễn Lan.

## Hồ sơ gửi đã xác nhận
- CHOT-IN-7f8961fa1984bd1a.
- NAS: \\192.168.1.203\n8n_upload\LE DO\orders\CHOT-IN-7f8961fa1984bd1a\evidence-e65a055fffba042b
- Zalo: 8374235780767, confirmed.
- WhatsApp: true_120363407119559834@g.us_3EB0EEB2870EB25885896B_47902441381955@lid, confirmed, ack=1.
- Đích cả hai kênh: File In - Giấy In - Màng Pet.
- Bản tổng hợp ghi rõ chú thích ảnh WhatsApp chưa kiểm chứng; nguồn gốc không bị sửa.

## Quy tắc hiện hành
Đối chiếu trùng theo nội dung chỉ trong ngày Việt Nam của lượt nhận. Không lấy đơn ngày trước để chặn đơn mới. Chống phát lại đúng message_id/request_id giữ nguyên xuyên ngày.
Yêu cầu in bù rõ số lượng + ảnh cùng khách trong 120 giây được lập hồ sơ IN BÙ, không ghi thành thay đổi sau duyệt, không tự tạo ERP mới. Chờ nhóm yên 120 giây. Thiếu ảnh, caption chưa kiểm chứng, nhiều khách xen kẽ hoặc sửa tiếp thì chuyển kiểm tra nội bộ.
Hàng đợi NAS và giao hai kênh dùng cơ chế cũ; mỗi kênh có biên nhận riêng. Không tự gửi lại khi kết quả không chắc chắn.
Trả lời AI cho khách vẫn chỉ private Chatwoot; thông báo sản xuất hai nhóm là luồng riêng được chủ hệ thống cho phép.

## Mã nguồn
hub/print_approval.py: nhận diện/chọn nguồn in bù, tạo hồ sơ, giao hai kênh.
hub/order_intake.py: tách in bù khỏi đơn mới; giới hạn đối chiếu cùng ngày.
hub/agent_loop.py: ngữ cảnh đề xuất cùng ngày, đa công cụ một lượt, hóa đơn không thành đơn mới.
whatsapp_desktop/print_sync.py: renderer NAS và vận chuyển có sẵn, không đổi trong lần này.

## Giới hạn đã biết
Tin LÊ ĐỘ thực tế có ảnh người khác xen kẽ và caption chưa xác minh nên được phục hồi có xét duyệt riêng theo yêu cầu chủ hệ thống; không coi đó là kiểm thử tự động không giám sát. Chưa giải quyết tổng quát mọi biến thể ngôn ngữ in bù.
