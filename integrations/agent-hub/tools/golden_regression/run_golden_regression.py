"""Golden Regression Runner (Layer 2) for CANAVI / CANAVI HCM2 Hub exports.

Runs inside `phucthanh-chatwoot-hub-1` with `/app/.venv/bin/python`:
  - `--mode audit-latest`: read-only audit of latest done exports + NAS files (0 API/worker cost)
  - `--mode live-replay`: safe sequential dispatch replay via `/dispatch/{brief_id}`
                          with strict safety assertions (`drafts_delta=0`, `deliveries_delta=0`)
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

# Ensure `/app` (or worktree root) is importable regardless of script location
for cand in (os.environ.get('HUB_APP_DIR', '/app'), str(Path(__file__).resolve().parents[2])):
    if cand and cand not in sys.path and (Path(cand) / 'hub').is_dir():
        sys.path.insert(0, cand)

from hub.quality_audit import audit_jpg_export, audit_pet_export  # noqa: E402

BUSY_STATES = {
    'preparing',
    'scheduled',
    'planning',
    'awaiting_upload',
    'queued',
    'reading',
    'exporting',
    'publishing',
    'uncertain',
    'claimed',
}
NATIVE_BUSY_STATES = {
    'scan_queued',
    'scan_running',
    'render_queued',
    'render_running',
    'png_check_queued',
    'uncertain',
}
NATIVE_AUTO_BUSY = {'planning', 'verifying', 'waiting_verify', 'waiting_scan'}
SIZE_TOL_CM = 0.15


def _db_connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, timeout=30.0)
    conn.row_factory = sqlite3.Row
    return conn


def _http_json(url: str, token: str, payload: dict[str, Any] | None = None, timeout: int = 30) -> Any:
    headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}
    data = json.dumps(payload, ensure_ascii=False).encode('utf-8') if payload is not None else None
    req = urllib.request.Request(url, data=data, headers=headers, method='POST' if data is not None else 'GET')
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode('utf-8'))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode('utf-8', errors='replace')
        raise RuntimeError(f'HTTP {exc.code} on {url}: {body[:400]}') from exc


def _check_case_outputs(
    conn: sqlite3.Connection,
    case: dict[str, Any],
    archive_root: str,
    *,
    min_created: float | None = None,
    require_persisted_audit: bool = False,
) -> dict[str, Any]:
    bid = case['brief_id']
    exp_pp = case['expected_process']
    exp_pet_cnt = int(case.get('expected_pet_count', 0))
    exp_panels = case.get('expected_jpg_panels') or []
    allow_dup = bool(case.get('allow_warn_duplicate', False))

    failures: list[str] = []
    warnings: list[str] = []
    metrics: dict[str, Any] = {}

    is_raster_pet = bool(case.get('raster_pet'))
    if is_raster_pet:
        actual_pp = exp_pp
        metrics['print_process'] = actual_pp
        metrics['ac_state'] = 'raster_pet'
        ac_created = float(min_created or 0.0)
    else:
        ac_sql = 'SELECT id, state, created, payload, result FROM artwork_checks WHERE brief_id=?'
        ac_params: list[Any] = [bid]
        if min_created is not None:
            ac_sql += ' AND created >= ?'
            ac_params.append(min_created)
        ac_sql += ' ORDER BY created DESC LIMIT 1'
        ac = conn.execute(ac_sql, ac_params).fetchone()
        if not ac:
            failures.append('Không tìm thấy artwork_checks')
            return {'name': case['name'], 'passed': False, 'status': 'FAIL', 'failures': failures, 'warnings': warnings, 'metrics': metrics}

        ac_res = json.loads(ac['result'] or '{}')
        comp = ac_res.get('comparison') or {}
        actual_pp = comp.get('print_process')
        metrics['print_process'] = actual_pp
        metrics['ac_state'] = ac['state']
        if actual_pp != exp_pp:
            failures.append(f"print_process={actual_pp} != expected {exp_pp}")

        ac_created = float(ac['created'])

    # Check JPG stream
    if exp_pp in ('sublimation', 'both'):
        j_sql = "SELECT id, state, created, payload FROM jpg_exports WHERE state='done' AND json_extract(payload,'$.brief_id')=?"
        j_params: list[Any] = [bid]
        if min_created is not None:
            j_sql += ' AND created >= ?'
            j_params.append(min_created)
        j_sql += ' ORDER BY created DESC LIMIT 1'
        jr = conn.execute(j_sql, j_params).fetchone()
        if not jr:
            failures.append('Thiếu jpg_exports done')
        else:
            jp = json.loads(jr['payload'] or '{}')
            verif = jp.get('verification') or {}
            if verif.get('pass') is not True:
                failures.append(f"JPG verification.pass={verif.get('pass')}")
            if jp.get('manual_intervention') is not None:
                failures.append(f"JPG có manual_intervention={jp.get('manual_intervention')}")

            report = jp.get('report') or {}
            plan = jp.get('plan') or {}
            live_audit = audit_jpg_export(
                plan,
                report,
                archive_root=archive_root,
                archive_relative=jp.get('archive_relative'),
                verification=verif,
                sibling_dups=jp.get('sibling_duplicate_panels'),
                intra_dups=jp.get('post_export_duplicate_panels'),
                blocked_parts=plan.get('blocked_parts'),
            )
            metrics['jpg_audit_status'] = live_audit['status']
            metrics['jpg_job_id'] = jr['id'][:10]
            metrics['jpg_panels'] = len(plan.get('panels') or [])

            persisted = jp.get('quality_audit')
            if persisted:
                metrics['jpg_persisted_audit'] = persisted.get('status')
            elif require_persisted_audit:
                failures.append('JPG chưa lưu payload.quality_audit trong DB')

            if not live_audit['passed']:
                failures.extend(live_audit['failures'])
            if live_audit['status'] == 'WARN_DUPLICATE' and not allow_dup:
                failures.append(f"Không mong đợi WARN_DUPLICATE: {live_audit['warnings']}")
            elif live_audit['warnings']:
                warnings.extend(live_audit['warnings'])

            actual_panels = plan.get('panels') or []
            if len(actual_panels) != len(exp_panels):
                failures.append(f"Số panel JPG={len(actual_panels)} != expected {len(exp_panels)}")
            else:
                for idx, (ap, ep) in enumerate(zip(actual_panels, exp_panels)):
                    if ap.get('kind') != ep.get('kind'):
                        failures.append(f"Panel {idx} kind={ap.get('kind')} != expected {ep.get('kind')}")
                    a_cm = ap.get('output_cm') or [0, 0]
                    e_cm = ep.get('output_cm') or [0, 0]
                    if len(a_cm) != 2 or abs(float(a_cm[0]) - float(e_cm[0])) > SIZE_TOL_CM or abs(float(a_cm[1]) - float(e_cm[1])) > SIZE_TOL_CM:
                        failures.append(f"Panel {idx} khổ={a_cm} != expected {e_cm}")

            for pa in live_audit.get('panels') or []:
                if pa.get('white_bg_min_rgb') is not None:
                    metrics['white_rgb_min'] = pa['white_bg_min_rgb']
                if isinstance(pa.get('ink_bbox_cm'), dict):
                    metrics['lr_diff_cm'] = pa['ink_bbox_cm'].get('lr_diff_cm')
    else:
        j_recent = conn.execute(
            "SELECT id, state FROM jpg_exports WHERE json_extract(payload,'$.brief_id')=? AND created >= ? AND state NOT IN ('superseded','not_jpg') LIMIT 1",
            (bid, ac_created - 0.5 if min_created is None else min_created),
        ).fetchone()
        if j_recent:
            failures.append(f"Mẫu PET lại phát sinh jpg_exports ({j_recent['id'][:10]}, {j_recent['state']})")

    # Check PET stream
    if exp_pp in ('pet', 'both'):
        p_sql = "SELECT id, state, created, payload FROM pet_exports WHERE state='done' AND json_extract(payload,'$.brief_id')=?"
        p_params: list[Any] = [bid]
        if min_created is not None:
            p_sql += ' AND created >= ?'
            p_params.append(min_created)
        p_sql += ' ORDER BY created DESC LIMIT 1'
        pr = conn.execute(p_sql, p_params).fetchone()
        if not pr:
            failures.append('Thiếu pet_exports done')
        else:
            pp = json.loads(pr['payload'] or '{}')
            verif = pp.get('verification') or {}
            if verif.get('pass') is not True:
                failures.append(f"PET verification.pass={verif.get('pass')}")
            if pp.get('manual_intervention') is not None:
                failures.append(f"PET có manual_intervention={pp.get('manual_intervention')}")

            pet_audit = audit_pet_export(pp)
            metrics['pet_audit_status'] = pet_audit['status']
            metrics['pet_job_id'] = pr['id'][:10]
            metrics['pet_files'] = len(pp.get('files') or [])

            persisted = pp.get('quality_audit')
            if persisted:
                metrics['pet_persisted_audit'] = persisted.get('status')
            elif require_persisted_audit:
                failures.append('PET chưa lưu payload.quality_audit trong DB')

            if not pet_audit['passed']:
                failures.extend(pet_audit['failures'])

            files = pp.get('files') or []
            if len(files) != exp_pet_cnt:
                failures.append(f"Số file PET={len(files)} != expected {exp_pet_cnt}")
            exp_pet_sizes = case.get('expected_pet_sizes_cm') or []
            for idx, (f_info, e_sz) in enumerate(zip(files, exp_pet_sizes)):
                if abs(float(f_info.get('width_cm', 0)) - float(e_sz[0])) > SIZE_TOL_CM or abs(float(f_info.get('height_cm', 0)) - float(e_sz[1])) > SIZE_TOL_CM:
                    failures.append(f"PET file {idx} khổ={[f_info.get('width_cm'), f_info.get('height_cm')]} != expected {e_sz}")
    else:
        p_recent = conn.execute(
            "SELECT id, state FROM pet_exports WHERE json_extract(payload,'$.brief_id')=? AND created >= ? AND state != 'superseded' LIMIT 1",
            (bid, ac_created - 0.5 if min_created is None else min_created),
        ).fetchone()
        if p_recent:
            failures.append(f"Mẫu JPG-only lại phát sinh pet_exports ({p_recent['id'][:10]}, {p_recent['state']})")

    status = 'FAIL' if failures else ('WARN_DUPLICATE' if warnings else 'PASS')
    return {
        'name': case['name'],
        'brief_id': bid,
        'passed': not failures,
        'status': status,
        'failures': failures,
        'warnings': warnings,
        'metrics': metrics,
    }


def _active_counts(conn: sqlite3.Connection) -> dict[str, int]:
    ph = ','.join('?' for _ in BUSY_STATES)
    nph = ','.join('?' for _ in NATIVE_BUSY_STATES)
    aph = ','.join('?' for _ in NATIVE_AUTO_BUSY)
    out = {
        'artwork_checks': conn.execute(f'SELECT COUNT(*) FROM artwork_checks WHERE state IN ({ph})', tuple(BUSY_STATES)).fetchone()[0],
        'jpg_exports': conn.execute(f'SELECT COUNT(*) FROM jpg_exports WHERE state IN ({ph})', tuple(BUSY_STATES)).fetchone()[0],
        'pet_exports': conn.execute(f'SELECT COUNT(*) FROM pet_exports WHERE state IN ({ph})', tuple(BUSY_STATES)).fetchone()[0],
        'dossiers': conn.execute('SELECT COUNT(*) FROM worker_fleet_dossiers').fetchone()[0],
        'native_selections': conn.execute(
            f"SELECT COUNT(*) FROM native_selections WHERE state IN ({nph}) OR json_extract(payload,'$.auto_status') IN ({aph})",
            tuple(NATIVE_BUSY_STATES) + tuple(NATIVE_AUTO_BUSY),
        ).fetchone()[0],
    }
    return out


def _brief_still_running(conn: sqlite3.Connection, bid: str, min_created: float) -> bool:
    ph = ','.join('?' for _ in BUSY_STATES)
    nph = ','.join('?' for _ in NATIVE_BUSY_STATES)
    aph = ','.join('?' for _ in NATIVE_AUTO_BUSY)
    if conn.execute(f'SELECT 1 FROM artwork_checks WHERE brief_id=? AND created>=? AND state IN ({ph}) LIMIT 1', (bid, min_created, *BUSY_STATES)).fetchone():
        return True
    if conn.execute(f"SELECT 1 FROM jpg_exports WHERE json_extract(payload,'$.brief_id')=? AND created>=? AND state IN ({ph}) LIMIT 1", (bid, min_created, *BUSY_STATES)).fetchone():
        return True
    if conn.execute(f"SELECT 1 FROM pet_exports WHERE json_extract(payload,'$.brief_id')=? AND created>=? AND state IN ({ph}) LIMIT 1", (bid, min_created, *BUSY_STATES)).fetchone():
        return True
    if conn.execute(
        f"SELECT 1 FROM native_selections WHERE brief_id=? AND created>=? AND (state IN ({nph}) OR json_extract(payload,'$.auto_status') IN ({aph})) LIMIT 1",
        (bid, min_created, *NATIVE_BUSY_STATES, *NATIVE_AUTO_BUSY),
    ).fetchone():
        return True
    if conn.execute("SELECT 1 FROM worker_fleet_dossiers WHERE brief=? LIMIT 1", (bid,)).fetchone():
        return True
    return False


def _run_live_case(
    conn: sqlite3.Connection,
    case: dict[str, Any],
    base_url: str,
    token: str,
    archive_root: str,
    timeout_s: int,
) -> dict[str, Any]:
    bid = case['brief_id']
    detail = _http_json(f'{base_url}/dispatch/{bid}', token)
    ws = detail.get('workspace') or {}
    if ws.get('busy'):
        return {
            'name': case['name'],
            'brief_id': bid,
            'passed': False,
            'status': 'FAIL',
            'failures': ['Workspace đang bận trước khi chạy'],
            'warnings': [],
            'metrics': {},
        }
    revision = ws.get('revision')
    spec = case['spec']
    t0 = time.time() - 0.5
    payload = {
        'action': 'resume_workspace',
        'expected_revision': revision,
        'sha256': case['sha256'],
        'export_spec': {'mode': spec['mode'], 'field_answers': spec.get('field_answers', {})},
        'source_ids': spec['source_ids'],
        'sources_confirmed': True,
        'note': f"golden-regression-live-replay {case['name']}",
    }
    resp = _http_json(f'{base_url}/dispatch/{bid}', token, payload=payload)
    dispatch_id = resp.get('id', '')

    exp_pp = case['expected_process']
    deadline = time.time() + timeout_s
    settled_since: float | None = None
    while time.time() < deadline:
        time.sleep(3)
        ac = conn.execute(
            'SELECT id, state, result FROM artwork_checks WHERE brief_id=? AND created>=? ORDER BY created DESC LIMIT 1',
            (bid, t0),
        ).fetchone()
        if not ac:
            continue
        if _brief_still_running(conn, bid, t0):
            settled_since = None
            continue
        # Check if expected exports are already materialized
        has_jpg = bool(conn.execute("SELECT 1 FROM jpg_exports WHERE json_extract(payload,'$.brief_id')=? AND created>=? LIMIT 1", (bid, t0)).fetchone())
        has_pet = bool(conn.execute("SELECT 1 FROM pet_exports WHERE json_extract(payload,'$.brief_id')=? AND created>=? LIMIT 1", (bid, t0)).fetchone())
        ac_res = json.loads(ac['result'] or '{}')
        errs = ac_res.get('errors') or []
        if ac['state'] == 'review' and errs and not has_jpg and not has_pet:
            break
        want_jpg = exp_pp in ('sublimation', 'both')
        want_pet = exp_pp in ('pet', 'both')
        if (not want_jpg or has_jpg) and (not want_pet or has_pet):
            # All expected exports finished and no longer busy
            if settled_since is None:
                settled_since = time.time()
            if time.time() - settled_since >= 2.0:
                break
    else:
        return {
            'name': case['name'],
            'brief_id': bid,
            'passed': False,
            'status': 'FAIL',
            'failures': [f'Timeout sau {timeout_s}s khi chờ live-replay {dispatch_id[:10]}'],
            'warnings': [],
            'metrics': {},
        }

    res = _check_case_outputs(conn, case, archive_root, min_created=t0, require_persisted_audit=True)
    res['metrics']['dispatch_id'] = dispatch_id[:10]
    res['metrics']['elapsed_s'] = round(time.time() - t0, 1)
    return res


def _print_summary(results: list[dict[str, Any]], safety: dict[str, Any] | None = None) -> None:
    print('\n=== GOLDEN REGRESSION SUMMARY ===')
    print(f"{'CASE':<16} {'PROC':<12} {'STATUS':<15} {'METRICS'}")
    print('-' * 95)
    for r in results:
        m = r.get('metrics') or {}
        proc = str(m.get('print_process') or '-')
        parts = []
        if m.get('jpg_job_id'):
            parts.append(f"jpg={m['jpg_job_id']}({m.get('jpg_persisted_audit') or m.get('jpg_audit_status')})")
        if m.get('pet_job_id'):
            parts.append(f"pet={m['pet_job_id']}({m.get('pet_persisted_audit') or m.get('pet_audit_status')})")
        if m.get('white_rgb_min') is not None:
            parts.append(f"rgb_min={m['white_rgb_min']}")
        if m.get('lr_diff_cm') is not None:
            parts.append(f"lr_diff={m['lr_diff_cm']}cm")
        if m.get('elapsed_s') is not None:
            parts.append(f"{m['elapsed_s']}s")
        print(f"{r['name']:<16} {proc:<12} {r['status']:<15} {' | '.join(parts)}")
        for msg in r.get('failures') or []:
            print(f"   [FAIL] {msg}")
        for msg in r.get('warnings') or []:
            print(f"   [WARN] {msg}")
    passed = sum(1 for r in results if r['passed'])
    print('-' * 95)
    print(f'TOTAL: {passed}/{len(results)} PASSED')
    if safety:
        print('SAFETY:', json.dumps(safety, ensure_ascii=False))


def main() -> int:
    parser = argparse.ArgumentParser(description='Layer 2 Golden Regression Runner')
    parser.add_argument('--mode', choices=['audit-latest', 'live-replay'], default='audit-latest')
    parser.add_argument('--cases', default='', help='Comma-separated case names (default: all)')
    parser.add_argument('--cases-file', default=str(Path(__file__).with_name('golden_cases.json')))
    parser.add_argument('--db', default=os.environ.get('HUB_DATABASE', '/data/hub.sqlite3'))
    parser.add_argument('--archive-root', default=os.environ.get('HUB_SOURCE_ARCHIVE', '/source-archive'))
    parser.add_argument('--hub-url', default='http://127.0.0.1:8095')
    parser.add_argument('--timeout', type=int, default=420)
    parser.add_argument('--report-out', default='')
    args = parser.parse_args()

    raw_cases = json.loads(Path(args.cases_file).read_text(encoding='utf-8'))['cases']
    if args.cases.strip():
        wanted = {x.strip().upper() for x in args.cases.split(',') if x.strip()}
        selected = [c for c in raw_cases if c['name'].upper() in wanted]
        missing = wanted - {c['name'].upper() for c in selected}
        if missing:
            print(f'Unknown cases: {sorted(missing)}', file=sys.stderr)
            return 2
    else:
        selected = raw_cases

    conn = _db_connect(args.db)
    safety: dict[str, Any] | None = None
    results: list[dict[str, Any]] = []

    try:
        if args.mode == 'audit-latest':
            for case in selected:
                results.append(_check_case_outputs(conn, case, args.archive_root, require_persisted_audit=False))
        else:
            token = os.environ.get('HUB_ADMIN_TOKEN', '').strip()
            if not token:
                print('HUB_ADMIN_TOKEN missing in environment', file=sys.stderr)
                return 2
            active_before = _active_counts(conn)
            if any(v > 0 for v in active_before.values()):
                print(f'Refusing live-replay while queues are active: {active_before}', file=sys.stderr)
                return 2
            drafts_before = conn.execute('SELECT COUNT(*) FROM drafts').fetchone()[0]
            deliveries_before = conn.execute('SELECT COUNT(*) FROM deliveries').fetchone()[0]

            for case in selected:
                results.append(_run_live_case(conn, case, args.hub_url.rstrip('/'), token, args.archive_root, args.timeout))

            # Brief settle for final dossier cleanup
            for _ in range(10):
                active_after = _active_counts(conn)
                if all(v == 0 for v in active_after.values()):
                    break
                time.sleep(2)
            active_after = _active_counts(conn)
            drafts_after = conn.execute('SELECT COUNT(*) FROM drafts').fetchone()[0]
            deliveries_after = conn.execute('SELECT COUNT(*) FROM deliveries').fetchone()[0]
            safety = {
                'drafts_delta': drafts_after - drafts_before,
                'deliveries_delta': deliveries_after - deliveries_before,
                'active_after': active_after,
            }
            if safety['drafts_delta'] != 0 or safety['deliveries_delta'] != 0 or any(v > 0 for v in active_after.values()):
                results.append({
                    'name': '__SAFETY__',
                    'passed': False,
                    'status': 'FAIL_SAFETY',
                    'failures': [f'Safety invariant violated: {safety}'],
                    'warnings': [],
                    'metrics': {},
                })
    finally:
        conn.close()

    _print_summary(results, safety)
    report_payload = {'mode': args.mode, 'timestamp': time.time(), 'results': results, 'safety': safety}
    if args.report_out:
        Path(args.report_out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.report_out).write_text(json.dumps(report_payload, ensure_ascii=False, indent=2), encoding='utf-8')
    return 0 if all(r['passed'] for r in results) else 1


if __name__ == '__main__':
    raise SystemExit(main())
