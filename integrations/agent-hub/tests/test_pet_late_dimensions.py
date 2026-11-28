import json
import sys
import tempfile
import time
import unittest
from pathlib import Path

TESTS_DIR = str(Path(__file__).resolve().parent)
if TESTS_DIR not in sys.path:
    sys.path.insert(0, TESTS_DIR)

from test_hub import setup as hub_setup
from hub.pet_late_dimensions import (
    apply_late_dimension_binding,
    find_pending_size_selections,
    try_bind_late_pet_dimensions,
)


def _seed_pending_selection(
    store,
    tmp_path,
    *,
    sel_id='sel_kimoanh_1',
    brief_id='brief_kimoanh_1',
    thread_id='g4766322565399535347',
    asset_name='333TPTrade_NON_2Mau.ai',
    title='Nón 2 màu - 333 TRIPLE PURE',
    created=None,
    error='[OWNER_SIZE_CONFIRM] Vị trí position_1: kích thước file 13.0×16.3 cm vượt khổ nón',
    state='candidates_ready',
    auto_status='review',
):
    now = created if created is not None else time.time() - 3600
    ctx_id = 'ctx_' + sel_id
    ctx_dir = Path(store.path).parent / 'native-auto'
    ctx_dir.mkdir(parents=True, exist_ok=True)
    (ctx_dir / (ctx_id + '.json')).write_text(
        json.dumps({
            'refs': ['brief', 'message:m1'],
            'parts': [{'text': 'message:m1'}, {'text': 'mai làm gấp mẫu này'}],
        }, ensure_ascii=False),
        encoding='utf-8',
    )
    brief_payload = {
        'id': brief_id,
        'account': 'wa-1',
        'thread_id': thread_id,
        'sources': [
            {
                'message_id': 'm1',
                'origin': 'customer',
                'direction': 'incoming',
                'text': 'mai làm gấp mẫu này cho em',
            }
        ],
        'brief': {
            'title': title,
            'requirements': [{'basis': 'text', 'text': 'mai làm gấp mẫu này cho em', 'quote': 'mai làm gấp mẫu này cho em', 'message_id': 'm1'}],
        },
    }
    sel_payload = {
        'brief_id': brief_id,
        'conversation': 45,
        'thread_id': thread_id,
        'asset': {'name': asset_name, 'sha256': 'a' * 64},
        'auto_context': ctx_id,
        'auto_status': auto_status,
        'error': error,
        'blocked_parts': ['old blocked'],
        'customer_dimension_plan': {'applied_notes': []},
        'ai_calls': {
            'artboard_regions_v5_partial': {'state': 'done', 'result': {'regions': []}},
            'selection_pet_artwork_v5_all_boards': {'state': 'done', 'result': {'faces': []}},
            'customer_dimensions_v1': {'state': 'done', 'result': {'adjustments': [], 'unmatched_requests': []}},
        },
        'auto_plan': {
            'faces': [
                {
                    'side': 'position_1',
                    'candidate_ids': ['0.1.1'],
                    'usages': [{'model_code': title, 'position': 'Thân trước'}],
                    'explanation': 'Logo 333',
                }
            ]
        },
    }
    with store.db() as d:
        d.execute('CREATE TABLE IF NOT EXISTS native_selections(id TEXT PRIMARY KEY,brief_id TEXT,account TEXT,state TEXT,payload TEXT,created REAL)')
        d.execute('CREATE TABLE IF NOT EXISTS design_briefs(id TEXT PRIMARY KEY,run_id TEXT,account TEXT,thread_id TEXT,conversation INTEGER,payload TEXT,created REAL)')
        d.execute(
            'INSERT OR REPLACE INTO design_briefs VALUES(?,?,?,?,?,?,?)',
            (brief_id, 'run_orig', 'wa-1', thread_id, 45, json.dumps(brief_payload, ensure_ascii=False), now),
        )
        d.execute(
            'INSERT OR REPLACE INTO native_selections VALUES(?,?,?,?,?,?)',
            (sel_id, brief_id, 'wa-1', state, json.dumps(sel_payload, ensure_ascii=False), now),
        )
    return ctx_dir / (ctx_id + '.json')


class PetLateDimensionsTests(unittest.TestCase):
    def test_find_pending_filters_correctly(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, store, _ = hub_setup.__wrapped__(Path(tmp))
            # Valid pending [OWNER_SIZE_CONFIRM] within 24h
            _seed_pending_selection(store, tmp, sel_id='sel_valid', brief_id='b_valid')
            # Too old (>24h)
            _seed_pending_selection(store, tmp, sel_id='sel_old', brief_id='b_old', created=time.time() - 90000)
            # Non-OWNER_SIZE_CONFIRM error
            _seed_pending_selection(store, tmp, sel_id='sel_other_err', brief_id='b_other', error='Font thiếu')
            # CANAVI group excluded
            _seed_pending_selection(store, tmp, sel_id='sel_canavi', brief_id='b_canavi', thread_id='g2671966061008128194')

            found = find_pending_size_selections(store, 'wa-1', 'g4766322565399535347')
            self.assertEqual([c['id'] for c in found], ['sel_valid'])
            self.assertEqual(find_pending_size_selections(store, 'wa-1', 'g2671966061008128194'), [])

    def test_bind_succeeds_updates_brief_cache_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, store, engine = hub_setup.__wrapped__(Path(tmp))
            ctx_file = _seed_pending_selection(store, tmp)
            called = {'count': 0}

            def fake_ask(prompt, parts, schema):
                called['count'] += 1
                return {
                    'is_size_followup': True,
                    'target_selection_id': 'sel_kimoanh_1',
                    'confidence': 'high',
                    'reason': 'Khách bổ sung kích thước ngang 6 cm cho mẫu 333TPTrade',
                }

            run = {'id': 'run_late_1', 'account': 'wa-1', 'thread_id': 'g4766322565399535347', 'conversation': 45}
            msgs = [{
                'message_id': '8536704536341',
                'origin': 'customer',
                'direction': 'incoming',
                'sender': 'Kim Oanh',
                'text': 'ngang 6 cm',
                'timestamp': time.time(),
            }]

            res = try_bind_late_pet_dimensions(engine, run, msgs, ask_fn=fake_ask)
            self.assertIsNotNone(res)
            self.assertTrue(res['bound'])
            self.assertEqual(res['selection_id'], 'sel_kimoanh_1')
            self.assertEqual(called['count'], 1)

            with store.db() as d:
                bp = json.loads(d.execute("SELECT payload FROM design_briefs WHERE id='brief_kimoanh_1'").fetchone()[0])
                sp = json.loads(d.execute("SELECT payload FROM native_selections WHERE id='sel_kimoanh_1'").fetchone()[0])

            mids = [s['message_id'] for s in bp['sources']]
            self.assertEqual(mids, ['m1', '8536704536341'])
            self.assertEqual(sp['auto_status'], 'waiting_scan')
            self.assertNotIn('error', sp)
            self.assertNotIn('customer_dimensions_v1', sp['ai_calls'])
            # Object-selection caches must stay preserved so AI isn't billed again for step 1 & 2.
            self.assertIn('artboard_regions_v5_partial', sp['ai_calls'])
            self.assertIn('selection_pet_artwork_v5_all_boards', sp['ai_calls'])

            ctx = json.loads(ctx_file.read_text(encoding='utf-8'))
            self.assertIn('message:8536704536341', ctx['refs'])
            self.assertTrue(any('LATE_CUSTOMER_SIZE_FOLLOWUP message:8536704536341: ngang 6 cm' == p.get('text') for p in ctx['parts']))

            # Second run must see selection is waiting_scan (no longer review), so zero extra LLM calls
            res2 = try_bind_late_pet_dimensions(engine, run, msgs, ask_fn=fake_ask)
            self.assertIsNone(res2)
            self.assertEqual(called['count'], 1)

    def test_no_llm_call_when_nothing_pending(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, store, engine = hub_setup.__wrapped__(Path(tmp))
            called = {'count': 0}

            def fake_ask(*args, **kwargs):
                called['count'] += 1
                return {}

            run = {'id': 'r1', 'account': 'wa-1', 'thread_id': 'g4766322565399535347', 'conversation': 45}
            msgs = [{'message_id': 'm99', 'origin': 'customer', 'direction': 'incoming', 'text': 'ngang 6 cm'}]
            self.assertIsNone(try_bind_late_pet_dimensions(engine, run, msgs, ask_fn=fake_ask))
            self.assertEqual(called['count'], 0)

    def test_rejects_ambiguous_or_non_size_messages(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, store, engine = hub_setup.__wrapped__(Path(tmp))
            _seed_pending_selection(store, tmp, sel_id='sel_1', brief_id='b1', asset_name='MauA.ai')
            _seed_pending_selection(store, tmp, sel_id='sel_2', brief_id='b2', asset_name='MauB.ai')

            run = {'id': 'r2', 'account': 'wa-1', 'thread_id': 'g4766322565399535347', 'conversation': 45}
            msgs = [{'message_id': 'm100', 'origin': 'customer', 'direction': 'incoming', 'text': 'ngang 6 cm'}]

            def fake_ambiguous(prompt, parts, schema):
                return {
                    'is_size_followup': True,
                    'target_selection_id': '',
                    'confidence': 'low',
                    'reason': 'Có 2 mẫu đang chờ nhưng khách không chỉ rõ mẫu nào',
                }

            self.assertIsNone(try_bind_late_pet_dimensions(engine, run, msgs, ask_fn=fake_ambiguous))
            with store.db() as d:
                for sid in ('sel_1', 'sel_2'):
                    sp = json.loads(d.execute('SELECT payload FROM native_selections WHERE id=?', (sid,)).fetchone()[0])
                    self.assertEqual(sp['auto_status'], 'review')

    def test_region_candidates_retains_complete_logo_group_above_35_pct_artboard(self):
        from hub.native_auto import region_candidates

        # Mirror 333TPTrade_NON_2Mau.ai on A4: logo group 0.1 is 40.5% of A4 with 0.6964 overlap against box_2d
        scan = {
            'artboards': [{'index': 0, 'bounds': [0.0, 0.0, 595.2756, -841.8898]}],
            'candidates': [
                {'id': '0.0', 'kind': 'GroupItem', 'bounds': [0.0, 0.0, 595.2756, -841.8898], 'width_cm': 21.0, 'height_cm': 29.7},
                {'id': '0.0.0', 'kind': 'PathItem', 'bounds': [0.0, 0.0, 595.2756, -841.8898], 'width_cm': 21.0, 'height_cm': 29.7},
                {'id': '0.1', 'kind': 'GroupItem', 'bounds': [78.6667, -167.1039, 517.3333, -630.1734], 'width_cm': 15.48, 'height_cm': 16.34},
                {'id': '0.1.1', 'kind': 'CompoundPathItem', 'bounds': [150.0, -200.0, 200.0, -250.0], 'width_cm': 1.76, 'height_cm': 1.76},
                {'id': '0.1.24', 'kind': 'CompoundPathItem', 'bounds': [422.5, -474.7, 517.3, -621.2], 'width_cm': 3.35, 'height_cm': 5.17},
            ],
        }
        regions = [{'artboard_index': 0, 'box': [0.232, 0.196, 0.768, 0.725]}]
        kept_ids = [c['id'] for c in region_candidates(scan, regions)]
        self.assertIn('0.1', kept_ids)
        self.assertNotIn('0.0', kept_ids)
        self.assertNotIn('0.0.0', kept_ids)


if __name__ == '__main__':
    unittest.main()
