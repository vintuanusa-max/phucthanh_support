import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import communication_policy as p

class PolicyTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/'config.json'
        self.original={'gemini_api_key':'test-secret','whatsapp_skip_groups':['WA only'],
                       'zalo_internal_members':['Nhân viên A'], 'zalo_skip_groups':['Nội bộ'],
                       'zalo_disable_reply_groups':['Khách A']}
        self.path.write_text(json.dumps(self.original),encoding='utf-8')
    def test_legacy_migration_and_secret_preservation(self):
        view=p.public_config(self.original)
        self.assertNotIn('test-secret',json.dumps(view))
        self.assertFalse(view['contacts'][0]['receive_messages'])
        self.assertTrue(view['contacts'][0]['auto_order'])
        view['contacts'][0]['receive_messages']=True
        saved=p.save(view,self.path)
        raw=p.read_raw(self.path)
        self.assertTrue(p.allowed(raw,'Khách A','receive_messages'))
        self.assertEqual(raw['gemini_api_key'],'test-secret')
        self.assertEqual(raw['whatsapp_skip_groups'],['WA only'])
        self.assertNotEqual(saved['revision'],view['revision'])
    def test_independent_receive_and_order_switches(self):
        cfg={'zalo_contact_rules':[{'name':'Khách A','receive_messages':False,'auto_order':True},
                                   {'name':'Khách B','receive_messages':True,'auto_order':False}]}
        self.assertFalse(p.allowed(cfg,'Khách A','receive_messages'))
        self.assertTrue(p.allowed(cfg,'Khách A','auto_order'))
        self.assertTrue(p.allowed(cfg,'Khách B','receive_messages'))
        self.assertFalse(p.allowed(cfg,'Khách B','auto_order'))
    def test_staff_skip_overrides_contact_and_defaults(self):
        for name in ['Nhân viên A','Nội bộ']:
            for action in ['receive_messages','auto_order']:
                self.assertFalse(p.allowed(self.original,name,action))
        self.assertFalse(p.is_internal(self.original,''))
        self.assertFalse(p.is_internal(self.original,'Nhân viên'))
        self.assertTrue(p.is_internal(self.original,'  NHÂN VIÊN A  '))
    def test_unlisted_default_and_exact_matching(self):
        cfg={'zalo_default_auto_order':False,'zalo_contact_rules':[{'name':'ABC','auto_order':True,'receive_messages':True}]}
        self.assertTrue(p.allowed(cfg,'abc','auto_order'))
        self.assertFalse(p.allowed(cfg,'ABC 2','auto_order'))
        self.assertFalse(p.allowed(cfg,'','auto_order'))
    def test_stale_revision_and_invalid_fields_do_not_write(self):
        view=p.public_config(self.original);p.save(view,self.path)
        before=self.path.read_bytes()
        with self.assertRaises(p.PolicyConflict):p.save(view,self.path)
        self.assertEqual(before,self.path.read_bytes())
        fresh=p.public_config(p.read_raw(self.path));fresh['gemini_api_key']='bad'
        with self.assertRaises(ValueError):p.save(fresh,self.path)
        self.assertEqual(before,self.path.read_bytes())
    def test_invalid_names_and_booleans(self):
        for rows in [[{'name':'','receive_messages':True,'auto_order':True}],
                     [{'name':'A','receive_messages':'false','auto_order':True}],
                     [{'name':'A','receive_messages':True,'auto_order':True},{'name':' a ','receive_messages':True,'auto_order':True}]]:
            view=p.public_config(self.original);view['contacts']=rows
            with self.assertRaises(ValueError):p.save(view,self.path)
        self.assertEqual(p.read_raw(self.path),self.original)
    def test_other_writer_lock_not_removed(self):
        lock=self.path.with_name('config.json.policy.lock');lock.write_text('other')
        with self.assertRaises(p.PolicyConflict):p.save(p.public_config(self.original),self.path)
        self.assertEqual(lock.read_text(),'other')
    def test_runtime_guard_stops_external_order_and_n8n(self):
        from core import integrations, intake
        def no_network(*args, **kwargs): raise AssertionError('network/ERP must not be called')
        with patch.object(integrations,'zalo_allowed',lambda *a:False), patch.object(integrations,'requests',Mock(post=no_network)):
            self.assertIsNone(integrations.forward_to_n8n('Customer','IMAGE','payload'))
        with patch.object(intake,'zalo_allowed',lambda *a:False), patch.object(intake.rt,'erp_bridge',Mock(capture=no_network)):
            self.assertIsNone(intake.process_extracted_screenshot_async('Customer','fake.png'))

class ApiTests(unittest.TestCase):
    def test_api_uses_only_safe_projection_and_conflict(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        import communication_api
        app=FastAPI();app.include_router(communication_api.router)
        with TestClient(app) as client,patch.object(p,'read_raw',return_value={'secret':'not-returned'}):
            res=client.get('/communication-config')
            self.assertEqual(res.status_code,200);self.assertNotIn('not-returned',res.text)
        with TestClient(app) as client,patch.object(p,'save',side_effect=p.PolicyConflict('changed')):
            self.assertEqual(client.post('/communication-config',json={}).status_code,409)

if __name__=='__main__':unittest.main()
