"""Owner rule: borrow all customer photos from the immediately preceding batch."""
import json


def select(db, run, payload, sources):
    from hub.evidence_document import select_sources
    from hub.intake_lifecycle import reusable
    from hub.text_quantity_orders import source_proof, explicit_quantity, uncovered_quantities

    if any(m.get('quoted_image') or m.get('quoted_file') or
           (m.get('origin') == 'customer' and m.get('images')) for m in sources):
        return None
    before = min(m['timestamp'] for m in sources)
    # Root collection batches only: derived split orders are not another chat batch.
    rows = db.execute("""SELECT * FROM intake_runs WHERE account=? AND thread_id=? AND id<>?
        AND json_extract(payload,'$.collection_scope')='group'
        AND json_extract(payload,'$.model_parent') IS NULL
        AND json_extract(payload,'$.proposal_parent') IS NULL
        AND CAST(json_extract(payload,'$.last_timestamp') AS REAL)<?
        ORDER BY CAST(json_extract(payload,'$.last_timestamp') AS REAL) DESC LIMIT 1""",
        (run['account'], run['thread_id'], run['id'], before)).fetchall()
    if not rows:
        return None
    previous = dict(rows[0]); prior = json.loads(previous['payload'])
    if previous['state'] not in ('review', 'waiting_details') or prior.get('request_id') or prior.get('submitted_payload'):
        return None
    original = select_sources(db, run['account'], run['thread_id'], prior['messages'])
    if any(m.get('origin') == 'customer' and not m.get('images') and
           any(a.get('kind') == 'image' for a in m.get('assets', [])) for m in original):
        raise ValueError('Cụm trước còn ảnh khách chưa tải được; cần đủ ảnh trước khi liên kết')
    # A prior unresolved quantity must not silently disappear into the new order.
    if uncovered_quantities(original) or any(explicit_quantity(m) for m in original):
        return None
    photos = [m for m in original if m.get('origin') == 'customer' and m.get('images')
              and not m.get('quoted_image') and not m.get('conversation_screenshot')
              and not m.get('images_ignored_by_group_rule')]
    if not photos:
        return None
    from hub.group_intake_rules import filter_messages
    policy = db.execute('SELECT payload FROM intake_policy WHERE account=?', (run['account'],)).fetchone()
    filtered = filter_messages(json.loads(policy[0]) if policy else {}, run['account'], photos)
    if any(not m.get('images') for m in filtered):
        return None
    if any(not reusable(db, {'payload': json.dumps(m), 'source_result': '{}'}) for m in photos):
        return None
    ids = {m['message_id'] for m in photos}
    hashes = {h for proof in source_proof(photos).values() for h in proof['images']}
    # Includes prepared/uncertain requests and photos consumed through a quote.
    for row in db.execute('SELECT id,state,payload,result FROM intake_runs WHERE account=? AND thread_id=? AND id<>?',
                          (run['account'], run['thread_id'], run['id'])):
        p = json.loads(row['payload']); result = json.loads(row['result'] or '{}')
        if not (p.get('request_id') or p.get('submitted_payload') or result.get('orders') or
                row['state'] in ('awaiting_evidence', 'evidence_ready', 'created', 'duplicate', 'sending', 'uncertain')):
            continue
        if ids.intersection(p.get('messages', [])):
            return None
        used = {h for proof in p.get('text_quantity_order', {}).get('sources', {}).values()
                for h in proof.get('images', [])}
        used.update(p.get('quote_evidence_order', {}).get('image_hashes', []))
        if hashes.intersection(used):
            return None
        # Older order paths may not have stored image hashes in their marker.
        clients = {m.get('client_message_id') for m in photos if m.get('client_message_id')}
        for mid in p.get('messages', []):
            capture = db.execute('SELECT payload FROM captures WHERE account=? AND thread_id=? AND message_id=? ORDER BY revision DESC LIMIT 1',
                                 (run['account'], run['thread_id'], mid)).fetchone()
            quote = (json.loads(capture[0]).get('quoted_image') or {}) if capture else {}
            if quote.get('message_id') in ids or quote.get('client_message_id') in clients:
                return None
    if len(sources) + len(photos) > 20:
        raise ValueError('Cụm trước có nhiều ảnh; tổng nguồn vượt 20 tin, cần nhân viên kiểm tra đủ ảnh')
    return {'run_id': previous['id'], 'message_ids': [m['message_id'] for m in photos],
            'sources': photos}
