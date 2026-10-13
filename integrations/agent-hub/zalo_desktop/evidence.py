"""Operator-selected evidence export. No Zalo UI, ERP write or automatic order creation."""

import argparse
import hashlib
import inspect
import json
import shutil
import subprocess
from pathlib import Path

from hub.evidence_document import save_document, select_sources

TRIAL_GROUP = "g7557409429748854839"


def export_sources(ids):
    code = "import sqlite3,json,base64,sys\n" + inspect.getsource(select_sources)
    code += "\ndb=sqlite3.connect('file:/data/hub.sqlite3?mode=ro',uri=True)\ndb.execute('PRAGMA query_only=ON')\ndb.execute('BEGIN')\n"
    code += "print(json.dumps(select_sources(db,'zalo-personal-1',sys.argv[1],json.loads(sys.argv[2])),ensure_ascii=False))\n"
    result = subprocess.run(
        [
            r"C:\Program Files\Docker\Docker\resources\bin\docker.exe",
            "exec",
            "phucthanh-chatwoot-hub-1",
            "/app/.venv/bin/python",
            "-c",
            code,
            TRIAL_GROUP,
            json.dumps(ids),
        ],
        capture_output=True,
        check=True,
        text=True,
        encoding="utf-8",
    )
    return json.loads(result.stdout)


def verify_originals(messages, nas_root):
    root = Path(nas_root).resolve()
    for message in messages:
        if message["thread_id"] != TRIAL_GROUP or message["display_name"] != "Gia đình vintuan":
            raise ValueError("Evidence is restricted to the trial group")
        if message.get("attachments"):
            raise ValueError("Unsupported attachment requires staff review")
        for asset in message.get("assets", []):
            if asset["state"] != "ready":
                raise ValueError("Source asset is not archived")
            path = (root / asset["relative_path"]).resolve()
            if not path.is_relative_to(root):
                raise ValueError("Invalid source asset path")
            with path.open("rb") as stream:
                if hashlib.file_digest(stream, "sha256").hexdigest() != asset["sha256"]:
                    raise ValueError("Original NAS asset changed")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--order", required=True)
    parser.add_argument("--message-ids", nargs="+", required=True)
    parser.add_argument("--nas-root", default=r"\\192.168.1.203\n8n_upload")
    parser.add_argument("--local-output", required=True)
    args = parser.parse_args()
    messages = export_sources(args.message_ids)
    verify_originals(messages, args.nas_root)
    result = save_document(messages, args.order, args.nas_root)
    local = Path(args.local_output) / result["document_id"][:16]
    local.mkdir(parents=True, exist_ok=True)
    for item in result["pages"]:
        path = local / item["name"]
        shutil.copyfile(Path(result["directory"]) / item["name"], path)
        assert hashlib.sha256(path.read_bytes()).hexdigest() == item["sha256"]
    result["local_directory"] = str(local.resolve())
    (local / "receipt.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
