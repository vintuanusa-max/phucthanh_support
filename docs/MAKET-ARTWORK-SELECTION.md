# Quy tắc đang áp dụng: chọn artwork PET theo artboard và maket
Cập nhật 24/10/2026. Đây là quy tắc hiện hành; thay thế cách gửi hàng trăm ảnh cụm theo lô cho AI.

## Quy trình tự động cho hồ sơ PET mới đủ điều kiện
1. Đọc nguồn AI/PDF, maket và yêu cầu khách. Phân biệt artboard (khổ trang) với artwork (hình cần in).
2. Bước khoanh vùng chỉ nhận ảnh toàn artboard tương ứng để tránh dùng tọa độ từ ảnh khác. Xác định vùng logo/chữ cần lấy; cùng hình ở nhiều góc nhìn không mặc định là nhiều mẫu.
3. Code lọc theo tọa độ và cấu trúc cha–con. Giữ nguyên nhóm chứa chữ/path/chi tiết trắng; không loại đối tượng chỉ vì là PathItem. Inventory nhiều đối tượng chỉ dùng để lọc bằng code, không gửi toàn bộ preview cho AI.
4. Chỉ gửi tối đa 12 ứng viên phù hợp sang bước đối chiếu chi tiết với đủ nguồn maket. Vượt giới hạn, vùng không rõ hoặc tọa độ không khớp: báo kiểm tra nội bộ, không quay lại quét hàng trăm cụm. Bộ khoanh vùng giới hạn 4 artboard và 8 ảnh nguồn; worker hiện vẫn yêu cầu nguồn PDF-compatible một trang.
5. Chọn đúng artwork và kích thước theo nguồn; giữ tỷ lệ, chữ và chi tiết trắng. PNG/TIFF cắt sát phần hình, giữ khoảng cách bên trong, nền trong suốt và kênh mực trắng. Không cữ, không trừ co, không lật gương. Quy tắc cữ/co thuộc JPG in túi, không áp vào PET.
6. Kiểm chứng PNG trước bước TIFF. Chống xuất lặp cùng bộ ID cụm và kích thước. Cache kết quả AI; lượt chưa rõ kết quả không tự gọi lại.
7. Lưu file trong DESIGNER của mẫu; đưa preview vào ghi chú NỘI BỘ Chatwoot để chủ xưởng duyệt. Không tự RIP hoặc gửi khách. Không tạo lại đơn ERP từ bước xuất file.

## Điều phối và giới hạn
Trang điều phối hiện ảnh artboard có khung vùng chọn, cụm artwork, kích thước, lý do chưa xuất và cảnh báo font. File nhiều đối tượng có thể vượt timeout đọc Illustrator; ảnh liên kết chưa nhúng, font thiếu hoặc nguồn không phù hợp phải được ghi rõ, không tự xem là đạt.

## Checklist xác nhận
- [x] Hub đang dùng artboard_regions_v5_partial; không còn vòng gọi maket_filter theo lô.
- [x] Chặn trên 12 ứng viên trước bước chọn chi tiết; giữ cụm cha và chi tiết trắng.
- [x] Kiểm thử tọa độ, cha–con và giới hạn ứng viên.
- [x] Thử thực tế GV2VB-100.10: 376 metadata → 2 ứng viên → chọn cụm 0.1.
- [x] PNG/TIFF 5,8 × 5,038 cm, 685 × 595 px; spot_1 có dữ liệu, alpha giữ nguyên.
- [x] Preview nội bộ Chatwoot hội thoại 10, tin 5547.
- [x] Nguồn code Hub và Windows worker đã lưu; kiểm tra lại bản đang chạy ngày 24/10/2026.

## Dấu vết lần thử
File: CANAVI/DESIGNER/FileinPETGV2VB-10010/versions/3b74594cbd512c0dea7e2869caa4ff255c44a0a1c497bcc53c104c02c71a5d17.
Luồng cũ đọc từng lô 24 cụm đã bị thay thế. Những lượt thử cũ bị hủy không được tự chạy lại. Các giới hạn trên là điều kiện dừng để kiểm tra, không phải cam kết mọi nguồn đều tự xuất thành công.

## Thông báo theo mẫu — 24/10/2026
Đã bỏ thông báo riêng của đề xuất DESIGNER, đối chiếu file nguồn, hồ sơ tổng hợp thành công và lỗi PET/native trực tiếp. Dữ liệu nguồn vẫn lưu và hiển thị source_checks trong điều phối. Bộ giám sát gom các lỗi cùng hồ sơ hiện hành thành một bản, Engine.effect chống gửi lặp; preview xuất cuối vẫn giữ. Không đọc riêng JXL trong artwork_checks; khi có AI/PDF dùng ảnh làm ngữ cảnh và không tạo thêm kiểm tra raster trong cùng hồ sơ. Bỏ qua hồ sơ cũ không còn hiện hành. Kiểm thử hai lỗi cùng mẫu -> một tin, quét lại -> không tin mới đã đạt.
SERE đã xuất riêng home resort theo xác nhận của chủ xưởng; preview nội bộ tin 5597, hội thoại 10. Phần serena RIVERSIDE thân túi thiếu nguồn đã ghi nội bộ. Không tự thay logo, không xác nhận toàn mẫu hoàn tất và không chạy lại phần đã xuất.

## 2026-10-24 — PET native: xuất từng phần
- [x] Đọc artboard trước, khoanh vùng; không gửi hàng trăm cụm cho AI.
- [x] `blocked_parts` ghi vị trí thiếu artwork/kích thước; không chặn vị trí đã đủ nguồn.
- [x] Kiểm chứng PNG chỉ theo vị trí đã chọn; vẫn chặn sai logo/chữ/font/kích thước của vị trí đó.
- [x] Gom thiếu nguồn theo hồ sơ; preview ghi rõ xuất một phần, không báo toàn mẫu hoàn tất.
- [x] Điều phối hiển thị phần cần bổ sung; parent đã chọn không bị báo worker kẹt giả.
- [x] Giữ khóa AI/child job/Chatwoot chống trùng; không tự phát lại hồ sơ cũ.
- [x] Kiểm thử phần đúng + phần lỗi, lỗi toàn nguồn, trùng artwork, trùng vị trí và sai tỷ lệ.
- Chỉ PNG/TIFF artwork: không cữ/co vải; nền trong suốt, mực trắng. Chưa RIP/gửi khách.
- SERE đã xuất home resort; phần serena RIVERSIDE thiếu nguồn ghi nội bộ. Không chạy lại file đã xuất.
- Phạm vi bản này: chọn artwork AI/PDF native PET; không thay đổi quy trình JPG.

## Quy trình hiện hành cho đơn mới — phần đủ nguồn xuất trước

Hai luồng độc lập:
1. **Lên đơn ERP:** đủ thông tin đặt hàng/số lượng thì xử lý tạo đơn Lên mẫu theo quy tắc và ánh xạ hiện có, kiểm tra chống trùng. Thiếu nguồn thiết kế không chặn luồng lên đơn. Luồng xuất file không tạo lại đơn ERP.
2. **Xuất file PET từ AI/PDF:** đối chiếu phiếu, maket và nguồn; đánh giá từng artwork/vị trí riêng. **Phần đủ nguồn và kích thước thì xuất trước**, kể cả khi vị trí khác còn thiếu. Phần thiếu không được đoán hoặc thay bằng logo khác: ghi rõ vị trí, lý do và thông tin cần bổ sung trong nội bộ Chatwoot và điều phối.

Mỗi phần xuất vẫn phải đúng artwork/phiên bản, chữ, chi tiết trắng, tỷ lệ và kích thước. Lỗi toàn nguồn như chưa xác định đúng mẫu hoặc công nghệ vẫn dừng để kiểm tra. Không có phần nào đủ nguồn thì chỉ báo cần xử lý, không tạo file giả. Preview ghi rõ xuất một phần và phần còn thiếu, không báo hoàn tất toàn mẫu.

Thông báo lỗi cần xử lý được gom theo hồ sơ mẫu hiện hành; chỉ gửi thay đổi có ý nghĩa hoặc preview mới. Giữ khóa chống xuất trùng, chống gọi AI trùng và chống gửi ghi chú lặp. Kết quả lần trước chưa rõ không tự gọi lại. File lưu trong DESIGNER; preview chỉ là ghi chú nội bộ Chatwoot chờ duyệt, chưa RIP/gửi khách.

### Checklist triển khai và dọn tồn
- [x] Tách luồng lên đơn khỏi luồng xuất file; bản sửa này không đổi logic ERP.
- [x] PET native xuất các vị trí đủ nguồn trước, tách danh sách thiếu `blocked_parts`.
- [x] Giữ kiểm chứng từng PNG trước TIFF; không bỏ kiểm tra vì xuất một phần.
- [x] Giữ nền trong suốt, mực trắng, cắt sát artwork và khoảng cách chi tiết; không cữ/co/lật gương trong PET.
- [x] Hiển thị phần thiếu trong điều phối và ghi chú nội bộ; chống báo lặp.
- [x] Kiểm thử phần đúng + phần lỗi, lỗi toàn nguồn, trùng artwork/vị trí và sai tỷ lệ đã đạt.
- [x] Đã dọn 151 hồ sơ tồn: 102 chờ kiểm tra và 49 chưa bắt đầu; đưa vào lịch sử, không xóa vật lý dữ liệu.
- [x] Đánh dấu `dispatch_archived_at`; `WorkflowControl.current()` trả false cho hồ sơ đã dọn để ngăn tự chạy lại.
- [x] Sao lưu SQLite trước khi dọn; giữ đơn ERP, tin Chatwoot, file đã xuất và dấu vết chống trùng.
- [x] Kiểm tra sau dọn: danh sách chờ 0, lịch sử 170, Hub health OK. Đây là số tại thời điểm dọn, đơn mới có thể làm tăng danh sách.
- [ ] Theo dõi một đơn mới thực tế đi hết luồng tự động sau bản sửa; không tự chạy lại 151 hồ sơ để thử.

Phạm vi xuất từng phần ở bản này là PNG/TIFF native AI/PDF. Không suy diễn rằng quy trình JPG đã được sửa theo cùng cơ chế. Các quy tắc JPG CMYK hiện có vẫn giữ nguyên.
## Ưu tiên group đầy đủ — thử lại OC (24/10/2026)
- Vùng AI là gợi ý, không phải biên cắt bắt buộc. Ngoài đối tượng nằm trọn vùng, xét GroupItem/RasterItem/PlacedItem giao vùng ít nhất 20% diện tích đối tượng, không quá 4 lần diện tích vùng và 35% artboard. Giữ group cha thay các nét con cùng cây; vẫn tối đa 12 ứng viên.
- Hình ứng viên phải đối chiếu với maket và kiểm chứng PNG. Không tự xuất chỉ vì giao vùng, không chọn group bao cả sản phẩm/đường đo.
- [x] Kiểm thử vùng OC sai ban đầu vẫn chọn được group đầy đủ 0.8; loại group toàn artboard.
- [x] Worker lưu AI editable riêng tự động cùng lượt PNG, giữ vector và khoảng cách chi tiết, không sửa file nguồn. AI được lưu ở thư mục phiên bản DESIGNER, chống ghi đè.
- [x] OC chạy lại tự động: scan 30e8f056 → chọn group 0.8 → PNG/TIFF e8d1d7b3; không region_correction_audit, không can thiệp vùng/ID. PNG 2362 × 1163 px (~20 × 9,847 cm), alpha và spot_1 đạt. AI editable tự lưu 20 × 9,834 cm, 40 path vector, không raster. Preview Chatwoot 5663, hội thoại 10. File nguồn giữ nguyên hash.

## 2026-10-24 — Gemini Pro chọn artwork có ảnh
- [x] Khoanh vùng artboard, chọn group và đối chiếu lựa chọn dùng `gemini-2.5-pro`.
- [x] Gửi PNG toàn artboard, ảnh nguồn maket, preview group trên nền tối và bounds Illustrator; không chỉ gửi cây JSON.
- [x] Lọc tại máy tối đa 12 cụm, ưu tiên group đầy đủ; không gửi hàng trăm cụm.
- [x] Lưu model và số ảnh theo lượt; giữ kết quả cũ, không tự gọi lại lượt chưa rõ kết quả.
- [x] Kiểm thử routing, chống gọi trùng, chọn group OC/TP; build import đạt.
- [ ] Đánh giá chất lượng thực tế Pro trên hồ sơ mới (không khẳng định chính xác tuyệt đối).
- Giữ preview nội bộ; không RIP/gửi khách. Hồ sơ đã hoàn tất/dọn không tự chạy lại.

### TP Pro end-to-end — 2026-10-24
- [x] Owner-requested fresh replay c0a8b2ce: Pro region (1 image), Pro selection (4 images), group 0.9; no manual state/group corrections.
- [x] Export d2cf7d00: PNG/TIFF, alpha preserved, spot_1 nonempty; internal Chatwoot preview 5671, conversation 10.
- [x] Editable AI retains original mockup artboard and adds vector artwork artboard 20.88 x 11.855 cm. Original NAS source unchanged.
- PNG raster tight bounds: 20.879 x 11.845 cm at 300 dpi; preserve relative layout. No RIP/customer send/ERP write.

### Pro stability batch — 2026-10-24
Three fresh automatic replays, source contexts reused; no manual group/state corrections.
- OC: PNG/TIFF and original-plus-artboard AI completed; internal preview 5684; group 0.8.
- JOSEON PDF: PNG/TIFF and original-plus-artboard AI completed; internal preview 5688. Tight PNG 24.003 x 21.387 cm; alpha and spot_1 passed.
- GV2VB-100: FAILED selection. Selected 0.2.73 is dimension line 15 cm (confirmed candidate preview and rendered output). Post-export verifier blocked TIFF. Do not approve this output. Raw run retained for investigation.
Result: 2/3 completed, not evidence of full stability. No ERP writes, RIP or customer sends. Must investigate localization/selection rejecting measurement-only groups before claiming reliable automation.

### Deferred investigation: GV2VB-100.10
Owner requests marking only, no fix or rerun yet. Maket includes multiple product views (owner suspects this contributes to wrong selection). Confirmed symptom: selected dimension group 0.2.73, output 15 cm line; verifier blocked TIFF. Root cause not yet established. Continue other samples unchanged, consolidate fixes later.

### Pro evaluation batch 2 — unchanged pipeline
Owner requested collecting failures before a combined fix. No code changes or manual group corrections.
- SERE d085eb10: review; Pro region maps to zero native groups. No export. Investigate coordinate/group association later.
- DINH a079302b: automatic PNG/TIFF + AI generated, preview 5698, but HUMAN VISUAL CHECK FAILED: PNG clips right/bottom artwork; automatic verifier falsely passed. Not approved for print. Internal correction warning posted. Original-plus-added-artboard AI has two pages.
- Cumulative six distinct Pro samples: TP/OC/JOSEON completed; 100 wrong dimension group blocked; SERE zero-group region; DINH clipped output falsely passed. This is a small diagnostic sample, not a reliability estimate.
- Deferred fixes: multi-view localization; dimension-group rejection; bounding/export clipping; verifier false acceptance. Preserve raw evidence, no RIP/customer sends or ERP changes.

### 2026-10-24 — PET native group size (owner instruction)
- Native AI/PDF PET selection: Gemini chooses artwork content only; Illustrator bounds determine physical size. Do not infer width/height from bag offsets, fabric size or A4. No native automatic hat resizing in this path; manual sizing remains separate.
- Removed dimension reconciliation from the native selection/review prompt and checks. Source group bounds override model size values; wrong artwork, missing impactful fonts, background wrappers and duplicate selection remain guarded.
- PNG alpha trim preserves existing pixels at 300 DPI; it must not enlarge remaining artwork back to the old group width. Transparent outer padding can disappear, but artwork scale and internal distances stay unchanged.
- PNG aspect validation compares height against requested native width rather than rounded raster width, avoiding magnified rounding error on narrow tall lettering (SERE).
- Updated native_auto.py, pet_exports.py, native_selection.py; backups suffix before-pet-native-size-20261024. Runtime image pet-source-size-20261024.
- Regression checks passed: native bounds override model dimensions/margins; alpha crop does not resize; white artwork retained; wrong-artwork gate still blocks.
- Fresh automatic runs queued for GV2VB-100.10 and SERE. No old output overwrite, ERP mutation, RIP or customer message.
- Completed source-size trials: GV2VB-100 group 0.1, editable board 5.8×5.0cm; PNG/TIFF 682×592 at 300 DPI, preview 5734. SERE group 0.1.24.0, editable board 1.5×11.5cm; PNG/TIFF 178×1358 at 300 DPI, preview 5735. Both TIFF reports confirm spot_1 nonempty and alpha preserved. Source SHA256 unchanged; editable AI has original page plus one new page. No manual selection/state intervention in these runs. Small raster extent differences reflect Illustrator rasterization/alpha crop; no resampling after crop. Both outputs await owner approval; this two-sample check is not a universal accuracy guarantee.

### 2026-10-24 — five older PET source-size automatic trials
- [x] Default native PET rule active: select correct artwork group, preserve native scale and internal spacing; no bag-offset/fabric/A4 inference. Transparent trim only, no resampling. PNG/TIFF alpha and spot_1; original-plus-new-artboard editable AI.
- [x] Explicit historical replay marker owner-pet-source-size-old5-20261024. JOSEON, OC, TP, SEE, CHERRIES: five source files, six exports (SEE body and strap). No manual group/state changes during processing.
- [x] All six TIFFs completed and archive hashes match manifests; spot_1 nonempty and alpha_preserved true. All six editable AIs contain original artboard plus export artboard. Original downloaded source SHA256 matches source asset.
- [x] Visually inspected all six artwork PNGs; artwork only, no bag/dimension frame. Outputs await owner approval; five-file result is not a universal accuracy guarantee.
- JOSEON: 657be558, Chatwoot 5737 (conversation 10); PNG tight extent 23.487 x 20.930 cm.
- OC: f39b6065, Chatwoot 5738 (conversation 10); PNG 20.007 x 9.847 cm.
- TP: 187960cd, Chatwoot 5739 (conversation 10); PNG 20.879 x 11.853 cm.
- SEE: 9a96c303 / 5a6d06e3, Chatwoot 5740 / 5741 (conversation 10); body 11.455 x 11.430 cm, strap 2.117 x 11.362 cm.
- CHERRIES: 970708ee, Chatwoot 5742 (conversation 16); PNG tight extent 12.751 x 21.006 cm. Native group has transparent padding; crop preserves source pixel scale.
- SEE/CHERRIES used separate trial briefs; original archived briefs/jobs remain archived. No ERP writes, RIP, customer sends, old-output overwrite or bulk replay.

### 2026-10-24 — SEE logo fill correction (supersedes prior visual acceptance)
- Prior SEE body export 9a96c303 / preview 5740 is incomplete: selected child 0.25.0 omitted colored circular fills. Do not use that body output. Strap 5a6d06e3 / preview 5741 remains the previous valid output.
- [x] Large Path/CompoundPath fill no longer excludes the complete parent group. Ambiguous wrappers offer parent and immediate child alternatives for visual selection; dimension filtering and 12-candidate ceiling remain.
- [x] Selection and verification explicitly preserve colored logo fills/rings. Transparency means outside the artwork, not removing fills inside a logo.
- [x] Artboard localization preview includes a coordinate grid (analysis only). Reconciliation completeness applies to selected artwork, not missing other positions.
- First retry localized incorrectly and was blocked; second chose correct body but blocked on missing strap. No file was exported by those attempts; no manual group override.
- [x] Final automatic replay d01e917d selected complete group 0.25. Export 14ff42a3: original group 14.84794 x 15.04904 cm; PNG 1754 x 1779 at 300 DPI. TIFF hash matched, alpha preserved, spot_1 nonempty. Editable AI has original plus new artboard, source hash unchanged.
- [x] Human visual inspection confirms turquoise fill and pink rings, cream lettering retained. Internal Chatwoot preview 5746 (conversation 10); requires owner approval. This replay exported body only; retain previous strap, do not interpret model's missing-strap report as absence from source.
- Runtime image pet-logo-complete-20261024; native_auto.py backed up before-logo-fill-20261024 and persisted to both Hub source and support mirror. No ERP changes, RIP or customer send.

### Quy trình PET được chủ xưởng duyệt — 2026-10-24
- [x] Áp dụng mặc định cho đơn PET mới: đọc maket và AI/PDF, tự chọn group hoàn chỉnh; giữ nền màu/vòng viền thuộc logo, chữ và chi tiết trắng.
- [x] Xuất nguyên kích thước native Illustrator; không suy từ cữ túi, không trừ co vải, không lật gương. Cắt sát alpha ngoài artwork mà không resize hoặc đổi khoảng cách chi tiết.
- [x] PNG nền ngoài artwork trong suốt; TIFF có mực trắng theo workflow hiện hành. AI editable giữ bản gốc và thêm artboard xuất để đối chiếu.
- [x] Phần đủ nguồn xuất trước; phần thiếu ghi rõ riêng. Preview chỉ ghi chú nội bộ Chatwoot để duyệt; chưa RIP/gửi khách.
- [x] Chống xuất trùng theo job/phiên bản, không ghi đè đầu ra cũ và không tự chạy lại hồ sơ đã dọn.
- Chủ xưởng đã xem và chấp nhận bản SEE sửa đủ nền màu (preview 5746). Kết quả thử không đồng nghĩa mọi nguồn mới luôn chọn đúng; giữ kiểm chứng và luồng duyệt nội bộ.
