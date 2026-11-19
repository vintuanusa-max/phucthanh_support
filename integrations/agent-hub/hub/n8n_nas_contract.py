"""Metadata-only boundary: source bytes remain in the NAS archive."""
from pathlib import PurePosixPath
import hashlib
import json


def asset_ref(asset):
    path=str(asset.get('relative_path') or '').replace('\\','/')
    p=PurePosixPath(path)
    if not path or p.is_absolute() or '..' in p.parts or ':' in path:
        raise ValueError('NAS path must be archive-relative')
    sha=asset.get('sha256','')
    if len(sha)!=64 or any(c not in '0123456789abcdef' for c in sha):
        raise ValueError('Verified source hash required')
    return {k:v for k,v in {
        'id':asset['id'],'name':asset.get('name',p.name),'relative_path':str(p),
        'sha256':sha,'size':asset.get('size'),
        'state':asset.get('state','unknown'),'storage':'nas_source_archive',
        'media_type':asset.get('mime_type','application/octet-stream'),
    }.items() if v is not None}


def message_ref(message):
    refs=[asset_ref(a) for a in message.get('assets',[]) if a.get('state')=='ready']
    unresolved=[{'id':a.get('id'),'name':a.get('name'),'state':a.get('state','missing')}
                for a in message.get('assets',[]) if a.get('state')!='ready']
    # Never silently replace missing image paths with bytes or guessed paths.
    image_ids=list(message.get('images',[]))
    return {'message_id':message['message_id'],'timestamp':message['timestamp'],
            'role':message.get('origin','unknown'),'text':message.get('text',''),
            'image_ids':image_ids,'assets':refs,'unresolved_assets':unresolved,
            'needs_image_path_reconciliation':bool(image_ids and not any(
                a['media_type'].startswith('image/') for a in refs))}


def envelope(account,thread_id,conversation,messages,wait_minutes,revision):
    normalized=[message_ref(m) for m in messages if m.get('origin') in ('customer','staff')
                and not m.get('recalled')]
    normalized.sort(key=lambda m:(m['timestamp'],m['message_id']))
    identity=hashlib.sha256(json.dumps([account,thread_id,revision,normalized],
        ensure_ascii=False,sort_keys=True).encode()).hexdigest()
    return {'mode':'analysis_only','effects_allowed':False,'protocol':1,
            'groups':[{'account':account,'thread_id':thread_id,'conversation':conversation,
                'batch_id':identity,'revision':revision,'wait_minutes':wait_minutes,
                'messages':normalized,'complete':True,'state':'ready'}]}
