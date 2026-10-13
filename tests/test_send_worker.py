"""Execute the real worker function with a fake UI; importing channels starts no threads."""
from contextlib import nullcontext
import json
from pathlib import Path
import queue
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from channels import zalo_web
from erp_bridge import Bridge


class OneTask:
    def __init__(self, task): self.task=task
    def get(self):
        if self.task is None: raise StopIteration
        task,self.task=self.task,None
        return task
    def task_done(self): pass


class Element:
    def __init__(self, page, kind, name=None): self.page,self.kind,self.name=page,kind,name
    @property
    def first(self): return self
    def all(self): return [Element(self.page,'chat',x) for x in self.page.names]
    def evaluate(self,*args): return self.name
    def click(self,**kw):
        if self.name: self.page.header=self.name
    def inner_text(self,**kw):
        self.page.reads+=1
        if self.page.drift and self.page.reads>=3: return 'An Bình - Nội bộ'
        return self.page.header
    def fill(self,value,**kw): self.page.draft=value
    def press(self,key):
        if self.kind=='#richInput' and key=='Enter':
            self.page.sent.append((self.page.header,self.page.draft))
            if self.page.fail_enter: raise RuntimeError('simulated transport loss at Enter')
    def filter(self,**kw): return self
    def is_visible(self,**kw): return False


class Page:
    def __init__(self, drift=False, fail_enter=False):
        self.names=['An Bình - Nội bộ','An Bình - Đặt hàng']
        self.header='Previous chat'
        self.draft=''
        self.reads=0
        self.sent=[]
        self.drift=drift
        self.fail_enter=fail_enter
    def locator(self,kind): return Element(self,kind)
    def bring_to_front(self): pass


class WorkerTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        (self.root/'erp_config.json').write_text(json.dumps({'enabled':True}))
        self.bridge=Bridge(self.root,queue.Queue(),lambda *_:True,lambda *_:[])
        self.addCleanup(self.bridge.close)
        self.bridge.store.ingest({'id':'event1','group_name':'An Bình - Đặt hàng','message':'Xong hàng'})
        self.bridge.store.mark('event1','dispatched')

    def run_worker(self,page,policy=lambda *_:True):
        fakes={'send_queue':OneTask({'erp_event_id':'event1','customer_name':'An Bình - Đặt hàng','message':'Xong hàng'}),
            'rt':SimpleNamespace(erp_bridge=self.bridge,SYSTEM_STATUS='RUNNING',screenshot_active=0),
            'time':SimpleNamespace(sleep=lambda _:None),'zalo_allowed':policy,
            '_send_worker_busy':threading.Event(),'report_status_to_nas':lambda *a:None,
            'zalo_lock':nullcontext(),'_get_zalo_page':lambda:page,
            'name_match':lambda *_:True,'_tls':SimpleNamespace(),'print':lambda *a:None}
        with patch.multiple(zalo_web,create=True,**fakes):
            with self.assertRaises(StopIteration): zalo_web.send_zalo_worker()
        with self.bridge.store.db() as db:
            return db.execute('SELECT state FROM delivery').fetchone()[0]

    def test_same_prefix_different_suffix_selects_exact_recipient(self):
        page=Page()
        self.assertEqual(self.run_worker(page),'submitted')
        self.assertEqual(page.sent,[('An Bình - Đặt hàng','Xong hàng')])

    def test_header_changes_before_enter_never_sends(self):
        page=Page(drift=True)
        self.assertEqual(self.run_worker(page),'failed')
        self.assertEqual(page.sent,[])
        self.assertEqual(page.draft,'')

    def test_exception_at_enter_becomes_uncertain(self):
        page=Page(fail_enter=True)
        self.assertEqual(self.run_worker(page),'uncertain')
        self.assertEqual(len(page.sent),1)

    def test_disabled_group_blocks_without_gui(self):
        page=Page()
        self.assertEqual(self.run_worker(page,lambda *_:False),'blocked')
        self.assertEqual(page.reads,0)
        self.assertEqual(page.sent,[])

    def test_storage_failure_before_enter_never_sends(self):
        page=Page()
        original=self.bridge.store.mark
        def mark(event,state,detail=''):
            if state=='sending': raise OSError('disk full')
            original(event,state,detail)
        self.bridge.store.mark=mark
        self.assertEqual(self.run_worker(page),'failed')
        self.assertEqual(page.sent,[])

    def test_storage_failure_after_enter_never_retries(self):
        page=Page()
        original=self.bridge.store.mark
        def mark(event,state,detail=''):
            if state=='submitted': raise OSError('disk full')
            original(event,state,detail)
        self.bridge.store.mark=mark
        self.assertEqual(self.run_worker(page),'uncertain')
        self.assertEqual(len(page.sent),1)


if __name__=='__main__': unittest.main()
