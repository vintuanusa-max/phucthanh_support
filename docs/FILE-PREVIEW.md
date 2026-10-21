# Bản xem PDF/AI cho đơn hàng và yêu cầu khách

Ngày triển khai: 20/10/2026.

- [x] DH-2610-275: thêm JPG của `6 panel cap IBC.pdf` vào Ảnh khách đặt, giữ đơn 110 nón.
- [x] Bộ render PDF và AI có PDF-compatible: đọc bản gốc theo SHA256, đầy đủ trang, không sửa file gốc.
- [x] Gắn bản xem vào tổng hợp bằng chứng khi lên đơn mới.
- [x] Hàng đợi riêng cho yêu cầu mở/xem file của khách; chỉ xét tin sau thời điểm bật.
- [x] Gửi bản xem về cùng nhóm Zalo/WhatsApp qua phiên Desktop; ghi kết quả nội bộ Chatwoot.
- [x] Không phát lại tác vụ đã claim; gián đoạn/không rõ kết quả chuyển nhân viên, không tự gửi lần hai.
- [ ] Kiểm chứng nhận ảnh thực tế với một yêu cầu xem file mới từ khách.

## Chọn đúng nguồn

Ưu tiên PDF/AI cùng tin; tiếp theo file trích dẫn được nhận diện bằng ID. Nếu không có trích dẫn, chỉ nhận một file duy nhất từ cùng người gửi, cùng nhóm, trong 10 phút trước hoặc 60 giây sau câu hỏi. Chờ ít nhất 60 giây trước khi xử lý. Nhiều file, không có file hoặc nguồn sửa/thu hồi: cần đối chiếu thủ công. Không tìm theo tên nhóm ở nơi khác.

Ví dụ: “file này in gì”, “mở giùm file này”, “xem giúp file PDF”, “không mở được trên điện thoại”. Không dùng lời đặt hàng hay duyệt in để kích hoạt gửi preview.

## Phạm vi

Chỉ yêu cầu của khách ở nhóm được chính sách cho phép. Không nhận tin bot, tài khoản máy, nhân viên nội bộ hoặc nhóm theo dõi lỗi File In. Ngoại lệ trả khách này chỉ gửi bản xem file với lời dẫn cố định; phản hồi AI khác vẫn là ghi chú nội bộ. Viber chưa có đường gửi ảnh preview đã xác minh, nên chuyển kiểm tra nội bộ.

Giới hạn: file 32 MB, tối đa 8 trang; AI phải có nội dung PDF-compatible. Vượt giới hạn, AI không tương thích hoặc file mã hóa: nhân viên mở bằng phần mềm gốc. Không tự RIP, không sửa thiết kế, không đổi màu file in. JPG xem trước dùng RGB để xem trên điện thoại; quy tắc JPG CMYK sản xuất CANAVI không thay đổi.

## Lưu trữ

Ảnh gửi khách: thư mục cùng tháng với originals, tại `previews/<sha256 đầu 20>-v1/page-NNN.jpg` và `all-pages.png`.
Bằng chứng đơn: giữ thư mục `orders/<mã hồ sơ>/evidence-<hash>`.
Nhật ký gửi Windows: `ArtworkInspector/preview-journal`. Hàng đợi Hub: bảng `file_previews`, cutoff bảng `file_preview_meta`.

## Mã

Hub: `hub/document_preview.py`, `hub/file_previews.py`, tích hợp `hub/evidence_document.py`, `hub/engine.py`, `hub/app.py`.
Windows ArtworkInspector: `preview_worker.py`, `preview_transport.py`, `preview_photo_transport.cjs`, `preview_renderer.cjs`, `send_preview.mjs`, `cdp.mjs`.
Không sửa guard nhóm của bộ chuyển duyệt in đang chạy; transport xem file là bản riêng.
