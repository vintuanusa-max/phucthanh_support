# PET tự xuất bản chờ duyệt — 19/10/2026

## Phạm vi
Chạy trên hồ sơ DESIGNER mới, thuộc các nhóm đã được phép đọc và lập hồ sơ. Chỉ nhánh PET; không tạo/sửa đơn ERP. Không phát lại lịch sử trước mốc `pet-exports/enabled-at`.

1. Đọc nguồn đã lưu NAS và kiểm SHA256.
2. Gemini đối chiếu phiếu, tin và maket; chọn object ID riêng từng mặt, mã đơn, kích thước và nguồn xác nhận số đo. Tên file có PET chỉ là dấu hiệu tìm ứng viên, không đủ xác nhận loại in.
3. Renderer lấy nét vector hoặc một ảnh nhúng có alpha từ PDF/AI tương thích. Không xóa màu kem/trắng bằng ngưỡng màu. Chặn clipping/transparency group phức tạp, chữ sống hoặc cụm ảnh-vector trộn chưa hỗ trợ.
4. Xuất PNG RGBA 300dpi, giữ tỷ lệ. Gemini kiểm tra độc lập bản tách với nguồn/maket. Kích thước cm trong PDF được phép scale theo số đo khách xác nhận; không tự lấy kích thước trang làm khổ in.
5. Worker Windows chạy Photoshop `IN_PHUC_THANH_ACTIONS/WHITE_1` trên bản PNG riêng. Save TIFF có `transparency`, `alphaChannels`, `spotColors`.
6. Mở lại TIFF kiểm `spot_1/SPOTCOLOR` có mực, khổ/DPI; kiểm TIFF 5 samples gồm alpha + spot, so alpha TIFF với PNG từng pixel.
7. Lưu NAS `{nhóm}/DESIGN_BRIEFS/PET_AUTO/{job_id}/`, kèm manifest liên kết nguồn, hash, đối tượng và số đo. Tên `{mã}_font.png/.tiff`, `{mã}_back.png/.tiff`. Job khác dùng thư mục khác, không ghi đè.
8. Đính kèm PNG/TIFF vào ghi chú PRIVATE Chatwoot để chủ xưởng duyệt. Chưa RIP, không chép thư mục watch/in, không gửi khách.

## Khi chưa rõ
- Thiếu số đo, mã, mặt in, mâu thuẫn A4/maket hoặc chưa xác định đúng nguồn: phiếu `review` và ghi chú nội bộ, mở hội thoại.
- JPG/ảnh mockup chưa tách nền, AI không có PDF tương thích, Office hoặc cấu trúc PDF chưa hỗ trợ: báo cần kiểm tra; không giả vờ đã tách đúng.
- Nhận diện thị giác là bước kiểm tra tự động, vẫn cần chủ xưởng duyệt trước sản xuất. Không cam kết chọn đúng mọi file.

## Chống lặp và phục hồi
- Một queue row theo artwork-check ID; mốc thời gian xét theo ngày tạo hồ sơ gốc.
- SQLite: `planning → queued → exporting → publishing → done`; nhánh thiếu dữ liệu `review`.
- Photoshop: ghi `started.json` trước action, `verified.json` sau kiểm chứng. Khởi động lại thấy started nhưng chưa verified: không chạy lại action, ghi chú kiểm tra.
- Upload lặp chấp nhận đúng hash/nội dung; khác nội dung bị chặn.
- Đăng Chatwoot dùng effects key `pet-files:{id}`. Kết quả không rõ giữ `uncertain`, không tự đăng lại. Không tự gửi vào nhóm thật.

## Mã và vận hành
- NAS `U:\DESIGNER\pet\auto\hub`: `pet_exports.py`, `pet_render.py`, hooks vào `artwork_checks.py`, `app.py`, `clients.py`.
- Hub runtime `/app/hub`; queue `/data/hub.sqlite3`; artifact `/data/pet-exports`.
- Windows `C:\Users\Admin\AppData\Local\PhucThanh\ArtworkInspector\pet_worker.py`, gọi từ `worker.py`, dùng launcher Startup hiện có. Photoshop cần hoạt động được trong phiên Windows đăng nhập.
- API adapter có xác thực: GET `pet-exports`; GET PNG; PUT TIFF; POST kết quả. Worker chỉ gọi localhost, không nhận lệnh shell từ hồ sơ.
- Không dùng hàm workflow cũ có copy RIP/AUTORIP.

## Checklist kiểm chứng
- [x] Renderer giữ file nguồn, alpha và kiểm hash/kích thước.
- [x] Chặn thiếu bằng chứng số đo, mặt trùng, mã/tên file không hợp lệ.
- [x] Không phát lại hồ sơ cũ; upload/complete lặp không đăng thêm ghi chú.
- [x] API yêu cầu xác thực và đúng tài khoản job.
- [x] Hai mặt TB1VB-EC.10 đã qua Photoshop thật, giữ alpha đúng từng pixel và kênh trắng.
- [x] Ca Gemini không chắc artwork/mockup chuyển review thay vì xuất sai.
- [x] Gemini thật chọn và thẩm định ca giả lập đủ dữ liệu, đi tới queued.
- [x] Triển khai worker theo Startup hiện có và nạp 4 API PET có xác thực; ba adapter trả HTTP 200.

## Giới hạn hiện hành
Tối đa 2 mặt/job, 45 triệu pixel/mặt, 64 MB/TIFF. Không tự tách ảnh phẳng/màu nền, không tự vẽ lại. Nhiều phần in quai/hông/đáy hoặc file phức tạp chuyển người kiểm tra. Quy tắc co vải và JPG CMYK là nhánh chuyển nhiệt riêng.
