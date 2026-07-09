#!/usr/bin/env node
/**
 * Convert a generated profile HTML file (or every *.html in a directory) to
 * a full-page PNG screenshot, matching the profile card's own width so the
 * PNG isn't mostly empty page-background margin.
 *
 * Requires puppeteer-core (npm install in this scripts/ dir, once) and a
 * system-installed Chrome/Chromium -- it does NOT download its own browser,
 * it drives whatever Chrome is already on the machine.
 *
 * Usage:
 *   node html_to_png.js <file.html>              -- one file -> file.png next to it
 *   node html_to_png.js <dir>                     -- every *.html in dir -> matching .png
 *   node html_to_png.js <dir> file1.html file2.html   -- just those files in dir
 */
const fs = require('fs');
const path = require('path');
const puppeteer = require('puppeteer-core');

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

  const browser = await puppeteer.launch({
    channel: 'chrome', // auto-detects the system Chrome install, cross-platform
    headless: 'new',
    defaultViewport: { width: 900, height: 1000, deviceScaleFactor: 2 },
  });
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
