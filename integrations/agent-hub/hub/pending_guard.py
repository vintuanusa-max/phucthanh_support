"""Keep unattended captured conversations visible to staff, independently of AI jobs."""
import logging
import time


def reason_for(current, history, scope, owner, now):
    if current.get('status') != 'pending':
        return None
    if not scope:
        return 'Hội thoại chưa bật AI trả lời; nhân viên tiếp nhận tin khách.'
    if owner != 'ai':
        return 'AI đã chuyển quyền xử lý cho nhân viên.'
    incoming = [m for m in history if not m.get('private') and m.get('message_type') in (0, 'incoming')]
    if not incoming:
        return 'Không xác định được tin khách để AI xử lý; cần kiểm tra.'
    latest = max(incoming, key=lambda m: m['id'])
    if any(not m.get('private') and m.get('message_type') in (1, 'outgoing') and m['id'] > latest['id'] for m in history):
        return None
    try:
        expired = now - float(latest['created_at']) >= 300
    except (KeyError, ValueError, TypeError):
        expired = True
    if expired:
        return 'AI chưa trả lời tin khách sau 5 phút hoặc không xử lý được; nhân viên tiếp nhận.'
    return None


class PendingGuard:
    def __init__(self, engine):
        self.engine = engine
        self.next_check = 0
        self.cursor = 0

    def poll(self):
        e = self.engine
        if time.monotonic() < self.next_check:
            return
        self.next_check = time.monotonic() + 2
        try:
            with e.store.db() as db:
                rows = db.execute('SELECT * FROM threads ORDER BY conversation').fetchall()
            rows = [r for r in rows if e.settings.inboxes.get(r['account'], {}).get('pending_guard_enabled') is True]
            if not rows:
                return
            row = rows[self.cursor % len(rows)]
            self.cursor += 1
            cid = row['conversation']
            current = e.cw.conversation(cid)
            if current.get('status') != 'pending':
                return
            history = e.cw.history(cid)
            reason = reason_for(current, history, (e.trial_for(cid) or e.order_intake.agent_loop.conversation_scope(cid)), e.store.ownership(cid)[0], time.time())
            if not reason:
                return
            # Recheck before opening. Explicit status is idempotent and may safely
            # retry after network failure, unlike sending public replies/orders.
            if e.cw.conversation(cid).get('status') != 'pending':
                return
            e.cw.status(cid, 'open')
            e.store.set_owner(cid, 'human')
            latest = max((m['id'] for m in history if not m.get('private')), default=0)
            e.note(f'pending-guard:{cid}:{latest}', cid, 'CẦN NHÂN VIÊN: ' + reason, apply_capture=True)
        except Exception as exc:
            logging.getLogger(__name__).warning('pending_guard: %s', type(exc).__name__)
