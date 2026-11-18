const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

function sha256(filePath) {
  const data = fs.readFileSync(filePath);
  return crypto.createHash('sha256').update(data).digest('hex');
}

const distDir = path.resolve('D:/Site/archschool-mobile/dist');
const updatesDir = path.resolve('D:/Site/archschool/backend/updates');
const runtimeVersion = '1.0.0';
const bundleId = `b-${Math.floor(Date.now() / 1000)}`;

const bundleDir = path.join(updatesDir, 'bundles', runtimeVersion, bundleId);
const targetAssetsDir = path.join(bundleDir, 'assets');

fs.mkdirSync(bundleDir, { recursive: true });
fs.mkdirSync(targetAssetsDir, { recursive: true });

// 1. Copy bundle
const jsDir = path.join(distDir, '_expo', 'static', 'js', 'android');
const files = fs.readdirSync(jsDir);
const bundleSource = files.find(f => f.endsWith('.hbc') || f.endsWith('.js'));
if (!bundleSource) {
  console.error('No bundle found in ' + jsDir);
  process.exit(1);
}

const targetBundle = path.join(bundleDir, 'index.android.bundle');
fs.copyFileSync(path.join(jsDir, bundleSource), targetBundle);
const bundleHash = sha256(targetBundle);
const bundleSize = fs.statSync(targetBundle).size;

// 2. Copy assets
const sourceAssetsDir = path.join(distDir, 'assets');
const assetList = [];

function copyRecursive(src, dest, relPrefix = '') {
  if (!fs.existsSync(src)) return;
  const entries = fs.readdirSync(src, { withFileTypes: true });
  for (const ent of entries) {
    const srcPath = path.join(src, ent.name);
    const destPath = path.join(dest, ent.name);
    const relKey = relPrefix ? `${relPrefix}/${ent.name}` : ent.name;

    if (ent.isDirectory()) {
      fs.mkdirSync(destPath, { recursive: true });
      copyRecursive(srcPath, destPath, relKey);
    } else {
      fs.copyFileSync(srcPath, destPath);
      const hash = sha256(destPath);
      const size = fs.statSync(destPath).size;
      assetList.push({
        key: `assets/${relKey.replace(/\\/g, '/')}`,
        url: `/api/v1/updates/assets/${runtimeVersion}/${bundleId}/assets/${relKey.replace(/\\/g, '/')}`,
        hash,
        size
      });
    }
  }
}

copyRecursive(sourceAssetsDir, targetAssetsDir);

// 3. Update meta/updates.json
const metaDir = path.join(updatesDir, 'meta');
fs.mkdirSync(metaDir, { recursive: true });
const manifestFile = path.join(metaDir, 'updates.json');

let currentData = { updates: [] };
if (fs.existsSync(manifestFile)) {
  try {
    currentData = JSON.parse(fs.readFileSync(manifestFile, 'utf8'));
    if (!currentData.updates) currentData = { updates: [] };
  } catch (e) {
    currentData = { updates: [] };
  }
}

// Mark existing as inactive
for (const u of currentData.updates) {
  if (u.platform === 'android' && u.runtimeVersion === runtimeVersion) {
    u.isActive = false;
  }
}

const newEntry = {
  platform: 'android',
  runtimeVersion,
  bundleId,
  bundleUrl: `/api/v1/updates/bundle/${runtimeVersion}/${bundleId}/index.android.bundle`,
  bundleHash,
  bundleSize,
  assets: assetList,
  mandatory: false,
  minApkVersion: null,
  apkUrl: null,
  apkSize: null,
  apkHash: null,
  releaseNotes: 'بازطراحی کارت وضعیت کلاس با برنامه روز بعد و حذف زنگ‌های امروز',
  isActive: true,
  createdAt: new Date().toISOString()
};

currentData.updates.unshift(newEntry);
// Keep last 10
currentData.updates = currentData.updates.slice(0, 10);

fs.writeFileSync(manifestFile, JSON.stringify(currentData, null, 2), 'utf8');

console.log(`Successfully synced update bundle ${bundleId}:`);
console.log(`- Bundle size: ${bundleSize} bytes`);
console.log(`- Bundle hash: ${bundleHash}`);
console.log(`- Assets copied: ${assetList.length}`);
console.log(`- Manifest updated: ${manifestFile}`);
