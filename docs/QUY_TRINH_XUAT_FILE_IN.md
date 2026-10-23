# Quy trình xuất file in — tóm tắt hiện hành
Cập nhật23/10/2026 từ tài liệu triển khai; không chạy xuất mới khi cập nhật tài liệu.

## Nhận nguồn và chọn artwork
1. Lấy đủ maket +tin kích thước +PDF/AI/ảnh/file tải từ link được phép. Lưu ID nguồn/hash/phiên bản. Link cần quyền hoặc chỉ là trang xem → ghi thiếu file; Canva chưa có bằng chứng đầu nối xuất hoàn chỉnh.
2. Ghép đúng mẫu/đơn, không chặn ERP nếu file chưa làm được.
3. PDF/AI: Illustrator đọc cụm đối tượng; AI đối chiếu maket chọn cụm. Điều phối8096 hiển thị cụm để chủ xưởng chọn lại. Font/đối tượng/kích thước mâu thuẫn → review; không tự thay font rồi coi như đúng.
4. Ảnh artwork riêng đủ rõ đi nhánh raster. Ảnh nằm trên sản phẩm không tự coi toàn bộ sản phẩm là artwork để xuất.
5. Chỉ vẽ lại bằng OpenAI khi có câu hỏi file của nhân viên và đúng khách xác nhận không có file, nguồn khớp. Receipt/cache chống gọi phí trùng; sai chữ/số hoặc timeout giữ review. Nhánh đã có mã và kiểm thử; vẫn cần theo dõi ca hội thoại mới end-to-end.

## Quy tắc xuất
| PET PNG/TIFF | JPG chuyển nhiệt |
|---|---|
| Cắt sát alpha ngoài, giữ khoảng cách nội bộ | Theo artboard/quy cách loại sản phẩm |
| Giữ đúng tỷ lệ/kích thước artwork | Giữ màu CMYK/ICC gốc, lưu AI đủ artboard khi tuyến có AI |
| PNG trong suốt, TIFF spot mực trắng | CANAVI túi áp khổ sau co; không áp nhầm cho PET |
| Trắng không contract; màu khác contract1pixel | Vải mét không định vị4góc |
| Không cữ, không bù co, không lật gương | Không lật gương; túi liền hai mặt mới xoay sau180° |

Ưu tiên kích thước khách/maket đã xác nhận. Thiếu kích thước ở vị trí nón đã nhận diện: mạc/mặt trước cao6,5cm; hông ngang tối đa7cm, giữ tỷ lệ. Không áp mặc định nón cho túi/vị trí chưa rõ.
CANAVI: khổ vải cao<70cm trừ ngang2/cao2,5cm; >=70cm trừ ngang2/cao5cm. Khổ đã xác nhận sau co không trừ lần nữa. Túi liền2mặt: cữ theo maket+0,5cm theo quy tắc đã duyệt, sau180°; túi ghép2miếng không áp kiểu liền. Artwork giữ tỷ lệ; cữ lệch phải ghi rõ.

## Kết quả và duyệt
- Lưu theo khách: DESIGNER/{Tên Mẫu}/versions/{job_id}; giữ nguồn và bản cũ. DESIGN_BRIEFS phục vụ hồ sơ/ngữ cảnh, không phải nơi người dùng tìm file sản xuất cuối.
- Preview chỉ ghi chú nội bộ Chatwoot, liên kết Tiến trình file in trong ERP; so sánh mẫu nguồn/bản xuất.
- Nút Duyệt file là phê duyệt bản xuất để copy ra folder khách, khác với câu khách duyệt mẫu gửi File In. Giữ gốc DESIGNER/AI, không ghi đè bản khác, không copy trùng.
- JPG theo tên file gốc bỏ dấu; tiền tố copy NEO cho AN NGUYEN/INJAE, MNT cho nhóm khác theo cấu hình đã yêu cầu. Không tự đổi quy tắc đặt tên TIFF sang JPG.
- Không tự RIP hoặc gửi khách. Nhập yêu cầu chỉnh sửa ở điều phối không có nghĩa đã có editor tự sửa mọi màu/chi tiết.

## Khi kẹt
Kiểm tra worker Windows, Adobe sẵn sàng/hộp thoại/font, nguồn NAS, chọn cụm, bước AI, bước xuất, bước đăng preview. Không bấm chạy lại job uncertain hoặc gọi lại model trả phí khi chưa đối chiếu kết quả cũ.
Chi tiết: [PET](PNG-TIFF-ARTWORK-RULES.md), [CANAVI](CANAVI-JPG-AUTO.md), [OpenAI](OPENAI_REDRAW.md), [tiến trình/duyệt](PRINT_FILE_PROGRESS.md), [điều phối](SYSTEM-MONITOR.md), [chọn cụm](ILLUSTRATOR-ARTWORK-SELECTION.md).
