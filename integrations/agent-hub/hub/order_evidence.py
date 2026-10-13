"""ERP-compatible PNG evidence; original images remain in the NAS archive."""

import base64
from io import BytesIO

from PIL import Image, ImageDraw, ImageOps

from hub.media import decode_image


def evidence_png(images, conversation, message_ids):
    if not images:
        return None
    frames = []
    for item in images[:2]:
        with Image.open(BytesIO(decode_image(item))) as source:
            if source.width * source.height > 24_000_000:
                raise ValueError("Order evidence image too large")
            frame = ImageOps.exif_transpose(source).convert("RGB")
            frame.thumbnail((1400, 1800))
            frames.append(frame)
    width = max(600, max(frame.width for frame in frames))
    canvas = Image.new("RGB", (width, 64 + sum(frame.height + 16 for frame in frames)), "white")
    ImageDraw.Draw(canvas).text(
        (12, 12),
        f"Chatwoot #{conversation} | Source messages: " + ",".join(map(str, message_ids)),
        fill="black",
    )
    y = 64
    for frame in frames:
        canvas.paste(frame, (0, y))
        y += frame.height + 16
    for _ in range(3):
        buf = BytesIO()
        canvas.save(buf, format="PNG")
        if len(buf.getvalue()) <= 5_000_000:
            return base64.b64encode(buf.getvalue()).decode()
        canvas = canvas.resize((int(canvas.width * 0.75), int(canvas.height * 0.75)))
    raise ValueError("Order evidence exceeds ERP limit")
