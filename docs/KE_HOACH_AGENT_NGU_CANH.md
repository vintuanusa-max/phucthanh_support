# Kế hoạch agent Phúc Thành — hiện hành 14/10/2026

## Quy tắc đã chốt

**Đơn đủ thông tin vẫn tự tạo trong ERP ở trạng thái Lên mẫu. Chỉ phản hồi AI cho khách giữ dưới dạng ghi chú private trong Chatwoot.** Hai quyền này độc lập; chế độ phản hồi nội bộ không tắt lên đơn.

Áp dụng mọi nhóm Zalo/WhatsApp được phép theo cấu hình, gồm nhóm mới về sau; giữ loại trừ nhóm nội bộ và tin riêng. Không phát lại lịch sử hoặc đề xuất cũ chỉ vì đổi cấu hình.

## Giai đoạn 1 — đã triển khai, theo dõi chất lượng thực tế

1. Gom tin/ảnh theo nguồn và nhóm, phân biệt khách/nhân viên, dựng ngữ cảnh và đề xuất trước.
2. Gemini gọi công cụ nhiều bước, nhận kết quả rồi quyết định tiếp; tối đa 6 bước, giới hạn thời gian và chống lặp.
3. get_order_status tra ERP theo đúng customer_id ánh xạ và mã đơn.
4. inspect_material tham khảo báo cáo vải khách của nhân viên trong đúng nhóm; có nguồn và thời điểm, không lấy tồn ERP, không suy ra số dư hiện tại.
5. propose_order_draft tạo đề xuất được kiểm chứng. Khi auto_order=true, đề xuất tiếp tục qua các kiểm tra lên đơn cũ, lưu bằng chứng PNG/NAS và API ERP với request_id ổn định. Công cụ đề xuất không tự tuyên bố ERP đã tạo thành công.
6. request_customer_clarification ghi câu hỏi dự kiến vào Chatwoot, không gửi khách. escalate_to_human mở Open kèm nguyên nhân khi cần người xử lý.

Thiếu dữ liệu, ảnh chưa sẵn sàng, nguồn mâu thuẫn, nghi sửa đơn cũ, khách chưa xác thực hoặc kết quả ghi ERP không chắc chắn thì chờ/đối chiếu, không tạo bừa hay tự gửi lại. Quy tắc auto_order riêng từng nhóm vẫn được kiểm tra trước ghi ERP.

## Giai đoạn 2 — chưa triển khai

Dịch vụ sửa file độc lập; job có phiên bản nguồn, yêu cầu chỉnh sửa và kết quả. Gemini Vision đối chiếu đầu ra; cần kiểm chứng chất lượng trước khi tự trả file. submit_design_revision hiện báo công cụ chưa sẵn sàng và chuyển nhân viên.

## Bật trả lời nhóm thật về sau

Chỉ sau khi chủ hệ thống xem ghi chú và đồng ý. Hiện public_replies=false, internal_only=true; quyền AI/human không tự bỏ chốt này. Luồng thông báo duyệt in tới nhóm File In đã có là luồng riêng, giữ nguyên.


## Cập nhật 14/10: in bù
Đã triển khai quy tắc in bù và đối chiếu cùng ngày. Xem DOI_CHIEU_DON_VA_IN_BU_20261014.md và checklist để biết phạm vi tự động, biên nhận thật và phần chờ nhân viên.
