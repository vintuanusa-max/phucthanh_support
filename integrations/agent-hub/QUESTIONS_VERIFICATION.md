# ERP — câu hỏi lỗi mẫu và thông tin, 27/10/2026
- [x] Fast path hẹp bằng chữ cho câu hỏi lỗi mẫu, giá, tiến độ, giao nhận, chất liệu; không gọi AI/ERP. Chỉ một ảnh, không file phụ và toàn bộ tin phải rõ câu hỏi.
- [x] Có số liệu, yêu cầu mới/lên mẫu, nhiều ảnh/file hoặc nội dung lẫn chưa rõ thì giữ luồng phân tích; không tự bỏ nguồn. Không cam kết mọi câu hỏi đều tránh được vision.
- [x] Text classifier bổ sung quote/information và hướng dẫn phản ánh lỗi; cache route đổi phiên bản, cache observation vẫn giữ.
- [x] Câu riêng trước dấu phẩy/chấm/chấm phẩy là phản ánh lỗi, sau đó yêu cầu in thêm rõ: lấy lượng của phần đặt thêm. Ví dụ 100 cái cũ bị lệch, in thêm 200 cái -> delta 200, không 100/300.
- [x] Giữ chặn phủ định, điều kiện và lượng mâu thuẫn; không tự gán đơn cũ hay đổi khách.
- [x] 82 test giả lập đạt trong container network none, không API key/DB thật. Test questions-final.xml. Không tạo đơn thật, không replay.
- [x] Hub question-routing-20261027; backup hai file .before-questions-20261027; ERP không restart.
- Phạm vi chỉ luồng lên đơn. Hỏi lỗi mẫu vẫn còn trên Chatwoot; bỏ qua tạo đơn không có nghĩa AI đã xem và giải quyết lỗi thiết kế. Luồng file/duyệt khác không bị tắt.
