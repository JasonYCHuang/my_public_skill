#!/usr/bin/env node
/**
 * Convert generated calendar HTML files to full-page PNG screenshots.
 *
 * Requires puppeteer-core (npm install puppeteer-core in this scripts/ dir,
 * once). Prefers a system-installed Chrome/Chromium; if that's not present
 * (e.g. a container/CI Linux box with no root), falls back to a Chrome
 * downloaded via `npx puppeteer browsers install chrome` under
 * ~/.cache/puppeteer.
 *
 * Usage:
 *   node screenshot.js <dir-with-html-files> [file1.html file2.html ...]
 *
 * If no filenames are given, every *.html file in the directory is shot.
 * Each output PNG is written next to its source HTML with the same name.
 */
const fs = require('fs');
const os = require('os');
const path = require('path');
const puppeteer = require('puppeteer-core');

// Puppeteer names its cache entries <platform>-<version>. The platform tag
// is arch-specific: Apple Silicon is "mac_arm" (inner folder
// chrome-mac-arm64), Intel Macs are "mac" (chrome-mac-x64). Keying off
// process.platform alone silently misses every arm64 Mac.
const CHROME_CACHE_PREFIX = {
  'darwin-arm64': 'mac_arm-',
  'darwin-x64': 'mac-',
  'linux-x64': 'linux-',
  'linux-arm64': 'linux-',
  'win32-x64': 'win64-',
};

// Relative paths to the executable inside a cache entry, all platforms. We
// probe rather than compute: cheaper than tracking Puppeteer's layout per
// arch, and a renamed folder degrades to "not found" instead of a crash.
const CHROME_EXE_LAYOUTS = [
  ['chrome-mac-arm64', 'Google Chrome for Testing.app', 'Contents', 'MacOS', 'Google Chrome for Testing'],
  ['chrome-mac-x64', 'Google Chrome for Testing.app', 'Contents', 'MacOS', 'Google Chrome for Testing'],
  ['chrome-linux64', 'chrome'],
  ['chrome-win64', 'chrome.exe'],
];

function findDownloadedChrome() {
  const cacheDir = process.env.PUPPETEER_CACHE_DIR || path.join(os.homedir(), '.cache', 'puppeteer');
  const chromeDir = path.join(cacheDir, 'chrome');
  if (!fs.existsSync(chromeDir)) return null;

  const prefix = CHROME_CACHE_PREFIX[`${process.platform}-${process.arch}`];
  if (!prefix) return null;

  // Numeric compare, else "chrome-99" sorts above "chrome-145".
  const entries = fs
    .readdirSync(chromeDir)
    .filter((e) => e.startsWith(prefix))
    .sort((a, b) => a.localeCompare(b, undefined, { numeric: true }))
    .reverse();

  for (const entry of entries) {
    for (const layout of CHROME_EXE_LAYOUTS) {
      const exe = path.join(chromeDir, entry, ...layout);
      if (fs.existsSync(exe)) return exe;
    }
  }
  return null;
}

async function launchBrowser(defaultViewport) {
  try {
    return await puppeteer.launch({ channel: 'chrome', headless: 'new', defaultViewport });
  } catch (err) {
    const executablePath = findDownloadedChrome();
    if (!executablePath) {
      console.error('找不到系統 Chrome，也找不到已下載的 Chrome。請執行: npx puppeteer browsers install chrome');
      throw err;
    }
    console.error('系統 Chrome 不可用，改用已下載的 Chrome:', executablePath);
    return await puppeteer.launch({ executablePath, headless: 'new', args: ['--no-sandbox'], defaultViewport });
  }
}

async function main() {
  const [, , dir, ...explicitFiles] = process.argv;
  if (!dir) {
    console.error('Usage: node screenshot.js <dir> [file1.html ...]');
    process.exit(1);
  }

  const files = explicitFiles.length
    ? explicitFiles
    : fs.readdirSync(dir).filter((f) => f.endsWith('.html'));

  if (files.length === 0) {
    console.error('No .html files found in', dir);
    process.exit(1);
  }

  const browser = await launchBrowser({ width: 1600, height: 1000, deviceScaleFactor: 2 });
  const page = await browser.newPage();

  for (const f of files) {
    const htmlPath = path.join(dir, f);
    const pngPath = htmlPath.replace(/\.html$/, '.png');
    await page.goto('file://' + htmlPath, { waitUntil: 'networkidle0' });
    await page.screenshot({ path: pngPath, fullPage: true });
    console.log('wrote', pngPath);
  }

  await browser.close();
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
