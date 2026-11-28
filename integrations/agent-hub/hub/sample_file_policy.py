"""New-message-only sample-file admission; existing group exceptions remain authoritative."""
import re
from pathlib import Path
from hub.source_readiness import norm
from hub.export_routing import JPG_GROUPS,CANAVI_GROUPS
EXTENSIONS=('.ai','.pdf','.psd','.cdr')
def requested(thread,messages,*,allow_sublimation=False):
    if thread in JPG_GROUPS | CANAVI_GROUPS:return False
    if not allow_sublimation:
        for m in messages:
            if m.get('recalled') or m.get('revision') or m.get('role') in ('staff','internal','bot') or m.get('origin') in ('staff','legacy_bot','erp') or m.get('direction')=='outgoing':continue
            text=norm(m.get('text',''))
            if re.search(r'CHUYEN NHIET|SUBLIMATION',text):return False
    for m in messages:
        if m.get('recalled') or m.get('revision') or m.get('role') in ('staff','internal','bot') or m.get('origin') in ('staff','legacy_bot','erp') or m.get('direction')=='outgoing':continue
        for clause in re.split(r'[.!?;\n]',norm(m.get('text',''))):
            if re.search(r'\b(KHONG|KO|CHUA|DUNG|KHOAN|HUY)\b',clause):continue
            has_bulk_qty=bool(re.search(r'\b(?:[2-9]|\d{2,})\s*(?:CAI|CON|BO|AO|NON|MU|TAM|TO|CHIEC|MET|M|SL|C)\b',clause))
            if re.search(r'(?<!\bDA )(?:\b(?:LEN|LAM|RA|XUAT)\s+(?:(?:LAI|THEM|GIUP|DUM|GIUM|CHO|1|MOT|CAI|C|CHI|E|EM|A|ANH)\s+){0,4}MAU(?:\s+(?:PET|LAI|THU|TEST))?\b|\bIN\s+(?:(?:LAI|GIUP|DUM|GIUM|CHO|1|MOT|CAI|C|CHI|E|EM|A|ANH)\s+){0,4}MAU\s+(?:LAI|PET|THU|TEST)\b|\bIN\s+LAI\s+(?:(?:GIUP|DUM|GIUM|CHO|1|MOT|CAI|C|CHI|E|EM|A|ANH)\s+){0,3}MAU\b(?!\s+(?:NAY|CU|DO|KIA|TREN|TRUOC|\d))|\b(?:IN\s+(?:LAI\s+)?(?:THU|TEST)|TEST\s+MAU)\b)',clause):return True
            if not has_bulk_qty and re.search(r'(?<!\bDA )\bIN\s+(?:(?:LAI|GIUP|DUM|GIUM|CHO|1|MOT|CAI|C|CHI|E|EM|A|ANH)\s+){0,4}MAU\b(?!\s+(?:NAY|CU|DO|KIA|TREN|TRUOC|\d))',clause):return True
    return False

def enabled(store,thread,messages,*,allow_sublimation=False):
    marker=Path(store.path).parent/'sample-file-pet-enabled-at'
    if not marker.exists():return False
    cutoff=float(marker.read_text())
    # Require the whole source batch to be new; never pick up historical requests.
    return bool(messages) and all(float(m.get('timestamp',0))>=cutoff for m in messages) and (requested(thread,messages,allow_sublimation=allow_sublimation) or pet_requested(thread,messages))


def pet_requested(thread,messages):
    if thread in JPG_GROUPS | CANAVI_GROUPS:return False
    for m in messages:
        if m.get('recalled') or m.get('revision') or m.get('origin')!='customer' or m.get('role') in ('staff','bot') or m.get('direction')=='outgoing':continue
        for clause in re.split(r'[.!?;\n]',norm(m.get('text',''))):
            if re.search(r'\b(KHONG|KO|CHUA|DUNG|KHOAN|HUY)\b|CHUYEN NHIET|SUBLIMATION',clause):continue
            if re.search(r'\b(?:RA|IN|XUAT)\s+(?:MAU\s+)?PET\b',clause):return True
    return False
