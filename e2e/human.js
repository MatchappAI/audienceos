// Helpers that drive the UI like a person: real mouse moves/clicks at the element's
// on-screen position, real key presses, scrolling into view. Never runs against :8760.
const { open, sleep, api, BASE } = require('./lib');
const fs = require('fs');
const path = require('path');
const SHOTS = process.env.SHOTS || path.join(__dirname, '..', 'qa', 'screenshots');
fs.mkdirSync(SHOTS, { recursive: true });

const results = [];
const log = (...a) => console.log('[' + new Date().toISOString().slice(11, 19) + ']', ...a);
function check(name, ok, detail = '', evidence = '') {
  results.push({ name, ok: !!ok, detail: String(detail).slice(0, 300), evidence });
  log(ok ? 'PASS' : 'FAIL', name, detail ? '— ' + String(detail).slice(0, 200) : '');
  return !!ok;
}

// Find a visible element whose own text (or aria-label/title) matches; returns an ElementHandle.
async function find(page, text, sel = 'button, a, [role=button], [role=tab], summary, label', { exact = false, within = null } = {}) {
  const h = await page.evaluateHandle((text, sel, exact, within) => {
    const root = within ? document.querySelector(within) : document;
    if (!root) return null;
    const vis = e => { const r = e.getBoundingClientRect(); const s = getComputedStyle(e); return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none'; };
    const norm = s => (s || '').replace(/\s+/g, ' ').trim();
    const els = [...root.querySelectorAll(sel)].filter(vis);
    const label = e => norm(e.innerText || e.textContent) || norm(e.getAttribute('aria-label')) || norm(e.getAttribute('title'));
    const isRe = typeof text === 'object';
    const m = e => { const l = label(e); return exact ? l === text : l.includes(text); };
    return els.find(e => label(e) === text) || els.find(m) || null;
  }, text, sel, exact, within);
  const el = h.asElement();
  return el;
}

async function click(page, text, opts = {}) {
  const el = typeof text === 'string' ? await find(page, text, opts.sel, opts) : text;
  if (!el) throw new Error('not found on screen: ' + text);
  await el.evaluate(e => e.scrollIntoView({ block: 'center', inline: 'center' }));
  await sleep(60);
  const box = await el.boundingBox();
  if (!box) throw new Error('no box: ' + text);
  const x = box.x + box.width / 2, y = box.y + box.height / 2;
  // What a person would actually hit at that point.
  const hit = await page.evaluate((x, y) => { const e = document.elementFromPoint(x, y); return e ? (e.closest('button,a,[role=button],label,summary,input,select,textarea') || e).outerHTML.slice(0, 120) : null; }, x, y);
  await page.mouse.move(x, y, { steps: 4 });
  await page.mouse.click(x, y);
  return { el, hit };
}

// Click a form field by its visible label then type into it (select-all first so it replaces).
async function fill(page, label, value, idx = 0) {
  const el = await page.evaluateHandle((label, idx) => {
    const norm = s => (s || '').replace(/\s+/g, ' ').trim();
    const ls = [...document.querySelectorAll('label')].filter(l => { const r = l.getBoundingClientRect(); return r.width > 0 && norm(l.querySelector('span')?.textContent || l.firstChild?.textContent).startsWith(label); });
    const l = ls[idx]; if (l) return l.querySelector('input,textarea,select') || (l.htmlFor && document.getElementById(l.htmlFor));
    return [...document.querySelectorAll('input,textarea,select')].find(e => (e.getAttribute('aria-label') || e.placeholder || '').startsWith(label)) || null;
  }, label, idx);
  const e = el.asElement(); if (!e) throw new Error('no field ' + label);
  const tag = await e.evaluate(x => x.tagName);
  await e.evaluate(x => x.scrollIntoView({ block: 'center' }));
  if (tag === 'SELECT') { await e.select(String(value)); return e; }
  await e.click({ clickCount: 3 });
  await page.keyboard.down('Meta'); await page.keyboard.press('KeyA'); await page.keyboard.up('Meta');
  await page.keyboard.press('Backspace');
  if (value !== '') await page.keyboard.type(String(value), { delay: 8 });
  return e;
}

async function main(page) { return page.evaluate(() => (document.querySelector('main') || document.body).innerText); }
async function waitText(page, re, ms = 30000) {
  const t0 = Date.now();
  for (;;) { const t = await main(page); if (re.test(t)) return t; if (Date.now() - t0 > ms) throw new Error('timeout waiting for ' + re + ' — saw: ' + t.slice(0, 300).replace(/\n/g, ' | ')); await sleep(400); }
}
async function shot(page, name, full = false) {
  const p = path.join(SHOTS, name + '.png');
  if (full) {
    // The app scrolls inside <main>, so a "full page" shot needs a viewport as tall as main's content.
    const vp = page.viewport();
    const hgt = await page.evaluate(() => { const m = document.querySelector('main'); return Math.max(document.documentElement.scrollHeight, m ? m.scrollHeight + m.getBoundingClientRect().top : 0); });
    await page.setViewport({ ...vp, height: Math.min(Math.max(vp.height, Math.ceil(hgt)), 6000) });
    await sleep(150);
    await page.screenshot({ path: p });
    await page.setViewport(vp);
  } else await page.screenshot({ path: p });
  return path.relative(path.join(__dirname, '..'), p);
}
// Layout problems a person would notice: horizontal scroll, text overflowing its box, overlapping controls.
async function layoutIssues(page) {
  return page.evaluate(() => {
    const out = [];
    const W = document.documentElement.clientWidth;
    if (document.documentElement.scrollWidth > W + 1) out.push(`page scrolls sideways (${document.documentElement.scrollWidth} > ${W})`);
    const scrollsX = el => { for (let a = el.parentElement; a && a !== document.body; a = a.parentElement) { const ox = getComputedStyle(a).overflowX; if ((ox === 'auto' || ox === 'scroll') && a.tagName !== 'MAIN') return true; } return false; };
    for (const e of document.querySelectorAll('button, .btn, .badge, .pill, h1, h2, h3, th, td, dd, .card, p')) {
      const r = e.getBoundingClientRect(); if (!r.width) continue;
      const card = e.parentElement && e.parentElement.closest('.card, .modal, .drawer');
      const limit = card ? card.getBoundingClientRect().right : W;
      if (r.left < limit - 2 && r.right > limit + 1 && !scrollsX(e)) out.push(`cut off: ${e.tagName}.${e.className} "${(e.innerText||'').slice(0,40)}"`);
      if (e.matches('button,.btn') && e.scrollWidth > e.clientWidth + 2 && getComputedStyle(e).overflow !== 'visible') out.push(`clipped button "${(e.innerText||'').slice(0,40)}"`);
    }
    return [...new Set(out)].slice(0, 15);
  });
}
function save(name) {
  const p = path.join(__dirname, name + '_results.json');
  fs.writeFileSync(p, JSON.stringify(results, null, 1));
  const pass = results.filter(r => r.ok).length;
  log(`${pass}/${results.length} passed → ${path.relative(path.join(__dirname, '..'), p)}`);
  return results.length - pass;
}
module.exports = { open, sleep, api, BASE, find, click, fill, main, waitText, shot, layoutIssues, check, save, log, results };
