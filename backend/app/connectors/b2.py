"""Backblaze B2 offsite upload (MASTER_SPEC §22.7).

"uploaded to Backblaze B2's free tier" via B2's native v2 API — authorize,
resolve the bucket, fetch an upload URL, push the artifact. No new
dependency: httpx is already on the stack, and the sync client keeps the
nightly beat task a plain function.

Credentials unset => callers skip honestly (see app/tasks/backups.py);
a failed upload NEVER fails the local encrypted backup — the artifact is
safe on disk, the offsite copy is retried next night.
"""

import hashlib
from urllib.parse import quote

import httpx

from app.core.config import get_settings

B2_API_BASE = "https://api.backblazeb2.com/b2api/v2"


class B2UploadError(Exception):
    """Raised when any B2 API step fails (auth, bucket lookup, upload)."""


class B2Uploader:
    def __init__(self, http: httpx.Client | None = None) -> None:
        self._http = http or httpx.Client(timeout=120)

    def upload(self, path: str) -> dict:
        """Upload one file. Returns the B2 file response dict (fileId, fileName...)."""
        settings = get_settings()
        data = open(path, "rb").read()

        # 1. authorize — basic auth over the application key pair
        r = self._http.get(
            f"{B2_API_BASE}/b2_authorize_account",
            auth=(settings.b2_application_key_id, settings.b2_application_key),
        )
        if r.status_code != 200:
            raise B2UploadError(f"authorize failed: HTTP {r.status_code}")
        authz = r.json()

        # 2. resolve bucket name -> bucket id
        r = self._http.get(
            f"{authz['apiUrl']}/b2api/v2/b2_list_buckets",
            headers={"Authorization": authz["authorizationToken"]},
            params={"accountId": authz["accountId"], "bucketName": settings.b2_bucket},
        )
        if r.status_code != 200:
            raise B2UploadError(f"bucket lookup failed: HTTP {r.status_code}")
        buckets = r.json().get("buckets", [])
        if not buckets:
            raise B2UploadError(f"bucket not found: {settings.b2_bucket!r}")
        bucket_id = buckets[0]["bucketId"]

        # 3. upload URL for that bucket
        r = self._http.get(
            f"{authz['apiUrl']}/b2api/v2/b2_get_upload_url",
            headers={"Authorization": authz["authorizationToken"]},
            params={"bucketId": bucket_id},
        )
        if r.status_code != 200:
            raise B2UploadError(f"get_upload_url failed: HTTP {r.status_code}")
        up = r.json()

        # 4. push the artifact
        file_name = path.rsplit("/", 1)[-1]
        r = self._http.post(
            up["uploadUrl"],
            headers={
                "Authorization": up["authorizationToken"],
                "X-Bz-File-Name": quote(file_name),
                "Content-Type": "b2/x-auto",
                "X-Bz-Content-Sha1": hashlib.sha1(data).hexdigest(),
            },
            content=data,
        )
        if r.status_code != 200:
            raise B2UploadError(f"upload failed: HTTP {r.status_code}: {r.text[:200]}")
        return r.json()
