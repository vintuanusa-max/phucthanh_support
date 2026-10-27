"""Split explicit sample requests before the sample-only short circuit.

Never split a source message between two durable ERP runs. Ambiguous mixed
messages remain reviewable instead of silently losing the production request.
"""
import re
from hub.psd_samples import sample_only, production_request


def request_groups(batch):
    samples = [(i, m) for i, m in batch if sample_only([m])]
    orders = [(i, m) for i, m in batch if production_request(m.get('text', ''))]
    if not samples or not orders:
        return None
    sample_ids = {i for i, _ in samples}
    # A sample request without a code may be immediately followed by its PSD.
    # Only accept one file, same author, before the next request; never images.
    for index,(i,m) in enumerate(batch[:-1]):
        if i not in sample_ids:
            continue
        ni,nm=batch[index+1]
        assets=nm.get('assets',[])
        if (m.get('sender_id') or m.get('sender')) and (m.get('sender_id') or m.get('sender')) == (nm.get('sender_id') or nm.get('sender')) and len(assets)==1 and assets[0].get('name','').lower().endswith('.psd') and not production_request(nm.get('text','')):
            sample_ids.add(ni)
    sample_codes = set(re.findall(r'\b[a-z]+\d+[a-z0-9_-]*\b', ' '.join(m.get('text','') for _,m in samples).casefold()))
    for i,m in batch:
        if i in sample_ids or production_request(m.get('text','')):
            continue
        assets=m.get('assets',[])
        # Attach only a named matching source; never steal the closest image.
        if assets and all(a.get('name','').lower().endswith('.psd') and any(
                re.search(r'(?<![a-z0-9])'+re.escape(code)+r'(?![a-z0-9])',a.get('name','').casefold())
                for code in sample_codes) for a in assets):
            sample_ids.add(i)
    return [[(i,m) for i,m in batch if i in sample_ids],
            [(i,m) for i,m in batch if i not in sample_ids]]


def split_requests(intake, run, payload, batch):
    from hub.intake_models import split
    if payload.get('model_parent'):
        return False
    groups=request_groups(batch)
    if groups:
        return split(intake,run,payload,batch,groups)
    # Two intents inside one source cannot be claimed twice.
    if any(re.search(r'\b(in test|test mẫu|in thử|làm mẫu)\b',m.get('text','').casefold())
           and production_request(m.get('text','')) for _,m in batch):
        raise ValueError('Cùng một tin có lên mẫu và sản xuất: cần tách rõ mẫu/lô, giữ nguồn và số lượng; chưa ghi ERP')
    return False
