"""Render explicitly selected source messages, never fabricated chat screenshots."""

import base64
import hashlib
import json
from datetime import datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

from hub.media import decode_image

VERSION = 1
LOCAL_TIME = timezone(timedelta(hours=7))


def select_sources(db, account, thread, message_ids):
    """Read exact message IDs in one thread; reject recalls, revisions and mixed sources."""
    if not 1 <= len(message_ids) <= 20 or len(set(message_ids)) != len(message_ids):
        raise ValueError("Select 1–20 unique source messages")
    result = []
    for identity in message_ids:
        rows = db.execute(
            "SELECT id,payload FROM captures WHERE account=? AND thread_id=? AND message_id=? ORDER BY revision DESC",
            (account, thread, identity),
        ).fetchall()
        if not rows:
            raise ValueError("Source message not found in selected group")
        capture_id, encoded = rows[0]
        message = json.loads(encoded)
        if message.get("recalled") or message.get("revision", 0):
            raise ValueError("Edited/recalled message requires staff review")
        images = []
        for media_id in message.get("images", []):
            row = db.execute(
                "SELECT mime_type,data FROM media WHERE id=? AND capture_id=?", (media_id, capture_id)
            ).fetchone()
            if not row:
                raise ValueError("Image does not belong to source message")
            images.append({"mime_type": row[0], "data": base64.b64encode(row[1]).decode()})
        result.append({**message, "images": images})
    return sorted(result, key=lambda item: (item["timestamp"], item["message_id"]))


def font(size, bold=False):
    candidates = [
        Path("C:/Windows/Fonts") / ("arialbd.ttf" if bold else "arial.ttf"),
        Path("/usr/share/fonts/truetype/dejavu") / ("DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"),
    ]
    for path in candidates:
        if path.exists():
            return ImageFont.truetype(str(path), size)
    raise ValueError("A Vietnamese-capable TrueType font is required")


def render_document(messages, order_code, notice=None, new_message_ids=None):
    if not messages or len(messages) > 20:
        raise ValueError("Evidence needs 1–20 messages")
    scope = {(m["account"], m["thread_id"]) for m in messages}
    if len(scope) != 1 or len({m["message_id"] for m in messages}) != len(messages):
        raise ValueError("Mixed or duplicated source messages")
    if any(m.get("recalled") or m.get("revision", 0) for m in messages):
        raise ValueError("Edited/recalled source requires staff review")
    ordered = sorted(messages, key=lambda m: (m["timestamp"], m["message_id"]))
    channel = 'WhatsApp' if ordered[0]['thread_id'].endswith('@g.us') else 'Zalo'
    records = []
    for message in ordered:
        record = {k: v for k, v in message.items() if k != "images"}
        record["image_hashes"] = [
            hashlib.sha256(decode_image(i)).hexdigest() for i in message.get("images", [])
        ]
        records.append(record)
    manifest = {
        "version": VERSION,
        "kind": "message_compilation_not_screenshot",
        "order_code": order_code,
        "timezone": "UTC+07:00",
        "selection": "explicit_source_ids",
        "messages": records,
    }
    if notice:
        manifest['system_notice']=notice
        manifest['new_message_ids']=new_message_ids or []
    raw = json.dumps(manifest, sort_keys=True, ensure_ascii=False).encode()
    identity = hashlib.sha256(raw).hexdigest()
    normal, small, strong, title = font(25), font(20), font(25, True), font(34, True)
    width, height, margin = 1400, 1980, 56
    pages, canvas, draw, y = [], None, None, 0

    def page():
        nonlocal canvas, draw, y
        if canvas is not None:
            pages.append(canvas)
        if len(pages) >= 10:
            raise ValueError("Evidence exceeds ERP limit of 10 pages; narrow selection")
        canvas = Image.new("RGB", (width, height), "#ffffff")
        draw = ImageDraw.Draw(canvas)
        draw.rectangle((0, 0, width, 145), fill="#a51d25" if notice else "#15354c")
        draw.text((margin, 25), "THAY ĐỔI SAU DUYỆT — TẠM DỪNG BẢN CŨ" if notice else "BẢN TỔNG HỢP TIN NHẮN", font=title, fill="white")
        draw.text(
            (margin, 82),
            f"Không phải ảnh chụp màn hình {channel} · Nội dung nguồn được giữ nguyên",
            font=small,
            fill="#dcebf1",
        )
        y = 170
        reference_label = "Hồ sơ chốt in: " if order_code.startswith('CHOT-IN-') else "Đơn ERP: "
        lines("Nhóm: " + ordered[0]["display_name"] + "  |  " + reference_label + order_code, strong)
        lines("ID nhóm: " + ordered[0]["thread_id"], small)
        lines("Múi giờ: UTC+07:00  |  Hồ sơ: " + identity[:20], small)
        y += 24

    def ensure(space):
        if y + space > height - 85:
            page()

    def lines(text, face=normal):
        nonlocal y
        # Character wrapping preserves source characters, including long URLs and newlines.
        for paragraph in str(text).split("\n"):
            current = ""
            for char in paragraph:
                if current and draw.textlength(current + char, font=face) > width - 2 * margin:
                    ensure(38)
                    draw.text((margin, y), current, font=face, fill="#182934")
                    y += 36
                    current = ""
                current += char
            ensure(38)
            draw.text((margin, y), current, font=face, fill="#182934")
            y += 36

    page()
    if notice:
        lines('THÔNG BÁO HỆ THỐNG (không phải lời khách):', strong)
        lines(notice)
        y += 24
    for n, message in enumerate(ordered, 1):
        ensure(165)
        stamp = datetime.fromtimestamp(message["timestamp"], LOCAL_TIME).strftime("%d/%m/%Y %H:%M:%S")
        role = f"Tài khoản {channel} trên máy" if message["direction"] == "outgoing" else "Thành viên nhóm"
        lines(f"{n:02d} · {stamp} · {message.get('sender') or '(không có tên)'}", strong)
        lines(role + "  |  ID tin: " + message["message_id"], small)
        if notice:
            lines('TIN/ẢNH BỔ SUNG MỚI' if message['message_id'] in (new_message_ids or []) else 'NGỮ CẢNH TRƯỚC THAY ĐỔI — KHÔNG DÙNG ĐỂ IN TIẾP', strong)
        has_images = bool(message.get("images"))
        if not (has_images and message["text"] == "[Ảnh Zalo lưu trong kho NAS]"):
            lines(message.get("text") or "[Không có nội dung chữ]")
        quote = message.get('quoted_image')
        if quote:
            if not quote['resolved']:
                raise ValueError('Unresolved quoted image')
            lines('Ảnh khách trích dẫn của: ' + quote['sender'], small)
            lines('ID ảnh gốc: ' + quote['message_id'] + ' | ID người gửi: ' + quote['sender_id'], small)
        for item in message.get("images", []):
            with Image.open(BytesIO(decode_image(item))) as original:
                if original.width * original.height > 24_000_000:
                    raise ValueError("Source image too large")
                frame = ImageOps.exif_transpose(original).convert("RGB")
                frame.thumbnail((width - 2 * margin, 1080))
            ensure(frame.height + 48)
            lines("Ảnh đính kèm — bản xem, bản gốc lưu riêng trên NAS", small)
            canvas.paste(frame, (margin, y))
            y += frame.height + 16
        for asset in message.get("assets", []):
            lines("Tệp nguồn: " + asset["name"], small)
            if asset.get("sha256"):
                lines("SHA256 gốc: " + asset["sha256"], small)
        y += 12
        ensure(24)
        draw.line((margin, y, width - margin, y), fill="#c9d5df", width=2)
        y += 25
    pages.append(canvas)
    output = []
    for n, canvas in enumerate(pages, 1):
        ImageDraw.Draw(canvas).text(
            (margin, height - 55),
            f"{order_code} · Trang {n}/{len(pages)} · Nguồn: dữ liệu tin nhắn {channel} đã thu nhận",
            font=small,
            fill="#536574",
        )
        buf = BytesIO()
        canvas.save(buf, format="PNG", optimize=True)
        if len(buf.getvalue()) > 5_000_000:
            # Keep all text at full resolution; reduce palette only for ERP's upload limit.
            buf = BytesIO()
            canvas.quantize(colors=256).save(buf, format="PNG", optimize=True)
        if len(buf.getvalue()) > 5_000_000:
            raise ValueError("PNG exceeds ERP limit")
        output.append(buf.getvalue())
    return identity, manifest, output


def erp_evidence_png(document):
    """Join complete evidence pages for the ERP's single-image API, without cropping."""
    root = Path(document['directory'])
    frames = []
    for page in document['pages']:
        raw = (root / page['name']).read_bytes()
        if hashlib.sha256(raw).hexdigest() != page['sha256']:
            raise ValueError('Evidence page hash mismatch')
        with Image.open(BytesIO(raw)) as img:
            frames.append(img.convert('RGB'))
    if not frames:
        raise ValueError('No evidence pages')
    width, height = max(f.width for f in frames), sum(f.height for f in frames)
    if width * height > 24_000_000:
        raise ValueError('Combined evidence exceeds pixel limit')
    canvas = Image.new('RGB', (width, height), 'white')
    y = 0
    for frame in frames:
        canvas.paste(frame, (0, y))
        y += frame.height
    buffer = BytesIO()
    canvas.save(buffer, format='PNG', optimize=True)
    data = buffer.getvalue()
    if len(data) > 5_000_000:
        raise ValueError('Combined evidence exceeds ERP limit')
    destination = root / 'erp-all-pages.png'
    if destination.exists() and destination.read_bytes() != data:
        raise ValueError('Existing combined evidence mismatch')
    destination.write_bytes(data)
    return data


def save_document(messages, order_code, nas_root, notice=None, new_message_ids=None):
    from zalo_desktop.vault import safe_name

    identity, manifest, pages = render_document(messages, order_code, notice, new_message_ids)
    root = (
        Path(nas_root)
        / safe_name(messages[0]["display_name"])
        / "orders"
        / safe_name(order_code)
        / ("evidence-" + identity[:16])
    )
    root.mkdir(parents=True, exist_ok=True)
    files = []
    for n, content in enumerate(pages, 1):
        path = root / f"page-{n:03}.png"
        digest = hashlib.sha256(content).hexdigest()
        if path.exists():
            if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
                raise ValueError("Existing evidence differs; never overwrite")
        else:
            temporary = path.with_suffix(".part")
            temporary.write_bytes(content)
            temporary.replace(path)
        if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise OSError("NAS evidence verification failed")
        files.append({"name": path.name, "sha256": digest, "size": len(content)})
    record = {**manifest, "document_id": identity, "pages": files}
    content = json.dumps(record, ensure_ascii=False, sort_keys=True, indent=2).encode()
    path = root / "source.json"
    if path.exists() and path.read_bytes() != content:
        raise ValueError("Existing evidence manifest differs")
    temporary = root / "source.part"
    temporary.write_bytes(content)
    temporary.replace(path)
    return {
        "document_id": identity,
        "directory": str(root),
        "pages": files,
        "source_message_ids": [m["message_id"] for m in manifest["messages"]],
    }
