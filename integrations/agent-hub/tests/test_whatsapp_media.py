import base64
import hashlib
import hmac

import pytest
from cryptography.hazmat.primitives import hashes, padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from whatsapp_desktop.media import decrypt, fetch


def fixture():
    raw=b'An image payload for integrity testing'
    key=b'k'*32
    keys=HKDF(algorithm=hashes.SHA256(),length=112,salt=None,info=b'WhatsApp Image Keys').derive(key)
    pad=padding.PKCS7(128).padder(); padded=pad.update(raw)+pad.finalize()
    enc=Cipher(algorithms.AES(keys[16:48]),modes.CBC(keys[:16])).encryptor()
    cipher=enc.update(padded)+enc.finalize()
    data=cipher+hmac.new(keys[48:80],keys[:16]+cipher,hashlib.sha256).digest()[:10]
    enc64=lambda x:base64.b64encode(x).decode()
    meta=dict(type='image',mediaKey=enc64(key),filehash=enc64(hashlib.sha256(raw).digest()),encFilehash=enc64(hashlib.sha256(data).digest()),size=len(raw))
    return raw,data,meta


def test_roundtrip_and_tamper():
    raw,data,meta=fixture()
    assert decrypt(data,meta)==raw
    with pytest.raises(ValueError):decrypt(data[:-1]+bytes([data[-1]^1]),meta)
    meta['filehash']=base64.b64encode(b'x'*32).decode()
    with pytest.raises(ValueError):decrypt(data,meta)


def test_view_once_and_untrusted_host_never_download():
    _,data,meta=fixture()
    with pytest.raises(ValueError):decrypt(data,{**meta,'isViewOnce':True})
    with pytest.raises(ValueError):fetch({**meta,'deprecatedMms3Url':'http://127.0.0.1/private'})
