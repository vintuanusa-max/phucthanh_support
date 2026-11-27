"""Short, readable output filenames with _LLM suffix and NEO_ prefix for NEO JPG groups."""
import re
import unicodedata
from pathlib import PurePosixPath

NEO_THREADS = frozenset({
    'g5402324928935037742',  # AN NGUYEN
    'g3427098896227768665',  # INJAE
    'g7815994588016353953',  # A CHAU
})

NEO_FOLDERS = frozenset({'AN NGUYEN', 'INJAE', 'A CHAU'})

_RESERVED_WINDOWS = {
    'CON', 'PRN', 'AUX', 'NUL',
    *{f'COM{i}' for i in range(1, 10)},
    *{f'LPT{i}' for i in range(1, 10)},
}

_KNOWN_EXTS = {
    '.pdf', '.ai', '.cdr', '.psd', '.psb', '.tif', '.tiff',
    '.jpg', '.jpeg', '.png', '.eps', '.svg',
}

_PANEL_TAIL_RE = re.compile(
    r'[_-]+(position_\d+|page_\d+|p\d+|front|back|left|right|brim|label|font|mt|ms|vai_met|front_back)$',
    re.I,
)

_LEADING_NOISE_PATTERNS = (
    re.compile(r'^(?:(?:NEO|MNT)[_\s.-]+)+', re.I),
    re.compile(
        r'^(?:FILE[\s_]*IN[\s_]*(?:PET|CN|CHUYEN[\s_]*NHIET|CHUYENNHIET)'
        r'|FILEIN(?:PET|CN)'
        r'|FILE[\s_]*IN(?=[_\s.-]|$)'
        r'|IN[\s_]+VAI[\s_]+IN(?=[_\s.-]|$)|IN[\s_]+VAI(?=[_\s.-]|$)|IN[\s_]+PET(?=[_\s.-]|$)|IN[\s_]+CN(?=[_\s.-]|$)|VAI[\s_]+IN(?=[_\s.-]|$)'
        r'|MAU[\s_]+IN(?=[_\s.-]|$)|MAQUETTE(?=[_\s.-]|$)|MAKET(?=[_\s.-]|$)|BO[\s_]*MK(?=[_\s.-]|$)|BOMK(?=[_\s.-]|$)|MK(?=[_\s.-]|$))[\s._-]*',
        re.I,
    ),
    re.compile(
        r'^(?:NON[\s_]+LUOI[\s_]+TRAI|NON[\s_]+TAI[\s_]+BEO|NON[\s_]+KET|NON[\s_]+COTTON'
        r'|NONLUOITRAI|NONTAIBEO|TUI[\s_]+VAI|TUI[\s_]+CANVAS|AO[\s_]+THUN)(?=[_\s.-]|$)[\s._-]*',
        re.I,
    ),
)

_TRAILING_NOISE_RE = re.compile(
    r'(?:[\s._-]+(?:merged|compressed|final|copy|trang)(?:[\s._-]*(?:\(\d+\)|\d+))?|\s*\(\d+\))$',
    re.I,
)


def _ascii(text):
    s = unicodedata.normalize('NFD', str(text or '').replace('đ', 'd').replace('Đ', 'D'))
    return ''.join(c for c in s if not unicodedata.combining(c))


def normalized_group_name(group):
    return re.sub(r'\s+', ' ', _ascii(group).upper()).strip()


def is_neo_group(group='', thread_id=''):
    if str(thread_id or '').strip() in NEO_THREADS:
        return True
    return normalized_group_name(group) in NEO_FOLDERS


def _alnum_count(text):
    return len(re.findall(r'[A-Za-z0-9]', text or ''))


def _compact_panel_suffix(raw_suffix):
    low = raw_suffix.lower()
    if low.startswith('position_'):
        return '_P' + low.split('_', 1)[1]
    if low.startswith('page_'):
        return '_P' + low.split('_', 1)[1]
    if low in ('mt', 'ms') or re.fullmatch(r'p\d+', low):
        return '_' + low.upper()
    return '_' + low


def _split_stem_and_panel(raw_name):
    s = str(raw_name or '').strip()
    if not s:
        return '', ''
    leaf = s.replace('\\', '/').split('/')[-1]
    p = PurePosixPath(leaf)
    stem = p.stem if p.suffix.lower() in _KNOWN_EXTS else leaf
    stem = re.sub(r'^[a-f0-9]{12}__', '', stem, flags=re.I)
    stem = _ascii(stem)
    stem = re.sub(r'[_-]+LLM\d*$', '', stem, flags=re.I)
    m = _PANEL_TAIL_RE.search(stem)
    if m and _alnum_count(stem[:m.start()]) >= 2:
        return stem[:m.start()], _compact_panel_suffix(m.group(1))
    return stem, ''


def _clean_body(body):
    cur = body.strip()
    for _ in range(4):
        nxt = _TRAILING_NOISE_RE.sub('', cur).strip()
        if nxt != cur and _alnum_count(nxt) >= 2:
            cur = nxt
        else:
            break
    for _ in range(4):
        changed = False
        for pat in _LEADING_NOISE_PATTERNS:
            nxt = pat.sub('', cur).strip()
            if nxt != cur and _alnum_count(nxt) >= 2:
                cur = nxt
                changed = True
                break
        if not changed:
            break
    cur = re.sub(r'(?:_-\s*|\s*-_|\s+-\s+|_-_)+', '_', cur)
    cur = re.sub(r'[\s]+', '_', cur)
    cur = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', cur)
    cur = re.sub(r'[^A-Za-z0-9_.-]', '_', cur)
    cur = re.sub(r'\.{2,}', '_', cur)
    cur = re.sub(r'[_-]+-[_-]+', '_', cur)
    cur = re.sub(r'_{2,}', '_', cur)
    cur = cur.strip('._-')
    return cur


def _truncate_body(body, limit):
    if len(body) <= limit:
        return body
    parts = [p for p in body.split('_') if p]
    if len(parts) > 1:
        kept = []
        cur_len = 0
        for part in parts:
            add_len = len(part) + (1 if kept else 0)
            if cur_len + add_len <= limit:
                kept.append(part)
                cur_len += add_len
            else:
                break
        if kept:
            return '_'.join(kept)
    return body[:limit].rstrip('._-')


def short_output_stem(raw_name, *, max_len=32):
    """Return a concise, ASCII, filesystem-safe stem preserving model code and side/panel."""
    if not isinstance(raw_name, str) or not raw_name.strip():
        raise ValueError('Missing output filename')
    body_raw, panel_suffix = _split_stem_and_panel(raw_name)
    body = _clean_body(body_raw)
    if not body:
        # Fallback if all tokens were stripped as boilerplate
        body = _clean_body(_ascii(PurePosixPath(raw_name.replace('\\', '/')).stem))
    if not body:
        raise ValueError('Invalid output filename')
    budget = max(8, int(max_len) - len(panel_suffix))
    body = _truncate_body(body, budget)
    stem = (body + panel_suffix).strip('._-')
    if not stem:
        raise ValueError('Invalid output filename')
    if stem.split('.')[0].upper() in _RESERVED_WINDOWS:
        stem = 'FILE_' + stem
    return stem


def llm_copy_filename(source_stem, suffix, *, group='', thread_id='', source_name='', max_len=32):
    """Build `<short_stem>_LLM<ext>` or `NEO_<short_stem>_LLM<ext>` for NEO JPG groups."""
    ext = (suffix or '').lower()
    if ext not in ('.jpg', '.jpeg', '.tif', '.tiff'):
        raise ValueError('Not final JPG/TIFF')
    chosen_raw = source_stem
    if source_name:
        src_body_raw, _ = _split_stem_and_panel(source_name)
        stem_body_raw, panel_suffix = _split_stem_and_panel(source_stem)
        src_key = re.sub(r'[^A-Za-z0-9]', '', _clean_body(src_body_raw) or _ascii(src_body_raw)).lower()
        stem_key = re.sub(r'[^A-Za-z0-9]', '', _clean_body(stem_body_raw) or _ascii(stem_body_raw)).lower()
        if src_key and src_key == stem_key:
            chosen_raw = src_body_raw + panel_suffix
    stem = short_output_stem(chosen_raw, max_len=max_len)
    stem = re.sub(r'^(?:(?:NEO|MNT)[_-]+)+', '', stem, flags=re.I)
    stem = re.sub(r'[_-]+LLM\d*$', '', stem, flags=re.I).strip('._-')
    if not stem:
        stem = short_output_stem(source_stem, max_len=max_len)
    prefix = 'NEO_' if ext in ('.jpg', '.jpeg') and is_neo_group(group, thread_id) else ''
    return f'{prefix}{stem}_LLM{ext}'
