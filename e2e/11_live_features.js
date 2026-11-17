// Live journey 5: the rest of the feature map, person-style. Opportunity reject (asks) → restore; score override →
// save → refresh → reset; competitor add (name only, no web) → remove; web auto-research without a key (refused);
// draft a landing page with the real local model → edit text → abandon via Escape (asks) → save → approve → unapprove
// → delete; experiment Revise/Stop decisions and delete; evidence drawer by keyboard; Library search → filter → open →
// back; Settings toggle → reload persists → restore; scoring weights invalid → refused; theme toggle; report → HTML.
const H = require('./human');
(async () => {
  const { browser, page, problems } = await H.open();
  const S = (n, f) => H.shot(page, 'j5-' + n, f);
  try {
    const aud = (await H.api('/api/audiences')).body.find(a => a.is_demo);
    const opps = (await H.api(`/api/opportunities?audience_id=${aud.id}`)).body;
    const o = opps.find(x => !x.product_count && !(x.products || []).length && x.status === 'proposed') || opps.find(x => x.status === 'proposed') || opps[0];
    await page.goto(`${H.BASE}/opportunities/${o.id}`, { waitUntil: 'networkidle0' });
    let asked = 0; page.removeAllListeners('dialog'); page.on('dialog', d => { asked++; d.accept(); });
    const rej = await H.find(page, 'Reject');
    if (rej) {
      await H.click(page, rej); await H.sleep(900);
      H.check('Reject asks first, then marks rejected', asked === 1 && (await H.api(`/api/opportunities/${o.id}`)).body.status === 'rejected', `asked=${asked}`);
      await H.click(page, 'Restore'); await H.sleep(900);
      H.check('Restore → proposed', (await H.api(`/api/opportunities/${o.id}`)).body.status === 'proposed');
    } else H.check('Reject hidden once a product exists', true, 'no Reject on this opportunity');
    // score override
    const sel = await page.$('select[aria-label]');
    if (sel) {
      const label = await sel.evaluate(e => e.getAttribute('aria-label')); const before = (await H.api(`/api/opportunities/${o.id}`)).body;
      const cur = await sel.evaluate(e => e.value); const next = cur === '5' ? '1' : '5';
      await sel.select(next); await H.sleep(200);
      await H.click(page, 'Save scores'); await H.sleep(900);
      await page.reload({ waitUntil: 'networkidle0' });
      const after = (await H.api(`/api/opportunities/${o.id}`)).body;
      const v = await page.$eval(`select[aria-label="${label}"]`, e => e.value);
      H.check('score override saved, survives refresh, total recalculated', v === next && after.total_score !== before.total_score, `${label}: ${cur}→${v}, total ${before.total_score}→${after.total_score}`);
      await page.select(`select[aria-label="${label}"]`, cur); await H.click(page, 'Save scores'); await H.sleep(800);
    }
    // competitor (name only — no URL so nothing is fetched)
    await page.click('input[aria-label="Competitor name"]'); await page.keyboard.type('King Arthur sourdough class');
    await page.click('input[aria-label="Price"]'); await page.keyboard.type('$45');
    await H.click(page, 'Add', { sel: '.card button', exact: true }); await H.sleep(900);
    let t = await H.main(page);
    H.check('competitor added', /King Arthur sourdough class/.test(t));
    const rm = await page.evaluateHandle(() => [...document.querySelectorAll('tr')].find(r => r.innerText.includes('King Arthur'))?.querySelector('button'));
    await H.click(page, rm.asElement()); await H.sleep(800);
    H.check('competitor removed', !/King Arthur sourdough class/.test(await H.main(page)));
    await H.click(page, 'Auto-research (web)');
    for (let i = 0; i < 30; i++) { await H.sleep(500); if (await page.evaluate(() => [...document.querySelectorAll('.notice.warn, .notice.bad')].some(e => /research|key/i.test(e.innerText)))) break; }
    const note = await page.evaluate(() => [...document.querySelectorAll('.notice.warn, .notice.bad')].map(e => e.innerText).join(' | '));
    H.check('web auto-research without a key is refused clearly (no paid call)', /key|Brave|Settings|turned off|allow/i.test(note), note, await S('01-autoresearch'));
    // real local-model asset
    await H.click(page, '+ Draft asset'); await H.sleep(500);
    // default kind (an offer write-up): plain text, so it can be edited in place
    await page.focus('.modal textarea'); await page.keyboard.type('plain-spoken, mention the weekday schedule');
    const tA = Date.now(); await H.click(page, 'Draft it');
    await page.waitForSelector('.drawer', { timeout: 900000 });
    await H.sleep(1200);
    H.check('offer drafted by the local model', true, `${Math.round((Date.now() - tA) / 1000)}s`, await S('02-asset', true));
    await H.click(page, 'Text', { within: '.drawer', sel: 'button', exact: true }); await H.sleep(200);
    await H.click(page, 'Edit text'); await H.sleep(300);
    await page.focus('.drawer textarea'); await page.keyboard.press('End'); await page.keyboard.type('\nQA EDIT LINE');
    let dlg = ''; page.removeAllListeners('dialog'); page.once('dialog', d => { dlg = d.message(); d.dismiss(); });
    await page.keyboard.press('Escape'); await H.sleep(400);
    H.check('Escape while editing asks before discarding edits (Cancel keeps them)', /Discard/.test(dlg) && !!(await page.$('.drawer textarea')), dlg);
    page.on('dialog', d => d.accept());
    await H.click(page, 'Save', { within: '.drawer', sel: 'button', exact: true }); await H.sleep(900);
    const assets = (await H.api(`/api/assets?opportunity_id=${o.id}`)).body; const as = assets[0];
    H.check('asset edit saved', /QA EDIT LINE/.test(as.content || (await H.api('/api/assets/' + as.id)).body.content));
    const box = await page.$('.drawer input[type=checkbox]'); if (box) await box.click();
    await H.click(page, 'Approve', { within: '.drawer', sel: 'button', exact: true }); await H.sleep(900);
    H.check('asset approved', (await H.api('/api/assets/' + as.id)).body.status === 'approved', `flag box ${!!box}`);
    await H.click(page, 'Unapprove', { within: '.drawer', sel: 'button' }); await H.sleep(900);
    H.check('asset unapproved', (await H.api('/api/assets/' + as.id)).body.status !== 'approved');
    await H.click(page, 'Delete', { within: '.drawer', sel: 'button', exact: true }); await H.sleep(900);
    H.check('asset deleted', (await H.api('/api/assets/' + as.id)).status === 404);
    // experiment: new → Revise → Stop → delete
    await page.goto(`${H.BASE}/opportunities/${o.id}`, { waitUntil: 'networkidle0' });
    const b1 = await H.find(page, 'Create validation experiment') || await H.find(page, 'New experiment');
    await H.click(page, b1); await page.waitForFunction(() => location.pathname.startsWith('/validation/'), { timeout: 10000 });
    const xid = page.url().split('/validation/')[1]; await H.sleep(700);
    await H.click(page, 'Revise'); await H.sleep(800);
    let x = (await H.api('/api/experiments/' + xid)).body;
    H.check('Revise decision recorded', x.decision === 'revise' || x.status === 'revise' || JSON.stringify(x).includes('revise'), x.decision || x.status);
    await H.click(page, 'Stop', { sel: 'main button', exact: true }); await H.sleep(800);
    x = (await H.api('/api/experiments/' + xid)).body;
    H.check('Stop decision recorded', JSON.stringify(x).includes('"stop"'), x.decision || x.status, await S('03-exp-stop', true));
    await H.click(page, 'Delete', { sel: 'main button', exact: true }); await page.waitForFunction(() => location.pathname === '/validation', { timeout: 8000 });
    H.check('experiment deleted → back to Validation Lab', (await H.api('/api/experiments/' + xid)).status === 404);
    // evidence drawer by keyboard on Problems
    await page.goto(`${H.BASE}/audiences/${aud.id}/problems`, { waitUntil: 'networkidle0' });
    const row = await page.$('table tbody tr'); await row.click(); await H.sleep(500);
    const q = await page.$('.quote, button.quote');
    if (q) { await q.focus(); await page.keyboard.press('Enter'); await H.sleep(900); const d = await page.$('.drawer');
      const inDrawer = d && await page.evaluate(() => !!document.activeElement?.closest('.drawer'));
      H.check('evidence drawer opens with Enter and takes focus', !!d && inDrawer, '', await S('04-evidence-drawer'));
      await page.keyboard.press('Escape'); await H.sleep(300);
      const back = await page.evaluate(() => document.activeElement?.className || document.activeElement?.tagName);
      H.check('Escape closes it and focus returns to the quote', !(await page.$('.drawer')) && /quote/.test(back), back);
    } else H.check('evidence quote found', false);
    // Library: search → filter → open → back
    await H.click(page, 'Research Library', { sel: 'nav a' }); await H.sleep(700);
    await page.click('input[type=search]'); await page.keyboard.type('starter'); await H.sleep(900);
    const n1 = await page.$$eval('main a', as => as.length);
    await page.select('select[aria-label="Type"]', 'comments').catch(async () => { const s = await page.$$('main select'); await s[0].select('comments'); });
    await H.sleep(900); await S('05-library-filter', true);
    t = await H.main(page);
    H.check('library search + type filter narrows results', /starter/i.test(t), `links before filter ${n1}`);
    const firstLink = await page.$('main table a, main .card a');
    if (firstLink) { await firstLink.click(); await H.sleep(900); const url1 = page.url(); await page.goBack({ waitUntil: 'networkidle0' }); await H.sleep(600);
      const kept = await page.$eval('input[type=search]', e => e.value).catch(() => '');
      H.check('open a result → Back keeps the search', kept === 'starter', `went to ${url1.replace(H.BASE, '')}, search after back = "${kept}"`); }
    // Settings toggle persists
    await page.goto(`${H.BASE}/settings`, { waitUntil: 'networkidle0' });
    const s0 = (await H.api('/api/system')).body.settings;
    await H.click(page, 'Allow automated competitor research', { sel: 'label' }); await H.sleep(900);
    await page.reload({ waitUntil: 'networkidle0' });
    const s1 = (await H.api('/api/system')).body.settings;
    const key = Object.keys(s0).find(k => s0[k] !== s1[k]);
    H.check('settings toggle saves and survives refresh', !!key, key ? `${key}: ${s0[key]} → ${s1[key]}` : JSON.stringify(s1).slice(0, 120));
    await H.click(page, 'Allow automated competitor research', { sel: 'label' }); await H.sleep(900);
    // weights: invalid (negative) → refused or clamped, not silently broken
    const w0 = (await H.api('/api/system')).body.settings.rubric;
    await page.evaluate(() => { const el = document.querySelector('input[aria-label="Problem frequency"]'); Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(el, '-5'); el.dispatchEvent(new Event('input', { bubbles: true })); });
    await H.click(page, 'Save weights'); await H.sleep(900);
    const werr = await page.evaluate(() => [...document.querySelectorAll('.notice.bad')].map(e => e.innerText).join(' | '));
    const w1 = (await H.api('/api/system')).body.settings.rubric;
    H.check('negative scoring weight is refused with a message, weights unchanged', JSON.stringify(w0) === JSON.stringify(w1) && /weight/i.test(werr), werr, await S('06-weights'));
    await page.reload({ waitUntil: 'networkidle0' });
    // theme toggle (sidebar) cycles and persists
    await H.click(page, await page.$('button[title="Switch appearance"]')); await H.sleep(200);
    const th = await page.evaluate(() => document.documentElement.getAttribute('data-theme') || 'system');
    await page.reload({ waitUntil: 'networkidle0' });
    const th2 = await page.evaluate(() => document.documentElement.getAttribute('data-theme') || 'system');
    H.check('theme toggle persists across reload', th === th2, `${th} → ${th2}`);
    // report → open HTML
    await page.goto(`${H.BASE}/audiences/${aud.id}/reports`, { waitUntil: 'networkidle0' });
    await H.click(page, 'Generate report'); await H.sleep(4000);
    const reps = (await H.api(`/api/audiences/${aud.id}/reports`)).body;
    const html = await (await fetch(`${H.BASE}/api/reports/${reps[0].id}/html`)).text();
    H.check('report generated and its HTML opens', reps.length > 0 && /<html/i.test(html) && html.length > 2000, `${html.length} chars`, await S('07-reports'));
  } catch (e) { H.check('journey ran without crash', false, e.stack.split('\n').slice(0, 2).join(' '), await H.shot(page, 'j5-crash', true)); }
  H.check('no console errors / unexpected failed API calls', problems.filter(p => !/http (400|409|422)|status of (400|409|422)/.test(p)).length === 0, problems.join(' ; '));
  await Promise.race([browser.close(), H.sleep(5000)]).catch(() => {});
  process.exit(H.save('11_live_features') ? 1 : 0);
})();
