"""Read the image URL recorded by Desktop; no login, cookies or source writes."""

import base64
import re
from io import BytesIO
from urllib.parse import urljoin, urlsplit

import httpx

from hub.media import MAX_IMAGE_BYTES, image_mime


def normalize_image(raw):
    if raw.startswith((b"\xff\x0a", b"\x00\x00\x00\x0cJXL \r\n\x87\n")):
        import pillow_jxl  # noqa: F401 -- registers the JPEG XL decoder
        from PIL import Image, ImageOps

        with Image.open(BytesIO(raw)) as source:
            if source.width * source.height > 24_000_000 or getattr(source, "n_frames", 1) != 1:
                raise ValueError("Image dimensions/animation unsupported")
            source.load()
            converted = ImageOps.exif_transpose(source).convert("RGB")
            output = BytesIO()
            converted.save(output, format="JPEG", quality=95, subsampling=0)
            raw = output.getvalue()
    return {"mime_type": image_mime(raw), "data": base64.b64encode(raw).decode("ascii")}


def validate_url(url):
    parsed = urlsplit(url)
    if (
        parsed.scheme != "https"
        or not re.fullmatch(r"photo-[a-z0-9-]+\.(zdn|zadn)\.vn", parsed.hostname or "")
        or parsed.port not in (None, 443)
        or parsed.username
        or parsed.password
    ):
        raise ValueError("Unsupported Zalo image URL")


def fetch_image(metadata):
    # Original image only: a thumbnail may omit text needed to answer correctly.
    url = metadata.get("oriUrl", "")
    with httpx.Client(timeout=15, follow_redirects=False, trust_env=False) as client:
        for _ in range(3):
            validate_url(url)
            with client.stream("GET", url) as response:
                if response.status_code in (301, 302, 307, 308):
                    url = urljoin(url, response.headers.get("location", ""))
                    continue
                if response.status_code != 200:
                    raise ValueError("Zalo image download failed")
                if int(response.headers.get("content-length", "0")) > MAX_IMAGE_BYTES:
                    raise ValueError("Image size limit")
                data = bytearray()
                for part in response.iter_bytes(65536):
                    data.extend(part)
                    if len(data) > MAX_IMAGE_BYTES:
                        raise ValueError("Image size limit")
                break
        else:
            raise ValueError("Image redirect limit")
    raw = bytes(data)
    return normalize_image(raw)
