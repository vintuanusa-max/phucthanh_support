# INJAE — đối chiếu đơn và hai logo PET, 21/10/2026

- [x] Lô0971 xám6m: DH-2610-307, đúng INJAE, Lên mẫu; không replay.
- [x] Lô0480 camo nhạt17m/camo đậm7m: DH-2610-308/309, MET, Lên mẫu; kiểm tra ERP trước tạo, giữ request_id theo run e0cfee3e.
- [x] Sửa meter_product.apply_meter_lines: đối chiếu từng nhãn màu và số mét từ khách; không lan mã MET sang dòng không khớp. 8 kiểm thử gồm đảo số lượng, dòng không liên quan, nhân viên, hủy, báo giá và đơn1dòng.
- [x] Deploy hub image injae-meter-lines-20261021; giữ sửa policy/no-replay trước đó. Không restart ERP.
- [x] Hai PDF gốc: Therapin cao3,7cm (456×437px); THERAPIN/OWN IT. ngang7cm (827×171px),300dpi. Lấy3vector trắng/file1; ảnh nhúng trắng/file2, bỏ nền theo tin8399429084800. PNG alpha; Photoshop TIFF spot_1 và alpha được verify.
- [x] NAS: INJAE/DESIGNER/THERAPIN/review-20261021. Chatwoot conv20 private notes3958/3959, mỗi ghi chú3tệp gồm preview nền xám, PNG và TIFF. Không RIP/gửi khách.
- [x] Bảo toàn đơn logo đã được nhân viên chuyển Ra giấy và gắn.prt. Không thayfile hoặc tạo lại.
- [ ] Lô1024: chỉ thấy tin dán bill gửi hàng; bill SP-1806 hai mét chưa đủ chứng minh đơn in mới. Ghi chú nội bộ cần kiểm tra.
- [ ] Tin ba màu1665/357/4705 mỗi1m lặp sau các đơn10-21/22/23 ngày14/10: chưa xác nhận đặt thêm hay nhắc lại; không tự tạo trùng.

Code và script kiểm chứng phiên này: workspace/work/injae-audit. Nguồn triển khai hub tại U:/chatwoot/.worktrees/phucthanh/phucthanh/hub; bản mirror U:/phucthanh_support/integrations/agent-hub/hub. Chưa commit/push thay đổi phiên này.

## Sửa kênh trắng theo xác nhận chủ — 21/10/2026
- Hai TIFF INJAE đã thay: artwork trắng không contract. Spot inverse-alpha khớp từng pixel alphaPNG; giữ kích thước và300dpi.
- Bản cũ lưu NAS before-white-no-contract. Ghi chú thay thế riêng, private, không RIP/gửi khách.
- Quy tắc thiết kế: chỉ contract1pixel lớp trắng lót dưới màu khác trắng; vùng trắng không co. Chưa thay global WHITE_1/action hay triển khai phân vùng tự động cho job hỗn hợp. Phiên này sửa riêng2TIFF theo yêu cầu.
- Script và báo cáo: workspace/work/injae-white-fix/verify.py và verification.json.
