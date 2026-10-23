# Illustrator — chọn cụm artwork và xuất PET nội bộ

Cập nhật 23/10/2026. Triển khai thực: Hub `native-consistency-20261023`, Windows ArtworkInspector, trang http://127.0.0.1:8096/.

## Đã làm
- [x] Đọc PDF/AI tương thích PDF một trang bằng Illustrator trên bản sao; không sửa nguồn.
- [x] Hiện tối đa 64 đối tượng/cụm (sâu 3 cấp), ảnh PNG nền xám, kích thước thật, số chữ sống. Clipping group giữ nguyên cụm.
- [x] Đối chiếu font PostScript trong PDF với font Illustrator; ghi tên thiếu. Chặn chọn cụm có chữ sống nếu nguồn thiếu font. Không tự thay font/cài font.
- [x] Chủ xưởng chọn một hoặc nhiều cụm cùng vị trí, nhập ngang cm và ghi chú; giữ tỷ lệ, không lật gương. Chặn chọn cả cha và con.
- [x] Native PNG chuyển vào pipeline Photoshop PET có sẵn: alpha + spot_1, trắng không contract, màu contract 1px, 300dpi; kiểm tra pixel độc lập.
- [x] Preview/PNG/TIFF vào ghi chú nội bộ Chatwoot; bản gốc và manifest ở folder khách/DESIGNER/mã/versions/job. Chưa RIP, gửi khách hay duyệt/copy ra folder sản xuất.
- [x] SHA256 nguồn/PNG/TIFF, job idempotent, không chạy chồng với pipeline khác; phiên bản hồ sơ cũ không nhận kết quả. Không tạo/sửa đơn ERP.
- [x] 6 kiểm thử DB tạm: chọn trùng, cha/con, font thiếu + chữ sống, ID sai, nguồn ngoài hồ sơ, DPI sai.

## JOSEON thực tế
- Brief `223865b67e8a84ee197dd351633e2db8036257d6df9dd97930a9346439dcbbf2`.
- Nguồn `GV2VB-JOSEON.10.pdf`, SHA256 `010ad83e0a3e59be2fa930ec4e77943b5530049b46cb17622bbeab842b949346`.
- 31 cụm; chọn `0.12`: JOSEON × Coca-Cola + nhân vật Better Together, 0 chữ sống.
- Nguồn có TimesNewRomanPS-BoldItalicMT, SegoeUIVariable; kiểm tra hiện tại đều có. Chủ xưởng đã từng thấy hộp thoại font, vẫn ghi trong ghi chú đối chiếu.
- Ngang đề xuất 24cm theo maket 34 - 5 - 5; cao giữ tỷ lệ khoảng 22,66cm. Cao suy từ cữ 35 - 10,5 - 3,6 = 20,9cm, chênh khoảng 1,76cm cần duyệt. Phiếu nói A4 khác maket: chưa sản xuất.
- File raster thực 2833×2675px, 300dpi, 23,986×22,648cm (làm tròn pixel/render Illustrator).
- Job `e4d7adbd4bff7feb544d3d68962676ec2eebb7320fc9586be7c9d65f12d85c61`, PET done, ghi chú riêng Chatwoot #5004.
- NAS `CANAVI HCM2/DESIGNER/GV2VB-JOSEON10/versions/e4d7adbd4bff7feb544d3d68962676ec2eebb7320fc9586be7c9d65f12d85c61`.
- TIFF SHA256 `cf6dea15c22037f501bf14744722495f36508d77b43bcec8d7b712139844e4fc`.
- Một lượt scan gặp lỗi tài nguyên: tái dùng 31 preview cũ, kiểm chứng lại toàn bộ ID/type/bounds/text. TIFF đã có được kiểm tra lại và gửi, không chạy lại Photoshop. Worker giới hạn OpenBLAS/OMP 1 luồng để giảm cấp phát bộ nhớ.

## Giới hạn cần hiểu đúng
- Từ mốc enabled-at: hồ sơ PET mới có PDF/AI tương thích PDF được tự xếp hàng native. Hồ sơ cũ không tự phát lại; chạy lại có mã lượt riêng. Các nhóm vẫn tuân chính sách đọc hiện có. Raster/JPG giữ nhánh riêng.
- AI chọn tối đa 8 vị trí, mỗi vị trí một PNG/TIFF. Điều phối chọn vị trí rồi đổi cụm/kích thước được. Chưa có editor kéo thả, thay màu hay sửa chữ.
- PDF nhiều trang, AI không PDF-compatible, ảnh liên kết ngoài, inventory vượt giới hạn hoặc trạng thái không rõ vẫn cần kiểm tra.
- Dialog được tắt trong lệnh trên bản sao và khôi phục sau đó; không Alt+F4 toàn ứng dụng/tài liệu của nhân viên.
- Hoàn tất PET có cụm native vẫn truy cập được để chọn lại; các hồ sơ hoàn tất thông thường giữ ẩn.

## Mã nguồn
Hub: hub/native_selection.py, hub/dispatch_control.py, hub/app.py.
Worker Windows: ArtworkInspector/native_local.py, native_worker.py, worker.py; dùng native_patterns.jsx_run và pet_worker hiện có.
Dashboard: SystemMonitor/dispatch.html. API điều phối dùng admin, adapter dùng ingest, frontend không chứa key; proxy loopback có Origin/Host/CSRF.

## Tự động native — 23/10/2026
- [x] Đọc đủ phiếu/maket/preview PDF, ảnh từng cụm Illustrator có nền xám thấy chữ trắng.
- [x] Gemini chọn ID native, xác minh cùng mẫu; ID không tồn tại, chồng cha/con, font thiếu ảnh hưởng chữ sống, inventory thiếu đều chặn.
- [x] Cữ ngang được lưu thành số đo tổng/trái/phải có nguồn, code tính phép trừ; giữ tỷ lệ artwork.
- [x] PNG thực xuất được AI kiểm tra độc lập trước TIFF; khác artwork/kích thước chặn. Cữ lệch/A4 khác maket ghi cảnh báo bản thử để duyệt.
- [x] Dashboard hiện AI tự chọn + trạng thái, vị trí, checkbox để chọn lại.
- [x] Lưu kết quả AI trước bước tiếp theo; gián đoạn chuyển kiểm tra, không tự gọi lặp gây phí.
- [x] 17 kiểm thử logic/SQLite tạm đã đạt; không đụng đơn ERP.
- [x] JOSEON xuất lại PNG/TIFF, Chatwoot #5012. AI tự chọn 0.12; code tính ngang 24cm; thực 23,986 × 22,648cm, 300dpi.
- [x] Đã bổ sung đối chiếu tự động có giới hạn cho kết quả AI mâu thuẫn (kiểm chứng 23/10 phía dưới). Lịch sử trước bản sửa: lần thử AI trả same_design=false nhưng issues rỗng; đã dùng một lượt đối chiếu riêng xác minh cùng mẫu rồi tái dùng plan, không chọn thủ công. Cảnh báo A4 do AI diễn giải sai đã có ghi chú nội bộ đính chính. Các lần tự mâu thuẫn tương tự hiện chuyển review, không xuất bừa.
- Kết quả mới: CANAVI HCM2/DESIGNER/GV2VB-JOSEON10/versions/4fbedbba7318cc5fb4d2f37e226fdf2aef918205e3b2af254704a34ef29fee20. Nguồn không thiếu font; chưa RIP/gửi khách.
Mã mới: hub/native_auto.py; pet_exports.prepare nối enqueue; app lifespan có monitor riêng.

## Sửa kết quả AI mâu thuẫn — 23/10/2026 13:49
- [x] Tách cùng nội dung artwork/phiên bản khỏi cảnh báo cữ/A4. Không tự sửa cờ false thành true.
- [x] Kết quả bị chặn/không nhất quán được đối chiếu nguồn thêm tối đa 1 lần ở bước chọn và 1 lần ở bước kiểm PNG (tối đa 4 lời gọi tổng gồm 2 bước chính).
- [x] 4 kiểm tra bắt buộc: công nghệ PET, nội dung artwork, đủ nguồn/chi tiết, kích thước. Mỗi kết luận có lý do và nguồn hợp lệ. fail/unknown hoặc còn blocker => review; không xuất.
- [x] Lưu trạng thái started trước gọi và result sau gọi; cache theo job/bước. Timeout/khởi động lại không tự gọi trả phí lần nữa.
- [x] Font/ID nguồn/cụm cha-con/tỷ lệ/kích thước pixel vẫn là chốt kiểm tra code, không bị kết luận AI ghi đè.
- [x] Điều phối có mục Kết quả đối chiếu lại AI; lỗi thiếu nguồn/font/artwork/kích thước hiển thị lý do và ghi chú riêng Chatwoot.
- [x] 30 kiểm thử DB tạm/logic đạt, gồm nguyên mẫu same_design=false nhưng issues rỗng, true có blocker, nguồn giả, timeout không retry, font thiếu, phép trừ cữ.
- [x] Một lượt Gemini thật trên nguồn JOSEON trong DB tạm tự kết luận cùng mẫu, giữ 0.12; ngang 24, cao 22.661358cm. Không tạo lại PNG/TIFF/đơn/ghi chú.
- [x] Hub health OK; worker 3 kênh còn chạy. Chưa RIP/gửi khách.
Giới hạn: kiểm thử không bảo đảm AI đúng với mọi file mới. Kết luận không chắc vẫn đưa kiểm tra; không có vòng lặp gọi lại vô hạn. Các hồ sơ cũ không tự phát lại.

## JOSEON chạy từ đầu qua bản mới — 23/10/2026
- [x] Owner yêu cầu xuất lại sau khi xóa PNG/TIFF. Lượt cc2ffbb33dac2296f5df1a5c2d4b603b1de585fbe877e1cc1734e1369172f6d7 tự đọc Illustrator, tự chọn 0.12, tính ngang 24cm; không truyền ID/kích thước đã chọn.
- [x] Hai lời gọi AI (selection + PNG check) đạt ngay; không cần reconcile hoặc sửa cờ thủ công.
- [x] TIFF done; Chatwoot private #5016; folder versions/dc03c8b2609bee79ed29f86232f7b5ed5e4d69f47223fe298de9de4bc1fcce94. PNG 2833×2675px 300dpi, 23.986×22.648cm.
- [x] Không tạo lại ERP, không RIP/gửi khách. Cảnh báo cữ dọc AI còn diễn giải mốc đo chưa nhất quán, bản thử cần chủ duyệt; không coi là đã chốt cữ sản xuất.

## Quy tắc ưu tiên mới — PET chỉ artwork (23/10/2026)
- [x] PNG/TIFF chỉ lấy artwork đã chọn đúng kích thước, giữ tỷ lệ, nền trong suốt và spot trắng; không cữ bố trí túi, co vải, đường may hay định vị.
- [x] PetExports.ask tách khỏi CANAVI_ARTWORK_POLICY của JPG; không tự thêm yêu cầu cảnh báo cữ.
- [x] Nội dung preview PET chỉ ghi kích thước artwork đã tính và font liên quan; không xuất các cảnh báo bố trí AI tự sinh. Raw AI vẫn lưu audit, lỗi thiếu/sai artwork/kích thước/font vẫn chặn.
- [x] Cữ chỉ áp dụng JPG in túi, không sửa module JPG. Không phát lại file/đơn đã xong.
- [x] 18 kiểm thử hồi quy đạt; module PET biên dịch thành công; hub pet-artwork-only-20261023.
Quy tắc này thay yêu cầu cảnh báo cữ dọc PET trong các mục lịch sử phía trên. Ghi chú Chatwoot cũ giữ làm lịch sử, ghi chú mới dùng quy tắc mới.

## PET cắt sát artwork — 23/10/2026
- [x] native_selection.trim_artwork cắt alpha_bbox ngoài và resize đều theo ngang chuẩn 300dpi; giữ khoảng trống bên trong artwork và chi tiết trắng.
- [x] Code kiểm kích thước sau cắt; AI chỉ kiểm nội dung, không so với khung nhóm rỗng cũ. JPG không đổi.
- [x] 3 kiểm thử cắt alpha + 18 hồi quy đạt. JOSEON PNG/TIFF đã tạo lại, private note #5093. PNG 2835×2526px, alpha_bbox toàn khung; 24.003×21.387cm.
- [x] Mẫu trước dư trên154px, dưới42px, trái51px đã sửa. Giữ khoảng cách logo/nhân vật bên trong, không tự sắp xếp lại thiết kế.

23/10/2026: Chủ xưởng xác nhận chuẩn cắt sát cho TẤT CẢ đơn PNG/TIFF; quy tắc chính thức: docs/PNG-TIFF-ARTWORK-RULES.md. Giữ kích thước sau crop, khoảng cách nội bộ, alpha và mực trắng.
