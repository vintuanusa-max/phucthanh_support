# Quy tắc ảnh số lượng → ERP và AI/PDF → PET nội bộ

Cập nhật21/10/2026. Image triển khai:image-quantity-rule-20261021.

- Đọc ảnh/maket, caption và tin trước/sau cùng mẫu; đúng ảnh trích dẫn theoID. Lượng rõ trên ảnh có giá trị, không bắt khách lặp lại bằng chữ. Tin sửa lượng sau cùng ưu tiên cho đúng mẫu; không cộng lượng cũ/mới hoặc vay số giữa mẫu.
- Không mặc định chữ MẪU=1cái. Không mặc định KẾT+số là mã kiểu. Phải phân biệt lượng với kích thước, mã màu, ngày giao, mã mẫu, đường may/vị trí in. Chưa rõ ghi nội bộ, không đoán.
- Xác nhận riêng LOTTE CHOCOLAT/Quyền/ảnh8394302114269: KẾT230 là230 cái đặt in; logo3cm;159/103 là mã màu. Đã tạo DH-2610-295, không phát lại. Không gán230 cho những mẫu khác.
- Đủ yêu cầu đặt hàng và lượng → luồngERP Lên mẫu hiện hữu; ánh xạ đúngID khách, chưa xác định dùngKHACH LE theo chính sách hiện có. Thiếu mã=null/Chờ mã, thiếu tênERP tự đặt. Giữ ledger nguồn/requestID, bất định không tự gửi lại.
- Tìm fileAI/PDF đúng mẫu qua nguồn tin, mã và hình ảnh, không chỉ tên file. Chọn logo/chữ/họa tiết thực, bỏ mockup/nền sản phẩm/đường đo, giữ đủ chi tiết trắng. Nhiều vị trí tách riêng.
- PET: PNG300dpi trong suốt; TIFF qua Photoshop WHITE_1, kiểm spot_1/alpha/kích thước. Không co vải, không dấuL, chưa lật gương. Kích thước theo maket/tin xác nhận; nếu chưa có thì quy tắc source_layout hiện hữu, giới hạn cao6,5cm. Mâu thuẫn không tự quyết.
- Đủartwork/kích thước có thể xuất bản duyệt dù đơn còn chờ lượng. Đủlượng tạoERP không cần chờTIFF. Không áp quy tắcPET sang JPG chuyển nhiệt.
- Chỉ ghi chú nội bộChatwoot và tệp duyệt. KhôngRIP, không gửi khách. Giữ khóajob, không xuất lại lịch sử tự động.

## Mã và kiểm chứng
- hub/image_quantity_rules.py dùng chung cho agent_loop.model_step, verify_action và clients.Agent nhánhorder_intake_only.
- hub/pet_exports.py làm rõ độc lập đơnERP và bảnPET; renderer/Photoshop/ledger giữ nguyên.
- Build/import đạt,15 kiểm thử hồi quy chốngtrùng/phục hồi đạt trong container không mạng. Đây không phải chứng minh Gemini đọc đúng mọiảnh; nguồn mờ hoặc mâu thuẫn vẫnchuyển duyệt.
- Có sao lưu `.before-image-quantity-20261021.bak`. Không sửaERP hoặc tạo đơn/file thử trong lần lưu quy tắc.
