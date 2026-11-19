"""Promote a selected logo only when its parent is or sibling has verified white backing."""
def _sibling_white_backing(face, scan, known, used_ids, board_w, board_h):
    ids = face['object_ids']
    child = ids[0]
    if '.' not in child:
        return None
    prefix, idx_str = child.rsplit('.', 1)
    try:
        child_idx = int(idx_str)
    except ValueError:
        return None
    child_obj = known.get(child)
    if not child_obj:
        return None
    # One printed face may consist of a separate logo and slogan. Inspect their
    # union, not just the first group; do not change any source geometry.
    selected = [known.get(i) for i in ids]
    if any(not obj or i.rsplit('.', 1)[0] != prefix for i, obj in zip(ids, selected)):
        return None
    child_idx = max(int(i.rsplit('.', 1)[1]) for i in ids)
    boxes = [obj['bounds'] for obj in selected]
    logo = [min(b[0] for b in boxes), max(b[1] for b in boxes),
            max(b[2] for b in boxes), min(b[3] for b in boxes)]
    logo_w = (logo[2] - logo[0]) * 2.54 / 72
    logo_h = (logo[1] - logo[3]) * 2.54 / 72
    logo_area = logo_w * logo_h
    if logo_area <= 0:
        return None
    matches = []
    for sib in scan.get('candidates', []):
        sid = sib.get('id', '')
        # Both faces can intentionally reuse the same source backing.
        if sid in ids or '.' not in sid:
            continue
        sprefix, sidx_str = sid.rsplit('.', 1)
        if sprefix != prefix:
            continue
        try:
            sib_idx = int(sidx_str)
        except ValueError:
            continue
        if sib_idx <= child_idx:
            continue
        if sib.get('kind') != 'PathItem' or sib.get('verified_white_fill') is not True:
            continue
        sb = sib['bounds']
        if not (sb[0] <= logo[0] + 1.0 and sb[1] >= logo[1] - 1.0 and sb[2] >= logo[2] - 1.0 and sb[3] <= logo[3] + 1.0):
            continue
        sib_w = (sb[2] - sb[0]) * 2.54 / 72
        sib_h = (sb[1] - sb[3]) * 2.54 / 72
        if not (sib_w <= logo_w + 10.0 and sib_h <= logo_h + 10.0 and sib_w * sib_h <= logo_area * 2.5):
            continue
        has_bg = False
        for bg in scan.get('candidates', []):
            bid = bg.get('id', '')
            if bid in (child, sid) or bg.get('verified_white_fill'):
                continue
            bb = bg['bounds']
            bg_w = (bb[2] - bb[0]) * 2.54 / 72
            bg_h = (bb[1] - bb[3]) * 2.54 / 72
            if not (bg_w <= 180 and bg_h <= 180):
                continue
            if board_w > 0 and bg_w >= board_w - 1.0 and bg_h >= board_h - 1.0:
                continue
            if (bg_w >= sib_w + 3.0 or bg_h >= sib_h + 3.0) and bb[0] <= sb[0] + 1.0 and bb[1] >= sb[1] - 1.0 and bb[2] >= sb[2] - 1.0 and bb[3] <= sb[3] + 1.0:
                has_bg = True
                break
        if has_bg:
            matches.append((sib_w * sib_h, sib))
    if not matches:
        return None
    matches.sort(key=lambda x: x[0])
    return matches[0][1]


def complete_faces(selection, scan):
    known = {c['id']: c for c in scan['candidates']}
    boards = scan.get('artboards', [])
    board_w = max((b.get('width_cm', 0) for b in boards), default=0)
    board_h = max((b.get('height_cm', 0) for b in boards), default=0)
    used_ids = {i for f in selection.get('faces', []) for i in f.get('object_ids', [])}
    changes = []
    for face in selection['faces']:
        ids = face['object_ids']
        if not ids:
            continue
        child = ids[0]
        parent = known.get(child.rsplit('.', 1)[0]) if '.' in child else None
        promoted = False
        if len(ids) == 1 and parent and parent['kind'] == 'GroupItem':
            children = parent.get('direct_child_ids', [])
            others = [i for i in children if i != child]
            if others and child in children:
                # Illustrator pageItems order is front-to-back. Only backing behind logo.
                if not any(children.index(i) < children.index(child) or not known.get(i, {}).get('verified_white_fill') for i in others):
                    logo = known[child]['bounds']
                    if all(known[i]['bounds'][0] <= logo[0] and known[i]['bounds'][1] >= logo[1]
                           and known[i]['bounds'][2] >= logo[2] and known[i]['bounds'][3] <= logo[3] for i in others):
                        face['object_ids'] = [parent['id']]
                        used_ids.add(parent['id'])
                        changes.append({'side': face['side'], 'logo':child, 'white_backing':others, 'complete_group':parent['id']})
                        promoted = True
        if not promoted:
            sib = _sibling_white_backing(face, scan, known, used_ids, board_w, board_h)
            if sib:
                face['object_ids'] = ids + [sib['id']]
                used_ids.add(sib['id'])
                changes.append({'side': face['side'], 'logo': child, 'logo_ids': list(ids), 'white_backing': [sib['id']], 'sibling_backing': True})
    selection['white_backing_completion'] = changes
    return selection
