"""Independent native selection per source artboard, original IDs preserved."""
import copy
import json
import re
from hub.jpg_native import prepare


def board_scan(scan, board):
    l, t, r, b = board['bounds']
    candidates = []
    for item in scan['candidates']:
        x, y, z, w = item['bounds']
        # Exclude parent groups spanning models; retain complete groups within a board.
        if x >= l - 1 and z <= r + 1 and y <= t + 1 and w >= b - 1:
            candidates.append(copy.deepcopy(item))
        elif item.get('kind') == 'GroupItem' and x >= l - 1 and z <= r + 1 and (z - x) <= (r - l) * 0.95 and b <= y <= t + 1 and (min(y, t) - max(w, b)) >= (t - b) * 0.25:
            candidates.append(copy.deepcopy(item))
    local = copy.deepcopy(board)
    local['index'] = 0
    return dict(scan, artboards=[local], candidates=candidates)


def prepare_multi(ask, scan, parts, refs, prompt, schema, digest, catalog, selected_artboards=None):
    boards = scan.get('artboards', [])
    if not 1 < len(boards) <= 40:
        raise ValueError('Multi-board source requires 2..40 verified artboards')
    selected_set = {int(x) for x in (selected_artboards or []) if isinstance(x, int) and 1 <= x <= len(boards)}
    results, issues, panels, draft_plans = [], [], [], []
    # Do not mix other model previews into the active board's visual context.
    context, skip = [], False
    for part in parts:
        text = part.get('text', '')
        if text.startswith(('file_page:', 'board_page:')):
            skip = True
            continue
        if skip and 'inline_data' in part:
            skip = False
            continue
        skip = False
        context.append(part)
    catalog_boards = {v['page']: v for v in catalog['boards']}
    reference_offsets_note = ''
    for i, board in enumerate(boards):
        page = i + 1
        if selected_set:
            if page not in selected_set:
                continue
        else:
            if not any(page in p.get("boards", []) for m in catalog["models"] for p in m["parts"]):
                continue
        try:
            codes = (catalog_boards.get(page) or {}).get('model_codes') or []
            if len(codes) != 1:
                if selected_set:
                    code = codes[0] if codes else f'AB{page}'
                else:
                    raise ValueError('Artboard chưa gắn duy nhất một mã mẫu')
            else:
                code = codes[0]
            local_refs = [r for r in refs if not r.startswith(('file_page:', 'board_page:'))]
            label = 'file_page:' + str(page)
            local_refs.append(label)
            board_instruction = (
                'Chỉ lập bản in cho mã ' + code + '. Phiếu có nhiều mã; chỉ dùng dòng của mã này. '
                'SOURCE_ARTBOARD 0 dưới đây là artboard nguồn số ' + str(page) + ', không phải các mẫu khác.'
            )
            if reference_offsets_note:
                board_instruction += ' ' + reference_offsets_note
            material = context + [
                {'text': board_instruction},
                {'text': label},
                {'inline_data': {'mime_type': 'image/png', 'data': board['preview']}}
            ]
            def scoped(prompt, material, schema, **kw):
                return ask(prompt, material, schema, board_page=page, **kw)
            from hub.jpg_part_strategy import table
            plan, _ = prepare(scoped, board_scan(scan, board), material, local_refs, prompt, schema, digest, part_table=table(catalog, page))
            if page > 1 and results:
                p1_comps = [c for pan in results[0]['plan'].get('panels', []) for c in pan.get('components', [])]
                if p1_comps and all(c.get('horizontal_alignment') == 'center' and c.get('horizontal_symmetry') for c in p1_comps):
                    for pan in plan.get('panels', []):
                        for comp in pan.get('components', []):
                            ev_h = str(comp.get('horizontal_alignment_evidence') or '').casefold()
                            if comp.get('horizontal_alignment') != 'center' and any(k in ev_h for k in ('artboard 1', 'file_page:1', 'không có cữ ngang', 'cùng mẫu', 'cùng kiểu')):
                                comp['horizontal_alignment'] = 'center'
                                comp['horizontal_symmetry'] = True
            if page == 1 and plan.get('panels'):
                p0 = plan['panels'][0]
                ref_comps = [
                    {
                        'side': c.get('side'),
                        'horizontal_alignment': c.get('horizontal_alignment'),
                        'maket_offsets_before_seam_cm': c.get('maket_offsets_before_seam_cm'),
                        'maket_top_cm': c.get('maket_top_cm'),
                        'mouth_allowance_cm': c.get('mouth_allowance_cm'),
                        'width_cm': round(c.get('width_cm', 0), 3),
                        'horizontal_symmetry': c.get('horizontal_symmetry'),
                    }
                    for c in p0.get('components', [])
                ]
                reference_offsets_note = (
                    'THÔNG SỐ CỮ MẪU ĐÃ XÁC MINH TỪ ARTBOARD 1 (`file_page:1` cùng kiểu túi/kích thước): '
                    f'width_cm={p0.get("width_cm")}, height_cm={p0.get("height_cm")}, components={json.dumps(ref_comps, ensure_ascii=False)}. '
                    'Nếu artboard hiện tại cùng kiểu túi và cùng kích thước logo nhưng không vẽ lại đường kích thước cữ đỏ: '
                    'nếu Artboard 1 đang horizontal_alignment="center" (horizontal_symmetry=true) thì BẮT BUỘC giữ nguyên horizontal_alignment="center" và horizontal_symmetry=true (tuyệt đối không chuyển thành left/right); chỉ dùng left/right khi Artboard 1 hoặc maket hiện tại có cữ lệch trái/phải rõ ràng.'
                )
            prefix = re.sub(r'[^A-Za-z0-9_.-]', '_', code)
            for panel in plan['panels']:
                panel['name'] = 'b' + str(page) + '_' + prefix + '_' + panel['name']
                panel['source_artboard_index'] = i
                panels.append(panel)
            results.append({'page': page, 'code': code, 'plan': plan})
        except ValueError as exc:
            if getattr(exc, 'draft_plan', None):
                draft_plans.append(exc.draft_plan)
            issues.append({'page': page, 'error': str(exc)})
    if not panels:
        err = ValueError('Không artboard nào đủ điều kiện: ' + str(issues))
        if draft_plans:
            err.draft_plan = draft_plans[0]
        raise err
    review_context = context[:]
    for i, board in enumerate(boards):
        review_context += [{'text': 'file_page:' + str(i + 1)}, {'inline_data': {'mime_type': 'image/png', 'data': board['preview']}}]
    clean_code = re.sub(r'[^A-Za-z0-9_.-]+', '_', results[0]['code'].strip()).strip('_') or 'MODEL'
    return {'renderer': 'native_group_v1', 'source_sha256': digest,
            'source_artboard_count': len(boards), 'order_code': clean_code + '_MULTI',
            'panels': panels, 'artboard_results': results, 'partial_issues': issues,
            'blocked_parts': [{'part': 'Artboard ' + str(v['page']), 'reason': v['error']} for v in issues]}, review_context
