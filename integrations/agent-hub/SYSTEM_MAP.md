# System map — Phuc Thanh Agent Hub

2026-10-13 owner confirmed the final 9 active-group customer bindings. Validated every
customer UUID against the ERP API and persisted through versioned mapping admin endpoints.
40 bindings total; no remaining unbound non-excluded groups among the audited active conversations.
Both CANAVI group IDs map to 7ad9941c-ecb4-4a62-b022-d3c53feb95c7, with distinct Chatwoot
conversation IDs and source reservations. Chi Phuong In Tui maps specifically to C PHƯỢNG TÚI,
not CHI PHUONG. Capture exclusions remain unchanged. No order/history replay or ERP restart.

2026-10-13 confirmed mapping and capture exclusions: added 8 owner-confirmed bindings
(A HUY, Quyền, EM KIỀU, CAP VƯƠNG and 4 groups to KHACH LE); 31 bindings total.
config.json zalo_skip_groups + zalo_skip_thread_ids exclude File In, GUI FILE IN,
Cty In Phuc Thanh and Gia dinh vintuan even after group rename. Set
zalo_default_read_private_messages=false. Reader loads local policy before reading;
excluded message databases are never snapshotted/decrypted/enqueued; queued captures and
vault assets are marked ignored_policy without ingest/download. Failed local policy read
halts capture/flush and blocks vault jobs. Hub capture_policy rejects excluded ingests
before store.capture. The Gia dinh vintuan ai_trials entry was removed. Existing stored
history/files remain untouched. Configuration changes to Hub capture_policy require Hub
restart; local reader config is refreshed each tick. No ERP restart or order creation.
44 focused tests passed; live Hub ignored 5 exclusion probes, zero captures persisted.
Reader running with original cutoff 1791803208997 and no errors after restart.
Updated full report: U:/phucthanh_support/docs/RA-SOAT-ANH-XA-ZALO.html:
288 unbound non-excluded groups, including 9 with existing Chatwoot conversations.

2026-10-13 group mapping audit: read 322 Zalo group IDs/names and 170 ERP customer IDs/names.
Validated 21 exact-name/prefix candidates through the ERP active-customer API; inserted bindings
with audit rows in one backed-up transaction, retaining 2 existing bindings (23 total).
17 new bindings are preseeded for verified Zalo groups without Chatwoot threads; get(account,thread_id)
will resolve them on first capture. Admin list currently shows only groups with threads; see
RA-SOAT-ANH-XA-ZALO.html for the complete inventory. 18 groups with conversations remain unresolved;
299 groups overall remain unbound, including dormant/internal groups. Accent-folded suggestions
are review-only, never automatically bound. No history replay, order writes or ERP restart.

2026-10-13 12:13 verified runtime and A THUC recovery (supersedes historical pending notes):
ERP restart confirmed stable_customer_id=true and active A THỨC UUID
6d691b47-7e5c-4128-a012-698bd8e0696a. Bound zalo-personal-1/g2189799774809638069
by stable ID. No ERP code edits/restart in this recovery turn.
Independent intake now allows null product codes with explicit positive quantities; ERP creates
len_mau pending code/price, never guesses codes from filenames/logos. Piece quantities such as
8c and 1.000c are independently grounded, including image requests. Normal reply schema unchanged.
67 focused tests passed; four changed source/test files hash-verified and Hub rebuilt/restarted.
Scoped reviewed runs created DH-2610-203 (1000, Ngan Anh/COC85) and DH-2610-204 (8, EMCO).
Earlier pre-activation 50c request was explicitly recovered from three exact source IDs using
read-only Zalo snapshot and separate vault; two HÙNG PHÚC images saved NAS, complete evidence
pages combined without cropping into one ERP PNG. Reserved intake_sources and frozen sending
payload before API write; DH-2610-205 confirmed. No global cutoff or history replay changes.
All three API receipts confirm exact customer/group/account; missing dimensions/product/price
and unconfirmed allocation of the 1000 pieces remain in order notes for staff.

2026-10-13 11:53 deployment update: user authorized the two-file ERP API update and will restart ERP
personally. Copied the reviewed backend_v2/routers/zalo_router.py and backend_v2/zalo_integration.py
to U:\phucthanh-erp, verified both SHA256 hashes, and backed up originals under
data/releases/customer-id-api-backup-20261013-115333. No ERP restart, schema changes or test orders.
ID API runtime verification remains pending the user's restart; prior 'staged only' notes below are historical.

2026-10-13 stable customer binding: customer_mappings(account,thread_id) stores customer UUID,
display label and version; customer_mapping_audit preserves changes. Group rename updates only threads.display_name.
Admin GET /admin/customer-mappings/list and POST /admin/customer-mappings/{account}/{thread_id} support
explicit UUID bindings with optimistic version checks; UI includes a group selector. Never auto-bind by fuzzy name or AI.
Order intake freezes binding/version, rechecks before sending, and requires ERP health stable_customer_id=true
plus exact customer UUID verification. Unsupported API -> private review, never fallback to names for bound groups.
Unbound groups retain prior behavior. Trial group g7557409429748854839 maps to customer
5e1f5d50-6c1f-4bc9-8a1f-1bdc12eefad7 (Gia đình vintuan). This enables durable mapping, not yet ID-based ERP writes:
production ERP still lacks this capability. A two-file ERP patch is staged locally only, awaiting permission.
The staged patch keeps old request hashes, rejects missing/deleted UUIDs, creates len_mau via existing transaction,
returns exact customer/group identities, and prevents legacy name-based completion routing for ID-bound orders.
No ERP schema migration. ID-based completed-order notifications are not implemented by this patch.
Validation: 42 Hub tests including rename, cross-account isolation, midflight changes and no-fallback behavior.

2026-10-13 configuration-driven order intake (supersedes earlier trial-only ERP notes below):
`hub/order_policy.py` preserves config.json defaults, NFC/exact names, internal sender/@mention exclusions,
skip groups and independent auto_order/receive_messages switches. Windows `zalo_desktop/order_sync.py`
reads the original NAS config, sends only allowlisted settings every 30 seconds to authenticated
POST /adapters/{account}/order-policy. Policy older than 120 seconds fails closed for new ERP writes.
`hub/order_intake.py` runs separately from AI reply ownership/trial scopes; no public messages are sent.
Activation timestamps exclude history. Incoming customer group captures only; group and sender ID bind
text/captions/images. A 45-second settle window groups up to 3 minutes, at most 12 messages/2 images.
An ignored image may become context for a later same-sender text within 3 minutes; created/review/uncertain
sources are never reused. Gemini uses structured JSON and only proposes new orders; price questions,
amendments, missing codes/ambiguous quantities route to ignore or private staff review. Literal product
code grounding is checked independently; filenames are not ERP codes. ERP remains pricing authority.
Existing ERP groups/observe preflights exact customer resolution: current Zalo API requires
`Tên khách - phần còn lại`. Plain `Gia đình vintuan` cannot automatically create an order through this
API without changing ERP; it stays review. No ERP code or service changes were authorized/applied.
Durable intake_runs/intake_sources reserve each source; ready -> analyzing -> awaiting_evidence ->
evidence_ready -> sending -> created. Analysis failure -> review; ambiguous write -> uncertain,
never automatic resubmission. Restarted analyzing/sending runs require human reconciliation.
Windows GET /adapters/{account}/order-evidence renders and hash-verifies NAS PNG+source.json under
<group>/orders/INTAKE-<runid>/evidence-<hash>. POST acknowledgment returns the saved PNG; only then
existing ERP orders API creates real len_mau orders with image_base64 as khach_dat. More than one PNG
page requires staff review (existing machine API accepts one image). Exact sent payload and result are
retained in Hub, NAS path and source text in ERP notes, success/review private notes in Chatwoot.
New eligible groups also use the existing NAS original-file/Drive archive; activation prevents backfill.
WhatsApp policy is supported but its connector/order scope is not activated here.
Admin /admin/intake_runs exposes the intake journal. No legacy bot was observed running on this host.
Validation: 73 focused offline tests passed; four synthetic calls to real Gemini correctly classified
new MET/5, price-only, old-order edit, missing code. Production end-to-end order test remains distinct.

Data authority: channel message IDs identify external messages; hub SQLite records observations and send intent;
Chatwoot owns staff workflow; ERP owns orders/pricing/customer mapping. Local observations are not proof of full channel history.

2026-10-13 NAS archive: Desktop archive.threads allowlists new captures by exact group ID/activation.
Capture records persist asset IDs in local outbox; a separate Vault thread downloads images/files/public
share links to local spool then copies originals atomically to \\192.168.1.203\n8n_upload\<group>\YYYY-MM\originals.
SHA256 verifies NAS copy; per-file .source.json preserves sender, source account/thread/message, text and URL.
Persistent group-ID mapping keeps renamed groups stable and disambiguates duplicate names. Asset IDs dedupe
repeated captures. Raw files are never executed or extracted. Downloads use public HTTPS only, validated
redirects and pinned public IP connections, <=256 MiB/120s. Private/login HTML share pages fail to staff.
Google Drive file links, OneDrive shares, Dropbox links have resolvers. Public Drive folders now use a
one-time recursive snapshot (max 50 files, 30 folders, depth 5, 256 MiB/file, 1 GiB total). Frozen inventory,
per-file hashes/manifests and final _snapshot.json distinguish complete snapshots from partial failure.
Existing files are hash-checked before reuse; no background monitoring of later additions. Google-native
Docs exports and authenticated/empty/unrecognized listings hand off to staff. Actual trial: one native PDF
(292462 bytes) and 3 Drive files (928817 bytes) saved and verified; recovery recorded in private Chatwoot note.
Local spool survives failures; bounded retries then failed status. New archive captures wait for completion
without stopping source reading. NAS failure retains local files. Hub acknowledgement releases ready local
spool. Chatwoot shows NAS paths/metadata instead of duplicate attachments; Gemini receives bounded previews.
Existing Chatwoot attachments and old Zalo data are untouched. Do not run two Vault workers for one state.

ERP intake: production v2 /api/v1/integrations/zalo/orders is verified read-only on 2026-10-13; it creates
real orders with trang_thai=len_mau, supports PNG image_base64, and deduplicates request_id+payload hash.
Scoped erp_orders_enabled + ERP_WRITE_ENABLED + explicit thread.erp_group mapping are all required before
the Hub writes while global mode remains review. draft_order is an internal extraction action, not a second
ERP draft system. Gemini must name incoming source_message_ids including the latest message; source IDs
are reserved once to prevent repeats. Source text/NAS paths go into line notes; bounded image PNG goes to ERP.
After creation the Hub records ERP IDs and hands the conversation to staff. Uncertain creation never retries
automatically. Outside trial groups cannot create orders in review mode. User selected customer Gia đình
vintuan and product MET. Production ERP requires legacy hyphen-prefixed group names: scoped exact_group_names
opt-in patch was prepared but user rejected changing/restarting ERP; DO NOT run that installer.
ERP writes remain off. Existing ERP UI created one authorized test DH-2610-197 (order UUID
726f7b04-f1c2-467a-af1e-446766b1df28), customer Gia đình vintuan, MET x5, len_mau; no replay.

Evidence PNG module (2026-10-13): hub/evidence_document.py renders exact source text, sender, UTC+07
time, source IDs and captured image previews. Explicit compilation label; never a simulated Zalo screenshot.
Operator CLI zalo_desktop/evidence.py reads the Hub SQLite through Docker in read-only transaction, exact
message IDs scoped to trial group g7557409429748854839. Media must belong to its capture; missing, recalled,
edited or unsupported sources stop for review. Original NAS assets SHA256 verified before rendering.
Vietnamese font, page wrapping without silent truncation, max 10 PNG pages <=5MB each. NAS output:
<group>/orders/<order-code>/evidence-<manifest-hash>/page-NNN.png + source.json (full source metadata,
preview/original hashes, PNG hashes). Identical input reuses identical output; altered existing files rejected.
No AI pairing by time alone; ambiguous selection requires staff. No automatic upload/auth reuse: initial
trial upload uses user's existing ERP session and existing Ảnh khách đặt control, never modifies ERP code.
CLI does not create orders/send Zalo messages/restart services.
Desktop image captions are metadata.title (verified on trial source 8368215292933). Reader now retains
that exact text alongside image bytes/archive references; separate image/text messages remain distinct.
Trial capture's omitted caption was recovered from the read-only Zalo snapshot, backed up and repaired
in Hub capture + NAS source metadata without replaying jobs/AI. Source Zalo databases unchanged.
Trial PNG evidence-0d6d19f30472de01/page-001.png (1552532 bytes) saved under Gia đình vintuan/orders/
DH-2610-197 and uploaded once via existing ERP UI; Ảnh khách đặt shows 1/10. No new order, ERP code edit,
service restart or automatic ERP write enabled. 35 focused evidence/caption/media/Vault tests passed.

POST /ingest -> authenticated adapter -> captures + jobs in one transaction -> worker -> Chatwoot API.
POST /webhooks/chatwoot -> HMAC timestamp/body -> account/inbox filter -> deduplicated jobs.
Incoming -> pending/AI ownership -> bounded public conversation context -> Gemini -> schema/evidence checks
-> recheck latest message and owner -> outgoing AgentBot message OR handoff OR order draft.
Outgoing -> ignore external echo/private -> exact thread mapping -> persistent delivery queue.
Adapter claim -> mark sending -> browser operation -> durable local result -> idempotent report.
Human takeover -> ownership generation advances -> in-flight draft cannot enqueue reply after recheck.
At channel claim, ownership is checked again. A send already issued to the platform cannot be recalled by takeover.

Network timeout on external mutations -> uncertain, no automatic retry. Process restart -> in-flight items uncertain.
SQLite file must live on local disk/Docker volume. One uvicorn worker only; do not horizontally scale this version.

Review mode writes proposed effects only. Demo fixtures contain no real customers and call no external service.
Admin token and adapter token are separate. Secrets never returned by status API. Webhook replay window is 300 seconds.
Media references are retained but not fetched from arbitrary paths/URLs. Unsupported media routes to humans.

Scoped Gemini/image trial (2026-10-12): per-inbox ai_trials maps exact Zalo group IDs to enabled_after.
When configured, other threads never invoke Gemini. Global mode stays review; ERP writes stay disabled.
Only new, <=5-minute incoming capture triggers qualify. Trial replies/handoffs apply to Chatwoot while
other AI effects remain disabled. Handoff sets durable human ownership, opens the conversation and adds
a private reason; explicit Hub control is required to resume AI, with human assignee cleared first.
Trial handoff_user_id=1 assigns the administrator after the private note (Chatwoot otherwise
self-assigns the API bridge). Failed/uncertain delivery notices also hand off the trial conversation.
Generation, claim and prepare all recheck ownership; native sends already issued cannot be recalled.

Desktop msgType=2, ev=0 -> allowlisted image_threads and activation timestamp -> bounded original-image
GET from photo-*.zdn.vn / photo-*.zadn.vn (validated redirects, no cookies) -> JPEG/PNG/WebP, <=4 MiB.
JPEG XL received from Zalo is decoded locally with pillow-jxl-plugin and converted to JPEG before upload;
single-frame images only, at most 24 megapixels, same 4 MiB input/output limits. Zalo originals are untouched.
Failed/unsupported image -> visible placeholder and handoff. No historical image backfill. Image bytes
travel via authenticated /ingest (6 MB request cap); Hub media table stores them once, keyed by capture/hash.
Chatwoot receives multipart attachments. Gemini receives inline_data only from captured media verified
against the same thread and actual Chatwoot message ID, not arbitrary attachment URLs. At most two recent
incoming images support follow-up text; private/staff images are excluded. Image text is untrusted input.
Reader skips already observed IDs before downloading. Source databases/WAL remain read-only.
Trial image 8366970122765 was explicitly checked via private Chatwoot notes 22/23, without a Zalo send.
Follow-up member image 8367012496496 exposed JPEG XL; after the decoder fix it was recovered once
into private note 33 and Gemini reply 34. Zalo echo 8367034368571 confirmed that one reply. The
recovery was explicit, not a replay of the failed capture queue; later new images use the normal reader.

Unimplemented: Zalo send support across app versions/E2EE/media, complete event capture/backfill, direct ERP query tools,
semantic order/customer authorization beyond existing human-approved ERP group mapping, robust automatic reconciliation.

Zalo Desktop inbound module (Windows, zalo_desktop/): configured Zalo process memory read only
-> verified ephemeral session key -> rb snapshot of account Message db/WAL/SHM -> page HMAC,
WAL checksum/commit and SQLite quick_check -> new-only source timestamp gate -> durable local
outbox -> existing /ingest. First start requires explicit baseline initialization; restart keeps it.
Group files g<id> stay distinct; sender names travel with each message. Reader remains read-only.
Per-inbox capture_enabled permits only capture effects to write while global AI mode stays review.
Live capture accounts are exposed in /admin/status. Other effects still follow global mode.
Reader heartbeat/errors are in its separate local state directory. No message history backfill,
edit/recall synchronization, media upload, or automatic recovery of uncertain Chatwoot writes.

Zalo Desktop staff sender (separate Windows process, zalo_desktop/sender.py):
Signed Chatwoot message_created -> verified user sender (exclude bridge), public text, exact
conversation/inbox mapping, created after delivery_after and no older than 5 minutes -> durable queue.
human_delivery_enabled permits this route while HUB_MODE=review keeps Gemini effects in review.
Claim atomically marks sending; claim-time policy is rechecked. Local journal reserves delivery ID
before any send and never sends it again after restart. prepare reserves the native client ID on Hub
before sending, so an echo arriving before the result can be recognized without a duplicate bubble.
Node transport opens localhost Inspector only per operation, checks PID/executable/Electron/build,
finds the main renderer, verifies current Zalo account and group ID/name/status/E2EE, calls native
sendZText with retry=0. No exported cookies/keys or persistent Zalo file modifications. Temporary
webpack module is removed; entry marker restored to the pinned build's main entry 13.
Transport closes Inspector; failed cleanup halts sender. 60-second watchdog closes abandoned sessions.
API success -> submitted; independent outgoing capture with matching account/thread/clientId/text
-> confirmed and suppress public echo. Missing echo after 120 seconds -> uncertain + private note.
Late results never downgrade confirmed. Lost responses/restarts do not requeue sends.
Unsupported/failed/uncertain sends create private notes in Chatwoot even in AI review mode.
Existing review deliveries are never released automatically. Bootstrap resets delivery to off.

2026-10-13: Customer @staff mentions no longer exclude order intake; actual sender/direction and group exclusions remain enforced. Scoped THANH NGUYEN messages 367/368 already reached Chatwoot conversation 34. Staff image quote resolution remains unsupported; do not substitute a nearby image or replay historical orders. Regression: 16 intake/exclusion tests passed.

2026-10-13 quoted photos: Desktop reads quote metadata, resolves photo only in same group using global/client message ID, sender ID and source timestamp. Never uses quote URLs or nearest image. Customer capture carries quoted_image provenance and NAS original/preview; staff messages alone still do not trigger orders. Missing/mismatched/unsupported quotes require review. Evidence labels original author/source ID; Gemini receives provenance. Excluded groups/private chats stay excluded. 39 focused tests passed (offline-reader test fixture updated for existing policy loader).

Quote recovery verified: exact original 8369101976399 from staff matched quote owner/client/timestamp; recovered customer messages 8369728780514 and 8369730143979 only. NAS original and two-page evidence saved. Atomic source reservation replaced policy_skip/ignored only after confirming no submitted run and ERP customer list latest order 22/09. Normal Hub submit created DH-2610-210 / 3dc35c8a-a3fb-4878-b066-ae216b7de5d3, customer THANH NGUYEN, qty100, placement1cm, pending product code. Recovery ID fbeda9d2266be33aec0ee61800372632eaaaa6c0143cd5c01a034f9705135409 remains durable; rerun refused. Multi-page evidence now combines complete pages into one PNG with hashes, 24MP/5MB caps, no cropping; 24 focused tests passed after addition.

2026-10-13 intake batching: same sender/group quiet window 120s; incomplete requests wait up to 1800s from first source. Supplements received within deadline remain eligible through quiet wait. Waiting sources merge durably, old waiting runs superseded. New messages before submission invalidate stale evidence proposal, source reservation and sending claim prevent duplicate submission. Recent already-created requests go to review on possible continuation. Gemini instructed to use explicit later corrections, not add quantities. NAS image previews now attach to Chatwoot while originals stay NAS. 43 focused tests passed; 18 intake tests passed after deadline-boundary fix. Owner authorized 279 previously unbound group IDs -> KHACH LE; 319 bindings total (includes historical excluded binding), 4 groups still excluded, zero unbound permitted known groups. HTML report is read-only and regenerated; no historical order replay.

Live verification: 279 KHACH LE bindings added; 319 total, 4 excluded groups untouched. Added 17 idempotent private NAS preview notes to existing Chatwoot conversations; HOANG DUNG conversation41 notes401/402/403 each have one real attachment. Missing/deleted conversation13 skipped (404), no public channel sends/order replay. Windows reader had exited during C-disk exhaustion; both reader/vault SQLite quick_check=ok, restarted using original cutoff1791803208997.

2026-10-13 print approvals (supersedes earlier media-send limitations):
Allowed customer groups from both Zalo and WhatsApp now have a separate approval route,
independent of ERP quantity/product completeness. After 120 seconds of group silence,
explicit printing approval or exact contextual "Ok nhe/Ok nhé/Ok nha" with a matching
photo within 5 minutes selects the latest same-author photo burst or resolved quoted
staff photo. Missing, mixed-author, recalled/revised or ambiguous images go to a private
review note. No generic OK without context; no private/internal/output group ingestion.
One NAS evidence document is shared by both destinations. print_deliveries stores separate
atomic, at-most-once claims per approval/account; a successful channel is never repeated
because the other failed. Unknown outcomes require reconciliation, never automatic retries.
Targets: Zalo g3307527274697028144; WhatsApp 120363407119559834@g.us (Desktop still labels
this ID IN PET, the group the owner renamed File In - Giay In - Mang Pet).
WhatsApp Desktop reader archives/dispatches both transports; it must remain running.
Zalo native photo sender checks account, exact destination ID, app build, group status,
and non-E2EE; uses native photo processor/sendMsgObject without app-level automatic retry.
Inspector is temporary with cleanup/watchdog. Original photo files/messages are untouched.
WA uses native media preparation/sendToChat through localhost-only 54329; per-app WebView2
registry AdditionalBrowserArguments/WhatsApp.Root.exe persists across normal app launches.
The reader's pinned session identity prevents silently using a different logged-in account.
No blanket policy or network-access expansion; both Desktop apps must be available to send.
Hub endpoints: GET print-deliveries/pending, POST print-deliveries/claim?destination=account,
POST print-deliveries/{delivery_id}; /print-evidence endpoints create/archive the shared PNG.
Completion creates a private Chatwoot note distinct from incomplete ERP warnings.
Live scoped recovery: photo8370172419607 + confirmation8370172968475 (A Thuc), approval
e9c12b727fc00f8e1126aeb09a1e038f0bf4a072eecee5e6239d657fa263a842.
Zalo acknowledged msg8370378960330; WA message3EB051FCD2343D29EC08FA independently ack2.
NAS evidence-a8baa17610cea087/page-001.png; no ERP order created by this recovery.
Earlier WA example3EB067185DFC4426A4307D was not resent. Baseline1791888734.8092554
preserved; only the owner's exact two A Thuc source IDs were backfilled.
Verification: 24 focused print/intake tests passed, including per-channel success/crash
no-retry, contextual OK adjacency, exact quoted photo, and source ambiguity checks.

2026-10-13 post-approval changes:
PrintChanges runs before ordinary approval detection. Only new captured customer messages
in permitted groups are considered; private/internal messages stay excluded. For a group
with a previously dispatched approval, quantity tokens, explicit correction/cancellation
words or a new photo/file produce a versioned change notice after 30 seconds of silence.
Implicit relation is bounded to the recent approval (24h); older explicit corrections and
multiple approvals/authors are prominently marked ambiguous and require staff matching.
The notice never silently replaces a sample or computes an inferred new quantity: it quotes
the prior quantity text and the new customer instruction. Every amendment warns STOP USING
THE OLD PRINT VERSION; images are labeled prior context/new addition. Staff verifies before
continuing production. This does not edit ERP orders or auto-approve a replacement image.
print_change_sources reserves exact source IDs once; amendments reuse the per-channel
print_deliveries at-most-once queue, share a root reference and increment change_version.
NAS source.json separates system_notice from original customer records; PNG has a red header.
If image composition exceeds limits, an explicitly text-only warning retains source IDs and
NAS references so large pictures do not suppress the warning. Capture edits/recalls that the
Desktop reader does not observe are not covered; this route handles new follow-up messages.
Live activation uses print_forward.changes_enabled_after, preserving initial capture and
print-forward baselines; no historical approval replay. No fabricated changes sent to groups.
Verified 35 focused tests, including quantity revisions, photo ambiguity, sequential versions,
independent channel dedup, excluded cross-group/prebaseline messages, PNG and size fallback.
Follow-up numeric-only messages after approval also create a held change notice (no inferred units); prior text preserves the previous instruction even when it omitted units. Additional numeric-follow-up test passed; final focused approval/change/evidence suite: 18 passed.

2026-10-13 W: customer folders and production slips:
Archive folders now use the existing support convention: group prefix before the first
hyphen/dash, unaccented uppercase. New customer_folders table binds account/group ID once;
legacy groups mappings and already archived relative paths/files stay unchanged. Groups
sharing a customer prefix intentionally share its folder; asset hashes still include source
account/group/message. Evidence documents use the same prefix convention for new saves.
ProductionSlips rules live in private HUB_INBOXES.production_slips per account: activation,
window_seconds and group-ID -> sender-ID/folder. A same-sender 'lệnh'/'lệnh in' precedes
an image or occurs in its caption within 15 minutes. Only exact allowed sender/group pairs
are classified by Gemini. It must read PHIẾU LỆNH SẢN XUẤT as the main top heading;
ordinary design photos and unclear headings are rejected. Failures create private review notes.
Verified originals copy idempotently to <customer>/DON HANG with full SHA256 verification;
JPEG XL also gets a PNG companion. Source provenance is saved separately. No ERP write or
public message send is performed by this rule. GET/POST production-slips endpoints use the
existing adapter authentication and recheck capture policy before releasing a copy job.
Live scoped verification: the four existing CANAVI images immediately after the reported
'lệnh in' message produced two production-slip matches and two design-photo rejections.
Only that exact batch is recovered; activation for future messages preserves all reader cutoffs.
Regression: 17 targeted archive/evidence/WhatsApp-media/slip tests passed.


## Pending visibility guard (2026-10-14)
Explicit per-inbox pending_guard_enabled: inspect one mapped conversation every 2 seconds. Pending without an AI trial or with human ownership opens for staff; active AI with no public reply after 300 seconds opens. Private notes are not replies. Preserve open/resolved/snoozed. Retry status checks on later cycles; no public messages, ERP writes, or capture replay. Independent order intake continues.


2026-10-14: waiting_details at 30 minutes now attempts one Gemini image quantity analysis before staff review. Uses exact original source IDs and run/request identity, respects supplements, capture policy, recalls and existing evidence/submission guards. Persist image_timeout_attempted before analysis; ambiguous or failed analysis opens staff review. No replay of already-reviewed/created runs. Text corrections override image quantities.


2026-10-14 ContextGate v1: bounded 6-hour/50-message same-account/group text history with staff role provenance, latest 10 Hub intake candidates (not live ERP status). Schema-validated Gemini intent with exact text evidence. Audit tables context_decisions and context_work_items. Per-inbox context_agent enabled/mode shadow or review/allowed_groups/internal_sender_ids. In review mode only unambiguous new_order without existing reference/missing/conflicts continues existing intake. Guard runs during analysis (including image timeout) and before ERP submission. Failure goes to staff, no new public replies or ERP update powers. Pilot limited to two configured group IDs; historical completed/review runs are not replayed. Authenticated GET /context-agent/status reports latest 50 decisions/work records. Existing source cutoffs and idempotency keys unchanged.


## Agent hiện hành — 2026-10-14
All allowed Zalo/WhatsApp groups: agentic.auto_order=true, internal_only=true, public_replies=false. Gemini proposals feed the existing OrderIntake source/quantity/customer/evidence validation and stable ERP request_id, then create real Lên mẫu orders. Public AI delivery is blocked in Engine even in live mode. inspect_material reads staff fabric reports in the same group (30 days, scan1000, return20); no ERP stock or computed balance. Prior ContextGate pilot is historical and remains a separate guard, not the agent scope. No replay of old proposals. Design worker not implemented. Tests33 pass; deployed config verified, no new live ERP test order created in this change.


## Xác nhận sau hỏi giá — cập nhật 14/10/2026
- [x] Lời OK/chốt/đặt/làm giúp của cùng khách lấy lại cụm review chưa gửi ERP trong cùng nhóm, cùng ngày, tối đa 30 phút và 12 tin nguồn.
- [x] Chờ yên 120 giây để gom bổ sung. Gemini và bước kiểm chứng độc lập đọc cả cụm; OK chỉ mở bước xem xét, không tự đủ điều kiện tạo đơn.
- [x] Hỏi giá đơn thuần hoặc phủ định không mở lại review; lượt created/uncertain hoặc có request_id/submitted_payload không được phục hồi theo cơ chế này.
- [x] Mẫu khác, số lượng mâu thuẫn hoặc thiếu dữ liệu vẫn chuyển nhân viên; không lấy số lượng của mẫu khác.
- [x] Đề xuất hợp lệ tiếp tục lưu bằng chứng NAS rồi tạo ERP Lên mẫu; phản hồi private Chatwoot.
- [x] 42 kiểm thử hồi quy + 1 kiểm thử nối hỏi giá/xác nhận tới đúng một ERP write giả lập đạt.
- [ ] Kiểm chứng lượt khách thật tiếp theo không cần phục hồi thủ công. Không phát lại đơn Chú Dũng đã tạo.


2026-10-15: price_quote.py + versioned pricebook.json add lookup_print_price/prepare_print_quote with deterministic arithmetic and source verification. business_reply_scope suppresses unrelated customer responses; private preview remains. Missing quantity/dimension followups can reclaim uncommitted review sources after recorded clarification. No ERP write for quotes. See docs/NAM_TINH_HUONG_VA_BAO_GIA_20261015.md for owner overrides and unresolved ranges.

2026-10-15 Production slips: SlipOrders independently extracts each copied CANAVI slip, verifies with Gemini, allows null design_code as ERP-generated month-sequence name; unresolved product code uses null product ID (Chờ mã), requires positive quantity. Durable production_slip_orders: extracting→ready→sending→created/duplicate, failure review/uncertain (no auto replay). Generic intake rejects reserved slips. API capabilities gates dispatch. Dedicated ERP production-slip/orders uses existing machine auth/idempotency and same-Vietnam-day customer/code or image duplicate checks. Private Chatwoot notes only. API v2 verified live; five CANAVI receipts created (DH-2610-228 through 232). Design transcription uses two independent reads; discrepancies fall back to ERP name counter. See PHIEU_LENH_TU_DONG_ERP_20261015.md.

2026-10-15 owner confirmation: removed fallback PET7X7 for unrecognized print type. Empty product_codes creates a real Len mau order with null catalog product ID (Chờ mã). Explicit PET 7x7 mapping remains; design/order naming unchanged.

## Viber Desktop (2026-10-15)
Activation update: owner restarted ERP; live Viber API capability and CHI DUNG CDG customer were verified. CDG viber:g1 is now bound to customer 58ca8cd4-1183-4a01-88b1-2e8a81378e98. Agent enabled only for this thread, auto_order=true, internal_only=true, public_replies=false. Order/agent cutoff 1792070386.6971679 prevents history/test replay. Reader reloaded with order-policy.json and shared policy/evidence sync; fresh heartbeat verified. Orders use existing Lên mẫu flow, same-day duplicate checks and durable request identity. No real Viber ERP order has yet been verified. This activation supersedes the historical rollout notes below.
ERP rollout pending ERP restart: order_policy now supports explicit CDG-only Viber policy; order_intake requires customer binding; reader can use shared order_sync for fresh policy/evidence. ERP router staged/deployed with viber source and CDG/account/customer guard, backup recorded in work/viber-orders-deployment.json. Customer CHI DUNG CDG verified. Activation script waits for live ERP capability before enabling new-only internal-agent auto orders; not activated yet. 58 relevant tests passed.
Current operation supersedes the one-shot notes below: after user-authorized successful message `test` (source event viber:552, one occurrence), sender now runs continuously. Admin Startup/PhucThanh-ViberSender.vbs invokes hidden runtime Start-Sender.ps1 without --one; repeated launch creates no extra processes. Fresh heartbeat errors=[]; durable sender.sqlite3 retained. AI public sending remains blocked. Real Windows reboot not tested.
Latest deployment: inbox 3 linked to existing AgentBot; Hub delivery enabled for fresh staff-only CDG text. A local --one worker is armed, errors=[]; it has not sent a real message. Native preflight verifies profile and clean dry-run with fresh group lookup. This supersedes earlier capture-only status below. Sender startup/continuous mode awaits end-to-end acceptance. AI remains disabled/internal-only.
Outgoing implementation now exists in viber_desktop/native_sender.py/js and sender.py. ChatStorage read-only getter RVA 0x46aeb0 resolves CDG from global 0x52e3ad8; the real getter, default Quote constructor and correct shared MessageInfo destructor passed a no-send preflight. No manual marker required. Per-attempt attach executes on QObject::thread matching QThread::currentThread and detaches after one attempt. Adapter writes send_ledger reservation before calling transport, then reconciles a new outgoing source EventID. Source observation is reported submitted, not recipient delivery confirmation. Startup/real delivery acceptance remain pending final end-to-end test; AI is blocked by staff-only delivery policy.
See VIBER.md. Scoped CDG capture, NAS archive, inbox 3/conversation 60. Outbound transport and ERP are not enabled.
Local-only outgoing work: viber_desktop/send_ledger.py commits an uncertain attempt before native invocation and rejects replay or changed payload for the same delivery ID; confirmation requires a source event ID. Not wired to production. Research harness ../viber-research/verify_dispatch.py queues only a GUI-thread dry run after an exact manual binding marker; actual transport verification remains pending. AI/public delivery remains disabled.

2026-10-15 ERP line notes: removed automatic raw source-message transcript and NAS evidence path from order_intake and legacy engine draft notes. Evidence remains in Hub/NAS and Chatwoot private notes. clean_order_note strips technical lines from pending intake payloads before submission. ERP router automatic missing-price reminder removed, backed up on NAS; requires owner restart. Hub deployed; 28 intake regression tests passed. Existing ERP orders unchanged.
