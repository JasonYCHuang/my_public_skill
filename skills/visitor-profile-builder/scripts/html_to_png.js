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

function findDownloadedChrome() {
  const cacheDir = process.env.PUPPETEER_CACHE_DIR || path.join(os.homedir(), '.cache', 'puppeteer');
  const chromeDir = path.join(cacheDir, 'chrome');
  if (!fs.existsSync(chromeDir)) return null;

  const platformPrefix = { linux: 'linux-', darwin: 'mac-', win32: 'win64-' }[process.platform];
  const entries = fs.readdirSync(chromeDir).filter((e) => platformPrefix && e.startsWith(platformPrefix)).sort();
  if (entries.length === 0) return null;
  const latest = entries[entries.length - 1];

  const candidates = {
    linux: path.join(chromeDir, latest, 'chrome-linux64', 'chrome'),
    darwin: path.join(chromeDir, latest, 'chrome-mac-x64', 'Google Chrome for Testing.app', 'Contents', 'MacOS', 'Google Chrome for Testing'),
    win32: path.join(chromeDir, latest, 'chrome-win64', 'chrome.exe'),
  }[process.platform];

  return candidates && fs.existsSync(candidates) ? candidates : null;
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

  const browser = await launchBrowser({ width: 900, height: 1000, deviceScaleFactor: 2 });
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
