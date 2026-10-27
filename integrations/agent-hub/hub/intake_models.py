"""Durable, source-exclusive model intake and production placement notices."""
import json
import re
import time

from hub.order_policy import key
from hub.store import event_key


def placement(message):
    text = key(message.get('text', ''))
    from hub.print_changes import quantities
    return bool(re.search(r'\b(cữ in|vị trí in|in cách|cách chân|cách lai|cách gấu)\b', text)
                and not quantities(text))


def split(intake, run, payload, batch, groups):
    if len(groups) < 2 or payload.get('model_parent'):
        return False
    by_id = {m['message_id']: identity for identity, m in batch}
    with intake.store.db() as db:
        db.execute('BEGIN IMMEDIATE')
        current = db.execute('SELECT state,payload FROM intake_runs WHERE id=?', (run['id'],)).fetchone()
        saved = json.loads(current['payload'])
        if current['state'] not in ('analyzing', 'review', 'waiting_details') or saved.get('request_id') or saved.get('submitted_payload'):
            raise ValueError('Hồ sơ đã gửi/đang xử lý; không tách lại')
        children = []
        for group in groups:
            messages = [m for _, m in group]
            ids = [m['message_id'] for m in messages]
            identity = event_key('intake-model-v1', run['account'], run['thread_id'], ids)
            child = {k: payload[k] for k in ('group_name', 'sender', 'sender_key', 'first_timestamp', 'last_timestamp')}
            child.update(messages=ids, model_parent=run['id'])
            db.execute("INSERT OR IGNORE INTO intake_runs VALUES(?,?,?,?,?,?,?,?)",
                       (identity, run['account'], run['thread_id'], run['conversation'], 'model_pending',
                        json.dumps(child, ensure_ascii=False), '{}', time.time()))
            for m in messages:
                claim = db.execute('SELECT run_id FROM intake_sources WHERE capture_id=?', (by_id[m['message_id']],)).fetchone()
                if not claim or claim[0] not in (run['id'], identity):
                    raise ValueError('Nguồn đã thuộc hồ sơ khác; không tạo trùng')
                db.execute('UPDATE intake_sources SET run_id=? WHERE capture_id=? AND run_id=?',
                           (identity, by_id[m['message_id']], run['id']))
            children.append(identity)
        db.execute("UPDATE intake_runs SET state='superseded',result=? WHERE id=?",
                   (json.dumps({'reason': 'Đã tách xử lý độc lập từng mẫu', 'children': children}), run['id']))
    return True


def poll(intake):
    with intake.store.db() as db:
        rows = db.execute("SELECT * FROM intake_runs WHERE state='model_pending' ORDER BY created").fetchall()
    for row in rows:
        run = dict(row)
        if not intake.engine.intake_management.enabled(run['account']):
            continue
        payload = json.loads(run['payload'])
        if not intake.quiet_now(run, payload):
            continue
        with intake.store.db() as db:
            if not db.execute("UPDATE intake_runs SET state='analyzing' WHERE id=? AND state='model_pending'", (run['id'],)).rowcount:
                continue
            batch = []
            for mid in payload['messages']:
                source = db.execute('SELECT id,payload FROM captures WHERE account=? AND thread_id=? AND message_id=? ORDER BY revision DESC LIMIT 1',
                                    (run['account'], run['thread_id'], mid)).fetchone()
                if source:
                    batch.append((source['id'], json.loads(source['payload'])))
        try:
            if len(batch) != len(payload['messages']) or any(m.get('revision') or m.get('recalled') or not intake.accepts(m) for _, m in batch):
                raise ValueError('Nguồn mẫu thiếu/đã thay đổi hoặc chính sách không cho phép')
            intake.analyze(run, payload, batch)
        except Exception as exc:
            reason = str(exc)[:500] if isinstance(exc, ValueError) else type(exc).__name__
            intake.state(run['id'], 'review', {'reason': reason})
        return True
    return False


def forward_placement(intake, run, messages):
    requests = [m for m in messages if placement(m)]
    if not requests:
        return False
    from hub.print_changes import quantities
    if any(quantities(m.get('text', '')) for m in messages):
        return False  # A quantity-bearing order retains its own placement notes.
    route = intake.engine.print_approvals.route()
    if not route or not route.get('delivery_enabled'):
        raise ValueError('Luồng chuyển cữ in chưa bật')
    if any(m.get('revision') or m.get('recalled') or m.get('attachments') or not intake.accepts(m) for m in messages):
        raise ValueError('Cần kiểm tra nguồn lời dặn cữ in')
    if not any(m.get('images') for m in messages) or any(m.get('quoted_image') and not m['quoted_image'].get('resolved') for m in messages):
        raise ValueError('Cữ in cần ảnh đúng mẫu đã tải đầy đủ')
    ids = [m['message_id'] for m in messages]
    confirmation = requests[-1]['message_id']
    identity = event_key('print-placement-v1', run['account'], run['thread_id'], confirmation)
    notice = 'DẶN CỮ IN — ' + requests[-1]['display_name'] + '\nKhách: ' + requests[-1]['sender']
    notice += '\n' + '\n'.join(m['text'] for m in requests)
    notice += '\nÁp dụng cho mẫu trong ảnh đính kèm. Đây là lời dặn vị trí in, không phải số lượng đặt mới.'
    payload = {'kind': 'placement', 'destination': route, 'confirmation': confirmation,
               'messages': ids, 'new_message_ids': ids, 'notice': notice}
    with intake.store.db() as db:
        db.execute('BEGIN IMMEDIATE')
        previous = db.execute('SELECT id,payload FROM print_approvals WHERE account=? AND thread_id=? AND confirmation_id=?',
                              (run['account'], run['thread_id'], confirmation)).fetchone()
        if previous and previous['id'] != identity:
            raise ValueError('Lời dặn đã có hồ sơ chuyển nhóm; đối chiếu trước khi gửi lại')
        for mid in ids:
            claimed = db.execute('SELECT approval_id FROM print_change_sources WHERE account=? AND thread_id=? AND message_id=?',
                                 (run['account'], run['thread_id'], mid)).fetchone()
            if claimed and claimed[0] != identity:
                raise ValueError('Nguồn đã thuộc thông báo sản xuất khác; không gửi trùng')
        db.execute('INSERT OR IGNORE INTO print_approvals VALUES(?,?,?,?,?,?,?)',
                   (identity, run['account'], run['thread_id'], confirmation, 'awaiting_evidence', json.dumps(payload, ensure_ascii=False), time.time()))
        for mid in ids:
            db.execute('INSERT OR IGNORE INTO print_change_sources VALUES(?,?,?,?)', (run['account'], run['thread_id'], mid, identity))
        db.execute("UPDATE intake_runs SET state='ignored',result=? WHERE id=?",
                   (json.dumps({'reason': 'Đã chuyển lời dặn cữ in sang luồng nhóm sản xuất', 'print_approval_id': identity}, ensure_ascii=False), run['id']))
    return True
