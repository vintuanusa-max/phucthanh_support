
## Quy tắc dọn Docker sau cập nhật — chủ xưởng xác nhận 22/10/2026
- Sau mỗi lần cập nhật hub: xác minh health và đúng mã đang chạy trước khi dọn.
- Chỉ giữ image hub hiện tại và một image hub dự phòng là bản hoạt động ngay trước cập nhật. latest và tag phiên bản có thể cùng trỏ một image.
- Kiểm tra tất cả container (kể cả đã dừng); không xóa image được container sử dụng, không dùng force.
- Chỉ xóa các image/tag cũ thuộc phucthanh-chatwoot-hub. Không dọn image Chatwoot/PostgreSQL/Redis hoặc ứng dụng khác theo quy tắc này.
- Tuyệt đối không xóa volume, database, checkpoint, lịch sử chống trùng, file NAS hoặc dữ liệu ERP; không dùng docker system prune --volumes hay compose down -v.
- Nếu bản mới lỗi: giữ image cũ để khôi phục, chưa dọn. Sau dọn kiểm tra health và báo số bản đã dọn.
