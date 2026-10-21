# Tách đặt lại và chỉnh thiết kế

Ngày áp dụng: 20/10/2026.

## Quy tắc

- Với nhóm/người gửi CANAVI đã cấu hình, “gửi thông tin đơn hàng”, “gửi đơn hàng”, “sản xuất lại”, “sx lại”, “đặt hàng” cũng có thể mở luồng kiểm tra phiếu. Không bắt buộc câu phải chứa từ “lệnh”.
- Đây chỉ là tín hiệu phân luồng. Vẫn xác minh tiêu đề PHIẾU LỆNH SẢN XUẤT ở đầu ảnh, đúng người/nhóm, tệp gốc và SHA256. Đọc độc lập số lượng, mã mẫu, ngày giao, loại in trước khi gửi API.
- Đặt/sản xuất lại kèm yêu cầu sửa cữ/màu/tràn viền: xem xét phần đặt hàng riêng; yêu cầu thiết kế ghi riêng nội bộ. Không lấy việc chuyển nhân viên thiết kế làm lý do bỏ phần đơn đủ dữ liệu.
- Agent có bước nhắc kiểm tra công việc đặt hàng còn thiếu khi định kết thúc mà chỉ chuyển nhân viên. Nhắc này không tự tạo đơn; các kiểm chứng nguồn/số lượng, chính sách và chống trùng hiện hữu vẫn áp dụng.
- Sửa file đơn thuần, in bù, giao vải hoặc hỏi giá không tự trở thành đơn mới.
- Không phát lại toàn bộ các phiếu cũ `no_trigger`. Mỗi lần khôi phục phải chỉ định nguồn và đối chiếu ERP.
- Không sửa ERP, không đổi chế độ AI chỉ ghi chú nội bộ.

## Ca PARTNERS

- Nhóm ID: `g2671966061008128194`; khách ERP CANAVI.
- Tin đặt `8396036804123`; phiếu `8396036885036`.
- Mã trên phiếu: **TB3VB-PARTNERS2.09-1**, 200 túi, TUI, giao 22/10/2026.
- File cùng cụm: `File in CN TB3VB-PARTNERS.10.ai`. Không lấy tên file thay mã trên phiếu.
- Yêu cầu riêng: màu/cữ như cũ, tràn thêm 3 cm viền phải, canh vừa khổ vải tránh hở mặt. Tin `8396050057367`, khách xác nhận `8396055595773`.
- Ghi chú riêng Chatwoot: hội thoại 16, tin 3359, private=true.

## Kiểm chứng

- [x] 13 kiểm tra phân luồng: lời đặt lại, lệnh in, hủy/chưa gửi/hỏi giá, sửa file và in bù, không nhắc lại khi đã đề xuất đơn.
- [x] Image Hub mới import thành công; đã triển khai 3 module.
- [x] Gemini xác minh ảnh phiếu và hai lượt đọc khớp 200 / TUI / 22-10-2026 / TB3VB-PARTNERS2.09-1.
- [x] Đối chiếu ERP gần đây theo đúng khách và PARTNERS: chưa có ứng viên trước khôi phục.
- [x] Khôi phục đúng một phiếu, giữ ID nguồn/request và ghi audit.
- [x] Biên nhận ERP: DH-2610-278, ID f2803701-b2ff-494c-883d-1285af69e62d. Đối chiếu chỉ có một đơn: CANAVI, TB3VB-PARTNERS2.09-1, TUI, 200, Lên mẫu, giao 22/10/2026. API và giao diện ERP đã kiểm chứng; ghi chú thành công Chatwoot 3363 là nội bộ.
