# Quy trình lên đơn ERP — tóm tắt hiện hành
Cập nhật 27/10/2026. Kiểm thử bằng dữ liệu giả, không tạo/sửa đơn thật.

1. Bộ đọc đưa tin/ảnh vào Chatwoot và Hub bằng ID nguồn/checkpoint. Nhóm bị bỏ qua không được phép tạo đơn, kể cả có ánh xạ.
2. Gom tin hợp lệ theo account + ID nhóm, không tách theo người gửi. Phân loại chữ/ngữ cảnh trước; chỉ đọc ảnh khi còn cần xác định yêu cầu, mẫu hoặc số lượng. Đối chiếu trích dẫn và lời đính chính; không lấy số đo/mã màu thành số lượng.
3. Chờ đủ thời gian cấu hình từ tin hợp lệ cuối của đợt (hiện 10 phút), kể cả đã đủ số lượng. Tin hợp lệ mới trong nhóm tính lại thời gian. Nguồn chưa tải xong tiếp tục chờ; không ghi ERP sớm.
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


## Câu hỏi, ảnh chuyển tiếp và đặt thêm
- Câu hỏi rõ về lỗi mẫu/giá/tiến độ/giao nhận/chất liệu có fast path bằng chữ, không gọi AI đọc ảnh hoặc ERP. Chỉ dùng khi toàn bộ đợt rõ mục đích, tối đa một tin có ảnh và không có file phụ; số liệu hay chỉ dẫn mới thì đi tiếp phân tích.
- Ảnh có byte trùng nguồn đơn created/duplicate đã có ID ERP, trong cùng account/nhóm: chỉ duyệt mẫu thì không tạo đơn; chỉ gửi lại chưa rõ mục đích thì giữ review, không đọc lại. Không fuzzy-match ảnh cắt/chụp/nén khác.
- Cache ảnh theo model/account/nhóm/MIME/SHA256. ContextGate dùng observation chắc chắn khi đủ nguồn; không dùng cache như quyết định tạo đơn. Verifier cuối vẫn có thể đọc ảnh gốc.
- Ảnh nhân viên làm ngữ cảnh, không thành yêu cầu đặt của khách. Không tự bỏ ảnh khách mới chỉ vì không có chữ số.
- Đặt thêm được ưu tiên trong đợt lẫn câu hỏi. Ví dụ “100 cái trước bị lệch, in thêm 200 cái” → lượng mới 200; không cộng thành 300 hoặc lấy 100. Điều kiện/phủ định/mâu thuẫn vẫn chặn để kiểm tra.
- Bỏ qua lên đơn không có nghĩa đã giải quyết lỗi thiết kế; tin gốc vẫn ở Chatwoot. Không chạy lại các nguồn đã committed/sending/uncertain.

Kiểm thử: 82 ca giả lập đạt (bộ 28 quy tắc + 26 ảnh/ngữ cảnh + 28 câu hỏi/đặt thêm), không API thật. Các test mới trong commit này độc lập với bộ thử xuất file; chưa đo chi phí hay độ chính xác AI thực tế. Xem INTAKE_ROUTING.md và CHECKLIST_VAN_HANH_HE_THONG.md.
