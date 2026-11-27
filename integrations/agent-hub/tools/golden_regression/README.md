# Bộ kiểm định & hồi quy chuẩn vàng (Layer 1 + Layer 2)

## Lớp 1 — Kiểm định tự động ngay trong Hub (`hub/quality_audit.py`)
Mỗi lần xuất xong một job JPG hoặc PET (`JpgExports.complete()` / `PetExports.complete()`), Hub tự động chạy kiểm định pixel + kích thước 300 DPI + căn giữa + phát hiện trùng lặp (`0` tốn thêm quota Gemini, `< 1s/job`):
- **Thân túi nền trắng không in (`bag_panel`, `background_mode='none'`)**:
  - Đo 8 điểm lề an toàn: yêu cầu `min_rgb >= 245` (chặn lỗi nền bị nhuộm tím/vàng/xám).
  - Đo bbox mực thực tế (bỏ qua 4 dấu góc chữ L `1 cm`): yêu cầu `|trái - phải| <= 0.25 cm` với mẫu căn giữa.
- **Khổ xuất 300 DPI**: đối chiếu pixel thực tế trên NAS (`/source-archive`) khớp `output_cm` (`<= 0.15 cm`).
- **PET TIFF**: đối chiếu kích thước 300 DPI, kênh `spot_1` không rỗng, giữ `alpha`, `verification.pass == True`.
- **Trạng thái lưu vào DB & Chatwoot private note**:
  - `PASS_VERIFIED`: đạt tất cả kiểm tra.
  - `WARN_DUPLICATE`: đạt chất lượng, kèm cảnh báo trùng file/vải mét trước khi RIP.
  - `FAIL_AUDIT`: phát hiện lỗi pixel/kích thước thực tế -> bật `manual_intervention.required = True` và `production_ready = False` để chặn auto-RIP.

## Lớp 2 — Bộ hồi quy chuẩn vàng (`Run-GoldenRegression.ps1`)
Chạy thủ công bất kỳ lúc nào (sau khi sửa code hoặc khi muốn kiểm tra 9 hồ sơ chuẩn vàng):

### 1. Chế độ `audit-latest` (tức thì, chỉ đọc DB + NAS, không tốn API / không chạy worker)
```powershell
cd \\192.168.1.203\docker\chatwoot\.worktrees\phucthanh\phucthanh\tools\golden_regression
powershell -ExecutionPolicy Bypass -File .\Run-GoldenRegression.ps1 -Mode audit-latest
```

### 2. Chế độ `live-replay` (chạy thật tuần tự qua `/dispatch/{brief_id}`, cam kết `drafts_delta=0`, `deliveries_delta=0`)
```powershell
powershell -ExecutionPolicy Bypass -File .\Run-GoldenRegression.ps1 -Mode live-replay -Cases SLOWING1_DUAL,SLOWING2_JPG
```
Hoặc chạy cả 9 mẫu:
```powershell
powershell -ExecutionPolicy Bypass -File .\Run-GoldenRegression.ps1 -Mode live-replay -All
```

Báo cáo JSON mỗi lần chạy được lưu vào `tools/golden_regression/reports/`.
