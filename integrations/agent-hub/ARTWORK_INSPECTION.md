# Đọc PDF/AI và đối chiếu hồ sơ in túi — 16/10/2026

## Đang hoạt động

- `hub/artwork_checks.py`: dò file PDF/AI đã có trong nguồn hồ sơ; với mã thiết kế rõ, tìm ứng viên trùng mã trong **cùng tài khoản/nhóm**, tối đa 1.000 capture gần nhất. Trùng tên/mã không xác nhận cùng phiên bản.
- `zalo_desktop/artwork_bridge.py`: tiến trình Windows riêng đọc file trong NAS theo relative_path đã lưu; kiểm tra containment, SHA256 và giới hạn dung lượng. Không điều khiển Zalo/WhatsApp/Viber hoặc sửa bản gốc.
- Windows runtime `C:/Users/Admin/AppData/Local/PhucThanh/ArtworkInspector`: vòng lặp 30 giây cho cấu hình ba đầu nối. Khóa một tiến trình; Startup `PhucThanh-ArtworkInspector.vbs` mở ẩn khi đăng nhập. Không cần restart các ứng dụng chat.
- Hub nhận bản sao có hash đúng, enqueue job; API nhận file không giữ kết nối trong lúc Gemini đọc.
- `hub/artwork_pdf.py`: Poppler đọc PDF hoặc phần PDF tương thích của AI. Đọc số trang, kích thước trang/boxes, text và báo cáo font; render PNG xem trước, không xuất file sản xuất.
- Gemini so sánh PDF preview với phiếu lệnh/maket/ảnh nguồn có ID cụ thể. Kết quả gồm file_role (artwork/maket/production_slip/mixed/unknown), same_design (proposed/unknown/mismatch), findings có loại missing/conflict/observation và ID nguồn, missing_fields.
- Lưu kết quả vào `artwork_checks`, hồ sơ `design_briefs.artwork_checks`, JSON `/data/design-briefs/`. Note **ĐỐI CHIẾU FILE GỐC — CẦN KIỂM TRA NỘI BỘ**, Open hội thoại. Luôn execution_allowed=false.

## Phạm vi và giới hạn

- Chỉ file đã lưu NAS và có SHA256; không tự tải đường link ngoài, tìm trong toàn bộ ổ đĩa hoặc chọn file khác nhóm.
- Tối đa 32 MiB/file, đọc/render tối đa 4 trang đầu; tài liệu trên 200 trang không xử lý. Ghi rõ nếu chưa kiểm toàn bộ. AI lớn hơn giới hạn, không PDF-compatible, PDF khóa hoặc lỗi parser chuyển nhân viên.
- Kích thước trang PDF không tự coi là khổ logo, artboard Illustrator native hoặc kích thước vải. Không đo cm từ pixel ảnh.
- Chưa kiểm chứng native AI layers, clipping/linked objects, editable fonts, màu máy in, mirror/bleed. Bản có outline/raster hoặc font đã nhúng không chứng minh chỉnh sửa chữ được.
- Không sửa layer/artboard, chia vải, dàn quai, tạo file RIP, hỏi khách hay thay ERP. Các phép tính cữ trong hồ sơ vẫn là đề xuất cần duyệt.
- Các file bổ sung chỉ được tự đối chiếu khi đã gắn nguồn vào hồ sơ hoặc có mã thiết kế khớp làm ứng viên. Không có liên kết rõ thì vẫn cần nhân viên kiểm tra; không đoán theo thời gian gần nhất.
- Mỗi hash/file/hồ sơ/phiên bản kiểm tra có khóa chống lặp. Lỗi/khởi động lại giữa chừng giữ review, không tự gửi lại ghi chú chưa rõ kết quả. Nguồn gốc vẫn ở NAS; xóa bản sao PDF tạm trên Hub sau hoàn tất, giữ preview và metadata.
- API ingest: GET/POST `/adapters/{account}/artwork-checks[/{id}]` yêu cầu Bearer ingest; xem hồ sơ qua GET `/design-briefs?conversation=<id>` yêu cầu Bearer admin. Không nhúng token vào tài liệu.

## Kiểm chứng thực tế

- `TDVB-DB.10 (1).pdf`, nguồn Zalo `8380302468470`, CANAVI HCM2: hash kiểm đúng, 1 trang PDF khoảng ngang 65.6368 × cao 79.8904 cm. Render cho thấy đây là **maket**, có hình túi phối cảnh và số đo.
- Gemini đối chiếu thành công với phiếu và hai ảnh chủ xưởng: mã TDVB-DB.10, thành phẩm 35×40, hông/đáy15, vải47.5×46, chuyển nhiệt một mặt, 100 túi; giữ phần thiếu artwork/file được duyệt, mốc ngang/cao, thông số may/co/xuất in. Không coi kích thước trang PDF là kích thước vải.
- Bản AI `IN CHUYỂN NHIỆT TDVB-THOCAM.10.ai`: đọc được phần PDF-compatible, 1 trang khoảng95.8547×99.8707cm; đã xem render. Đây cũng là trang maket; phép thử parser không tự tạo việc/đơn mới cho THOCAM.
- Lần đối chiếu v1 không đạt kiểm chứng định dạng nguồn và đã ghi lỗi. Bản v2 có schema ràng buộc loại file và danh sách nguồn, đã hoàn tất; giữ v1 để truy vết, không coi là hai yêu cầu thiết kế.
- 5 kiểm thử riêng kiểm đơn vị, AI không tương thích, mã mẫu, containment/hash/size, upload lặp và đảm bảo chỉ ghi chú riêng/không ERP. 37 kiểm thử ở lượt tích hợp trước đạt; kiểm thử riêng bổ sung sau đó đạt.

## Phần tiếp theo chưa thực hiện

Đọc layer/vector native và liên kết trong AI bằng worker riêng; xác nhận phiên bản/mảnh/mốc đo; kiểm tra geometry từng đối tượng; giao diện duyệt; worker thiết kế thực và xuất file chỉ khi được cho phép.


## Bổ sung kiểm kê đối tượng — 16/10/2026
- [x] `hub/artwork_objects.py`: subprocess PyMuPDF, timeout45s; chữ/font/cỡ chữ, ảnh nhúng/pixel/ma trận, vector path/segments, bbox point và cm. ID theo trang+thứ tự, được định danh trong job chứa hash nguồn.
- [x] Tối đa600 đối tượng/4 trang, đánh dấu truncated. Các cữ/khổ đo là trong PDF, chưa xác minh tỷ lệ sản xuất; clipping/mask có thể làm vùng nhìn thấy khác bbox.
- [x] Gemini nhận các ID object làm nguồn đối chiếu logo/chữ/ảnh với maket/phiếu. Findings vẫn là đề xuất, không tự chọn logo để xuất. Nét vector có thể là chữ outline hoặc mảnh logo, không coi mỗi path là một logo.
- [x] Ghi metadata vào hồ sơ và thông báo riêng Chatwoot; không sửa PDF/AI, không tạo đơn hay xuất in.
- [ ] Worker Illustrator kiểm tra native group/layer/clipping/linked images và kích thước artwork đã duyệt.
- [ ] Duyệt chọn logo và phép biến đổi từ maket sang vải trước thực thi Designer.

### Tái sử dụng DESIGNER
NAS `U:/DESIGNER/repos/phuc_thanh_designer-by-hands/workflows/pet_workflow.py` gọi `extract layer.py`, nhưng file đó thiếu trong bản NAS. Bản máy ở `C:/Users/Admin/Documents/GitHub/phuc_thanh_designer/extract layer.py` có trích PDF object bằng PDFium và nhánh AI SVG/ZIP; không dùng giả định AI ZIP cho file AI PDF-compatible thực tế. Giữ hợp đồng pages/objects/bounds, dùng parser PDF-compatible và hệ tọa độ ghi rõ. Không chạy workflow PET hiện có vì nó có thao tác chọn/sửa/xuất Illustrator.
Nguồn API parser: https://pymupdf.readthedocs.io/en/latest/page.html


### Kiểm chứng đối tượng và phần chờ
TDVB-DB.10: 13 span chữ, 1 ảnh nhúng, 250 vector paths; ghi chú1872 đã được đính chính bằng ghi chú riêng1873. Ảnh p1-o14 chỉ chứa con vịt và nốt nhạc, không chứa logo/chữ vector ngoài ảnh. Gemini từng gán sai hai phần này; hồ sơ đã loại nhận định đó, yêu cầu kiểm tra nhóm vector. Không được dùng nhận diện đề xuất để tự xuất.
Bản hồ sơ NAS: CANAVI HCM2/DESIGN_BRIEFS/TDVB-DB.10-owner-reference-20261016/object-brief-20261016.json.
Mã đang chạy: kiểm kê metadata đối tượng + đối chiếu preview trang. Bản bổ sung preview riêng ảnh nhúng đã qua kiểm thử cục bộ, CHƯA triển khai: đang chờ chủ xưởng cho phép gửi các ảnh nhúng này tới Gemini. Không diễn giải bản đang chạy là đã có bước kiểm chứng ảnh nhúng riêng tự động.
