# Khách trả lời số lượng muộn — 31/10/2026

## Quy tắc đang áp dụng
- Một lượt khách gửi ảnh nhưng chưa có số lượng có thể chờ lượt sau bổ sung. Collector chỉ lấy lại nguồn chưa được ghi ERP, chưa gửi/chưa có kết quả không chắc chắn, cùng tài khoản và ID nhóm, qua kiểm tra `reusable()`.
- Không gom toàn bộ lịch sử tùy ý. Giữ giới hạn hiện có của collector: cùng ngày Việt Nam, tối đa 24 giờ và giới hạn số nguồn; trường hợp ngoài phạm vi hoặc nhiều mẫu chưa rõ cần kiểm tra.
- Bộ xác nhận giữ đủ ảnh mẫu, câu hỏi của nhân viên và câu trả lời khách. Câu hỏi là bằng chứng, không phải một yêu cầu độc lập.
- Khi câu hỏi đã thuộc cụm được collector nối lại, cho phép xác nhận trong tối đa 24 giờ; câu hỏi chỉ nằm trong lịch sử ngoài cụm vẫn giới hạn 1 giờ.
- AI xác định mẫu, số lượng tổng hoặc đặt thêm; code kiểm chứng ID, tác giả, thời gian, trích dẫn và các nguồn còn lại. Không bỏ yêu cầu độc lập khác để ép tạo một đơn.
- Đơn đã có, nguồn đã ghi ERP/đang gửi/chưa rõ kết quả không được tự tạo lại. Tổng số lượng được đối soát ERP; đặt thêm vẫn đi theo khóa nguồn riêng.
- Chạy lại có kiểm soát dùng hàng `intake_operator_retry`, giữ đề xuất AI và request_id ổn định; không nhập tay tên mẫu hoặc số lượng.

## Ca xác nhận thực tế
CHÚ PHÁT: ảnh mẫu → nhân viên hỏi số lượng → khách trả lời 100 cái muộn.
Collector đã nối đủ ba tin nhưng bộ xác nhận cũ chặn nhầm câu hỏi của nhân viên.
Sau sửa, kiểm tra ERP chưa có NAVICO, chạy lại qua hàng retry và tạo đúng một đơn DH-2610-456, Lên mẫu, NAVICO 100 cái; không gán tay dữ liệu.

## Checklist
- [x] Giữ câu hỏi nhân viên trong bằng chứng xác nhận.
- [x] Giữ nguồn đã được collector nối lại dù ngoài cửa sổ lịch sử 1 giờ.
- [x] Kiểm thử cô lập: trả lời muộn, ảnh + hỏi + đáp, yêu cầu khác bị chặn, câu hỏi cũ chưa nối bị chặn, ERP đã có trả duplicate.
- [x] Đồng bộ Hub chính, mirror và container; Hub khởi động khỏe.
- [x] Ca thật CHÚ PHÁT chỉ chạy sau khi chủ xưởng cho phép; đối soát ERP sau chạy có đúng một đơn 100 cái.
- [x] Không thay đổi cơ chế khóa nguồn hoặc tự chạy lại hồ sơ cũ.
- [x] Không đưa cấu hình bí mật, token, API key, file phiên hoặc cơ sở dữ liệu vào commit.

## Tệp liên quan
- `integrations/agent-hub/hub/conversation_confirmation.py`
- `integrations/agent-hub/tests/test_delayed_quantity_confirmation.py`
- Collector và khóa hiện có: `order_intake.py`, `intake_lifecycle.py` (không sửa trong bản vá này).

Chạy kiểm thử độc lập, không gọi API: `python integrations/agent-hub/tests/test_delayed_quantity_confirmation.py`.
