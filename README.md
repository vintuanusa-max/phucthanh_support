# Phúc Thành Support — bot Zalo / WhatsApp

> Repo gồm bot web gốc và [mô-đun tích hợp mới](integrations/agent-hub/README.md) cho Chatwoot, Gemini, Desktop, NAS, ERP và duyệt in hai kênh. Các kế hoạch trong `docs/` là tài liệu lịch sử; xem README của mô-đun tích hợp để biết trạng thái mới.
> Cấu hình vận hành, khóa, phiên đăng nhập và dữ liệu khách hàng được giữ riêng, không đưa vào Git.

Bản tái cấu trúc của `phuc_thanh_zalo` (Giai đoạn 1). Hành vi giữ nguyên bản ngày
2026-10-12 (đã gồm bản sửa image guard). Lệnh chạy không đổi:

```
py -m uvicorn main:app --host 0.0.0.0 --port 8000
```

`manager_api.py` (cổng 9000) vẫn khởi động `main:app` như trước.

## Cấu trúc

```
main.py                 điểm vào: log -> API -> ERP bridge -> các kênh -> OpenClaw
core/
  runtime.py            trạng thái dùng chung (SYSTEM_STATUS, queue, lock, event)
  settings.py           đọc config.json (tự nạp lại khi file đổi)
  policy.py             chính sách theo kênh: allowed(channel, name, action)
  messages.py           IncomingMessage + publish/subscribe (móc cho Chatwoot)
  text_rules.py         nhận diện đơn, so tên, thư mục khách (thuần, test được)
  history.py            lịch sử tin đã quét
  extraction.py         Gemini trích đơn từ ảnh
  intake.py             đưa đơn vào ERP bridge
  downloads.py          tải link Drive / link chia sẻ
  integrations.py       n8n, OpenClaw
  logging_tee.py        ghi log ra zalo_bot.log
channels/
  base.py               giao diện chung của một kênh
  zalo_web.py           Zalo Web (CDP 9222): quét, gửi, chụp, broadcast
  whatsapp_wpp.py       WhatsApp Web (CDP 9223) + WPPConnect
api/routes.py           endpoint HTTP (đường dẫn như cũ)
erp_bridge*.py, communication_*.py, config_manager.py, manager_api.py  — giữ nguyên
```

Thêm kênh mới: tạo module trong `channels/` theo `channels/base.py`, đăng ký trong
`channels/__init__.py`, thêm nhánh trong `core/policy.allowed()`.

## Khác bản cũ

- Bỏ luồng AppSheet chết trong `process_extracted_screenshot_async` (chỉ chạy khi
  nguồn khác zalo/whatsapp — không bao giờ xảy ra), cùng khoá AppSheet và Gemini
  viết cứng trong code.
- `/api/screenshot` khi lỗi trả `{"status":"error","msg":...}` (bản cũ trả `null`
  do lệnh return nằm sau return).
- Kiểm tra `whatsapp_disable_reply_groups` gộp về `core.policy.whatsapp_reply_disabled`.
- Bộ quét gọi `core.messages.publish(...)` cho mỗi tin mới; chưa có subscriber nên
  không có tác dụng.
- `requirements.txt` thêm `gdown`, `Pillow` (code đã dùng từ trước).

## Cấu hình (không có trong git)

Copy từ máy đang chạy, không tạo lại: `config.json`, `erp_config.json`,
`bot_config.json`, `data/erp_integration/`, `processed_history.json`,
`whatsapp_history.json`. Mẫu: `config.example.json`, `erp_config.example.json`.

## Test

```
python -m unittest discover -s tests
```

Test không mở trình duyệt, không gọi mạng. Chưa kiểm thử với Zalo/WhatsApp thật.
