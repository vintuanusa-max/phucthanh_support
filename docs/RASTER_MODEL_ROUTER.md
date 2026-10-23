# Bộ định tuyến ảnh — 22/10/2026

- [x] Gemini đọc ảnh artwork đã liên kết với hồ sơ/maket và kích thước in, chọn giữ nguyên / upscale / redraw / cần kiểm tra.
- [x] Giữ nguyên khi đủ nét; Real-ESRGAN scale=2, face_enhance=false khi cần tăng độ phân giải.
- [x] Phục dựng/upscale cần nhân viên hỏi file + khách xác nhận không có (hoặc chủ xưởng yêu cầu rõ riêng mẫu thử).
- [x] SDXL ControlNet Canny chỉ cho minh họa không chữ, không tự đoán chữ/số. Không fallback sang Kontext.
- [x] BiRefNet tách nền khó và kiểm tra alpha/nét trắng; tối đa một bước phục dựng + một bước tách nền, không thử nhiều model liên tiếp.
- [x] Receipt trước POST, không tự gọi trả phí lần hai khi trạng thái chưa rõ. Kiểm tra chữ/số và hình trước khi xếp xuất PNG/TIFF.
- [x] Giữ DESIGNER/{Tên Mẫu}/versions/{job_id}, no mirror, white spot không contract; màu contract 1px; chỉ private Chatwoot, không ERP/RIP/gửi khách.
- [x] 8 mock tests đạt (provider và router).
- [ ] Schnell không bật trong tuyến phục dựng; nhánh sáng tạo mới chưa triển khai vì cần intent sáng tạo được xác nhận, không được suy từ câu không có file.
- [ ] Thử CẦN THƠ v3: Gemini chọn upscale, đọc đúng CTY TNHH BVTV VN / CẦN THƠ / 0919 377 886 - 0939 873 459. Real-ESRGAN prediction f2ektd28adrgc0d1c28sffz43c succeeded, chỉ một POST. Chưa tải/kiểm tra/xuất TIFF vì replicate.delivery phân giải về 127.0.0.1 trên cả Windows và Docker. Không sửa DNS hoặc gọi model lần hai. Cần kiểm tra cấu hình mạng; bản v2 cũ giữ nguyên.

Giới hạn: ảnh sản phẩm chưa có artwork riêng vẫn review; câu trả lời không file phải nằm trong hồ sơ hiện tại và nối đúng nguồn. Không khẳng định tự xử lý mọi ảnh hoặc mọi cuộc hội thoại.

22/10: Sau khi chủ xưởng bật WARP, đã tải lại prediction f2ektd28adrgc0d1c28sffz43c, không POST lần hai. Kiểm tra trực tiếp chữ/số với ảnh gốc (không gọi Gemini bước phục hồi). V3 PNG 1422x768, cao6.5cm, TIFF alpha+spot_1 đã kiểm tra. Worker trước đó đã dừng, được khởi động lại. Job 9c5d3d7db8ed36a8abc5b8e6e325897254860340c71be57adc707147ddb0c6c5 done; private Chatwoot #4041 có3attachments. NAS A THUC/DESIGNER/CAN_THO/versions/{job}. Không ERP/RIP/gửi khách. Kết nối phụ thuộc WARP đang bật; chưa xác nhận hoạt động khi tắt WARP.
