# Zalo quoted-image fallback — 2026-11-01

## Running flow

- Windows reader keeps the exact quoted message metadata from the local Zalo database.
- For an explicit single PET addition in customer text, with an expired quoted image and no usable image, `quote_screenshot.py` attempts a native Windows screenshot once per source fingerprint. No Computer Use service or image AI is used.
- `ZaloQuoteCapture.cs` opens the existing Zalo window, selects an unambiguous exact group name if necessary, and verifies the visible customer text, sender, quoted sender/image, date and time. Search/selection is bounded; missing/ambiguous/offscreen messages fail closed. It does not automatically scroll through old history or guess a group.
- PrintWindow captures only Zalo and crops to its chat container. Blank output is rejected. Original failed media metadata remains unchanged.
- Screenshot is archived under the customer's monthly `evidence` folder and uploaded as `conversation_evidence`, not `images` or a printable asset.
- Hub binds the screenshot to account, group, current message, quoted message and source hash. It stores it separately and posts an idempotent private Chatwoot note.
- A single clear PET addition uses only the text quantity and existing intake ERP write/receipt guards. Missing product code remains null/Chờ mã; no code is guessed from PET. The old quantity is not copied.
- Missing screenshot requires review without an image-AI call on this fast path. Other order types and multi-request batches continue through the existing classifier; they are not covered by this narrow deterministic shortcut.
- ERP evidence selection includes the screenshot. Print-source routing and AI image lists do not include it.

## Retry and safety

- A failed or interrupted screenshot attempt is retained for review, not retried endlessly.
- Newly edited/recalled messages, ambiguous quantities, conditional orders and design requests do not use this shortcut.
- Completed or uncertain ERP writes remain protected by the original request ID and source ledger.
- No old completed order is replayed; no RIP, customer message, or print-file copy is initiated by this fallback.

## Verification

- [x] Native MSAA + PrintWindow captured the authorized customer group and its explicit PET addition without Computer Use.
- [x] Verified capture includes group header, quoted image and customer text.
- [x] Isolated DB tests: strict proof binding; wrong group/text rejected; duplicated ingest remains one capture/evidence; screenshot excluded from AI image list and included in ERP evidence.
- [x] Quantity tests reject negation, questions, multiple quantities, total quantity and design requests. Staff mention @Thiết Kế alone is not treated as a design request.
- [x] Existing ERP flow created one authorized Lên mẫu order with the quantity from text. The Chatwoot private note includes the screenshot. No AI image call was required for this retry.
- [x] Portable synthetic-image/isolated-DB checks: altered source/hash rejection, submitted/existing ERP guard, stable request ID and missing-proof review; no external API or real ERP write.
- [ ] Unattended selection of a different group through the search UI: code present, not production-tested in this session. Ambiguous selection stops safely.

Files: hub/quote_conversation_evidence.py, models.py, store.py, engine.py,
order_intake.py, evidence_document.py; zalo_desktop/quote_screenshot.py,
vault.py, ZaloQuoteCapture.cs, capture-verified-quote.ps1.

Regression check (from integrations/agent-hub, with project dependencies):
`PYTHONPATH=. python tests/test_quote_screenshot_contract.py`
