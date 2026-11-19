"""Model aliases within one receipt day; never fuzzy-edit model identifiers."""
import re
import unicodedata
from datetime import datetime, timedelta, timezone

VN = timezone(timedelta(hours=7))

def day_bounds(timestamp):
    day = datetime.fromtimestamp(float(timestamp), VN).replace(hour=0, minute=0, second=0, microsecond=0)
    return day.timestamp(), (day + timedelta(days=1)).timestamp()

def keys(value):
    text = ''.join(c for c in unicodedata.normalize('NFD', str(value).upper().replace('Đ', 'D')) if not unicodedata.combining(c))
    text = re.sub(r'\.(?:AI|PDF|PSD|CDR)\b', '', text)
    found = []
    for m in re.finditer(r'(?<![A-Z0-9])([A-Z0-9]+(?:-[A-Z0-9]+)*)(?:\.(0?[1-9]|1[0-2]))(?![A-Z0-9.])', text):
        base = re.sub(r'^(?:GV|HN|TD|TB)\d*[A-Z0-9]*-', '', m[1])
        found.append((base, int(m[2])))
    return set(found)

def same_model(left, right):
    a, b = keys(left), keys(right)
    return len(a) == 1 and len(b) == 1 and a == b

def confirmed_slip(db, account, thread, message_id):
    if not db.execute("SELECT 1 FROM sqlite_master WHERE name='intake_runs'").fetchone():
        return False
    return bool(db.execute("SELECT 1 FROM intake_runs WHERE account=? AND thread_id=? AND json_extract(payload,'$.individual_slip')=1 AND EXISTS(SELECT 1 FROM json_each(json_extract(payload,'$.messages')) WHERE CAST(value AS TEXT)=?) LIMIT 1", (account, thread, str(message_id))).fetchone())

def isolated_sources(collector, run, messages):
    """Read primary-sender images separately, reuse already extracted slips."""
    import json
    rule = (collector.intake.policy(run['account']) or {}).get('group_intake_rules', {}).get(run['account'], {}).get(run['thread_id'], {})
    if rule.get('mode') != 'primary_slip_sender':
        return None
    days = {day_bounds(m['timestamp']) for m in messages}
    candidates = {str(m['message_id']): m for m in messages}
    with collector.store.db() as db:
        # A later file can complete a slip received earlier today, outside this batch.
        if any(a.get('name', '').lower().endswith(('.ai', '.pdf', '.psd', '.cdr')) for m in messages for a in m.get('assets', [])):
            for start, end in days:
                for row in db.execute('SELECT payload FROM captures WHERE account=? AND thread_id=? AND CAST(json_extract(payload,\'$.timestamp\') AS REAL)>=? AND CAST(json_extract(payload,\'$.timestamp\') AS REAL)<? ORDER BY revision DESC', (run['account'], run['thread_id'], start, end)):
                    m = json.loads(row[0]); candidates.setdefault(str(m['message_id']), m)
        known = set()
        for row in db.execute('SELECT payload FROM design_briefs WHERE account=? AND thread_id=?', (run['account'], run['thread_id'])):
            p = json.loads(row[0])
            if p.get('brief', {}).get('image_context') == 'production_slip' or any(confirmed_slip(db,run['account'],run['thread_id'],s['message_id']) for s in p.get('sources',[]) if s.get('images')):
                known.update(str(s['message_id']) for s in p.get('sources', []) if s.get('images'))
    return [[m] for mid, m in candidates.items() if mid not in known and str(m.get('sender_id')) == str(rule.get('primary_sender_id')) and m.get('images') and not m.get('recalled') and not m.get('revision')]
