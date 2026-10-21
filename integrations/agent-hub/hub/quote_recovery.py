"""Resolve exact local quote IDs without guessing from message proximity."""
import json
from hub.order_additions import resolve_quote_db
from hub.store import event_key


def recover_quotes(store, messages):
    with store.db() as db:
        for message in messages:
            quote = message.get('quoted_image')
            if not quote or quote.get('resolved'):
                continue
            original = resolve_quote_db(db, message)
            if not original:
                continue
            target = db.execute('SELECT id,payload FROM captures WHERE account=? AND thread_id=? AND message_id=? ORDER BY revision DESC LIMIT 1', (message['account'], message['thread_id'], message['message_id'])).fetchone()
            source = db.execute('SELECT id FROM captures WHERE account=? AND thread_id=? AND message_id=? ORDER BY revision DESC LIMIT 1', (message['account'], message['thread_id'], original['message_id'])).fetchone()
            if not target or not source:
                continue
            current = json.loads(target[1])
            if current.get('revision') or current.get('recalled'):
                continue
            media = [db.execute('SELECT mime_type,data FROM media WHERE id=? AND capture_id=?', (mid, source[0])).fetchone() for mid in original['images']]
            if not all(media):
                continue
            ids = []
            for mid, row in zip(original['images'], media):
                identity = event_key('exact-quote', target[0], mid)
                db.execute('INSERT OR IGNORE INTO media VALUES(?,?,?,?)', (identity, target[0], row[0], row[1]))
                ids.append(identity)
            current['images'] = current.get('images') or ids
            current['quoted_image'] = {**quote, 'resolved': True, 'message_id': original['message_id'], 'sender': original.get('sender',''), 'timestamp': original['timestamp']}
            current['attachments'] = [a for a in current.get('attachments',[]) if a != 'zalo-desktop:quoted-image-unresolved']
            db.execute('UPDATE captures SET payload=? WHERE id=?', (json.dumps(current,ensure_ascii=False), target[0]))
            message.update(current)
