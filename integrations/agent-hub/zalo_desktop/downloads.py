"""Bounded public file downloads. No credentials, HTML execution or archive extraction."""

import base64
import ipaddress
import re
import socket
import time
from pathlib import Path
from urllib.parse import parse_qs, unquote, urljoin, urlsplit

import httpx
from httpcore import ConnectError, SyncBackend


class PublicBackend(SyncBackend):
    def connect_tcp(self, host, port, timeout=None, local_address=None, socket_options=None):
        addresses = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
        if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):
            raise ValueError("Private download destination")
        # Pin each validated address for TCP; httpcore still uses the original host for TLS/SNI.
        for address in dict.fromkeys(a[4][0] for a in addresses):
            try:
                return super().connect_tcp(address, port, timeout, local_address, socket_options)
            except ConnectError:
                continue
        raise ConnectError("No public download address reachable")


def download_url(url):
    parsed = urlsplit(url)
    if parsed.hostname == "drive.google.com":
        match = re.search(r"/file/d/([a-zA-Z0-9_-]+)", parsed.path)
        file_id = match[1] if match else parse_qs(parsed.query).get("id", [""])[0]
        if not re.fullmatch(r"[a-zA-Z0-9_-]{10,200}", file_id):
            raise ValueError("Google Drive folder or unsupported share link")
        return "https://drive.usercontent.google.com/download?export=download&id=" + file_id
    if parsed.hostname in {"1drv.ms", "onedrive.live.com"}:
        share = base64.urlsafe_b64encode(url.encode()).decode().rstrip("=")
        return "https://api.onedrive.com/v1.0/shares/u!" + share + "/root/content"
    if parsed.hostname in {"www.dropbox.com", "dropbox.com"}:
        return (
            re.sub(r"([?&])dl=[01]", r"\g<1>dl=1", url)
            if "dl=" in url
            else url + ("&" if parsed.query else "?") + "dl=1"
        )
    return url


def validate_public_url(url):
    parsed = urlsplit(url)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.port not in (None, 443)
    ):
        raise ValueError("Only public HTTPS file links are supported")
    addresses = socket.getaddrinfo(parsed.hostname, 443, type=socket.SOCK_STREAM)
    if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):
        raise ValueError("Private or reserved download destination")


def filename_from_response(response, url):
    disposition = response.headers.get("content-disposition", "")
    encoded = re.search(r"filename\*=UTF-8''([^;]+)", disposition, re.I)
    simple = re.search(r'filename="?([^";]+)', disposition, re.I)
    name = unquote(encoded[1] if encoded else simple[1] if simple else "")
    if name.strip().lower() in {"", "undefined", "null"}:
        name = unquote(Path(urlsplit(url).path).name)
    return name or "download.bin"


def download(url, destination, *, max_bytes=256 * 1024 * 1024):
    url = download_url(url)
    started = time.monotonic()
    transport = httpx.HTTPTransport()
    transport._pool._network_backend = PublicBackend()
    with httpx.Client(timeout=15, follow_redirects=False, trust_env=False, transport=transport) as client:
        for _ in range(6):
            validate_public_url(url)
            with client.stream("GET", url) as response:
                if response.status_code in {301, 302, 303, 307, 308}:
                    url = urljoin(url, response.headers.get("location", ""))
                    continue
                if response.status_code != 200:
                    raise ValueError("File link expired, unavailable or requires permission")
                mime = response.headers.get("content-type", "application/octet-stream").split(";")[0]
                if mime in {"text/html", "application/xhtml+xml"}:
                    raise ValueError("Share page requires permission or an unsupported download step")
                if int(response.headers.get("content-length", "0")) > max_bytes:
                    raise ValueError("File exceeds download limit")
                total = 0
                with Path(destination).open("wb") as stream:
                    for chunk in response.iter_bytes(65536):
                        total += len(chunk)
                        if total > max_bytes or time.monotonic() - started > 120:
                            raise ValueError("File download size/time limit")
                        if total == len(chunk) and chunk.lstrip().lower().startswith(
                            (b"<!doctype html", b"<html")
                        ):
                            raise ValueError("Share link returned an HTML page")
                        stream.write(chunk)
                if not total:
                    raise ValueError("Empty downloaded file")
                return {"name": filename_from_response(response, url), "mime": mime, "bytes": total}
    raise ValueError("Too many file redirects")
