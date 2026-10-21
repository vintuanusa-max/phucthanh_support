# PDF maket → PNG/TIFF PET chờ duyệt — 21/10/2026

## Quy tắc đang áp dụng
- Nhận hồ sơ mới đã được bộ kiểm tra artwork liên kết file PDF/AI và tin đặt mẫu. Không chỉ dựa tên file để khẳng định công nghệ; chuyển nhiệt/thêu/công nghệ khác không tự coi là PET.
- Chọn đúng đối tượng logo/chữ/họa tiết trên sản phẩm, bỏ hình sản phẩm, logo nhà cung cấp, QR, footer, đường đo.
- Hai góc nhìn cùng vị trí chỉ xuất một file. Nhiều vị trí in thật tách mỗi vị trí một PNG/TIFF; không gộp chỉ vì dùng cùng logo. Hỗ trợ tối đa8 vị trí trong một kế hoạch; vượt giới hạn chuyển kiểm tra.
- Ưu tiên kích thước khách xác nhận. Nếu chưa rõ, dùng kích thước bố trí artwork trong PDF/artboard nguồn (source_layout); maket nhiều vị trí lấy riêng từng cụm, không lấy cả trang chứa sản phẩm làm logo. Chỉ cho ngang thì tính cao theo tỷ lệ artwork.
- Mỗi file PET cao hơn 6,5 cm: thu đồng tỷ lệ về cao 6,5 cm, ngang giảm tương ứng; không phóng file nhỏ. Ghi kích thước trước/sau và hệ số trong hồ sơ. Không áp quy tắc này sang JPG túi/co vải.
- Kiểm tra nguồn và preview trên nền sáng/tối để không bỏ sót chữ trắng. Không loại chữ trắng vì giống màu nền; chỉ bỏ theo xác nhận riêng cho đúng đơn (BIG_BANG mặt trước chỉ vương miện). Nền trắng đục che đối tượng hoặc tách không chắc thì chuyển kiểm tra.
- Ảnh nhúng ưu tiên alpha gốc; chỉ bỏ nhiễu alpha<=1/255, không xóa nền theo màu trắng. Giữ trắng thuộc logo. Ảnh nền chưa trong suốt hoặc cấu trúc chưa hỗ trợ phải chuyển duyệt.
- PNG300dpi trong suốt, không co vải/không định vịL/không lật gương. Photoshop WHITE_1 tạo TIFF, mở lại kiểm spot_1 có dữ liệu, alpha và kích thước/DPI khớp.
- Lưu theo luồng PET_AUTO hiện hữu và ghi chú nội bộ có nguồn, kích thước, file. Chưa RIP/gửi khách. Queue giữ chống chạy lại khi kết quả chưa rõ; không phát lại hồ sơ cũ.

## Kiểm chứng
- [x] PDF Cô Vàng: object logo gốc, ngang9cm, cao~5,047cm sau trim alpha; loại khoảng trống gây sai tỷ lệ.
- [x] Kế hoạch nhiều vị trí giữ tách riêng; nguồn kích thước phải truy vết được.
- [x] Kiểm thử source_layout, giới hạn cao 6,5 cm, alpha và artwork trắng; PDF BIG_BANG có bản nguồn nền tối.
- [x] Docker build/import thành công; nạp hub pet-white-cap-20261021.
- [x] Mẫu Cô Vàng đã có TIFF xác minh trước đây, ghi chú3449. Không xuất lại mẫu đó.
- [ ] Đối chiếu đầu-cuối một hồ sơ mới tự chọn bằng Gemini khi phát sinh. Không khẳng định mọi PDF đều tách được.

Mã: integrations/agent-hub/hub/pet_exports.py và pet_render.py. Worker TIFF hiện hữu giữ nguyên.
