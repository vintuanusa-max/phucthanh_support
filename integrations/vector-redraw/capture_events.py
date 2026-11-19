"""Linux side: emit capture watermarks on SQLite journal commits. No timer or API calls."""
import ctypes
import os
import select
import sqlite3
import struct
import sys
from pathlib import Path

def watch(database):
    path=Path(database).resolve()
    libc=ctypes.CDLL(None,use_errno=True)
    fd=libc.inotify_init1(os.O_CLOEXEC|os.O_NONBLOCK)
    if fd<0:raise OSError(ctypes.get_errno(),"inotify_init1")
    # CLOSE_WRITE, MODIFY, MOVED_TO, CREATE and DELETE cover rollback and WAL modes.
    flags=0x8|0x2|0x80|0x100|0x200
    if libc.inotify_add_watch(fd,os.fsencode(path.parent),flags)<0:
        raise OSError(ctypes.get_errno(),"inotify_add_watch")
    names={os.fsencode(path.name+s) for s in ("","-journal","-wal")}
    def changed():
        relevant=False
        while True:
            try:buf=os.read(fd,65536)
            except BlockingIOError:return relevant
            pos=0
            while pos<len(buf):
                _,mask,_,length=struct.unpack_from("iIII",buf,pos)
                pos+=16
                name=buf[pos:pos+length].rstrip(b"\0");pos+=length
                if name in names or mask&0x4000:relevant=True
    last=-1
    try:
        with sqlite3.connect(path.as_uri()+"?mode=ro",uri=True,timeout=30) as db:
            while True:
                high=db.execute("select coalesce(max(rowid),0) from captures").fetchone()[0]
                if high!=last:
                    print(high,flush=True);last=high
                while True:
                    ready,_,_=select.select([fd,sys.stdin],[],[])
                    if sys.stdin in ready and not os.read(sys.stdin.fileno(),1):return
                    if changed():break
                # Coalesce bursts before querying. SQLite rereads only on a filesystem event.
                import time
                time.sleep(.15)
                changed()
    finally:os.close(fd)
if __name__=="__main__":watch(sys.argv[1])
