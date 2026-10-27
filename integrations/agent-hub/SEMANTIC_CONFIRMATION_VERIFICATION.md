
## 27/10/2026 — AI đọc hội thoại xác nhận thay ACK regex
- [x] Hook analyze/submit dùng conversation_confirmation: Gemini2.5Flash đọc hội thoại customer/staff1giờ, bỏ system, không lọc đầu vào bằng chữ ok. Tối đa200 nguồn; quá giới hạn thì review.
- [x] JSON mode new/total/additional, mẫu, lượng, đơn vị, ID câu hỏi/câu trả lời và trích dẫn thật. Code kiểm tra vai trò, thời gian, nguồn, số dương và độ phủ batch.
- [x] Mẫu chưa rõ dùng cơ chế nối ảnh đã kiểm thử. Tổng/sản lượng đối chiếu ERP trước phân tích và gửi; đặt thêm đi qua OrderAdditions với khóa nguồn hiện có. Không thay tin gốc.
- [x] Cache theo toàn ngữ cảnh+model+nhóm; tin mới làm cache khác. Không replay nguồn đã tạo/đang gửi/chưa rõ kết quả.
- [x] 151 ca giả lập cách ly đạt. 8 tình huống hội thoại giả thử Gemini thật: đã điều chỉnh total/new và thử lại2ca; kết quả cuối đạt các kỳ vọng an toàn. Một ReadTimeout đã thử lại đạt. Không gọi ERP ghi thật, không tạo đơn thử.
- [ ] Nhiều mẫu/nhiều yêu cầu trong một xác nhận chưa tách chắc thì review; không gộp hoặc bỏ nguồn. 8ca không chứng minh tất cả cách nói ngoài thực tế.
- Image semantic-confirmation-20261027; giữ image cũ rollback. Không restart ERP.

Kiểm chứng commit: snapshot HEAD + đúng17file staged, 112ca hồi quy đạt; quét secrets staged0phát hiện. Các thay đổi giao diện/xuất file khác giữ ngoài commit. Không API/ERP thật trong kiểm thử commit.
