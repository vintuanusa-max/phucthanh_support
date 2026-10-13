# Kế hoạch tích hợp Chatwoot (bản cũ)

> **Đã thay bằng [KE_HOACH_TIN_NHAN.md](KE_HOACH_TIN_NHAN.md)** (2026-10-12): phạm vi chỉ còn
> kiểm soát toàn bộ tin nhắn và trả lời chính xác. Các phần ERP/lên đơn dưới đây tạm hoãn.

Mục tiêu: mọi hội thoại (Zalo cá nhân, WhatsApp cá nhân, sau này Zalo OA, WhatsApp
Cloud, Messenger) được quản lý trong **Chatwoot**. Nhân viên đọc, trả lời, lên đơn
và chạy kịch bản ngay trong Chatwoot. Bot Zalo/WhatsApp hiện có chỉ còn là "đường
ống" nhận và gửi tin.

Ngày lập: 2026-10-12. Nền tảng: `phucthanh_support` sau Giai đoạn 1.

---

## 1. Kiến trúc đích

```
 Khách                     Máy MAY1 (192.168.1.101)                       NAS (192.168.1.203)
┌─────────┐   Zalo Web   ┌──────────────────────────────────────┐     ┌──────────────────────────┐
│ Zalo    │◄────────────►│ channels/zalo_web     ┐              │     │ Chatwoot (Docker)         │
│ cá nhân │              │                        ├─ publish()──►│ ①   │  - Inbox "Zalo cá nhân"   │
├─────────┤  WA Web      │ channels/whatsapp_wpp ┘   IncomingMsg│────►│    (kênh API)             │
│WhatsApp │◄────────────►│                                      │     │  - Inbox "WhatsApp cá nhân"│
│ cá nhân │              │ integrations/chatwoot/               │     │    (kênh API)             │
└─────────┘              │   inbound  : SQLite → Chatwoot API   │     │  - Inbox native (sau này):│
                         │   outbound : webhook → SQLite →      │◄────│    WA Cloud, Messenger    │
                         │              hàng đợi gửi của kênh   │ ②   │  - Automation, Macro,     │
                         │ erp_bridge (giữ nguyên)              │     │    Canned, Agent Bot      │
                         └──────────────────────────────────────┘     │  - Dashboard App ─────┐   │
                                       ▲                              └───────────────────────┼───┘
                                       │ outbox "xong hàng"           ┌───────────────────────▼───┐
                                       └──────────────────────────────│ ERP phucthanh-erp         │
                                                                      │  Duyệt Đơn, khách hàng    │
                                                                      └───────────────────────────┘
① Tin khách → Chatwoot (message_type incoming)
② Nhân viên trả lời trong Chatwoot → webhook message_created (outgoing) → bot gửi ra Zalo/WA
```

Nguyên tắc:

1. **Chatwoot là nơi làm việc, ERP là nơi chứa dữ liệu chuẩn** (khách, đơn, mã hàng).
   Liên kết bằng custom attribute `erp_customer_id` trên contact Chatwoot.
2. **Bot vẫn là chốt chặn cuối.** `core.policy.allowed()` và các kiểm tra hiện có
   (đúng nhóm, đúng tên trước Enter, trạng thái `sending/submitted/uncertain`)
   vẫn áp dụng cho mọi tin đi từ Chatwoot. Không bao giờ tự gửi lại tin `uncertain`.
3. **Không mất tin, không gửi trùng.** Cả hai chiều đều đi qua SQLite bền trước khi
   gọi mạng, kèm khoá idempotent (giống `erp_bridge`).
4. **Tài khoản cá nhân dễ bị khoá:** không dùng Campaign/broadcast của Chatwoot cho
   inbox Zalo/WA cá nhân. Giới hạn tốc độ gửi trong bot.

## 2. Ánh xạ dữ liệu

| Bot | Chatwoot | Ghi chú |
|---|---|---|
| Kênh (`zalo`, `whatsapp`) | Inbox kiểu **API** (mỗi tài khoản một inbox) | Chatwoot không có kênh Zalo native |
| Chat/nhóm | Contact + Conversation | Zalo Web không có id ổn định → `identifier = "zalo:" + tên nhóm chuẩn hoá`. WhatsApp dùng `chat_id` (`...@c.us` / `...@g.us`) |
| Người gửi trong nhóm | Ghi vào nội dung: `**Tên người gửi:** nội dung` | Contact trong Chatwoot là cả nhóm |
| `IncomingMessage.message_id` | Khoá idempotent của bridge (bảng `inbound`) | Bộ quét có thể publish lại cùng tin (vd. khi lưu đơn lỗi) → bridge phải bỏ trùng |
| File đã lưu ở W:\ | `attachments[]` (multipart) | File thiết kế lớn (> ~40 MB, .ai/.psd) chỉ gửi đường dẫn W:\, không upload |
| Đơn chờ duyệt (`intake`) | Private note + label `don-cho-duyet` | Note có link tới Duyệt Đơn của ERP |
| Thông báo "xong hàng" (ERP outbox) | Tin outgoing trong conversation | Xem mục 5.4 |

Khi nhóm Zalo đổi tên, contact mới sẽ được tạo. Bảng `contact_map` trong bridge cho
phép admin gộp tay (endpoint `/api/chatwoot/contact-map`). Đây là giới hạn của Zalo
Web; Zalo OA thì có user id ổn định.

## 3. Thành phần cần xây

### 3.1 Trên NAS: Chatwoot

- Docker Compose chính thức: `rails` + `sidekiq` + `postgres` + `redis`. Cần khoảng
  **4 GB RAM trống**; kiểm tra NAS trước khi cài.
- Ghim phiên bản ảnh (vd. `chatwoot/chatwoot:v4.x.y`). Không dùng `latest`.
- HTTPS qua DSM Reverse Proxy + Let's Encrypt (bắt buộc để dùng app di động, và cho
  webhook Meta khi thêm WA Cloud/Messenger).
- `ACTIVE_STORAGE_SERVICE=local`, volume trên `/volume2/docker/chatwoot/storage`.
- Sao lưu hằng ngày `pg_dump` + thư mục storage qua DSM Task Scheduler.
- Bật 2FA cho tài khoản quản trị.

### 3.2 Trên MAY1: `integrations/chatwoot/` trong `phucthanh_support`

Chạy trong cùng tiến trình bot, vì việc gửi phải đi qua trình duyệt trên MAY1.

```
integrations/chatwoot/
  config.py      đọc chatwoot_config.json (url, account_id, api_token, inbox_id theo kênh,
                 webhook_secret, enabled, giới hạn tốc độ) — không vào git
  store.py       SQLite data/chatwoot/bridge.sqlite3:
                   inbound(id PK = sha256(channel|chat_id|message_id), payload, state, attempts, next_try, cw_message_id)
                   outbound(cw_message_id PK, conversation_id, channel, chat_name, content, attachments, state, detail, reported)
                   contact_map(channel, chat_key PK, cw_contact_id, cw_conversation_id, source_id)
  client.py      gọi Chatwoot Application API (header api_access_token)
  inbound.py     subscriber của core.messages → ghi inbound; worker đẩy lên Chatwoot
  outbound.py    nhận webhook → ghi outbound; worker chuyển vào send_queue / wa_send_queue
  routes.py      POST /api/chatwoot/webhook, GET /api/chatwoot/status, contact-map
```

Đăng ký trong `main.py`: `chatwoot.start(app)` sau `start_erp_bridge`, chỉ khi
`enabled=true`.

### 3.3 Trong ERP (`phucthanh-erp`)

- **Dashboard App "Lên đơn"** (trang ERP nhúng iframe trong sidebar conversation của
  Chatwoot). Nhận ngữ cảnh contact/conversation qua `postMessage`, hiển thị khách ERP
  tương ứng, các đơn chờ duyệt từ chat này, form tạo đơn (mã hàng, số lượng, ngày
  giao, ảnh chọn từ attachment của conversation).
- Endpoint ERP gọi Chatwoot API để ghi private note "Đã tạo đơn DH-xxx".
- Thêm cột/thuộc tính liên kết `customer ↔ chatwoot_contact_id`.

## 4. Luồng chi tiết

### 4.1 Tin vào (khách → Chatwoot)

1. Bộ quét kênh gọi `publish(IncomingMessage)` (đã có từ Giai đoạn 1).
2. `inbound.on_message`: `INSERT OR IGNORE` vào `inbound` rồi trả về ngay (đang giữ
   khoá trình duyệt nên không gọi mạng ở đây).
3. Worker nền (mỗi 2 giây):
   - Tìm `contact_map`. Nếu chưa có: tạo contact (`POST /api/v1/accounts/{id}/contacts`
     với `inbox_id`, `identifier`, `name`), rồi tạo conversation
     (`POST .../conversations` với `source_id`, `inbox_id`, `contact_id`).
     Conversation đã `resolved` thì mở lại, không tạo mới.
   - `POST .../conversations/{cid}/messages` với `message_type=incoming` (multipart nếu
     có file). Lưu `cw_message_id`, đặt `state=sent`.
   - Lỗi 4xx: `failed` để admin xem. Lỗi mạng/5xx: thử lại với backoff, giống `erp_bridge`.
4. Ghi nhớ id các tin bridge tự tạo, để webhook trả về (incoming) thì bỏ qua.

### 4.2 Tin ra (Chatwoot → khách)

1. Inbox kiểu API có `webhook_url` → `http://192.168.1.101:8000/api/chatwoot/webhook`.
   Kiểm tra chữ ký bằng `secret` của webhook; nếu phiên bản Chatwoot chưa hỗ trợ ký
   thì dùng token bí mật trong URL và chỉ nhận từ IP của NAS.
2. Chỉ nhận `event=message_created`, `message_type=outgoing`, `private=false`. Bỏ qua
   tin do chính bridge tạo.
3. `INSERT OR IGNORE` vào `outbound` theo `cw_message_id` (webhook gửi lại không gây
   gửi trùng). Trả 200 ngay.
4. Worker: kiểm tra `core.policy.allowed(channel, chat_name, "receive_messages")`, rồi
   đưa task vào hàng đợi của kênh kèm `chatwoot_message_id`. Send worker của Zalo cần
   một nhánh giống `erp_event_id`: khớp **chính xác** tên nhóm, đánh dấu
   `sending → submitted` quanh phím Enter.
5. Kết quả: `submitted` thì không làm gì thêm (hoặc cập nhật trạng thái tin nếu API
   hỗ trợ). `failed/blocked/uncertain` thì ghi **private note** vào conversation:
   "⚠ Chưa gửi được ra Zalo: …", để nhân viên biết và tự xử lý.
6. File đính kèm từ Chatwoot: tải `data_url` về thư mục tạm rồi gửi qua kênh. Zalo Web
   cần thêm thao tác đính kèm file. Đây là chức năng mới, làm sau cùng (mục 6, GĐ C).

### 4.3 Tin nhân viên gõ thẳng trên điện thoại / Zalo PC

Bộ quét hiện bỏ qua tin `.me`, nên Chatwoot sẽ không thấy các tin này. Nếu cần đồng
bộ thì làm sau: quét cả tin của mình, đẩy lên dạng `outgoing` có đánh dấu
(`content_attributes.external_echo=true`). Webhook của tin này phải được outbound bỏ
qua (theo id đã ghi nhớ) để tránh gửi lại ra Zalo. Rủi ro vòng lặp cao, nên chỉ làm
khi các giai đoạn trước đã ổn.

## 5. Lên đơn và kịch bản trong Chatwoot

### 5.1 Đơn tự động (giữ nguyên lõi hiện tại)

Bot vẫn nhận diện tin có số lượng → chụp màn hình → `erp_bridge.capture` → Gemini →
ERP Duyệt Đơn. Thêm: khi tạo intake, bridge ghi private note và label
`don-cho-duyet` vào conversation tương ứng. Khi ERP xác nhận tạo đơn, ghi note
"Đã tạo DH-xxx" và đổi label sang `da-len-don`.

### 5.2 Lên đơn thủ công từ Chatwoot

Cách chính là **Dashboard App "Lên đơn"** (mục 3.3): nhân viên đang xem hội thoại thì
bấm, kiểm tra rồi tạo đơn. ERP ghi note ngược lại vào conversation.

Cách phụ, nhanh: nhân viên gắn label `len-don`. Automation rule (event
`conversation_updated`, điều kiện label `len-don`) gửi webhook tới bridge. Bridge lấy
tin khách gần nhất cùng ảnh đính kèm tạo intake vào Duyệt Đơn (nguồn `chatwoot`, cần
mở rộng `erp_bridge` vì hiện chỉ nhận `zalo|whatsapp`).

### 5.3 Kịch bản trả lời

| Nhu cầu | Công cụ Chatwoot |
|---|---|
| Câu trả lời mẫu (báo giá, thời gian giao, STK) | **Canned responses** (gõ `/`) |
| Chuỗi thao tác một chạm (trả lời + label + giao người) | **Macros** |
| Tự gắn label/giao nhân viên theo từ khoá, theo inbox, ngoài giờ | **Automation rules** (`message_created`, `conversation_created`) |
| Bot hỏi đáp / tra trạng thái đơn ("đơn em xong chưa") | **Agent Bot** (webhook tới bridge hoặc n8n; trả lời qua API; chuyển cho người bằng cách mở conversation) |
| Gợi ý trả lời, tóm tắt bằng AI | Tích hợp OpenAI có sẵn, hoặc Captain (kiểm tra giấy phép bản self-host trước) |

Với inbox Zalo/WA cá nhân: tự động trả lời phải có giới hạn tần suất (vd. tối đa 1
tin tự động / chat / 30 phút) để tránh bị khoá.

### 5.4 Thông báo "xong hàng"

Hiện ERP outbox → `erp_bridge` → gửi thẳng Zalo. Khi chuyển sang Chatwoot, ERP gọi
Chatwoot tạo tin `outgoing` trong conversation của khách, rồi tin đi qua luồng 4.2.
Lợi ích: lịch sử nằm trong Chatwoot, nhân viên thấy được. Giữ đường cũ làm phương án
dự phòng (cờ cấu hình) cho đến khi luồng mới ổn định. **Không bật cả hai cùng lúc**
cho cùng một khách, vì sẽ gửi trùng.

## 6. Lộ trình

| GĐ | Nội dung | Tiêu chí xong |
|---|---|---|
| **0 — Hạ tầng** | Cài Chatwoot trên NAS, HTTPS, tạo account, 2 inbox API, user cho nhân viên, token cho bridge. Thử bằng curl: tạo contact/conversation/tin `incoming`, nhận webhook `outgoing` về máy test | Curl tạo được tin vào, webhook về đúng payload; đã có bản sao lưu |
| **A — Phản chiếu tin vào (chỉ đọc)** | `integrations/chatwoot` inbound + store + contact_map. Nhân viên vẫn trả lời trên Zalo như cũ | Chạy song song 1 tuần: số tin trên Chatwoot khớp số tin bot quét được, không trùng, ảnh/file hiện đủ |
| **B — Trả lời từ Chatwoot** | Webhook → outbound → send worker (khớp chính xác tên + trạng thái gửi). Bật theo danh sách nhóm thử (`chatwoot_reply_groups`) | 2–3 nhóm thử, 1 tuần: không gửi nhầm nhóm, lỗi đều có private note, không có `uncertain` bị gửi lại |
| **C — Đơn hàng trong Chatwoot** | Note/label cho intake, Dashboard App "Lên đơn" trong ERP, gửi file từ Chatwoot ra Zalo | Tạo được đơn từ Chatwoot cho 10 đơn thật, đối chiếu đúng trên ERP |
| **D — Kịch bản** | Canned responses, macros, automation (gắn nhãn, giao việc, ngoài giờ), Agent Bot tra trạng thái đơn | Nhân viên dùng hằng ngày; tự động trả lời không vượt giới hạn tần suất |
| **E — Chuyển thông báo "xong hàng" qua Chatwoot** | Mục 5.4, tắt đường gửi thẳng theo từng khách | Không còn gửi trùng; lịch sử đầy đủ trong Chatwoot |
| **F — Kênh chính thức** | Inbox native WhatsApp Cloud API / Messenger (Chatwoot hỗ trợ sẵn); adapter Zalo OA (webhook OA → `channels/zalo_oa.py` → cùng luồng API inbox) | Khách mới được hướng sang kênh chính thức; ZNS cho thông báo |
| **G — (tuỳ chọn) Đồng bộ tin nhân viên gõ trên điện thoại** | Mục 4.3 | Không có vòng lặp gửi lại sau 2 tuần chạy thử |

GĐ A và B là nền móng: chỉ chuyển nhân viên sang làm việc trong Chatwoot sau khi B đạt.

## 7. Bảo mật và vận hành

- `chatwoot_config.json` chỉ có trên MAY1 (đã nằm trong `.gitignore`). Token bridge là
  token của một user Chatwoot riêng ("Bot Bridge"), chỉ được vào 2 inbox.
- Webhook: kiểm tra chữ ký/secret và IP nguồn; giới hạn kích thước body.
- Trang `/api/chatwoot/status` cho biết hàng đợi in/out, số `failed`/`uncertain`, lần
  đồng bộ cuối. Báo Telegram khi `failed` tăng hoặc mất kết nối Chatwoot quá 5 phút.
- Chatwoot ngừng hoạt động thì bot vẫn quét và lên đơn như cũ (inbound chỉ dồn hàng
  đợi), nên không mất đơn.
- **Trước GĐ 0 phải làm:** thu hồi Gemini API key và AppSheet key đã từng nằm trong
  code/git của `phuc_thanh_zalo`, rồi tạo key mới trong `config.json` trên MAY1.

## 8. Việc cần quyết định trước khi làm

1. NAS có đủ RAM (~4 GB) cho Chatwoot không, hay cài trên máy khác?
2. Tên miền HTTPS cho Chatwoot (vd. `chat.vintuan.com`).
3. Số nhân viên dùng Chatwoot và cách chia nhóm (bán hàng, thiết kế, giao hàng).
4. Nhóm Zalo nào chạy thử GĐ B.
5. Có cần GĐ G (đồng bộ tin nhân viên gõ trên điện thoại) không.
