# Cấu hình ánh xạ nhóm ERP
Nguồn chính: U:\phucthanh_support\config.json, mục erp_customer_mappings.
Mỗi dòng mappings gồm account, thread_id, group_name, customer_id, customer_name. Khóa là account + thread_id; tên chỉ để đối chiếu. customer_id là UUID ERP.
Nhóm chưa cấu hình dùng default_customer KHACH LE. Xóa ánh xạ thì các lần xử lý tiếp theo dùng KHACH LE. Không sửa đơn đã tạo. Đề xuất chờ có thay đổi ánh xạ phải được kiểm tra lại.
Nhóm bỏ qua và nhân viên nội bộ vẫn áp dụng độc lập; ánh xạ không mở lại nhóm bị bỏ qua.
Bộ đọc Zalo đồng bộ riêng mục này khoảng 30 giây; hub xác minh cấu trúc rồi lưu cache nguyên tử trong /data/group-customer-mappings.json. Không chứa token. Khi config lỗi giữ cache hợp lệ trước đó, không chấp nhận ID nhóm trùng. Đồng bộ Zalo thất bại lâu sẽ làm chính sách hết hạn và dừng lên đơn Zalo.
Không cần trang quản lý hoặc chỉnh cache trực tiếp. Nếu bộ đọc Zalo ngừng thì thay đổi file chưa được đồng bộ.
Ngày 2026-10-23 đã nhập đủ 323 ánh xạ, gồm 62 có hội thoại hiện hữu và các nhóm lịch sử. Các khóa khác của config.json được so sánh giữ nguyên; bản sao lưu nằm cạnh config.
Kiểm thử đạt: ánh xạ cũ; version ổn định; nhóm mới KHACH LE; ID trùng bị chặn; cache hợp lệ giữ nguyên; bỏ ánh xạ về KHACH LE; không sửa đơn cũ.
