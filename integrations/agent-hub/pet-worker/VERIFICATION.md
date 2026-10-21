# Kiểm chứng PET tự động — 19/10/2026

- 5 unittest mô-đun: tên file; bằng chứng số đo/mặt; render/hash/alpha; complete private chống lặp; không phát lại brief cũ.
- 6 integration tests trên bản code staged chính xác: 5 artwork regression + 1 xác thực API/phân tài khoản.
- Photoshop thật: hai mặt TB1VB-EC.10, xuất vào thư mục regression riêng, không gửi lại Chatwoot. Hai TIFF có spot_1/SPOTCOLOR không rỗng, 300dpi, alpha bằng PNG từng pixel, source AI không bị ghi.
- Gemini thật: ca TB1VB-EC.10 phức tạp bị giữ review do chưa chắc cụm đối tượng; không tự phát hành bản sai. Một lượt đầu hết thời gian, đã rút gọn input và tăng giới hạn chờ.
- Gemini thật: ca PET giả lập có 2 đối tượng, kích thước khách xác nhận, chọn → render → kiểm tra độc lập → queued. Đã sửa false-positive khi verifier đòi cm đầu ra bằng cm bbox PDF, dù khách yêu cầu scale đồng tỷ lệ.
- Triển khai backup suffix `backup-pet-20261019-120715`; không restart ERP. Hub có bảng pet_exports, 4 API; các adapter Zalo/WhatsApp/Viber trả HTTP200 idle.
- Hiện chưa có hồ sơ PET mới sau mốc bật để xác nhận một lượt khách thật từ đầu tới cuối. Không tạo đơn giả hoặc gửi note thử vào hội thoại khách để giả bằng chứng.
- Luồng phức tạp, thiếu số đo hoặc thiếu artwork vẫn cần chủ xưởng xem ghi chú. Đây là xuất chờ duyệt, không phải tự duyệt sản xuất.
