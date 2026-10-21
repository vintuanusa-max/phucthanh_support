# CANAVI: tự xuất JPG CMYK và AI — 19/10/2026

## Luồng đang bật
- [x] Hồ sơ mới CANAVI / CANAVI HCM2 → đọc PDF/AI, đối chiếu phiếu lệnh và maket.
- [x] Gemini chọn object IDs và đề xuất artboard/cữ có dẫn nguồn; không dùng thông số mẫu cũ cho đơn khác.
- [x] Kiểm tra khổ, trục ngang/cao, số mặt, đối tượng, cữ, loại in. Thiếu hoặc mâu thuẫn → Open + ghi chú nội bộ Chatwoot.
- [x] Worker Windows mở bản sao bằng Illustrator; sao chép đối tượng gốc, lưu AI thật có maket tham chiếu và đủ artboard in. Nền cùng màu liên kết process swatch để sửa lại.
- [x] Xuất JPG CMYK 300 dpi từ PDF-compatible AI, không chuyển vòng qua RGB; giữ ICC CMYK nguồn. PNG xem trước riêng là RGB để xem trên Chatwoot.
- [x] Mặt túi có 4 dấu L nhánh1cm; vải mét không định vị.
- [x] Lưu AI/JPG/preview/plan/report trên NAS, kiểm tra hash; Gemini kiểm tra lại bố cục output với nguồn trước khi ghi chú chờ duyệt.
- [x] Queue bền vững + marker đã bắt đầu + receipt đã xác minh. Nếu gián đoạn xuất, chuyển kiểm tra, không tự xuất lặp. Ghi chú dùng event ID cố định.
- [x] Dùng worker ArtworkInspector tự khởi động Windows sẵn có.
- [ ] Chủ xưởng duyệt file từng đơn trước khi đưa in. Không có thao tác RIP hoặc gửi khách trong module này.

## Quy tắc khổ
Chỉ JPG chuyển nhiệt: khổ trước co trừ ngang2cm; cao<70 trừ2,5cm; cao>=70 trừ5cm. Khổ đã xác nhận sau co không trừ tiếp. PNG/TIFF PET không áp độ co này.
Cữ đo từ mép khổ sau co; không tự áp cữ9cm hoặc khổ của mẫu khác. Hai miếng riêng không xoay; vải liền cần nguồn xác nhận mới xoay180.
Vải mét ngang160cm; cao20cm chỉ khi được xác nhận cho mẫu màu trơn đó. Hoa văn cần xác minh bước nối, hiện chuyển duyệt.

## Phạm vi hỗ trợ và giới hạn
Tự xuất khi file PDF-compatible AI/PDF một trang, một profile CMYK, ảnh CMYK hoặc vector path process CMYK có thể ánh xạ duy nhất sang đối tượng Illustrator. Giữ clipping chữ nhật bao trọn artwork; clipping phức tạp/cắt nội dung, blend/transparency, chữ sống, RGB/spot khác, nhiều trang/artboard nguồn, kích thước không chắc → ghi chú kiểm tra.
AI giữ giá trị CMYK nguồn. JPG là raster8bit/nén JPEG nên có lượng tử hóa khoảng1/255 ở màu phẳng và anti-alias tại biên; không coi giá trị pixel JPG là số phần trăm CMYK native. Profile thiếu hoặc nhiều profile không tự đoán.
Bản đầu chỉ nhận hồ sơ tạo sau mốc bật, không phát lại hàng loạt hồ sơ cũ. Đơn không đủ file sẽ nằm ở ghi chú thiếu nguồn của hồ sơ thiết kế.

## Vị trí
- Mã hub: integrations/agent-hub/hub/jpg_exports.py, jpg_plan.py, artwork_checks.py, app.py trong phucthanh_support.
- Mã worker: U:\DESIGNER\proposal\canavi_jpg\jpg_worker.py.
- Runtime: C:\Users\Admin\AppData\Local\PhucThanh\ArtworkInspector.
- NAS (từ 20/10/2026): {CANAVI hoặc CANAVI HCM2}\DESIGNER\{ma_mau}\REVIEW-{YYYYMMDD}-{job_id_12}. Kho DESIGN_BRIEFS dành cho hồ sơ phân tích; bản xuất mới nằm trong DESIGNER theo mã mẫu. Bản đã xuất trước thay đổi giữ nguyên đường dẫn và lịch sử, không tự di chuyển hay xuất lại.
- API nội bộ có xác thực: GET /adapters/{account}/jpg-exports; POST /adapters/{account}/jpg-exports/{id}.
- SQLite jpg_exports: planning → queued → exporting → publishing → done; review/uncertain cần đối chiếu.

## Kiểm chứng
15 kiểm tra quy tắc/queue đạt; kiểm thử native MELANO đạt: AI4artboard (1tham chiếu+3in), front/back41x36,5cm; vải mét160x20cm, JPGCMYK300dpi và ICC nguồn. Đây là kiểm chứng kỹ thuật và preview, chưa phải kiểm màu máy in vật lý.

### Nghiệm thu trọn luồng
- Job thử da4beb1f757bc71246caae4a3c77843e5bcbb3bdfc65c2a4fc4c255565d80bbd: Gemini tự chọn đúng image IDs p1-o1/p1-o2, nền p1-o167; worker xuất3JPG+AI4artboard, lưu NAS, kiểm chứng độc lập pass=true.
- Chatwoot CANAVI hội thoại10: ghi chú3041 private=true kèm3preview. Tên mẫu có TEST_AUTO, không phải đơn sản xuất mới.
- Lần thẩm định đầu thiếu quy tắc co ở prompt đã giữ review; sau bổ sung quy tắc chỉ kiểm chứng lại receipt, không xuất lặp. Ghi chú3040 giữ làm lịch sử;3041 là kết quả mới.
- Căn giữa được tính bằng code theo khổ SAU CO; không để model tự lấy khổ thô để tính x.
- Các crop đối tượng có ID được đưa vào bước chọn artwork. Hình clipping phức tạp hoặc không ánh xạ duy nhất vẫn chuyển duyệt.
