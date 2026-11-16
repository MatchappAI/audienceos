const puppeteer = require('puppeteer-core');
const BASE = process.env.BASE || 'http://127.0.0.1:8761';
if (/:8760\b/.test(BASE)) { console.error('Refusing to run against port 8760 (the live app with real data). Use a scratch server on 8761.'); process.exit(2); }
async function open(opts = {}) {
  const browser = await puppeteer.launch({ executablePath: process.env.CHROME || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    headless: 'new', args: ['--headless=new', '--no-first-run', '--no-default-browser-check', '--disable-gpu', `--window-size=${opts.w||1440},${opts.h||900}`],
    defaultViewport: { width: opts.w || 1440, height: opts.h || 900 }, userDataDir: require('fs').mkdtempSync(require('path').join(require('os').tmpdir(), 'aos-e2e-')) });
  const page = await browser.newPage();
  const problems = [];
  page.on('console', m => { if (m.type() === 'error') problems.push('console: ' + m.text()); });
  page.on('pageerror', e => problems.push('pageerror: ' + e.message));
  page.on('response', r => { if (r.url().includes('/api/') && r.status() >= 400) problems.push(`http ${r.status()} ${r.request().method()} ${r.url().replace(BASE,'')}`); });
  page.on('dialog', d => d.accept());
  return { browser, page, problems };
}
const sleep = ms => new Promise(r => setTimeout(r, ms));
async function clickText(page, text, sel = 'button, a') {
  const ok = await page.evaluate((text, sel) => {
    const els = [...document.querySelectorAll(sel)].filter(e => e.offsetParent !== null && e.textContent.trim().includes(text));
    const el = els.find(e => e.textContent.trim() === text) || els[0];
    if (!el) return false; el.click(); return true;
  }, text, sel);
  if (!ok) throw new Error('not found: ' + text);
}
async function text(page) { return page.evaluate(() => document.querySelector('main').innerText); }
async function api(path, opts = {}) {
  const r = await fetch(BASE + path, { ...opts, headers: { 'x-audienceos': '1', 'content-type': 'application/json', ...(opts.headers||{}) } });
  const t = await r.text(); try { return { status: r.status, body: JSON.parse(t) }; } catch { return { status: r.status, body: t }; }
}
module.exports = { open, sleep, clickText, text, api, BASE };
