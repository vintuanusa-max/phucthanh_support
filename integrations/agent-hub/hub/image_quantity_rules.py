"""Owner-approved image quantity interpretation, 2026-10-21. No execution side effects."""
IMAGE_QUANTITY_RULES = '''
ĐỐI CHIẾU SỐ LƯỢNG ẢNH/TIN:
Đọc toàn bộ maket, ảnh trích dẫn đúng ID, caption và tin trước/sau của cùng mẫu; không chỉ tìm chữ số trong tin chữ. Nếu ảnh ghi lượng đặt rõ và khách yêu cầu làm/in thì có thể đề xuất đơn Lên mẫu, không bắt buộc khách lặp lại lượng bằng chữ. Chữ MẪU không tự quy thành 1 cái và không làm mất lượng ghi trong ảnh.
Cụm KẾT + số có thể là số lượng nón/két đặt in, không được mặc định đó là mã kiểu. Trường hợp chủ đã xác nhận: khách Quyền, mẫu LOTTE CHOCOLAT, ảnh8394302114269 ghi KẾT230 = đặt in230 cái; cao3cm là kích thước logo;159/103 là mã màu vải. Chỉ áp xác nhận230 cho đúng hồ sơ này, không gán230 cho mẫu khác hoặc tự tạo lại đơn đã có.
Với mẫu tương tự, đối chiếu toàn bộ bố cục, đơn vị, nội dung đặt hàng và xác nhận liên quan; không biến mọi số cạnh KẾT thành lượng. Phân biệt lượng với mã màu, mã mẫu, ngày giao, kích thước và số đường may/vị trí in. Nếu chưa phân biệt chắc thì ghi rõ nội bộ để người kiểm tra.
Tin sửa lượng sau cùng áp cho đúng mẫu được ưu tiên; không cộng lượng cũ+mới, không vay lượng giữa các mẫu. Dẫn ngắn gọn nguồn/chữ đã đọc và lý do chọn lượng trong reason để kiểm chứng. Giữ chống trùng nguồn/requestID; chưa rõ kết quả gửiERP không gửi lại. Thiếu mãERP dùng null/Chờ mã, thiếu tên để ERP tự đặt. Phản hồi chỉ ghi chú nội bộ Chatwoot, không tự gửi khách.
'''
