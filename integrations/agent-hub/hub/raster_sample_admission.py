"""Admit only new, settled raster sample dialogues or clean standalone raster PET requests."""
import re
import time
from pathlib import Path
from hub.source_readiness import norm
from hub.sample_file_policy import requested, pet_requested, EXTENSIONS
from hub.raster_consent import restoration_consent
from hub.export_routing import JPG_GROUPS, CANAVI_GROUPS

RASTER_EXTENSIONS = ('.png', '.jpg', '.jpeg', '.webp')


def evidence(intake, run, messages):
    marker = Path(intake.store.path).parent / 'raster-sample-enabled-at'
    if not marker.exists() or not messages:
        return None
    cutoff = float(marker.read_text())
    if any(float(m.get('timestamp', 0)) < cutoff for m in messages):
        return None
    live = [m for m in messages if not m.get('recalled') and not m.get('revision')]
    if any(a.get('name', '').lower().endswith(EXTENSIONS) for m in live for a in m.get('assets', [])):
        return None
    if not any(m.get('images') for m in live):
        return None
    context = intake.context_gate.build(run, live)
    batch = context.get('batch', [])
    if not requested(run['thread_id'], batch):
        return None
    # No historical image guessing: this feature only authorizes this settled batch.
    consent = restoration_consent(dict(context, history=[]))
    ids = {m['message_id'] for m in live}
    if not consent or not set(consent['source_message_ids']) <= ids:
        return None
    return consent


def standalone_raster(intake, run, messages, *, ignore_cutoff=False):
    """Admit standalone raster (.png/.jpg/.jpeg/.webp) customer print batches outside CANAVI/JPG groups."""
    thread = run.get('thread_id', '')
    if thread in JPG_GROUPS | CANAVI_GROUPS or not messages:
        return None
    if not ignore_cutoff:
        marker = Path(intake.store.path).parent / 'standalone-raster-pet-enabled-at'
        if not marker.exists():
            try:
                with marker.open('x') as f:
                    f.write(str(time.time()))
            except FileExistsError:
                pass
            return None
        cutoff = float(marker.read_text())
        if any(float(m.get('timestamp', 0)) < cutoff for m in messages):
            return None

    live = [m for m in messages if not m.get('recalled') and not m.get('revision')]
    if not live:
        return None
    # Vector attachments always take precedence via the native vector pipeline.
    if any(a.get('name', '').lower().endswith(EXTENSIONS) for m in live for a in m.get('assets', [])):
        return None

    customer_msgs = [
        m for m in live
        if m.get('direction', 'incoming') == 'incoming'
        and m.get('role') not in ('staff', 'internal', 'bot')
        and m.get('origin') not in ('staff', 'legacy_bot', 'erp')
    ]
    if not customer_msgs:
        return None

    source_ids = []
    has_raster_file = False
    has_any_image = False
    for m in live:
        if m.get('role') == 'bot':
            continue
        m_has_file = any(
            isinstance(a, dict)
            and a.get('kind') == 'file'
            and a.get('state') == 'ready'
            and str(a.get('name', '')).lower().endswith(RASTER_EXTENSIONS)
            for a in m.get('assets', [])
        )
        m_has_img = bool(m.get('images')) or any(
            isinstance(a, dict) and str(a.get('name', '')).lower().endswith(RASTER_EXTENSIONS)
            for a in m.get('assets', [])
        )
        if m_has_file:
            has_raster_file = True
        if m_has_img:
            has_any_image = True
        if m_has_file or m_has_img:
            source_ids.append(m['message_id'])

    if not has_any_image:
        return None

    all_text = ' '.join(norm(m.get('text', '')) for m in customer_msgs)
    # Exclude non-PET techniques explicitly requested.
    if re.search(r'CHUYEN NHIET|SUBLIMATION|IN LUOI|KEO LUA|KHONG\s+IN\s+PET|KO\s+IN\s+PET', all_text):
        return None

    has_print_sample_cue = bool(requested(thread, live) or pet_requested(thread, live))
    has_explicit_print_or_dim = False
    for m in customer_msgs:
        for clause in re.split(r'[.!?;\n]', norm(m.get('text', ''))):
            if re.search(r'\b(KHONG|KO|CHUA|DUNG|KHOAN|HUY)\b', clause):
                continue
            has_in = bool(re.search(r'\bIN\b', clause))
            has_dim = bool(
                re.search(r'\b(?:NGANG|CAO|RONG|DAI|KT|KICH THUOC)\s*[:=]?\s*\d+(?:[.,]\d+)?(?:\s*(?:CM|MM))?\b', clause)
                or re.search(r'\b\d+(?:[.,]\d+)?\s*(?:CM|MM)\b', clause)
            )
            has_sample_or_pos = bool(
                re.search(r'\b(?:LAM\s+MAU|LEN\s+MAU|RA\s+MAU|IN\s+PET|MAT\s+TRUOC|MAT\s+SAU|HONG|BEN\s+HONG|MAC|NON|AO|TUI)\b', clause)
            )
            if has_in or (has_raster_file and (has_dim or has_sample_or_pos)):
                has_explicit_print_or_dim = True
                break
        if has_explicit_print_or_dim:
            break

    # Embroidery-only batches (contains THEU without IN / sample PET / raster file print cue) stay out.
    if re.search(r'\bTHEU\b', all_text) and not has_print_sample_cue and not has_explicit_print_or_dim:
        return None

    if not (has_print_sample_cue or (has_explicit_print_or_dim and (has_raster_file or re.search(r'\bIN\b', all_text)))):
        return None

    return {
        'method': 'standalone_raster_pet',
        'has_raster_file': has_raster_file,
        'source_message_ids': source_ids,
    }
