# Mỗi vị trí in một dòng — 27/10/2026
Thay thế quy tắc gộp một dòng trước đó trong PRINT_POSITIONS.md.
- 600 sản phẩm in hai vị trí: hai dòng, mỗi dòng 600 lượt in; cùng print_position_group để ERP tạo một đơn. Không chia 300, không gộp dù trùng mã hàng.
- Mẫu độc lập để print_position_group=null, giữ hành vi cũ. Không suy quan hệ hai vị trí từ hai ảnh mơ hồ.
- Thiếu mã từng dòng để Chờ mã. Mã thực tế theo nguồn/xác nhận; không mặc định PET7X7 cho mọi nón.
- Hub: context_gate.py, clients.py, models.py, agent_loop.py, order_intake.py; đã triển khai và restart riêng Hub.
- ERP: backend_v2/routers/zalo_router.py nhận print_position_group, nhóm dòng trong cùng transaction/request_id; kiểm tra lượng/ngày giao thống nhất. Đã sao lưu, cập nhật source dev và production. CHỜ CHỦ XƯỞNG RESTART ERP.
- Hub kiểm tra health.print_position_groups trước gửi; chưa hỗ trợ thì dừng review, không gửi tạo các đơn rời.
- 4 ca kiểm thử grouping đạt (cùng sản phẩm, mẫu riêng, hỗn hợp, lượng mâu thuẫn); schema tool và compile đạt.
- DH-2610-361 sửa trên UI đơn cũ; người dùng xác nhận cả hai PET7X7. anfa 600, HỮU NGHỊ 600, len_mau. Hai line ID: 6414dae6-51a7-48f8-95da-c115a56250d1 và f0f5327e-2ad6-439f-9f11-9ac2cb360d21. Không tạo lại đơn.
- Không restart ERP, không RIP/gửi khách, không dọn Docker.
