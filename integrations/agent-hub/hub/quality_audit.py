"""Deterministic pixel and geometry quality audit for Hub JPG and PET exports (Layer 1)."""
from __future__ import annotations

import base64
import io
from pathlib import Path
from typing import Any

from PIL import Image, ImageChops

PX_PER_CM = 300.0 / 2.54
SIZE_TOL_CM = 0.15
WHITE_BG_MIN_RGB = 245
CENTER_TOL_CM = 0.25
INSET_CM = 2.0


def _is_unprinted_white_bag(panel: dict[str, Any]) -> bool:
    """Return True when panel is a bag_panel whose background should be unprinted white fabric."""
    if panel.get('kind') != 'bag_panel':
        return False
    if panel.get('background_mode') not in ('none', None, ''):
        return False
    if panel.get('background_object_id') or panel.get('background_cmyk'):
        return False
    return True


def _load_panel_rgb(
    archive_root: str | Path | None,
    archive_relative: str | None,
    file_name: str | None,
    preview_obj: dict[str, Any] | None,
) -> tuple[Image.Image | None, tuple[int, int] | None, str]:
    """Load final archive JPG at full resolution when readable, falling back to preview PNG."""
    if archive_root and archive_relative and file_name:
        candidate = Path(archive_root) / str(archive_relative).replace('\\', '/') / file_name
        try:
            if candidate.is_file():
                with Image.open(candidate) as im:
                    raw_size = im.size
                    rgb_im = im.convert('RGB')
                return rgb_im, raw_size, 'archive_jpg'
        except OSError:
            pass
    if isinstance(preview_obj, dict) and preview_obj.get('data'):
        try:
            raw = base64.b64decode(preview_obj['data'])
            with Image.open(io.BytesIO(raw)) as im:
                rgb_im = im.convert('RGB')
            return rgb_im, None, 'preview_png'
        except Exception:
            pass
    return None, None, 'missing'


def _clamp_pt(x: float, y: float, width: int, height: int) -> tuple[int, int]:
    return (max(0, min(width - 1, int(round(x)))), max(0, min(height - 1, int(round(y)))))


def _compute_ink_bbox(rgb_im: Image.Image, inset_x: int, inset_y: int) -> tuple[int, int, int, int] | None:
    """Compute ink bbox (any RGB channel < 245) inside the inset region avoiding 1 cm L marks."""
    w, h = rgb_im.size
    if w <= 2 * inset_x + 4 or h <= 2 * inset_y + 4:
        return None
    inner = rgb_im.crop((inset_x, inset_y, w - inset_x, h - inset_y))
    r, g, b = inner.split()
    min_ch = ImageChops.darker(ImageChops.darker(r, g), b)
    mask = min_ch.point(lambda v: 255 if v < WHITE_BG_MIN_RGB else 0)
    return mask.getbbox()


def audit_jpg_export(
    plan: dict[str, Any],
    report: dict[str, Any],
    *,
    archive_root: str | Path | None = None,
    archive_relative: str | None = None,
    previews: list[dict[str, Any]] | None = None,
    verification: dict[str, Any] | None = None,
    sibling_dups: list[dict[str, Any]] | None = None,
    intra_dups: list[dict[str, Any]] | None = None,
    blocked_parts: list[Any] | None = None,
) -> dict[str, Any]:
    """Run deterministic pixel, size, centering, and duplicate checks on a finished JPG export."""
    failures: list[str] = []
    warnings: list[str] = []
    panel_audits: list[dict[str, Any]] = []

    plan_panels = plan.get('panels') or []
    report_panels = report.get('panels') or []

    for idx, (pl, rp) in enumerate(zip(plan_panels, report_panels)):
        name = str(pl.get('name') or rp.get('name') or f'panel_{idx}')
        kind = str(pl.get('kind') or '')
        out_cm = pl.get('output_cm') or rp.get('size_cm') or [0.0, 0.0]
        prev = previews[idx] if previews and idx < len(previews) else None
        rgb_im, raw_size, source = _load_panel_rgb(
            archive_root, archive_relative, rp.get('file'), prev
        )

        entry: dict[str, Any] = {
            'name': name,
            'kind': kind,
            'output_cm': list(out_cm) if isinstance(out_cm, (list, tuple)) else out_cm,
            'pixel_source': source,
        }

        try:
            if source == 'archive_jpg' and raw_size and len(out_cm) == 2:
                actual_w_cm = raw_size[0] / PX_PER_CM
                actual_h_cm = raw_size[1] / PX_PER_CM
                entry['actual_size_cm'] = [round(actual_w_cm, 3), round(actual_h_cm, 3)]
                if (
                    abs(actual_w_cm - float(out_cm[0])) > SIZE_TOL_CM
                    or abs(actual_h_cm - float(out_cm[1])) > SIZE_TOL_CM
                ):
                    failures.append(
                        f"Panel '{name}' sai khổ ảnh thực tế: {actual_w_cm:.2f}×{actual_h_cm:.2f} cm "
                        f"!= {out_cm[0]}×{out_cm[1]} cm"
                    )

            if rgb_im is not None and len(out_cm) == 2 and float(out_cm[0]) > 0 and float(out_cm[1]) > 0:
                w, h = rgb_im.size
                px_x = w / float(out_cm[0])
                px_y = h / float(out_cm[1])
                if _is_unprinted_white_bag(pl):
                    pts = [
                        _clamp_pt(w * 0.5, 1.6 * px_y, w, h),
                        _clamp_pt(w * 0.5, h - 1.6 * px_y, w, h),
                        _clamp_pt(1.6 * px_x, h * 0.5, w, h),
                        _clamp_pt(w - 1.6 * px_x, h * 0.5, w, h),
                        _clamp_pt(INSET_CM * px_x, INSET_CM * px_y, w, h),
                        _clamp_pt(w - INSET_CM * px_x, INSET_CM * px_y, w, h),
                        _clamp_pt(INSET_CM * px_x, h - INSET_CM * px_y, w, h),
                        _clamp_pt(w - INSET_CM * px_x, h - INSET_CM * px_y, w, h),
                    ]
                    samples = [rgb_im.getpixel(pt) for pt in pts]
                    pt_mins = [min(s) for s in samples]
                    min_rgb = [min(s[c] for s in samples) for c in range(3)]
                    dark_count = sum(1 for m in pt_mins if m < WHITE_BG_MIN_RGB)
                    comps = pl.get('components') or []
                    all_inset_x = bool(comps) and all(
                        isinstance(c.get('x_cm'), (int, float)) and c['x_cm'] >= 2.2 for c in comps
                    )
                    entry['white_bg_min_rgb'] = min_rgb
                    entry['white_bg_dark_points'] = dark_count
                    if dark_count >= 5 or (all_inset_x and min(pt_mins) < WHITE_BG_MIN_RGB):
                        failures.append(
                            f"Panel '{name}' nền thân túi không trắng sạch "
                            f"(min RGB={min_rgb}, {dark_count}/8 điểm lề < {WHITE_BG_MIN_RGB})"
                        )

                    inset_x = int(round(INSET_CM * px_x))
                    inset_y = int(round(INSET_CM * px_y))
                    bb = _compute_ink_bbox(rgb_im, inset_x, inset_y)
                    if bb is None:
                        failures.append(f"Panel '{name}' không thấy mực artwork bên trong vùng in")
                    else:
                        left_cm = (bb[0] + inset_x) / px_x
                        top_cm = (bb[1] + inset_y) / px_y
                        right_cm = (w - (bb[2] + inset_x)) / px_x
                        bottom_cm = (h - (bb[3] + inset_y)) / px_y
                        lr_diff_cm = abs(left_cm - right_cm)
                        entry['ink_bbox_cm'] = {
                            'left_cm': round(left_cm, 3),
                            'right_cm': round(right_cm, 3),
                            'top_cm': round(top_cm, 3),
                            'bottom_cm': round(bottom_cm, 3),
                            'lr_diff_cm': round(lr_diff_cm, 4),
                        }
                        if (
                            comps
                            and all(c.get('horizontal_alignment') == 'center' for c in comps)
                            and all_inset_x
                            and lr_diff_cm > CENTER_TOL_CM
                        ):
                            failures.append(
                                f"Panel '{name}' lệch ngang trên ảnh thực tế "
                                f"(trái {left_cm:.2f} cm, phải {right_cm:.2f} cm, "
                                f"lệch {lr_diff_cm:.2f} cm > {CENTER_TOL_CM} cm)"
                            )
                else:
                    ext = rgb_im.getextrema()
                    if all(lo >= 254 and hi == 255 for lo, hi in ext):
                        failures.append(f"Panel '{name}' trắng hoàn toàn (không có nội dung in)")
        finally:
            if rgb_im is not None:
                rgb_im.close()

        panel_audits.append(entry)

    if verification is not None and verification.get('pass') is not True:
        failures.append('AI verification chưa đạt (pass=false)')
    if blocked_parts:
        failures.append(f"Còn {len(blocked_parts)} phần chưa xuất (blocked_parts)")

    for item in sibling_dups or []:
        if isinstance(item, dict):
            warnings.append(str(item.get('reason') or 'Trùng vải mét với hồ sơ song song'))
    for item in intra_dups or []:
        if isinstance(item, dict):
            warnings.append(str(item.get('reason') or 'Trùng panel trong cùng job'))

    if failures:
        status = 'FAIL_AUDIT'
        passed = False
    elif warnings:
        status = 'WARN_DUPLICATE'
        passed = True
    else:
        status = 'PASS_VERIFIED'
        passed = True

    return {
        'version': 'quality-audit-v1',
        'kind': 'jpg',
        'status': status,
        'passed': passed,
        'failures': failures,
        'warnings': warnings,
        'panels': panel_audits,
    }


def audit_pet_export(
    payload: dict[str, Any],
    *,
    root: str | Path | None = None,
    job_id: str | None = None,
) -> dict[str, Any]:
    """Run deterministic policy, dimension, DPI, alpha, and spot_1 checks on a PET export."""
    failures: list[str] = []
    warnings: list[str] = []
    file_audits: list[dict[str, Any]] = []

    files = payload.get('files') or []
    reports = payload.get('reports') or []
    if not files:
        failures.append('PET không có file xuất nào')
    if len(reports) != len(files):
        failures.append(f"Thiếu báo cáo Photoshop TIFF cho PET ({len(reports)}/{len(files)})")

    for idx, info in enumerate(files):
        rep = reports[idx] if idx < len(reports) else {}
        name = str(info.get('name') or f'file_{idx}')
        w_cm = info.get('width_cm')
        h_cm = info.get('height_cm')
        pixels = info.get('pixels') or []
        entry: dict[str, Any] = {
            'name': name,
            'width_cm': w_cm,
            'height_cm': h_cm,
            'pixels': list(pixels) if isinstance(pixels, (list, tuple)) else pixels,
            'spot': rep.get('spot'),
            'spot_nonempty': rep.get('spot_nonempty'),
            'alpha_preserved': rep.get('alpha_preserved'),
        }
        if len(pixels) == 2 and w_cm and h_cm:
            px_w_cm = pixels[0] / PX_PER_CM
            px_h_cm = pixels[1] / PX_PER_CM
            if abs(px_w_cm - float(w_cm)) > SIZE_TOL_CM or abs(px_h_cm - float(h_cm)) > SIZE_TOL_CM:
                failures.append(
                    f"File PET '{name}' sai khổ 300 DPI: {px_w_cm:.2f}×{px_h_cm:.2f} cm != {w_cm}×{h_cm} cm"
                )
        else:
            failures.append(f"File PET '{name}' thiếu thông số pixel/cm hợp lệ")

        if root and job_id:
            png_path = Path(root) / str(job_id) / name
            if not png_path.is_file():
                failures.append(f"Thiếu file PET PNG trên đĩa: {name}")

        if rep.get('spot') != 'spot_1' or rep.get('spot_nonempty') is not True or rep.get('alpha_preserved') is not True:
            failures.append(
                f"TIFF PET '{rep.get('name') or name}' chưa đạt chuẩn spot_1/alpha "
                f"(spot={rep.get('spot')}, nonempty={rep.get('spot_nonempty')}, alpha={rep.get('alpha_preserved')})"
            )
        file_audits.append(entry)

    verif = payload.get('verification') or {}
    if verif.get('pass') is not True:
        failures.append('AI verification PET chưa đạt (pass=false)')
    blocked = payload.get('blocked_parts') or []
    if blocked:
        failures.append(f"PET còn {len(blocked)} phần chưa xuất (blocked_parts)")

    status = 'FAIL_AUDIT' if failures else 'PASS_VERIFIED'
    return {
        'version': 'quality-audit-v1',
        'kind': 'pet',
        'status': status,
        'passed': not failures,
        'failures': failures,
        'warnings': warnings,
        'files': file_audits,
    }


def format_audit_note(audit: dict[str, Any] | None) -> str:
    """Format a concise Vietnamese Chatwoot internal review line from a quality_audit record."""
    if not isinstance(audit, dict) or not audit.get('status'):
        return ''
    status = audit['status']
    if status == 'PASS_VERIFIED':
        head = 'Kiểm định tự động (Quality Audit): ĐẠT CHUẨN (PASS_VERIFIED)'
    elif status == 'WARN_DUPLICATE':
        head = 'Kiểm định tự động (Quality Audit): ĐẠT KÈM CẢNH BÁO TRÙNG (WARN_DUPLICATE)'
    else:
        head = 'Kiểm định tự động (Quality Audit): KHÔNG ĐẠT — CHẶN AUTO-RIP (FAIL_AUDIT)'

    details: list[str] = []
    if audit.get('kind') == 'pet':
        files = audit.get('files') or []
        if files and not audit.get('failures'):
            details.append(f"{len(files)} file TIFF 300 DPI spot_1+alpha đạt chuẩn")
    else:
        for pnl in audit.get('panels') or []:
            parts: list[str] = []
            if pnl.get('white_bg_min_rgb') is not None:
                parts.append(f"nền RGB min={pnl['white_bg_min_rgb']}")
            if isinstance(pnl.get('ink_bbox_cm'), dict):
                bb = pnl['ink_bbox_cm']
                parts.append(f"lệch ngang={bb.get('lr_diff_cm')}cm")
            if parts:
                details.append(f"{pnl.get('name')}: {', '.join(parts)}")

    for msg in (audit.get('failures') or [])[:3]:
        details.append('Lỗi: ' + str(msg))
    for msg in (audit.get('warnings') or [])[:2]:
        details.append('Cảnh báo: ' + str(msg))

    if details:
        return head + ' — ' + '; '.join(details)
    return head
