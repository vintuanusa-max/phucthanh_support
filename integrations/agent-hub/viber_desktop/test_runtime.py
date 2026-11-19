import importlib.util,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
s=importlib.util.spec_from_file_location('rt',Path(__file__).with_name('runtime.py'));rt=importlib.util.module_from_spec(s);s.loader.exec_module(rt)
class T(unittest.TestCase):
 def test_same_root_new_version(self):
  with tempfile.TemporaryDirectory() as d:
   b=Path(d);p=b/'v2'/'Viber.exe'
   self.assertEqual(rt.active_exe(b,[SimpleNamespace(info={'exe':str(p)})]),p)
 def test_foreign_not_selected(self):
  with tempfile.TemporaryDirectory() as d:self.assertIsNone(rt.active_exe(Path(d)/'Viber',[SimpleNamespace(info={'exe':str(Path(d)/'Other'/'Viber.exe')})]))
 def test_two_versions_block(self):
  with tempfile.TemporaryDirectory() as d:
   with self.assertRaises(RuntimeError):rt.active_exe(d,[SimpleNamespace(info={'exe':str(Path(d)/v/'Viber.exe')}) for v in ('v1','v2')])
 def test_closed(self):
  with tempfile.TemporaryDirectory() as d:self.assertIsNone(rt.active_exe(d,[]))
 def test_signature_changes(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d);(p/'plugins/sqldrivers').mkdir(parents=True)
   for n in ('Viber.exe','Qt6Core.dll','Qt6Sql.dll','plugins/sqldrivers/qsqlite.dll'):(p/n).write_bytes(b'a')
   old=rt.signature(p);(p/'Qt6Sql.dll').write_bytes(b'updated');self.assertNotEqual(old,rt.signature(p))
if __name__=='__main__':unittest.main()
