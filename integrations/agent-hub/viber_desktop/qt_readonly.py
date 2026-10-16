"""Own-process Qt SQL adapter. Never loads code into or writes to Viber."""
import ctypes as C,os
from pathlib import Path
P=C.c_void_p
class QtSql:
 def __init__(self):
  self.root=Path(os.environ['LOCALAPPDATA'])/'Viber';self.directory=os.add_dll_directory(str(self.root));self.core=C.CDLL(str(self.root/'Qt6Core.dll'));self.sql=C.CDLL(str(self.root/'Qt6Sql.dll'));self.keep=[]
  self.argc=C.c_int(1);self.argv=(C.c_char_p*2)(b'PhucThanhViberReadOnly',None);self.app=C.create_string_buffer(4096)
  self.fn(self.core,'??0QCoreApplication@@QEAA@AEAHPEAPEADH@Z',None,[P,P,P,C.c_int])(self.app,C.byref(self.argc),self.argv,0x060b02)
  self.fn(self.core,'?addLibraryPath@QCoreApplication@@SAXAEBVQString@@@Z',None,[P])(self.string(str(self.root/'plugins')))
  self.db=C.create_string_buffer(64)
  self.fn(self.sql,'?addDatabase@QSqlDatabase@@SA?AV1@AEBVQString@@0@Z',P,[P,P,P])(self.db,self.string('QSQLITE'),self.string('pt-readonly'))
 def fn(self,dll,name,restype,args):
  f=getattr(dll,name);f.restype=restype;f.argtypes=args;return f
 def string(self,text):
  out=C.create_string_buffer(24);data=text.encode('utf-16-le');raw=C.create_string_buffer(data+b'\0\0')
  self.fn(self.core,'?fromUtf16@QString@@SA?AV1@PEB_S_J@Z',P,[P,P,C.c_int64])(out,raw,len(data)//2);self.keep.append(out);return out
 def release_strings(self):
  for value in self.keep:self.fn(self.core,'?clear@QString@@QEAAXXZ',None,[P])(value)
  self.keep.clear()
 def close(self):
  self.fn(self.sql,'?close@QSqlDatabase@@QEAAXXZ',None,[P])(self.db)
 def open(self,path):
  self.fn(self.sql,'?close@QSqlDatabase@@QEAAXXZ',None,[P])(self.db)
  self.fn(self.sql,'?setConnectOptions@QSqlDatabase@@QEAAXAEBVQString@@@Z',None,[P,P])(self.db,self.string('QSQLITE_OPEN_READONLY'))
  self.fn(self.sql,'?setDatabaseName@QSqlDatabase@@QEAAXAEBVQString@@@Z',None,[P,P])(self.db,self.string(str(path)))
  return self.fn(self.sql,'?open@QSqlDatabase@@QEAA_NXZ',C.c_bool,[P])(self.db)
 def query(self,text,columns=1,limit=100):
  q=C.create_string_buffer(64);self.fn(self.sql,'??0QSqlQuery@@QEAA@AEBVQSqlDatabase@@@Z',None,[P,P])(q,self.db)
  try:
   ok=self.fn(self.sql,'?exec@QSqlQuery@@QEAA_NAEBVQString@@@Z',C.c_bool,[P,P])(q,self.string(text))
   if not ok:return None
   rows=[]
   while len(rows)<limit and self.fn(self.sql,'?next@QSqlQuery@@QEAA_NXZ',C.c_bool,[P])(q):
    row=[]
    for i in range(columns):
     v=C.create_string_buffer(64);s=C.create_string_buffer(24)
     self.fn(self.sql,'?value@QSqlQuery@@QEBA?AVQVariant@@H@Z',P,[P,P,C.c_int])(q,v,i)
     self.fn(self.core,'?toString@QVariant@@QEBA?AVQString@@XZ',P,[P,P])(v,s)
     ptr=C.c_void_p.from_buffer(s,8).value;size=C.c_int64.from_buffer(s,16).value
     if not 0<=size<=200000:raise RuntimeError('Unsupported QString layout')
     row.append(C.string_at(ptr,size*2).decode('utf-16-le') if ptr and size else '')
     self.fn(self.core,'??1QVariant@@QEAA@XZ',None,[P])(v)
     self.keep.append(s)
    rows.append(row)
   return rows
  finally:
   self.fn(self.sql,'??1QSqlQuery@@QEAA@XZ',None,[P])(q)
   self.release_strings()
