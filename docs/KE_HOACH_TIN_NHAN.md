# Kế hoạch: kiểm soát toàn bộ tin nhắn và trả lời chính xác

Phạm vi chỉ gồm hai nhiệm vụ:

1. **Kiểm soát toàn bộ tin nhắn:** mọi tin trên Zalo và WhatsApp của tài khoản (khách
   gửi, nhân viên gửi từ điện thoại/PC, bot gửi) đều được ghi lại đầy đủ, không mất,
   không trùng, và xem được tập trung trong Chatwoot.
2. **Trả lời chính xác:** tin trả lời từ Chatwoot đi đúng chat, đúng nội dung, đúng một
   lần. Trạng thái gửi luôn biết được.

Không thuộc phạm vi: ERP, lên đơn, kịch bản tự động. Bridge ERP hiện có giữ nguyên,
không sửa.

Ngày lập: 2026-10-12. Nền tảng: `phucthanh_support` sau Giai đoạn 1.

---

## 1. Hiện trạng: vì sao chưa kiểm soát được hết

Các lỗ hổng dưới đây đọc ra từ code hiện tại (`channels/zalo_web.py`, `channels/whatsapp_wpp.py`).

### 1.1 Zalo: mất tin

| # | Lỗ hổng | Hậu quả |
|---|---|---|
| Z1 | Bot chỉ vào chat **có chấm đỏ chưa đọc** (cộng chat đang mở) | Nhân viên đọc tin trên điện thoại là chấm đỏ mất, bot không bao giờ vào chat đó. **Đây là lỗ lớn nhất.** |
| Z2 | Chỉ đọc khối **"Hôm nay"**, lịch sử reset mỗi ngày | Tin đến gần nửa đêm mà sang ngày mới mới quét thì mất |
| Z3 | Chỉ đọc phần tin đang hiển thị trong DOM (30 tin chữ, 20 ảnh, 20 file cuối), không cuộn lên | Khách gửi dồn nhiều tin, hoặc bot dừng một lúc, thì tin cũ hơn bị bỏ qua |
| Z4 | Chu kỳ quét có giới hạn 90 giây, tối đa 30 chat | Lúc đông tin, các chat còn lại phải đợi; thêm Z1 thì có thể mất hẳn |
| Z5 | Khoá chống trùng của tin chữ là `hash(nhóm, người gửi, nội dung)` | Khách gửi "ok" hai lần trong ngày thì lần sau bị coi là trùng và bỏ |
| Z6 | Chỉ lấy chữ (`span.text`), ảnh, file | Mất sticker, ghi âm, video, danh thiếp, vị trí, link card, tin thu hồi/sửa |
| Z7 | Bỏ qua tin của chính tài khoản (`.me`) | Không thấy nhân viên đã trả lời gì từ điện thoại, nên không kiểm soát được |
| Z8 | Tên nhóm đọc từ header, chờ bằng `sleep` | Nếu header đổi trước nội dung, tin có thể gắn nhầm nhóm |
| Z9 | Người gửi không xác định được thì ghi là "Khách" | Không biết ai trong nhóm nói |

### 1.2 WhatsApp: mất tin

| # | Lỗ hổng | Hậu quả |
|---|---|---|
| W1 | Bỏ qua mọi chat có tên là số điện thoại | **Khách mới chưa lưu danh bạ bị bỏ hoàn toàn** |
| W2 | Mỗi chat chỉ lấy 20 tin cuối, chỉ tin trong ngày | Tin dồn nhiều hoặc qua nửa đêm thì mất |
| W3 | Bỏ qua tin `fromMe` | Không thấy tin nhân viên gửi |
| W4 | Mỗi chu kỳ duyệt **mọi** chat bằng polling 2 phút | Chậm, nặng; tin đến giữa hai chu kỳ phải chờ |

### 1.3 Trả lời: chưa chính xác

| # | Vấn đề |
|---|---|
| R1 | Zalo tìm chat bằng **tên** (danh sách bên trái, rồi ô tìm kiếm). Gửi thường (không có `erp_event_id`) dùng `name_match` gần đúng (60% từ khoá), và **có nhánh bấm kết quả đầu tiên hoặc Enter mà không kiểm tra tên** |
| R2 | WhatsApp chọn chat bằng `name_match` gần đúng trên danh sách chat, **lấy chat đầu tiên khớp**. "An Bình" có thể khớp "An Bình 2" |
| R3 | WhatsApp ghép nội dung tin thẳng vào chuỗi JS (`` `{message}` ``). Tin có `` ` ``, `${`, `\` sẽ gửi sai hoặc lỗi |
| R4 | Gửi xong không kiểm tra tin đã thực sự hiện trong chat. "Đã gửi" chỉ có nghĩa là đã bấm Enter |
| R5 | Gửi thường không có trạng thái bền. Bot khởi động lại giữa chừng thì không biết tin đã đi chưa |
| R6 | Chưa gửi được file/ảnh ra Zalo; chưa trả lời kèm trích dẫn tin gốc |

---

## 2. Kiến trúc đích

```
              MAY1 (bot)                                                     NAS
┌──────────────────────────────────────────────────────────────┐      ┌───────────────┐
│ Kênh Zalo ─┐                                                  │      │   Chatwoot    │
│            ├─► Thu thập (sự kiện + quét đối soát)            │      │               │
│ Kênh WA  ──┘        │                                         │      │ Inbox API     │
│                     ▼                                         │      │  Zalo / WA    │
│            ┌──────────────────────┐   đồng bộ lên             │      │               │
│            │  SỔ TIN NHẮN (SQLite) │ ─────────────────────────┼─────►│ incoming +    │
│            │  threads / messages   │                          │      │ outgoing echo │
│            │  outbound / sync_log  │ ◄────────────────────────┼──────│ webhook trả lời│
│            └──────────────────────┘   lệnh gửi                │      └───────────────┘
│                     │                                         │
│                     ▼                                         │
│            Bộ gửi chính xác: mở chat theo thread_id →         │
│            kiểm tra → gửi → đọc lại xác nhận → báo trạng thái │
└──────────────────────────────────────────────────────────────┘
```

Ba nguyên tắc:

1. **Sổ tin nhắn trên MAY1 là nguồn sự thật.** Mọi tin (vào, ra, kể cả tin nhân viên
   gõ trên điện thoại) được ghi vào sổ trước, rồi mới đồng bộ lên Chatwoot. Chatwoot
   hay mạng có hỏng thì tin vẫn không mất, chỉ đồng bộ chậm hơn.
2. **Định danh bằng ID, không bằng tên.** Mỗi chat có `thread_id` ổn định, mỗi tin có
   `msg_id` của chính nền tảng. Tên chỉ để hiển thị và kiểm tra thêm.
3. **Hai lớp thu thập:** bắt sự kiện realtime cho nhanh, cộng **quét đối soát** định kỳ
   để vá chỗ sự kiện bị sót. Đối soát dựa vào sổ (tin cuối đã biết của từng chat), không
   dựa vào chấm đỏ hay khối "Hôm nay".

---

## 3. Sổ tin nhắn (`data/messages/ledger.sqlite3`)

```sql
threads(
  channel TEXT, thread_id TEXT,          -- WA: 84xxx@c.us / ...@g.us; Zalo: id hội thoại (xem 4.1)
  kind TEXT,                              -- user | group
  display_name TEXT, name_history TEXT,   -- lưu tên cũ khi đổi tên
  last_msg_id TEXT, last_ts REAL,         -- mốc đối soát
  cw_contact_id INT, cw_conversation_id INT, cw_source_id TEXT,
  PRIMARY KEY(channel, thread_id))

messages(
  channel TEXT, msg_id TEXT,              -- id gốc của nền tảng (Zalo bb_msg_id_..., WA id._serialized)
  thread_id TEXT, direction TEXT,         -- in | out_bot | out_staff (gõ trên điện thoại/PC)
  sender_id TEXT, sender_name TEXT,
  type TEXT,                              -- text|image|file|video|voice|sticker|link|contact|location|recalled|other
  text TEXT, quoted_msg_id TEXT, attachments TEXT,  -- JSON: đường dẫn file đã lưu
  ts REAL, captured_by TEXT,              -- event | sweep
  edited INT DEFAULT 0, recalled INT DEFAULT 0,
  cw_message_id INT, cw_state TEXT DEFAULT 'pending',  -- pending|synced|failed
  PRIMARY KEY(channel, msg_id))

outbound(
  id TEXT PRIMARY KEY,                    -- 'cw:<chatwoot message id>' (idempotent)
  channel TEXT, thread_id TEXT, expected_name TEXT,
  text TEXT, attachments TEXT, quoted_msg_id TEXT,
  state TEXT,                             -- queued|sending|submitted|confirmed|failed|blocked|uncertain
  detail TEXT, platform_msg_id TEXT, attempts INT, created REAL, updated REAL, reported INT)

sync_log(ts REAL, channel TEXT, kind TEXT, detail TEXT)   -- lần quét, gap tìm được, lỗi
```

Quy tắc:

- Ghi bằng `INSERT OR IGNORE` theo `(channel, msg_id)`: cùng một tin bắt hai lần (sự
  kiện + đối soát) chỉ ghi một bản.
- Tin không có `msg_id` thật (trường hợp hiếm của DOM Zalo) thì không ghi vào sổ
  chính, mà ghi vào `sync_log` như một lỗi cần xem. Không dùng hash nội dung làm id,
  vì đó chính là lỗi Z5.
- File tải về lưu theo `W:\<thư mục khách>\` như hiện nay. Đường dẫn ghi trong `attachments`.
- `processed_history.json` / `whatsapp_history.json` cũ chỉ để chuyển đổi, rồi bỏ.

---

## 4. Nhiệm vụ 1: thu thập toàn bộ tin

### 4.1 WhatsApp

WPPConnect cung cấp sự kiện và ID đầy đủ, nên chuyển từ polling sang sự kiện.

1. **Sự kiện realtime:** sau khi tiêm WPP, đăng ký `WPP.on('chat.new_message', ...)`
   (cả tin vào lẫn `fromMe`), cùng sự kiện thu hồi/sửa tin nếu bản WPP đang dùng có.
   Đẩy sang Python bằng `page.expose_binding` và ghi ngay vào sổ.
2. **Đối soát mỗi 5 phút, và ngay khi khởi động:** lấy danh sách chat có
   `t > last_ts` của chat đó trong sổ, rồi với mỗi chat gọi `getMessages` lùi dần cho
   đến khi gặp `last_msg_id` đã biết. Không giới hạn 20 tin, không giới hạn "trong ngày".
3. **Bỏ bộ lọc W1:** chat tên là số điện thoại vẫn thu thập. Chỉ loại
   `status@broadcast` và channel/newsletter.
4. **Media:** `downloadMedia` cho mọi loại (ảnh, file, video, ghi âm, sticker), giữ
   nguyên cơ chế lưu W:\ hiện tại. Tải lỗi thì vẫn ghi tin vào sổ (`attachments` rỗng,
   `detail` báo lỗi) và đưa vào hàng đợi tải lại; không bỏ tin.
5. **Tin nhân viên gửi** (`fromMe` mà không phải do bot gửi) ghi `direction=out_staff`.
   Tin do bot gửi được nhận ra nhờ `platform_msg_id` lưu trong `outbound` (4.4).

### 4.2 Zalo

Zalo Web không có API công khai, nên cần một bước khảo sát để chọn cách thu thập.

**Bước khảo sát (spike, 3–5 ngày, chạy trên tài khoản Zalo phụ, không phải tài khoản thật):**

| Cách | Cần kiểm tra |
|---|---|
| **A. DOM cải tiến** (giữ Zalo Web hiện tại) | Phần tử hội thoại ở danh sách bên trái có ID hội thoại ổn định không (thuộc tính `id`/`data-id`, hoặc ID trong link avatar)? `bb_msg_id_*` có giữ nguyên khi tải lại trang không? Cuộn lên lấy tin cũ có ổn định không? |
| **B. Đọc kho dữ liệu cục bộ của Zalo Web** (IndexedDB trong trình duyệt bot) | Zalo Web có lưu tin, kèm ID hội thoại, ID tin và cờ "của mình", trong IndexedDB không? Đọc bằng `page.evaluate` có ổn định không, cập nhật có realtime không? |
| **C. Thư viện `zca-js`** (Node, giao thức Zalo Web) | Có sự kiện cho mọi tin (kể cả của mình) với `threadId`/`msgId`, gửi theo `threadId`. **Cần xác nhận:** chạy song song với Zalo Web trong Chrome có làm một bên bị đăng xuất không. Rủi ro khoá tài khoản ra sao so với cách hiện tại |

Tiêu chí chọn, theo thứ tự ưu tiên: (1) có `thread_id` ổn định, (2) bắt được 100%
tin trong bộ test 7.1, (3) không làm tài khoản bị đăng xuất/khoá, (4) ít phụ thuộc vào
giao diện Zalo thay đổi.

Dự kiến B hoặc C thắng, A làm dự phòng. Dù chọn cách nào, phải sửa các lỗ hổng sau:

- **Z1:** đối soát không dựa vào chấm đỏ. Mỗi chu kỳ so `last_ts` trong danh sách hội
  thoại (thời gian tin cuối hiển thị ở danh sách, hoặc dữ liệu B/C) với sổ. Chat nào
  có tin mới hơn sổ thì vào đọc, đã đọc hay chưa đều vậy.
- **Z2/Z3:** trong chat, cuộn lên cho tới khi gặp `last_msg_id` đã biết (giới hạn an
  toàn 500 tin, quá thì ghi `sync_log` cảnh báo). Bỏ điều kiện "Hôm nay".
- **Z4:** bỏ giới hạn 90 giây/30 chat cho đối soát. Thay bằng hàng đợi chat cần đọc,
  ưu tiên chat có tin mới nhất. Gửi tin vẫn được chen ngang (giữ cơ chế `_send_worker_busy`).
- **Z5:** khoá chống trùng là `bb_msg_id` (hoặc `msgId` của B/C).
- **Z6:** nhận diện thêm loại tin. Loại nào chưa trích được nội dung thì vẫn ghi vào sổ
  với `type=other` và một ảnh chụp riêng tin đó, để không mất dấu.
- **Z7:** đọc cả tin `.me` và ghi `out_staff`, trừ tin do bot gửi.
- **Z8:** chỉ đọc nội dung khi ID hội thoại đang mở (hoặc header) khớp với chat định
  đọc, kiểm tra cả trước và sau khi đọc; lệch thì bỏ kết quả lượt đó và đọc lại.
- **Z9:** lưu `sender_id` nếu có (B/C có), DOM thì lấy tên hiển thị.

### 4.3 Đồng bộ lên Chatwoot (một chiều: sổ → Chatwoot)

- Mỗi kênh (mỗi tài khoản) là một **inbox kiểu API**. Mỗi `thread` là một contact cộng
  một conversation, lưu `cw_*` trong bảng `threads`. Contact `identifier` =
  `"<channel>:<thread_id>"`.
- Worker đọc `messages` có `cw_state='pending'` theo thứ tự `ts`:
  - `direction=in`: tạo tin `message_type=incoming`. Trong nhóm thì thêm
    `**Tên người gửi:**` vào đầu nội dung. File gửi kèm dạng multipart
    (file thiết kế > 40 MB thì chỉ ghi đường dẫn W:\).
  - `direction=out_staff`: tạo tin `outgoing` có đánh dấu
    `content_attributes: {"echo": true, "platform_msg_id": ...}` để webhook bỏ qua
    (4.4 bước 2), không gửi ngược lại ra Zalo/WA.
  - `direction=out_bot`: tin này vốn sinh ra từ Chatwoot nên không tạo lại; chỉ cập
    nhật trạng thái (4.4 bước 6).
- Lỗi mạng/5xx thì thử lại với backoff. Lỗi 4xx thì `cw_state=failed`, hiện trên trang
  trạng thái.
- Tên chat đổi thì cập nhật tên contact, thêm vào `name_history`; vẫn cùng conversation
  vì khoá là `thread_id`.

### 4.4 Chống vòng lặp (bắt buộc)

Khi bot tạo tin outgoing trên Chatwoot (echo), Chatwoot sẽ bắn webhook
`message_created` về bot. Bộ nhận webhook bỏ qua tin nếu có `content_attributes.echo`,
hoặc nếu `id` nằm trong danh sách `cw_message_id` do bot tạo. Phải ghi id **trước** khi
gọi API (đặt trạng thái chờ theo khoá nội dung) để tránh trường hợp webhook về trước
khi API trả kết quả.

---

## 5. Nhiệm vụ 2: trả lời chính xác

### 5.1 Luồng

1. Nhân viên trả lời trong Chatwoot. Webhook `message_created` của inbox API gọi
   `POST /api/chatwoot/webhook` trên MAY1, kiểm tra chữ ký/secret và IP nguồn là NAS.
2. Chỉ nhận `message_type=outgoing`, `private=false`, không phải echo (4.4).
3. Tra `threads` theo `cw_conversation_id` để ra `(channel, thread_id, expected_name)`.
   Không tra được thì **không gửi**: ghi private note "Không xác định được chat đích".
4. `INSERT OR IGNORE` vào `outbound` với `id='cw:<message id>'`, nên webhook gửi lặp
   không gây gửi trùng. Trả HTTP 200 ngay.
5. Bộ gửi của kênh xử lý tuần tự, mỗi tin qua 5 bước:

| Bước | WhatsApp | Zalo |
|---|---|---|
| a. Kiểm tra chính sách | `core.policy.allowed(channel, thread, "receive_messages")`; giới hạn tốc độ (vd. 20 tin/phút toàn tài khoản, 1 tin/2 giây mỗi chat) | như WA |
| b. Mở đúng chat | Theo `thread_id` (`WPP.chat.openChatBottom(id)`); **không tìm theo tên** | Theo `thread_id` (cách chọn ở 4.2). Riêng cách A chưa có ID thì: tìm theo tên, **chỉ chấp nhận khớp chính xác** (`exact_group`), bỏ hẳn nhánh "bấm kết quả đầu / Enter không kiểm tra" |
| c. Kiểm tra trước khi gửi | ID chat đang mở = `thread_id` | ID hội thoại đang mở = `thread_id` **và** header = `expected_name` (chuẩn hoá); kiểm tra lại ngay trước Enter (như luồng ERP hiện có) |
| d. Gửi | `WPP.chat.sendTextMessage(id, text, {quotedMsg})`, truyền `text` làm **tham số** của `evaluate`, không ghép chuỗi (sửa R3). Lưu `platform_msg_id` trả về | Điền ô nhập, ghi `sending`, Enter, ghi `submitted` |
| e. Xác nhận | Theo dõi `ack` của tin (đã gửi / đã nhận / đã xem) → `confirmed` | Đọc lại chat: tin `.me` mới nhất có nội dung khớp và xuất hiện sau mốc gửi → lấy `bb_msg_id`, đặt `confirmed`. Sau 15 giây chưa thấy thì `uncertain` |

6. **Báo lại Chatwoot:** `confirmed` thì cập nhật trạng thái tin (nếu phiên bản Chatwoot
   hỗ trợ cập nhật trạng thái cho kênh API), không thì im lặng.
   `failed / blocked / uncertain` thì ghi **private note** vào conversation, ví dụ:
   "⚠ Chưa gửi được ra Zalo (lý do). Kiểm tra chat trước khi gửi lại."
7. **Không bao giờ tự gửi lại** tin `sending/submitted/uncertain` sau khi bot khởi động
   lại (giữ nguyên nguyên tắc của `erp_bridge`). Chỉ `queued` mới được xử lý tiếp. Nhân
   viên muốn gửi lại thì gửi tin mới trong Chatwoot.
8. Tin đã `confirmed` được ghi vào `messages` với `direction=out_bot` và
   `msg_id=platform_msg_id`, để đối soát (4.2/4.1) không nhận nhầm thành `out_staff`.

### 5.2 Gửi file/ảnh và trả lời kèm trích dẫn

- WA: `WPP.chat.sendFileMessage(id, base64, {filename, caption})`. File tải từ
  `data_url` của attachment trên Chatwoot (mạng nội bộ NAS).
- Zalo: thao tác đính kèm trong Zalo Web qua `set_input_files` (cách A), hoặc API
  gửi file (cách C). Xác nhận bằng cách đọc lại như bước e.
- Trích dẫn: Chatwoot gửi `content_attributes.in_reply_to` (id tin Chatwoot). Tra
  ngược ra `msg_id` gốc trong sổ, rồi gửi kèm `quotedMsg` (WA) hoặc thao tác "Trả lời"
  (Zalo). Không tra được thì gửi tin thường.

---

## 6. Giám sát

- Trang `GET /api/messages/status`: theo từng kênh hiển thị trạng thái đăng nhập, độ
  trễ thu thập (tin mới nhất trong sổ so với hiện tại), số tin chờ đồng bộ Chatwoot,
  số outbound `failed/uncertain`, lần đối soát cuối và số "gap" tìm được (tin chỉ có
  được nhờ đối soát, tức sự kiện đã sót).
- Cảnh báo Telegram khi: mất đăng nhập Zalo/WA; WPP không sẵn sàng quá 2 phút; độ trễ
  thu thập quá 5 phút; có outbound `uncertain`; đồng bộ Chatwoot lỗi quá 10 phút.
- **Báo cáo đối soát hằng ngày** (gửi Telegram lúc 7h): số tin vào/ra theo kênh, số gap
  (tăng đều là dấu hiệu sự kiện có vấn đề), số tin `type=other`, số lần gửi không xác nhận.

---

## 7. Kiểm thử nghiệm thu

Chạy trên **tài khoản Zalo/WA phụ** cùng 2–3 máy điện thoại test, trước khi dùng tài khoản thật.

### 7.1 Thu thập (yêu cầu 100%)

| Kịch bản | Kỳ vọng |
|---|---|
| Gửi đủ loại tin: chữ, emoji, chữ trùng nhau ("ok" × 3), 25 ảnh một lượt, file PDF/AI, video, ghi âm, sticker, danh thiếp, vị trí, link, trả lời trích dẫn | Đủ từng tin trong sổ và Chatwoot, đúng thứ tự, đúng loại |
| Nhân viên mở và đọc chat trên điện thoại **trước khi** bot kịp quét | Vẫn đủ tin (kiểm tra Z1) |
| 10 chat cùng gửi dồn 50 tin trong 1 phút | Đủ tin, không gắn nhầm chat |
| Tắt bot 30 phút, khách vẫn nhắn, rồi bật lại | Đối soát lấy lại đủ tin |
| Khách nhắn lúc 23:58–00:02 | Đủ tin ở cả hai ngày |
| Khách mới, số chưa lưu danh bạ (WA) | Có conversation mới |
| Nhân viên trả lời từ điện thoại | Hiện trong Chatwoot dạng outgoing, **không** bị gửi lại |
| Đổi tên nhóm giữa chừng | Vẫn cùng conversation, tên cập nhật |
| Thu hồi / sửa tin | Sổ đánh dấu, Chatwoot có ghi chú |

### 7.2 Trả lời (yêu cầu 0 lần gửi nhầm)

| Kịch bản | Kỳ vọng |
|---|---|
| Hai nhóm tên gần giống ("An Bình - Đặt hàng" và "An Bình - Nội bộ"), trả lời xen kẽ 50 tin | 100% đúng nhóm |
| Nội dung có `` ` ``, `${x}`, `\n`, emoji, tiếng Việt có dấu, 2.000 ký tự | Nội dung nhận được giống hệt |
| Webhook gửi lặp cùng một tin 3 lần | Chỉ gửi 1 lần |
| Tắt bot đúng lúc đang gửi | Tin thành `uncertain`, có private note, không tự gửi lại |
| Đang gửi thì có người bấm sang chat khác trên máy MAY1 | Không gửi, `failed` + note |
| Chat bị chặn theo chính sách | `blocked` + note, không mở chat |
| Gửi ảnh, file, trả lời kèm trích dẫn | Đúng chat, đúng file, đúng tin được trích |
| Nhân viên trả lời liên tục 30 tin vào 1 chat | Đúng thứ tự, tôn trọng giới hạn tốc độ |

---

## 8. Lộ trình

| Bước | Nội dung | Thời lượng ước tính | Xong khi |
|---|---|---|---|
| **0** | Cài Chatwoot trên NAS (Docker, HTTPS, sao lưu), tạo 2 inbox API, user "Bot Bridge". Chuẩn bị tài khoản Zalo/WA phụ | 2–3 ngày | Dùng curl tạo được tin incoming, nhận được webhook outgoing |
| **1** | Khảo sát Zalo (4.2: A/B/C) và chọn cách | 3–5 ngày | Có biên bản chọn cách, kèm bằng chứng về `thread_id` |
| **2** | Sổ tin nhắn + thu thập WhatsApp (sự kiện + đối soát, sửa W1–W4) | 1 tuần | Đạt 7.1 cho WA |
| **3** | Thu thập Zalo theo cách đã chọn (sửa Z1–Z9) | 1–2 tuần | Đạt 7.1 cho Zalo |
| **4** | Đồng bộ sổ → Chatwoot, kèm echo và chống vòng lặp | 1 tuần | Chạy song song 1 tuần trên tài khoản thật, chỉ đọc: Chatwoot khớp sổ 100% |
| **5** | Trả lời chính xác WhatsApp (5.1, sửa R2–R5) | 1 tuần | Đạt 7.2 cho WA |
| **6** | Trả lời chính xác Zalo (5.1, sửa R1, R4, R5) | 1–2 tuần | Đạt 7.2 cho Zalo |
| **7** | File, ảnh, trích dẫn (5.2); giám sát và báo cáo (6) | 1 tuần | Đạt các dòng file/trích dẫn trong 7.2; có báo cáo hằng ngày |
| **8** | Chuyển nhân viên sang trả lời bằng Chatwoot: bật theo từng nhóm, rồi toàn bộ | 1–2 tuần | Không còn trả lời trên Zalo Web ở MAY1; báo cáo không có gửi nhầm |

Bước 2 làm song song được với bước 1. Trong bước 4–7 nhân viên vẫn làm việc như cũ,
nên không ảnh hưởng vận hành.

## 9. Rủi ro

| Rủi ro | Giảm thiểu |
|---|---|
| Zalo/WA khoá tài khoản vì tự động hoá | Thử trên tài khoản phụ trước; giới hạn tốc độ gửi; không broadcast; chỉ gửi khi nhân viên bấm trong Chatwoot |
| Zalo đổi giao diện làm hỏng cách A | Ưu tiên B/C; test DOM tổng hợp như hiện có; cảnh báo khi độ trễ thu thập tăng |
| `zca-js` (nếu chọn C) làm đăng xuất Zalo Web | Kiểm tra trong bước 1. Nếu xung đột thì C thay hẳn Chrome Zalo, không chạy song song |
| Chatwoot ngừng | Sổ vẫn ghi; đồng bộ bù khi Chatwoot hoạt động lại. Trả lời tạm trên Zalo Web; đối soát ghi lại thành `out_staff` |
| Ổ W:\ mất kết nối | Tin vẫn vào sổ; file đưa vào hàng đợi tải lại; cảnh báo |

## 10. Cần bạn quyết định

1. Có chấp nhận dùng `zca-js` (cách C) nếu khảo sát cho thấy tốt hơn không? Mức rủi ro
   tương đương cách hiện tại (đều là không chính thức), nhưng thay đổi cách chạy trên MAY1.
2. Có tài khoản Zalo và số WhatsApp phụ để test không?
3. NAS còn khoảng 4 GB RAM cho Chatwoot không, và dùng tên miền HTTPS nào?
4. Giới hạn tốc độ gửi mong muốn (đề xuất: 20 tin/phút mỗi tài khoản).
