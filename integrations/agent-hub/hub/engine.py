import json
import threading

from hub.ai_policy import ai_delivery, fresh_trial_message, requests_human, trial
from hub.delivery_policy import delivery_block, human_delivery
from hub.order_evidence import evidence_png
from hub.store import event_key


def human_assigned(conversation):
    meta = conversation.get("meta") or {}
    assignee = meta.get("assignee")
    return bool(assignee) and meta.get("assignee_type") != "AgentBot" and assignee.get("type") != "agent_bot"


class Engine:
    def __init__(self, settings, store, chatwoot, agent, erp):
        self.settings, self.store = settings, store
        self.cw, self.agent, self.erp = chatwoot, agent, erp
        self.lock = threading.RLock()
        from hub.customer_mapping import CustomerMappings
        from hub.order_intake import OrderIntake

        self.customer_mappings = CustomerMappings(store)
        self.order_intake = OrderIntake(self)
        from hub.print_approval import PrintApprovals
        self.print_approvals = PrintApprovals(self)
        from hub.production_slips import ProductionSlips
        self.production_slips = ProductionSlips(self)
        from hub.slip_orders import SlipOrders
        self.slip_orders = SlipOrders(self)
        from hub.pending_guard import PendingGuard
        self.pending_guard = PendingGuard(self)
        from hub.artwork_checks import ArtworkChecks
        self.artwork_checks = ArtworkChecks(self)
        from hub.quality_monitor import QualityMonitor
        self.quality_monitor = QualityMonitor(self)
        from hub.leave_monitor import LeaveMonitor
        self.leave_monitor = LeaveMonitor(self)
        from hub.file_previews import FilePreviews
        self.file_previews = FilePreviews(self)

    def effect(self, key, conversation, kind, payload, *, apply_capture=False):
        review = self.settings.mode == "review" and not apply_capture
        with self.store.db() as db:
            old = db.execute("SELECT * FROM effects WHERE id=?", (key,)).fetchone()
            if old:
                if old["state"] in ("done", "review"):
                    return json.loads(old["response"] or "{}")
                raise ValueError("Previous external operation requires reconciliation")
            state = "review" if review else "sending"
            db.execute(
                "INSERT INTO effects VALUES(?,?,?,?,?,NULL)",
                (key, conversation, kind, json.dumps(payload, ensure_ascii=False), state),
            )
        if review:
            return {}
        try:
            outgoing = dict(payload)
            if outgoing.get("_media_ids"):
                outgoing["_images"] = self.store.images(outgoing["_media_ids"])
            if kind == "message":
                result = self.cw.message(conversation, outgoing)
            elif kind == "assignment":
                result = self.cw.assign(conversation, payload["user_id"])
            else:
                result = self.cw.status(conversation, payload["status"])
        except Exception:
            with self.store.db() as db:
                db.execute("UPDATE effects SET state='uncertain' WHERE id=?", (key,))
            raise
        with self.store.db() as db:
            db.execute("UPDATE effects SET state='done',response=? WHERE id=?", (json.dumps(result), key))
        return result

    def note(self, key, conversation, text, *, apply_capture=False):
        return self.effect(
            key,
            conversation,
            "message",
            {
                "content": text,
                "message_type": "outgoing",
                "private": True,
                "content_attributes": {"phucthanh": {"event_id": key, "origin": "hub_note"}},
            },
            apply_capture=apply_capture,
        )

    def handoff(self, key, conversation, reason):
        self.store.set_owner(conversation, "human")
        active = bool(self.trial_for(conversation))
        # Open first: even a failed note must leave the conversation visible to staff.
        self.effect(key + ":open", conversation, "status", {"status": "open"}, apply_capture=active)
        try:
            self.note(key + ":note", conversation, "CẦN NHÂN VIÊN: " + reason, apply_capture=active)
        finally:
            scope = self.trial_for(conversation)
            if scope and scope.get("handoff_user_id"):
                self.effect(
                    key + ":assign",
                    conversation,
                    "assignment",
                    {"user_id": scope["handoff_user_id"]},
                    apply_capture=True,
                )

    def trial_for(self, conversation):
        mapping = self.store.thread(conversation=conversation)
        if not mapping:
            return None
        return trial(self.settings.inboxes.get(mapping["account"], {}), mapping["thread_id"])

    def captured_images(self, conversation, message):
        marker = (message.get("content_attributes") or {}).get("phucthanh") or {}
        mapping = self.store.thread(conversation=conversation)
        if not mapping:
            return []
        with self.store.db() as db:
            row = db.execute(
                "SELECT c.payload,e.response FROM captures c JOIN effects e ON e.id=c.id "
                "WHERE c.id=? AND c.account=? AND c.thread_id=? AND e.state='done'",
                (marker.get("event_id", ""), mapping["account"], mapping["thread_id"]),
            ).fetchone()
        if not row or json.loads(row["response"] or "{}").get("id") != message["id"]:
            return []
        return self.store.images(json.loads(row["payload"]).get("images", []))

    def accept_webhook(self, payload):
        event = payload.get("event")
        if payload.get("account", {}).get("id") != self.settings.cw_account:
            raise ValueError("Wrong Chatwoot account")
        inbox = payload.get("inbox", {}).get("id") or payload.get("inbox_id")
        if inbox not in {int(i["inbox_id"]) for i in self.settings.inboxes.values()}:
            raise ValueError("Inbox not configured")
        if event not in {"message_created", "conversation_status_changed", "conversation_updated"}:
            return False
        conversation = (payload.get("conversation") or payload).get("id")
        if not isinstance(conversation, int) or isinstance(conversation, bool):
            raise ValueError("Missing conversation ID")
        if event != "message_created":
            # Never auto-resume AI from an old/out-of-order webhook.
            if payload.get("status") == "open" or human_assigned(payload):
                self.store.set_owner(conversation, "human")
            return False
        if not isinstance(payload.get("id"), int):
            raise ValueError("Missing message ID")
        if payload.get("private") is True:
            return False
        attrs = payload.get("content_attributes") or {}
        marker = attrs.get("phucthanh") or {}
        message_type = payload.get("message_type")
        if message_type == "outgoing":
            if marker.get("origin") == "external_echo":
                return False
            if marker.get("origin") != "ai":
                self.store.set_owner(conversation, "human")
            return self.store.enqueue(event_key("outgoing", payload["id"]), "outgoing", payload)
        if message_type == "incoming":
            return self.store.enqueue(event_key("incoming", payload["id"]), "incoming", payload)
        return False

    def process_raster_pet(self, key, payload):
        from hub.raster_pet import process
        process(self, payload['id'])

    def process_artwork_check(self, key, payload):
        self.artwork_checks.process(payload['id'])

    def process_design_brief(self, key, payload):
        self.order_intake.design_briefs.collect(payload['run'], payload['messages'])

    def process_one(self):
        self.pending_guard.poll()
        self.store.expire_deliveries()
        job = self.store.claim()
        if not job:
            return self.quality_monitor.poll() or self.leave_monitor.poll() or self.production_slips.poll() or self.slip_orders.poll() or self.order_intake.poll() or self.print_approvals.poll()
        try:
            payload = json.loads(job["payload"])
            getattr(self, "process_" + job["kind"])(job["id"], payload)
            self.store.finish(job["id"], "done")
        except Exception as exc:
            # Do not expose requests, credentials or customer text in diagnostic errors.
            self.store.finish(job["id"], "uncertain", type(exc).__name__)
        return True

    def process_capture(self, key, message):
        if self.store.reconcile_echo(message):
            return
        cfg = self.settings.inboxes[message["account"]]
        apply_capture = cfg.get("capture_enabled") is True
        mapping = self.store.thread(account=message["account"], thread_id=message["thread_id"])
        if not mapping:
            if self.settings.mode == "review" and not apply_capture:
                conversation = int(event_key(message["account"], message["thread_id"])[:10], 16)
                contact = conversation
            else:
                identifier = "pt:" + event_key(message["account"], message["thread_id"])
                conversation, contact = self.cw.create_thread(
                    int(cfg["inbox_id"]), identifier, message["display_name"]
                )
            self.store.bind(
                message["account"], message["thread_id"], message["display_name"], conversation, contact
            )
            mapping = self.store.thread(conversation=conversation)
        conversation = mapping["conversation"]
        text = message["text"]
        if message["sender"] and message["direction"] == "incoming":
            text = message["sender"] + ": " + text
        if message["attachments"]:
            text += "\n[Tệp chưa nhập vào Chatwoot; nhân viên kiểm tra trên kênh gốc]"
        for asset in message.get("assets", []):
            if asset["state"] == "ready":
                text += (
                    "\nĐã lưu NAS: "
                    + cfg.get("archive_root", "").rstrip("\\/")
                    + "\\"
                    + asset["relative_path"].replace("/", "\\")
                )
            else:
                text += "\nChưa lưu được tệp: " + asset["name"] + "; cần nhân viên kiểm tra quyền tải."
        if message["revision"] or message["recalled"]:
            self.note(
                key,
                conversation,
                "Tin được sửa/thu hồi: " + message["message_id"] + "\n" + text,
                apply_capture=apply_capture,
            )
            return
        if message["direction"] == "outgoing":
            self.store.set_owner(conversation, "human")
        self.effect(
            key,
            conversation,
            "message",
            {
                "content": text or "[Tin chưa hỗ trợ hiển thị]",
                "message_type": message["direction"],
                "private": False,
                "source_id": key,
                "_media_ids": message.get("images", []),
                "content_attributes": {
                    "phucthanh": {
                        "event_id": key,
                        "origin": "external_echo" if message["direction"] == "outgoing" else "capture",
                        "has_unsupported_media": bool(message["attachments"]),
                        "source_timestamp": message["timestamp"],
                        "assets": message.get("assets", []),
                    }
                },
            },
            apply_capture=apply_capture,
        )

    def process_incoming(self, key, message):
        conversation = message["conversation"]["id"]
        mapping = self.store.thread(conversation=conversation)
        from hub.quality_monitor import monitored
        if mapping and monitored(mapping["account"],mapping["thread_id"]):return
        if mapping and self.order_intake.scope(mapping["account"]).get("enabled_after"):
            from hub.order_policy import allowed

            policy = self.order_intake.policy(mapping["account"])
            channel = self.settings.inboxes[mapping["account"]]["channel"]
            if policy is None or not allowed(policy, channel, mapping["display_name"], "receive_messages"):
                return
        scoped = bool(self.trial_for(conversation))
        restricted = any("ai_trials" in c for c in self.settings.inboxes.values())
        if restricted:
            mapping = self.store.thread(conversation=conversation)
            if not scoped or not fresh_trial_message(
                self.settings.inboxes[mapping["account"]], mapping["thread_id"], message
            ):
                return
        owner, generation = self.store.ownership(conversation)
        if owner != "ai":
            return
        if self.settings.mode == "live" and not self.settings.cw_bot_id:
            self.handoff(key, conversation, "Chưa cấu hình ID Agent Bot của Chatwoot")
            return
        current = self.cw.conversation(conversation)
        # Pending denotes bot ownership; open/resolved/snoozed belong to the human workflow.
        if current.get("status") != "pending" or human_assigned(current):
            self.store.set_owner(conversation, "human")
            return
        if requests_human(message.get("content") or ""):
            self.handoff(key, conversation, "Khách yêu cầu nhân viên hoặc phản ánh khiếu nại")
            return
        if message.get("content_attributes", {}).get("phucthanh", {}).get("has_unsupported_media"):
            self.handoff(key, conversation, "Không lấy được ảnh hoặc loại tệp chưa hỗ trợ; cần xem trên Zalo")
            return
        try:
            images = self.captured_images(conversation, message) if scoped else []
        except Exception:
            self.handoff(key, conversation, "Không đọc được ảnh đã nhận; cần kiểm tra trên Zalo")
            return
        if message.get("attachments") and not images:
            self.handoff(key, conversation, "Tệp/ảnh chưa được xác minh; nhân viên kiểm tra trên Zalo")
            return
        public = [m for m in self.cw.history(conversation)[-30:] if not m.get("private")]
        # Images and follow-up text often arrive as separate group messages.
        # Keep at most two recent verified incoming images, never staff/private media.
        image_message_ids = [message["id"]] if images else []
        if scoped and len(images) < 2:
            for previous in reversed(public):
                if previous["id"] >= message["id"] or previous.get("message_type") not in (0, "incoming"):
                    continue
                if not fresh_trial_message(
                    self.settings.inboxes[mapping["account"]], mapping["thread_id"], previous
                ):
                    continue
                prior = self.captured_images(conversation, previous)
                if prior:
                    images.extend(prior[: 2 - len(images)])
                    image_message_ids.append(previous["id"])
                if len(images) >= 2:
                    break
        history = [
            {"id": m["id"], "role": m.get("message_type"), "text": m.get("content") or ""} for m in public
        ]
        with self.store.db() as db:
            ordered_ids = [
                r[0]
                for r in db.execute(
                    "SELECT message_id FROM order_sources WHERE conversation=?", (conversation,)
                )
            ]
        try:
            decision = self.agent.decide(
                {
                    "conversation_id": conversation,
                    "messages": history,
                    "latest_message": message.get("content") or "",
                    "latest_message_id": message["id"],
                    "already_ordered_message_ids": ordered_ids,
                    "images": images,
                    "image_message_ids": image_message_ids,
                }
            )
        except Exception:
            self.handoff(key, conversation, "Dịch vụ Gemini lỗi hoặc kết quả không hợp lệ")
            return
        with self.lock:
            newest = [
                m
                for m in self.cw.history(conversation)
                if not m.get("private") and m.get("message_type") in (0, "incoming")
            ]
            if newest and max(m["id"] for m in newest) > message["id"]:
                return
            if self.store.ownership(conversation) != ("ai", generation):
                return
            latest = self.cw.conversation(conversation)
            if latest.get("status") != "pending" or human_assigned(latest):
                self.store.set_owner(conversation, "human")
                return
            if decision.action == "handoff":
                self.handoff(key, conversation, decision.reason or "AI cần nhân viên hỗ trợ")
            elif decision.action == "draft_order":
                if mapping and self.order_intake.scope(mapping["account"]).get("enabled_after"):
                    # Independent intake owns order creation, including human-owned conversations.
                    return
                if not decision.orders:
                    self.handoff(key, conversation, "Đề xuất đơn thiếu dòng hàng")
                    return
                draft = {"orders": [line.model_dump(mode="json") for line in decision.orders]}
                source_ids = sorted(set(decision.source_message_ids))
                if scoped:
                    eligible = {m["id"] for m in public if m.get("message_type") in (0, "incoming")}
                    eligible.add(message["id"])
                    if (
                        message["id"] not in source_ids
                        or not set(source_ids) <= eligible
                        or set(source_ids) & set(ordered_ids)
                    ):
                        self.handoff(
                            key,
                            conversation,
                            "Nguồn đặt hàng thiếu hoặc trùng yêu cầu trước; cần nhân viên đối chiếu",
                        )
                        return
                    png = evidence_png(images, conversation, source_ids)
                    if png:
                        draft["image_base64"] = png
                with self.store.db() as db:
                    db.execute("BEGIN IMMEDIATE")
                    if source_ids:
                        existing = db.execute(
                            "SELECT message_id FROM order_sources WHERE conversation=?", (conversation,)
                        ).fetchall()
                        if set(source_ids) & {r[0] for r in existing}:
                            raise ValueError("Order source already reserved")
                        db.executemany(
                            "INSERT INTO order_sources VALUES(?,?,?)",
                            [(conversation, sid, key) for sid in source_ids],
                        )
                    db.execute(
                        "INSERT OR IGNORE INTO drafts(id,conversation,payload) VALUES(?,?,?)",
                        (key, conversation, json.dumps(draft, ensure_ascii=False)),
                    )
                scope = self.trial_for(conversation) or {}
                if scope.get("erp_orders_enabled") and self.settings.erp_write:
                    try:
                        result = self.approve_order(key)
                        codes = ", ".join(
                            str(o.get("ma_don_hang", o.get("id", ""))) for o in result.get("orders", [])
                        )
                        self.handoff(key, conversation, "Đã tạo đơn thật ERP ở trạng thái Lên mẫu: " + codes)
                    except Exception:
                        self.handoff(
                            key,
                            conversation,
                            "Chưa xác nhận tạo đơn ERP; kiểm tra trạng thái yêu cầu "
                            + key
                            + " trước khi thử lại",
                        )
                else:
                    self.handoff(
                        key, conversation, "Yêu cầu lên đơn đang chờ cấu hình ERP/khách hàng. Mã: " + key
                    )
            else:
                if not decision.reply.strip():
                    self.handoff(key, conversation, "AI trả lời rỗng")
                    return
                self.effect(
                    key + ":reply",
                    conversation,
                    "message",
                    {
                        "content": decision.reply,
                        "sender_type": "AgentBot",
                        "sender_id": self.settings.cw_bot_id,
                        "message_type": "outgoing",
                        "private": False,
                        "content_attributes": {
                            "phucthanh": {
                                "event_id": key + ":reply",
                                "origin": "ai",
                                "generation": generation,
                            }
                        },
                    },
                    apply_capture=scoped,
                )

    def process_outgoing(self, key, message):
        conversation = message["conversation"]["id"]
        mapping = self.store.thread(conversation=conversation)
        if not mapping:
            cfg = next(
                i for i in self.settings.inboxes.values() if int(i["inbox_id"]) == message["inbox"]["id"]
            )
            if cfg["channel"] != "native":
                self.handoff(key, conversation, "Chưa liên kết ID hội thoại kênh cá nhân; chưa gửi tin")
            return
        attrs = (message.get("content_attributes") or {}).get("phucthanh") or {}
        if attrs.get("origin") == "ai" and self.store.ownership(conversation) != (
            "ai",
            attrs.get("generation"),
        ):
            self.note(key + ":cancel", conversation, "Đã hủy tin AI vì nhân viên tiếp quản")
            return
        cfg = self.settings.inboxes[mapping["account"]]
        if int(cfg["inbox_id"]) != (message.get("inbox", {}).get("id") or message.get("inbox_id")):
            raise ValueError("Conversation/inbox mismatch")
        if attrs.get('origin') == 'ai' and cfg.get('agentic',{}).get('internal_only'):
            self.note(key+':internal-only',conversation,'Đã chặn gửi AI: đang ở chế độ xem trước nội bộ.',apply_capture=True)
            return
        permitted = human_delivery(self.settings, cfg, message) or ai_delivery(
            self.settings, cfg, message, mapping["thread_id"]
        )
        reason = delivery_block(self.settings, cfg, message, mapping["thread_id"])
        state = (
            "review"
            if self.settings.mode == "review" and not permitted
            else ("blocked" if reason else "queued")
        )
        with self.store.db() as db:
            db.execute(
                "INSERT OR IGNORE INTO deliveries(id,account,thread_id,conversation,payload,state) VALUES(?,?,?,?,?,?)",
                (
                    key,
                    mapping["account"],
                    mapping["thread_id"],
                    conversation,
                    json.dumps(message, ensure_ascii=False),
                    state,
                ),
            )
        if state == "blocked":
            self.note(
                key + ":blocked",
                conversation,
                "Chưa gửi ra kênh: " + reason,
                apply_capture=permitted,
            )

    def approve_order(self, key):
        if not self.settings.erp_write:
            raise ValueError("ERP write disabled; review only")
        with self.store.db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM drafts WHERE id=?", (key,)).fetchone()
            if not row or row["state"] != "draft":
                raise ValueError("Draft is unavailable/already submitted")
            scope = self.trial_for(row["conversation"]) or {}
            if self.settings.mode != "live" and not scope.get("erp_orders_enabled"):
                raise ValueError("ERP disabled outside explicit trial")
            mapping = db.execute(
                "SELECT erp_group FROM threads WHERE conversation=?", (row["conversation"],)
            ).fetchone()
            if not mapping or not mapping["erp_group"]:
                raise ValueError("Human-verified ERP customer mapping required")
            payload = json.loads(row["payload"])
            payload.update(request_id="chatwoot:" + key, group_name=mapping["erp_group"])
            db.execute("UPDATE drafts SET state='sending',payload=? WHERE id=?", (json.dumps(payload), key))
        try:
            result = self.erp.create_order(payload)
        except Exception:
            with self.store.db() as db:
                db.execute("UPDATE drafts SET state='uncertain' WHERE id=?", (key,))
            raise
        with self.store.db() as db:
            db.execute("UPDATE drafts SET state='created',result=? WHERE id=?", (json.dumps(result), key))
        self.note(
            key + ":erp",
            row["conversation"],
            "ERP đã tạo đơn: " + json.dumps(result, ensure_ascii=False),
            apply_capture=bool(scope),
        )
        return result

    def process_notice(self, key, payload):
        mapping = self.store.thread(conversation=payload["conversation"])
        cfg = self.settings.inboxes.get(mapping["account"], {}) if mapping else {}
        if self.trial_for(payload["conversation"]):
            with self.store.db() as db:
                row = db.execute(
                    "SELECT state FROM deliveries WHERE id=?", (key.rsplit(":", 1)[0],)
                ).fetchone()
            if row and row["state"] in {"blocked", "failed", "uncertain"}:
                self.handoff(key, payload["conversation"], payload["text"])
                return
        from hub.quality_monitor import monitored
        quality=bool(mapping and monitored(mapping['account'],mapping['thread_id']) and payload.get('quality_review'))
        if quality:
            self.store.set_owner(payload['conversation'],'human')
            self.effect(key+':open',payload['conversation'],'status',{'status':'open'},apply_capture=True)
        self.note(
            key,
            payload["conversation"],
            payload["text"],
            apply_capture=quality or cfg.get("human_delivery_enabled") is True,
        )

