# PET — chọn đủ artwork và phục hồi nguồn PDF (23/11/2026)

Áp dụng cho hồ sơ mới theo cấu trúc nguồn, không theo tên Thùy Đinh/KIM OANH. Bản đang chạy đã được đối chiếu; cập nhật Git này không phát lại hồ sơ cũ.

## Quy tắc đã áp dụng
- Giữ thứ tự lớp Illustrator theo đường dẫn object dạng số, không theo thứ tự AI trả về. Chữ màu không bị lớp hiệu ứng trắng che.
- Giữ các Path/CompoundPath rời đủ điều kiện trong danh sách ứng viên cùng Group; không tự chọn mọi vật thể giao vùng. Giữ bộ lọc chú thích, nền sản phẩm và khóa chọn trùng cha/con.
- Cho AI xem cả artboard, ảnh cận vùng logo và preview candidate. Nhận chỉ dẫn sửa cho đúng lượt; giữ đủ chi tiết/nền trắng thuộc logo. AI vẫn có thể bỏ sót: preview cần được đối chiếu, không bảo đảm 100%.
- Chỉ PET native scan PDF bị lỗi liên kết `must be embedded` mới được nhập lại bản PDF tạm. AI gốc, lỗi khác và nhánh kiểm tra JPG không tự dùng fallback này.
- Bản tạm bỏ PieceInfo chỉnh sửa Illustrator hỏng; giữ nội dung trang. Với UserUnit khác1, quy đổi content và page boxes rồi đặt UserUnit1. Kiểm tra khổ, rotation và pixel trang với nguồn trước khi dùng; sai thì dừng có lý do.
- Dấu `pdf_page_reimport` theo candidate tới xuất PNG và AI nhiều artboard. Không trộn object của hai cách nhập. Giữ SHA nguồn gốc, kiểm tra loại/bounds object; không ghi đè nguồn.
- Không thay đổi mực trắng thích ứng, co thích ứng, CROPT hoặc quy tắc ERP. Bản thử dùng internal_only, chưa RIP/gửi khách.

## Bằng chứng
- Thùy Đinh: PNG/TIFF/AI hoàn tất, kiểm tra đủ Power100, tia sét và hiệu ứng trắng. Hồi quy152 phương án giữ IDs/kích thước;201 bản quét giữ các group cũ.
- KIM OANH: hai PNG/TIFF (mặt trước và vành), một AI gồm artboard nguồn+2 artboard xuất. Mặt trước chọn thêm nền trắng rời sau đối chiếu thực tế. Giữ DH-2611-230.
-333 bản quét cũ vẫn dùng nguồn cũ; script Adobe render không đổi. PDF KIM OANH trước/sau xử lý khớp pixel. Đây là hồi quy dữ liệu và kiểm tra hai hồ sơ thực tế, không phải xuất lại toàn bộ lịch sử.

## Triển khai và checklist
- [x] Hub native_auto và worker native_local/native_worker đã áp dụng trước lượt commit.
- [x] Source trên Git lưu ở integrations/agent-hub/hub và integrations/system-monitor/artwork-worker; runtime Windows ở ArtworkInspector.
- [x] Giữ bản sao trước sửa, đối chiếu hash runtime, kiểm thử phần nguồn/chọn artwork.
- [x] File mới đi theo quy tắc chung; không có điều kiện tên khách/mẫu trong bản sửa.
- [x] Không chạy lại hồ sơ, tạo đơn hay gửi tin khi cập nhật tài liệu/Git.
- [ ] Khi triển khai máy khác: đối chiếu phiên bản nền và dependencies đang dùng trước khi copy; đây là đồng bộ các module PET đang chạy, không phải gói cài lại toàn hệ thống.
- [ ] Nếu preview còn thiếu chi tiết, kiểm tra candidate và lớp nền trước khi đổi model hay bỏ kiểm chứng.
