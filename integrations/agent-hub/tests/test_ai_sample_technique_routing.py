import json
import time
from pathlib import Path
from types import SimpleNamespace

import pymupdf as fitz

from hub.artwork_checks import known_native_pet
from hub.direct_pet_intake import collect as collect_pet
from hub.export_routing import apply_routing
from hub.sample_file_policy import enabled as sample_enabled, requested as sample_requested
from test_hub import setup as hub_setup


def _msg(mid, *, text='', assets=None, ts=None):
    return {
        'message_id': mid,
        'sender': 'Như Quyền',
        'sender_id': 'cust1',
        'origin': 'customer',
        'role': 'customer',
        'direction': 'incoming',
        'text': text,
        'images': [],
        'assets': assets or [],
        'timestamp': ts if ts is not None else time.time(),
    }


def _asset(name, sha=None):
    return {
        'id': 'a' * 64,
        'name': name,
        'kind': 'file',
        'state': 'ready',
        'relative_path': f'QUYEN/2026-11/originals/a__{name}',
        'sha256': sha or ('b' * 64),
        'size': 1024,
        'mime_type': 'application/octet-stream',
        'error': '',
    }


def test_sample_file_policy_sublimation_flag(tmp_path):
    now = time.time()
    msgs = [_msg('m1', text='Cho làm mẫu chuyển nhiệt nhé', assets=[_asset('mau89.ai')], ts=now)]
    assert sample_requested('g_quyen', msgs) is False
    assert sample_requested('g_quyen', msgs, allow_sublimation=True) is True

    marker = tmp_path / 'sample-file-pet-enabled-at'
    marker.write_text(str(now - 60), encoding='utf-8')
    store = SimpleNamespace(path=str(tmp_path / 'hub.sqlite3'))
    assert sample_enabled(store, 'g_quyen', msgs) is False
    assert sample_enabled(store, 'g_quyen', msgs, allow_sublimation=True) is True


def test_direct_pet_intake_sample_sets_ai_technique_inspect(tmp_path):
    _, store, engine = hub_setup.__wrapped__(tmp_path)
    engine.settings.inboxes['zalo-personal-1'] = dict(engine.settings.inboxes['wa-1'])
    now = time.time()
    (Path(store.path).parent / 'sample-file-pet-enabled-at').write_text(str(now - 60), encoding='utf-8')
    collector = SimpleNamespace(
        store=store,
        e=engine,
        intake=SimpleNamespace(policy=lambda _: {}),
        workflow=SimpleNamespace(register=lambda p: None),
    )

    # Case 1: Sample request with PET in filename -> must still inspect content via AI
    run1 = {'id': 'r1', 'account': 'zalo-personal-1', 'thread_id': 'g_quyen', 'conversation': 5}
    msgs1 = [
        _msg('m1', text='[File Zalo: File in PET nón 88.ai]', assets=[_asset('File in PET nón 88.ai', sha='1' * 64)], ts=now),
        _msg('m2', text='Cho làm giúp q mẫu này nhé Tuấn', ts=now + 1),
    ]
    assert collect_pet(collector, run1, msgs1) is True
    with store.db() as db:
        row1 = json.loads(db.execute("SELECT payload FROM design_briefs WHERE run_id='r1'").fetchone()[0])
    assert row1['direct_pet_source'] is False
    assert row1['ai_technique_inspect'] is True
    assert row1['n8n_export_kind'] == 'auto'

    # Case 2: Sample request mentioning chuyen nhiet -> admitted with ai_technique_inspect=True
    run2 = {'id': 'r2', 'account': 'zalo-personal-1', 'thread_id': 'g_quyen', 'conversation': 5}
    msgs2 = [_msg('m3', text='Làm mẫu chuyển nhiệt file này', assets=[_asset('mau_89.ai', sha='2' * 64)], ts=now)]
    assert collect_pet(collector, run2, msgs2) is True
    with store.db() as db:
        row2 = json.loads(db.execute("SELECT payload FROM design_briefs WHERE run_id='r2'").fetchone()[0])
    assert row2['direct_pet_source'] is False
    assert row2['ai_technique_inspect'] is True
    assert row2['n8n_export_kind'] == 'auto'

    # Case 3: Non-sample explicit PET asset -> keeps legacy direct_pet_source=True
    run3 = {'id': 'r3', 'account': 'zalo-personal-1', 'thread_id': 'g_quyen', 'conversation': 5, 'agent_admitted': True}
    msgs3 = [_msg('m4', text='In giúp em 200 cái', assets=[_asset('File in PET nón 90.ai', sha='3' * 64)], ts=now)]
    assert collect_pet(collector, run3, msgs3) is True
    with store.db() as db:
        row3 = json.loads(db.execute("SELECT payload FROM design_briefs WHERE run_id='r3'").fetchone()[0])
    assert row3['direct_pet_source'] is True
    assert row3.get('ai_technique_inspect') is None
    assert row3['n8n_export_kind'] == 'export_pet'


def test_known_native_pet_respects_ai_technique_inspect(tmp_path):
    _, store, _ = hub_setup.__wrapped__(tmp_path)
    p = {'thread_id': 'g_quyen', 'asset': _asset('File in PET nón 88.ai')}
    brief = {'ai_technique_inspect': True, 'direct_pet_source': False, 'sources': []}
    with store.db() as db:
        assert known_native_pet(db, brief, p, 'b1') is False
        assert known_native_pet(db, brief, {**p, 'owner_export_spec': {'mode': 'pet'}}, 'b1') is True


def test_export_routing_preserves_explicit_both_and_conflict():
    brief = {'thread_id': 'g_quyen', 'sources': [{'message_id': 'm1', 'role': 'customer', 'text': 'Làm mẫu'}]}
    r_pet = apply_routing(
        {'print_process': 'pet', 'process_basis': 'explicit', 'process_sources': ['file_page:1'], 'process_reason': 'FILE IN PET'},
        brief,
    )
    assert r_pet['print_process'] == 'pet' and r_pet['routing_policy'] == 'source_process_evidence'

    r_sub = apply_routing(
        {'print_process': 'sublimation', 'process_basis': 'explicit', 'process_sources': ['file_page:1'], 'process_reason': 'IN CHUYỂN NHIỆT'},
        brief,
    )
    assert r_sub['print_process'] == 'sublimation' and r_sub['routing_policy'] == 'source_process_evidence'

    r_both = apply_routing(
        {'print_process': 'both', 'process_basis': 'explicit', 'process_sources': ['file_page:1'], 'process_reason': 'PET + CN'},
        brief,
    )
    assert r_both['print_process'] == 'both' and r_both['routing_policy'] == 'source_process_evidence'

    r_cap_logo = apply_routing(
        {'print_process': 'sublimation', 'process_basis': 'cap_logo', 'process_sources': ['file_page:1'], 'process_reason': 'Logo nhỏ trước nón'},
        brief,
    )
    assert r_cap_logo['print_process'] == 'pet'

    r_cap_pat = apply_routing(
        {'print_process': 'pet', 'process_basis': 'cap_pattern', 'process_sources': ['file_page:1'], 'process_reason': 'Hoa văn full nón'},
        brief,
    )
    assert r_cap_pat['print_process'] == 'sublimation'

    r_conflict = apply_routing(
        {
            'print_process': 'unknown',
            'process_basis': 'unknown',
            'process_sources': [],
            'process_reason': '',
            'findings': [{'kind': 'conflict', 'text': 'Tên file PET nhưng nội dung ghi chuyển nhiệt', 'sources': ['file_page:1']}],
        },
        brief,
    )
    assert r_conflict['print_process'] == 'unknown' and r_conflict['routing_policy'] == 'conflict_review'


def test_pet_exports_skips_conflict_or_sublimation_when_ai_technique_inspect(tmp_path):
    _, store, engine = hub_setup.__wrapped__(tmp_path)
    now = time.time()
    asset = _asset('File in PET nón 88.ai', sha='4' * 64)
    brief = {
        'id': 'b_conflict',
        'ai_technique_inspect': True,
        'n8n_export_kind': 'auto',
        'brief': {'title': 'File in PET nón 88.ai'},
        'sources': [],
    }
    with store.db() as db:
        db.execute(
            'INSERT INTO design_briefs VALUES(?,?,?,?,?,?,?)',
            ('b_conflict', 'r1', 'zalo-personal-1', 'g_quyen', 5, json.dumps(brief), now),
        )
    row = {
        'id': 'ac_conflict',
        'brief_id': 'b_conflict',
        'account': 'zalo-personal-1',
        'payload': json.dumps({'asset': asset, 'conversation': 5, 'thread_id': 'g_quyen', 'source_message_id': 'm1'}),
    }
    engine.artwork_checks.pet.prepare(
        row,
        brief,
        {'state': 'parsed', 'file_kind': 'pdf_compatible_ai', 'object_inventory': {'objects': []}},
        [],
        ['brief'],
        {'print_process': 'unknown', 'same_design': 'unknown', 'file_role': 'mixed', 'findings': [{'kind': 'conflict', 'text': 'conflict'}]},
        tmp_path / 'missing.bin',
    )
    with store.db() as db:
        assert db.execute('SELECT count(*) FROM pet_exports').fetchone()[0] == 0


def test_jpg_exports_mixed_sublimation_goes_to_review_and_clean_artwork_queues(tmp_path):
    _, store, engine = hub_setup.__wrapped__(tmp_path)
    now = time.time()
    engine.artwork_checks.jpg.since = now - 60
    asset = _asset('mau_89.ai', sha='5' * 64)
    pdf_path = tmp_path / 'mau_89.ai'
    doc = fitz.open()
    doc.new_page(width=200, height=200)
    doc.save(str(pdf_path))
    doc.close()

    for idx, (bid, ac_id, role, expected_state) in enumerate(
        [
            ('b_mixed', 'a' * 64, 'mixed', 'review'),
            ('b_art', 'b' * 64, 'artwork', 'queued'),
        ],
        1,
    ):
        brief = {'id': bid, 'ai_technique_inspect': True, 'n8n_export_kind': 'export_jpg', 'brief': {'title': 'mau_89.ai'}, 'sources': []}
        with store.db() as db:
            db.execute(
                'INSERT INTO design_briefs VALUES(?,?,?,?,?,?,?)',
                (bid, f'r{idx}', 'zalo-personal-1', 'g_quyen', 5, json.dumps(brief), now),
            )
        row = {
            'id': ac_id,
            'brief_id': bid,
            'account': 'zalo-personal-1',
            'created': now,
            'payload': json.dumps({'asset': asset, 'conversation': 5, 'thread_id': 'g_quyen', 'source_message_id': 'm1'}),
        }
        comparison = {
            'print_process': 'sublimation',
            'process_basis': 'explicit',
            'process_sources': ['file_page:1'],
            'same_design': 'proposed',
            'file_role': role,
            'findings': [],
        }
        engine.artwork_checks.jpg.prepare(
            row,
            brief,
            {'state': 'parsed', 'file_kind': 'pdf_compatible_ai', 'object_inventory': {'objects': []}},
            [],
            ['brief', 'file_page:1'],
            comparison,
            pdf_path,
        )
        with store.db() as db:
            got = db.execute('SELECT state, payload FROM jpg_exports WHERE id=?', (ac_id,)).fetchone()
        assert got is not None and got['state'] == expected_state
        if expected_state == 'review':
            assert 'tách cụm artwork' in json.loads(got['payload'])['review_reason']
