// Seeded random walk through the real UI in headless Chrome (never visible). Each step either uses a visible,
// enabled control on the current screen (real mouse click at its position, real typing) or a session action (back,
// forward, reload, second tab changing data, server restart, slow/offline network, AI engine down/up, Escape,
// keyboard Tab+Enter, rapid triple click, jump to a route). After every step: no page errors, no uncaught
// exceptions, no 5xx, no console errors other than the browser's own "Failed to load resource" line for a refused
// (4xx) call. Every few steps: the money on screen equals the API, and reloading changes nothing.
//
//   BASE=http://127.0.0.1:8771 CTRL=http://127.0.0.1:PORT node ui_walk.js --seed 3 --steps 300 --out out/ui_3.json
// (run it through `mbt.py ui`, which starts the scratch server, the stand-in engine and the control endpoint.)
const puppeteer = require(require('path').join(__dirname, '..', '..', 'e2e', 'node_modules', 'puppeteer-core'));
const fs = require('fs');
const path = require('path');
const os = require('os');

const BASE = process.env.BASE; const CTRL = process.env.CTRL;
if (!BASE || /:8760\b/.test(BASE)) { console.error('BASE must be a scratch server, never :8760'); process.exit(2); }
const arg = (k, d) => { const i = process.argv.indexOf('--' + k); return i > 0 ? process.argv[i + 1] : d; };
const SEED = +arg('seed', 1), STEPS = +arg('steps', 200), OUTF = arg('out', path.join(__dirname, 'out', `ui_${SEED}.json`));
function mulberry32(a) { return () => { a |= 0; a = a + 0x6D2B79F5 | 0; let t = Math.imul(a ^ a >>> 15, 1 | a); t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t; return ((t ^ t >>> 14) >>> 0) / 4294967296; }; }
const rnd = mulberry32(SEED);
const pick = xs => xs[Math.floor(rnd() * xs.length)];
const sleep = ms => new Promise(r => setTimeout(r, ms));
const api = async (p, o = {}) => { const r = await fetch(BASE + p, { ...o, headers: { 'x-audienceos': '1', 'content-type': 'application/json', ...(o.headers || {}) } }); const t = await r.text(); try { return { status: r.status, body: JSON.parse(t) }; } catch { return { status: r.status, body: t }; } };
const ctrl = async what => { try { await fetch(CTRL + '/' + what, { method: 'POST' }); } catch (e) { } };

const TEXT_VALUES = ['QA value', '12500', '12.5k', '', ' ', '0', '-5', '1e9', 'مرحبا ‮', '🍞🍞', "'; DROP TABLE x;--", '<img src=x onerror=alert(1)>', 'https://example.com/a', 'not a url', '2026-02-31', '2026-01-15', '29.99', '10.005', 'a'.repeat(5000), 'pay@example.com'];
const pattern = u => { const p = new URL(u).pathname; return p.replace(/\/(aud|org|pr|op|ex|ast|as|src)_[0-9a-f]+/g, '/:id').replace(/\/[a-z]+_[0-9a-f]{8,}/g, '/:id') || '/'; };
const norm = s => (s || '').replace(/\s+/g, ' ').replace(/\$?[\d,]+(\.\d+)?%?/g, '#').trim().slice(0, 50);

(async () => {
  const browser = await puppeteer.launch({ executablePath: process.env.CHROME || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    headless: 'new', args: ['--headless=new', '--no-first-run', '--no-default-browser-check', '--disable-gpu', '--window-size=1440,900'],
    defaultViewport: { width: 1440, height: 900 }, userDataDir: fs.mkdtempSync(path.join(os.tmpdir(), 'aos-ui-')) });
  const problems = [], seen = {}, used = {}, offeredFailed = {}, steps = [];
  const stats = { steps: 0, clicks: 0, typed: 0, selects: 0, session: {}, money_checks: 0, reload_checks: 0, confirms: { accepted: 0, dismissed: 0 } };
  let lastStep = null;
  async function wire(page, tag) {
    await page.setRequestInterception(true);
    page.on('request', r => { const u = r.url(); if (u.startsWith(BASE) || u.startsWith('data:') || u.startsWith('blob:') || u === 'about:blank') r.continue(); else r.abort(); });
    page.on('pageerror', e => problems.push({ step: stats.steps, kind: 'pageerror', msg: e.message, last: lastStep, tag }));
    page.on('console', m => { if (m.type() === 'error' && !/Failed to load resource: (the server responded with a status of 4|net::ERR_FAILED|net::ERR_INTERNET_DISCONNECTED|net::ERR_CONNECTION_REFUSED|net::ERR_BLOCKED)/.test(m.text())) problems.push({ step: stats.steps, kind: 'console', msg: m.text().slice(0, 300), last: lastStep, tag }); });
    page.on('response', r => { if (r.url().startsWith(BASE + '/api/') && r.status() >= 500) problems.push({ step: stats.steps, kind: '5xx', msg: `${r.status()} ${r.request().method()} ${r.url().replace(BASE, '')}`, last: lastStep, tag });
      if (r.url().startsWith(BASE + '/api/') && r.status() >= 400 && r.status() < 500 && r.request().method() !== 'GET' && lastStep && lastStep.kind === 'control') {
        const k = lastStep.key; offeredFailed[k] = (offeredFailed[k] || 0) + 1; } });
    page.on('dialog', async d => { if (d.type() === 'confirm' && rnd() < 0.35) { stats.confirms.dismissed++; await d.dismiss(); } else { stats.confirms.accepted++; await d.accept(); } });
    const cdp = await page.target().createCDPSession();
    await cdp.send('Browser.setDownloadBehavior', { behavior: 'deny' }).catch(() => {});
    return cdp;
  }
  let page = await browser.newPage();
  let cdp = await wire(page, 'main');
  await page.goto(BASE + '/', { waitUntil: 'networkidle2' });

  const controls = () => page.evaluate(() => {
    const vis = e => { const b = e.getBoundingClientRect(); const s = getComputedStyle(e); return b.width > 0 && b.height > 0 && s.visibility !== 'hidden' && s.display !== 'none'; };
    const name = e => ((e.getAttribute('aria-label') || e.innerText || e.value || e.placeholder || e.title || '') + '').replace(/\s+/g, ' ').trim().slice(0, 50);
    const out = [];
    const all = [...document.querySelectorAll('button, a[href], input, select, textarea, summary, [role=button], [role=tab], tr[tabindex], .dropzone')];
    all.forEach((e, i) => {
      if (!vis(e) || e.disabled || e.getAttribute('aria-disabled') === 'true') return;
      let lab = name(e);
      if (/INPUT|SELECT|TEXTAREA/.test(e.tagName)) { const l = e.closest('label'); lab = (l ? (l.querySelector('span')?.innerText || l.innerText) : '').replace(/\s+/g, ' ').trim().slice(0, 40) + ' [' + (e.type || e.tagName.toLowerCase()) + ']' + (lab && e.tagName !== 'INPUT' ? '' : ''); }
      const kind = e.tagName === 'A' ? 'link' : e.tagName.toLowerCase();
      if (e.type === 'file') return;
      const href = e.getAttribute('href') || '';
      const ext = kind === 'link' && /^https?:/.test(href) && !href.startsWith(location.origin);
      e.setAttribute('data-qa-idx', String(i));
      out.push({ idx: i, kind, type: e.type || '', label: lab, ext, inMain: !!e.closest('main'), inModal: !!e.closest('.modal, .drawer, [role=dialog]'), opts: e.tagName === 'SELECT' ? [...e.options].map(o => o.value) : null });
    });
    return out;
  });

  async function checkMoney() {
    const u = new URL(page.url()); const p = u.pathname;
    const statVal = async label => page.evaluate(l => { const s = [...document.querySelectorAll('.stat')].find(x => x.querySelector('.label')?.innerText.trim() === l); return s ? s.querySelector('.value').innerText.trim() : null; }, label);
    const fmt = v => v == null ? '—' : (v < 0 ? '-' : '') + '$' + Math.abs(v).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    let m;
    if ((m = p.match(/^\/creators\/(org_[0-9a-f]+)$/))) {
      const st = (await api(`/api/creators/${m[1]}/statement`)).body; const shown = await statVal('Balance owed to creator');
      if (shown != null && st && st.organization) { stats.money_checks++; if (shown !== fmt(st.balance_owed)) problems.push({ step: stats.steps, kind: 'money-screen-vs-api', msg: `creator balance shows ${shown}, API ${fmt(st.balance_owed)}`, last: lastStep }); }
    } else if ((m = p.match(/^\/products\/(pr_[0-9a-f]+)$/))) {
      const pr = (await api(`/api/products/${m[1]}`)).body; const shown = await statVal('Net sales');
      if (shown != null && pr && pr.pnl) { stats.money_checks++; if (shown !== fmt(pr.pnl.net_sales)) problems.push({ step: stats.steps, kind: 'money-screen-vs-api', msg: `product net sales shows ${shown}, API ${fmt(pr.pnl.net_sales)}`, last: lastStep }); }
    } else if (p === '/') {
      const d = (await api('/api/dashboard')).body; const shown = await statVal('Owed to creators');
      if (shown != null && d && d.stats) { stats.money_checks++; if (shown !== fmt(d.stats.creator_balance_owed)) problems.push({ step: stats.steps, kind: 'money-screen-vs-api', msg: `dashboard owed shows ${shown}, API ${fmt(d.stats.creator_balance_owed)}`, last: lastStep }); }
    }
  }
  async function reloadSame() {
    const active = (await api('/api/jobs?active=true')).body;
    if (Array.isArray(active) && active.length) return;
    if (await page.$('.modal, .drawer, [role=dialog]')) return;
    const grab = () => page.evaluate(() => (document.querySelector('main') || document.body).innerText.split('\n').filter(l => !/ago|running|Running|%|Waiting|Starting|seconds|just now|min\b/.test(l)).join('\n'));
    await sleep(400); const a = await grab();
    await page.reload({ waitUntil: 'networkidle2' }); await sleep(400); const b = await grab();
    stats.reload_checks++;
    if (a !== b) {
      const la = a.split('\n'), lb = b.split('\n'); const d = la.find((x, i) => x !== lb[i]);
      problems.push({ step: stats.steps, kind: 'reload-changed-screen', msg: `${pattern(page.url())}: first differing line: ${JSON.stringify(d)} vs ${JSON.stringify(lb[la.indexOf(d)])}`, last: lastStep, soft: true });
    }
  }
  const ROUTES = async () => {
    const a = (await api('/api/audiences')).body || []; const o = (await api('/api/opportunities')).body || []; const x = (await api('/api/experiments')).body || [];
    const pr = (await api('/api/products')).body || []; const cr = ((await api('/api/creators')).body || {}).creators || [];
    const r = ['/', '/audiences', '/audiences?new=1', '/intelligence', '/opportunities', '/validation', '/library', '/creators', '/settings', '/nope/404'];
    if (a.length) { const id = pick(a).id; r.push(...['', '/sources', '/problems', '/signals', '/opportunities', '/experiments', '/products', '/reports'].map(t => `/audiences/${id}${t}`), `/intelligence/${id}`); }
    if (o.length) r.push(`/opportunities/${pick(o).id}`); if (x.length) r.push(`/validation/${pick(x).id}`);
    if (pr.length) r.push(`/products/${pick(pr).id}`); if (cr.length) r.push(`/creators/${pick(cr).id}`);
    r.push('/products/pr_doesnotexist', '/creators/org_missing', '/validation/ex_missing');
    return r;
  };

  for (let i = 0; i < STEPS; i++) {
    stats.steps = i;
    const pat = pattern(page.url());
    let cs = [];
    try { cs = await controls(); } catch (e) { cs = []; }
    const modalOpen = cs.some(c => c.inModal);
    const pool = cs.filter(c => !c.ext && (!modalOpen || c.inModal));
    for (const c of pool) { const k = `${pat}|${c.kind}: ${norm(c.label)}`; seen[k] = (seen[k] || 0) + 1; }
    const r = rnd();
    try {
      if (r < 0.78 && pool.length) {
        // prefer controls not used yet on this screen
        const fresh = pool.filter(c => !used[`${pat}|${c.kind}: ${norm(c.label)}`]);
        const c = (fresh.length && rnd() < 0.7) ? pick(fresh) : pick(pool);
        const key = `${pat}|${c.kind}: ${norm(c.label)}`;
        lastStep = { i, kind: 'control', key, url: page.url() };
        used[key] = (used[key] || 0) + 1;
        const el = await page.$(`[data-qa-idx="${c.idx}"]`);
        if (!el) continue;
        await el.evaluate(e => e.scrollIntoView({ block: 'center', inline: 'center' }));
        if (c.kind === 'select') {
          const v = pick(c.opts.length ? c.opts : ['']); await el.select(v); stats.selects++;
        } else if ((c.kind === 'input' && !/checkbox|radio|submit|button/.test(c.type)) || c.kind === 'textarea') {
          await el.click({ clickCount: 3 }); await page.keyboard.down('Meta'); await page.keyboard.press('KeyA'); await page.keyboard.up('Meta'); await page.keyboard.press('Backspace');
          const v = c.type === 'number' ? pick(['0', '5', '29.99', '-1', '100', '1000000', '10.005']) : c.type === 'date' ? pick(['2026-01-15', '2026-02-28']) : pick(TEXT_VALUES);
          if (v) await page.keyboard.type(v.slice(0, 400), { delay: 0 });
          if (rnd() < 0.3) await page.keyboard.press('Enter');
          stats.typed++;
        } else {
          const box = await el.boundingBox();
          if (!box) continue;
          const x = box.x + box.width / 2, y = box.y + box.height / 2;
          await page.mouse.move(x, y, { steps: 2 });
          if (rnd() < 0.08) { lastStep.kind = 'control'; lastStep.rapid = true; await page.mouse.click(x, y); await page.mouse.click(x, y); await page.mouse.click(x, y); stats.session.rapid = (stats.session.rapid || 0) + 1; }
          else await page.mouse.click(x, y);
          stats.clicks++;
        }
      } else {
        const a = pick(['back', 'forward', 'reload', 'route', 'route', 'second_tab', 'escape', 'tab_enter', 'slow', 'offline', 'engine_down', 'engine_up', 'server_restart', 'reload_check', 'close_reopen']);
        lastStep = { i, kind: 'session', key: a, url: page.url() };
        stats.session[a] = (stats.session[a] || 0) + 1;
        if (a === 'back') await page.goBack({ waitUntil: 'networkidle2', timeout: 8000 }).catch(() => {});
        else if (a === 'forward') await page.goForward({ waitUntil: 'networkidle2', timeout: 8000 }).catch(() => {});
        else if (a === 'reload') await page.reload({ waitUntil: 'networkidle2' });
        else if (a === 'route') await page.goto(BASE + pick(await ROUTES()), { waitUntil: 'networkidle2' });
        else if (a === 'escape') await page.keyboard.press('Escape');
        else if (a === 'tab_enter') { for (let k = 0; k < 1 + Math.floor(rnd() * 6); k++) await page.keyboard.press('Tab'); await page.keyboard.press('Enter'); }
        else if (a === 'slow') { await cdp.send('Network.enable'); await cdp.send('Network.emulateNetworkConditions', { offline: false, latency: 1200, downloadThroughput: 50000, uploadThroughput: 50000 }); await page.reload({ waitUntil: 'networkidle2', timeout: 30000 }).catch(() => {}); await cdp.send('Network.emulateNetworkConditions', { offline: false, latency: 0, downloadThroughput: -1, uploadThroughput: -1 }); }
        else if (a === 'offline') { await cdp.send('Network.enable'); await cdp.send('Network.emulateNetworkConditions', { offline: true, latency: 0, downloadThroughput: -1, uploadThroughput: -1 }); const cs2 = await controls().catch(() => []); const b = cs2.find(c => c.kind === 'button' && c.inMain); if (b) { const el = await page.$(`[data-qa-idx="${b.idx}"]`); if (el) await el.click().catch(() => {}); } await sleep(800); await cdp.send('Network.emulateNetworkConditions', { offline: false, latency: 0, downloadThroughput: -1, uploadThroughput: -1 }); await page.reload({ waitUntil: 'networkidle2' }); }
        else if (a === 'engine_down') await ctrl('engine_down');
        else if (a === 'engine_up') await ctrl('engine_up');
        else if (a === 'server_restart') { await ctrl('restart'); await page.reload({ waitUntil: 'networkidle2' }).catch(() => {}); }
        else if (a === 'reload_check') await reloadSame();
        else if (a === 'close_reopen') { const u = page.url(); await page.close(); page = await browser.newPage(); cdp = await wire(page, 'main'); await page.goto(u, { waitUntil: 'networkidle2' }); }
        else if (a === 'second_tab') {
          const p2 = await browser.newPage(); await wire(p2, 'tab2');
          await p2.goto(BASE + pick(await ROUTES()), { waitUntil: 'networkidle2' });
          // change data behind the first tab's back
          const pr = (await api('/api/products')).body || []; const cr = ((await api('/api/creators')).body || {}).creators || [];
          if (pr.length && rnd() < .5) await api(`/api/products/${pick(pr).id}`, { method: 'PATCH', body: JSON.stringify({ notes: 'changed in another tab ' + i }) });
          else if (cr.length) { const c = pick(cr); await api(`/api/creators/${c.id}/payouts`, { method: 'POST', body: JSON.stringify({ date: '2026-02-01', amount: 1 }) }); }
          await p2.close();
        }
      }
      await page.waitForNetworkIdle({ idleTime: 250, timeout: 6000 }).catch(() => {});
      if (!page.url().startsWith(BASE)) await page.goto(BASE + '/', { waitUntil: 'networkidle2' });
      if (i % 4 === 3) await checkMoney();
      if (i % 25 === 24) await reloadSame();
      // keep the world populated: reseed when the walk deleted most things
      if (i % 30 === 29) { const a = (await api('/api/audiences')).body || []; if (a.length < 2) await ctrl('reseed'); }
    } catch (e) {
      if (!/Execution context was destroyed|detached|Target closed|Node is either not visible|not clickable|Navigating frame was detached|Session closed/.test(e.message)) problems.push({ step: i, kind: 'driver', msg: e.message.slice(0, 200), last: lastStep, soft: true });
      try { if (page.isClosed()) { page = await browser.newPage(); cdp = await wire(page, 'main'); } await page.goto(BASE + '/', { waitUntil: 'networkidle2' }); } catch (e2) { }
    }
    steps.push(lastStep);
  }
  // coverage vs the earlier inventory (qa/inventory.json): same labelling, ids/numbers normalised
  let inv = {}; try { inv = JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'inventory.json'))); } catch { }
  const invKeys = new Set();
  for (const [r, list] of Object.entries(inv)) { const pat = pattern(BASE + r.split('?')[0]); for (const c of list) { const m = c.match(/^([a-z.]+): (.*?)( \(NOT keyboard-focusable\))?( \(disabled\))?$/); if (m && !m[4]) invKeys.add(`${pat}|${m[1].replace('.dropzone', '')}: ${norm(m[2])}`); } }
  const usedKeys = new Set(Object.keys(used));
  const invHit = [...invKeys].filter(k => usedKeys.has(k) || [...usedKeys].some(u => u.split('|')[0] === k.split('|')[0] && u.split('|')[1].slice(0, 18) === k.split('|')[1].slice(0, 18)));
  const hard = problems.filter(p => !p.soft);
  const out = { seed: SEED, steps: STEPS, stats, problems, hard_problems: hard.length, soft_problems: problems.length - hard.length,
    controls_seen: Object.keys(seen).length, controls_used: usedKeys.size, screens_seen: [...new Set(Object.keys(seen).map(k => k.split('|')[0]))],
    inventory_total: invKeys.size, inventory_used: invHit.length, inventory_missing: [...invKeys].filter(k => !invHit.includes(k)).slice(0, 80),
    offered_but_refused: Object.entries(offeredFailed).sort((a, b) => b[1] - a[1]).slice(0, 40), used: Object.keys(used) };
  fs.mkdirSync(path.dirname(OUTF), { recursive: true });
  fs.writeFileSync(OUTF, JSON.stringify(out, null, 1));
  console.log(JSON.stringify({ seed: SEED, steps: STEPS, hard_problems: hard.length, soft: out.soft_problems, controls_seen: out.controls_seen, controls_used: out.controls_used, inventory: `${out.inventory_used}/${out.inventory_total}`, money_checks: stats.money_checks, reload_checks: stats.reload_checks }));
  for (const p of hard.slice(0, 15)) console.log('PROBLEM', JSON.stringify(p).slice(0, 400));
  await Promise.race([browser.close(), sleep(5000)]);
  process.exit(hard.length ? 1 : 0);
})();
