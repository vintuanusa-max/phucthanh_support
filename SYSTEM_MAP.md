> Cập nhật tài liệu 23/10/2026: xem [Tổng quan hệ thống](TONG_QUAN_HE_THONG.md) và checklist hiện hành được liên kết tại đó. Các mục bên dưới giữ làm lịch sử; ghi chú “chờ triển khai” cũ phải đối chiếu bản cập nhật hiện hành. Lượt này chỉ cập nhật tài liệu, không thay đổi dịch vụ hay dữ liệu ERP.

2026-10-22: Tab Tiến trình file in + order_print_files/order_print_requests deployed and live checked. Hub OrderPrintBridge polls commands and projects previews; manual export original artwork, preserves enclosed whites, no paid redraw/no ERP mutations/no public send/RIP. CHU PHAT DH-2610-323 PNG/TIFF done, private note4477, duplicate-click reused same job. See phucthanh_support/docs/PRINT_FILE_PROGRESS.md.


### 2026-10-23 Native PET automatic selection
PET PDF/AI mới -> native_auto.enqueue -> Illustrator scan -> Gemini chọn native IDs -> native PNG -> AI kiểm tra PNG -> pet_exports/Photoshop TIFF -> private Chatwoot. /data/native-auto lưu context và enabled-at. native_selections lưu trạng thái/plan/verification; gián đoạn AI không tự retry. Dashboard8096 hiển thị cụm/side để đổi lựa chọn. Không ERP/RIP/customer send. Xem docs/ILLUSTRATOR-ARTWORK-SELECTION.md.

2026-10-23 13:49: native_auto.ask_once/resolve lưu ai_calls per job/bước, đối chiếu một lần khi kết quả không nhất quán/chặn. 4 checks có lý do+source; không chắc -> review + private note; decision_summary trên dispatch. Hai bước chính + tối đa hai đối chiếu; interrupted không retry. Hard geometry/font gates giữ nguyên. Image native-consistency-20261023.

2026-10-23: PET artwork-only. PetExports.ask không nối policy cữ JPG; native_auto ghi chú bằng kích thước code, không cảnh báo cữ túi. PNG/TIFF alpha/spot giữ nguyên. JPG policy không đổi.

PET tight bounds: native_selection.trim_artwork loại alpha rỗng ngoài, chuẩn ngang sau crop; native_auto kiểm geometry bằng code; pet.ask khi GEOMETRY_VERIFIED_BY_CODE chỉ kiểm nội dung. Private outputs, no ERP/RIP.

## 2026-10-23 — WhatsApp image-only quantity
- Fixed order_intake.image_only_caption_pending: ready image + draft proposal may proceed despite legacy caption-unverified marker without typed order verbs. Independent verify_action remains mandatory. Missing media, questions/negative text remain blocked.
- 15 focused guard checks passed; deployed caption-image-order-20261023. Current image plus pet-tight-bounds backup retained.
- KTTHAO source 3A03CB59EED5FAB1B548: owner confirmed separate new 1100 Halloween masks. Same durable intake request created DH-2610-334 (MATNA, KTTHAO); private Chatwoot note 5104. Readback later showed dang_chay_giay; no status overwrite. Existing DH-2610-304 untouched.
2026-10-23: image-only order intake waits before AgentLoop for 1800s; last_timestamp controls inactivity deadline for new batches. Timeout reuses durable run, independent image verification, evidence and normal ERP submit. 15 guard + 5 timer tests passed. Deployed image-wait-30m-20261023. No replay of created orders; all AI notes private.
2026-10-23: config.json.erp_customer_mappings authoritative; Zalo order_sync sends mapping section with sanitized policy; mapping_file validates atomic /data cache; CustomerMappings.get uses account/thread ID, KHACH LE fallback, audit/version retained. No existing ERP order mutations. See docs/GROUP-CUSTOMER-MAPPINGS.md.
2026-10-23: Zalo reader.capture_allowed drops exact unsupported:2 placeholder from configured zalo_internal_members before vault/upload; pending outbox marked ignored_policy; checkpoint preserved. Real staff content and customer attachments retained. 4 focused tests passed.
