"""Read consistent copies of WhatsApp's cache; never open a browser or write its profile."""
import shutil
import tempfile
from pathlib import Path

from .native import text_database


def live_records(store):
    latest = {}
    errors = []
    for record in store.iterate_records(bad_deserializer_data_handler=lambda *a: errors.append(True)):
        previous = latest.get(record.key.raw_key)
        if previous is None or record.ldb_seq_no > previous.ldb_seq_no:
            latest[record.key.raw_key] = record
    if errors:
        raise ValueError('Unsupported cache format')
    return [r.value for r in latest.values() if r.is_live and isinstance(r.value, dict)]


def jid(value):
    return value.get('_serialized', '') if isinstance(value, dict) else str(value or '')


def text_field(value):
    # CCL returns non-ASCII V8 OneByteString values as bytes; these are Latin-1
    # code units, not encrypted names. Only decode fields whose schema is text.
    return value.decode('latin-1') if isinstance(value,bytes) else (value if isinstance(value,str) else '')


def load():
    from ccl_chromium_reader import ccl_chromium_indexeddb
    source = Path.home() / 'AppData/Local/Packages/5319275A.WhatsAppDesktop_cv1g1gvanyjgm/LocalCache/EBWebView/Default/IndexedDB/https_web.whatsapp.com_0.indexeddb.leveldb'
    def marks():
        return {p.name: (p.stat().st_size, p.stat().st_mtime_ns) for p in source.iterdir() if p.is_file() and p.name != 'LOCK'}
    before = marks()
    with tempfile.TemporaryDirectory(prefix='pt-whatsapp-cache-') as tmp:
        for name in before:
            shutil.copyfile(source / name, Path(tmp) / name)
        if marks() != before:
            raise ValueError('Cache changed during snapshot')
        with ccl_chromium_indexeddb.WrappedIndexDB(Path(tmp)) as indexed:
            model = indexed['model-storage']
            groups = {jid(r['id']): text_field(r['name']) for r in live_records(model['chat'])
                      if jid(r.get('id')).endswith('@g.us') and text_field(r.get('name')).strip()}
            contacts = {jid(r['id']): next((text_field(r[k]) for k in ('name','pushname','shortName') if text_field(r.get(k))), '') for r in live_records(model['contact'])}
            metadata = live_records(model['message'])
    text = text_database()
    try:
        # Private chat contents are not queried.
        bodies = {str(r[0]): (r[1], float(r[2]), r[3]) for r in text.execute("SELECT id,chatId,timestamp,text FROM message WHERE chatId LIKE '%@g.us'")}
    finally:
        text.close()
    return groups, contacts, metadata, bodies


def convert(meta, groups, contacts, bodies, account, policy):
    from hub.order_policy import capture_allowed
    identity = meta.get('id', '')
    if not isinstance(identity,str):
        return None
    parts = identity.split('_')
    if len(parts) < 3 or parts[0] not in ('true', 'false'):
        return None
    thread = parts[1]
    if not thread.endswith('@g.us') or not groups.get(thread):
        return None
    name = groups[thread]
    if not capture_allowed(policy, 'whatsapp', thread, name):
        return None
    outgoing = parts[0] == 'true'
    sender_id = jid(meta.get('author')) or (parts[-1] if len(parts) > 3 and '@' in parts[-1] else jid(meta.get('from')))
    sender = contacts.get(sender_id) or ('Tài khoản WhatsApp trên máy' if outgoing else 'Thành viên chưa xác định tên')
    body = bodies.get(str(meta.get('rowId')))
    stamp = float(meta.get('t') or 0)
    if stamp <= 0:
        return None
    if body and (body[0] != thread or body[1] != stamp):
        raise ValueError('Message source mismatch')
    kind = meta.get('type')
    if kind not in ('chat', 'image', 'document', 'video', 'audio', 'ptt', 'sticker'):
        return None
    text = body[2] if body else ''
    unsupported = kind != 'chat' or not body
    return dict(account=account, thread_id=thread, message_id=identity, display_name=name,
                sender=sender, sender_id=sender_id, timestamp=stamp,
                direction='outgoing' if outgoing else 'incoming', origin='staff' if outgoing else 'customer',
                text=text or '[WhatsApp: nội dung/đính kèm cần kiểm tra trên ứng dụng]',
                attachments=['whatsapp-desktop:pending-media'] if unsupported else [],
                images=[], assets=[], revision=0, recalled=False)
