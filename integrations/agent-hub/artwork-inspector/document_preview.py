"""Read-only PDF/PDF-compatible AI previews; original bytes remain untouched."""
import base64
import copy
import hashlib
from io import BytesIO
from pathlib import Path

from PIL import Image

VERSION = "pdf-preview-v1"


def render_asset(root, asset):
    import pymupdf as fitz

    root = Path(root).resolve()
    relative = Path(asset["relative_path"])
    path = (root / relative).resolve()
    if relative.is_absolute() or root not in path.parents:
        raise ValueError("File preview outside NAS archive")
    if path.suffix.lower() not in (".pdf", ".ai") or asset.get("state") != "ready":
        raise ValueError("File preview requires a ready PDF/AI")
    if path.stat().st_size > 32_000_000:
        raise ValueError("File preview exceeds 32 MB")
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != asset["sha256"]:
        raise ValueError("File preview source hash changed")
    if b"%PDF-" not in raw[:1024]:
        raise ValueError("AI has no PDF-compatible content; staff must open in Illustrator")
    pages = []
    with fitz.open(stream=raw, filetype="pdf") as doc:
        if doc.needs_pass or not 1 <= len(doc) <= 8:
            raise ValueError("Encrypted file or more than 8 pages; staff review required")
        for number, page in enumerate(doc, 1):
            if page.rect.width <= 0 or page.rect.height <= 0:
                raise ValueError("Invalid document page")
            scale = min(2, 2400 / max(page.rect.width, page.rect.height))
            pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), colorspace=fitz.csRGB, alpha=False)
            data = pix.tobytes("jpeg", jpg_quality=90)
            if len(data) > 4_000_000:
                raise ValueError("Preview image too large")
            pages.append({
                "mime_type": "image/jpeg", "data": base64.b64encode(data).decode(),
                "preview_label": f"Xem file {asset['name']} — trang {number}/{len(doc)} (không phải file in)",
                "source_sha256": asset["sha256"], "page": number,
            })
    return pages


def enrich(messages, root):
    result = copy.deepcopy(messages)
    count = 0
    for message in result:
        seen = set()
        for asset in message.get("assets", []):
            if Path(asset.get("name", "")).suffix.lower() not in (".pdf", ".ai"):
                continue
            identity = asset.get("sha256") or asset.get("id")
            if identity in seen:
                continue
            seen.add(identity)
            pages = render_asset(root, asset)
            count += len(pages)
            if count > 8:
                raise ValueError("Too many document pages for evidence; staff review required")
            message.setdefault("images", []).extend(pages)
    return result


def contact_sheet(pages):
    """Complete, labelled PNG for customer preview; no cropped/missing pages."""
    from PIL import ImageDraw, ImageFont
    frames = []
    font = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 24)
    for item in pages:
        img = Image.open(BytesIO(base64.b64decode(item["data"]))).convert("RGB")
        img.thumbnail((2000, 1600))
        frame = Image.new("RGB", (2000, img.height + 100), "white")
        ImageDraw.Draw(frame).text((20, 20), item["preview_label"], font=font, fill="black")
        frame.paste(img, ((2000-img.width)//2, 90))
        frames.append(frame)
    height = sum(f.height for f in frames)
    if not frames or height * 2000 > 24_000_000:
        raise ValueError("Preview sheet too large")
    sheet = Image.new("RGB", (2000, height), "white")
    y = 0
    for frame in frames:
        sheet.paste(frame, (0, y))
        y += frame.height
    out = BytesIO()
    sheet.save(out, format="PNG", optimize=True)
    if len(out.getvalue()) > 4_000_000:
        raise ValueError("Preview sheet too large to send")
    return out.getvalue()
