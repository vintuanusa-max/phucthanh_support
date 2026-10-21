# Hồ sơ thiết kế và cấu hình in túi — 16/10/2026

## Phạm vi đang chạy

Tổng hợp yêu cầu thành JSON, liên kết tin/ảnh/file nguồn, ghi chú **riêng** Chatwoot và chờ nhân viên kiểm tra. Không sửa file, xuất file, tự hỏi khách hoặc gọi ERP từ mô-đun thiết kế. Các đơn hàng vẫn theo luồng ERP độc lập.

11 tình huống trong báo cáo rà soát đã được nhập hồi cứu: 10 hồ sơ mới (ghi chú 1847–1856) và hồ sơ EM KIỀU có sẵn 1846. Hồi cứu là dữ liệu tham khảo, không khẳng định việc còn tồn. File A THỨC `in nón x6.cdr` đã được nhân viên xử lý theo lời chủ xưởng, không được tự tạo việc lại.

## Các lớp dữ liệu

1. Nguồn bất biến: tài khoản, ID nhóm/tin, tác giả/vai trò, thời gian, text gốc, ID Chatwoot, ảnh trích dẫn, media ID, đường dẫn NAS và hash đã có.
2. Yêu cầu: từng thay đổi kèm tin và trích dẫn; phân biệt lời khách, câu hỏi nhân viên, thông tin trên ảnh chưa xác minh.
3. Hồ sơ in túi `bag_print`: thông số, nguồn của từng thông số, hình học đề xuất, phần thiếu/mâu thuẫn. Hồ sơ mới chỉ đề xuất liên quan hồ sơ cũ, không tự thay thế.
4. Trạng thái: `needs_staff_review`, `execution_allowed=false`, `ready_for_execution=false`. Nhân viên cần duyệt trước khi worker thiết kế tương lai thực thi.

API có Bearer admin: `GET /design-briefs?conversation=<id>`. JSON bền vững trong Docker volume Hub `/data/design-briefs/`; SQLite có `design_briefs` và `design_scans`. Không coi đường dẫn `/data` là thư mục U: của Windows. File gốc vẫn tại NAS, chưa sao chép toàn bộ vào hồ sơ.

## Module riêng cho túi, dùng chung nguồn/hồ sơ

| Nhóm thông tin | Trường cần biết |
|---|---|
| Nhận diện | Mã mẫu, phiên bản phiếu lệnh, PDF/AI gốc, maket đúng phiên bản |
| Thành phẩm | Cao, ngang, hông, đáy; cấu tạo túi; có đáy hay không |
| Vải in | Kích thước thực; chiều ngang/cao; mảnh riêng một mặt hay trải hai mặt; trục gấp/chia |
| Phần cần in | Trước, sau, hông, đáy, quai — riêng từng phần; có hông/đáy không có nghĩa in hông/đáy |
| Cữ in | Khoảng cách và mốc đo; đối tượng logo/chữ/ảnh nào; đo tới biên nào; miệng túi, đường may, đường gấp |
| Bù kỹ thuật | Phần cộng miệng, đường may, co vải; phần nào đã nằm trong kích thước vải |
| Quai | Có in không, mã mẫu quai, file tương ứng, rộng/dài/số lượng, hướng xoay, cách lặp, khổ 160cm khi áp dụng |
| Xuất in | Khổ/đơn vị, định dạng, profile màu, mirror, bleed, quy định máy/RIP, version được duyệt |

Các trường `bag_facts` có field, value, source_message_ids, evidence và basis=text/image. Các giá trị từ ảnh vẫn phải kiểm. Đã bổ sung đọc PDF và AI PDF-compatible, khổ trang/boxes/text/font report và render đối chiếu; xem ARTWORK_INSPECTION.md. Đã có kiểm kê bbox/kích thước trong file của chữ, ảnh và vector path; chưa xác minh native AI layers/linked objects hoặc kích thước sản xuất của artwork. Chưa xác minh file nguồn đủ để sửa hoặc khớp đúng phiên bản maket.

## Quy tắc hình học đã mã hóa

- Cữ từ miệng thành phẩm + phần miệng túi = cữ từ mép vải. Ví dụ 4 + 5 = **9cm**. Không cộng lại khi cữ đã đo từ mép vải.
- Giữ nguyên kích thước vải đã cho nếu xác định mảnh một mặt. Không cộng +5 lần nữa vào chiều cao vải đã bao gồm phần miệng.
- Không suy chia đôi chỉ từ “in 1 mặt”. Nếu vải trải hai mặt, cần xác nhận chia và trục chiều cao/ngang; thiếu thì chờ kiểm tra. Không suy trục từ số lớn hơn.
- Không tự suy đáy 15cm phải cộng 7.5cm/15cm vào bản in khi chưa có quy cách cắt/gấp.
- Có in quai: đề xuất khổ ngang 160cm, nhưng thiếu mã mẫu/quy cách quai thì chưa đủ dữ liệu tạo artboard.
- Mâu thuẫn số đo: không tính hình học; giữ nguồn để người chọn phiên bản đúng.

## Ví dụ chủ xưởng cung cấp: TDVB-DB.10

Nguồn: hai ảnh đính kèm của chủ xưởng trong yêu cầu này và lời giải thích đi kèm. Phiếu cùng mã đã xác định ở CANAVI HCM2, tin Zalo 8380302270476. Không mặc định mọi ảnh gửi sau phiếu là cùng phiên bản.

- Thành phẩm: cao 35, ngang 40, hông 15, đáy 15 cm.
- Kỹ thuật: chuyển nhiệt 1 mặt, số lượng 100. Có đáy; chưa có lệnh in riêng đáy/hông/quai.
- Phiếu ghi `KT vải in 47.5 x 46`, `Miệng túi +5cm`.
- Chủ xưởng xác nhận mẫu này là mảnh một mặt, không chia đôi. Cần giữ rõ chiều nào là ngang/cao trước dàn; không chỉ lưu chuỗi `47.5 x 46`.
- Maket: cữ trên 4cm; theo chủ xưởng cữ từ mép vải là **9cm**. Mép phải logo 2.3cm, mép trái cụm chữ 2cm phải gắn đúng đối tượng và mốc đo, không dùng một cữ chung cho cả artwork.
- Quai đen 62cm btp không tự suy là quai phải in.
- Chưa có file PDF/AI gốc kèm hai ảnh này; cần file, phiên bản, kích thước artwork và quy định xuất in. Chưa đủ điều kiện tự dựng file.

## Checklist còn lại trước worker tự thiết kế

- [x] Tự tổng hợp nội bộ và hồ sơ hồi cứu có nguồn.
- [x] Cấu trúc riêng in túi và phép tính cữ/chia có điều kiện.
- [x] Phiếu lệnh mới sao chép thành công cũng được xét hồ sơ thiết kế; tin bổ sung đi qua intake hiện có.
- [x] Bộ đọc PDF/AI PDF-compatible: khổ trang/boxes, text/font report, render; đã bổ sung bbox đối tượng; còn thiếu native artboard/layer/link và xác nhận tỷ lệ in.
- [ ] Liên kết chắc chắn mã mẫu/phiếu/maket/file; duyệt phiên bản thay thế, không gộp theo thời gian đơn thuần.
- [x] Cấu trúc bag_panels/placements: mỗi logo/chữ có cữ và mốc đo riêng, mỗi mặt/hông/đáy/quai có nguồn artwork và kích thước đề xuất; còn cần worker thực thi và xác minh orientation.
- [ ] Template đã duyệt cho từng kiểu túi/cách may/quai và quy tắc co vải, đường may, bố trí lặp.
- [ ] Giao diện nhân viên duyệt/sửa trường thiếu, lưu người duyệt và thời gian; mở khóa worker có chủ đích.
- [ ] Worker thiết kế + kiểm tra kích thước bằng code, đối chiếu bản xem trước bằng thị giác, duyệt bản cuối rồi xuất.

Kết luận về độ đủ: đủ làm hồ sơ đầu vào để nhân viên hoàn thiện và làm nền cho bot; **chưa đủ để tự sản xuất file in**. Không được nâng `ready_for_execution` chỉ vì AI không còn ghi missing_fields.

Kiểm chứng: 10 kiểm thử mô-đun thiết kế/túi đạt; 42 kiểm thử cuối gồm Hub/phiếu/thiết kế/túi đạt. Phiếu mẫu tự đọc hết thời gian và được ghi review, không tự dùng dữ liệu chưa kiểm. Hồ sơ từ hướng dẫn chủ xưởng đã lưu JSON + hai PNG tại NAS CANAVI HCM2/DESIGN_BRIEFS/TDVB-DB.10-owner-reference-20261016, ghi chú riêng #1858, ID 4e38741e80f447fab474082dfd6bddb7d1def4a755f479e3234b9605bdc95d88. Đây là bản owner-provided, không ghi nhận là OCR đã được xác minh.
