# Quy tắc chung xuất PNG/TIFF

Chủ xưởng xác nhận ngày 23/10/2026. Áp dụng cho mọi đơn PNG/TIFF, không phụ thuộc khách/nhóm.

1. Chọn đúng artwork và đúng phiên bản nguồn trước khi xuất.
2. Cắt sát vùng alpha có hình ở mép ngoài; không để khung nhóm/artboard rỗng tạo cữ trên/dưới/trái/phải.
3. Không xóa khoảng trống bên trong artwork, không dồn hoặc di chuyển các chi tiết. Giữ nguyên vị trí tương đối trong cụm.
4. Sau khi cắt, chuẩn hóa đúng kích thước in đã xác định; scale đồng đều, giữ tỷ lệ phần có hình. Không ép khớp tỷ lệ khung rỗng cũ. Kiểm tra kích thước vật lý theo pixel/DPI, dung sai làm tròn tối đa 0,04 cm.
5. PNG nền trong suốt; không xóa phần trắng thật của artwork.
6. TIFF có kênh mực trắng: phần màu trắng không contract; phần màu khác contract 1 pixel theo workflow đã duyệt.
7. Không lật gương, không bù co vải, không định vị góc, không cảnh báo cữ túi trong PNG/TIFF. Cữ bố trí chỉ thuộc JPG in túi.
8. Thiếu hoặc mâu thuẫn artwork/kích thước/font thì ghi rõ để kiểm tra, không tự đoán.
9. Lưu bản gốc và kết quả trong DESIGNER, chống xuất trùng; preview ghi chú nội bộ Chatwoot để chủ xưởng duyệt. Chưa RIP/gửi khách.

## Bằng chứng triển khai
Nhánh Illustrator native đã cắt alpha và kiểm chứng với JOSEON: PNG 2835×2526px, alpha_bbox (0,0,2835,2526), TIFF hoàn tất, ghi chú nội bộ #5093. Các nhánh khác phải tuân chuẩn này; tài liệu không thay cho việc kiểm chứng từng nhánh xuất.
