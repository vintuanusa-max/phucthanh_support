# Zalo Desktop reader

Windows-only inbound module for the verified Zalo PC 26.10.11 format. It has no Zalo send operation.
It uses PROCESS_QUERY_INFORMATION + PROCESS_VM_READ against the configured executable only.
Session material stays in process memory; it is never logged, persisted, or sent to the hub.

## State and data flow

Zalo Message/*.db + *-wal -> stable metadata/WAL-index observation -> authenticated SQLCipher v4
pages -> last committed WAL snapshot -> SQLite in memory -> supported field decoder -> local outbox
-> authenticated POST /ingest -> dedicated Chatwoot inbox.

Initialize exactly once with `python -m zalo_desktop.reader --config reader.local.json --initialize`.
This records the current clock and file fingerprints. Only messages with source timestamps AFTER
that boundary are imported. Restart preserves that boundary and pending outbox. Never delete state
as a restart procedure. Each account/source must have a separate state directory and inbox mapping.

Run with `uv run --frozen --no-dev --group desktop python -m zalo_desktop.reader --config reader.local.json`.
Source db/WAL/SHM are opened as rb only. No source SQLite connection, checkpoint, cleanup, injection,
patch, hook, or DLL load is performed. Decoded snapshots live in RAM; captured new messages are
stored in the separate local state DB to survive outages. Snapshot checks are for ingestion, not a
replacement for an application-supported backup. If the source changes during reading, retry later.

## Chatwoot controls

Set capture_enabled=true only for the Zalo entry of HUB_INBOXES. Keep HUB_MODE=review,
delivery_enabled=false and ERP_WRITE_ENABLED=false. Capture effects then write to Chatwoot;
AI-generated effects remain review-only. No other inbox gains capture permission.
The bootstrap configuration script preserves capture_enabled on subsequent startup.

## Groups and limitations

A file g<id>.db maps to its own Chatwoot conversation/contact, with sender names prefixed to
incoming text. This is a shared group thread, not separate chats for each member. Group display names
are read automatically from Core/Index.db (group.userId/displayName) every 60 seconds.
Authenticated lazy APSW virtual pages read only required metadata pages, overlay committed WAL,
and reject a changing source. No plaintext index is saved. WAL limit is 512 MiB for this metadata path.
POST /adapters/{account}/thread-names updates existing mapped contacts without creating messages
or conversations. Group IDs remain internal identity keys, so duplicate names stay separate.
Unknown names show “Nhóm Zalo (đang lấy tên)” and are corrected on a successful metadata refresh.
Cached names stay in memory on temporary errors; automatic names take priority over thread_names.
DMs use an observed sender name
when available. Account identity is pinned, not guessed from whichever user signs into Zalo next.
Text ev=0 has been verified. Outside the explicit image trial below, other formats/media produce a visible
placeholder requiring the original Zalo app. Existing message edits/recalls and historical backfill are not
synchronized in this version. Re-importing history requires a separate deliberate workflow.

Polling defaults to 10 seconds. Database/WAL snapshots are bounded to 256 MiB each; larger files
remain unprocessed with a visible error. Frequent writes can postpone a stable snapshot. New formats,
Zalo upgrades, missing process read access or missing key leave the collector waiting with errors,
never reset the baseline and never write to Zalo. Do not run the old relay for this same account.

`status.json` records heartbeat, pending/accepted counts and sanitized errors. Accepted means stored
by the Hub, not necessarily delivered to Chatwoot. Inspect Hub jobs/effects for uncertain operations;
these need reconciliation and are not blindly retried. POST /ingest retries use stable message IDs.
No production SLA or complete capture of messages absent from the local Zalo database is implied.

References: https://sqlite.org/fileformat2.html#walformat ; https://www.zetetic.net/sqlcipher/design/

Metadata VFS reference: https://rogerbinns.github.io/apsw/vfs.html
# Staff replies from Chatwoot

The separate `python -m zalo_desktop.sender --config reader.local.json` process sends public
text replies authored by Chatwoot users. Set `node_exe` in the local configuration to the
installed Node 24 executable. Keep `user_id`, `account`, and `zalo_exe` consistent with the reader.
Use `Start-Sender.ps1` / `Stop-Sender.ps1` from the installed runtime directory.

Hub inbox flags: `delivery_enabled=true`, `human_delivery_enabled=true`, `desktop_sender=true`,
`delivery_after=<activation Unix seconds>`, `excluded_sender_ids=[<bridge user ID>]`.
Keep `HUB_MODE=review` to leave AI replies in review outside explicit `ai_trials`. Only new staff messages are eligible;
old review items are not replayed. Text older than five minutes is blocked.

Supported build: Zalo PC 26.10.11, renderer hash b7bec208c4c8f73e09f8, Electron 22.3.9.
Supports ordinary non-E2EE groups with visibility/status 0 and exact ID/name mapping.
Images, files, quotes requiring platform metadata, individual chats and E2EE are not supported.
No additional login, browser session, or UI automation is used. The sender briefly opens
Inspector on localhost, executes the existing native send function, then closes Inspector.
An app update, different account, changed name or unavailable session blocks delivery.

`state/sender/sender.sqlite3` stores at-most-once attempts separately from source data.
`state/sender/status.json` reports health without secrets. Do not delete the journal or
reset a sending/uncertain delivery to queued. Check the actual group before any manual resend.
`halt.flag` means transport/cleanup needs investigation; Start-Sender refuses to clear it.
The reader's `channel_send=false` continues to describe the read-only reader, not this process.

API acceptance is submitted, not proof of receipt by all participants. An independent Desktop
echo confirms the platform message and prevents a duplicate public Chatwoot bubble. Without an
echo within two minutes the Hub adds a private warning and never retries automatically.

# Scoped image and Gemini trial

Hub inbox `ai_trials` and Desktop `image_threads` both map `g7557409429748854839` to
`{"enabled_after": <Unix seconds>}`. Only this group (Gia đình vintuan) is enabled in this trial.
Keep other trial maps empty and ERP writes off. With trial configuration present, other groups
do not invoke Gemini. Set conversation 11 to AI using the Hub owner control after removing any
human assignment in Chatwoot. New incoming messages can generate actual text replies while
global mode remains review. Messages sent by the signed-in Zalo account are staff messages;
they do not trigger AI, and they pause it until explicitly resumed.

For new image messages, the reader downloads the original URL recorded by Desktop, without
cookies or another login. Only HTTPS photo CDN URLs under zdn.vn/zadn.vn and validated redirects
are accepted. JPEG/PNG/WebP up to 4 MiB are supported. No source Zalo files are changed.
JPEG XL (.jxl) is decoded using the desktop dependency group and converted to JPEG in memory
before upload (single-frame, <=24 megapixels, <=4 MiB input/output).
Decoder: https://github.com/Isotr0py/pillow-jpegxl-plugin
Image bytes are retained in the local reader outbox, Hub media database and Chatwoot attachment
storage; only the authorized trial's incoming images are sent to the configured Gemini API.
At most two verified incoming images from the last five minutes accompany follow-up text.
Failed downloads, unsupported media, unclear image content, provider errors and human requests
stop AI, open the Chatwoot conversation and add a private explanation. Staff can claim it there.
Resume AI explicitly through the Hub dashboard after removing the human assignee.
Sending images back to Zalo is still unsupported; AI replies are text only.

