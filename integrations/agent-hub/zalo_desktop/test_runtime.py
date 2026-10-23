import importlib.util,unittest
from types import SimpleNamespace
from pathlib import Path
spec=importlib.util.spec_from_file_location('rt',Path(__file__).with_name('runtime.py'));rt=importlib.util.module_from_spec(spec);spec.loader.exec_module(rt)
OLD=r'C:\Users\Admin\AppData\Local\Programs\Zalo\Zalo-26.10.11\Zalo.exe'
NEW=OLD.replace('26.10.11','26.10.20')
def p(exe,pid=1,args=None):return SimpleNamespace(info={'exe':exe,'pid':pid,'cmdline':args or [exe]})
class Tests(unittest.TestCase):
 def test_upgrade(self):self.assertEqual(rt.select_session(OLD,[p(NEW)])[1],NEW)
 def test_child_ignored(self):self.assertEqual(rt.select_session(OLD,[p(NEW),p(NEW,2,['Zalo.exe','--type=renderer'])])[0][1],1)
 def test_closed(self):self.assertIsNone(rt.select_session(OLD,[]))
 def test_foreign(self):self.assertIsNone(rt.select_session(OLD,[p(r'C:\Temp\Zalo-26.10.20\Zalo.exe')]))
 def test_ambiguous(self):self.assertIsNone(rt.select_session(OLD,[p(NEW),p(OLD,2)]))
 def test_pid_change(self):self.assertNotEqual(rt.select_session(OLD,[p(NEW)])[0],rt.select_session(OLD,[p(NEW,2)])[0])
if __name__=='__main__':unittest.main()
