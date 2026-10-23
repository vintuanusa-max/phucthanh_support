# Replicate redraw — 22/10/2026

- [x] Provider: black-forest-labs/flux-kontext-pro; image reference, no mirroring.
- [x] Requires staff asking for source design file followed by customer confirmation no file, with message IDs and same-customer guard. Current window: 30 minutes; answer must belong to current design brief context.
- [x] Only selected standalone artwork; ambiguous/missing source, product-photo-only, unreadable text or white-on-white artwork goes to private staff review.
- [x] Gemini reads original text, then checks generated image and exact normalized text/digits. Failed checks stop TIFF export.
- [x] One POST per brief/side; durable receipt written BEFORE submission. Unknown outcome requires staff inspection; never automatic paid retry.
- [x] Secret stored in /data/secrets/replicate-token, outside Git/source, mode 0600. GET account/model validated, no token in receipts.
- [x] Six isolated mocked tests: consent, illegible source, success/cache, altered digits, uncertain submit, output host restriction.
- [ ] Real paid generation through this background provider and resulting Photoshop/Chatwoot end-to-end still require observation on the next eligible new request. Existing CAN_THO result was produced by earlier manual imagegen, not this provider.

Outputs follow existing {customer}/DESIGNER/{model}/versions/{job_id}, PNG + TIFF spot_1; white artwork no contraction, colors contracted 1px; private Chatwoot review only. No ERP replay, no RIP or customer send. Old archived jobs remain untouched.

If source image cannot be confidently tied to the customer's no-file answer, keep a private review note; do not redraw an arbitrary recent logo. This release does not add product-photo extraction or silently reuse historical consent.
