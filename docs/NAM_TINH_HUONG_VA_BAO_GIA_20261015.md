# Năm tình huống khách hàng và báo giá — 15/10/2026

## Chính sách vận hành
1. Ảnh rồi số lượng: gom theo cùng khách/nhóm, chờ yên 120 giây. Tin bổ sung sau câu hỏi nội bộ được nối lại trong cùng ngày, tối đa 30 phút. Kiểm chứng đúng mẫu/số lượng rồi lên ERP Lên mẫu.
2. Số lượng trên ảnh: Gemini đọc ảnh cùng ngữ cảnh; tin sửa số lượng sau ưu tiên. Không nhầm kích thước/vị trí in với lượng sản phẩm. Cơ chế đọc lại ảnh sau 30 phút đã có vẫn giữ.
3. Có ý đặt in nhưng thiếu lượng: soạn câu hỏi bao nhiêu trong ghi chú private Chatwoot; không tự gán lượng. Hiện chưa gửi câu hỏi ra nhóm khách.
4. Duyệt mẫu nhân viên gửi: giữ luồng tổng hợp PNG NAS và chuyển nhóm File In - Giấy In - Màng Pet trên Zalo/WhatsApp. Đổi màu/sửa mẫu chuyển nhân viên, worker thiết kế giai đoạn 2 chưa triển khai. Đổi địa chỉ là yêu cầu giao nhận riêng, chưa tự sửa ERP; nhân viên kiểm tra.
5. Hỏi giá: Gemini đọc ngữ cảnh, gọi lookup_print_price để tra nguồn rồi prepare_print_quote. Thiếu ngang/cao/số lượng/kỹ thuật thì hỏi bổ sung nội bộ. Kích thước phải do nguồn chứng minh, không suy từ pixel. Công cụ tính giá, Gemini không được bịa số. Giá chưa thành đơn; cần khách xác nhận đặt.
Ngoài phạm vi câu hỏi thiếu lượng/thông số báo giá và báo giá: không soạn trả lời khách. Ghi chú vận hành/chuyển người vẫn được giữ. business_reply_scope=true; public_replies=false, internal_only=true; auto_order=true trên nhóm được phép.

## Nguồn và các xác nhận ưu tiên của chủ hệ thống
Nguồn: U:\phucthanh_support\docs\BANG GIA IN PHUC THANH.xlsx, sheet BAOGIA.
Bản gốc Excel được giữ nguyên. hub/pricebook.json là snapshot kèm SHA256, dòng và ô nguồn; không tự đồng bộ khi Excel đổi. Sau sửa Excel cần nhập lại, kiểm tra quy tắc, kiểm thử và triển khai. Bộ tính chặn snapshot khác hash đã duyệt, không lặng lẽ áp giá cũ lên bảng mới.
- PET diện tích: chủ xác nhận 15/10 dùng C25 (7×7cm=1000đ) cho tất cả kích thước có ít nhất một chiều ≤29cm. Giá = 1000 × ngang × cao / 49. Cả hai chiều >29cm: nhân viên báo riêng. Quy tắc này thay mốc C35 cho luồng tính diện tích.
- Laser hình chữ nhật: chủ xác nhận sửa C32 thành chu vi=2×(dài+rộng), giá=100×chu vi/50cm. Hình bất kỳ không lấy chu vi khung bao; cần đường cắt thực tế/nhân viên.
- Đơn giá tính theo công thức làm tròn tới một đồng, tổng=đơn giá đã làm tròn×lượng; đây là bản báo giá tham khảo nội bộ, không áp giá vào ERP.
- CANAVI có C37 riêng, không dùng giá chung; ranh giới A5/A4/A3 chưa rõ nên giữ nhân viên xác nhận.
- PET mét ở C5 còn thiếu khoảng 5–10m và chồng mốc 100/500m: chưa tự chọn giá tại các khoảng này.
- Nón đã may C28 và túi C26 chưa đủ điều kiện kích thước/vị trí/số mặt: chuyển nhân viên. Các mức rõ ở C19, C30, C36 và khoảng rõ ở C5/C6 được tra đúng đơn vị.
- Chưa có quy định VAT/phí khác; không cam kết bao gồm.

## Mô-đun và kiểm thử
hub/price_quote.py: tra snapshot, điều kiện tính, phép tính, nguồn ô/hash và các xác nhận trên.
hub/agent_loop.py: 2 công cụ báo giá, kiểm chứng nguồn bằng Gemini, phản hồi nội bộ, giới hạn chủ đề.
hub/order_intake.py: nối lời bổ sung với câu hỏi đã ghi nhận, giữ chống tạo trùng và nguồn ảnh.
Tests: 65 kiểm thử gộp ban đầu đạt; sau xác nhận công thức, 33 giá/agent và 28 intake đạt, có kiểm tra 29cm, công thức laser, giá CANAVI, thiếu kích thước và đúng một ERP write giả lập.
Chưa tuyên bố đã kiểm chứng một cuộc báo giá thật tự động ngoài nhóm; không phát lại tin cũ hoặc gửi thử công khai.

## Kiểm chứng sau triển khai
Gemini thật đã approved nguồn giả lập PET 10×10cm, 50 cái. Bộ tính trả 2041đ/cái, tổng 102050đ, nguồn C25 và override chủ hệ thống. Không gửi tin công khai, không ghi ERP. Cấu hình cả hai kênh được đọc lại: business_reply_scope=true, auto_order=true, public_replies=false, internal_only=true. Hub running.
