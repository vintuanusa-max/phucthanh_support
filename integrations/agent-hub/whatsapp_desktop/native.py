"""Read-only in-memory format probe. Prints schema only, never keys or row contents.
Protocol reference: kraftdenker/ZAPiXDESK (GPL-3.0); independently implemented probe.
"""
import ctypes as C,hashlib,sqlite3,struct
from pathlib import Path
from zalo_desktop.codec import snapshot, committed_frames
from cryptography.hazmat.primitives.ciphers import Cipher,algorithms,modes
from cryptography.hazmat.decrepit.ciphers.modes import OFB
root=Path.home()/'AppData/Local/Packages/5319275A.WhatsAppDesktop_cv1g1gvanyjgm/LocalState'
static=bytes.fromhex('23a7f19c11e5bd784235c96f85d24913')
def session_secret():
 n=C.WinDLL('ncrypt');h=C.c_void_p();out=C.c_void_p();size=C.c_ulong()
 n.NCryptCreateProtectionDescriptor.argtypes=[C.c_wchar_p,C.c_ulong,C.POINTER(C.c_void_p)]
 n.NCryptProtectSecret.argtypes=[C.c_void_p,C.c_ulong,C.c_void_p,C.c_ulong,C.c_void_p,C.c_void_p,C.POINTER(C.c_void_p),C.POINTER(C.c_ulong)]
 n.NCryptCloseProtectionDescriptor.argtypes=[C.c_void_p]
 assert n.NCryptCreateProtectionDescriptor('LOCAL=user',0,C.byref(h))==0
 try:
  assert n.NCryptProtectSecret(h,0,static,len(static),None,None,C.byref(out),C.byref(size))==0
  return C.string_at(out,32)
 finally:
  C.WinDLL('kernel32').LocalFree.argtypes=[C.c_void_p];C.WinDLL('kernel32').LocalFree(out);n.NCryptCloseProtectionDescriptor(h)
def page(data,key,num):
 d=Cipher(algorithms.AES(key),OFB(struct.pack('<I',num)+data[-12:])).decryptor().update(data)
 return d[:16]+data[16:24]+d[24:] if num==1 else d
def frames(path,key):
 raw=Path(str(path)+'-wal').read_bytes();assert struct.unpack('>I',raw[8:12])[0]==4096
 result=[]
 for off in range(32,len(raw)-4119,4120):
  num,commit=struct.unpack('>II',raw[off:off+8]);result.append((num,commit,page(raw[off+24:off+4120],key,num)))
 return result
def open_db(path,key):
 raw,wal,_=snapshot(path)
 committed,count=committed_frames(wal)
 count=count or len(raw)//4096
 data=bytearray()
 for num in range(1,count+1):
  data.extend(page(committed.get(num,raw[(num-1)*4096:num*4096]),key,num))
 assert data[:16]==b'SQLite format 3\0'
 data[18:20]=b'\1\1';d=sqlite3.connect(':memory:');d.deserialize(bytes(data))
 d.execute('PRAGMA query_only=ON');d.execute('PRAGMA trusted_schema=OFF')
 assert d.execute('PRAGMA quick_check').fetchone()[0]=='ok'
 return d

def active_session():
 session=open_db(root/'session.db',session_secret())
 candidates=[]
 for (ck,) in session.execute('SELECT clientKey FROM session_accounts ORDER BY lastActiveTimestamp'):
  folder=root/'sessions'/hashlib.sha1(ck).hexdigest().upper()
  if folder.exists():candidates.append((ck,folder))
 session.close()
 if len(candidates)!=1:raise ValueError('Exactly one active WhatsApp session required')
 return candidates[0]

def session_identity():
 ck,_=active_session()
 return hashlib.sha256(ck).hexdigest()

def text_database(name='genericStorage.db', key_slot=1):
 if (name,key_slot) not in {('genericStorage.db',1),('mediaDownloads.db',2),('contacts.db',2)}:
  raise ValueError('Unsupported database')
 ck,folder=active_session()
 f=C.WinDLL('clipc').GetOfflineDeviceUniqueID
 f.argtypes=[C.c_ulong,C.c_void_p,C.POINTER(C.c_ulong),C.POINTER(C.c_ulong),C.c_void_p,C.c_ulong,C.c_ulong]
 salt='cv1g1gv'.encode('utf-16le');method=C.c_ulong();size=C.c_ulong(32);buf=C.create_string_buffer(32)
 assert f(len(salt),salt,C.byref(method),C.byref(size),buf,0,0)==0
 aux=hashlib.pbkdf2_hmac('sha256',ck,buf.raw,10000,32);iv=hashlib.pbkdf2_hmac('sha256',aux,buf.raw,10000,16)
 nk=Cipher(algorithms.AES(aux),modes.CBC(iv)).encryptor().update(static+bytes([16])*16)
 native=open_db(folder/'nativeSettings.db',nk)
 key=native.execute('SELECT value FROM settings WHERE key=?',(key_slot,)).fetchone()[0];native.close()
 return open_db(folder/name,key)
