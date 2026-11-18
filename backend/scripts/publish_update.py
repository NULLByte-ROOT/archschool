#!/usr/bin/env python3
"""
ArchSchool Mobile Update Publisher
==================================
Packages and deploys self-hosted OTA JavaScript bundles and APK binaries
to the ArchSchool update server without Expo/EAS cloud dependencies.

Usage:
  python publish_update.py --dist-dir <path_to_expo_dist> [options]
  python publish_update.py --bundle-file <path_to_bundle> [options]
  python publish_update.py --apk-file <path_to_apk> [options]
"""

import argparse
import hashlib
import json
import logging
import os
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("publish_update")

# Add backend directory to sys.path so app modules can be imported
SCRIPT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = SCRIPT_DIR.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


def sha256_file(filepath: Path) -> str:
    h = hashlib.sha256()
    with filepath.open("rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def detect_runtime_version(mobile_dir: Optional[Path]) -> str:
    """Attempt to detect runtimeVersion or version from app.json / package.json."""
    if not mobile_dir or not mobile_dir.exists():
        return "1.0.0"

    app_json = mobile_dir / "app.json"
    if app_json.exists():
        try:
            with app_json.open("r", encoding="utf-8") as f:
                data = json.load(f)
            expo_cfg = data.get("expo", {})
            runtime_v = expo_cfg.get("runtimeVersion")
            if isinstance(runtime_v, str) and runtime_v.strip():
                return runtime_v.strip()
            if isinstance(runtime_v, dict) and "policy" in runtime_v:
                # If policy is appVersion, check version
                ver = expo_cfg.get("version")
                if ver:
                    return str(ver).strip()
            ver = expo_cfg.get("version")
            if ver:
                return str(ver).strip()
        except Exception:
            pass

    pkg_json = mobile_dir / "package.json"
    if pkg_json.exists():
        try:
            with pkg_json.open("r", encoding="utf-8") as f:
                data = json.load(f)
            ver = data.get("version")
            if ver:
                return str(ver).strip()
        except Exception:
            pass

    return "1.0.0"


def find_bundle_in_dist(dist_dir: Path) -> Optional[Path]:
    """Locate the exported JavaScript/Hermes bundle inside an expo export dist directory."""
    # Check standard expo export structure: _expo/static/js/android/*.hbc or *.js
    js_dir = dist_dir / "_expo" / "static" / "js" / "android"
    if js_dir.exists():
        bundles = list(js_dir.glob("*.hbc")) or list(js_dir.glob("*.js"))
        if bundles:
            return bundles[0]

    # Check root dist for index.android.bundle or *.bundle or *.hbc
    for pattern in ("index.android.bundle", "*.bundle", "*.hbc", "*.js"):
        matches = list(dist_dir.glob(pattern))
        if matches:
            return matches[0]

    # Recursive search for large JS or bytecode files
    candidates = []
    for p in dist_dir.rglob("*"):
        if p.is_file() and p.suffix in (".bundle", ".hbc", ".js") and not p.name.endswith(".map"):
            candidates.append(p)
    if candidates:
        # Sort largest first
        candidates.sort(key=lambda p: p.stat().st_size, reverse=True)
        return candidates[0]

    return None


def collect_assets(dist_dir: Path, target_assets_dir: Path, runtime_version: str, bundle_id: str) -> List[Dict[str, Any]]:
    """Copies assets to target directory and returns metadata array."""
    assets: List[Dict[str, Any]] = []
    source_assets = dist_dir / "assets"
    if not source_assets.exists() or not source_assets.is_dir():
        return assets

    for p in source_assets.rglob("*"):
        if p.is_file():
            rel_path = p.relative_to(source_assets).as_posix()
            asset_key = f"assets/{rel_path}"
            dest = target_assets_dir / rel_path
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(p, dest)

            file_size = p.stat().st_size
            file_hash = sha256_file(p)
            assets.append({
                "key": asset_key,
                "url": f"/api/v1/updates/assets/{runtime_version}/{bundle_id}/{asset_key}",
                "hash": file_hash,
                "size": file_size,
            })

    return assets


def update_database(update_data: Dict[str, Any], db_url: Optional[str] = None) -> bool:
    """Persist update record to database (PostgreSQL / SQLite)."""
    try:
        from app.database import get_db, SessionLocal, engine
        from app import models

        # Ensure tables exist
        models.Base.metadata.create_all(bind=engine)

        db = SessionLocal()
        try:
            # Mark previous active records for this platform/runtime_version as inactive
            db.query(models.AppUpdate).filter(
                models.AppUpdate.platform == update_data["platform"],
                models.AppUpdate.runtime_version == update_data["runtime_version"],
                models.AppUpdate.is_active == True,
            ).update({"is_active": False})

            record = models.AppUpdate(
                platform=update_data["platform"],
                runtime_version=update_data["runtime_version"],
                bundle_id=update_data.get("bundle_id"),
                bundle_url=update_data.get("bundle_url"),
                bundle_hash=update_data.get("bundle_hash"),
                bundle_size=update_data.get("bundle_size"),
                assets_json=json.dumps(update_data.get("assets", [])),
                min_apk_version=update_data.get("min_apk_version"),
                apk_url=update_data.get("apk_url"),
                apk_size=update_data.get("apk_size"),
                apk_hash=update_data.get("apk_hash"),
                mandatory=update_data.get("mandatory", False),
                release_notes=update_data.get("release_notes", ""),
                is_active=True,
            )
            db.add(record)
            db.commit()
            logger.info("Successfully updated AppUpdate record in database.")
            return True
        finally:
            db.close()
    except Exception as exc:
        logger.warning("Could not persist update to database (%s). Relying on updates.json fallback.", exc)
        return False


def update_json_manifest(updates_dir: Path, update_data: Dict[str, Any]) -> None:
    """Updates meta/updates.json with rolling release metadata."""
    meta_dir = updates_dir / "meta"
    meta_dir.mkdir(parents=True, exist_ok=True)
    manifest_file = meta_dir / "updates.json"

    current_data: Dict[str, Any] = {"updates": []}
    if manifest_file.exists():
        try:
            with manifest_file.open("r", encoding="utf-8") as f:
                loaded = json.load(f)
                if isinstance(loaded, dict) and "updates" in loaded:
                    current_data = loaded
                elif isinstance(loaded, list):
                    current_data = {"updates": loaded}
        except Exception:
            current_data = {"updates": []}

    # Deactivate older records with same platform and runtimeVersion
    updates_list = current_data.get("updates", [])
    for u in updates_list:
        if (
            u.get("platform") == update_data["platform"]
            and u.get("runtimeVersion") == update_data["runtime_version"]
        ):
            u["isActive"] = False

    new_entry = {
        "platform": update_data["platform"],
        "runtimeVersion": update_data["runtime_version"],
        "bundleId": update_data.get("bundle_id"),
        "bundleUrl": update_data.get("bundle_url"),
        "bundleHash": update_data.get("bundle_hash"),
        "bundleSize": update_data.get("bundle_size"),
        "assets": update_data.get("assets", []),
        "mandatory": update_data.get("mandatory", False),
        "minApkVersion": update_data.get("min_apk_version"),
        "apkUrl": update_data.get("apk_url"),
        "apkSize": update_data.get("apk_size"),
        "apkHash": update_data.get("apk_hash"),
        "releaseNotes": update_data.get("release_notes", ""),
        "isActive": True,
        "createdAt": datetime.now(timezone.utc).isoformat(),
    }

    # Prepend new entry
    updates_list.insert(0, new_entry)
    # Keep up to 20 manifest entries in history
    current_data["updates"] = updates_list[:20]

    temp_manifest = meta_dir / "updates.json.tmp"
    with temp_manifest.open("w", encoding="utf-8") as f:
        json.dump(current_data, f, indent=2, ensure_ascii=False)
    temp_manifest.replace(manifest_file)
    logger.info("Updated manifest file at %s", manifest_file)


def main():
    parser = argparse.ArgumentParser(description="Publish ArchSchool self-hosted mobile updates")
    parser.add_argument("--platform", default="android", choices=["android", "ios"], help="Target platform")
    parser.add_argument("--runtime-version", default=None, help="Runtime version (e.g. 1.0.0)")
    parser.add_argument("--dist-dir", default=None, help="Directory containing exported files from 'expo export'")
    parser.add_argument("--bundle-file", default=None, help="Direct path to index.android.bundle")
    parser.add_argument("--apk-file", default=None, help="Path to new app-release.apk to publish")
    parser.add_argument("--min-apk-version", default=None, help="Minimum APK version required")
    parser.add_argument("--release-notes", default="", help="Release notes text")
    parser.add_argument("--mandatory", action="store_true", help="Mark update as mandatory")
    parser.add_argument("--keep-count", type=int, default=2, help="Number of bundle versions to retain")
    parser.add_argument("--updates-dir", default=None, help="Custom updates storage root (defaults to uploads/updates)")
    parser.add_argument("--mobile-dir", default=None, help="Path to archschool-mobile directory")
    parser.add_argument("--bundle-id", default=None, help="Custom bundle ID (defaults to b-TIMESTAMP)")

    args = parser.parse_args()

    mobile_dir = Path(args.mobile_dir) if args.mobile_dir else BACKEND_DIR.parent / "archschool-mobile"
    runtime_v = args.runtime_version or detect_runtime_version(mobile_dir)
    logger.info("Target runtime version: %s (platform: %s)", runtime_v, args.platform)

    updates_dir = Path(args.updates_dir) if args.updates_dir else BACKEND_DIR / "uploads" / "updates"
    updates_dir.mkdir(parents=True, exist_ok=True)

    bundle_id = args.bundle_id or f"b-{int(time.time())}"
    target_bundle_dir = updates_dir / "bundles" / runtime_v / bundle_id
    target_assets_dir = target_bundle_dir / "assets"

    bundle_dest = target_bundle_dir / "index.android.bundle"
    bundle_hash = None
    bundle_size = None
    assets = []

    # 1. Process Dist Directory or Bundle File
    if args.dist_dir:
        dist_path = Path(args.dist_dir)
        if not dist_path.exists() or not dist_path.is_dir():
            logger.error("Dist directory does not exist: %s", dist_path)
            sys.exit(1)

        source_bundle = find_bundle_in_dist(dist_path)
        if not source_bundle:
            logger.error("Could not find bundle file inside %s", dist_path)
            sys.exit(1)

        target_bundle_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_bundle, bundle_dest)
        bundle_hash = sha256_file(bundle_dest)
        bundle_size = bundle_dest.stat().st_size
        logger.info("Copied bundle to %s (size: %d bytes, hash: %s)", bundle_dest, bundle_size, bundle_hash[:12])

        assets = collect_assets(dist_path, target_assets_dir, runtime_v, bundle_id)
        logger.info("Collected %d associated assets.", len(assets))

    elif args.bundle_file:
        source_bundle = Path(args.bundle_file)
        if not source_bundle.exists() or not source_bundle.is_file():
            logger.error("Bundle file does not exist: %s", source_bundle)
            sys.exit(1)

        target_bundle_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_bundle, bundle_dest)
        bundle_hash = sha256_file(bundle_dest)
        bundle_size = bundle_dest.stat().st_size
        logger.info("Copied bundle to %s (size: %d bytes)", bundle_dest, bundle_size)

    # 2. Process APK if provided
    apk_url = None
    apk_hash = None
    apk_size = None
    if args.apk_file:
        apk_source = Path(args.apk_file)
        if not apk_source.exists() or not apk_source.is_file():
            logger.error("APK file does not exist: %s", apk_source)
            sys.exit(1)

        target_apk_dir = updates_dir / "apk"
        target_apk_dir.mkdir(parents=True, exist_ok=True)
        target_apk = target_apk_dir / "app-release.apk"
        shutil.copy2(apk_source, target_apk)

        apk_hash = sha256_file(target_apk)
        apk_size = target_apk.stat().st_size
        apk_url = "/api/v1/updates/apk/app-release.apk"
        logger.info("Published APK to %s (size: %d bytes, hash: %s)", target_apk, apk_size, apk_hash[:12])

    # Check if anything was updated
    if not bundle_dest.exists() and not apk_url:
        logger.error("Nothing to publish! Provide either --dist-dir, --bundle-file, or --apk-file.")
        sys.exit(1)

    bundle_url = (
        f"/api/v1/updates/bundle/{runtime_v}/{bundle_id}/index.android.bundle"
        if bundle_dest.exists()
        else None
    )

    update_payload = {
        "platform": args.platform,
        "runtime_version": runtime_v,
        "bundle_id": bundle_id if bundle_dest.exists() else None,
        "bundle_url": bundle_url,
        "bundle_hash": bundle_hash,
        "bundle_size": bundle_size,
        "assets": assets,
        "mandatory": args.mandatory,
        "min_apk_version": args.min_apk_version,
        "apk_url": apk_url,
        "apk_size": apk_size,
        "apk_hash": apk_hash,
        "release_notes": args.release_notes,
    }

    # 3. Update Database and Manifest Fallback
    update_database(update_payload)
    update_json_manifest(updates_dir, update_payload)

    # 4. Prune obsolete bundles
    from app.routers.updates import prune_superseded_bundles
    pruned = prune_superseded_bundles(
        runtime_version=runtime_v,
        keep_count=args.keep_count,
        active_bundle_id=bundle_id,
        updates_dir=updates_dir,
    )
    if pruned:
        logger.info("Pruned %d superseded bundles: %s", len(pruned), ", ".join(pruned))
    else:
        logger.info("Bundle storage is clean; no obsolete bundles pruned.")

    logger.info("✅ ArchSchool update published successfully!")
    logger.info("Runtime: %s | Bundle ID: %s | Mandatory: %s", runtime_v, bundle_id, args.mandatory)


if __name__ == "__main__":
    main()
