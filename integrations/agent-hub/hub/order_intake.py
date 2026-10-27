"""Independent, durable new-message order intake. Never sends public replies."""

import base64
from hub.workflow_errors import describe
import json
import re
import time
from decimal import Decimal

import httpx

from hub.evidence_document import select_sources
from hub.media import decode_image
from hub.order_policy import eligible, key, sanitize, allowed
from hub.store import event_key
from hub.order_notes import clean_order_note


def confirms_order(text):
    text = key(text)
    if re.search(r'\?|\b(chưa|không|khoan|đừng|hủy|huỷ)\b', text):
        return False
    return bool(re.search(r'\b(ok|oke|đồng ý|chốt|đặt|làm giúp|in giúp|in luôn|in dùm|in giùm|cho in)\b', text))


def image_only_caption_pending(message, order_text, *, image_proposal=False):
    """Allow only the legacy caption marker, never a missing media attachment."""
    text = key(order_text)
    return (
        message.get('attachments') == ['whatsapp-desktop:caption-unverified']
        and bool(message.get('images'))
        and len(message.get('assets', [])) == len(message['images'])
        and all(a.get('kind') == 'image' and a.get('state') == 'ready'
                and a.get('sha256') and a.get('relative_path') for a in message['assets'])
        and not re.search(r'\?|\b(chưa|không|khoan|đừng|hủy|huỷ)\b', text)
        and (image_proposal or bool(re.search(r'\b(chạy|chốt|đặt|in giúp|làm giúp|in luôn|in dùm|in giùm)\b', text)))
    )


def sender_key(message):
    return message.get("sender_id") or key(message["sender"])


def piece_quantities(text):
    values = re.findall(r"(?<![\w.])(\d{1,3}(?:\.\d{3})+|\d+(?:[.,]\d+)?)\s*(?:c\b|cái\b)", text, re.I)
    return {
        Decimal(v.replace(".", "") if re.fullmatch(r"\d{1,3}(?:\.\d{3})+", v) else v.replace(",", "."))
        for v in values
    }


class OrderIntake:
    def __init__(self, engine):
        self.engine = engine
        self.store = engine.store
        from hub.context_gate import ContextGate
        self.context_gate = ContextGate(engine)
        from hub.agent_loop import AgentLoop
        self.agent_loop = AgentLoop(self)
        from hub.design_briefs import DesignBriefs
        self.design_briefs = DesignBriefs(self)
        from hub.order_additions import OrderAdditions
        self.additions = OrderAdditions(self)
        with self.store.db() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS intake_policy (
                    account TEXT PRIMARY KEY, payload TEXT NOT NULL, updated REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS intake_runs (
                    id TEXT PRIMARY KEY, account TEXT NOT NULL, thread_id TEXT NOT NULL,
                    conversation INTEGER NOT NULL, state TEXT NOT NULL, payload TEXT NOT NULL,
                    result TEXT NOT NULL DEFAULT '{}', created REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS intake_sources (
                    capture_id TEXT PRIMARY KEY, run_id TEXT NOT NULL);
            """)

    def sync_policy(self, account, config):
        value = sanitize(config)
        # NAS config.json delivered by the Zalo reader is authoritative for all channels.
        if account == 'zalo-personal-1':
            import os
            path=os.environ.get('GROUP_CUSTOMER_MAPPING_FILE')
            if path:
                from hub.mapping_file import synchronize
                synchronize(config,path)

        with self.store.db() as db:
            db.execute(
                "INSERT OR REPLACE INTO intake_policy VALUES(?,?,?)",
                (account, json.dumps(value, ensure_ascii=False), time.time()),
            )

    def recover(self):
        self.agent_loop.recover()
        with self.store.db() as db:
            interrupted = db.execute(
                "SELECT id,conversation,state FROM intake_runs WHERE state IN ('analyzing','sending')"
            ).fetchall()
            for row in interrupted:
                state = "uncertain" if row["state"] == "sending" else "review"
                db.execute("UPDATE intake_runs SET state=? WHERE id=?", (state, row["id"]))
        for row in interrupted:
            self.store.enqueue(
                row["id"] + ":interrupted",
                "notice",
                {
                    "conversation": row["conversation"],
                    "text": "CẦN NHÂN VIÊN: Bộ lên đơn bị gián đoạn. Đối chiếu ERP trước khi làm lại: "
                    + row["id"][:12],
                },
            )

    def policy(self, account):
        with self.store.db() as db:
            row = db.execute("SELECT * FROM intake_policy WHERE account=?", (account,)).fetchone()
        if not row or row["updated"] < time.time() - 120:
            return None  # A disconnected/malformed source config must stop new orders.
        return json.loads(row["payload"])

    def scope(self, account):
        return self.engine.settings.inboxes.get(account, {}).get("order_intake", {})

    def accepts(self, message):
        from hub.quality_monitor import monitored
        if monitored(message["account"],message["thread_id"]):return False
        cfg = self.engine.settings.inboxes.get(message["account"], {})
        if cfg.get('production_slips',{}).get('auto_order'):
            with self.store.db() as db:
                reserved=db.execute("SELECT 1 FROM production_slips WHERE account=? AND thread_id=? AND message_id=? AND state IN ('classifying','review','copy_pending','copied')",(message['account'],message['thread_id'],message['message_id'])).fetchone()
            if reserved:return False
        policy = self.policy(message["account"])
        scope = self.scope(message["account"])
        agent_scope=self.agent_loop.scope(message)
        if agent_scope and policy is not None:
            channel=cfg.get('channel')
            if not allowed(policy,channel,message['display_name'],'receive_messages'):return False
            policy=dict(policy)
            policy[channel+'_default_auto_order']=True
            policy[channel+'_contact_rules']=[{**r,'auto_order':True} for r in policy.get(channel+'_contact_rules',[])]
        return bool(
            scope.get("enabled_after")
            and policy is not None
            and message["timestamp"] >= scope["enabled_after"]
            and eligible(policy, cfg.get("channel"), message)
        )

    def media_scope(self, message):
        # Already queued files must still ingest after a later policy change. The
        # Windows reader applies policy before downloading; creation rechecks it.
        scope = self.scope(message["account"])
        media = self.engine.settings.inboxes.get(message["account"], {}).get("media_capture", {})
        return any(s.get("enabled_after") and message["timestamp"] >= s["enabled_after"] for s in (scope, media))

    def notify(self, run, reason):
        with self.store.db() as db:
            current=db.execute('SELECT state,result FROM intake_runs WHERE id=?',(run['id'],)).fetchone()
        if current and current['state']=='ignored' and json.loads(current['result']).get('intent'):
            return

        self.engine.store.set_owner(run["conversation"], "human")
        self.engine.effect(
            run["id"] + ":open", run["conversation"], "status", {"status": "open"}, apply_capture=True
        )
        self.engine.note(run["id"] + ":notice", run["conversation"], reason, apply_capture=True)

    def state(self, identity, state, result=None):
        if state == 'review':
            from hub.intake_intent import classify, evidence, HISTORY
            with self.store.db() as db:
                row=db.execute('SELECT * FROM intake_runs WHERE id=?',(identity,)).fetchone()
                proposals=db.execute('SELECT 1 FROM agent_proposals WHERE run_id=? LIMIT 1',(identity,)).fetchone()
                if row and row['state'] not in ('sending','uncertain','created','duplicate') and not proposals:
                    p=json.loads(row['payload']);category,why=classify(evidence(db,row,p),p,result)
                    if category in HISTORY:
                        state='ignored';result={**(result or {}),'intent':category,'reason':why,'erp_committed':False}
        with self.store.db() as db:
            db.execute(
                "UPDATE intake_runs SET state=?,result=? WHERE id=?",
                (state, json.dumps(result or {}, ensure_ascii=False), identity),
            )
        if state in ('created','duplicate'):
            from hub.print_linking import sync_links
            sync_links(self.store)

    def poll(self):
        """One operation at a time; claims survive restart without replaying writes."""
        from hub.intake_models import poll as poll_models
        if poll_models(self):return True
        if self.additions.recover_notice():return True
        with self.store.db() as db:
            expired = db.execute(
                "SELECT * FROM intake_runs WHERE state='waiting_details' "
                "AND COALESCE(json_extract(payload,'$.last_timestamp'),json_extract(payload,'$.first_timestamp'),created)<? ORDER BY created",
                (time.time() - self.engine.intake_management.seconds(),),
            ).fetchall()
            expired = next((x for x in expired if self.engine.intake_management.enabled(x['account'])),None)
        if expired:
            pending_payload = json.loads(expired['payload'])
            deadline = pending_payload.get('last_timestamp', pending_payload.get('first_timestamp', expired['created'])) + self.engine.intake_management.seconds()
            with self.store.db() as db:
                supplements = db.execute(
                    "SELECT c.payload FROM captures c LEFT JOIN intake_sources s ON s.capture_id=c.id "
                    "WHERE c.account=? AND c.thread_id=? AND s.capture_id IS NULL "
                    "AND json_extract(c.payload,'$.timestamp')>=?",
                    (expired['account'], expired['thread_id'], pending_payload.get('last_timestamp', expired['created'])),
                ).fetchall()
            if not any(sender_key(json.loads(r[0])) == pending_payload['sender_key']
                       and self.accepts(json.loads(r[0])) for r in supplements):
                if self.image_timeout_review(dict(expired), pending_payload):
                    return True
                self.state(expired['id'], 'review', {'reason': 'Đã hết thời gian chờ cấu hình, chưa đủ thông tin'})
                self.notify(dict(expired), 'CẦN NHÂN VIÊN: Yêu cầu đã hết thời gian chờ cấu hình nhưng chưa đủ thông tin để lên đơn.')
                return True
        with self.store.db() as db:
            waiting = db.execute(
                "SELECT * FROM intake_runs WHERE state='evidence_ready' ORDER BY created"
            ).fetchall()
            waiting = next((x for x in waiting if self.engine.intake_management.enabled(x['account'])),None)
        if waiting:
            self.submit(dict(waiting))
            return True
        for account, cfg in self.engine.settings.inboxes.items():
            if not self.engine.intake_management.enabled(account):continue
            scope = self.scope(account)
            if not scope.get("enabled_after") or self.policy(account) is None:
                continue
            with self.store.db() as db:
                rows = db.execute(
                    "SELECT c.id,c.payload FROM captures c JOIN jobs j ON j.id=c.id AND j.state='done' "
                    "LEFT JOIN intake_sources s ON s.capture_id=c.id "
                    "WHERE c.account=? AND s.capture_id IS NULL AND json_extract(c.payload,'$.timestamp')>=? "
                    "ORDER BY json_extract(c.payload,'$.timestamp'),c.rowid LIMIT 200",
                    (account, scope["enabled_after"]),
                ).fetchall()
            available = [(r["id"], json.loads(r["payload"])) for r in rows]
            checked_streams = set()
            for identity, message in available:
                if not self.accepts(message):
                    with self.store.db() as db:
                        db.execute(
                            "INSERT OR IGNORE INTO intake_sources VALUES(?,?)", (identity, "policy_skip")
                        )
                    continue
                stream_key = (message['thread_id'], sender_key(message))
                if stream_key in checked_streams:
                    continue
                checked_streams.add(stream_key)
                # Load the complete sender/group stream, not only the first 200 global rows.
                with self.store.db() as db:
                    stream = db.execute(
                        "SELECT c.id,c.payload,j.state AS job_state FROM captures c "
                        "LEFT JOIN jobs j ON j.id=c.id LEFT JOIN intake_sources s ON s.capture_id=c.id "
                        "WHERE c.account=? AND c.thread_id=? AND s.capture_id IS NULL "
                        "AND json_extract(c.payload,'$.timestamp')>=? ORDER BY json_extract(c.payload,'$.timestamp'),c.rowid",
                        (account, message['thread_id'], scope['enabled_after'])).fetchall()
                candidates = [(r['id'], json.loads(r['payload']), r['job_state']) for r in stream]
                candidates = [(i,m,st) for i,m,st in candidates
                              if sender_key(m)==sender_key(message) and self.accepts(m)]
                from hub.intake_quiet import settled_batch
                selected = settled_batch(candidates, time.time(), self.engine.intake_management.seconds())
                if not selected:
                    continue
                batch = [(i,m) for i,m,_ in selected]
                with self.store.db() as db:
                    db.execute(
                        "UPDATE intake_runs SET state='waiting_details',payload=json_remove(payload,'$.request_id','$.orders','$.image_base64','$.nas_evidence','$.image_groups_verified','$.image_timeout_attempted','$.print_line_sources') WHERE account=? AND thread_id=? "
                        "AND state IN ('awaiting_evidence','evidence_ready') "
                        "AND json_extract(payload,'$.sender_key')=?",
                        (account, message['thread_id'], sender_key(message)),
                    )
                # Recover uncommitted image context when text arrives after the settle window.
                with self.store.db() as db:
                    prior = db.execute(
                        "SELECT c.id,c.payload,r.result AS source_result FROM captures c JOIN intake_sources s ON s.capture_id=c.id "
                        "JOIN intake_runs r ON r.id=s.run_id AND (r.state IN ('ignored','waiting_details') OR (r.state='review' AND (?=1 OR (?=1 AND (json_extract(r.result,'$.reason') IN ('Đã hết thời gian chờ cấu hình, chưa đủ thông tin','Đã đọc ảnh sau 30 phút; chưa xác định đủ dữ liệu đơn mới') OR EXISTS(SELECT 1 FROM agent_actions a WHERE a.run_id=r.id AND a.state='done' AND (a.tool='request_customer_clarification' OR (a.tool='escalate_to_human' AND instr(lower(json_extract(a.args,'$.reason')),'số lượng')>0) OR (a.tool='prepare_print_quote' AND json_extract(a.result,'$.state')='missing_fields')))))) AND json_extract(r.payload,'$.submitted_payload') IS NULL AND json_extract(r.payload,'$.request_id') IS NULL)) "
                        "WHERE json_extract(r.payload,'$.submitted_payload') IS NULL AND json_extract(r.payload,'$.request_id') IS NULL AND c.account=? AND c.thread_id=? AND json_extract(c.payload,'$.timestamp')>=? "
                        "AND json_extract(c.payload,'$.timestamp')<? AND date(json_extract(c.payload,'$.timestamp'),'unixepoch','+7 hours')=date(?,'unixepoch','+7 hours') ORDER BY c.rowid DESC LIMIT 12",
                        (
                            int(any(confirms_order(m['text']) for _,m in batch)),
                            int(any(re.search(r'\d+\s*(?:cái|chiếc|c|cm|mét|met|bộ|áo)\b|^\s*\d+\s*$',key(m['text'])) for _,m in batch)),
                            account,
                            message["thread_id"],
                            max(scope["enabled_after"], message["timestamp"] - 86400),
                            message["timestamp"],
                            message["timestamp"],
                        ),
                    ).fetchall()
                from hub.intake_lifecycle import reusable, explicit_addition
                with self.store.db() as db:
                    prior = [r for r in prior if reusable(db, r)]
                # A new addition uses its fresh quantity; old design remains available
                # through explicit quote/history, never promoted into the new batch.
                if explicit_addition([m for _, m in batch]):
                    prior = []
                context = [(r["id"], json.loads(r["payload"])) for r in prior]
                context = [
                    (i, m)
                    for i, m in context
                    if sender_key(m) == sender_key(message) and self.accepts(m)
                ]
                batch = sorted(
                    context + batch, key=lambda item: (item[1]["timestamp"], item[1]["message_id"])
                )
                mapping = self.store.thread(account=account, thread_id=message["thread_id"])
                if not mapping:
                    continue
                run_id = event_key("order-intake-v1", *[i for i, _ in batch])
                run = dict(
                    id=run_id,
                    account=account,
                    thread_id=message["thread_id"],
                    conversation=mapping["conversation"],
                )
                payload = {
                    "messages": [m["message_id"] for _, m in batch],
                    "group_name": message["display_name"],
                    "sender": message["sender"],
                    "sender_key": sender_key(message),
                    "first_timestamp": min(m['timestamp'] for _, m in batch),
                    "last_timestamp": max(m['timestamp'] for _, m in batch),
                }
                with self.store.db() as db:
                    db.execute("BEGIN IMMEDIATE")
                    db.execute(
                        "INSERT INTO intake_runs(id,account,thread_id,conversation,state,payload,created) "
                        "VALUES(?,?,?,?,'analyzing',?,?)",
                        (
                            run_id,
                            account,
                            message["thread_id"],
                            mapping["conversation"],
                            json.dumps(payload, ensure_ascii=False),
                            time.time(),
                        ),
                    )
                    db.executemany(
                        "DELETE FROM intake_sources WHERE capture_id=? AND run_id IN "
                        "(SELECT id FROM intake_runs WHERE state IN ('ignored','waiting_details') OR (state='review' AND json_extract(payload,'$.submitted_payload') IS NULL AND json_extract(payload,'$.request_id') IS NULL))",
                        [(i,) for i, _ in context],
                    )
                    db.executemany("INSERT INTO intake_sources VALUES(?,?)", [(i, run_id) for i, _ in batch])
                    db.execute("UPDATE intake_runs SET state='superseded' WHERE state IN ('waiting_details','review') "
                               "AND id NOT IN (SELECT run_id FROM intake_sources)")
                try:
                    self.analyze(run, payload, batch)
                except Exception as exc:
                    self.state(run_id, "review", {"reason": type(exc).__name__})
                    reason = "Lỗi phân tích/kiểm tra dữ liệu"
                    if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code in (409, 422):
                        reason = (
                            "Tên nhóm chưa khớp duy nhất khách ERP; API yêu cầu dạng Tên khách - phần còn lại"
                        )
                    elif isinstance(exc, ValueError):
                        reason = str(exc)
                    reason = describe(reason, "Tiếp nhận đơn ERP")
                    self.notify(
                        run,
                        "CẦN NHÂN VIÊN: Chưa lên đơn tự động. " + reason + ". Mã đối chiếu " + run_id[:12],
                    )
                return True
        return False

    def quiet_now(self, run, payload):
        latest = float(payload.get('last_timestamp', payload.get('first_timestamp', run.get('created',0))))
        with self.store.db() as db:
            rows = db.execute("SELECT payload FROM captures WHERE account=? AND thread_id=? AND json_extract(payload,'$.timestamp')>?",
                              (run['account'],run['thread_id'],latest)).fetchall()
        for row in rows:
            message=json.loads(row[0])
            if sender_key(message)==payload['sender_key'] and self.accepts(message):
                # A new source has not yet been incorporated, even if its timer expired.
                return False
        return time.time() >= latest + self.engine.intake_management.seconds()

    def image_timeout_review(self, run, payload):
        # Claim once before calling Gemini; restarts recover analyzing to review.
        if payload.get('image_timeout_attempted'):
            return False
        with self.store.db() as db:
            batch = []
            for mid in payload['messages']:
                row = db.execute('SELECT id,payload FROM captures WHERE account=? AND thread_id=? AND message_id=? ORDER BY revision DESC LIMIT 1',
                                 (run['account'], run['thread_id'], mid)).fetchone()
                if not row:
                    return False
                m = json.loads(row['payload'])
                if m.get('revision') or m.get('recalled') or not self.accepts(m):
                    return False
                batch.append((row['id'], m))
            if not any(m.get('images') for _, m in batch):
                return False
            payload['image_timeout_attempted'] = True
            claimed = db.execute("UPDATE intake_runs SET state='analyzing',payload=? WHERE id=? AND state='waiting_details'",
                                 (json.dumps(payload, ensure_ascii=False), run['id'])).rowcount
        if not claimed:
            return True
        try:
            self.analyze(run, payload, batch, image_timeout=True)
            with self.store.db() as db:
                state = db.execute('SELECT state FROM intake_runs WHERE id=?', (run['id'],)).fetchone()[0]
            if state in ('waiting_details','awaiting_evidence','evidence_ready','created','duplicate','ignored','superseded','uncertain','sending'):
                return True
        except Exception:
            pass  # Do not log credentials or image data.
        self.state(run['id'], 'review', {'reason': 'Đã đọc ảnh sau 30 phút; chưa xác định đủ dữ liệu đơn mới'})
        self.notify(run, 'CẦN NHÂN VIÊN: Đã kiểm tra ảnh sau 30 phút nhưng số lượng/đơn mới chưa rõ, ảnh không đọc được hoặc dữ liệu mâu thuẫn.')
        return True

    def analyze(self, run, payload, batch, *, image_timeout=False, agent_decision=None):
        if not self.quiet_now(run, payload):
            self.state(run['id'], 'waiting_details', {'reason':'Chờ đủ thời gian cấu hình từ tin cuối của đợt khách gửi'})
            return
        messages = [m for _, m in batch]
        from hub.intake_lifecycle import reusable
        with self.store.db() as db:
            consumed = any(not reusable(db, {'payload': json.dumps(m), 'source_result': '{}'}) for m in messages)
        if consumed:
            self.state(run['id'], 'review', {'reason': 'Nguồn tin đã ghi ERP hoặc đang gửi/chưa rõ kết quả; đối soát trước, không tạo lại'})
            return
        # Reconcile delayed Desktop quote references before any order/context gate.
        from hub.quote_recovery import recover_quotes
        recover_quotes(self.store, messages)
        from hub.psd_samples import collect as collect_psd_sample
        if agent_decision is None and collect_psd_sample(self, run, messages):
            return
        from hub.intake_preflight import route
        if agent_decision is None and route(self, run, messages):
            return
        from hub.intake_models import split, forward_placement
        from hub.order_groups import image_groups
        if agent_decision is None and split(self, run, payload, batch, image_groups(messages)):
            return
        if forward_placement(self, run, messages):
            return
        if self.additions.handle(run,messages):
            return
        if agent_decision is None:
            self.design_briefs.collect(run, messages)
        from hub.print_approval import is_reprint
        if any(is_reprint(m['text']) for m in messages):
            self.state(run['id'], 'review', {'reason':'In bù: xử lý bằng hồ sơ chuyển nhóm sản xuất, không tạo đơn mới'})
            self.notify(run, 'YÊU CẦU IN BÙ: đã tách khỏi luồng tạo đơn mới; theo dõi hồ sơ chuyển nhóm sản xuất. Nếu thiếu ảnh, cần nhân viên bổ sung.')
            return
        for m in messages:
            quote = m.get('quoted_image')
            if quote and (not quote['resolved'] or not m['images']):
                raise ValueError('Quoted image unavailable; staff must verify original')
        from hub.order_groups import image_groups, validate_group_quantity
        groups = image_groups(messages)
        if len(groups) > 1 and agent_decision is None:
            from hub.models import IntakeDecision
            from hub.agent_loop import verify_action
            orders, source_ids = [], []
            line_sources = []
            if len(groups) > 4 or len(messages) > 12:
                raise ValueError('Too many image groups; needs review')
            for group_number, group in enumerate(groups, 1):
                group_messages = [m for _, m in group]
                group_images = [i for m in group_messages for i in self.store.images(m.get('images', []))]
                if len(group_images) > 2:
                    raise ValueError('Image group has more than two images; needs review')
                context = {
                    'order_intake_only': True,
                    'image_group_only': True,
                    'messages': [{'id': n, 'text': m['text'], 'assets': m.get('assets', []),
                                  'image_count': len(m.get('images', []))} for n, m in group],
                    'latest_message_id': group[-1][0],
                    'latest_message': group[-1][1]['text'],
                    'image_message_ids': [n for n, m in group if m.get('images')],
                    'images': group_images,
                    'already_ordered_message_ids': [],
                }
                part = self.engine.agent.decide(context)
                expected_ids = {n for n, _ in group}
                if part.action != 'draft_order' or not part.orders or set(part.source_message_ids) != expected_ids:
                    raise ValueError('Image group is incomplete or ambiguous; needs review')
                validate_group_quantity(part.orders, group_messages)
                check_context = self.context_gate.build(run, group_messages)
                check_context['verification_images'] = group_images
                verify_action(self.engine.settings, check_context, 'propose_order_draft',
                              {'items': [o.model_dump(mode='json') for o in part.orders],
                               'source_message_ids': [m['message_id'] for m in group_messages]})
                # Only a single line within an independently verified image cluster
                # provides an unambiguous per-order source. Never guess within a cluster.
                line_sources.extend([[m['message_id'] for m in group_messages] if len(part.orders)==1 else [] for _ in part.orders])
                orders.extend(part.orders)
                source_ids.extend(part.source_message_ids)
            agent_decision = IntakeDecision(action='draft_order', orders=orders, source_message_ids=source_ids)
            payload['image_groups'] = [[m['message_id'] for _, m in group] for group in groups]
            payload['image_groups_verified'] = True
            payload['print_line_sources'] = line_sources
        text = "\n".join(m["text"] for m in messages)
        # Image-only orders wait for supplements before invoking the agent.
        # A timeout or a verified proposal resumes the same durable run.
        if (agent_decision is None and not image_timeout
                and any(m.get('images') or m.get('assets') for m in messages)
                and not re.search(r'\d', text)
                and time.time() < max(m['timestamp'] for m in messages) + self.engine.intake_management.seconds()):
            self.state(run['id'], 'waiting_details', {'reason': 'Chờ theo thời gian cấu hình để bổ sung số lượng; sau đó đọc ảnh tự động'})
            return
        agent_scope = self.agent_loop.scope(run)
        if agent_decision is None and agent_scope and max(m["timestamp"] for m in messages) >= agent_scope.get("enabled_after", float("inf")):
            if self.agent_loop.run(run, messages):
                return
        if not re.search(r"\d|đặt|đơn|in\b|mẫu|làm|lấy|order", key(text)) and not any(
            m["images"] for m in messages
        ):
            self.state(run["id"], "ignored")
            return
        # A visual proposal may carry quantity entirely in the image. The legacy
        # caption marker is not missing media; independent verification below
        # remains mandatory before this exception can reach ERP.
        image_proposal = bool(agent_decision and agent_decision.action == 'draft_order' and agent_decision.orders)
        caption_images = [m for m in messages if image_only_caption_pending(m, text, image_proposal=image_proposal)]
        if len(messages) > 12 or any(
            (m["attachments"] and m not in caption_images)
            or any(a["state"] != "ready" for a in m.get("assets", [])) for m in messages
        ):
            raise ValueError("Incomplete media or oversized message batch")
        if caption_images:
            if agent_decision is None or agent_decision.action != 'draft_order' or not agent_decision.orders:
                raise ValueError('Image quantities require an independently verified order proposal')
            from hub.agent_loop import verify_action
            verification = self.context_gate.build(run, messages)
            verification['verification_images'] = self.store.images(
                [image_id for m in messages for image_id in m.get('images', [])])
            verify_action(self.engine.settings, verification, 'propose_order_draft',
                          {'items': [o.model_dump(mode='json') for o in agent_decision.orders],
                           'source_message_ids': [m['message_id'] for m in messages]})
            payload['image_quantity_verified'] = True
        with self.store.db() as db:
            previous = db.execute(
                "SELECT 1 FROM intake_runs WHERE account=? AND thread_id=? AND id<>? "
                "AND state NOT IN ('ignored','review','cancelled','waiting_details','superseded') AND created>? "
                "AND (? IS NULL OR COALESCE(json_extract(payload,'$.model_parent'),'')<>?) "
                "AND json_extract(payload,'$.sender_key')=? AND date(created,'unixepoch','+7 hours')=date(?,'unixepoch','+7 hours')",
                (run["account"], run["thread_id"], run["id"], time.time() - self.engine.intake_management.seconds(), payload.get('model_parent'), payload.get('model_parent'), payload["sender_key"], max(m["timestamp"] for m in messages)),
            ).fetchone()
        if previous:
            raise ValueError("Possible continuation or correction of an earlier order")
        images = []
        image_ids = []
        for n, m in enumerate(messages, 1):
            if m["images"]:
                images.extend(self.store.images(m["images"]))
                image_ids.append(n)
        if any(sum(len(m.get('images', [])) for _, m in group) > 2 for group in groups):
            raise ValueError("Image group has more than two images; needs review")
        for group_number, group in enumerate(groups if not payload.get('image_groups_verified') else [], 1):
            scoped_run = {**run, 'id': run['id'] + ':group:' + str(group_number)} if len(groups) > 1 else run
            if not self.context_gate.check(scoped_run, [m for _, m in group]):
                if len(groups) > 1:
                    self.state(run['id'], 'review', {'reason': 'Image group context needs review'})
                return
        decision = agent_decision or self.engine.agent.decide(
            {
                "order_intake_only": True,
                "image_quantity_after_wait": image_timeout,
                "messages": [
                    {"id": n, "text": m["text"], "assets": m.get("assets", []),
                     "quoted_image": m.get("quoted_image")}
                    for n, m in enumerate(messages, 1)
                ],
                "latest_message_id": len(messages),
                "latest_message": messages[-1]["text"],
                "image_message_ids": image_ids,
                "images": images,
                "already_ordered_message_ids": [],
            }
        )
        if decision.action == "reply":
            self.state(run["id"], "waiting_details" if images else "ignored")
            return
        if decision.action != "draft_order" or not decision.orders:
            self.state(run["id"], "waiting_details", {"reason": decision.reason})
            return
        ids = set(decision.source_message_ids)
        if not ids or not ids <= set(range(1, len(messages) + 1)) or len(messages) not in ids:
            raise ValueError("Invalid order source IDs")
        from hub.meter_product import apply_meter_lines
        meter_mapped = apply_meter_lines(decision.orders, [messages[i-1] for i in sorted(ids)])
        from hub.meter_product import apply_an_nguyen_sheets
        meter_mapped |= apply_an_nguyen_sheets(decision.orders, [messages[i-1] for i in sorted(ids)], run['thread_id'])
        from hub.mask_product import apply_mask_product
        mask_mapped = apply_mask_product(decision.orders)
        # Owner-approved semantic mapping: verified mask order line -> MATNA.
        for line in decision.orders:
            if line.ma_san_pham and id(line) not in mask_mapped and not (id(line) in meter_mapped and line.ma_san_pham == "MET") and not re.search(
                r"(?<!\w)" + re.escape(key(line.ma_san_pham)) + r"(?!\w)", key(text)
            ):
                raise ValueError("Product code is not present in source text")
            if re.search(r"\.(pdf|zip|png|jpg|ai|cdr|psd)\b", key(line.ma_san_pham)):
                raise ValueError("Design filename cannot be a product code")
            numbers = {
                Decimal(n.replace(",", ".")) for n in re.findall(r"(?<![\w.])\d+(?:[.,]\d+)?(?!\w)", text)
            }
            explicit_pieces = piece_quantities(text)
            numbers.update(explicit_pieces)
            if (explicit_pieces and line.so_luong not in explicit_pieces) or (
                not images and line.so_luong not in numbers
            ):
                raise ValueError("Số lượng không xuất hiện trong tin nguồn; cần nhân viên kiểm tra")
        if any(not self.accepts(m) for m in messages):
            raise ValueError("Group policy changed during analysis")
        binding = self.resolve_customer_binding(run, payload["group_name"])
        if binding:
            payload["customer_binding"] = binding
        orders = [line.model_dump(mode="json") for line in decision.orders]
        for line in orders:
            line["ghi_chu_mau_do"] = clean_order_note(line["ghi_chu_mau_do"])
        payload["orders"] = orders
        from hub.drive_order_brief import collect_drive_order
        try:
            collect_drive_order(self.engine, run, payload, messages)
        except Exception:
            self.engine.note(run['id']+':drive-design-review',run['conversation'],
                'CẦN KIỂM TRA FILE DRIVE: hồ sơ thiết kế chưa nối được; đơn ERP vẫn xử lý riêng.',apply_capture=True)

        payload["request_id"] = ("chatwoot-id:" if binding else "chatwoot-intake:") + run["id"]
        with self.store.db() as db:
            db.execute(
                "UPDATE intake_runs SET state='awaiting_evidence',payload=? WHERE id=?",
                (json.dumps(payload, ensure_ascii=False), run["id"]),
            )

    def resolve_customer_binding(self, run, group_name):
        """Keep explicit group IDs; unmatched names use the owner-approved retail ID.

        Authentication, outages and removed mapped customers must never silently
        turn into retail orders. Legacy successful Zalo resolution stays intact.
        """
        mappings = self.engine.customer_mappings
        binding = mappings.get(run["account"], run["thread_id"])
        if binding:
            self.engine.erp.validate_customer_id(binding["customer_id"])
            return binding
        try:
            self.engine.erp.observe_group(group_name)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code not in (409, 422):
                raise
        else:
            return None
        retail_id = "aa6e7f8c-67d2-4fe8-85c2-c8c60a604a99"
        customer = self.engine.erp.validate_customer_id(retail_id)
        if customer.get("name", "").strip().upper() != "KHACH LE":
            raise ValueError("Khách lẻ cấu hình không đúng; cần kiểm tra")
        binding = mappings.set(run["account"], run["thread_id"], retail_id,
                               customer["name"], expected_version=0)
        self.engine.note(run["id"] + ":retail-binding", run["conversation"],
                         "Ánh xạ nhóm vào KHACH LE: chưa có liên kết ID khách và tên nhóm không khớp duy nhất khách ERP. Nhân viên có thể đổi ánh xạ nếu xác định được khách.",
                         apply_capture=True)
        return binding

    def evidence_request(self, account):
        with self.store.db() as db:
            row = db.execute(
                "SELECT * FROM intake_runs WHERE account=? AND state='awaiting_evidence' "
                "ORDER BY created LIMIT 1",
                (account,),
            ).fetchone()
            if not row:
                return None
            payload = json.loads(row["payload"])
            messages = select_sources(db, account, row["thread_id"], payload["messages"])
        if payload.get('addition_fallback'):
            from hub.order_additions import fallback_sources
            messages=fallback_sources(messages)
        return {"id": row["id"], "messages": messages, "reference": "INTAKE-" + row["id"][:16]}

    def evidence_saved(self, account, identity, data):
        if data.get("error"):
            with self.store.db() as db:
                row = db.execute(
                    "SELECT * FROM intake_runs WHERE id=? AND account=? AND state='awaiting_evidence'",
                    (identity, account),
                ).fetchone()
            if not row:
                raise ValueError("No pending evidence")
            self.state(identity, "review", {"reason": "NAS evidence failed"})
            self.notify(
                dict(row), "CẦN NHÂN VIÊN: Chưa tạo đơn vì không lưu được bằng chứng NAS hoặc PNG quá dài."
            )
            return
        image = decode_image({"mime_type": "image/png", "data": data["image_base64"]})
        if len(image) > 5_000_000 or not image.startswith(b"\x89PNG\r\n\x1a\n"):
            raise ValueError("Invalid evidence PNG")
        with self.store.db() as db:
            row = db.execute(
                "SELECT * FROM intake_runs WHERE id=? AND account=?", (identity, account)
            ).fetchone()
            if not row or row["state"] not in {"awaiting_evidence", "evidence_ready"}:
                raise ValueError("Evidence is not pending")
            payload = json.loads(row["payload"])
            if set(data["source_message_ids"]) != set(payload["messages"]):
                raise ValueError("Evidence source mismatch")
            archive = self.engine.settings.inboxes[account].get("archive_root", "").rstrip("\\/")
            if (
                not archive
                or not data["directory"].startswith(archive + "\\")
                or ".." in data["directory"].split("\\")
            ):
                raise ValueError("Evidence must be saved under the configured NAS root")
            payload["image_base64"] = base64.b64encode(image).decode()
            payload["nas_evidence"] = data["directory"]
            db.execute(
                "UPDATE intake_runs SET state='evidence_ready',payload=? WHERE id=?",
                (json.dumps(payload, ensure_ascii=False), identity),
            )

    def submit(self, run):
        if not self.engine.intake_management.enabled(run["account"]):return
        # Re-read durable state: stale workers must never replay a completed/uncertain order.
        with self.store.db() as db:
            current = db.execute("SELECT * FROM intake_runs WHERE id=?", (run["id"],)).fetchone()
        if not current or current["state"] != "evidence_ready":
            return
        run = dict(current)
        policy = self.policy(run["account"])
        if policy is None:
            # Reader heartbeat expired: wait for a fresh policy, retaining evidence/idempotency.
            return
        payload = json.loads(run["payload"])
        if time.time() < payload.get('last_timestamp',run.get('created',0)) + self.engine.intake_management.seconds():
            return
        try:
            with self.store.db() as db:
                messages = select_sources(db, run["account"], run["thread_id"], payload["messages"])
                newer = db.execute(
                    "SELECT payload FROM captures WHERE account=? AND thread_id=? "
                    "AND json_extract(payload,'$.timestamp')>?",
                    (run['account'], run['thread_id'], max(max(m['timestamp'] for m in messages), payload.get('last_timestamp', 0))),
                ).fetchall()
            if any(sender_key(json.loads(r[0])) == payload['sender_key'] and self.accepts(json.loads(r[0])) for r in newer):
                # No ERP write started: discard only derived draft/evidence, keep raw source IDs.
                for field in ('request_id','orders','image_base64','nas_evidence','image_groups_verified','image_timeout_attempted','image_quantity_verified','print_line_sources'):
                    payload.pop(field,None)
                with self.store.db() as db:
                    db.execute("UPDATE intake_runs SET state='waiting_details',payload=?,result=? WHERE id=? AND state='evidence_ready' AND json_extract(payload,'$.submitted_payload') IS NULL",
                               (json.dumps(payload,ensure_ascii=False),json.dumps({'reason':'Tin mới đến trước lúc ghi ERP; gom lại và tính lại thời gian chờ'}),run['id']))
                return
            if not self.engine.settings.erp_write or not allowed(policy, self.engine.settings.inboxes[run["account"]]["channel"], payload["group_name"]) or any(not self.accepts(m) for m in messages):
                raise ValueError("ERP disabled or policy changed")
            from hub.order_groups import image_groups
            groups = image_groups(messages)
            for number, group in enumerate(groups if not (payload.get('image_groups_verified') or payload.get('addition_fallback')) else [], 1):
                scoped_run = {**run, 'id': run['id'] + ':group:' + str(number)} if len(groups) > 1 else run
                if not self.context_gate.check(scoped_run, [m for _, m in group]):
                    self.state(run['id'], 'review', {'reason': 'Image group context needs review'})
                    return
            self.engine.erp.require_print_position_support(payload)
            binding = self.engine.customer_mappings.get(run["account"], run["thread_id"])
            if binding != payload.get("customer_binding"):
                raise ValueError("Ánh xạ khách đã thay đổi; cần nhân viên đối chiếu đề xuất cũ")
            if binding:
                self.engine.erp.validate_customer_id(binding["customer_id"])
            else:
                self.engine.erp.observe_group(payload["group_name"])
        except Exception as exc:
            self.state(run["id"], "review", {"reason": type(exc).__name__})
            self.notify(
                run, "CẦN NHÂN VIÊN: Đơn đã phân tích nhưng chưa ghi ERP; kiểm tra cấu hình/khách hàng."
            )
            return
        body = {k: payload[k] for k in ("request_id", "group_name", "orders", "image_base64")}
        body["source"] = self.engine.settings.inboxes[run["account"]]["channel"]
        if binding:
            body.update(
                customer_id=binding["customer_id"], group_id=run["thread_id"], source_account=run["account"]
            )
        for line in body["orders"]:
            line["ghi_chu_mau_do"] = clean_order_note(line["ghi_chu_mau_do"])
        if not self.quiet_now(run, payload):
            return  # Next poll incorporates new sources before any ERP write.
        # Freeze the exact external request for reconciliation before any network write.
        payload["submitted_payload"] = body
        with self.store.db() as db:
            claimed = db.execute(
                "UPDATE intake_runs SET state='sending',payload=? WHERE id=? AND state='evidence_ready'",
                (json.dumps(payload, ensure_ascii=False), run["id"]),
            )
            if claimed.rowcount != 1:
                return
        try:
            result = self.engine.erp.create_order(body)
        except Exception as exc:
            self.state(run["id"], "uncertain", {"reason": type(exc).__name__})
            self.notify(
                run,
                "CẦN NHÂN VIÊN: ERP chưa xác nhận kết quả; không tự gửi lại để tránh trùng đơn. "
                + run["id"][:12],
            )
            return
        self.state(run["id"], "created", result)
        if payload.get('addition_fallback'):
            text=('ĐẶT THÊM — ĐÃ TẠO ĐƠN RIÊNG: '+', '.join(o.get('ma_don_hang',o.get('id','')) for o in result['orders'])+
                '\nSố lượng bổ sung: '+payload['addition_fallback']['delta']+' cái. Không tăng đơn cũ. Đối chiếu mẫu/ảnh nguồn trước khi in.')
            with self.store.db() as db:
                event=db.execute('SELECT id FROM order_additions WHERE account=? AND thread_id=? AND source_message_id=?',
                    (run['account'],run['thread_id'],payload['addition_fallback']['source_message_id'])).fetchone()
                db.execute("UPDATE order_additions SET state='new_created',result=?,payload=? WHERE id=?",
                    (json.dumps(result),json.dumps({'local_notice':{'run':dict(run),'messages':messages,'text':text}},ensure_ascii=False),event['id']))
            self.additions.notice(run,messages,event['id'],text)
        codes = ", ".join(str(o.get("ma_don_hang", o.get("id", ""))) for o in result["orders"])
        self.engine.note(
            run["id"] + ":created",
            run["conversation"],
            "Đã tạo đơn ERP trạng thái Lên mẫu: " + codes + "\nBằng chứng NAS: " + payload["nas_evidence"],
            apply_capture=True,
        )

