"""Operator-owned dossiers and an explicit, durable pre-export approval gate."""
import copy
import hashlib
import json
import math
import os
import re
import time
from pathlib import Path, PureWindowsPath

from hub.store import event_key


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def is_manual(store, bid):
    with store.db() as db:
        row = db.execute('SELECT payload FROM design_briefs WHERE id=?', (bid,)).fetchone()
    return bool(row and json.loads(row[0]).get('manual_export'))


def source_path(root, value):
    if not root:
        raise ValueError('Hub chưa cấu hình kho nguồn NAS')
    value = str(value).strip().replace('\\', '/')
    for prefix in ('W:/', '//192.168.1.203/n8n_upload/'):
        if value.lower().startswith(prefix.lower()):
            value = value[len(prefix):]
            break
    if not value or PureWindowsPath(value).drive or value.startswith('/') or any(s in ('', '.', '..') for s in value.split('/')) or ':' in value:
        raise ValueError('Chọn đường dẫn tương đối trong NAS n8n_upload, hoặc W:\\...')
    base = Path(root).resolve(strict=True)
    path = (base / value).resolve(strict=True)
    if base not in path.parents or not path.is_file():
        raise ValueError('File không nằm trong kho NAS')
    return path, value


def create(e, data):
    """Register only: no AI, ERP, export or message side effects."""
    title = str(data.get('title', '')).strip()
    if not 1 <= len(title) <= 100:
        raise ValueError('Nhập tên mẫu 1–100 ký tự')
    path, relative = source_path(os.environ.get('HUB_SOURCE_ARCHIVE', ''), data.get('path'))
    if path.suffix.lower() not in ('.ai', '.pdf'):
        raise ValueError('Chế độ chọn group hiện hỗ trợ AI/PDF; không giả lập chọn group cho PSD/CDR')
    from hub.artwork_pdf import MAX_BYTES
    if not 0 < path.stat().st_size <= MAX_BYTES:
        raise ValueError('File rỗng hoặc vượt giới hạn đọc nguồn hiện tại')
    before = path.stat()
    sha = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            sha.update(chunk)
    if (before.st_size, before.st_mtime_ns) != (path.stat().st_size, path.stat().st_mtime_ns):
        raise ValueError('File đang thay đổi; đợi lưu xong')
    account = next((a for a in e.settings.inboxes if a == 'zalo-personal-1'), next(iter(e.settings.inboxes), None))
    if not account:
        raise ValueError('Chưa cấu hình worker nhận việc')
    asset = dict(name=path.name, relative_path=relative, sha256=sha.hexdigest(), state='ready', kind='file')
    bid = event_key('manual-dossier-v1', account, relative, asset['sha256'], title)
    mid = 'manual-file:' + asset['sha256']
    sources = [dict(message_id=mid, text=path.name, images=[], assets=[asset])]
    reference = str(data.get('reference_path') or '').strip()
    if reference:
        ref, _ = source_path(os.environ['HUB_SOURCE_ARCHIVE'], reference)
        if ref.suffix.lower() not in ('.jpg', '.jpeg', '.png') or not 0 < ref.stat().st_size <= 8_000_000:
            raise ValueError('Maket: chọn JPG/PNG tối đa 8MB')
        raw = ref.read_bytes()
        from hub.media import image_mime
        mime = image_mime(raw)
        image_id = hashlib.sha256(raw).hexdigest()
        sources.append(dict(message_id='manual-reference:' + image_id, text=ref.name, images=[image_id], assets=[]))
    payload = dict(account=account, thread_id='manual:' + bid, conversation_id=0, manual_export=True,
                   execution_allowed=True, sources=sources,
                   brief=dict(title=title, kind='print_export', image_context='standalone_artwork',
                              source_message_ids=[s['message_id'] for s in sources], requirements=[], missing_fields=[], conflicts=[]))
    with e.store.db() as db:
        db.execute('BEGIN IMMEDIATE')
        existed = db.execute('SELECT 1 FROM design_briefs WHERE id=?', (bid,)).fetchone()
        if not existed:
            if reference:
                db.execute('INSERT OR IGNORE INTO media VALUES(?,?,?,?)', (image_id, bid, mime, raw))
            db.execute('INSERT INTO design_briefs VALUES(?,?,?,?,?,?,?)', (bid, bid, account, payload['thread_id'], 0, json.dumps(payload, ensure_ascii=False), time.time()))
    return dict(id=bid, duplicate=bool(existed), message='Đã mở hồ sơ. Nhập thông số và yêu cầu AI lập phương án; chưa xuất file.')


def review_data(e, bid):
    if not is_manual(e.store, bid):
        return None
    result = []
    with e.store.db() as db:
        for kind in ('jpg_exports', 'native_selections'):
            clause = "json_extract(payload,'$.brief_id')=?" if kind == 'jpg_exports' else 'brief_id=?'
            for row in db.execute('SELECT * FROM ' + kind + ' WHERE ' + clause + " AND state='awaiting_owner'", (bid,)):
                p = json.loads(row['payload'])
                if kind == 'jpg_exports':
                    scanfile = Path(e.store.path).parent / 'artwork-checks' / p['source'].get('inspection_id', row['id']) / 'native-groups.json'
                    if not scanfile.exists() and p.get('parent_job_id'):
                        scanfile = scanfile.parent.parent / p['parent_job_id'] / 'native-groups.json'
                    scan = json.loads(scanfile.read_text()) if scanfile.exists() else {}
                    plan = p.get('plan', {})
                else:
                    scanrow = db.execute('SELECT payload FROM native_selections WHERE id=?', (p['scan_id'],)).fetchone()
                    scan = json.loads(scanrow[0]).get('scan', {}) if scanrow else {}
                    plan = dict(candidate_ids=p.get('candidate_ids', []), side=p.get('side'), width_cm=p.get('width_cm'))
                result.append(dict(id=row['id'], kind=kind, revision=digest(p), plan=plan, scan=scan))
    return dict(jobs=result, local_only=True)


def selected(ids, candidates):
    byid = {c['id']: c for c in candidates}
    if not isinstance(ids, list) or not ids or any(not isinstance(i, str) for i in ids) or len(set(ids)) != len(ids) or not set(ids) <= byid.keys():
        raise ValueError('Chọn ít nhất một đối tượng có trong file nguồn')
    if any(a != b and b.startswith(a + '.') for a in ids for b in ids):
        raise ValueError('Không chọn đồng thời group cha và con')
    return [byid[i] for i in ids]


def approve(e, bid, data):
    """Edit only selection; preserve validated layout, source and output routing."""
    live = review_data(e, bid)
    if not live:
        raise ValueError('Không phải hồ sơ chạy tay')
    item = next((j for j in live['jobs'] if j['id'] == data.get('job_id') and j['kind'] == data.get('kind')), None)
    if not item:
        raise ValueError('Lượt không còn chờ duyệt; không xuất lại')
    if item['revision'] != data.get('revision'):
        raise ValueError('Phương án đã đổi; tải lại trước khi duyệt')
    kind = item['kind']
    with e.store.db() as db:
        db.execute('BEGIN IMMEDIATE')
        row = db.execute('SELECT * FROM ' + kind + ' WHERE id=?', (item['id'],)).fetchone()
        p = json.loads(row['payload'])
        if row['state'] != 'awaiting_owner' or digest(p) != item['revision']:
            raise ValueError('Lượt đã được xử lý ở phiên khác')
        scan = item['scan']
        if kind == 'native_selections':
            chosen = selected(data.get('candidate_ids'), scan.get('candidates', []))
            from hub.native_auto import validate
            face = dict(p['auto_face'], candidate_ids=[c['id'] for c in chosen])
            face = validate(dict(is_pet=True, same_design=True, issues=[], faces=[face]), scan, face['dimension_refs'])[0]
            p.update(candidate_ids=face['candidate_ids'], candidates=face['candidates'], width_cm=face['width_cm'], auto_face=face)
            state = 'render_queued'
        else:
            edits = data.get('selections', [])
            plan = copy.deepcopy(p['plan'])
            components = [(pi, ci, c) for pi, panel in enumerate(plan.get('panels', [])) for ci, c in enumerate(panel.get('components', []))]
            if len(edits) != len(components):
                raise ValueError('Cần đủ lựa chọn cho từng mặt trong phương án')
            for edit, (pi, ci, component) in zip(edits, components):
                if edit.get('panel') != pi or edit.get('component') != ci:
                    raise ValueError('Sai mặt cần duyệt')
                ids = edit.get('object_ids')
                if ids == component['object_ids']:
                    continue
                if plan.get('renderer') != 'native_group_v1':
                    raise ValueError('Loại nguồn này duyệt nguyên phương án; chưa hỗ trợ thay group trực tiếp')
                chosen = selected(ids, scan.get('candidates', []))
                if scan.get('missing_fonts') and any(c.get('live_text_count') for c in chosen):
                    raise ValueError('Đối tượng mới chọn có font thiếu')
                bounds = [c['bounds'] for c in chosen]
                width = (max(b[2] for b in bounds) - min(b[0] for b in bounds)) * 2.54 / 72
                if not math.isfinite(width) or width <= 0:
                    raise ValueError('Bounds đối tượng không hợp lệ')
                # Complicated source registrations must retain their original object geometry.
                if any(component.get(k) for k in ('native_reference','alignment_reference_box','native_frame_registration')):
                    raise ValueError('Mặt canh theo object con: giữ lựa chọn hoặc lập lại phương án sau khi đổi group')
                oldwidth = component['width_cm']
                align = component.get('horizontal_alignment', 'left')
                component['x_cm'] += (oldwidth-width)/2 if align == 'center' else oldwidth-width if align == 'right' else 0
                component.update(object_ids=ids, width_cm=width)
                panel = plan['panels'][pi]
                byid = {o['id']: o for o in panel.get('objects', [])}
                byid.update({o['id']: dict({k:v for k,v in o.items() if k!='preview'}, native=True, page=o.get('page', 1)) for o in chosen})
                needed = {i for c in panel['components'] for i in c['object_ids']}
                needed |= {x for x in [panel.get('background_object_id'), *[c.get('background_object_id') for c in panel['components']]] if x}
                panel['objects'] = [byid[i] for i in sorted(needed)]
            p['plan'] = plan
            state = 'queued'
        p.pop('review_reason', None)
        p['owner_approval'] = dict(at=time.time(), job_id=item['id'], plan_hash=digest(p.get('plan')), revision=item['revision'], selections=data.get('selections'), candidate_ids=data.get('candidate_ids'))
        db.execute('UPDATE ' + kind + ' SET state=?,payload=? WHERE id=?', (state, json.dumps(p, ensure_ascii=False), item['id']))
    return dict(message='Đã duyệt và giao worker xuất. Lượt này không thể duyệt chạy trùng.', id=item['id'])


def discard(e, bid, data):
    live = review_data(e, bid)
    item = next((j for j in (live or {}).get('jobs', []) if j['id'] == data.get('job_id') and j['kind'] == data.get('kind')), None)
    if not item or item['revision'] != data.get('revision'):
        raise ValueError('Phương án đã đổi hoặc không còn chờ duyệt')
    with e.store.db() as db:
        db.execute('BEGIN IMMEDIATE')
        row = db.execute('SELECT state,payload FROM '+item['kind']+' WHERE id=?', (item['id'],)).fetchone()
        if row['state'] != 'awaiting_owner' or digest(json.loads(row['payload'])) != item['revision']:
            raise ValueError('Phương án đã được xử lý ở phiên khác')
        p=json.loads(row['payload']);p['owner_discarded_at']=time.time()
        db.execute('UPDATE '+item['kind']+" SET state='superseded',payload=? WHERE id=?", (json.dumps(p),item['id']))
    return dict(message='Đã bỏ phương án chưa xuất; có thể nhập lại thông số sau khi bỏ hết phần đang chờ.')
