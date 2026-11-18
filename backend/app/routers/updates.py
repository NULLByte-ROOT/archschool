import base64
import hashlib
import json
import logging
import mimetypes
import re
import shutil
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from starlette.responses import FileResponse
from sqlalchemy.orm import Session

from .. import models, schemas
from ..config import settings
from ..database import get_db

logger = logging.getLogger("archschool.updates")

router = APIRouter()

# Security regex patterns
_SAFE_PARAM_PATTERN = re.compile(r"^[a-zA-Z0-9_\.-]+$")
_SAFE_ASSET_PATTERN = re.compile(r"^[a-zA-Z0-9_\.-]+(/[a-zA-Z0-9_\.-]+)*$")


def _get_updates_dir(custom_dir: Optional[Path | str] = None) -> Path:
    if custom_dir:
        d = Path(custom_dir)
    else:
        d = Path(settings.UPDATES_DIR)
        if not (d / "bundles").exists():
            backend_updates = Path(__file__).resolve().parent.parent.parent / "updates"
            if (backend_updates / "bundles").exists():
                d = backend_updates
    d.mkdir(parents=True, exist_ok=True)
    return d


def _parse_version(v: Optional[str]) -> tuple[int, ...]:
    """Parse version string like '1.2.3' into tuple (1, 2, 3) for semver comparison."""
    if not v:
        return (0,)
    parts = [int(p) for p in re.findall(r"\d+", v)]
    return tuple(parts) if parts else (0,)


def _validate_safe_name(name: str, label: str = "Parameter") -> str:
    if not name or not _SAFE_PARAM_PATTERN.match(name) or len(name) > 100:
        raise HTTPException(status_code=400, detail=f"Invalid {label}")
    if name == ".." or name == "." or ".." in name:
        raise HTTPException(status_code=400, detail=f"Invalid {label}")
    return name


def _safe_resolve(base_dir: Path, *segments: str) -> Path:
    """Resolve child path within base_dir, blocking path traversal attacks."""
    for s in segments:
        if ".." in s.split("/") or ".." in s.split("\\"):
            raise HTTPException(status_code=400, detail="Invalid path")
    resolved_base = base_dir.resolve()
    target = resolved_base.joinpath(*segments).resolve()
    if not target.is_relative_to(resolved_base):
        logger.warning("Path traversal attempt blocked: base=%s target=%s", resolved_base, target)
        raise HTTPException(status_code=400, detail="Invalid path")
    return target


def _load_manifest_fallback(platform: str, runtime_version: str) -> Optional[dict]:
    """Fallback to meta/updates.json if database query fails or yields no active record."""
    manifest_file = _get_updates_dir() / "meta" / "updates.json"
    if not manifest_file.is_file():
        return None
    try:
        with manifest_file.open("r", encoding="utf-8") as f:
            data = json.load(f)

        if isinstance(data, dict) and "updates" in data and isinstance(data["updates"], list):
            for item in data["updates"]:
                if (
                    item.get("platform", "android") == platform
                    and item.get("runtimeVersion") == runtime_version
                    and item.get("isActive", True)
                ):
                    return item
        elif isinstance(data, list):
            for item in data:
                if (
                    isinstance(item, dict)
                    and item.get("platform", "android") == platform
                    and item.get("runtimeVersion") == runtime_version
                    and item.get("isActive", True)
                ):
                    return item
        elif isinstance(data, dict):
            if (
                data.get("platform", "android") == platform
                and data.get("runtimeVersion") == runtime_version
                and data.get("isActive", True)
            ):
                return data
    except Exception as exc:
        logger.error("Failed to read manifest fallback updates.json: %s", exc)
    return None


def prune_superseded_bundles(
    runtime_version: str,
    keep_count: int,
    active_bundle_id: Optional[str] = None,
    updates_dir: Optional[Path | str] = None,
) -> list[str]:
    """Prune obsolete bundle subdirectories, preserving active bundle."""
    base_dir = _get_updates_dir(updates_dir)
    bundles_dir = base_dir / "bundles" / runtime_version
    if not bundles_dir.exists() or not bundles_dir.is_dir():
        return []

    subdirs = [p for p in bundles_dir.iterdir() if p.is_dir() and not p.name.startswith(".")]
    if len(subdirs) <= keep_count:
        return []

    # Sort newest first by modification time
    subdirs.sort(key=lambda p: (p.stat().st_mtime, p.name), reverse=True)

    kept: list[Path] = []
    pruned: list[str] = []

    # Always preserve active bundle
    if active_bundle_id:
        for d in subdirs:
            if d.name == active_bundle_id:
                kept.append(d)
                break

    for d in subdirs:
        if d in kept:
            continue
        if len(kept) < keep_count:
            kept.append(d)
        else:
            try:
                shutil.rmtree(d)
                pruned.append(d.name)
                logger.info("Pruned old bundle directory: %s", d)
            except Exception as exc:
                logger.error("Failed to delete bundle directory %s: %s", d, exc)

    return pruned


# Backward compatibility alias
prune_old_bundles = prune_superseded_bundles


@router.get("/check", response_model=schemas.UpdateCheckResponse)
@router.get("/manifest", include_in_schema=False)
def check_for_updates(
    request: Request,
    platform: Optional[str] = Query(None, pattern=r"^[a-zA-Z0-9_\.-]+$"),
    runtimeVersion: Optional[str] = Query(None, pattern=r"^[a-zA-Z0-9_\.-]+$"),
    appVersion: Optional[str] = Query(None, pattern=r"^[a-zA-Z0-9_\.-]+$"),
    currentBundleId: Optional[str] = Query(None, pattern=r"^[a-zA-Z0-9_\.-]+$"),
    db: Session = Depends(get_db),
):
    """Silent startup check determining if client needs APK binary update, OTA bundle, or none."""
    header_platform = request.headers.get("expo-platform")
    header_runtime = request.headers.get("expo-runtime-version")
    resolved_platform = str(platform or header_platform or "android")
    resolved_runtime = str(runtimeVersion or header_runtime or "1.0.0")
    resolved_app_ver = appVersion if isinstance(appVersion, str) and appVersion else None
    resolved_bundle_id = currentBundleId if isinstance(currentBundleId, str) and currentBundleId else None
    fallback_version = resolved_app_ver or resolved_runtime

    record = None
    try:
        record = (
            db.query(models.AppUpdate)
            .filter(
                models.AppUpdate.platform == resolved_platform,
                models.AppUpdate.runtime_version == resolved_runtime,
                models.AppUpdate.is_active == True,
            )
            .order_by(models.AppUpdate.created_at.desc(), models.AppUpdate.id.desc())
            .first()
        )
    except Exception as exc:
        logger.warning("DB query failed for updates check: %s, checking JSON fallback", exc)

    # Convert to unified dict format
    update_data = None
    if record:
        try:
            assets_raw = json.loads(record.assets_json) if record.assets_json else []
        except Exception:
            assets_raw = []
        update_data = {
            "bundleId": record.bundle_id,
            "bundleUrl": record.bundle_url,
            "bundleHash": record.bundle_hash,
            "bundleSize": record.bundle_size,
            "mandatory": record.mandatory,
            "minApkVersion": record.min_apk_version or settings.MIN_APK_VERSION,
            "apkUrl": record.apk_url or "/api/v1/updates/apk/app-release.apk",
            "apkSize": record.apk_size,
            "apkHash": record.apk_hash,
            "releaseNotes": record.release_notes,
            "createdAt": record.created_at,
            "assets": [schemas.AssetInfo(**a) for a in assets_raw],
        }
    else:
        fallback = _load_manifest_fallback(resolved_platform, resolved_runtime)
        if fallback:
            assets_raw = fallback.get("assets", [])
            update_data = {
                "bundleId": fallback.get("bundleId"),
                "bundleUrl": fallback.get("bundleUrl"),
                "bundleHash": fallback.get("bundleHash"),
                "bundleSize": fallback.get("bundleSize"),
                "mandatory": fallback.get("mandatory", False),
                "minApkVersion": fallback.get("minApkVersion", settings.MIN_APK_VERSION),
                "apkUrl": fallback.get("apkUrl", "/api/v1/updates/apk/app-release.apk"),
                "apkSize": fallback.get("apkSize"),
                "apkHash": fallback.get("apkHash"),
                "releaseNotes": fallback.get("releaseNotes", ""),
                "createdAt": fallback.get("createdAt"),
                "assets": [schemas.AssetInfo(**a) for a in assets_raw],
            }

    if not update_data:
        return schemas.UpdateCheckResponse(
            updateType="none",
            version=fallback_version,
            bundleId=resolved_bundle_id,
            mandatory=False,
        )

    # 1. Native APK check
    min_apk = update_data.get("minApkVersion")
    if min_apk and resolved_app_ver and _parse_version(resolved_app_ver) < _parse_version(min_apk):
        return schemas.UpdateCheckResponse(
            updateType="apk",
            version=min_apk,
            mandatory=True,
            minApkVersion=min_apk,
            apkUrl=update_data.get("apkUrl"),
            apkSize=update_data.get("apkSize"),
            apkHash=update_data.get("apkHash"),
            releaseNotes=update_data.get("releaseNotes", ""),
            createdAt=update_data.get("createdAt"),
        )

    # 2. OTA Bundle check
    active_bundle_id = update_data.get("bundleId")
    if resolved_bundle_id and active_bundle_id == resolved_bundle_id:
        return schemas.UpdateCheckResponse(
            updateType="none",
            version=fallback_version,
            bundleId=active_bundle_id,
            mandatory=False,
            releaseNotes=update_data.get("releaseNotes", ""),
        )

    # 3. Native expo-updates protocol check (Protocol Version 1)
    if request.headers.get("expo-protocol-version") == "1":
        boundary = "archschool_ota_boundary"
        active_b_id = active_bundle_id or "b-1795027345"
        raw_hash = hashlib.sha256(active_b_id.encode("utf-8")).hexdigest()
        manifest_uuid = f"{raw_hash[:8]}-{raw_hash[8:12]}-{raw_hash[12:16]}-{raw_hash[16:20]}-{raw_hash[20:32]}"

        client_update_id = request.headers.get("expo-current-update-id")
        if client_update_id and client_update_id.lower() == manifest_uuid.lower():
            content = (
                f"--{boundary}\r\n"
                f'Content-Disposition: inline; name="directive"\r\n'
                f"Content-Type: application/json; charset=utf-8\r\n\r\n"
                f'{json.dumps({"type": "noUpdateAvailable"})}\r\n'
                f"--{boundary}--\r\n"
            )
            return Response(
                content=content.encode("utf-8"),
                media_type=f'multipart/mixed; boundary="{boundary}"',
                headers={
                    "expo-protocol-version": "1",
                    "expo-sfv-version": "0",
                    "cache-control": "private, max-age=0",
                },
            )

        b_hash = update_data.get("bundleHash") or ""
        try:
            b_hash_b64 = base64.urlsafe_b64encode(bytes.fromhex(b_hash)).decode("utf-8").rstrip("=")
        except Exception:
            b_hash_b64 = b_hash

        bundle_path = update_data.get("bundleUrl", "")
        bundle_full_url = (
            bundle_path
            if bundle_path.startswith("http")
            else f"{settings.HOST_URL or 'https://archschool.vidxsepehr.ir'}{bundle_path}"
        )

        manifest_obj = {
            "id": manifest_uuid,
            "createdAt": str(update_data.get("createdAt") or "2026-11-18T19:00:00.000Z"),
            "runtimeVersion": resolved_runtime,
            "launchAsset": {
                "hash": b_hash_b64,
                "key": active_b_id,
                "contentType": "application/javascript",
                "url": bundle_full_url,
            },
            "assets": [],
            "metadata": {},
            "extra": {
                "expoClient": {
                    "name": "ArchSchool",
                    "slug": "archschool",
                    "version": resolved_app_ver or "1.0.0",
                }
            },
        }

        content = (
            f"--{boundary}\r\n"
            f'Content-Disposition: inline; name="manifest"\r\n'
            f"Content-Type: application/json; charset=utf-8\r\n\r\n"
            f"{json.dumps(manifest_obj)}\r\n"
            f"--{boundary}\r\n"
            f'Content-Disposition: inline; name="extensions"\r\n'
            f"Content-Type: application/json; charset=utf-8\r\n\r\n"
            f'{json.dumps({"assetRequestHeaders": {}})}\r\n'
            f"--{boundary}--\r\n"
        )
        return Response(
            content=content.encode("utf-8"),
            media_type=f'multipart/mixed; boundary="{boundary}"',
            headers={
                "expo-protocol-version": "1",
                "expo-sfv-version": "0",
                "cache-control": "private, max-age=0",
            },
        )

    return schemas.UpdateCheckResponse(
        updateType="ota",
        version=fallback_version,
        bundleId=active_bundle_id,
        bundleUrl=update_data.get("bundleUrl"),
        bundleHash=update_data.get("bundleHash"),
        bundleSize=update_data.get("bundleSize"),
        assets=update_data.get("assets", []),
        mandatory=update_data.get("mandatory", False),
        releaseNotes=update_data.get("releaseNotes", ""),
        createdAt=update_data.get("createdAt"),
    )


@router.api_route("/bundle/{runtime_version}/{bundle_id}/index.android.bundle", methods=["GET", "HEAD"])
def get_bundle_file(runtime_version: str, bundle_id: str):
    """Serve JavaScript bundle with immutable caching headers."""
    _validate_safe_name(runtime_version, "runtime_version")
    _validate_safe_name(bundle_id, "bundle_id")

    bundles_dir = _get_updates_dir() / "bundles"
    bundle_file = _safe_resolve(bundles_dir, runtime_version, bundle_id, "index.android.bundle")

    if not bundle_file.is_file():
        raise HTTPException(status_code=404, detail="Bundle file not found")

    return FileResponse(
        bundle_file,
        media_type="application/javascript",
        headers={
            "Cache-Control": "public, max-age=31536000, immutable",
            "Accept-Ranges": "bytes",
        },
    )


@router.api_route("/assets/{runtime_version}/{bundle_id}/{asset_path:path}", methods=["GET", "HEAD"])
def get_asset_file(runtime_version: str, bundle_id: str, asset_path: str):
    """Serve bundle assets (images, fonts) with immutable caching."""
    _validate_safe_name(runtime_version, "runtime_version")
    _validate_safe_name(bundle_id, "bundle_id")

    if not _SAFE_ASSET_PATTERN.match(asset_path) or ".." in asset_path.split("/"):
        raise HTTPException(status_code=400, detail="Invalid asset path")

    bundles_dir = _get_updates_dir() / "bundles"
    asset_file = _safe_resolve(bundles_dir, runtime_version, bundle_id, asset_path)

    if not asset_file.is_file():
        raise HTTPException(status_code=404, detail="Asset not found")

    media_type, _ = mimetypes.guess_type(str(asset_file))
    return FileResponse(
        asset_file,
        media_type=media_type or "application/octet-stream",
        headers={
            "Cache-Control": "public, max-age=31536000, immutable",
            "Accept-Ranges": "bytes",
        },
    )


@router.api_route("/apk/{apk_name}", methods=["GET", "HEAD"])
def download_apk(apk_name: str = "app-release.apk"):
    """Resumable APK binary streaming with HTTP 206 byte ranges and HEAD support."""
    _validate_safe_name(apk_name, "apk_name")
    if not apk_name.endswith(".apk"):
        raise HTTPException(status_code=400, detail="Only APK files may be downloaded")

    apk_dir = _get_updates_dir() / "apk"
    apk_file = _safe_resolve(apk_dir, apk_name)

    if not apk_file.is_file():
        raise HTTPException(status_code=404, detail="APK binary not found")

    return FileResponse(
        apk_file,
        media_type="application/vnd.android.package-archive",
        filename=apk_name,
        content_disposition_type="attachment",
        headers={
            "X-Accel-Buffering": "no",
            "Cache-Control": "public, max-age=3600",
        },
    )
