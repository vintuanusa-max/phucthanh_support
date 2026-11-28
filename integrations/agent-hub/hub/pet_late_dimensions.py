"""Detect and bind late customer dimension follow-up messages to pending PET [OWNER_SIZE_CONFIRM] jobs."""
import json
import re
import time
from pathlib import Path

from hub import native_selection as ns
from hub.export_routing import CANAVI_GROUPS, JPG_GROUPS
from hub.print_api import ask as print_api_ask


def _clean_customer_text(text):
    cleaned = re.sub(r'\[(?:File|Ảnh)[^\]]*\]', ' ', str(text or ''))
    return re.sub(r'\s+', ' ', cleaned).strip()


def find_pending_size_selections(store, account, thread_id, *, max_age_seconds=86400, workflow=None):
    """Return active native_selections paused at [OWNER_SIZE_CONFIRM] for this customer thread."""
    if not account or not thread_id or thread_id in (JPG_GROUPS | CANAVI_GROUPS):
        return []
    cutoff = time.time() - float(max_age_seconds)
    out = []
    with store.db() as d:
        tables = {r[0] for r in d.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if 'native_selections' not in tables or 'design_briefs' not in tables:
            return []
        rows = d.execute(
            """
            SELECT ns.id, ns.brief_id, ns.account, ns.state, ns.payload, ns.created,
                   db.payload AS brief_payload
            FROM native_selections ns
            JOIN design_briefs db ON db.id = ns.brief_id
            WHERE ns.account = ?
              AND ns.state = 'candidates_ready'
              AND json_extract(ns.payload, '$.thread_id') = ?
              AND json_extract(ns.payload, '$.auto_status') = 'review'
              AND json_extract(ns.payload, '$.error') LIKE '[OWNER_SIZE_CONFIRM]%'
              AND ns.created >= ?
            ORDER BY ns.created DESC
            """,
            (account, thread_id, cutoff),
        ).fetchall()
    for row in rows:
        if workflow is not None and not workflow.current(row['brief_id']):
            continue
        payload = json.loads(row['payload'] or '{}')
        brief_payload = json.loads(row['brief_payload'] or '{}')
        faces_summary = []
        for f in (payload.get('auto_plan') or {}).get('faces') or []:
            if isinstance(f, dict):
                faces_summary.append({
                    'side': f.get('side', ''),
                    'usages': f.get('usages', []),
                    'explanation': f.get('explanation', ''),
                })
        existing_mids = {
            str(s.get('message_id') or '').strip()
            for s in (brief_payload.get('sources') or [])
            if isinstance(s, dict) and s.get('message_id')
        }
        out.append({
            'id': row['id'],
            'brief_id': row['brief_id'],
            'account': row['account'],
            'state': row['state'],
            'created': row['created'],
            'asset_name': (payload.get('asset') or {}).get('name', ''),
            'title': ((brief_payload.get('brief') or {}).get('title') or ''),
            'error': payload.get('error', ''),
            'faces': faces_summary,
            'existing_message_ids': existing_mids,
            'payload': payload,
            'brief_payload': brief_payload,
        })
    return out


def apply_late_dimension_binding(e, candidate, followup_messages, *, reason='', followup_run_id=''):
    """Atomically append late customer dimension messages to the brief/selection and requeue PET planning."""
    msg_ids = []
    cleaned_msgs = []
    for m in followup_messages or []:
        mid = str(m.get('message_id') or '').strip()
        if not mid:
            continue
        msg_ids.append(mid)
        cleaned_msgs.append(dict(m))
    if not msg_ids:
        raise ValueError('No follow-up messages to bind')

    selection_id = candidate['id']
    brief_id = candidate['brief_id']
    auto_context_id = ''

    with ns.LOCK, e.store.db() as d:
        d.execute('BEGIN IMMEDIATE')
        b_row = d.execute('SELECT payload FROM design_briefs WHERE id=?', (brief_id,)).fetchone()
        s_row = d.execute('SELECT state, payload FROM native_selections WHERE id=?', (selection_id,)).fetchone()
        if not b_row or not s_row:
            raise ValueError('Pending selection or brief no longer exists')
        if s_row['state'] != 'candidates_ready':
            raise ValueError('Selection is no longer in candidates_ready')

        sp = json.loads(s_row['payload'] or '{}')
        if sp.get('auto_status') != 'review' or not str(sp.get('error') or '').startswith('[OWNER_SIZE_CONFIRM]'):
            raise ValueError('Selection is no longer waiting at [OWNER_SIZE_CONFIRM]')

        bp = json.loads(b_row['payload'] or '{}')
        sources = list(bp.get('sources') or [])
        existing_ids = {str(s.get('message_id') or '').strip() for s in sources if isinstance(s, dict)}
        added_msgs = []
        for m in cleaned_msgs:
            mid = str(m['message_id']).strip()
            if mid not in existing_ids:
                existing_ids.add(mid)
                sources.append(m)
                added_msgs.append(m)
        if not added_msgs:
            return {'bound': False, 'already_bound': True, 'selection_id': selection_id, 'brief_id': brief_id}

        bp['sources'] = sources
        brief_reqs = list(((bp.get('brief') or {}).get('requirements')) or [])
        for m in added_msgs:
            brief_reqs.append({
                'basis': 'text',
                'text': m.get('text', ''),
                'quote': m.get('text', ''),
                'message_id': str(m['message_id']).strip(),
                'late_followup': True,
            })
        if isinstance(bp.get('brief'), dict):
            bp['brief']['requirements'] = brief_reqs
        followups_log = list(bp.get('late_dimension_followups') or [])
        followups_log.append({
            'run_id': followup_run_id,
            'message_ids': [str(m['message_id']).strip() for m in added_msgs],
            'reason': reason,
            'bound_at': time.time(),
        })
        bp['late_dimension_followups'] = followups_log
        d.execute('UPDATE design_briefs SET payload=? WHERE id=?', (json.dumps(bp, ensure_ascii=False), brief_id))

        ai_calls = dict(sp.get('ai_calls') or {})
        ai_calls.pop('customer_dimensions_v1', None)
        sp['ai_calls'] = ai_calls
        sp.pop('customer_dimension_plan', None)
        sp.pop('error', None)
        sp.pop('auto_started', None)
        sp['blocked_parts'] = []
        sp['auto_status'] = 'waiting_scan'
        sp['late_dimension_followup'] = {
            'run_id': followup_run_id,
            'message_ids': [str(m['message_id']).strip() for m in added_msgs],
            'reason': reason,
            'bound_at': time.time(),
        }
        auto_context_id = str(sp.get('auto_context') or '').strip()
        d.execute('UPDATE native_selections SET payload=? WHERE id=?', (json.dumps(sp, ensure_ascii=False), selection_id))

    # Append follow-up message text/refs to the persisted native-auto context file so post-render verification sees it.
    if auto_context_id:
        ctx_path = Path(e.store.path).parent / 'native-auto' / (auto_context_id + '.json')
        if ctx_path.is_file():
            try:
                ctx = json.loads(ctx_path.read_text(encoding='utf-8'))
                refs = list(ctx.get('refs') or [])
                parts = list(ctx.get('parts') or [])
                for m in added_msgs:
                    mid = str(m['message_id']).strip()
                    ref = f'message:{mid}'
                    if ref not in refs:
                        refs.append(ref)
                    txt = _clean_customer_text(m.get('text', ''))
                    if txt:
                        note_text = f'LATE_CUSTOMER_SIZE_FOLLOWUP {ref}: {txt}'
                        if not any(isinstance(p, dict) and p.get('text') == note_text for p in parts):
                            parts.append({'text': note_text})
                ctx['refs'] = refs
                ctx['parts'] = parts
                ctx_path.write_text(json.dumps(ctx, ensure_ascii=False), encoding='utf-8')
            except Exception:
                pass

    conv = candidate['payload'].get('conversation')
    asset_name = candidate.get('asset_name') or selection_id[:12]
    if conv:
        quotes = '; '.join(f"{m['message_id']}: {_clean_customer_text(m.get('text', ''))}" for m in added_msgs)
        e.note(
            f'late-size-bind:{selection_id}:{"+".join(sorted(m["message_id"] for m in added_msgs))}',
            conv,
            f'TỰ NỐI KÍCH THƯỚC KHÁCH BỔ SUNG — {asset_name}\n'
            f'Đã gắn tin nhắn bổ sung ({quotes}) vào hồ sơ {selection_id[:12]} và xếp hàng xuất lại PNG/TIFF.',
            apply_capture=True,
        )

    return {
        'bound': True,
        'already_bound': False,
        'selection_id': selection_id,
        'brief_id': brief_id,
        'asset_name': asset_name,
        'message_ids': [str(m['message_id']).strip() for m in added_msgs],
        'reason': reason,
    }


def try_bind_late_pet_dimensions(e, run, active_msgs, *, ask_fn=None):
    """Identify whether a late customer text message clarifies cm sizes for a pending [OWNER_SIZE_CONFIRM] PET job."""
    customer_msgs = []
    for m in active_msgs or []:
        if not isinstance(m, dict) or m.get('recalled') or m.get('revision'):
            continue
        if m.get('origin', 'customer') != 'customer' or m.get('direction') == 'outgoing':
            continue
        txt = _clean_customer_text(m.get('text', ''))
        if txt:
            customer_msgs.append(m)
    if not customer_msgs:
        return None

    workflow = getattr(getattr(getattr(e, 'artwork_checks', None), 'pet', None), 'workflow', None)
    candidates = find_pending_size_selections(e.store, run.get('account', ''), run.get('thread_id', ''), workflow=workflow)
    if not candidates:
        return None

    # Filter out messages already present on all candidate briefs.
    batch_mids = {str(m.get('message_id') or '').strip() for m in customer_msgs if m.get('message_id')}
    unbound_candidates = [c for c in candidates if not (batch_mids <= c['existing_message_ids'])]
    if not unbound_candidates:
        return None

    candidate_ids = [c['id'] for c in unbound_candidates]
    schema = {
        'type': 'object',
        'required': ['is_size_followup', 'target_selection_id', 'confidence', 'reason'],
        'properties': {
            'is_size_followup': {'type': 'boolean'},
            'target_selection_id': {'type': 'string', 'enum': candidate_ids + ['']},
            'confidence': {'type': 'string', 'enum': ['high', 'low']},
            'reason': {'type': 'string'},
        },
    }

    cand_summary = [
        {
            'selection_id': c['id'],
            'asset_name': c['asset_name'],
            'title': c['title'],
            'pending_reason': c['error'],
            'faces': c['faces'],
        }
        for c in unbound_candidates
    ]
    msg_summary = [
        {'message_id': str(m.get('message_id') or ''), 'text': _clean_customer_text(m.get('text', ''))}
        for m in customer_msgs
    ]
    prompt = (
        'LATE_PET_DIMENSIONS_BINDING: Xác định xem cụm tin nhắn mới của khách hàng (FOLLOWUP_MESSAGES) '
        'có phải là lời CHỐT / BỔ SUNG KÍCH THƯỚC IN (cm/mm, ví dụ "ngang 6 cm", "mạc cao 5cm", "ngang 7cm") '
        'dành cho một hồ sơ xuất file PET đang tạm dừng chờ xác nhận kích thước [OWNER_SIZE_CONFIRM] trong PENDING_SELECTIONS hay không.\n'
        'QUY TẮC:\n'
        '1. Chỉ đặt is_size_followup=true, confidence="high" và chọn đúng target_selection_id khi tin khách nêu rõ kích thước in cho một hồ sơ duy nhất (chỉ có 1 hồ sơ chờ hoặc tin khách nêu rõ tên mẫu/loại sản phẩm trùng khớp duy nhất 1 hồ sơ).\n'
        '2. Nếu có từ 2 hồ sơ đang chờ [OWNER_SIZE_CONFIRM] trở lên mà tin khách KHÔNG nói rõ áp dụng cho mẫu nào -> đặt confidence="low", target_selection_id="" (KHÔNG đoán bừa giữa nhiều mẫu).\n'
        '3. Nếu tin khách là hỏi giá, báo số lượng, hẹn giao, hỏi tiến độ, chào hỏi, hủy/đổi mẫu hoặc không liên quan kích thước in -> is_size_followup=false, target_selection_id="".\n'
        '4. Trả JSON thuần theo schema.'
    )
    parts = [
        {'text': 'FOLLOWUP_MESSAGES ' + json.dumps(msg_summary, ensure_ascii=False)},
        {'text': 'PENDING_SELECTIONS ' + json.dumps(cand_summary, ensure_ascii=False)},
    ]

    caller = ask_fn or (lambda p, pts, sch: print_api_ask(e, p, pts, sch, getattr(e.settings, 'gemini_model', 'gemini-2.5-flash')))
    decision = caller(prompt, parts, schema)
    if not isinstance(decision, dict):
        return None
    if decision.get('is_size_followup') is not True or decision.get('confidence') != 'high':
        return None
    target_id = str(decision.get('target_selection_id') or '').strip()
    chosen = next((c for c in unbound_candidates if c['id'] == target_id), None)
    if not chosen:
        return None

    return apply_late_dimension_binding(
        e,
        chosen,
        customer_msgs,
        reason=str(decision.get('reason') or '').strip(),
        followup_run_id=str(run.get('id') or ''),
    )
