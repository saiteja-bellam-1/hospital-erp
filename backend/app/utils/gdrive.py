"""
Google Drive backup utility using OAuth refresh token.
No Google SDK — uses REST API with requests.
"""
import json
import time
import requests
from datetime import datetime

DRIVE_API = "https://www.googleapis.com/drive/v3/files"
UPLOAD_API = "https://www.googleapis.com/upload/drive/v3/files"
COMMON_PARAMS = {"supportsAllDrives": "true", "includeItemsFromAllDrives": "true"}


def _get_access_token(gdrive_config: dict) -> str:
    """Get access token using OAuth refresh token."""
    resp = requests.post("https://oauth2.googleapis.com/token", data={
        "grant_type": "refresh_token",
        "refresh_token": gdrive_config["refresh_token"],
        "client_id": gdrive_config["client_id"],
        "client_secret": gdrive_config["client_secret"],
    }, timeout=15)
    if resp.status_code != 200:
        raise Exception(f"Token refresh failed: {resp.status_code} {resp.text[:200]}")
    return resp.json()["access_token"]


def _find_or_create_folder(access_token: str, parent_id: str, folder_name: str) -> str:
    """Find a subfolder by name, or create it."""
    headers = {"Authorization": f"Bearer {access_token}"}

    query = f"name='{folder_name}' and '{parent_id}' in parents and mimeType='application/vnd.google-apps.folder' and trashed=false"
    resp = requests.get(DRIVE_API,
        params={**COMMON_PARAMS, "q": query, "fields": "files(id,name)", "pageSize": 1},
        headers=headers, timeout=15,
    )
    if resp.status_code == 200:
        files = resp.json().get("files", [])
        if files:
            return files[0]["id"]

    resp = requests.post(DRIVE_API,
        params=COMMON_PARAMS,
        headers={**headers, "Content-Type": "application/json"},
        json={"name": folder_name, "mimeType": "application/vnd.google-apps.folder", "parents": [parent_id]},
        timeout=15,
    )
    if resp.status_code in (200, 201):
        return resp.json()["id"]

    raise Exception(f"Failed to create folder: {resp.status_code} {resp.text[:200]}")


def upload_backup(gdrive_config: dict, hospital_id: str, file_data: bytes, filename: str) -> dict:
    """Upload a gzip backup file to Google Drive."""
    access_token = _get_access_token(gdrive_config)
    folder_id = gdrive_config["folder_id"]

    hospital_folder_id = _find_or_create_folder(access_token, folder_id, hospital_id)
    headers = {"Authorization": f"Bearer {access_token}"}

    # Check if file exists (overwrite)
    query = f"name='{filename}' and '{hospital_folder_id}' in parents and trashed=false"
    search_resp = requests.get(DRIVE_API,
        params={**COMMON_PARAMS, "q": query, "fields": "files(id)", "pageSize": 1},
        headers=headers, timeout=15,
    )
    existing_id = None
    if search_resp.status_code == 200:
        files = search_resp.json().get("files", [])
        if files:
            existing_id = files[0]["id"]

    if existing_id:
        resp = requests.patch(
            f"{UPLOAD_API}/{existing_id}",
            params={**COMMON_PARAMS, "uploadType": "media"},
            headers={**headers, "Content-Type": "application/gzip"},
            data=file_data, timeout=120,
        )
    else:
        metadata = json.dumps({"name": filename, "parents": [hospital_folder_id]})
        boundary = "----BackupBoundary"
        body = (
            f"--{boundary}\r\n"
            f"Content-Type: application/json; charset=UTF-8\r\n\r\n"
            f"{metadata}\r\n"
            f"--{boundary}\r\n"
            f"Content-Type: application/gzip\r\n\r\n"
        ).encode() + file_data + f"\r\n--{boundary}--".encode()

        resp = requests.post(UPLOAD_API,
            params={**COMMON_PARAMS, "uploadType": "multipart"},
            headers={**headers, "Content-Type": f"multipart/related; boundary={boundary}"},
            data=body, timeout=120,
        )

    if resp.status_code not in (200, 201):
        raise Exception(f"Upload failed: {resp.status_code} {resp.text[:300]}")

    return {"file_id": resp.json().get("id"), "name": filename}


def cleanup_old_backups(gdrive_config: dict, hospital_id: str, retention_days: int = 30):
    """Delete backup files older than retention_days."""
    access_token = _get_access_token(gdrive_config)
    folder_id = gdrive_config["folder_id"]
    headers = {"Authorization": f"Bearer {access_token}"}

    query = f"name='{hospital_id}' and '{folder_id}' in parents and mimeType='application/vnd.google-apps.folder' and trashed=false"
    resp = requests.get(DRIVE_API,
        params={**COMMON_PARAMS, "q": query, "fields": "files(id)", "pageSize": 1},
        headers=headers, timeout=15,
    )
    if resp.status_code != 200:
        return
    folders = resp.json().get("files", [])
    if not folders:
        return

    hospital_folder_id = folders[0]["id"]

    query = f"'{hospital_folder_id}' in parents and trashed=false"
    resp = requests.get(DRIVE_API,
        params={**COMMON_PARAMS, "q": query, "fields": "files(id,name,createdTime)", "pageSize": 100},
        headers=headers, timeout=15,
    )
    if resp.status_code != 200:
        return

    from datetime import timedelta
    cutoff = datetime.utcnow() - timedelta(days=retention_days)

    for f in resp.json().get("files", []):
        try:
            created = datetime.fromisoformat(f["createdTime"].replace("Z", "+00:00")).replace(tzinfo=None)
            if created < cutoff:
                requests.delete(f"{DRIVE_API}/{f['id']}", params=COMMON_PARAMS, headers=headers, timeout=15)
        except Exception:
            pass


def test_connection(gdrive_config: dict) -> dict:
    """Test the connection and folder access."""
    access_token = _get_access_token(gdrive_config)
    folder_id = gdrive_config["folder_id"]

    resp = requests.get(
        f"{DRIVE_API}/{folder_id}",
        params={**COMMON_PARAMS, "fields": "id,name,mimeType"},
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=10,
    )
    if resp.status_code == 404:
        raise Exception("Folder not found. Check folder ID and sharing.")
    if resp.status_code != 200:
        raise Exception(f"Folder access failed: {resp.status_code} {resp.text[:200]}")

    folder_info = resp.json()
    return {"folder_name": folder_info.get("name"), "folder_id": folder_id}
