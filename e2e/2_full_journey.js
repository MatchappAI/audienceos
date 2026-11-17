const { open, sleep, clickText, text, api, BASE } = require('./lib');
const FX = require('path').join(__dirname, '..', 'fixtures', 'demo') + '/';
const log = (...a) => console.log('[' + new Date().toISOString().slice(11, 19) + ']', ...a);
const results = [];
const check = (name, ok, detail = '') => { results.push({ name, ok: !!ok, detail }); log(ok ? 'PASS' : 'FAIL', name, detail); };
async function waitText(page, re, ms = 30000) { const t0 = Date.now(); for (;;) { const t = await text(page); if (re.test(t)) return t; if (Date.now() - t0 > ms) throw new Error('timeout waiting ' + re); await sleep(500); } }
async function setInput(page, selector, value) { await page.$eval(selector, (el, v) => { const s = Object.getOwnPropertyDescriptor(el.__proto__, 'value').set; s.call(el, v); el.dispatchEvent(new Event('input', { bubbles: true })); el.dispatchEvent(new Event('change', { bubbles: true })); }, value); }
async function byLabel(page, label, value, idx = 0) {
  await page.evaluate((label, value, idx) => {
    const ls = [...document.querySelectorAll('label.field')].filter(l => l.querySelector('span')?.textContent.trim() === label);
    const el = ls[idx]?.querySelector('input,textarea,select'); if (!el) throw new Error('no field ' + label);
    const proto = el.tagName === 'SELECT' ? HTMLSelectElement.prototype : el.tagName === 'TEXTAREA' ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
    Object.getOwnPropertyDescriptor(proto, 'value').set.call(el, value); el.dispatchEvent(new Event('input', { bubbles: true })); el.dispatchEvent(new Event('change', { bubbles: true }));
  }, label, value, idx);
}
(async () => {
  const { browser, page, problems } = await open();
  const shot = n => page.screenshot({ path: `${__dirname}/shots/${n}.png`, fullPage: true });
  require('fs').mkdirSync(__dirname + '/shots', { recursive: true });
  try {
    const auds = (await api('/api/audiences')).body; const aud = auds.find(a => a.is_demo); const aid = aud.id;
    // 1. Problems + evidence drawer
    await page.goto(`${BASE}/audiences/${aid}/problems`, { waitUntil: 'networkidle0' });
    let t = await text(page); await shot('01-problems');
    const intel = (await api(`/api/audiences/${aid}/intelligence`)).body;
    check('analysis produced problems', (intel.clusters || []).length >= 2, `clusters=${(intel.clusters||[]).length}`);
    const row = await page.$('table tbody tr'); if (row) { await row.click(); await sleep(800); }
    const q = await page.$('.quote, button.quote, [data-evidence], .ev'); 
    if (q) { await q.click(); await sleep(1200); const d = await page.$('.drawer'); check('evidence drawer opens from a quote', !!d, d ? (await page.$eval('.drawer', e => e.innerText.slice(0, 160))).replace(/\n/g, ' | ') : ''); await shot('02-evidence'); await page.keyboard.press('Escape'); await sleep(300); check('Escape closes drawer', !(await page.$('.drawer'))); }
    else check('evidence drawer opens from a quote', false, 'no quote element found');
    // 2. Intelligence + signals
    for (const tab of ['signals', 'opportunities', 'overview']) { await page.goto(`${BASE}/audiences/${aid}/${tab}`, { waitUntil: 'networkidle0' }); await shot('03-' + tab); }
    await page.goto(`${BASE}/intelligence/${aid}`, { waitUntil: 'networkidle0' }); await shot('04-intel');
    check('intelligence page renders profile', /Audience|profile|Unknown/i.test(await text(page)));
    // 3. Opportunity → scenario → approve → experiment
    const opps = (await api(`/api/opportunities?audience_id=${aid}`)).body; check('opportunities proposed', opps.length >= 1, `n=${opps.length}: ` + opps.map(o => o.name).join(' / '));
    const opp = opps.find(o => o.status === 'proposed');
    await page.goto(`${BASE}/opportunities/${opp.id}`, { waitUntil: 'networkidle0' }); await shot('05-opp');
    await clickText(page, 'Recalculate').catch(() => {}); await sleep(800);
    await clickText(page, 'Approve for testing'); for (let i = 0; i < 40 && (await api(`/api/opportunities/${opp.id}`)).body.status !== 'approved'; i++) await sleep(250); await page.waitForFunction(() => ![...document.querySelectorAll('button')].some(b => b.disabled && /Create validation/.test(b.textContent)));
    check('opportunity approved', (await api(`/api/opportunities/${opp.id}`)).body.status === 'approved');
    await clickText(page, 'Create validation experiment'); await page.waitForFunction(() => location.pathname.startsWith('/validation/'), { timeout: 15000 });
    const xid = page.url().split('/validation/')[1]; log('experiment', xid); await sleep(800); await shot('06-exp');
    // criteria thresholds
    const thr = await page.$$('input[aria-label="Threshold"]'); check('default criteria present', thr.length === 2);
    await page.evaluate(() => { const ins = [...document.querySelectorAll('input[aria-label="Threshold"]')]; const vals = ['2', '10']; ins.forEach((el, i) => { Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(el, vals[i]); el.dispatchEvent(new Event('input', { bubbles: true })); }); });
    await clickText(page, 'Save design'); await sleep(1200);
    let x = (await api(`/api/experiments/${xid}`)).body; check('criteria saved', x.criteria.length === 2 && x.criteria.every(c => c.value !== ''), JSON.stringify(x.criteria));
    const fin = await page.$('input[type=file]');
    await fin.uploadFile(FX + 'experiment_results_demo.csv'); await sleep(2000);
    await (await page.$('input[type=file]')).uploadFile(FX + 'orders_demo.csv'); await sleep(2000);
    await (await page.$('input[type=file]')).uploadFile(FX + 'orders_demo.csv'); await sleep(2000);
    t = await text(page); check('re-import of orders skipped as duplicates', /skipped \d+ already imported/.test(t), (t.match(/Imported[^\n]*/) || [''])[0]);
    x = (await api(`/api/experiments/${xid}`)).body; check('experiment metrics', x.events.length >= 1 && x.orders.length >= 1, `events=${x.events.length} orders=${x.orders.length} purchases=${x.metrics.values.purchases} rec=${x.evaluation.recommendation}`);
    await shot('07-exp-results');
    await clickText(page, 'Go'); await sleep(1500);
    check('decision Go → opportunity validated', (await api(`/api/opportunities/${opp.id}`)).body.status === 'validated');
    // 4. Asset (landing page) from the opportunity
    await page.goto(`${BASE}/opportunities/${opp.id}`, { waitUntil: 'networkidle0' });
    await clickText(page, '+ Draft asset'); await sleep(600);
    await page.select('.modal select', 'landing_page');
    const tA = Date.now(); await clickText(page, 'Draft it');
    await page.waitForSelector('.drawer', { timeout: 900000 });
    check('landing page drafted', true, `${Math.round((Date.now() - tA) / 1000)} s`); await sleep(1000); await shot('08-asset');
    const box = await page.$('.drawer input[type=checkbox]'); if (box) await box.click();
    await clickText(page, 'Approve', '.drawer button'); await sleep(1200);
    const as = (await api(`/api/assets?opportunity_id=${opp.id}`)).body; check('asset approved', as[0].status === 'approved', `flags_box=${!!box}`);
    for (const f of ['md', 'html', 'docx']) { const r = await fetch(`${BASE}/api/assets/${as[0].id}/export?format=${f}`); const b = await r.arrayBuffer(); check(`asset export ${f}`, r.status === 200 && b.byteLength > 200, `${b.byteLength} B`); }
    const pv = await fetch(`${BASE}/api/assets/${as[0].id}/preview`); check('preview CSP strict', /default-src 'none'/.test(pv.headers.get('content-security-policy')));
    await page.keyboard.press('Escape'); await sleep(300);
    // 5. Product
    await page.goto(`${BASE}/opportunities/${opp.id}`, { waitUntil: 'networkidle0' });
    await clickText(page, 'Create product'); await page.waitForFunction(() => location.pathname.startsWith('/products/'), { timeout: 15000 });
    const pid = page.url().split('/products/')[1]; await sleep(800);
    await byLabel(page, 'Storefront', 'Gumroad'); await byLabel(page, 'Checkout link (https)', 'https://example.gumroad.com/l/starter');
    await byLabel(page, 'Price ($)', '39');
    await clickText(page, 'Save', '.card button'); await sleep(1200);
    await page.evaluate(() => [...document.querySelectorAll('label.check input[type=checkbox]')].forEach(c => { if (!c.checked) c.click(); }));
    await byLabel(page, 'Approved by', 'Audit Tester');
    await clickText(page, 'Approve for launch'); await sleep(1200);
    let p = (await api(`/api/products/${pid}`)).body; check('product approved', p.status === 'approved', p.status + ' ' + (await text(page)).match(/These marketing[^\n]*|Every launch[^\n]*/)?.[0]);
    await clickText(page, 'Mark as launched'); await sleep(1000);
    p = (await api(`/api/products/${pid}`)).body; check('product launched', p.status === 'launched');
    await (await page.$('input[type=file]')).uploadFile(FX + 'orders_demo.csv'); await sleep(2000);
    p = (await api(`/api/products/${pid}`)).body; check('product orders imported', p.pnl.orders >= 1, JSON.stringify({ orders: p.pnl.orders, net: p.pnl.net_sales, fees: p.pnl.fees, contrib: p.pnl.contribution }));
    await setInput(page, 'input[aria-label="Amount"]:not([type=date])', '12'); // first Amount is in Sales; cost form's later
    await page.evaluate(() => { const amts = [...document.querySelectorAll('input[aria-label="Amount"]')]; const el = amts[1]; Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(el, '12'); el.dispatchEvent(new Event('input', { bubbles: true })); const s = amts[0]; Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(s, ''); s.dispatchEvent(new Event('input', { bubbles: true })); });
    await page.evaluate(() => { const c = [...document.querySelectorAll('.card')].find(c => c.querySelector('h2')?.textContent === 'Costs'); c.querySelector('button.btn:not(.ghost)').click(); });
    await sleep(1200); p = (await api(`/api/products/${pid}`)).body; check('cost added', p.costs.length === 1 && p.costs[0].amount === 12);
    await shot('09-product');
    // 6. Creator: deal, payout, statements, portal
    const org = p.organization_id;
    await page.goto(`${BASE}/creators/${org}`, { waitUntil: 'networkidle0' });
    if (/Save deal/.test(await text(page))) { await clickText(page, 'Save deal'); await sleep(1200); }
    let st = (await api(`/api/creators/${org}/statement`)).body;
    const pnl = p.pnl; const base = pnl.net_sales - pnl.fees - pnl.shared_costs; const exp = Math.round(Math.max(0, base) * 70 + 1e-6) / 100; // half-up to the cent, as statements round
    check('70/30 on contribution', Math.abs(st.all_time_creator_share - exp) < 0.011, `base=${base.toFixed(2)} creator=${st.all_time_creator_share} expected=${exp} agency=${st.totals.agency_share}`);
    await setInput(page, 'input[aria-label="Amount"]', '10'); await clickText(page, 'Record payout'); await sleep(1200);
    st = (await api(`/api/creators/${org}/statement`)).body; check('payout reduces balance', Math.abs(st.balance_owed - (exp - 10)) < 0.011, `owed=${st.balance_owed}`);
    await shot('10-creator');
    const csv = await (await fetch(`${BASE}/api/creators/${org}/statement.csv`)).text(); check('statement CSV matches', csv.includes(`Balance owed to creator,${st.balance_owed.toFixed(2)}`), csv.split('\n').slice(-2).join(' | '));
    const pdf = await fetch(`${BASE}/api/creators/${org}/statement.pdf`); const pb = Buffer.from(await pdf.arrayBuffer()); check('statement PDF', pb.slice(0, 4).toString() === '%PDF', `${pb.length} B`);
    const portal = await fetch(`${BASE}/api/creators/${org}/portal`); const ph = await portal.text(); check('portal has no scripts + CSP', !/<script/i.test(ph) && /default-src 'none'/.test(portal.headers.get('content-security-policy')));
    // 7. Reports + library + backup
    await page.goto(`${BASE}/audiences/${aid}/reports`, { waitUntil: 'networkidle0' });
    await clickText(page, 'Generate report').catch(e => log('no generate btn', e.message)); await sleep(4000);
    const reps = (await api(`/api/audiences/${aid}/reports`)).body; check('report generated', reps.length >= 1, Object.keys(reps[0]?.files || {}).join(','));
    for (const k of Object.keys(reps[0]?.files || {})) { const r = await fetch(`${BASE}/api/reports/${reps[0].id}/${k}`); check('report file ' + k, r.status === 200); }
    await page.goto(`${BASE}/library`, { waitUntil: 'networkidle0' }); await shot('11-library');
    const lib = (await api('/api/library?q=starter')).body; check('library search', (lib.content || []).length + (lib.comments || []).length > 0);
  } catch (e) { log('ERROR', e.stack); await shot('zz-error'); results.push({ name: 'script', ok: false, detail: e.message }); }
  log('BROWSER PROBLEMS', JSON.stringify(problems));
  require('fs').writeFileSync(__dirname + '/j2_results.json', JSON.stringify({ results, problems }, null, 1));
  log(`SUMMARY ${results.filter(r => r.ok).length}/${results.length} pass`);
  await browser.close();
})();
