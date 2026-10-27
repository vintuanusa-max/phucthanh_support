# ERP intake routing — 2026-10-27

- [x] Wait configured quiet window before routing; new eligible messages reset it.
- [x] Text/context classifier before intake splitting and image calls. Only certain payment, delivery, invoice, progress, complaint batches with no order/sample request are ignored by ERP intake. Mixed/unclear/image-only batches continue.
- [x] Classifier failure continues existing analysis, never silently drops a batch.
- [x] Versioned image observations cached by model + account + group + MIME + image SHA256. Agent uses certain observations, with current message IDs; uncertain/failed extraction falls back to original images.
- [x] Original images remain in independent proposal verification. Cached observations never mean an order was already created; source claims/request idempotency remain authoritative.
- [x] Payment quantity is not a new order in proposal and verification prompts.
- [x] No replay of old runs. DH-2610-363 owner-deleted: retain existing created/source ledger; no recreation requested.
- [x] Four offline regression tests (including mixed/unknown routing, source coverage, cache hits, group isolation) passed.
- [ ] Live Gemini classification test: blocked by automatic approval review; not executed. Production accuracy/token savings still require observation.

Files: intake_preflight.py, order_intake.py, agent_loop.py. Tables: intake_route_audit, intake_analysis_cache, created lazily. Existing branches outside AgentLoop retain original vision; cache is not claimed global to all workflows.

## Source lifecycle
- [x] Non-order intents and placement notices excluded from recovered order batch.
- [x] Stable message-ID guard against committed, sending, uncertain sources and retained order_source_links (including deleted ERP orders).
- [x] Explicit additions do not reclaim previous captures; quantity is taken from new request. Separate total accepted only with explicit total wording.
- [x] Eight SQLite in-memory tests passed; no real ERP test writes, no external model test calls.
- [x] Image observations remain separate from source consumption ledger.
- [ ] End-to-end production accuracy remains subject to new-message observation.


## 2026-10-27: grouped quiet window and non-order media
- Group eligible captures by account/thread, regardless of sender; late eligible messages invalidate pending draft/evidence before submission.
- Exact media duplicate detection only within the same group and confirmed ERP-linked runs; fresh additions bypass suppression. Ambiguous forwards stay review, approvals are ignored by order intake.
- Narrow text fast path for complaint/progress/quote/delivery/information; mixed requests or unknown sources fall through. Version route-v2-nonorder preserves existing visual cache keys.
- ContextGate uses complete certain cached observations, retains original vision on cache miss/uncertainty.
- Parse explicit addition clause after a completed complaint separately from historical quantities; retain conditional/negative/conflicting guards.
- Offline validation: 82 passing cases in the simulation set, no production writes. Production model accuracy and real token savings remain unmeasured.

Pre-commit verification: clean HEAD plus exactly the staged ERP changes passed 55/55 targeted tests in an offline container. Staged-content secret-pattern scan found no credentials; no runtime config, sessions, DB or image data included.
