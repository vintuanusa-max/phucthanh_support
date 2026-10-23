# Kiểm tra ERP và Chatwoot từ 18h — 21/10/2026

Phạm vi: 18:00–khoảng 20:44, UTC+7. Chỉ đọc dữ liệu sản xuất; không tạo, sửa, giảm, hủy hoặc xóa đơn; không gửi tin khách.

## Quy tắc trạng thái
- GET ERP xác nhận mutation_policy=quantity-states-v2.
- Tăng: len_mau, mau_co_san, dang_chay_giay.
- Giảm/hủy/xóa: len_mau, mau_co_san.
- Chạy lại 32 ca trạng thái/thao tác, giảm xen tăng và bỏ dòng: PASS trên dữ liệu giả, không mạng/DB thật. Kiểm tra khóa bản ghi và vị trí guard trong routes đạt. Đây không phải thử giao dịch ghi vào ERP sản xuất.
- Bot hiện tự cộng lượng; không có công cụ tự hủy/giảm. Quy tắc giảm/hủy/xóa được chặn tại API ERP.

## Đối chiếu tin
Đã quét danh sách 71 hội thoại Chatwoot, thấy 12 tin incoming không private thuộc 5 nhóm từ mốc 18h; khớp 12 capture cục bộ.

### A Thức — 400 cái: còn kẹt
Hai ảnh + 400c, khoảng 18:09; Chatwoot #7, tin 4011–4013. AI nhận đúng new_order, mẫu mũ tai bèo logo CTY TNHH BVTV VN CẦN THƠ, nhưng trả thiếu product_details/design_confirmation nên run vào review, chưa có kết quả ERP trong hub.
Run: 57407ca6d349c9e90acb6dd463bd817c657e812beb22189842182d04d87a34d5.
Ghi chú nội bộ 4014 xác nhận chưa tạo đơn mới. Ánh xạ đúng A THỨC. GET tìm ERP theo CẦN THƠ và BVTV VN trong cửa sổ 3 ngày đều không có kết quả. Tìm từ khóa không bảo đảm phát hiện đơn thủ công đặt tên khác; cần đối chiếu thêm trước khi xử lý lại. Chưa replay/tạo đơn trong lần rà soát này.

### Các nhóm còn lại
- C9 Kỉ Niệm Đong Đầy: 4 tin trao đổi không phải yêu cầu đặt hàng; không tạo đơn là phù hợp.
- Cty In Phúc Thanh: tin nghỉ phép, không phải đơn.
- CANAVI, INJAE và một tin nhân viên A Thức: tổng 4 tin loại 2 chỉ có placeholder, chưa đọc được nội dung. Chưa thể xác nhận các tin này có đơn hay không; không suy đoán từ placeholder.

## Kết luận
Ma trận trạng thái đã được nạp. Luồng lên đơn chưa hoàn toàn thông suốt: trường hợp 400 cái A Thức bị chặn ở bước đánh giá ngữ cảnh, không phải lỗi trạng thái ERP. Cần xử lý có kiểm soát và kiểm tra chống trùng trước khi replay. AI vẫn chỉ ghi chú nội bộ.
