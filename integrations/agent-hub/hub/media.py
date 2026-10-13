"""Bounded image bytes; never fetch arbitrary attachment URLs on the Hub."""

import base64

MAX_IMAGE_BYTES = 4 * 1024 * 1024


def image_mime(data):
    if not 0 < len(data) <= MAX_IMAGE_BYTES:
        raise ValueError("Image size limit")
    if data.startswith(b"\xff\xd8\xff") and data.endswith(b"\xff\xd9"):
        return "image/jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n") and b"IEND" in data[-16:]:
        return "image/png"
    if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return "image/webp"
    raise ValueError("Unsupported or incomplete image")


def decode_image(item):
    data = base64.b64decode(item["data"], validate=True)
    if image_mime(data) != item["mime_type"]:
        raise ValueError("Image MIME mismatch")
    return data
