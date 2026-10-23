# Sáu phần hoàn thiện luồng đơn hàng và thiết kế — 21/10/2026

## Ràng buộc giữ nguyên
Đủ thông tin: tự tạo ERP trạng thái Lên mẫu; thiếu mã hàng: Chờ mã; thiếu tên: ERP đặt tên. Giữ chống phát lại theo ID nguồn; đối chiếu đơn mới trong ngày, tìm đơn đặt thêm trong 3 ngày. File và phản hồi AI chỉ ghi chú nội bộ Chatwoot. Không RIP, không gửi khách. Việc xuất file không đồng nghĩa đã được duyệt.

## Thứ tự triển khai và tiêu chí nghiệm thu
1. Theo dõi xuyên suốt từng hồ sơ: nối đúng ID hồ sơ → lượt tiếp nhận → ERP → PET/JPG; không nối chỉ bằng tên nhóm. Hiển thị trạng thái độc lập, tránh coi có đơn là có file. API đọc có xác thực; không phát lại tác vụ.
2. Cảnh báo dịch vụ/hàng đợi: heartbeat riêng bộ đọc, hub, ArtworkInspector; phân biệt không có tin mới với mất heartbeat. Cảnh báo có thời gian, bước kẹt, khử trùng; thông báo phục hồi. Không tự chạy lại tác vụ uncertain.
3. Bổ sung ngữ cảnh: gắn tin mới bằng ID trích dẫn/hồ sơ/mẫu và người gửi; lưu nguồn, phiên bản trước/sau. Nếu nhiều mẫu phù hợp, ghi nội bộ yêu cầu chọn. Không tự lấy số lượng hay kích thước mẫu khác.
4. Phiên bản file: mã hồ sơ + vị trí in + phiên bản + SHA256; không ghi đè file đã duyệt. Phân biệt bản mới nhất, bản đã duyệt, bản hết hiệu lực. Tin bổ sung làm bản cũ cần duyệt lại, không tự RIP.
5. Quy tắc sản phẩm: PET nón, PET túi, JPG túi, vải mét là các cấu hình riêng. PET không trừ co; giới hạn cao 6,5 cm chỉ dùng phạm vi nón đã thống nhất. JPG trừ co theo chiều cao vải, CMYK gốc, AI đủ artboard; vải mét không có định vị. Mực trắng giữ nguyên, phần màu khác contract 1 pixel.
6. Lỗi dễ xử lý: mã lỗi ổn định + bước lỗi + nguồn + thông tin thiếu/mâu thuẫn + hành động cần làm. Không đưa token/khóa vào ghi chú; không chỉ báo ValueError. Thử các lỗi file thiếu, kích thước mâu thuẫn, phần mềm bận, kết quả gửi chưa rõ.

## Checklist triển khai
- [x] Ghi kế hoạch, tiêu chí và ràng buộc sáu phần.
- [x] Viết bộ tổng hợp trạng thái chỉ đọc theo ID hồ sơ (phần 1).
- [x] Kiểm thử bộ tổng hợp với hồ sơ cùng nhóm nhưng khác mẫu, file chưa duyệt, bảng thiếu.
- [x] Tích hợp API có xác thực và kiểm tra trên hub đang chạy.
- [ ] Phần 2: heartbeat, cảnh báo kẹt và khử trùng thông báo; kiểm thử dừng/phục hồi giả lập.
- [ ] Phần 3: cập nhật hồ sơ từ tin bổ sung; kiểm thử chéo mẫu và sửa thông tin cũ.
- [ ] Phần 4: quản lý phiên bản và duyệt; kiểm thử không dùng nhầm bản cũ.
- [ ] Phần 5: tách quy tắc sản phẩm; kiểm thử PET không co và JPG ngưỡng 70 cm.
- [ ] Phần 6: lý do lỗi và hướng xử lý; kiểm thử không lộ dữ liệu xác thực.
- [ ] Triển khai, kiểm tra luồng thật chỉ nội bộ; ghi bằng chứng từng phần.

Chưa đánh dấu hoàn thành phần nào chỉ dựa trên việc đã viết mã. Giữ nhật ký kiểm thử và triển khai riêng.

## Bằng chứng phần 1
API GET /workflow/status có xác thực quản trị, chỉ đọc. Đã kiểm tra 100 hồ sơ trên hub ngày 21/10/2026, HTTP 200. Kiểm tra giả lập: nối đúng ID, không suy ra duyệt từ done, không phát hành file. Image workflow-status-20261021. Chưa có màn hình tổng hợp hoặc thao tác duyệt; các phần 2–6 chưa triển khai trong đợt này.


## Được thay thế về cách tổ chức nghiệp vụ
Theo yêu cầu mới, dùng HAI_LUONG_DON_HANG_VA_FILE_MAU.md làm kế hoạch/checklist hiện hành. Sáu phần kỹ thuật giữ phía sau hai luồng, xem bằng chứng và giới hạn trong tài liệu mới; không dùng các ô trạng thái cũ phía trên làm kết luận hiện tại.
