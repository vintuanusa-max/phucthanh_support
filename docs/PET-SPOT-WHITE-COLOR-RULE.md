
## Cập nhật21/10/2026 — spot trắng theo vùng
- Chính sách `white-preserve-color-contract1-v1`: giữ alpha vùng artwork trắng; vùng màu khác co lớp trắng lót1pixel ở300dpi. Không co artwork hoặc đổi kích thước.
- Nhận trắng bằng RGB mỗi kênh>=250 để dung sai làm tròn raster; không xóa màu hoặc sửa RGB của PNG. Alpha trong suốt không có mực. Spot=max(alpha trắng, alpha toàn ảnh co1px); tránh khe ở ranh trắng/màu. Co có đệm trong suốt ở mép canvas.
- Photoshop vẫn chạy WHITE_1 nhưng spot co đồng loạt được thay bằng mask chọn vùng trước lưu. Không sửa action gốc.
- Sau lưu, đọc5samples TIFF và so từng pixel spot với mask dự kiến, so alpha với PNG. Không khớp/rỗng thì review, chưa phát hành. Ghi spot-policy trongmanifest cho job mới; không chạy lại job cũ.
- Chỉ private Chatwoot để duyệt; chưa RIP hoặc gửi khách.
- Dependencies riêng cạnhpet_worker.py trongspot-deps: tifffile2026.3.3,numpy2.4.6,imagecodecs2026.3.6. Cài bằng uv pip install --target <worker>/spot-deps với đúng interpreter worker. Không đưa thư viện binary vàoGit.
- Kiểm thử: trắng nguyên vẹn, trắng alpha127, màu đỏ/đen co1px, xám245 không coi trắng, nềntrong suốt, ranh trắng/màu không hở.3TIFF thực quaPhotoshop được so mask từngpixel. Đây là kiểm chứng file, chưa thử máy in.
