from hub.ai_usage import tracked_run
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
    values = re.findall(r"(?<![\w.])(\d{1,3}(?:\.\d{3})+|\d+(?:[.,]\d+)?)\s*(?:c\b|cái\b|chiếc\b|áo\b|nón\b|tấm\b|bộ\b|pet\b)", text, re.I)
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
        if row:
            return json.loads(row["payload"])
        return self.engine.settings.inboxes.get(account, {}).get("capture_policy")

    def scope(self, account):
        return self.engine.settings.inboxes.get(account, {}).get("order_intake", {})

    def accepts(self, message):
        from hub.quality_monitor import monitored
        if monitored(message["account"],message["thread_id"]):return False
        cfg = self.engine.settings.inboxes.get(message["account"], {})
        from hub.unified_intake import new_message, context_eligible
        unified=new_message(message)
        if not unified and cfg.get('production_slips',{}).get('auto_order'):
            with self.store.db() as db:
                reserved=db.execute("SELECT 1 FROM production_slips WHERE account=? AND thread_id=? AND message_id=? AND state IN ('classifying','review','copy_pending','copied')",(message['account'],message['thread_id'],message['message_id'])).fetchone()
            if reserved:return False
        policy = self.policy(message["account"])
        scope = self.scope(message["account"])
        agent_scope=self.agent_loop.scope(message)
        if agent_scope and policy is not None:
            channel=cfg.get('channel')
            if not allowed({**policy,channel+'_disable_reply_groups':[]},channel,message['display_name'],'receive_messages'):return False
            policy=dict(policy)
            policy[channel+'_default_auto_order']=True
            policy[channel+'_contact_rules']=[{**r,'auto_order':True} for r in policy.get(channel+'_contact_rules',[])]
        if unified and policy is not None:
            return bool(scope.get("enabled_after") and message["timestamp"]>=scope["enabled_after"] and context_eligible(policy,cfg.get("channel"),message))
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
            from hub.intake_text_conversation import chat_display_state
            with self.store.db() as db:
                row=db.execute('SELECT * FROM intake_runs WHERE id=?',(identity,)).fetchone()
                proposals=db.execute('SELECT 1 FROM agent_proposals WHERE run_id=? LIMIT 1',(identity,)).fetchone()
                if row and row['state'] not in ('sending','uncertain','created','duplicate') and not proposals:
                    p=json.loads(row['payload']);ev_msgs=evidence(db,row,p);category,why=classify(ev_msgs,p,result)
                    if category in HISTORY:
                        state='ignored';result={**(result or {}),'intent':category,'reason':why,'erp_committed':False}
                        if 'display_state' not in result and ev_msgs:
                            result['display_state']=chat_display_state(ev_msgs)
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
        from hub.intake_operator_retry import poll as poll_operator_retry
        if poll_operator_retry(self):return True
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
                    "AND json_extract(c.payload,'$.timestamp')>=? AND json_extract(c.payload,'$.timestamp')<=?",
                    (expired['account'], expired['thread_id'], pending_payload.get('last_timestamp', expired['created']), deadline),
                ).fetchall()
            if self.quiet_now(dict(expired), pending_payload) and not any(self.accepts(json.loads(r[0])) for r in supplements):
                if self.image_timeout_review(dict(expired), pending_payload):
                    return True
                self.state(expired['id'], 'review', {'reason': 'Đã hết thời gian chờ cấu hình, chưa đủ thông tin'})
                self.notify(dict(expired), 'CẦN NHÂN VIÊN: Yêu cầu đã hết thời gian chờ cấu hình nhưng chưa đủ thông tin để lên đơn.')
                return True
        with self.store.db() as db:
            waiting = db.execute(
                "SELECT * FROM intake_runs WHERE state='evidence_ready' ORDER BY created"
            ).fetchall()
        for x in waiting:
            if not self.engine.intake_management.enabled(x['account']):
                continue
            row = dict(x)
            if self.policy(row['account']) is None or not self.quiet_now(row, json.loads(row['payload'])):
                continue
            self.submit(row)
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
                stream_key = message['thread_id']
                if stream_key in checked_streams:
                    continue
                checked_streams.add(stream_key)
                # Load the complete customer group stream, not only the first 200 global rows.
                with self.store.db() as db:
                    stream = db.execute(
                        "SELECT c.rowid AS sequence,c.id,c.payload,j.created AS received,j.state AS job_state,s.run_id AS source_run FROM captures c "
                        "LEFT JOIN jobs j ON j.id=c.id LEFT JOIN intake_sources s ON s.capture_id=c.id "
                        "WHERE c.account=? AND c.thread_id=? "
                        "AND json_extract(c.payload,'$.timestamp')>=? ORDER BY json_extract(c.payload,'$.timestamp'),c.rowid",
                        (account, message['thread_id'], scope['enabled_after'])).fetchall()
                from hub.intake_quiet import human_activity
                candidates = []
                from hub.late_capture_batch import window,recoverable
                wait=self.engine.intake_management.seconds()
                members=window(stream,identity,wait)
                member_ids={r['id'] for r,m in members}
                with self.store.db() as db:
                    reclaim={rid for rid in {r['source_run'] for r,m in members} if rid and recoverable(db,rid,member_ids)}
                for r,m in members:
                    if (r['source_run'] is None or r['source_run'] in reclaim) and self.accepts(m):
                        candidates.append((r['id'], m, r['job_state']))
                    elif human_activity(m) and not self.accepts(m):
                        candidates.append((None, m, 'done'))
                from hub.intake_quiet import settled_batch
                from hub.intake_run_now import ticket as run_now_ticket
                manual_ticket=run_now_ticket(self.store,account,message['thread_id'],candidates,self.engine.intake_management.seconds())
                sync_settle = min(wait, 120)
                selected = settled_batch(candidates, time.time(), self.engine.intake_management.seconds(),force=bool(manual_ticket))
                if not manual_ticket and any(time.time()<float(r['received'] or m['timestamp'])+sync_settle for r,m in members):
                    continue
                if not selected:
                    continue
                batch = [(i,m) for i,m,_ in selected if i is not None]
                # Each settled batch owns only its new sources. Never pull sources
                # from prior ignored/review/waiting runs or invalidate their evidence.
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
                    "collection_scope": "group",
                    "unified_intake": all(__import__("hub.unified_intake",fromlist=["new_message"]).new_message(m) for _,m in batch),
                    "first_timestamp": min(m['timestamp'] for _, m in batch),
                    "last_timestamp": max(m['timestamp'] for _, m in batch),
                }
                with self.store.db() as db:
                    db.execute("BEGIN IMMEDIATE")
                    latest=db.execute('SELECT max(rowid) FROM captures WHERE account=? AND thread_id=?',(account,message['thread_id'])).fetchone()[0]
                    if latest!=max(r['sequence'] for r in stream) or any(not recoverable(db,rid,member_ids) for rid in reclaim):
                        continue
                    owners=db.execute("SELECT DISTINCT run_id FROM intake_sources WHERE capture_id IN (SELECT value FROM json_each(?))",(json.dumps([cid for cid,_ in batch]),)).fetchall()
                    if any(r[0] not in reclaim for r in owners):
                        continue
                    if manual_ticket:
                        claimed=db.execute("UPDATE intake_run_now SET state='consumed',run_id=? WHERE id=? AND state='queued'",(run_id,manual_ticket)).rowcount
                        if not claimed:continue
                        payload['manual_quiet_until']=max(m['timestamp'] for _,m,_ in selected)
                        payload['manual_run_request']=manual_ticket
                    for rid in reclaim:
                        db.execute("UPDATE intake_runs SET state='superseded',result=? WHERE id=?",(json.dumps({'merged_into':run_id,'reason':'Nguồn đến muộn trong cùng đợt, đã gom để phân tích chung'}),rid))
                        db.execute('DELETE FROM intake_sources WHERE run_id=?',(rid,))
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
                    db.executemany("INSERT INTO intake_sources VALUES(?,?)", [(i, run_id) for i, _ in batch])
                try:
                    self.analyze(run, payload, batch)
                except Exception as exc:
                    self.state(run_id, "review", {"reason": __import__("hub.intake_errors",fromlist=["detail"]).detail(exc)})
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
        # A verified single-slip task is independent of later unrelated group traffic.
        if payload.get('proposal_parent') and payload.get('verified_proposal_id'):
            from hub.agent_order_tasks import saved_proposal
            with self.store.db() as db:
                parent=db.execute('SELECT account,thread_id,payload FROM intake_runs WHERE id=?',(payload['proposal_parent'],)).fetchone()
                draft=saved_proposal(db,payload['proposal_parent'],payload['verified_proposal_id'])
            if (parent and parent['account']==run['account'] and parent['thread_id']==run['thread_id']
                    and json.loads(parent['payload']).get('individual_slip') and draft
                    and set(draft['source_message_ids'])==set(payload.get('messages',[]))):
                return True
        latest = float(payload.get('last_timestamp', payload.get('first_timestamp', run.get('created',0))))
        with self.store.db() as db:
            rows = db.execute("SELECT payload FROM captures WHERE account=? AND thread_id=? AND json_extract(payload,'$.timestamp')>?",
                              (run['account'],run['thread_id'],latest)).fetchall()
        from hub.intake_quiet import human_activity
        wait_seconds = self.engine.intake_management.seconds()
        activity_latest = latest
        for message in sorted((json.loads(row[0]) for row in rows), key=lambda m: float(m['timestamp'])):
            if not human_activity(message):
                continue
            # A completed quiet window closes this batch. Later conversations
            # belong to a new batch, even when they have already been captured.
            if float(message['timestamp']) > activity_latest + wait_seconds:
                break
            if human_activity(message):
                activity_latest = max(activity_latest, float(message['timestamp']))
            if self.accepts(message):
                # After evidence is ready, later messages already reviewed in their own batch
                # no longer count as uncollected. Keep the quiet timer and quantity checks.
                if run.get('state') == 'evidence_ready' and payload.get('text_quantity_order'):
                    with self.store.db() as db:
                        separate = db.execute("SELECT 1 FROM intake_runs r, json_each(r.payload,'$.messages') m WHERE r.account=? AND r.thread_id=? AND r.id<>? AND r.state IN ('review','ignored','created','duplicate') AND m.value=? LIMIT 1", (run['account'],run['thread_id'],run['id'],message['message_id'])).fetchone()
                    if separate and not __import__('re').search(r'\d|\b(?:hủy|huỷ|đổi|thôi|khoan|dừng|giảm|tăng|chỉnh|thêm|bớt|nhầm|sai)\b', __import__('re').sub(r'\b\d+\s+ảnh\s+chụp\b', 'ảnh chụp', message.get('text','').casefold().replace('[tin zalo loại 2; xem trên ứng dụng zalo]',''))):
                        continue
                # A new source has not yet been incorporated, even if its timer expired.
                return False
        return (activity_latest <= float(payload.get('manual_quiet_until',0))
                or time.time() >= activity_latest + wait_seconds)

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
                if m.get('revision') or m.get('recalled'):
                    continue # Retired source must not veto a fresh replacement image.
                if not self.accepts(m):return False
                batch.append((row['id'], m))
            if not any(m.get('images') for _, m in batch):
                return False
            active_ids=[m['message_id'] for _,m in batch]
            payload['retired_source_message_ids']=list(dict.fromkeys(payload.get('retired_source_message_ids',[])+[mid for mid in payload['messages'] if mid not in active_ids]))
            payload['messages']=active_ids
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

    @tracked_run
    def analyze(self, run, payload, batch, *, image_timeout=False, agent_decision=None):
        if not self.quiet_now(run, payload):
            self.state(run['id'], 'waiting_details', {'reason':'Chờ đủ thời gian cấu hình từ tin cuối của đợt khách gửi'})
            return
        from hub.group_intake_rules import filter_messages, only_ignored_images
        filtered=filter_messages(self.policy(run['account']),run['account'],[m for _,m in batch])
        batch=[(pair[0],msg) for pair,msg in zip(batch,filtered)]
        messages = filtered
        file_job = None
        if agent_decision is None:
            # File dispatch remains independent from ERP quantity extraction.
            from hub.file_intake_branch import enqueue
            file_job = enqueue(self, run, messages)
            # Resolve configured staff identities before quantity or image routing.
            context = self.context_gate.build(run, messages)
            roles = {m['message_id']: m['role'] for m in context['batch']}
            messages = [dict(m, origin=roles.get(m['message_id'], m.get('origin', 'customer'))) for m in messages]
            batch = [(pair[0], m) for pair, m in zip(batch, messages)]
            active = [m for m in messages if not m.get('recalled') and not m.get('revision')]
            if active and all(m.get('origin') == 'staff' for m in active):
                self.state(run['id'], 'ignored', {'display_state':'Nhân viên gửi', 'intent':'staff_only', 'reason':'Nhân viên gửi thông tin/mẫu; chưa có phản hồi đặt hàng của khách.', 'no_action':True, 'image_read':False})
                return
            from hub.intake_text_conversation import chat_display_state, conversation_state
            conversation = conversation_state(messages)
            if conversation:
                self.state(run['id'], 'ignored', {'display_state':conversation, 'intent':'text_conversation', 'reason':'Tin chữ không có nguồn ảnh/file hoặc số lượng đặt hàng; không gọi AI.', 'no_action':True, 'image_read':False})
                return
            from hub.intake_logistics import logistics_only, norm as _approval_norm
            if logistics_only(messages):
                ds = chat_display_state(messages)
                self.state(run['id'], 'ignored', {'display_state':ds, 'intent':'logistics', 'reason':'Trao đổi giao nhận/tiến độ hàng đã in; không có yêu cầu đặt mới.', 'no_action':True, 'image_read':False})
                return
            _cust_msgs = [m for m in messages if not m.get('recalled') and not m.get('revision') and m.get('origin') == 'customer' and m.get('direction', 'incoming') == 'incoming']
            if _cust_msgs and not any(
                any(m.get(k) for k in ('images', 'assets', 'attachments', 'quoted_image', 'quoted_file'))
                or re.search(r'\d|https?://|\[anh zalo|\[file zalo', _approval_norm(m.get('text', '')))
                or re.search(r'\b(?:mot|hai|ba|bon|nam|sau|bay|tam|chin|muoi|tram|nghin|ngan|chuc)\s+(?:cai|tam|met|non|bo|chiec)\b', _approval_norm(m.get('text', '')))
                or re.search(r'\b(?:dat them|in them|lam them|in bu|bu cho|bu them|len mau|lam mau|ve mau|ve lai|sua mau|dat hang|so luong|sl|bao gia|hoi gia|chot tong|them)\b', _approval_norm(m.get('text', '')))
                for m in _cust_msgs
            ):
                _cids = [m['message_id'] for m in _cust_msgs if m.get('message_id')]
                _pa = None
                if _cids:
                    _marks = ','.join('?' for _ in _cids)
                    with self.store.db() as db:
                        if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='print_approvals'").fetchone():
                            _pa = db.execute(
                                f"SELECT id, state FROM print_approvals WHERE account=? AND thread_id=? AND confirmation_id IN ({_marks}) AND state IN ('awaiting_evidence','ready','confirmed') LIMIT 1",
                                (run['account'], run['thread_id'], *_cids),
                            ).fetchone()
                if _pa:
                    ds = chat_display_state(messages)
                    self.state(run['id'], 'ignored', {
                        'display_state': ds,
                        'intent': 'print_approval',
                        'approval_id': _pa['id'],
                        'reason': f"Khách duyệt in mẫu (đã chuyển luồng duyệt in CHOT-IN-{_pa['id'][:16]}); không có số lượng/yêu cầu đặt đơn ERP mới nên không gọi AI.",
                        'no_action': True,
                        'image_read': False,
                    })
                    return
            from hub.individual_slips import run as read_individual_slips
            if read_individual_slips(self,run,messages):return
            from hub.canavi_slip_policy import sender_id as canavi_primary_sender
            if not payload.get('individual_slip') and canavi_primary_sender(self.policy(run['account']), run):
                from hub.psd_samples import collect as collect_psd_sample
                if not file_job and collect_psd_sample(self, run, messages):
                    return
                ds = chat_display_state(messages)
                self.state(run['id'], 'ignored', {
                    'display_state': ds,
                    'intent': 'canavi_no_slip',
                    'reason': 'Nhóm CANAVI chỉ lên đơn ERP từ ảnh Phiếu Lệnh của người gửi phiếu chính; cụm này không có phiếu lệnh hợp lệ nên không gọi AI lên đơn.',
                    'no_action': True,
                    'image_read': False,
                })
                return
            from hub.text_quantity_orders import split_explicit, try_prepare
            if split_explicit(self, run, payload, messages):return
            if not payload.get('_semantic_fallback') and try_prepare(self, run, payload, messages):return
            from hub.text_quantity_policy import text_quantity
            from hub.intake_semantic_fallback import candidate
            if not payload.get('_semantic_fallback') and not text_quantity(messages) and not candidate(messages):
                ds = chat_display_state(messages)
                reason = ('Khách nhắn/hỏi; chưa có nhân viên trả lời và chưa có số lượng đặt hàng.'
                          if ds == 'Khách hỏi'
                          else 'Trao đổi giữa khách và nhân viên; chưa có số lượng đặt hàng.')
                self.state(run['id'],'ignored',{'display_state':ds,'intent':'conversation','reason':reason,'no_action':True,'image_read':False})
                return
        if only_ignored_images(messages):
            self.state(run['id'],'ignored',{'reason':'Ảnh không thuộc người gửi phiếu chính của nhóm; không gọi AI','no_action':True,'image_read':False})
            return
        # Trust only the exact proposal already verified and durably saved by Agent.
        verified_batch = False
        if agent_decision is not None and payload.get('unified_intake'):
            with self.store.db() as db:
                saved = db.execute('SELECT p.payload FROM agent_proposals p JOIN agent_runs a ON a.id=p.run_id WHERE p.run_id=? AND a.state=?', (run['id'], 'completed')).fetchall()
            if len(saved) == 1:
                from hub.agent_loop import Draft
                draft = Draft.model_validate_json(saved[0][0])
                expected_ids = [n for n, m in enumerate(messages, 1) if m['message_id'] in draft.source_message_ids]
                verified_batch = (agent_decision.orders == draft.items and sorted(agent_decision.source_message_ids) == expected_ids)
        if agent_decision is not None and payload.get('verified_proposal_id'):
            from hub.agent_order_tasks import verified_child
            with self.store.db() as db:
                verified_batch = verified_child(db,run,payload,messages,[o.model_dump(mode='json') for o in agent_decision.orders])
            if not verified_batch:raise ValueError('Đề xuất tách việc không khớp nguồn/bằng chứng đã kiểm chứng')
        from hub.intake_lifecycle import reusable
        with self.store.db() as db:
            consumed = any(not reusable(db, {'payload': json.dumps(m), 'source_result': '{}'}) for m in messages)
        if consumed:
            self.state(run['id'], 'review', {'reason': 'Nguồn tin đã ghi ERP hoặc đang gửi/chưa rõ kết quả; đối soát trước, không tạo lại'})
            return
        # Reconcile delayed Desktop quote references before unified_intake or legacy gates.
        from hub.quote_recovery import recover_quotes
        recover_quotes(self.store, messages)
        if payload.get('unified_intake') and agent_decision is None:
            context=self.context_gate.build(run,messages)
            if not any(m.get('role')=='customer' for m in context['batch']):
                self.state(run['id'],'ignored',{'reason':'Cụm chỉ có nhân viên; giữ ngữ cảnh, không tạo đơn từ lời nhân viên','no_action':True})
                return
            if not self.agent_loop.scope(run):
                self.state(run['id'],'review',{'reason':'Chưa bật Agent cho nhóm; không tạo đơn bằng nhánh phiếu riêng'})
                return
            from hub.group_original_jpg import enabled as _jpg_group_enabled
            from hub.psd_samples import sample_only as _psd_sample_only, collect as _collect_psd_sample
            from hub.text_quantity_policy import text_quantity as _has_text_qty
            if (
                _jpg_group_enabled(run['thread_id'])
                and _psd_sample_only(messages)
                and not _has_text_qty(messages)
                and not any(m.get('images') for m in messages if not m.get('recalled') and not m.get('revision') and m.get('origin') == 'customer')
                and _collect_psd_sample(self, run, messages)
            ):
                return
            self.agent_loop.run(run,messages,staff_images_checked=True)
            # Preserve independent source/file collection after AI, never a second ERP writer.
            with self.store.db() as db:
                design_actions=db.execute("SELECT args FROM agent_actions WHERE run_id=? AND tool='handoff_design_sample' AND state='done'",(run['id'],)).fetchall()
            for action in design_actions:
                ids=set(json.loads(action['args'])['source_message_ids'])
                selected=[m for m in messages if m['message_id'] in ids]
                if selected and not file_job:self.design_briefs.collect(dict(run, batch_settled=True, agent_admitted=True),selected)
            from hub.psd_samples import collect as collect_psd_sample
            if not file_job:collect_psd_sample(self,run,messages)
            return
        from hub.conversation_confirmation import apply as apply_quantity_confirmation
        if not verified_batch and apply_quantity_confirmation(self, run, messages):
            return
        from hub.intake_requests import split_requests
        if agent_decision is None and split_requests(self, run, payload, batch):
            return
        from hub.psd_samples import collect as collect_psd_sample
        if agent_decision is None and not file_job and collect_psd_sample(self, run, messages):
            return
        from hub.intake_models import split, forward_placement
        from hub.order_groups import image_groups
        if agent_decision is None and split(self, run, payload, batch, image_groups(messages)):
            return
        if forward_placement(self, run, messages):
            return
        # Verified proposals already isolate the new quantity and its exact sources.
        # Do not reinterpret them through the legacy addition shortcut.
        if agent_decision is None and self.additions.handle(run,messages):
            return
        if agent_decision is None and not file_job:
            self.design_briefs.collect(dict(run, batch_settled=True), messages)
        from hub.print_approval import is_reprint
        if any(is_reprint(m['text']) for m in messages):
            self.state(run['id'], 'review', {'reason':'In bù: xử lý bằng hồ sơ chuyển nhóm sản xuất, không tạo đơn mới'})
            self.notify(run, 'YÊU CẦU IN BÙ: đã tách khỏi luồng tạo đơn mới; theo dõi hồ sơ chuyển nhóm sản xuất. Nếu thiếu ảnh, cần nhân viên bổ sung.')
            return
        for m in messages:
            quote = m.get('quoted_image')
            if quote and (not quote['resolved'] or not m['images']):
                from hub.quote_recovery import batch_image_fallback
                if not batch_image_fallback(self.store, m, messages):
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
        if (agent_decision is None and not image_timeout and not payload.get('manual_run_request')
                and any(m.get('images') or m.get('assets') for m in messages)
                and not re.search(r'\d', text)
                and time.time() < max(m['timestamp'] for m in messages) + self.engine.intake_management.seconds()):
            self.state(run['id'], 'waiting_details', {'reason': 'Chờ theo thời gian cấu hình để bổ sung số lượng; sau đó đọc ảnh tự động'})
            return
        agent_scope = self.agent_loop.scope(run)
        if agent_decision is None and agent_scope and max(m["timestamp"] for m in messages) >= agent_scope.get("enabled_after", float("inf")):
            if self.agent_loop.run(run, messages,staff_images_checked=True):
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
        from hub.quoted_files import verified_reference_only
        if len(messages) > 12 or any(
            ((m["attachments"] and m not in caption_images)
             or any(a["state"] != "ready" for a in m.get("assets", [])))
            and not (verified_batch and verified_reference_only(m)) for m in messages
        ):
            raise ValueError("Incomplete media or oversized message batch")
        if caption_images and not verified_batch:
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
        images = []
        image_ids = []
        for n, m in enumerate(messages, 1):
            if m["images"]:
                images.extend(self.store.images(m["images"]))
                image_ids.append(n)
        if not verified_batch and any(sum(len(m.get('images', [])) for _, m in group) > 2 for group in groups):
            raise ValueError("Image group has more than two images; needs review")
        for group_number, group in enumerate(groups if not (payload.get('image_groups_verified') or verified_batch) else [], 1):
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
        if not ids or not ids <= set(range(1, len(messages) + 1)) or (len(messages) not in ids and not (payload.get("unified_intake") and agent_decision is not None)):
            raise ValueError("Invalid order source IDs")
        from hub.meter_product import apply_meter_lines
        meter_mapped = apply_meter_lines(decision.orders, [messages[i-1] for i in sorted(ids)])
        from hub.meter_product import apply_an_nguyen_sheets
        meter_mapped |= apply_an_nguyen_sheets(decision.orders, [messages[i-1] for i in sorted(ids)], run['thread_id'])
        from hub.mask_product import apply_mask_product
        mask_mapped = apply_mask_product(decision.orders)
        from hub.single_slip_policy import verified_slip, normalize_product
        with self.store.db() as db:
            verified_single_slip = verified_batch and verified_slip(db,run,payload)
        if verified_single_slip:
            for line in decision.orders:normalize_product(line)
        # Owner-approved semantic mapping: verified mask order line -> MATNA.
        from unicodedata import normalize
        _norm_vemau = lambda s: re.sub(r"[\u0300-\u036f]", "", normalize("NFKD", (s or "").replace("đ", "d").replace("Đ", "D"))).lower()
        vemau_allowed = bool(re.search(r"\b(?:(?:len|lam|in|ra|ve)(?:\s+[a-z0-9]+){0,5}\s+mau|ve\s+lai|lam\s+ro\s+net)\b", _norm_vemau(text)))
        for line in decision.orders:
            is_vemau = bool(line.ma_san_pham and vemau_allowed and line.ma_san_pham.strip().upper() == "VEMAU")
            if line.ma_san_pham and not verified_single_slip and id(line) not in mask_mapped and not (id(line) in meter_mapped and line.ma_san_pham == "MET") and not is_vemau and not re.search(
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
            if id(line) in meter_mapped or (is_vemau and line.so_luong == Decimal("2")):numbers.add(line.so_luong)
            if (explicit_pieces and id(line) not in meter_mapped and not (is_vemau and line.so_luong == Decimal("2")) and line.so_luong not in explicit_pieces) or (
                not images and line.so_luong not in numbers
            ):
                raise ValueError("Số lượng không xuất hiện trong tin nguồn; cần nhân viên kiểm tra")
        if any(not self.accepts(m) for m in messages):
            raise ValueError("Group policy changed during analysis")
        binding = self.resolve_customer_binding(run, payload["group_name"])
        if binding:
            payload["customer_binding"] = binding
        orders = [line.model_dump(mode="json") for line in decision.orders]
        if payload.get('n8n_expected'):
            from hub.n8n_erp_dispatch import validate_expected
            validate_expected(payload['n8n_expected'], orders)
        for line in orders:
            line["ghi_chu_mau_do"] = clean_order_note(line["ghi_chu_mau_do"])
        payload["orders"] = orders
        if verified_batch:
            payload["image_groups_verified"] = True
        from hub.drive_order_brief import collect_drive_order
        try:
            collect_drive_order(self.engine, run, payload, messages)
        except Exception:
            self.engine.note(run['id']+':drive-design-review',run['conversation'],
                'CẦN KIỂM TRA FILE DRIVE: hồ sơ thiết kế chưa nối được; đơn ERP vẫn xử lý riêng.',apply_capture=True)

        payload["request_id"] = ("chatwoot-id:" if binding else "chatwoot-intake:") + run["id"]
        with self.store.db() as db:
            db.execute(
                "UPDATE intake_runs SET state='awaiting_evidence',result='{}',payload=? WHERE id=?",
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
            from hub.quantity_review import sources_for_run
            messages = sources_for_run(db,row,payload)
        if payload.get('addition_fallback'):
            from hub.order_additions import fallback_sources
            messages=fallback_sources(messages)
        # Evidence sources are reloaded with encoded media; retain the original quote
        # in captures, but explicitly label the same-batch replacement in the document.
        from hub.quote_recovery import batch_image_fallback
        from types import SimpleNamespace
        encoded_media = SimpleNamespace(images=lambda images: images)
        for message in messages:
            quote = message.get('quoted_image')
            if quote and not quote.get('resolved') and batch_image_fallback(encoded_media, message, messages):
                message['unavailable_original_quote'] = quote
                message['quoted_image'] = None
                message['text'] = message.get('text', '') + "\n[Ảnh trích dẫn cũ chưa lấy được; dùng ảnh khách gửi trong cùng cụm, ID tin: " + ', '.join(message['quote_evidence_fallback']['source_message_ids']) + "]"
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
        try:
            image = base64.b64decode(data["image_base64"], validate=True)
        except Exception as exc:
            raise ValueError("Invalid evidence base64") from exc
        if not (0 < len(image) <= 5_000_000 and image.startswith(b"\x89PNG\r\n\x1a\n") and b"IEND" in image[-16:]):
            raise ValueError("Invalid evidence PNG")
        with self.store.db() as db:
            row = db.execute(
                "SELECT * FROM intake_runs WHERE id=? AND account=?", (identity, account)
            ).fetchone()
            if not row or row["state"] not in {"awaiting_evidence", "evidence_ready"}:
                raise ValueError("Evidence is not pending")
            payload = json.loads(row["payload"])
            expected = payload["messages"]
            marker = payload.get("text_quantity_order", {})
            if marker.get("operator_decisions"):
                expected = marker["evidence_ids"]
                if not expected or not set(expected).issubset(payload["messages"]):
                    raise ValueError("Invalid approved evidence selection")
            received = data["source_message_ids"]
            if len(received) != len(expected) or set(received) != set(expected):
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
        if not self.quiet_now(run, payload):
            return
        try:
            with self.store.db() as db:
                from hub.quantity_review import sources_for_run
                messages = sources_for_run(db,run,payload)
            # A later batch must not erase this settled batch's order/evidence.
            if payload.get('text_quantity_order'):
                from hub.text_quantity_orders import validate_quantity_sources
                if not validate_quantity_sources(payload['text_quantity_order'],messages):
                    raise ValueError('Customer quantity context changed before submit')
            if payload.get('quote_evidence_order'):
                from hub.quote_conversation_evidence import load, fingerprint, explicit_extra
                marker=payload['quote_evidence_order']
                with self.store.db() as db:
                    if marker.get('image_hashes'):
                        import hashlib
                        hashes=[hashlib.sha256(base64.b64decode(im['data'])).hexdigest() for m in messages for im in m.get('images',[])]
                        valid=len(messages)==1 and hashes==marker['image_hashes']
                    else:
                        valid = len(messages)==1 and load(db,messages[0]) is not None
                if not valid or marker.get('source_digest')!=fingerprint(messages[0]) or marker.get('quantity')!=explicit_extra(messages[0]):
                    raise ValueError('Quoted order evidence changed; reconcile before submit')
            from hub.conversation_confirmation import apply as apply_quantity_confirmation
            from hub.agent_order_tasks import verified_child
            with self.store.db() as db:
                independent_verified=verified_child(db,run,payload,messages,payload.get('orders',[]))
            if not independent_verified and not payload.get('quote_evidence_order') and not payload.get('text_quantity_order') and apply_quantity_confirmation(self, run, messages):
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
            if payload.get('n8n_expected'):
                from hub.n8n_erp_dispatch import validate_expected
                validate_expected(payload['n8n_expected'], payload['orders'])
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
        from hub.canavi_slip_policy import GROUPS
        from hub.single_slip_policy import verified_slip
        if binding and run["account"] == "zalo-personal-1" and run["thread_id"] in GROUPS:
            with self.store.db() as db:
                slip = verified_slip(db, run, payload)
            if slip:
                for line in body["orders"]:
                    notes = (line.get("ghi_chu_mau_do") or "").splitlines()
                    evidence = [s.partition(":")[2].strip() for s in notes
                                if s.strip().casefold().startswith("quy cách phiếu:")]
                    line["canavi_spec"] = evidence[0][:1500] if len(evidence) == 1 else ""
        # Preserve only verified customer color allocation; no full transcripts.
        from hub.color_quantity import submission_note
        marker = payload.get('text_quantity_order', {})
        batch_items = marker.get('batch_items', [])
        for index, line in enumerate(body["orders"]):
            details = batch_items[index]['details'] if batch_items else marker
            if (marker.get('batch_items') or details.get('sample_default')
                    or (payload.get('verified_proposal_id') and payload.get('image_groups_verified'))):
                # These notes were built from immutable source IDs and explicit text.
                line["ghi_chu_mau_do"] = line.get("ghi_chu_mau_do", "")
            else:
                line["ghi_chu_mau_do"] = submission_note(details,line)
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

