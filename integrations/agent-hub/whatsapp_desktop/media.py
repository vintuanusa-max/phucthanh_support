"""Fetch authenticated WhatsApp media; never persist media keys or signed URLs.

Wire format reference: Baileys src/Utils/messages-media.ts (HKDF/AES/HMAC).
"""
import base64
import hashlib
import hmac
import json
from datetime import datetime
from urllib.parse import urlsplit

import httpx
from cryptography.hazmat.primitives import hashes, padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from zalo_desktop.media import normalize_image
from zalo_desktop.vault import safe_name

LIMIT = 50 * 1024 * 1024


def decrypt(data, meta):
    if len(data) < 26 or len(data) > LIMIT + 1024:
        raise ValueError('Media size invalid')
    kind = {'image': 'Image', 'document': 'Document'}.get(meta.get('type'))
    if not kind or meta.get('isViewOnce'):
        raise ValueError('Unsupported media')
    def decoded(name):
        value = base64.b64decode(meta[name], validate=True)
        if len(value) != 32:
            raise ValueError('Invalid media metadata')
        return value
    if not hmac.compare_digest(hashlib.sha256(data).digest(), decoded('encFilehash')):
        raise ValueError('Encrypted hash mismatch')
    keys = HKDF(algorithm=hashes.SHA256(), length=112, salt=None,
                info=f'WhatsApp {kind} Keys'.encode()).derive(decoded('mediaKey'))
    cipher, tag = data[:-10], data[-10:]
    if not hmac.compare_digest(hmac.new(keys[48:80], keys[:16] + cipher, hashlib.sha256).digest()[:10], tag):
        raise ValueError('Media authentication failed')
    ctx = Cipher(algorithms.AES(keys[16:48]), modes.CBC(keys[:16])).decryptor()
    padded = ctx.update(cipher) + ctx.finalize()
    unpad = padding.PKCS7(128).unpadder()
    raw = unpad.update(padded) + unpad.finalize()
    if not hmac.compare_digest(hashlib.sha256(raw).digest(), decoded('filehash')):
        raise ValueError('Plaintext hash mismatch')
    if meta.get('size') != len(raw):
        raise ValueError('Media length mismatch')
    return raw


def fetch(meta):
    if meta.get('isViewOnce') or meta.get('type') not in ('image', 'document'):
        raise ValueError('Unsupported media')
    if not isinstance(meta.get('size'), (int, float)) or not 0 < meta['size'] <= LIMIT:
        raise ValueError('Media size limit')
    url = meta.get('deprecatedMms3Url')
    if not isinstance(url, str) or not url:
        path = meta.get('directPath')
        if not isinstance(path, str) or not path.startswith('/') or path.startswith('//'):
            raise ValueError('Invalid media path')
        url = 'https://mmg.whatsapp.net' + path
    u = urlsplit(url)
    if u.scheme != 'https' or u.hostname != 'mmg.whatsapp.net' or u.port not in (None,443) or u.username or u.password:
        raise ValueError('Unsupported media host')
    with httpx.Client(timeout=30, follow_redirects=False, trust_env=False) as client:
        with client.stream('GET', url) as response:
            if response.status_code != 200:
                raise ValueError('Media unavailable')
            data = bytearray()
            for chunk in response.iter_bytes(65536):
                data.extend(chunk)
                if len(data) > LIMIT + 1024:
                    raise ValueError('Download size limit')
    return decrypt(bytes(data), meta)


def enrich(message, meta, vault):
    raw = fetch(meta)
    digest = hashlib.sha256(raw).hexdigest()
    asset_id = hashlib.sha256((message['account']+'\0'+message['message_id']).encode()).hexdigest()
    kind = meta['type']
    mime = meta.get('mimetype') if isinstance(meta.get('mimetype'),str) else 'application/octet-stream'
    image = normalize_image(raw) if kind == 'image' and len(raw) <= 4*1024*1024 else None
    suffix = {'image/jpeg':'.jpg','image/png':'.png','image/webp':'.webp'}.get(mime, '.bin')
    name = safe_name(meta.get('filename') if isinstance(meta.get('filename'),str) else 'WhatsApp'+suffix)
    relative = '/'.join((vault.folder(message),datetime.fromtimestamp(message['timestamp']).strftime('%Y-%m'),'originals',asset_id[:12]+'__'+name))
    destination = vault.root / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    if not destination.exists():
        temporary = destination.with_name(destination.name+'.part')
        temporary.write_bytes(raw)
        temporary.replace(destination)
    if hashlib.sha256(destination.read_bytes()).hexdigest() != digest:
        raise ValueError('NAS hash mismatch')
    asset = dict(id=asset_id,name=name,kind='image' if kind=='image' else 'file',state='ready',relative_path=relative,sha256=digest,size=len(raw),mime_type=mime)
    manifest = destination.with_name(destination.name+'.source.json')
    manifest.write_text(json.dumps({**{k:message[k] for k in ('account','thread_id','message_id','sender','timestamp','text')},**asset},ensure_ascii=False,indent=2),encoding='utf-8')
    message['assets']=[asset]
    message['images']=[image] if image else []
    message['attachments']=[] if image else ['whatsapp-desktop:file-requires-review']
    if message['text'] == '[WhatsApp: nội dung/đính kèm cần kiểm tra trên ứng dụng]':
        message['attachments'].append('whatsapp-desktop:caption-unverified')
    return message
