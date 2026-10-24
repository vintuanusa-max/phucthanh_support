# Quy tắc đang áp dụng: chọn artwork PET theo artboard và maket
Cập nhật 24/10/2026. Đây là quy tắc hiện hành; thay thế cách gửi hàng trăm ảnh cụm theo lô cho AI.

## Quy trình tự động cho hồ sơ PET mới đủ điều kiện
1. Đọc nguồn AI/PDF, maket và yêu cầu khách. Phân biệt artboard (khổ trang) với artwork (hình cần in).
2. Bước khoanh vùng chỉ nhận ảnh toàn artboard tương ứng để tránh dùng tọa độ từ ảnh khác. Xác định vùng logo/chữ cần lấy; cùng hình ở nhiều góc nhìn không mặc định là nhiều mẫu.
3. Code lọc theo tọa độ và cấu trúc cha–con. Giữ nguyên nhóm chứa chữ/path/chi tiết trắng; không loại đối tượng chỉ vì là PathItem. Inventory nhiều đối tượng chỉ dùng để lọc bằng code, không gửi toàn bộ preview cho AI.
4. Chỉ gửi tối đa 12 ứng viên phù hợp sang bước đối chiếu chi tiết với đủ nguồn maket. Vượt giới hạn, vùng không rõ hoặc tọa độ không khớp: báo kiểm tra nội bộ, không quay lại quét hàng trăm cụm. Bộ khoanh vùng giới hạn 4 artboard và 8 ảnh nguồn; worker hiện vẫn yêu cầu nguồn PDF-compatible một trang.
5. Chọn đúng artwork và kích thước theo nguồn; giữ tỷ lệ, chữ và chi tiết trắng. PNG/TIFF cắt sát phần hình, giữ khoảng cách bên trong, nền trong suốt và kênh mực trắng. Không cữ, không trừ co, không lật gương. Quy tắc cữ/co thuộc JPG in túi, không áp vào PET.
6. Kiểm chứng PNG trước bước TIFF. Chống xuất lặp cùng bộ ID cụm và kích thước. Cache kết quả AI; lượt chưa rõ kết quả không tự gọi lại.
7. Lưu file trong DESIGNER của mẫu; đưa preview vào ghi chú NỘI BỘ Chatwoot để chủ xưởng duyệt. Không tự RIP hoặc gửi khách. Không tạo lại đơn ERP từ bước xuất file.

## Điều phối và giới hạn
Trang điều phối hiện ảnh artboard có khung vùng chọn, cụm artwork, kích thước, lý do chưa xuất và cảnh báo font. File nhiều đối tượng có thể vượt timeout đọc Illustrator; ảnh liên kết chưa nhúng, font thiếu hoặc nguồn không phù hợp phải được ghi rõ, không tự xem là đạt.

## Checklist xác nhận
- [x] Hub đang dùng artboard_regions_v5_partial; không còn vòng gọi maket_filter theo lô.
- [x] Chặn trên 12 ứng viên trước bước chọn chi tiết; giữ cụm cha và chi tiết trắng.
- [x] Kiểm thử tọa độ, cha–con và giới hạn ứng viên.
- [x] Thử thực tế GV2VB-100.10: 376 metadata → 2 ứng viên → chọn cụm 0.1.
- [x] PNG/TIFF 5,8 × 5,038 cm, 685 × 595 px; spot_1 có dữ liệu, alpha giữ nguyên.
- [x] Preview nội bộ Chatwoot hội thoại 10, tin 5547.
- [x] Nguồn code Hub và Windows worker đã lưu; kiểm tra lại bản đang chạy ngày 24/10/2026.

## Dấu vết lần thử
File: CANAVI/DESIGNER/FileinPETGV2VB-10010/versions/3b74594cbd512c0dea7e2869caa4ff255c44a0a1c497bcc53c104c02c71a5d17.
Luồng cũ đọc từng lô 24 cụm đã bị thay thế. Những lượt thử cũ bị hủy không được tự chạy lại. Các giới hạn trên là điều kiện dừng để kiểm tra, không phải cam kết mọi nguồn đều tự xuất thành công.

## Thông báo theo mẫu — 24/10/2026
Đã bỏ thông báo riêng của đề xuất DESIGNER, đối chiếu file nguồn, hồ sơ tổng hợp thành công và lỗi PET/native trực tiếp. Dữ liệu nguồn vẫn lưu và hiển thị source_checks trong điều phối. Bộ giám sát gom các lỗi cùng hồ sơ hiện hành thành một bản, Engine.effect chống gửi lặp; preview xuất cuối vẫn giữ. Không đọc riêng JXL trong artwork_checks; khi có AI/PDF dùng ảnh làm ngữ cảnh và không tạo thêm kiểm tra raster trong cùng hồ sơ. Bỏ qua hồ sơ cũ không còn hiện hành. Kiểm thử hai lỗi cùng mẫu -> một tin, quét lại -> không tin mới đã đạt.
SERE đã xuất riêng home resort theo xác nhận của chủ xưởng; preview nội bộ tin 5597, hội thoại 10. Phần serena RIVERSIDE thân túi thiếu nguồn đã ghi nội bộ. Không tự thay logo, không xác nhận toàn mẫu hoàn tất và không chạy lại phần đã xuất.

## 2026-10-24 — PET native: xuất từng phần
- [x] Đọc artboard trước, khoanh vùng; không gửi hàng trăm cụm cho AI.
- [x] `blocked_parts` ghi vị trí thiếu artwork/kích thước; không chặn vị trí đã đủ nguồn.
- [x] Kiểm chứng PNG chỉ theo vị trí đã chọn; vẫn chặn sai logo/chữ/font/kích thước của vị trí đó.
- [x] Gom thiếu nguồn theo hồ sơ; preview ghi rõ xuất một phần, không báo toàn mẫu hoàn tất.
- [x] Điều phối hiển thị phần cần bổ sung; parent đã chọn không bị báo worker kẹt giả.
- [x] Giữ khóa AI/child job/Chatwoot chống trùng; không tự phát lại hồ sơ cũ.
- [x] Kiểm thử phần đúng + phần lỗi, lỗi toàn nguồn, trùng artwork, trùng vị trí và sai tỷ lệ.
- Chỉ PNG/TIFF artwork: không cữ/co vải; nền trong suốt, mực trắng. Chưa RIP/gửi khách.
- SERE đã xuất home resort; phần serena RIVERSIDE thiếu nguồn ghi nội bộ. Không chạy lại file đã xuất.
- Phạm vi bản này: chọn artwork AI/PDF native PET; không thay đổi quy trình JPG.

## Quy trình hiện hành cho đơn mới — phần đủ nguồn xuất trước

Hai luồng độc lập:
1. **Lên đơn ERP:** đủ thông tin đặt hàng/số lượng thì xử lý tạo đơn Lên mẫu theo quy tắc và ánh xạ hiện có, kiểm tra chống trùng. Thiếu nguồn thiết kế không chặn luồng lên đơn. Luồng xuất file không tạo lại đơn ERP.
2. **Xuất file PET từ AI/PDF:** đối chiếu phiếu, maket và nguồn; đánh giá từng artwork/vị trí riêng. **Phần đủ nguồn và kích thước thì xuất trước**, kể cả khi vị trí khác còn thiếu. Phần thiếu không được đoán hoặc thay bằng logo khác: ghi rõ vị trí, lý do và thông tin cần bổ sung trong nội bộ Chatwoot và điều phối.

Mỗi phần xuất vẫn phải đúng artwork/phiên bản, chữ, chi tiết trắng, tỷ lệ và kích thước. Lỗi toàn nguồn như chưa xác định đúng mẫu hoặc công nghệ vẫn dừng để kiểm tra. Không có phần nào đủ nguồn thì chỉ báo cần xử lý, không tạo file giả. Preview ghi rõ xuất một phần và phần còn thiếu, không báo hoàn tất toàn mẫu.

Thông báo lỗi cần xử lý được gom theo hồ sơ mẫu hiện hành; chỉ gửi thay đổi có ý nghĩa hoặc preview mới. Giữ khóa chống xuất trùng, chống gọi AI trùng và chống gửi ghi chú lặp. Kết quả lần trước chưa rõ không tự gọi lại. File lưu trong DESIGNER; preview chỉ là ghi chú nội bộ Chatwoot chờ duyệt, chưa RIP/gửi khách.

### Checklist triển khai và dọn tồn
- [x] Tách luồng lên đơn khỏi luồng xuất file; bản sửa này không đổi logic ERP.
- [x] PET native xuất các vị trí đủ nguồn trước, tách danh sách thiếu `blocked_parts`.
- [x] Giữ kiểm chứng từng PNG trước TIFF; không bỏ kiểm tra vì xuất một phần.
- [x] Giữ nền trong suốt, mực trắng, cắt sát artwork và khoảng cách chi tiết; không cữ/co/lật gương trong PET.
- [x] Hiển thị phần thiếu trong điều phối và ghi chú nội bộ; chống báo lặp.
- [x] Kiểm thử phần đúng + phần lỗi, lỗi toàn nguồn, trùng artwork/vị trí và sai tỷ lệ đã đạt.
- [x] Đã dọn 151 hồ sơ tồn: 102 chờ kiểm tra và 49 chưa bắt đầu; đưa vào lịch sử, không xóa vật lý dữ liệu.
- [x] Đánh dấu `dispatch_archived_at`; `WorkflowControl.current()` trả false cho hồ sơ đã dọn để ngăn tự chạy lại.
- [x] Sao lưu SQLite trước khi dọn; giữ đơn ERP, tin Chatwoot, file đã xuất và dấu vết chống trùng.
- [x] Kiểm tra sau dọn: danh sách chờ 0, lịch sử 170, Hub health OK. Đây là số tại thời điểm dọn, đơn mới có thể làm tăng danh sách.
- [ ] Theo dõi một đơn mới thực tế đi hết luồng tự động sau bản sửa; không tự chạy lại 151 hồ sơ để thử.

Phạm vi xuất từng phần ở bản này là PNG/TIFF native AI/PDF. Không suy diễn rằng quy trình JPG đã được sửa theo cùng cơ chế. Các quy tắc JPG CMYK hiện có vẫn giữ nguyên.