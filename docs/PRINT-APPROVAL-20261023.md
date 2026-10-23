# Quy trình duyệt in tự động
Trạng thái cập nhật 23/10/2026. Tài liệu này thay phần mô tả lỗi tạm thời trước đây; bản cũ đã sao lưu.

## Phạm vi và thời điểm
Tự động với nhóm được phép có nguồn và câu duyệt rõ. Chỉ xử lý tin xác nhận từ **18:00 ngày23/10/2026 UTC+7** trở đi; đây là mốc cố định, không đặt lại mỗi ngày. /data/print-forward-policy.json lưu send_after=1792753200. Hồ sơ trước mốc không gửi lại vì nhân viên đã xử lý.

## Các bước
1. Bộ đọc lưu tin/ảnh khách và ảnh mẫu nhân viên vào Chatwoot/NAS. Vai trò nhân viên đối chiếu danh sách config, không dựa riêng origin cũ. Ảnh nhân viên không được dùng làm yêu cầu lên đơn.
2. Nhận các câu như in đi, ok in đi, in luôn đi, in ln đi, duyệt mẫu, chốt luôn nhé. Phủ định/câu hỏi/điều kiện chưa phải duyệt. Nhận diện hiện dùng quy tắc từ ngữ có kiểm tra ngữ cảnh, không hiểu mọi cách diễn đạt.
3. Tìm đúng mẫu trong cùng nhóm, tối đa24giờ trước câu chốt. Cụm ảnh cùng tác giả gần nhau trong120giây; không lấy ảnh khách khác. Trích dẫn phải có ảnh gốc đã giải quyết. Tối đa12tin/8ảnh.
4. Làm gấp/in gấp/cho chạy/chốt luôn phải gắn mẫu nhân viên. OK mơ hồ mà hệ thống đã nhận cần ảnh gần trong5phút. “Ok em” không mặc định được nhận; có thể cần đối chiếu.
5. Chờ hội thoại yên ít nhất120giây; khách bổ sung/đổi yêu cầu thì giữ kiểm tra. Không hứa thời gian gửi cố định nếu hàng đợi/mạng đang kẹt.
6. Tạo bằng chứng tổng hợp ảnh và câu chốt, lưu NAS; sender thăm dò khoảng15giây, claim riêng từng kênh.
7. Gửi File In - Giấy In - Màng Pet: Zalo g3307527274697028144; WhatsApp120363407119559834@g.us. Chỉ confirmed cả hai mới hoàn tất hồ sơ và ghi xác nhận nội bộ.

## Trạng thái và chống trùng
| Trạng thái | Ý nghĩa/cách xử lý |
|---|---|
| awaiting_evidence | Chờ dựng bản tổng hợp |
| ready | Có bằng chứng, chờ kênh chưa gửi |
| review | Thiếu/mâu thuẫn nguồn; kiểm tra nội bộ |
| confirmed | Đã xác nhận cả hai kênh |
| excluded_before_cutoff | Tin trước mốc18h; không gửi |
| delivery sending/submitted/uncertain/blocked | Xem kết quả từng kênh; không xóa để gửi lại |

Khóa hồ sơ theo account+groupID+messageID và fingerprint ảnh. Mỗi approval/account chỉ một bản gửi. WhatsApp confirmed thì không gửi lại khi bổ sung Zalo. Uncertain phải đối chiếu biên nhận/tin thật trước quyết định; không retry tự động. Mẫu lặp cùng ảnh có thể bị giữ để tránh nhầm lệnh cũ.

## Đã kiểm chứng
- [x] Nhận câu duyệt và vai trò nhân viên theo config; các guard phủ định/ngữ cảnh.
- [x] Khôi phục55 ảnh nhân viên đúng ngày23/10; những ảnh mới tiếp tục được tải độc lập điều kiện ERP.
- [x] Bộ gửi Zalo26.10.20 cập nhật, prepare ready và cleanup=true.
- [x] BÍCH VÂN và Chú Dũng đã confirmed trên cả Zalo/WhatsApp.
- [x] Chú Dũng lượt đầu được đối chiếu thủ công; sau đó đã bổ sung in ln/in luôn vào luồng tự động.
- [x] Giữ mốc18h, khóa từng kênh, không tạo/sửa đơn ERP.
- [ ] Chưa bảo đảm mọi câu nói tự nhiên hoặc mọi lần Zalo cập nhật đều tương thích.
- [ ] Thiếu ảnh thật, nhiều mẫu hoặc kết quả gửi chưa rõ vẫn phải kiểm tra.

## Các ca giữ lại
Hồng Ánh có ảnh bổ sung sau OK: đã ghi nội bộ để đối chiếu bản cuối. Chị Yến còn chỉnh màu. Chị Én nhắc mẫu đã duyệt trước18h: không gửi lại. Không reset các ca này chỉ vì dịch vụ restart.

## Thành phần để tra cứu
Hub: hub/print_approval.py, hub/print_changes.py; bảng print_approvals/print_deliveries/print_change_sources.
Windows: WhatsAppDesktopReader/code/whatsapp_desktop/print_sync.py điều phối hai đích; zalo_desktop/desktop_photo_transport.cjs gửi ảnh Zalo. Bộ đọc Zalo reader.py +vault giữ ảnh, checkpoint riêng.
Xem thêm [ảnh nhân viên](STAFF-MEDIA-20261023.md), [checklist](CHECKLIST_VAN_HANH_HE_THONG.md).
