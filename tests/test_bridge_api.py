import json
from pathlib import Path
import queue
import tempfile
import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient
from erp_bridge import Bridge
from erp_bridge_api import build_router


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.token='only-test-token-'+'a'*40
        (self.root/'erp_config.json').write_text(json.dumps({'enabled':False,'token':self.token,'erp_url':'http://erp.invalid'}))
        self.bridge=Bridge(self.root,queue.Queue(),lambda *_:True,lambda *_:[])
        self.addCleanup(self.bridge.close)
        app=FastAPI()
        app.include_router(build_router(self.bridge))
        self.client=TestClient(app)
        self.headers={'X-Zalo-Token':self.token}
        self.path='/api/erp-integration'
        self.payload={'request_id':'r1','image_base64':'private-image','group_name':'Test - Nhóm','orders':[{'ma_san_pham':'Hình ABC','ten_mau':'Hình ABC','so_luong':3}]}
        with self.bridge.store.db() as db:
            db.execute("INSERT INTO intake(id,group_name,image,target_text,payload,state) VALUES (?,?,?,?,?,'failed')",
                       ('r1','Test - Nhóm',b'private-image','3 abc',json.dumps(self.payload)))

    def test_unauthorized_cannot_read_change_or_enable(self):
        for method,path,body in [('GET','/intake',None),('POST','/control',{'enabled':True}),('POST','/intake/r1/products',{'product_codes':['PET']})]:
            r=self.client.request(method,self.path+path,json=body)
            self.assertEqual(r.status_code,401)
        self.assertFalse(self.bridge.settings()['enabled'])

    def test_status_exposes_lines_but_no_token_or_image(self):
        r=self.client.get(self.path+'/intake',headers=self.headers)
        self.assertEqual(r.status_code,200)
        self.assertNotIn(self.token,r.text)
        self.assertNotIn('private-image',r.text)
        self.assertEqual(r.json()['items'][0]['lines'][0]['ten_mau'],'Hình ABC')

    def test_product_selection_keeps_message_id_and_design(self):
        r=self.client.post(self.path+'/intake/r1/products',headers=self.headers,json={'product_codes':['PET']})
        self.assertEqual(r.status_code,200)
        with self.bridge.store.db() as db: row=db.execute('SELECT * FROM intake').fetchone()
        self.assertEqual(row['state'],'ready')
        payload=json.loads(row['payload'])
        self.assertEqual(payload['request_id'],'r1')
        self.assertEqual(payload['orders'][0]['ma_san_pham'],'PET')
        self.assertEqual(payload['orders'][0]['ten_mau'],'Hình ABC')
        self.assertEqual(payload['image_base64'],'private-image')
        r=self.client.post(self.path+'/intake/r1/products',headers=self.headers,json={'product_codes':['PAPER']})
        self.assertEqual(r.status_code,409)

    def test_wrong_line_count_does_not_change_payload(self):
        r=self.client.post(self.path+'/intake/r1/products',headers=self.headers,json={'product_codes':['PET','PAPER']})
        self.assertEqual(r.status_code,422)
        with self.bridge.store.db() as db: row=db.execute('SELECT * FROM intake').fetchone()
        self.assertEqual(json.loads(row['payload']),self.payload)
        self.assertEqual(row['state'],'failed')

    def test_activation_preserves_scoped_credentials(self):
        r=self.client.post(self.path+'/control',headers=self.headers,json={'enabled':True})
        self.assertEqual(r.json(),{'enabled':True})
        cfg=self.bridge.settings()
        self.assertTrue(cfg['enabled'])
        self.assertEqual(cfg['token'],self.token)
        self.assertEqual(cfg['erp_url'],'http://erp.invalid')


if __name__=='__main__': unittest.main()
