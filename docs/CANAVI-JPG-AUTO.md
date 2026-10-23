# CANAVI: tự xuất JPG CMYK và AI — 22/10/2026

## Đang áp dụng
- [x] Đọc phiếu lệnh, maket và AI/PDF; gom đủ maket của các hồ sơ cùng một file/đợt yêu cầu.
- [x] Khi có AI và PDF cùng tên trong CANAVI, ưu tiên bản AI để giữ cấu trúc gốc, tránh xuất đôi. Vẫn đối chiếu preview PDF-compatible của AI với phiếu và maket.
- [x] Đọc PatternColor native trên bản sao AI: giữ hash, artboard, vị trí, tên pattern. Không sửa file nguồn.
- [x] Nhánh tự động hoa văn full túi: hỗ trợ1–2hoa văn, mỗi hoa văn tấm liền2mặt. Mặt sau xoay180°, không lật gương. Chọn vùng bao ngoài cùng pattern thay vì khung thành phẩm bên trong.
- [x] Khổ JPG sau co: ngang trừ2cm; cao>=70cm trừ5cm, cao<70cm trừ2.5cm. Không áp vào PET.
- [x] Tấm túi4góc L nhánh1cm. Vải mét để khách cắt quai:160×20cm, không co và không định vị. Chỉ tạo vải mét khi nguồn yêu cầu in quai/vải mét; túi có quai không đủ để tự thêm.
- [x] Giữ pattern/CMYK/ICC gốc, mở rộng vùng lặp, không kéo méo; AI giữ artboard tham khảo và tất cả artboard xuất.
- [x] Cùng file/hash/nhóm/đợt của các hồ sơ pattern chỉ xếp một job; marker của worker ngăn tự chạy lại khi kết quả không rõ.
- [x] Lưu CANAVI hoặc CANAVI HCM2/DESIGNER/{Tên mẫu}/REVIEW-...; preview chỉ ghi chú nội bộ Chatwoot.
- [x] Giữ luồng lên đơn ERP độc lập; module này không tạo/sửa đơn, không gửi khách hoặc RIP.

## Phải chuyển review
Thiếu phiếu/maket/file, sai phiên bản, trục vải không rõ, không chắc tấm liền, logo rời/cữ riêng, pattern khác giữa hai mặt, mã quai khác, khổ vải mét khách ghi khác mặc định, clipping phức tạp hoặc không có PatternColor native phù hợp. PDF có hoa văn đã bung thành quá nhiều nét vẫn cần review; không tuyên bố mọi PDF đều tự xuất được. Luồng JPG thông thường trước đây vẫn giữ riêng.

Xác nhận THOCAM42×92 là tấm liền chỉ được dùng làm quy tắc có ngữ cảnh tương đương; không suy mọi yêu cầu in2mặt thành tấm liền.

## Kiểm chứng
- 10 kiểm thử quy tắc đạt: đủ nguồn, khổ sau co, loại trừ sai pattern, không tự thêm mét, giữ no-mirror.
- Kiểm thử hàng đợi SQLite tạm:4panel, một job cho2hồ sơ cùng nguồn, không ERP/public.
- Đọc native THOCAM:2artboard,8vùng pattern; chuẩn hóa đúng4vùng40×42cm.
- Chạy xuất bằng module tổng quát:4JPG khớp SHA256 với4file THOCAM đã làm trước. Bản thử chỉ lưu cục bộ, không gửi thêm preview.
- Đã triển khai hub image `phucthanh-chatwoot-hub:canavi-native-auto-20261022` và Windows ArtworkInspector; worker đã nạp lại.

## Mã và vận hành
Hub: integrations/agent-hub/hub/{jpg_patterns.py,jpg_exports.py,artwork_checks.py} trong phucthanh_support.
Worker nguồn: U:/DESIGNER/agent/windows_artwork/{native_patterns.py,pattern_export.py,jpg_worker.py,worker.py}.
Worker chạy: C:/Users/Admin/AppData/Local/PhucThanh/ArtworkInspector.
Sao lưu: hub backups/canavi-native-auto-20261022; worker backup-canavi-auto-20261022.
Lỗi COM/hộp thoại: báo review; không tự Alt+F4/Enter mù vì có thể đóng tài liệu chưa lưu.
