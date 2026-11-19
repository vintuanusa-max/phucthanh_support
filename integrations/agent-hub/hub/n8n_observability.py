"""Read-only business receipts for the local operations dashboard."""
import json
import time
import re


def obj(raw):
    if isinstance(raw, dict): return raw
    try:
        value = json.loads(raw or '{}')
        return value if isinstance(value, dict) else {}
    except (ValueError, TypeError): return {}


def safe(value):
    text = str(value or '')[:2000]
    text = re.sub(r'(?i)(bearer\s+|(?:api[_-]?key|token|password)\s*[=:]\s*)[^\s,;]+', r'\1[ẩn]', text)
    return re.sub(r'https?://[^\s]+', '[URL trong lỗi đã ẩn]', text)


def snapshot(store):
    items, batches = [], []
    with store.db() as db:
        tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        groups = {(r['account'], r['thread_id']):r['display_name'] for r in db.execute('SELECT account,thread_id,display_name FROM threads')} if 'threads' in tables else {}
        if 'n8n_batch_outbox' not in tables:
            return dict(items=[], batches=[], updated=time.time(), read_only=True)
        outbox = db.execute('SELECT * FROM n8n_batch_outbox WHERE created>=? ORDER BY created DESC', (time.time()-7*86400,)).fetchall()
        for batch in outbox:
            source = obj(batch['payload']); group = (source.get('groups') or [{}])[0]
            result = obj(batch['result'])
            name = groups.get((batch['account'],batch['thread_id'])) or group.get('group') or batch['thread_id']
            batches.append(dict(id=batch['id'],group=name,state=batch['state'],created=batch['created'],updated=batch['updated'],message_count=len(group.get('messages',[])),error=safe(result.get('error')),action=safe(result.get('action'))))
            tasks = db.execute("SELECT * FROM n8n_task_execution WHERE mode='production' AND batch_id=? ORDER BY updated DESC", (batch['id'],)).fetchall() if 'n8n_task_execution' in tables else []
            for task in tasks:
                payload, result = obj(task['payload']), obj(task['result'])
                details = obj(result.get('details'))
                state = result.get('business_state') or task['state']
                error = result.get('error') or result.get('reason') or '; '.join(map(str,payload.get('review') or []))
                orders, files, brief_ids = details.get('orders') or [], [], result.get('brief_ids') or []
                if details.get('archive_relative'): files.append(details['archive_relative'])
                receipt = result.get('receipt_id')
                table = {'erp_order':'intake_runs','export_pet':'pet_exports','export_jpg':'jpg_exports','sample_design':'psd_samples'}.get(task['kind'])
                if receipt and table in tables:
                    row = db.execute('SELECT * FROM '+table+' WHERE id=? AND account=?', (receipt,task['account'])).fetchone()
                    if row:
                        state = row['state']; p = obj(row['payload']); r = obj(row['result']) if 'result' in row.keys() else {}
                        error = p.get('error') or r.get('error') or r.get('reason') or error
                        orders = r.get('orders') or orders
                        if p.get('archive_relative'): files = [p['archive_relative']]
                        if p.get('brief_id'): brief_ids = [p['brief_id']]
                        if table=='psd_samples':
                            error=p.get('reason') or error
                            if (p.get('report') or {}).get('path'): files=[p['report']['path']]
                if result.get('reply_draft'):
                    error += '\nBản nháp nội bộ: '+result['reply_draft']
                if task['kind']=='print_approval':
                    error += '\n'+'; '.join(str(d.get('account'))+': '+str(d.get('state')) for d in details.get('deliveries',[]))
                label = {'erp_order':'Lên đơn ERP','export_pet':'Xuất PNG/TIFF','export_jpg':'Xuất JPG CMYK','sample_design':'Lên mẫu','inspect_sources':'Đọc nguồn bổ sung','reply':'Soạn trả lời','unsupported':'Chưa hỗ trợ'}.get(task['kind'],task['kind'])
                if task['kind']=='print_approval':label='Duyệt in → nhóm nội bộ'
                if task['kind'] in ('inspect_sources','reply','sample_design') and task['state']=='pending_binding':
                    error = 'Chưa có bộ xử lý tự động nối với công việc n8n này; cần kiểm tra nội bộ.'
                elif error == 'WAITING_VERIFIED_BUSINESS_BINDING':
                    error = 'Chưa đối soát được công việc với đơn ERP/hồ sơ file; chưa xác nhận hoàn tất.'
                items.append(dict(id=task['id'],batch_id=batch['id'],group=name,model=payload.get('model_code') or 'Chưa xác định mẫu',kind=task['kind'],kind_label=label,state=state,ledger_state=task['state'],error=safe(error),created=batch['created'],updated=task['updated'],attempts=task['attempts'],orders=[{k:o[k] for k in ('id','code') if k in o} for o in orders if isinstance(o,dict)],files=[safe(f) for f in files],brief_ids=brief_ids,source_count=len(payload.get('message_ids') or [])))
    return dict(items=items,batches=batches,updated=time.time(),read_only=True)
