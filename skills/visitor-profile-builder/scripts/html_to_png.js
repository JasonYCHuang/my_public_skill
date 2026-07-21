#!/usr/bin/env node
/**
 * Convert a generated profile HTML file (or every *.html in a directory) to
 * a full-page PNG screenshot, matching the profile card's own width so the
 * PNG isn't mostly empty page-background margin.
 *
 * Requires puppeteer-core (npm install in this scripts/ dir, once). Prefers
 * a system-installed Chrome/Chromium; if that's not present (e.g. a
 * container/CI Linux box with no root), falls back to a Chrome downloaded
 * via `npx puppeteer browsers install chrome` under ~/.cache/puppeteer.
 *
 * Usage:
 *   node html_to_png.js <file.html>              -- one file -> file.png next to it
 *   node html_to_png.js <dir>                     -- every *.html in dir -> matching .png
 *   node html_to_png.js <dir> file1.html file2.html   -- just those files in dir
 */
const fs = require('fs');
const os = require('os');
const path = require('path');
const puppeteer = require('puppeteer-core');

// Puppeteer names its cache entries <platform>-<version>, where <platform> is
// its own BrowserPlatform enum, not process.platform: arm64 gets a separate
// tag with an UNDERSCORE ("mac_arm", "linux_arm"), x64 does not. Keying off
// process.platform alone silently misses every arm64 machine — and note
// "linux_arm-145..." does not start with "linux-", so an arm64 Linux box
// (Graviton, Ampere) needs its own entry rather than sharing the x64 one.
const CHROME_CACHE_PREFIX = {
  'darwin-arm64': 'mac_arm-',
  'darwin-x64': 'mac-',
  'linux-x64': 'linux-',
  'linux-arm64': 'linux_arm-',
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

// Linux-only launch flags. Both are about headless servers, so they stay off
// macOS (where Chrome's sandbox works fine and should keep working):
//   --no-sandbox            Chrome refuses to start as root, which is the
//                           normal case in a container or a bare cloud VM.
//                           We only ever load file:// HTML this repo just
//                           generated, so there is no untrusted content for
//                           the sandbox to contain.
//   --disable-dev-shm-usage Docker defaults /dev/shm to 64MB; Chrome writes
//                           screenshots through it and crashes part-way on a
//                           long card. Sends it to /tmp instead.
const LINUX_ARGS = process.platform === 'linux'
  ? ['--no-sandbox', '--disable-dev-shm-usage']
  : [];

async function launchBrowser(defaultViewport) {
  try {
    // LINUX_ARGS applies here too, not just in the fallback: a cloud box with
    // apt-installed Chrome takes this branch, and without --no-sandbox it
    // died as root even though a perfectly good Chrome was present.
    return await puppeteer.launch({ channel: 'chrome', headless: 'new', args: LINUX_ARGS, defaultViewport });
  } catch (err) {
    const executablePath = findDownloadedChrome();
    if (!executablePath) {
      console.error('找不到系統 Chrome，也找不到已下載的 Chrome。請執行: npx puppeteer browsers install chrome');
      throw err;
    }
    console.error('系統 Chrome 不可用，改用已下載的 Chrome:', executablePath);
    return await puppeteer.launch({ executablePath, headless: 'new', args: ['--no-sandbox', ...LINUX_ARGS], defaultViewport });
  }
}

async function main() {
  const [, , target, ...explicitFiles] = process.argv;
  if (!target) {
    console.error('Usage: node html_to_png.js <file.html | dir> [file1.html ...]');
    process.exit(1);
  }

  const isDir = fs.existsSync(target) && fs.statSync(target).isDirectory();
  const dir = isDir ? target : path.dirname(target);
  const files = isDir
    ? (explicitFiles.length ? explicitFiles : fs.readdirSync(dir).filter((f) => f.endsWith('.html')))
    : [path.basename(target)];

  if (files.length === 0) {
    console.error('No .html files found in', dir);
    process.exit(1);
  }

  // Phone-shaped on purpose. These PNGs are read on a phone, in a chat app,
  // where the image is scaled to the screen width — so rendering at roughly
  // a phone's own CSS width is what makes the text land at natural reading
  // size instead of pinch-zoom size. 3x keeps it sharp on a retina screen.
  //
  // Height is deliberately short: a fullPage screenshot is never smaller
  // than the viewport, so a tall one pads short cards with dead background.
  // fullPage still grows to fit the whole card.
  const browser = await launchBrowser({ width: 430, height: 400, deviceScaleFactor: 3 });
  const page = await browser.newPage();

  for (const f of files) {
    const htmlPath = path.join(dir, f);
    const pngPath = htmlPath.replace(/\.html$/, '.png');
    await page.goto('file://' + path.resolve(htmlPath), { waitUntil: 'networkidle0' });
    await page.screenshot({ path: pngPath, fullPage: true });
    console.log('wrote', pngPath);
  }

  await browser.close();
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
