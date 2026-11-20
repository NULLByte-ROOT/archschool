"""Comprehensive tests for Milestone 1 Backend Update Service & Storage Engine.

Covers:
- test_check_none: returns "none" when currentBundleId matches active bundle.
- test_check_ota: returns "ota" when a new bundle is available, returning correct bundleUrl, bundleHash, and assets.
- test_check_apk: returns "apk" with mandatory=true when appVersion < minApkVersion.
- test_bundle_download: serves index.android.bundle with status 200, Content-Type application/javascript, immutable cache headers.
- test_asset_download: serves bundle assets with appropriate mime type and cache headers.
- test_apk_download_full: serves APK with 200 OK and Content-Disposition.
- test_apk_download_resumable_byte_range: sends Range: bytes=0-1023, asserts 206 Partial Content, Content-Range header, and correct partial slice.
- test_storage_pruning: creates 5 dummy bundle directories, calls retention pruner, asserts only the latest KEEP_BUNDLES_COUNT (3) directories remain.
- test_json_fallback: tests manifest retrieval when DB table is empty or DB is bypassed, reading from meta/updates.json.
- test_path_traversal_blocked: verifies malicious path parameters are rejected with HTTP 400.
"""

import json
import os
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app import models
from app.routers.updates import prune_superseded_bundles


def test_check_none(client: TestClient, db_session: Session, test_updates_dir: Path):
    """Assert returns updateType: 'none' when client bundle matches active bundle."""
    active_update = models.AppUpdate(
        platform="android",
        runtime_version="1.0.0",
        bundle_id="20261117-01",
        bundle_url="/api/v1/updates/bundle/1.0.0/20261117-01/index.android.bundle",
        bundle_hash="sha256-test12345",
        bundle_size=1024,
        is_active=True,
        mandatory=False,
        min_apk_version="1.0.0",
        apk_url="/api/v1/updates/apk/app-release.apk",
        release_notes="Initial release",
        assets_json="[]",
    )
    db_session.add(active_update)
    db_session.commit()

    response = client.get(
        "/api/v1/updates/check",
        params={
            "platform": "android",
            "runtimeVersion": "1.0.0",
            "appVersion": "1.0.0",
            "currentBundleId": "20261117-01",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["updateType"] == "none"
    assert data["version"] == "1.0.0"
    assert data["bundleId"] == "20261117-01"
    assert data["mandatory"] is False


def test_check_ota(client: TestClient, db_session: Session, test_updates_dir: Path):
    """Assert returns updateType: 'ota' when client has older bundle, delivering bundleUrl and assets."""
    assets = [
        {
            "key": "app_logo",
            "url": "/api/v1/updates/assets/1.0.0/20261117-02/assets/logo.png",
            "hash": "sha256-logo123",
            "size": 2048,
        }
    ]
    new_update = models.AppUpdate(
        platform="android",
        runtime_version="1.0.0",
        bundle_id="20261117-02",
        bundle_url="/api/v1/updates/bundle/1.0.0/20261117-02/index.android.bundle",
        bundle_hash="sha256-newhash99",
        bundle_size=4096,
        is_active=True,
        mandatory=True,
        min_apk_version="1.0.0",
        apk_url="/api/v1/updates/apk/app-release.apk",
        release_notes="Critical OTA bugfix",
        assets_json=json.dumps(assets),
    )
    db_session.add(new_update)
    db_session.commit()

    response = client.get(
        "/api/v1/updates/check",
        params={
            "platform": "android",
            "runtimeVersion": "1.0.0",
            "appVersion": "1.0.0",
            "currentBundleId": "20261117-01",  # Client is running old bundle
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["updateType"] == "ota"
    assert data["bundleId"] == "20261117-02"
    assert data["bundleUrl"] == "/api/v1/updates/bundle/1.0.0/20261117-02/index.android.bundle"
    assert data["bundleHash"] == "sha256-newhash99"
    assert data["bundleSize"] == 4096
    assert data["mandatory"] is True
    assert len(data["assets"]) == 1
    assert data["assets"][0]["key"] == "app_logo"


def test_check_apk(client: TestClient, db_session: Session, test_updates_dir: Path):
    """Assert returns updateType: 'apk' with mandatory=true when appVersion < minApkVersion."""
    active_update = models.AppUpdate(
        platform="android",
        runtime_version="1.0.0",
        bundle_id="20261117-01",
        bundle_url="/api/v1/updates/bundle/1.0.0/20261117-01/index.android.bundle",
        bundle_hash="sha256-bundle",
        bundle_size=1024,
        is_active=True,
        mandatory=False,
        min_apk_version="1.0.0",
        apk_url="/api/v1/updates/apk/app-release.apk",
        apk_size=39526501,
        apk_hash="sha256-apkhash123",
        release_notes="Native upgrade mandatory for new runtime",
        assets_json="[]",
    )
    db_session.add(active_update)
    db_session.commit()

    # Client is on version 0.9.0 which is lower than minApkVersion 1.0.0
    response = client.get(
        "/api/v1/updates/check",
        params={
            "platform": "android",
            "runtimeVersion": "1.0.0",
            "appVersion": "0.9.0",
            "currentBundleId": "20261117-01",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["updateType"] == "apk"
    assert data["mandatory"] is True
    assert data["minApkVersion"] == "1.0.0"
    assert data["apkUrl"] == "/api/v1/updates/apk/app-release.apk"
    assert data["apkSize"] == 39526501
    assert data["apkHash"] == "sha256-apkhash123"


def test_bundle_download(client: TestClient, test_updates_dir: Path):
    """Assert serves index.android.bundle with 200, application/javascript, and immutable cache headers."""
    bundle_dir = test_updates_dir / "bundles" / "1.0.0" / "20261117-01"
    bundle_dir.mkdir(parents=True, exist_ok=True)
    bundle_file = bundle_dir / "index.android.bundle"
    test_content = b"var __BUNDLE_START__ = true; console.log('ArchSchool OTA Bundle');"
    bundle_file.write_bytes(test_content)

    response = client.get("/api/v1/updates/bundle/1.0.0/20261117-01/index.android.bundle")

    assert response.status_code == 200
    assert "application/javascript" in response.headers.get("content-type", "").lower()
    assert "public" in response.headers.get("cache-control", "").lower()
    assert "immutable" in response.headers.get("cache-control", "").lower()
    assert response.content == test_content


def test_asset_download(client: TestClient, test_updates_dir: Path):
    """Assert serves bundle assets with appropriate mime type and cache headers."""
    asset_dir = test_updates_dir / "bundles" / "1.0.0" / "20261117-01" / "assets"
    asset_dir.mkdir(parents=True, exist_ok=True)
    asset_file = asset_dir / "logo.png"
    png_content = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDRdummy_png_bytes"
    asset_file.write_bytes(png_content)

    response = client.get("/api/v1/updates/assets/1.0.0/20261117-01/assets/logo.png")

    assert response.status_code == 200
    assert "image/png" in response.headers.get("content-type", "").lower()
    assert "immutable" in response.headers.get("cache-control", "").lower()
    assert response.content == png_content


def test_apk_download_full(client: TestClient, test_updates_dir: Path):
    """Assert serves APK file with status 200 OK, Content-Disposition, and Accept-Ranges: bytes."""
    apk_file = test_updates_dir / "apk" / "app-release.apk"
    apk_content = b"PK\x03\x04" + b"A" * 4092  # 4096 bytes dummy zip/apk
    apk_file.write_bytes(apk_content)

    # HEAD request check
    head_resp = client.head("/api/v1/updates/apk/app-release.apk")
    assert head_resp.status_code == 200
    assert head_resp.headers.get("accept-ranges") == "bytes"
    assert "application/vnd.android.package-archive" in head_resp.headers.get("content-type", "").lower()

    # GET full download
    response = client.get("/api/v1/updates/apk/app-release.apk")

    assert response.status_code == 200
    assert "application/vnd.android.package-archive" in response.headers.get("content-type", "").lower()
    assert "attachment" in response.headers.get("content-disposition", "").lower()
    assert "ArchSchool.apk" in response.headers.get("content-disposition", "") or "app-release.apk" in response.headers.get("content-disposition", "")
    assert response.headers.get("accept-ranges") == "bytes"
    assert len(response.content) == 4096
    assert response.content == apk_content


def test_apk_download_resumable_byte_range(client: TestClient, test_updates_dir: Path):
    """Assert handles HTTP Range header, returning 206 Partial Content, Content-Range, and exact slice."""
    apk_file = test_updates_dir / "apk" / "app-release.apk"
    apk_content = bytes(i % 256 for i in range(4096))  # 4096 distinct bytes
    apk_file.write_bytes(apk_content)

    # 1. Request first 1024 bytes (0-1023)
    response = client.get(
        "/api/v1/updates/apk/app-release.apk",
        headers={"Range": "bytes=0-1023"},
    )

    assert response.status_code == 206
    assert response.headers.get("content-range") == "bytes 0-1023/4096"
    assert len(response.content) == 1024
    assert response.content == apk_content[0:1024]

    # 2. Request second chunk (1024-2047)
    response_chunk2 = client.get(
        "/api/v1/updates/apk/app-release.apk",
        headers={"Range": "bytes=1024-2047"},
    )

    assert response_chunk2.status_code == 206
    assert response_chunk2.headers.get("content-range") == "bytes 1024-2047/4096"
    assert len(response_chunk2.content) == 1024
    assert response_chunk2.content == apk_content[1024:2048]


def test_storage_pruning(test_updates_dir: Path):
    """Assert creates 5 dummy bundle directories and prunes down to KEEP_BUNDLES_COUNT (3)."""
    bundles_root = test_updates_dir / "bundles" / "1.0.0"
    bundles_root.mkdir(parents=True, exist_ok=True)

    # Create 5 bundle directories with spaced modification times
    now = time.time()
    bundle_names = ["bundle_01", "bundle_02", "bundle_03", "bundle_04", "bundle_05"]
    for idx, name in enumerate(bundle_names):
        bdir = bundles_root / name
        bdir.mkdir(parents=True, exist_ok=True)
        (bdir / "index.android.bundle").write_text(f"console.log('{name}');")
        # Set artificial modification times: bundle_01 is oldest, bundle_05 is newest
        mtime = now - ((5 - idx) * 100)
        os.utime(bdir, (mtime, mtime))

    assert len(list(bundles_root.iterdir())) == 5

    # Run pruning with keep_count=3
    pruned = prune_superseded_bundles(
        runtime_version="1.0.0",
        keep_count=3,
        active_bundle_id="bundle_05",
        updates_dir=test_updates_dir,
    )

    remaining_dirs = sorted([p.name for p in bundles_root.iterdir()])
    assert len(remaining_dirs) == 3
    assert remaining_dirs == ["bundle_03", "bundle_04", "bundle_05"]
    assert "bundle_01" in pruned
    assert "bundle_02" in pruned
    assert not (bundles_root / "bundle_01").exists()
    assert not (bundles_root / "bundle_02").exists()


def test_json_fallback(client: TestClient, db_session: Session, test_updates_dir: Path):
    """Assert manifest retrieval succeeds reading from meta/updates.json when DB has no records."""
    # Ensure DB is empty
    db_session.query(models.AppUpdate).delete()
    db_session.commit()

    manifest_data = {
        "platform": "android",
        "runtimeVersion": "1.0.0",
        "bundleId": "fallback-bundle-2026",
        "bundleUrl": "/api/v1/updates/bundle/1.0.0/fallback-bundle-2026/index.android.bundle",
        "bundleHash": "sha256-jsonfallbackhash",
        "bundleSize": 5120,
        "mandatory": True,
        "minApkVersion": "1.0.0",
        "apkUrl": "/api/v1/updates/apk/app-release.apk",
        "apkSize": 39526501,
        "apkHash": "sha256-fallbackapk",
        "releaseNotes": "Emergency OTA delivery via JSON fallback",
        "assets": [
            {
                "key": "splash_img",
                "url": "/api/v1/updates/assets/1.0.0/fallback-bundle-2026/assets/splash.png",
                "hash": "sha256-splash",
                "size": 1024,
            }
        ],
    }

    meta_file = test_updates_dir / "meta" / "updates.json"
    meta_file.write_text(json.dumps(manifest_data), encoding="utf-8")

    response = client.get(
        "/api/v1/updates/check",
        params={
            "platform": "android",
            "runtimeVersion": "1.0.0",
            "appVersion": "1.0.0",
            "currentBundleId": "old-client-bundle",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["updateType"] == "ota"
    assert data["bundleId"] == "fallback-bundle-2026"
    assert data["bundleHash"] == "sha256-jsonfallbackhash"
    assert data["bundleSize"] == 5120
    assert data["mandatory"] is True
    assert len(data["assets"]) == 1
    assert data["assets"][0]["key"] == "splash_img"


def test_path_traversal_blocked(client: TestClient, test_updates_dir: Path):
    """Assert path traversal attempts are blocked with 400 Bad Request."""
    from fastapi import HTTPException
    from app.routers.updates import _safe_resolve, _validate_safe_name

    with pytest.raises(HTTPException) as exc_info:
        _validate_safe_name("..", "runtime_version")
    assert exc_info.value.status_code == 400

    with pytest.raises(HTTPException) as exc_info:
        _validate_safe_name("../../etc/passwd", "apk_name")
    assert exc_info.value.status_code == 400

    with pytest.raises(HTTPException) as exc_info:
        _safe_resolve(test_updates_dir, "..", "secret.txt")
    assert exc_info.value.status_code == 400

    with pytest.raises(HTTPException) as exc_info:
        _safe_resolve(test_updates_dir, "bundles", "1.0.0", "..", "..", "windows", "system32")
    assert exc_info.value.status_code == 400

