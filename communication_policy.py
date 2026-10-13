"""Allowlisted web configuration and runtime Zalo contact policy.

Never return credentials from config.json. Saves preserve unrelated fields.
"""
import hashlib
import json
import os
import tempfile
import unicodedata
from pathlib import Path

CONFIG_FILE = Path(__file__).resolve().with_name('config.json')
FIELDS = ('zalo_contact_rules', 'zalo_default_receive_messages',
          'zalo_default_auto_order', 'zalo_internal_members',
          'zalo_skip_groups', 'zalo_disable_reply_groups')

class PolicyConflict(ValueError):
    pass

def key(name):
    return ' '.join(unicodedata.normalize('NFC', str(name or '')).casefold().split())

def contains(names, name):
    return bool(key(name)) and any(key(n) == key(name) for n in names)

def read_raw(path=None):
    with Path(path or CONFIG_FILE).open(encoding='utf-8-sig') as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError('config.json phải là đối tượng JSON')
    return data

def is_internal(config, name):
    return contains(config.get('zalo_internal_members', []), name)

def allowed(config, name, action):
    if action not in ('receive_messages', 'auto_order'):
        return False
    if not key(name) or is_internal(config, name) or contains(config.get('zalo_skip_groups', []), name):
        return False
    if action == 'receive_messages' and contains(config.get('zalo_disable_reply_groups', []), name):
        return False
    for row in config.get('zalo_contact_rules', []):
        if key(row.get('name')) == key(name):
            return row.get(action) is True
    return config.get('zalo_default_' + action, True) is True

def revision(config):
    raw = json.dumps({k:config.get(k) for k in FIELDS},sort_keys=True,ensure_ascii=False)
    return hashlib.sha256(raw.encode()).hexdigest()

def public_config(config):
    contacts = [{k:r[k] for k in ('name','receive_messages','auto_order')}
                for r in config.get('zalo_contact_rules', [])]
    for name in config.get('zalo_disable_reply_groups', []):
        row = next((r for r in contacts if key(r['name']) == key(name)), None)
        if row is None:
            contacts.append({'name':name, 'receive_messages':False,
                             'auto_order':config.get('zalo_default_auto_order', True)})
        else:
            row['receive_messages'] = False
    return {'schema_version':1, 'revision':revision(config),
            'defaults':{'receive_messages':config.get('zalo_default_receive_messages',True),
                        'auto_order':config.get('zalo_default_auto_order',True)},
            'contacts':contacts, 'internal_members':config.get('zalo_internal_members',[]),
            'skip_groups':config.get('zalo_skip_groups',[])}

def names(values):
    if not isinstance(values,list) or len(values)>2000:
        raise ValueError('Danh sách tối đa 2000 tên')
    result=[]; seen=set()
    for value in values:
        if not isinstance(value,str) or not value.strip() or len(value)>200 or any(c in value for c in '\r\n\x00'):
            raise ValueError('Tên phải có 1–200 ký tự trên một dòng')
        if key(value) in seen:
            raise ValueError('Tên bị trùng trong danh sách')
        seen.add(key(value)); result.append(value.strip())
    return result

def validate(payload):
    if not isinstance(payload,dict) or set(payload)-{'schema_version','revision','defaults','contacts','internal_members','skip_groups'}:
        raise ValueError('Trường cấu hình không được hỗ trợ')
    if payload.get('schema_version') != 1 or not isinstance(payload.get('revision'),str):
        raise ValueError('Hãy tải lại cấu hình trước khi lưu')
    defaults=payload.get('defaults')
    if not isinstance(defaults,dict) or set(defaults)!= {'receive_messages','auto_order'} or any(type(v) is not bool for v in defaults.values()):
        raise ValueError('Lựa chọn mặc định phải là bật/tắt')
    rows=payload.get('contacts')
    if not isinstance(rows,list) or len(rows)>2000:
        raise ValueError('Danh sách tối đa 2000 khách/nhóm')
    for row in rows:
        if not isinstance(row,dict) or set(row)!= {'name','receive_messages','auto_order'} or any(type(row[k]) is not bool for k in ('receive_messages','auto_order')):
            raise ValueError('Lựa chọn khách không hợp lệ')
    clean_names=names([r['name'] for r in rows])
    return {'zalo_contact_rules':[dict(r,name=n) for r,n in zip(rows,clean_names)],
            'zalo_default_receive_messages':defaults['receive_messages'],
            'zalo_default_auto_order':defaults['auto_order'],
            'zalo_internal_members':names(payload.get('internal_members')),
            'zalo_skip_groups':names(payload.get('skip_groups')),
            'zalo_disable_reply_groups':[n for r,n in zip(rows,clean_names) if not r['receive_messages']]}

def save(payload,path=None):
    changes=validate(payload)
    path=Path(path or CONFIG_FILE)
    lock=path.with_name(path.name+'.policy.lock')
    try:
        fd=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY)
    except FileExistsError:
        raise PolicyConflict('Đang có lượt lưu khác; tải lại và thử lại')
    os.close(fd)
    tmp=None
    try:
        current=read_raw(path)
        if payload['revision'] != revision(current):
            raise PolicyConflict('Cấu hình đã thay đổi; tải lại trước khi lưu')
        current.update(changes)
        with tempfile.NamedTemporaryFile('w',encoding='utf-8',dir=path.parent,delete=False) as f:
            tmp=f.name
            json.dump(current,f,ensure_ascii=False,indent=2);f.flush();os.fsync(f.fileno())
        os.replace(tmp,path);tmp=None
        return public_config(current)
    finally:
        if tmp:os.unlink(tmp)
        lock.unlink()
