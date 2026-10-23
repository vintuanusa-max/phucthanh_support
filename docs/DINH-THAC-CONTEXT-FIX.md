# ĐÌNH THẠC — bổ sung số lượng sau file (21/10/2026)
- Xác nhận khách ERP DINH THAC: 0997d0ac-a25c-4f6c-8925-20dcbf97489f.
- Nhóm zalo-personal-1/g2076783837431625476 đã chuyển từ KHACH LE sang ID trên, có lịch sử ánh xạ.
- File nguồn8399475904422 CTY ANCATERING.pdf; tin8399724997237 “Cháu in luôn cho chú nha,352 cái”.
- Nguyên nhân: confirms_order chưa có “in luôn” nên không lấy file của lượt review trước; agent tham chiếu nguồn lịch sử bị chặn khi không thuộc batch.
- Bổ sung in luôn/in dùm/in giùm/cho in, giữ chặn phủ định/câu hỏi. 6 kiểm thử đạt. Giữ giới hạn cùng nhóm/người/ngày, chưa có request_id/submitted_payload; không nới kiểm tra nguồn tùy ý.
- Phục hồi run17fc4ebb... theo xác nhận trực tiếp của chủ, chuyển quyền nguồn file từ runfcb644f0... sang run mới; run cũ superseded, không phát lại. Tin loại4 chưa đọc được vẫn giữ capture để kiểm tra, không suy diễn hay xóa.
- Chỉ 352 cái, Chờ mã, Lên mẫu. Đã đối chiếu ANCATERING ở đúng khách không có trùng trước khi xử lý. Phản hồi chỉ nội bộ.
- Kết quả thực tế: DH-2610-306, UUID8fcddbd0-03b5-43ec-89cf-c666e32f46a4; ERP xác nhận len_mau,352.00, đúngDINH THAC. Ghi chú3875 private=true.
- Khôi phục thủ công: bước submit tự động của payload phục hồi báo AttributeError trước khi có submitted_payload; đã dùng API idempotent với request_id nguyên run sau khi kiểm tra chưa gửi. Không tuyên bố đã sửa AttributeError này; bản sửa tổng quát trong lượt là nhận xác nhận in luôn và nối nguồn cũ.

## Submit AttributeError — đã sửa 21/10/2026
Tái hiện trên bản sao SQLite tạm, chặn network: order_policy.py:62 gọi .get trên None khi policy heartbeat quá120giây; submit.py truyền policy None. Không liên quan mã hàng/số lượng.
Đã sửa submit đọc lại trạng thái bền vững: chỉ evidence_ready mới xét gửi; policy None thì giữ nguyên chờ, không gọi ERP/không chuyển review. Khi heartbeat hợp lệ, tiếp tục kiểm tra nguồn/khách/policy và atomicclaim sending như cũ. Không nới các chặn nghiệp vụ.
6 kiểm thử SQLite memory+ERP mock đạt: hết hạnchờ, hợp lệgửi, createdkhônggửi lại, timeoutuncertain, uncertainkhônggửi lại, policycấm khônggửi. Image submit-policy-20261021 đã triển khai; health200. Đơn306 đã xác minh chỉ đọc vẫn352 Lên mẫu và đúngDINH THAC, không tạo lại. Ghi chú AI vẫnprivate theoEngine.note hiện hành.

## Rà soát các lượt kẹt gửi — 21/10/2026
Đã kiểm toàn bộ intake_runs:49created,1amended,61ignored,410review,42superseded tại thời điểm kiểm tra. Không còn reason AttributeError, không có evidence_ready/sending/uncertain; không có review kèm đủ orders+image_base64 cần gửi lại. Request chưa kết thúc duy nhất có orders là Lê Độ60 inbù, đã có chỉ định không tạo ERP mới nên giữ nguyên.
Không tạo thêm đơn trong lượt rà soát. Không coi410review là đã đủ thông tin; đây là các lý do nghiệp vụ khác ngoài lỗi submit đang xét.
Phát hiện tiến trình Zalo reader không chạy, policy cũ4454giây; khởi động lại bằng Start-Reader.ps1 giữ cutoff/checkpoint. Hub đã nhận policy Zalo mới7,7giây. Không đổi mapping/số lượng đơn cũ, không gửi tin khách.
