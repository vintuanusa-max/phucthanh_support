# Quy trình lên đơn ERP — tóm tắt hiện hành
Cập nhật23/10/2026, tổng hợp từ tài liệu triển khai và các lần kiểm chứng trước; lần cập nhật tài liệu này không thử ghi đơn thật.

1. Bộ đọc đưa tin/ảnh vào Chatwoot và Hub bằng ID nguồn/checkpoint. Nhóm bị bỏ qua không được phép tạo đơn, kể cả có ánh xạ.
2. Ghép cụm cùng khách/nhóm/mẫu; đọc lượng trong lời nhắn hoặc ảnh. Đối chiếu trích dẫn và lời đính chính; không lấy số đo/mã màu thành số lượng.
3. Với trường hợp chỉ ảnh, chờ30phút không có bổ sung rồi phân tích/kiểm chứng ảnh theo run hiện có. Đây không phải lịch bắt buộc cho mọi đơn; thiếu lượng hoặc mâu thuẫn vẫn review.
4. Đủ dữ liệu đặt hàng → lưu bằng chứng, gửi request ERP có khóa chống trùng → tạo **Lên mẫu**. Không đợi file thiết kế hoặc file in xong.
5. Ánh xạ account+IDnhóm từ config.json.erp_customer_mappings. Chưa cấu hình → KHACH LE; thiếu mã hàng → Chờ mã; thiếu tên → ERP tự đặt. MET cho in mét và trường hợp AN NGUYEN đã xác nhận giữ lượng tấm; mặt nạ → MATNA. Không suy mã từ một con số đơn lẻ.
6. Đọc kết quả ERP, lưu IDđơn và ghi chú riêng Chatwoot. Không báo đã tạo chỉ vì đã có bản đề xuất.
7. Nối tiến trình file với đúng đơn/nhóm/mẫu và cụm nguồn; một lượt nhiều đơn không gán toàn bộ ảnh cho mọi đơn. Chưa khớp → chờ đối chiếu.

## Chống trùng và đặt thêm
ID nguồn/request_id bảo vệ phát lại; đối chiếu đơn mới trong ngày. Tìm đơn đặt thêm theo file in/ghi chú đúng khách trong3ngày gần nhất, không quét toàn bộ lịch sử. Không chắc đơn cũ thì xét tạo đơn mới theo chính sách, nhưng vẫn kiểm tra nguồn và trùng trước khi ghi.

| Thao tác | Trạng thái cho phép |
|---|---|
| Tăng lượng đơn cũ | Lên mẫu, Mẫu có sẵn, Đang chạy giấy |
| Giảm/hủy/xóa | Lên mẫu, Mẫu có sẵn |
| In thêm sau Đang chạy giấy | Đơn Lên mẫu riêng cho lượng thêm |

API có hàng rào trạng thái; bot chưa được coi là đã có công cụ tự giảm/hủy mọi yêu cầu. Yêu cầu chưa hỗ trợ chuyển nhân viên. Kết quả ghi không chắc phải đối chiếu ERP, không tạo lại mù.

## Phân biệt nhân viên và khách
Tin/ảnh nhân viên được lưu làm ngữ cảnh duyệt mẫu, lỗi sản xuất hoặc nghỉ phép. Danh sách internal_members và origin=staff loại khỏi điều kiện tạo đơn. Tin bot/echo không kích hoạt vòng lặp.

## Theo dõi
Xem tin gốc → trạng thái intake → bằng chứng → IDđơn ERP → ghi chú Chatwoot. Chưa có bằng chứng triển khai một lượt quét lại toàn bộ mỗi giờ; không mặc định restart sẽ giải quyết mọi trường hợp sót.

Chi tiết/lịch sử: [Hai luồng](HAI_LUONG_DON_HANG_VA_FILE_MAU.md), [ánh xạ](GROUP-CUSTOMER-MAPPINGS.md), [phiếu lệnh](PHIEU_LENH_TU_DONG_ERP_20261015.md), [checklist](CHECKLIST_VAN_HANH_HE_THONG.md).
