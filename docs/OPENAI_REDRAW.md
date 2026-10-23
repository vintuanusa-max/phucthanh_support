# OpenAI redraw — 22/10/2026
- [x] CẦN THƠ v5 được chủ xưởng duyệt: xuất PNG/TIFF, cao6.5cm, không lật gương, alpha+spot_1. Note private #4044, ba attachments. NAS A THUC/DESIGNER/CAN_THO/versions/90deb9d28f428f1c191a048bcf72c1df7d32258e96ee7e060f5386a5a6560419.
- [x] Raster router chọn redraw cho nhiễu/xước/méo nét dù chữ vẫn đọc được; OpenAI gpt-image-2.5-sunburst high, một ảnh/lượt/vị trí. Không dùng SDXL/ KonText cho nhánh này. Ảnh sạch chỉ thiếu pixel vẫn có upscale; đủ nét keep.
- [x] Redraw yêu cầu restoration_consent gồm ID câu hỏi nhân viên và câu trả lời khách không có file; không có thì review nội bộ. Giữ gate hiện tại 30 phút, đúng khách và hồ sơ hiện tại.
- [x] Đối chiếu chữ/số, hình/màu bằng verifier trước khi queued; sai hoặc chưa rõ → review, không tự thử lại.
- [x] Receipt ghi trước POST; lỗi/timeout không tự retry; cache kết quả đã kiểm chứng theo SHA nguồn. Usage và request ID lưu riêng, không ghi khóa.
- [x] Ba kiểm thử giả lập không mạng đạt: consent/cache/cost; timeout chống retry; chữ sai chặn xuất. Không gọi model thật khi triển khai.
- [ ] Cần quan sát hội thoại mới thực tế (nhân viên hỏi, khách trả lời không file) để kiểm chứng end-to-end; ảnh sản phẩm không có artwork riêng hoặc nguồn không nối chắc vẫn chờ kiểm tra.
- Secret /data/secrets/openai-api-key ngoài Git. ERP độc lập, chưa RIP/gửi khách; preview chỉ private Chatwoot. Bản v5 đã có nên không gọi OpenAI lại khi xuất TIFF.

## 22/10/2026 — Rà soát xác nhận không có file và chống phí trùng
- [x] Nhận câu hỏi ngắn “có file không?”, xác nhận đúng người gửi ảnh; cặp hỏi/đáp trong 30 phút.
- [x] Chọn nguồn trong cụm ảnh cùng khách (cụm tối đa 5 phút), đọc cả hội thoại và maket. Có tin đổi mẫu chen giữa, ảnh khách khác hoặc nguồn mơ hồ: giữ chờ kiểm tra nội bộ, không gọi vẽ lại.
- [x] Khách xác nhận ở lượt sau: tiếp tục đúng hồ sơ review đang chờ file. Mốc openai-followup-enabled-at ngăn phát lại lịch sử; không mở lại archived/done/uncertain.
- [x] Receipt chung theo model/account/nhóm/hash ảnh, không phụ thuộc brief hay số lần khách xác nhận. Chữ OCR khác hoặc lần trước chưa rõ kết quả: review, không tự mua thêm lượt.
- [x] Giữ PNG alpha, TIFF spot_1, trắng không contract, màu contract 1px; không lật gương, chưa RIP/gửi khách. Preview nội bộ theo pipeline hiện có.
- [x] 10 kiểm thử giả lập không mạng: chọn nguồn, nhầm người, ảnh cũ, nhiều mẫu, tin trả lời sau, chống trùng và timeout. Không phát sinh phí OpenAI; không thay đổi ERP.
- [ ] Chưa xác nhận end-to-end trên một hội thoại khách mới sau triển khai. Ảnh chỉ là sản phẩm không có artwork riêng, nhiều mẫu không rõ hoặc câu trả lời quá 30 phút vẫn chuyển kiểm tra nội bộ. Đây là giới hạn chủ ý, không tuyên bố tự xử lý mọi ảnh.
- Runtime: phucthanh-chatwoot-hub:openai-guard-20261022. Tests: integrations/agent-hub/tests/test_openai_redraw_guard.py (secret mocked, không ghi khóa).
