import hashlib
import importlib.util
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unicodedata import normalize

from hub.approval_names import NEO_THREADS, approved_jpg_name
from hub.llm_copy import files_for, valid_paths
from hub.output_names import is_neo_group, llm_copy_filename, short_output_stem
from hub.pet_render import code_name

WORKER_DIR = Path(r'C:\Users\Admin\AppData\Local\PhucThanh\ArtworkInspector')
if not WORKER_DIR.is_dir():
    WORKER_DIR = Path(__file__).resolve().parents[4] / 'phucthanh_support' / 'integrations' / 'system-monitor' / 'artwork-worker'


def _load_worker_module(name, filename):
    path = WORKER_DIR / filename
    if not path.is_file():
        return None
    if str(WORKER_DIR) not in sys.path:
        sys.path.insert(0, str(WORKER_DIR))
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class OutputNamesTests(unittest.TestCase):
    def test_neo_group_threads_and_folders(self):
        self.assertIn('g5402324928935037742', NEO_THREADS)
        self.assertIn('g3427098896227768665', NEO_THREADS)
        self.assertIn('g7815994588016353953', NEO_THREADS)
        self.assertTrue(is_neo_group(group='AN NGUYEN'))
        self.assertTrue(is_neo_group(group='INJAE'))
        self.assertTrue(is_neo_group(group='A CHAU'))
        self.assertTrue(is_neo_group(group='A CHÂU'))
        self.assertFalse(is_neo_group(group='CANAVI'))
        self.assertFalse(is_neo_group(group='KIM OANH'))

    def test_short_output_stem_examples(self):
        self.assertEqual(short_output_stem('FileinPETTB3VB-IBD11_position_1'), 'TB3VB-IBD11_P1')
        self.assertEqual(short_output_stem('FILEINPETTB3VD-KEMNGHIA11_position_2'), 'TB3VD-KEMNGHIA11_P2')
        self.assertEqual(short_output_stem('MK - NÓN LƯỠI TRAI - AHA SANTA RUN.pdf'), 'AHA_SANTA_RUN')
        self.assertEqual(
            short_output_stem('RD26CP ALL STYLES ARTWORK merged _compressed (1)-trang.pdf'),
            'RD26CP_ALL_STYLES_ARTWORK',
        )
        vai = short_output_stem('In_Vai_in_1m3_vs_70cm_-_chop_D45_H36_-_Hoa_van_moi')
        self.assertEqual(vai, '1m3_vs_70cm_chop_D45_H36_Hoa_van')
        self.assertLessEqual(len(vai), 32)
        self.assertEqual(short_output_stem('CON'), 'FILE_CON')
        self.assertEqual(code_name('MK - NÓN LƯỠI TRAI - AHA SANTA RUN'), 'AHA_SANTA_RUN')

    def test_llm_copy_filename_rules(self):
        # TIFF gets _LLM suffix without NEO_
        self.assertEqual(
            llm_copy_filename(
                'MK-NONLUOITRAI-AHASANTARUN_front',
                '.tiff',
                group='KIM OANH',
                source_name='MK - NÓN LƯỠI TRAI - AHA SANTA RUN.pdf',
            ),
            'AHA_SANTA_RUN_front_LLM.tiff',
        )
        self.assertEqual(
            llm_copy_filename(
                'FileinPETTB3VB-IBD11_position_1',
                '.tiff',
                group='CANAVI HCM2',
                source_name='File in PET TB3VB-IBD.11.ai',
            ),
            'TB3VB-IBD.11_P1_LLM.tiff',
        )
        # NEO groups get NEO_ prefix for JPGs and _LLM suffix
        self.assertEqual(
            llm_copy_filename(
                'In_Vai_in_1m3_vs_70cm_-_chop_D45_H36_-_Hoa_van_moi',
                '.jpg',
                group='AN NGUYEN',
                thread_id='g5402324928935037742',
            ),
            'NEO_1m3_vs_70cm_chop_D45_H36_Hoa_van_LLM.jpg',
        )
        self.assertEqual(
            llm_copy_filename('n268_ht', '.jpg', group='INJAE', thread_id='g3427098896227768665'),
            'NEO_n268_ht_LLM.jpg',
        )
        self.assertEqual(
            llm_copy_filename(
                'RD26CP_ALL_STYLES_ARTWORK_merged_compressed_1-trang',
                '.jpg',
                group='A CHAU',
                thread_id='g7815994588016353953',
                source_name='RD26CP ALL STYLES ARTWORK merged _compressed (1)-trang.pdf',
            ),
            'NEO_RD26CP_ALL_STYLES_ARTWORK_LLM.jpg',
        )
        # Never duplicate NEO_ or _LLM
        self.assertEqual(
            llm_copy_filename('NEO_MSP1796_CAMO_LLM', '.jpg', group='A CHAU'),
            'NEO_MSP1796_CAMO_LLM.jpg',
        )
        # Non-NEO JPG keeps _LLM only
        self.assertEqual(
            llm_copy_filename('TB3VB-SBUS3.11_position_1', '.jpg', group='CANAVI'),
            'TB3VB-SBUS3.11_P1_LLM.jpg',
        )

    def test_approved_jpg_name_includes_achau_and_short_stem(self):
        self.assertEqual(
            approved_jpg_name('RD26CP ALL STYLES ARTWORK merged _compressed (1)-trang.pdf', 'g7815994588016353953'),
            'NEO_RD26CP_ALL_STYLES_ARTWORK.jpg',
        )
        self.assertEqual(
            approved_jpg_name('File in CN TB3VB-SBUS3.11.ai', 'g999', 'front', multiple=True),
            'MNT_TB3VB-SBUS3.11_front.jpg',
        )

    def test_files_for_valid_paths_and_worker_copy(self):
        sha = hashlib.sha256(b'fake-jpg-bytes').hexdigest()
        payload = {
            'archive_relative': 'A CHAU/DESIGNER/RD26CP/REVIEW-20261127-1234',
            'source': {
                'thread_id': 'g7815994588016353953',
                'asset': {'name': 'RD26CP ALL STYLES ARTWORK merged _compressed (1)-trang.pdf'},
            },
            'report': {
                'panels': [{'file': 'RD26CP_ALL_STYLES_ARTWORK_page_1.jpg', 'sha256': sha}],
            },
        }
        files = files_for('jpg_exports', payload)
        self.assertEqual(len(files), 1)
        self.assertEqual(files[0]['name'], 'NEO_RD26CP_ALL_STYLES_ARTWORK_P1_LLM.jpg')
        self.assertTrue(valid_paths(files, [f"A CHAU/{files[0]['name']}"]))
        self.assertTrue(valid_paths(files, [f"A CHAU/NEO_RD26CP_ALL_STYLES_ARTWORK_P1_LLM2.jpg"]))

        worker_mod = _load_worker_module('llm_copy_worker_test', 'llm_copy_worker.py')
        if worker_mod is not None:
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                src = root / files[0]['source']
                src.parent.mkdir(parents=True, exist_ok=True)
                src.write_bytes(b'fake-jpg-bytes')
                copied = worker_mod.copy_files(root, files)
                self.assertEqual(copied, ['A CHAU/NEO_RD26CP_ALL_STYLES_ARTWORK_P1_LLM.jpg'])
                self.assertTrue((root / copied[0]).is_file())
                # Worker rejects NEO folder JPG without NEO_ prefix
                bad = [dict(files[0], name='RD26CP_ALL_STYLES_ARTWORK_P1_LLM.jpg')]
                with self.assertRaises(ValueError):
                    worker_mod.copy_files(root, bad)

    def test_files_for_dedups_colliding_panel_names(self):
        sha1 = hashlib.sha256(b'a').hexdigest()
        sha2 = hashlib.sha256(b'b').hexdigest()
        payload = {
            'archive_relative': 'KIM OANH/DESIGNER/M1/versions/v1',
            'reports': [
                {'name': 'VERY_LONG_IDENTICAL_MODEL_CODE_NAME_A.tiff', 'sha256': sha1},
                {'name': 'VERY_LONG_IDENTICAL_MODEL_CODE_NAME_B.tiff', 'sha256': sha2},
            ],
        }
        # Force long prefix so truncation collides before suffix; ensure unique names returned
        payload['reports'] = [
            {'name': 'ALPHA_BETA_GAMMA_DELTA_EPSILON_ZETA_ETA_1.tiff', 'sha256': sha1},
            {'name': 'ALPHA_BETA_GAMMA_DELTA_EPSILON_ZETA_ETA_2.tiff', 'sha256': sha2},
        ]
        files = files_for('pet_exports', payload)
        names = [f['name'] for f in files]
        self.assertEqual(len(set(names)), 2)
        self.assertTrue(all(n.endswith('_LLM.tiff') for n in names))


class DailyBugFixTests(unittest.TestCase):
    def test_vemau_regex_allows_natural_urgent_sample_phrase(self):
        _norm = lambda s: re.sub(
            r'[\u0300-\u036f]', '', normalize('NFKD', (s or '').replace('đ', 'd').replace('Đ', 'D'))
        ).lower()
        pat = re.compile(r'\b(?:(?:len|lam|in|ra|ve)(?:\s+[a-z0-9]+){0,5}\s+mau|ve\s+lai|lam\s+ro\s+net)\b')
        for phrase in (
            'mai làm gấp mẫu này cho em',
            'làm nhanh mẫu này giúp anh',
            'lên lại giúp 1 cái mẫu',
            'in test mẫu này trước',
        ):
            self.assertIsNotNone(pat.search(_norm(phrase)), phrase)
        self.assertIsNone(pat.search(_norm('báo giá áo này bao nhiêu')))

    def test_order_intake_analyze_vemau_end_to_end(self):
        import sys
        import time
        from unittest.mock import patch

        tests_dir = str(Path(__file__).resolve().parent)
        if tests_dir not in sys.path:
            sys.path.insert(0, tests_dir)
        from test_hub import setup as hub_setup
        from hub.models import Capture, IntakeDecision

        with tempfile.TemporaryDirectory() as tmp:
            t = Path(tmp)
            s, store, engine = hub_setup.__wrapped__(t)
            s.inboxes['wa-1'].update(
                channel='zalo',
                capture_enabled=True,
                archive_root=str(t / 'archive'),
                order_intake={'enabled_after': time.time() - 3600},
            )
            s.erp_write = True
            store.bind('wa-1', 'g4766322565399535347', 'KIM OANH-IN NÓN', 10, 45)
            engine.erp.observe_group = lambda name: None
            engine.erp.validate_customer_id = lambda cid: None
            engine.order_intake.sync_policy('wa-1', {'zalo_internal_members': ['Nhân viên']})
            engine.order_intake.resolve_customer_binding = lambda r, g: {'customer_id': 'CUST_KO', 'customer_name': 'KIM OANH'}
            cap = Capture(
                account='wa-1',
                thread_id='g4766322565399535347',
                message_id='m_vemau_1',
                sender='Kim Oanh',
                display_name='KIM OANH-IN NÓN',
                text='mai làm gấp mẫu này cho em',
                timestamp=time.time() - 2500,
            )
            m = store.capture(cap)
            store.finish(m, 'done')
            run_id = 'run-vemau-1'
            payload = {
                'messages': ['m_vemau_1'],
                'group_name': 'KIM OANH-IN NÓN',
                'sender': 'Kim Oanh',
                'sender_key': 'k1',
                'unified_intake': True,
            }
            with store.db() as d:
                d.execute(
                    "INSERT INTO intake_runs(id,account,thread_id,conversation,state,payload,result,created) VALUES(?,?,?,?,?,?,?,?)",
                    (run_id, 'wa-1', 'g4766322565399535347', 45, 'queued', json.dumps(payload), '{}', time.time()),
                )
            run = dict(id=run_id, account='wa-1', thread_id='g4766322565399535347', conversation=45, payload=json.dumps(payload))
            msgs = [(1, cap.model_dump(mode='json'))]
            dec = IntakeDecision(
                action='draft_order',
                source_message_ids=[1],
                orders=[{'ma_san_pham': 'VEMAU', 'ten_mau': 'Mẫu nón 333TPTrade', 'so_luong': 2, 'ghi_chu_mau_do': 'Gấp'}],
            )
            with patch('hub.drive_order_brief.collect_drive_order', return_value=None):
                engine.order_intake.analyze(run, payload, msgs, agent_decision=dec)
            with store.db() as d:
                row = d.execute('SELECT state FROM intake_runs WHERE id=?', (run_id,)).fetchone()
            self.assertEqual(row['state'], 'awaiting_evidence')

            dec_bad = IntakeDecision(
                action='draft_order',
                source_message_ids=[1],
                orders=[{'ma_san_pham': 'XYZ999', 'ten_mau': 'Fake', 'so_luong': 2}],
            )
            with self.assertRaisesRegex(ValueError, 'Product code is not present in source text'):
                engine.order_intake.analyze(run, payload, msgs, agent_decision=dec_bad)

    def test_untagged_pure_cmyk_pdf_export(self):
        try:
            import pymupdf as fitz
        except ImportError:
            self.skipTest('pymupdf not installed in this python interpreter')
        mod = _load_worker_module('original_pdf_export_test', 'original_pdf_export.py')
        if mod is None:
            self.skipTest('original_pdf_export.py not found')
        with tempfile.TemporaryDirectory() as tmp:
            t = Path(tmp)
            pdf = t / 'untagged.pdf'
            doc = fitz.open()
            page = doc.new_page(width=200, height=100)
            page.draw_rect(fitz.Rect(10, 10, 190, 90), fill=(0.2, 0.4, 0.6))
            doc.save(pdf)
            doc.close()
            out_dir = t / 'out'
            out_dir.mkdir()
            job = {
                'archive_relative': 'INJAE/DESIGNER/n268_ht/REVIEW-1',
                'plan': {
                    'order_code': 'n268 ht',
                    'source_kind': 'pdf',
                    'panels': [{'name': 'page_1', 'output_cm': [200 * 2.54 / 72, 100 * 2.54 / 72]}],
                },
            }
            res = mod.export(job, pdf, out_dir)
            rep = res['report']
            self.assertIsNone(rep['icc_sha256'])
            self.assertTrue(rep['panels'][0]['untagged_source'])
            self.assertFalse(rep['panels'][0]['source_icc_preserved'])
            self.assertEqual(rep['panels'][0]['mode'], 'CMYK')

    def test_native_selection_result_clears_stale_error_on_success(self):
        import io
        import time
        from PIL import Image

        tests_dir = str(Path(__file__).resolve().parent)
        if tests_dir not in sys.path:
            sys.path.insert(0, tests_dir)
        from test_hub import setup as hub_setup
        from hub import native_selection as ns

        with tempfile.TemporaryDirectory() as tmp:
            t = Path(tmp)
            _, store, engine = hub_setup.__wrapped__(t)
            ns.init(engine)
            sha = hashlib.sha256(b'ai-bytes').hexdigest()
            sid = 'sel-stale-err-1'
            im = Image.new('RGBA', (118, 118), (0, 0, 0, 0))
            for x in range(20, 100):
                for y in range(20, 100):
                    im.putpixel((x, y), (10, 20, 30, 255))
            buf = io.BytesIO()
            im.save(buf, format='PNG', dpi=(300, 300))
            png_b64 = __import__('base64').b64encode(buf.getvalue()).decode()

            payload = {
                'brief_id': 'brief-1',
                'conversation': 10,
                'thread_id': 'g123',
                'asset': {'name': 'MauTest.ai', 'sha256': sha, 'relative_path': 'KIM OANH/2026-11/MauTest.ai'},
                'side': 'position_1',
                'candidate_ids': ['0.1'],
                'candidates': [{'id': '0.1', 'bounds': [0, 100, 100, 0]}],
                'width_cm': 1.0,
                'note': 'Artwork test stale error clear',
                'font_warnings': [],
                'error': 'Kết quả Illustrator không hợp lệ: Không ghi đè kết quả khác',
            }
            engine.artwork_checks.pet.workflow.current = lambda bid, p=None: True
            with store.db() as d:
                d.execute(
                    "INSERT INTO native_selections VALUES(?,?,?,?,?,?)",
                    (sid, 'brief-1', 'wa-1', 'render_running', json.dumps(payload), time.time()),
                )
            res = ns.result(engine, 'wa-1', sid, {'png': png_b64})
            self.assertEqual(res['state'], 'png_ready')
            with store.db() as d:
                row = d.execute('SELECT state, payload FROM native_selections WHERE id=?', (sid,)).fetchone()
            self.assertEqual(row['state'], 'png_ready')
            saved = json.loads(row['payload'])
            self.assertNotIn('error', saved)

    def test_fast_worker_lock_check_and_state_write_resilience(self):
        from unittest.mock import patch

        mod = _load_worker_module('fast_worker_test', 'fast_worker.py')
        if mod is None:
            self.skipTest('fast_worker.py not found')
        with tempfile.TemporaryDirectory() as tmp:
            state_path = Path(tmp) / 'approval-state.json'
            state_path.write_text('{"time": 0}', encoding='utf-8')
            old_t = 1000.0
            import os
            os.utime(state_path, (old_t, old_t))
            with patch.object(mod, 'STATE', state_path), patch.object(mod, '_lock_held', return_value=False), patch.object(mod.subprocess, 'Popen') as popen:
                mod.ensure_started(['cfg1.json'])
                popen.assert_called_once()
            with patch.object(mod, 'STATE', state_path), patch.object(mod, '_lock_held', return_value=True), patch.object(mod.subprocess, 'Popen') as popen:
                mod.ensure_started(['cfg1.json'])
                popen.assert_not_called()

            # Verify state write OSError does not crash main loop
            cfg_path = Path(tmp) / 'cfg.json'
            cfg_path.write_text('{"account": "wa-1"}', encoding='utf-8')
            with patch.object(mod, 'STATE', state_path), \
                 patch.object(mod, 'cycle', side_effect=[{'time': 1}, KeyboardInterrupt()]), \
                 patch.object(Path, 'replace', side_effect=PermissionError('locked')), \
                 patch.object(mod.time, 'sleep'), \
                 patch('sys.argv', ['fast_worker.py', '--config', str(cfg_path)]):
                with self.assertRaises(KeyboardInterrupt):
                    mod.main()

    def test_pet_designer_folder_matches_worker_ascii_model_with_dots(self):
        from hub.fleet_attempts import output_relative
        from hub.pet_render import designer_folder_name

        fleet_paths = _load_worker_module('fleet_paths_test', 'fleet_paths.py')
        self.assertEqual(designer_folder_name('TDVB-SOIVIET.11'), 'TDVB-SOIVIET11')
        if fleet_paths is not None:
            self.assertEqual(designer_folder_name('TDVB-SOIVIET.11'), fleet_paths.ascii_model('TDVB-SOIVIET.11'))
            self.assertEqual(designer_folder_name('333TPTrade_NON_2Mau'), fleet_paths.ascii_model('333TPTrade_NON_2Mau'))
        rel = output_relative(
            {
                'id': 'a' * 64,
                'archive_folder': 'CANAVI HCM2',
                'plan': {'order_code': 'TDVB-SOIVIET.11'},
                'source': {},
            },
            'pet-exports',
            'local-backup',
        )
        self.assertEqual(
            rel,
            f"CANAVI HCM2/DESIGNER/TDVB-SOIVIET11/versions/{'a' * 64}/worker-results/local-backup",
        )
        sha = hashlib.sha256(b'tiff').hexdigest()
        files = files_for(
            'pet_exports',
            {
                'archive_relative': rel,
                'source': {'thread_id': 'g2671966061008128194', 'asset': {'name': 'File in PET TDVB-SOIVIET.11.ai'}},
                'plan': {'order_code': 'TDVB-SOIVIET.11'},
                'reports': [{'name': 'TDVB-SOIVIET.11_position_1.tiff', 'sha256': sha}],
            },
        )
        self.assertEqual(files[0]['source'], rel + '/TDVB-SOIVIET.11_position_1.tiff')
        self.assertEqual(files[0]['name'], 'TDVB-SOIVIET.11_P1_LLM.tiff')


if __name__ == '__main__':
    unittest.main()
