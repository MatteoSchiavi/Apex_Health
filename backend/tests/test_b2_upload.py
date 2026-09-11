"""B2 offsite upload tests (Phase 8, §22.7).

All HTTP runs through httpx.MockTransport — no real B2 calls, ever (§0, §20).
The live drill proves the restore path; the offsite copy only needs to prove
it calls the right B2 v2 API sequence and never takes the local backup down.
"""

import base64
import hashlib

import httpx
import pytest

from app.connectors.b2 import B2UploadError, B2Uploader


def _b2_transport(calls: list[httpx.Request], fail_stage: str | None = None) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        url = str(request.url)
        authz = {
            "accountId": "acct-1",
            "authorizationToken": "tok-1",
            "apiUrl": "https://api001.backblazeb2.com",
        }
        if "b2_authorize_account" in url:
            if fail_stage == "authorize":
                return httpx.Response(401, json={"message": "bad key"})
            return httpx.Response(200, json=authz)
        if "b2_list_buckets" in url:
            if fail_stage == "bucket":
                return httpx.Response(200, json={"buckets": []})
            return httpx.Response(
                200, json={"buckets": [{"bucketId": "bkt-1", "bucketName": "apex-backups"}]}
            )
        if "b2_get_upload_url" in url:
            return httpx.Response(
                200, json={"uploadUrl": "https://up.example/b2", "authorizationToken": "tok-up"}
            )
        if "up.example" in url:
            if fail_stage == "upload":
                return httpx.Response(500, json={"message": "internal"})
            return httpx.Response(
                200, json={"fileId": "f1", "fileName": request.headers["X-Bz-File-Name"]}
            )
        return httpx.Response(404, json={"message": "unknown route"})

    return httpx.MockTransport(handler)


@pytest.fixture
def b2_settings(monkeypatch):
    monkeypatch.setattr(
        "app.connectors.b2.get_settings",
        lambda: type(
            "S",
            (),
            {
                "b2_application_key_id": "key-id",
                "b2_application_key": "app-key",
                "b2_bucket": "apex-backups",
            },
        )(),
    )


def test_upload_calls_full_b2_sequence(tmp_path, b2_settings):
    """authorize -> list_buckets -> get_upload_url -> upload, sha1 + name headers set."""
    art = tmp_path / "bk"
    art.mkdir(parents=True)
    path = art / "hcc-20260911-020000.daily.sql.gz.enc"
    path.write_bytes(b"fernet-ciphertext-not-really")

    calls: list[httpx.Request] = []
    uploader = B2Uploader(
        http=httpx.Client(transport=_b2_transport(calls), timeout=30)
    )
    resp = uploader.upload(str(path))

    assert resp["fileId"] == "f1"
    assert [c.url.path for c in calls] == [
        "/b2api/v2/b2_authorize_account",
        "/b2api/v2/b2_list_buckets",
        "/b2api/v2/b2_get_upload_url",
        "/b2",
    ]
    # The upload carried the file name and a valid sha1 of the content.
    up_call = calls[-1]
    assert up_call.headers["X-Bz-File-Name"] == path.name
    assert up_call.headers["X-Bz-Content-Sha1"] == hashlib.sha1(path.read_bytes()).hexdigest()
    # Basic auth went to the authorize call only.
    assert calls[0].headers["Authorization"].startswith("Basic ")
    assert "Authorization" in calls[-1].headers and "tok-up" in calls[-1].headers["Authorization"]


@pytest.mark.parametrize("fail_stage", ["authorize", "bucket", "upload"])
def test_upload_failure_modes(tmp_path, b2_settings, fail_stage):
    path = tmp_path / "hcc-20260911-020000.daily.sql.gz.enc"
    path.write_bytes(b"x")
    calls: list[httpx.Request] = []
    uploader = B2Uploader(
        http=httpx.Client(transport=_b2_transport(calls, fail_stage), timeout=30)
    )
    with pytest.raises(B2UploadError):
        uploader.upload(str(path))


def test_task_reports_b2_upload_and_never_fails_local_backup(tmp_path, fake_pg_dump, monkeypatch):
    """A broken B2 must leave the local artifact + 'created' status intact (§22.7)."""
    import os
    from types import SimpleNamespace

    from app.tasks.backups import run_nightly_backup

    d = tmp_path / "bk"
    d.mkdir()
    monkeypatch.setattr(
        "app.tasks.backups.get_settings",
        lambda: SimpleNamespace(
            backup_encryption_key="test-backup-key",
            database_url=os.environ["DATABASE_URL"],
            backup_dir=str(d),
            pg_dump_bin=fake_pg_dump,
            backup_retain_daily=14,
            backup_retain_monthly=6,
            b2_application_key_id="key-id",
            b2_application_key="app-key",
            b2_bucket="apex-backups",
        ),
    )
    monkeypatch.setattr(
        "app.connectors.b2.B2Uploader.upload",
        lambda self, p: (_ for _ in ()).throw(B2UploadError("network down")),
    )

    from datetime import UTC, datetime

    report = run_nightly_backup(now=datetime(2026, 9, 11, 2, 0, 0, tzinfo=UTC))
    assert report["status"] == "created"  # local backup succeeded
    assert report["b2"].startswith("failed:")  # offsite failed honestly
    import pathlib

    assert pathlib.Path(report["path"]).exists()


def test_authorize_uses_application_key_pair(b2_settings, tmp_path):
    """The basic-auth pair is exactly the configured key id + application key."""
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["auth"] = request.headers["Authorization"]
        return httpx.Response(401)

    f = tmp_path / "artifact.enc"
    f.write_bytes(b"x")
    uploader = B2Uploader(http=httpx.Client(transport=httpx.MockTransport(handler)))
    with pytest.raises(B2UploadError):
        uploader.upload(str(f))
    expected = "Basic " + base64.b64encode(b"key-id:app-key").decode()
    assert captured["auth"] == expected
