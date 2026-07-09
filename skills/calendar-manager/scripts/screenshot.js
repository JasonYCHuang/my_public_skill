#!/usr/bin/env node
/**
 * Convert generated calendar HTML files to full-page PNG screenshots.
 *
 * Requires puppeteer-core (npm install puppeteer-core in this scripts/ dir,
 * once) and a system-installed Chrome/Chromium -- it does NOT download its
 * own browser, it drives whatever Chrome is already on the machine.
 *
 * Usage:
 *   node screenshot.js <dir-with-html-files> [file1.html file2.html ...]
 *
 * If no filenames are given, every *.html file in the directory is shot.
 * Each output PNG is written next to its source HTML with the same name.
 */
const fs = require('fs');
const path = require('path');
const puppeteer = require('puppeteer-core');

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

  const browser = await puppeteer.launch({
    channel: 'chrome', // auto-detects the system Chrome install, cross-platform
    headless: 'new',
    defaultViewport: { width: 1600, height: 1000, deviceScaleFactor: 2 },
  });
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
