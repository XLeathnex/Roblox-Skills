#!/usr/bin/env python3
"""Upload the images listed in <dir>/assets.json through Roblox Open Cloud and write their ids back.

    ROBLOX_API_KEY=...  python3 scripts/upload_assets.py ui/assets --user 12345
    ROBLOX_API_KEY=...  python3 scripts/upload_assets.py ui/assets --group 67890

The key needs the Assets API with read and write. Entries that already have an id are skipped.
Images are uploaded as assetType "Image" so the returned id works directly in ImageLabel.Image.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

API = "https://apis.roblox.com/assets/v1"


def _request(url: str, key: str, data: bytes | None = None, content_type: str | None = None) -> dict:
    req = urllib.request.Request(url, data=data, method="POST" if data is not None else "GET")
    req.add_header("x-api-key", key)
    if content_type:
        req.add_header("Content-Type", content_type)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as e:
        raise SystemExit(f"Roblox API {e.code} for {url}: {e.read().decode('utf-8', 'replace')[:400]}")


def upload(path: Path, name: str, key: str, creator: dict) -> int:
    boundary = uuid.uuid4().hex
    meta = {"assetType": "Image", "displayName": name[:50], "description": "UI asset",
            "creationContext": {"creator": creator}}
    body = b"".join([
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"request\"\r\nContent-Type: application/json\r\n\r\n".encode(),
        json.dumps(meta).encode(), b"\r\n",
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"fileContent\"; filename=\"{path.name}\"\r\nContent-Type: image/png\r\n\r\n".encode(),
        path.read_bytes(), b"\r\n", f"--{boundary}--\r\n".encode(),
    ])
    op = _request(f"{API}/assets", key, body, f"multipart/form-data; boundary={boundary}")
    op_path = op.get("path") or f"operations/{op.get('operationId')}"
    for _ in range(40):
        status = _request(f"{API}/{op_path}", key)
        if status.get("done"):
            response = status.get("response") or {}
            if "assetId" not in response:
                raise SystemExit(f"upload of {path.name} finished without an asset id: {status}")
            return int(response["assetId"])
        time.sleep(1.5)
    raise SystemExit(f"upload of {path.name} did not finish in time ({op_path})")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("dir")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--user")
    g.add_argument("--group")
    a = ap.parse_args()
    key = os.environ.get("ROBLOX_API_KEY")
    if not key:
        raise SystemExit("set ROBLOX_API_KEY (an Open Cloud key with Assets read + write)")
    folder = Path(a.dir)
    manifest = folder / "assets.json"
    data = json.loads(manifest.read_text())
    creator = {"userId": str(a.user)} if a.user else {"groupId": str(a.group)}
    done = 0
    for name, info in data.items():
        if not isinstance(info, dict) or info.get("id") or not info.get("file"):
            continue
        asset_id = upload(folder / info["file"], name, key, creator)
        info["id"] = asset_id
        manifest.write_text(json.dumps(data, indent=2) + "\n")
        print(f"{name}: rbxassetid://{asset_id}")
        done += 1
    print(f"uploaded {done} image(s). Rebuild the UI so the ids are written into the instances.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
