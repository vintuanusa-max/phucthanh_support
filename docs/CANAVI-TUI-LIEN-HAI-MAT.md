# CANAVI túi liền hai mặt — quy tắc tự động 20/10/2026

- Chỉ áp dụng khi nguồn xác định túi liền hai mặt. Không áp cho hai miếng rời hoặc suy ra từ riêng cụm “in hai mặt”.
- Một artboard chung; trước 0 độ/cữ từ trên, sau 180 độ/cữ từ dưới. Cữ ngang mặt sau đảo mép theo phép xoay.
- Lấy cữ maket và cộng 0,5cm đường may bằng code. Phần miệng túi lấy từ phiếu, không mặc định5cm cho đơn khác. Không dùng phần vải dư chia đều để thay cữ maket.
- Khổ JPG: ngang trước co trừ2cm; cao<70 trừ2,5cm; cao>=70 trừ5cm. Khổ đã sau co không trừ tiếp. Không áp co cho PNG/TIFF PET.
- Giữ artwork/CMYK nguồn, không cộng lại phần tràn viền đã có. JPG CMYK300dpi + AI có artboard nguồn và artboard in; 4 dấu L1cm cho túi, vải mét không định vị.
- Lưu CANAVI hoặc CANAVI HCM2/DESIGNER/{mã mẫu}/{lượt xuất}; đưa preview và liên kết vào ghi chú nội bộ Chatwoot. Không RIP/gửi khách.
- Chưa rõ liền/rời, khổ/cữ, thiếu artwork, profile hoặc cấu trúc vector chưa hỗ trợ: chuyển ghi chú kiểm tra, không đoán/xuất sai.

## Triển khai
- [x] jpg_exports.py: schema và prompt phân biệt cấu tạo/side/vertical_anchor.
- [x] jpg_plan.py: cộng0,5cm, kiểm đủ mặt/hướng xoay/cữ.
- [x] jpg_worker.py: đặt artwork từ mép dưới theo chiều cao thật sau xoay.
- [x] 6 kiểm tra hồi quy, build/import Docker thành công.
- [x] Nạp hub canavi-joined-auto-20261020, khởi động lại worker khi idle.
- [x] PARTNERS đã xuất riêng, note3368. Không phát lại đơn này.
- [ ] Kiểm chứng đầu-cuối một đơn mới đủ nguồn khi phát sinh; không khẳng định mọi cấu trúc AI đều được hỗ trợ.
