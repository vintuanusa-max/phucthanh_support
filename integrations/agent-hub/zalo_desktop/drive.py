"""One-time snapshots of public Drive folders; no login or ongoing subscription."""

import hashlib
import json
import re
import shutil
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlsplit

import httpx

from .downloads import PublicBackend, download


def folder_id(url):
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.hostname != "drive.google.com":
        return None
    match = re.fullmatch(r"/drive/(?:u/\d+/)?folders/([\w-]{10,200})/?", parsed.path)
    return match[1] if match else None


class FolderPage(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self.active = None
        self.title = ""
        self.in_title = False

    def handle_starttag(self, tag, attrs):
        if tag == "title":
            self.in_title = True
        if tag == "a":
            self.active = [dict(attrs).get("href", ""), ""]

    def handle_data(self, data):
        if self.in_title:
            self.title += data
        if self.active is not None:
            self.active[1] += data

    def handle_endtag(self, tag):
        if tag == "title":
            self.in_title = False
        if tag == "a" and self.active is not None:
            self.links.append(self.active)
            self.active = None


def list_folder(url):
    identity = folder_id(url)
    if not identity:
        raise ValueError("Unsupported Drive folder URL")
    params = {"id": identity}
    resource = parse_qs(urlsplit(url).query).get("resourcekey", [])
    if resource:
        params["resourcekey"] = resource[0]
    transport = httpx.HTTPTransport()
    transport._pool._network_backend = PublicBackend()
    with httpx.Client(transport=transport, timeout=15, trust_env=False, follow_redirects=False) as client:
        with client.stream(
            "GET", "https://drive.google.com/embeddedfolderview?" + urlencode(params)
        ) as response:
            if response.status_code != 200:
                raise ValueError("Drive folder requires access")
            body = bytearray()
            for chunk in response.iter_bytes(65536):
                body.extend(chunk)
                if len(body) > 2 * 1024 * 1024:
                    raise ValueError("Drive listing limit")
    page = FolderPage()
    page.feed(body.decode("utf-8"))
    if not page.title:
        raise ValueError("Unrecognized Drive folder page")
    entries, seen = [], set()
    for href, name in page.links:
        parsed = urlsplit(href)
        match = re.fullmatch(r"/file/d/([\w-]{10,200})/(?:view)?", parsed.path)
        child_folder = folder_id(href)
        if parsed.hostname == "docs.google.com":
            raise ValueError("Google-native document export requires staff")
        if parsed.hostname != "drive.google.com" or not (child_folder or match):
            continue
        key = child_folder or match[1]
        if key in seen:
            continue
        seen.add(key)
        entries.append({"id": key, "name": name.strip(), "url": href, "folder": bool(child_folder)})
    if not entries:
        raise ValueError("Empty or inaccessible Drive folder; staff must verify")
    return page.title, entries


def archive_folder(vault, key, payload):
    from datetime import datetime

    from .vault import safe_name

    month = datetime.fromtimestamp(payload["timestamp"]).strftime("%Y-%m")
    relative = Path(vault.folder(payload)) / month / "drive" / key[:12]
    root = vault.root / relative
    inventory_path = vault.home / (key + ".folder.json")
    if inventory_path.exists():
        inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    else:
        inventory, visited = [], set()

        def visit(url, path, depth):
            identity = folder_id(url)
            if identity in visited:
                raise ValueError("Drive folder cycle")
            visited.add(identity)
            if depth > 5 or len(visited) > 30:
                raise ValueError("Drive folder depth/count limit")
            _, children = list_folder(url)
            for child in children:
                # IDs avoid collisions even for same-name children on Windows.
                name = hashlib.sha256(child["id"].encode()).hexdigest()[:10] + "__" + safe_name(child["name"])
                child_path = path / name
                if child["folder"]:
                    visit(child["url"], child_path, depth + 1)
                else:
                    inventory.append({**child, "path": child_path.as_posix()})
                    if len(inventory) > 50:
                        raise ValueError("Drive folder file limit (50)")

        visit(payload["url"], Path(), 0)
        inventory_path.write_text(json.dumps(inventory, ensure_ascii=False), encoding="utf-8")
    total, results = 0, []
    for item in inventory:
        destination = root / item["path"]
        manifest = destination.with_name(destination.name + ".source.json")
        if destination.exists() and manifest.exists():
            result = json.loads(manifest.read_text(encoding="utf-8"))
            with destination.open("rb") as stream:
                if hashlib.file_digest(stream, "sha256").hexdigest() != result["sha256"]:
                    raise ValueError("Existing Drive snapshot file changed")
        else:
            child_key = hashlib.sha256((key + item["id"]).encode()).hexdigest()
            spool = vault.home / (child_key + ".drive-download")
            info = download(item["url"], spool, max_bytes=min(256 * 1024 * 1024, 1024**3 - total))
            with spool.open("rb") as stream:
                digest = hashlib.file_digest(stream, "sha256").hexdigest()
            if destination.exists():
                with destination.open("rb") as stream:
                    if hashlib.file_digest(stream, "sha256").hexdigest() != digest:
                        raise ValueError("Refuse to overwrite Drive snapshot")
            else:
                destination.parent.mkdir(parents=True, exist_ok=True)
                temp = destination.with_name(destination.name + ".part")
                shutil.copyfile(spool, temp)
                temp.replace(destination)
            with destination.open("rb") as stream:
                if hashlib.file_digest(stream, "sha256").hexdigest() != digest:
                    raise OSError("Drive NAS hash mismatch")
            result = {
                "path": item["path"],
                "name": item["name"],
                "sha256": digest,
                "size": info["bytes"],
                "mime_type": info["mime"],
            }
            temp = manifest.with_name(manifest.name + ".part")
            temp.write_text(
                json.dumps({**payload, **result, "drive_file_id": item["id"]}, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            temp.replace(manifest)
            spool.unlink(missing_ok=True)
        total += result["size"]
        if total > 1024**3:
            raise ValueError("Drive snapshot exceeds 1 GiB")
        results.append({k: result[k] for k in ("path", "name", "sha256", "size", "mime_type")})
    index = root / "_snapshot.json"
    temp = index.with_suffix(".part")
    temp.write_text(
        json.dumps({**payload, "files": results, "complete": True}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temp.replace(index)
    return {
        "name": "Google Drive — " + str(len(results)) + " files",
        "relative_path": (relative / index.name).as_posix(),
        "sha256": hashlib.sha256(index.read_bytes()).hexdigest(),
        "size": total,
        "mime_type": "application/json",
    }
