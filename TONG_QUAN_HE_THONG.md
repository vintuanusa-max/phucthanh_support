# Tổng quan hệ thống Phúc Thanh
Cập nhật: 23/10/2026, UTC+7. Đây là trang bắt đầu để tra cứu; không phải cam kết mọi trường hợp đều tự xử lý thành công.

## Ba luồng độc lập
| Luồng | Đầu vào | Kết quả | Khi cần kiểm tra |
|---|---|---|---|
| Lên đơn ERP | Tin khách, ảnh ghi lượng, phiếu lệnh | Đơn Lên mẫu, đúng khách và nguồn | Thiếu lượng, mâu thuẫn, chưa chắc trùng |
| Xuất file | Hồ sơ nguồn, maket, PDF/AI/ảnh/link tải được | PNG/TIFF PET hoặc JPG CMYK, AI theo tuyến | Thiếu nguồn, font, kích thước, artwork mơ hồ |
| Duyệt in | Câu khách duyệt + ảnh mẫu nhân viên | Bản tổng hợp vào File In Zalo và WhatsApp | Thiếu ảnh, nhiều mẫu, đổi yêu cầu, kết quả gửi chưa rõ |

Lỗi xuất file không được chặn lên đơn đủ dữ liệu. Duyệt in không tạo lại đơn, không đồng nghĩa duyệt/copy file trong ERP. Gửi File In là gửi nội bộ xưởng được cho phép; AI trả lời và preview vẫn là ghi chú nội bộ Chatwoot. Chưa tự RIP/gửi file cho khách.

## Sơ đồ vận hành
Zalo/WhatsApp/Viber → bộ đọc Windows + checkpoint → Hub + kho ảnh NAS → Chatwoot.
Hub phân luồng: ERP / hồ sơ thiết kế + worker Windows Adobe / hồ sơ chốt in + bộ gửi hai kênh.
Bot khôi phục từ hàng đợi có khóa chống trùng; không xóa checkpoint hoặc reset trạng thái để chữa lỗi.

## Đọc tài liệu nào?
- [Quy trình duyệt in](docs/PRINT-APPROVAL-20261023.md)
- [Quy trình lên đơn ERP](docs/QUY_TRINH_LEN_DON_ERP.md)
- [Quy trình xuất file](docs/QUY_TRINH_XUAT_FILE_IN.md)
- [Checklist chung](docs/CHECKLIST_VAN_HANH_HE_THONG.md)
- [Ánh xạ theo ID nhóm](docs/GROUP-CUSTOMER-MAPPINGS.md)
- [Hai luồng nghiệp vụ và lịch sử thay đổi](docs/HAI_LUONG_DON_HANG_VA_FILE_MAU.md)
- [Điều phối và giám sát](docs/SYSTEM-MONITOR.md)
- [Tiến trình file trong ERP](docs/PRINT_FILE_PROGRESS.md)
- [Bản đồ kỹ thuật](SYSTEM_MAP.md)

## Nơi kiểm tra khi có vấn đề
| Nơi | Dùng để xem |
|---|---|
| http://127.0.0.1:8096/ trên máy bot | Bộ đọc/worker, hồ sơ file chưa xong, chọn lại cụm artwork hoặc yêu cầu xử lý |
| Chatwoot http://localhost:3000 | Tin gốc, ảnh mẫu, ghi chú thiếu dữ liệu và xác nhận gửi nội bộ |
| ERP → đơn → Tiến trình file in | Mẫu đặt/bản xuất, phiên bản, yêu cầu xuất và Duyệt/copy |
| U:\phucthanh_support\config.json | Nhóm bỏ qua, nhân viên nội bộ, erp_customer_mappings |
| W: (NAS n8n_upload) | Nguồn và kết quả theo khách; DESIGNER/{Tên Mẫu}/versions/{job_id} |

Nhóm bỏ qua có ưu tiên hơn ánh xạ khách. Nhóm mới chưa ánh xạ → KHACH LE. Không thay đổi đơn đã tạo khi sửa ánh xạ.

## Giới hạn và an toàn vận hành
- Máy cần đăng nhập, ứng dụng/phiên hợp lệ và mạng hoạt động; worker Adobe có thể chờ hộp thoại/font.
- Watchdog hỗ trợ mở lại tiến trình, không bảo đảm mọi tin đã được đọc hoặc mọi job đã hoàn tất. HTTP200 không chứng minh nghiệp vụ đúng.
- Kết quả ghi/gửi uncertain phải đối chiếu, không retry mù. Không cam kết chống sót tuyệt đối; chưa có bằng chứng một lượt quét hồi tố toàn bộ mỗi giờ.
- Bộ gửi Zalo hiện xác minh theo phiên bản26.10.20. Phiên bản đổi cấu trúc có thể cần cập nhật; không coi tự tìm đường dẫn là tự tương thích mọi API gửi.
- ERP sản xuất chỉ restart khi chủ xưởng thực hiện/cho phép. Docker giữ bản đang chạy + một dự phòng; không dọn volume dữ liệu.
- Không đưa API key, token, khóa phiên vào tài liệu hoặc Git.
