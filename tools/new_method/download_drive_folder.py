"""Download files from a Google Drive folder using existing Earth Engine OAuth credentials."""

from __future__ import annotations

import argparse
import io
import sys
from pathlib import Path

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from cpis.common.file_utils import ensure_dir, save_json  # noqa: E402
from cpis.common.logging_utils import build_logger  # noqa: E402


EE_CREDENTIALS = Path.home() / ".config" / "earthengine" / "credentials"
DRIVE_SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]
FOLDER_MIME = "application/vnd.google-apps.folder"


def _load_credentials(path: Path) -> Credentials:
    if not path.exists():
        raise FileNotFoundError(f"Credential file not found: {path}")
    creds = Credentials.from_authorized_user_file(str(path), scopes=DRIVE_SCOPES)
    if not creds.valid:
        if not creds.refresh_token:
            raise RuntimeError("Credential file does not contain a refresh token.")
        creds.refresh(Request())
    return creds


def _build_drive(creds: Credentials):
    return build("drive", "v3", credentials=creds, cache_discovery=False)


def _resolve_folder_id(service, *, folder_name: str, shared_drive_id: str | None, log) -> str:
    safe_folder_name = folder_name.replace("'", "\\'")
    query = f"name = '{safe_folder_name}' and mimeType = '{FOLDER_MIME}' and trashed = false"
    kwargs = {
        "q": query,
        "fields": "files(id,name,driveId,parents)",
        "pageSize": 50,
        "supportsAllDrives": True,
        "includeItemsFromAllDrives": True,
    }
    if shared_drive_id:
        kwargs["corpora"] = "drive"
        kwargs["driveId"] = shared_drive_id
    else:
        kwargs["corpora"] = "allDrives"
    resp = service.files().list(**kwargs).execute()
    files = resp.get("files", [])
    if not files:
        raise RuntimeError(f"Drive folder not found: {folder_name}")
    if len(files) > 1:
        ids = ", ".join(f"{row.get('name')}:{row.get('id')}" for row in files[:10])
        raise RuntimeError(f"Multiple folders matched '{folder_name}'. Use --folder-id. Matches: {ids}")
    folder_id = str(files[0]["id"])
    log(f"Resolved folder '{folder_name}' -> {folder_id}")
    return folder_id


def _iter_files(service, *, folder_id: str, shared_drive_id: str | None):
    page_token = None
    while True:
        kwargs = {
            "q": f"'{folder_id}' in parents and trashed = false",
            "fields": "nextPageToken,files(id,name,mimeType,size,modifiedTime)",
            "pageSize": 1000,
            "pageToken": page_token,
            "supportsAllDrives": True,
            "includeItemsFromAllDrives": True,
        }
        if shared_drive_id:
            kwargs["corpora"] = "drive"
            kwargs["driveId"] = shared_drive_id
        else:
            kwargs["corpora"] = "allDrives"
        resp = service.files().list(**kwargs).execute()
        for row in resp.get("files", []):
            yield row
        page_token = resp.get("nextPageToken")
        if not page_token:
            break


def _download_file(service, *, file_id: str, out_path: Path, log) -> None:
    ensure_dir(out_path.parent)
    request = service.files().get_media(fileId=file_id, supportsAllDrives=True)
    with out_path.open("wb") as fh:
        downloader = MediaIoBaseDownload(fh, request, chunksize=16 * 1024 * 1024)
        done = False
        while not done:
            status, done = downloader.next_chunk()
            if status is not None:
                log(f"  progress {out_path.name}: {int(status.progress() * 100)}%")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    group = ap.add_mutually_exclusive_group(required=True)
    group.add_argument("--folder-name", default="", help="Google Drive folder name")
    group.add_argument("--folder-id", default="", help="Google Drive folder id")
    ap.add_argument("--out-dir", required=True, help="Local output directory")
    ap.add_argument("--credentials", default=str(EE_CREDENTIALS), help="Authorized user credentials JSON")
    ap.add_argument("--shared-drive-id", default="", help="Optional shared drive id")
    ap.add_argument("--pattern", default="*.tif", help="Only download files matching this suffix-style glob")
    ap.add_argument("--ignore-existing", action="store_true", help="Skip files that already exist locally")
    ap.add_argument("--max-files", type=int, default=0, help="Limit files downloaded; 0 means no cap")
    ap.add_argument("--log-file", default="", help="Optional log file")
    args = ap.parse_args()

    out_dir = ensure_dir(args.out_dir)
    log = build_logger(args.log_file if args.log_file else (Path(out_dir) / "download_drive_folder.log"))
    creds = _load_credentials(Path(args.credentials))
    service = _build_drive(creds)
    folder_id = str(args.folder_id).strip()
    shared_drive_id = str(args.shared_drive_id).strip() or None
    if not folder_id:
        folder_id = _resolve_folder_id(service, folder_name=str(args.folder_name).strip(), shared_drive_id=shared_drive_id, log=log)

    pattern = str(args.pattern).strip()
    all_files = []
    for row in _iter_files(service, folder_id=folder_id, shared_drive_id=shared_drive_id):
        name = str(row.get("name", ""))
        if not Path(name).match(pattern):
            continue
        if str(row.get("mimeType", "")) == FOLDER_MIME:
            continue
        all_files.append(row)
    if int(args.max_files) > 0:
        all_files = all_files[: int(args.max_files)]
    if not all_files:
        raise RuntimeError("No matching files found in Drive folder.")

    downloaded = 0
    skipped = 0
    rows = []
    for idx, row in enumerate(all_files, 1):
        name = str(row["name"])
        dst = Path(out_dir) / name
        if bool(args.ignore_existing) and dst.exists():
            skipped += 1
            log(f"[{idx}/{len(all_files)}] skip existing {name}")
            rows.append({"name": name, "file_id": row["id"], "status": "skipped_existing", "out": str(dst.resolve())})
            continue
        log(f"[{idx}/{len(all_files)}] download {name}")
        _download_file(service, file_id=str(row["id"]), out_path=dst, log=log)
        downloaded += 1
        rows.append({"name": name, "file_id": row["id"], "status": "downloaded", "out": str(dst.resolve())})

    summary = {
        "folder_id": folder_id,
        "folder_name": str(args.folder_name).strip(),
        "out_dir": str(Path(out_dir).resolve()),
        "pattern": pattern,
        "downloaded": int(downloaded),
        "skipped_existing": int(skipped),
        "files_considered": int(len(all_files)),
        "files": rows,
    }
    save_json(Path(out_dir) / "download_drive_folder.summary.json", summary)
    log(f"Wrote summary: {Path(out_dir) / 'download_drive_folder.summary.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
