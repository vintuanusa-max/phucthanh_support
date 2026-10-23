# AN NGUYEN — MET và JPG (22/10/2026)

- [x] Chủ xưởng xác nhận MET cho đơn in theo tấm; giữ nguyên số tấm, không quy đổi mét dài.
- [x] Quy tắc chỉ áp ID Zalo g5402324928935037742; không đổi các nhóm khác, không ghi đè mã khác đã xác định.
- [x] Tin khách số lượng tấm được đối chiếu với từng dòng đơn; không lấy kích thước trong tên file làm số lượng.
- [x] Đã đổi tên 5 JPG thử thành tên PDF gốc bỏ dấu; giữ SHA256, không render lại.
- [x] Hub nhận PDF artwork đã đối chiếu đúng mẫu, không có conflict; lên lịch original_pdf_v1.
- [x] Windows xuất toàn trang gốc 300dpi CMYK/ICC. Không trừ co, không lật, không thêm định vị.
- [x] Tên JPG bỏ dấu; nhiều trang thêm page_N. Lưu DESIGNER/{tên file}/REVIEW-{ngày}-{id}.
- [x] Khóa nguồn theo nhóm/lượt/sha256, job durable; lỗi gửi ghi chú không tự gửi lại khi chưa rõ kết quả.
- [x] Preview private Chatwoot; chưa RIP/gửi khách. Gốc PDF vẫn giữ nguyên.
- [x] 7 kiểm thử quy tắc; renderer thực tế cho hash JPG bằng bản đã kiểm chứng; từ chối maket chưa xác định.
- [ ] Chứng kiến một đơn mới thực tế đi trọn tự động sau triển khai. Không tạo đơn giả hoặc replay đơn thật để thử.

Giới hạn: nhánh AN NGUYEN này nhận PDF có profile CMYK duy nhất. AI chưa được tự xuất theo nhánh này; ghi chú kiểm tra. Duyệt/copy JPG của CANAVI yêu cầu AI gốc vẫn giữ nguyên, không áp cơ chế đó cho PDF AN NGUYEN. Bản PDF có khổ trang khác tên file giữ khổ trang và cần người duyệt.

## Cập nhật AI 22/10
- [x] AI PDF-compatible nhận vào luồng; Illustrator mở bản sao, xác minh CMYK và số/kích thước artboard.
- [x] Giữ file AI nguồn, tên JPG gốc bỏ dấu; nhiều artboard thêm page_N.
- [x] Từ chối ảnh liên kết ngoài/chữ sống chưa xác minh; profile thiếu hoặc artboard lệch → review nội bộ.
- [x] Kiểm thử native AI 2 artboard 5,08×7,62 và 7,62×5,08 cm, hai JPG CMYK 300 dpi; nguồn không đổi.
- [ ] Chờ AI khách thật đầu tiên trong nhóm; hiện kho không có AI để kiểm chứng thực tế.
Giới hạn trước đây AI chưa hỗ trợ được thay bằng hỗ trợ có điều kiện nêu trên. Không tự RIP/gửi khách.

## Duyệt JPG 22/10
- [x] Duyệt hỗ trợ bản gốc PDF/AI đã xác minh, không chỉ AI CANAVI.
- [x] Prefix theo ID nhóm: AN NGUYEN g5402324928935037742 và INJAE g3427098896227768665 -> NEO_; nhóm khác -> MNT_.
- [x] Tên gốc bỏ dấu, tránh thêm prefix hai lần; nhiều artboard có suffix page/front/back.
- [x] Cùng tên/hash bỏ qua; khác hash từ chối trước copy, không ghi đè; giữ DESIGNER.
- [x] Đã đưa 5 JPG cũ đúng đơn 317/318/319/320/325 vào danh sách chờ chủ xưởng duyệt. Không bấm duyệt thay người dùng.
- [x] Kiểm thử copy trên thư mục tạm: bản gốc giữ nguyên, lặp lại không copy, xung đột bị chặn. TIFF không đổi quy tắc tên. Chưa RIP/gửi khách.
