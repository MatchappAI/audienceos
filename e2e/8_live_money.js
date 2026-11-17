// Live journey 3 (person-style, typed): opportunity → approve → experiment → Go → product (typed setup) → approve →
// launch → orders typed by hand + CSV → cost → deal (typed) → abandoned edit → payout (rapid double-click on a slow
// network) → statement / CSV / portal agree → two windows editing the same deal and product → retire → reopen.
const H = require('./human');
const path = require('path');
const FX = path.join(__dirname, '..', 'fixtures', 'demo');
const money = s => Number(String(s).replace(/[^0-9.-]/g, ''));
(async () => {
  const { browser, page, problems } = await H.open();
  const S = (n, f) => H.shot(page, 'j3-' + n, f);
  try {
    const aud = (await H.api('/api/audiences')).body.find(a => a.is_demo);
    const opps = (await H.api(`/api/opportunities?audience_id=${aud.id}`)).body;
    H.check('analysis left opportunities to work with', opps.length > 0, opps.map(o => o.name).join(' / '));
    const opp = opps.find(o => o.status === 'proposed') || opps[0];
    // via navigation, like a person: sidebar → Product Opportunities → click the card/link
    await page.goto(H.BASE + '/', { waitUntil: 'networkidle0' });
    await H.click(page, 'Product Opportunities', { sel: 'nav a' }); await H.sleep(700);
    await H.click(page, opp.name, { sel: 'main a' }); await page.waitForFunction(() => location.pathname.startsWith('/opportunities/'));
    await H.sleep(600); await S('01-opportunity', true);
    await H.click(page, 'Approve for testing'); await H.sleep(1200);
    await H.click(page, 'Create validation experiment'); await page.waitForFunction(() => location.pathname.startsWith('/validation/'), { timeout: 15000 });
    const xid = page.url().split('/validation/')[1]; await H.sleep(800);
    // thresholds typed
    const thr = await page.$$('input[aria-label="Threshold"]');
    for (const [i, v] of [[0, '2'], [1, '10']]) { if (thr[i]) { await thr[i].click({ clickCount: 3 }); await page.keyboard.type(v); } }
    await H.click(page, 'Save design'); await H.sleep(1000);
    await (await page.$('input[type=file]')).uploadFile(path.join(FX, 'experiment_results_demo.csv')); await H.sleep(1800);
    await (await page.$('input[type=file]')).uploadFile(path.join(FX, 'orders_demo.csv')); await H.sleep(1800);
    await S('02-experiment', true);
    await H.click(page, 'Go'); await H.sleep(1500);
    H.check('Go decision → opportunity validated', (await H.api(`/api/opportunities/${opp.id}`)).body.status === 'validated');
    // product
    await page.goto(`${H.BASE}/opportunities/${opp.id}`, { waitUntil: 'networkidle0' });
    await H.click(page, 'Create product'); await page.waitForFunction(() => location.pathname.startsWith('/products/'), { timeout: 15000 });
    const pid = page.url().split('/products/')[1]; await H.sleep(700);
    await H.fill(page, 'Price ($)', '39'); await H.fill(page, 'Storefront', 'Gumroad');
    await H.fill(page, 'Checkout link (https)', 'http://not-secure.example');
    await H.click(page, 'Save', { sel: '.card button', exact: true }); await H.sleep(800);
    let t = await H.main(page);
    H.check('http checkout link refused with a message', /https/.test(t) && (await H.api(`/api/products/${pid}`)).body.checkout_url == null, (t.match(/[^\n]*https:\/\/[^\n]*/) || [''])[0]);
    await H.fill(page, 'Checkout link (https)', 'https://example.gumroad.com/l/starter');
    await H.click(page, 'Save', { sel: '.card button', exact: true }); await H.sleep(900);
    let p = (await H.api(`/api/products/${pid}`)).body;
    H.check('product setup saved (price, storefront, link)', p.price === 39 && p.storefront === 'Gumroad' && /^https/.test(p.checkout_url), `${p.price} ${p.storefront} ${p.checkout_url}`);
    // approval checklist — tick each box with the mouse
    for (const cb of await page.$$('label.check input[type=checkbox]')) { if (!(await cb.evaluate(e => e.checked))) { await cb.evaluate(e => e.scrollIntoView({ block: 'center' })); await cb.click(); } }
    await H.fill(page, 'Approved by', 'Live QA');
    await H.click(page, 'Approve for launch'); await H.sleep(1000);
    await H.click(page, 'Mark as launched'); await H.sleep(1000);
    p = (await H.api(`/api/products/${pid}`)).body;
    H.check('product approved then launched through the UI', p.status === 'launched', p.status, await S('03-launched', true));
    // orders typed by hand
    const typeOrder = async (ref, amt, fee) => {
      await page.click('input[aria-label="Order ID"]', { clickCount: 3 }); await page.keyboard.type(ref);
      await page.click('input[aria-label="Amount"]', { clickCount: 3 }); await page.keyboard.type(amt);
      await page.click('input[aria-label="Fee"]', { clickCount: 3 }); await page.keyboard.type(fee);
    };
    await typeOrder('HAND-1', '39', '2.10');
    await H.click(page, 'Add', { sel: '.card button', exact: true }); await H.sleep(900);
    // refund larger than the sale must be refused
    await typeOrder('HAND-2', '39', '2.10'); await page.click('input[aria-label="Refunded"]'); await page.keyboard.type('50');
    await H.click(page, 'Add', { sel: '.card button', exact: true }); await H.sleep(900);
    t = await H.main(page);
    p = (await H.api(`/api/products/${pid}`)).body;
    const err = await page.evaluate(() => [...document.querySelectorAll('.notice.bad')].map(e => e.innerText).join(' | '));
    H.check('refund bigger than the sale is refused, with a message', !p.sales.some(s => s.order_ref === 'HAND-2') && /refund/i.test(err), err, await S('03b-refund-error'));
    await page.click('input[aria-label="Refunded"]', { clickCount: 3 }); await page.keyboard.press('Backspace');
    // rapid double-click Add on a slow network: one order
    const cdp = await page.target().createCDPSession();
    await cdp.send('Network.enable'); await cdp.send('Network.emulateNetworkConditions', { offline: false, latency: 1500, downloadThroughput: 50000, uploadThroughput: 50000 });
    const addBtn = await H.find(page, 'Add', '.card button', { exact: true });
    const b = await addBtn.boundingBox();
    await page.mouse.click(b.x + b.width / 2, b.y + b.height / 2, { clickCount: 1 }); await page.mouse.click(b.x + b.width / 2, b.y + b.height / 2, { clickCount: 1 }); await page.mouse.click(b.x + b.width / 2, b.y + b.height / 2);
    await H.sleep(300);
    const busyShot = await S('04-slow-network-adding');
    await H.sleep(5000);
    await cdp.send('Network.emulateNetworkConditions', { offline: false, latency: 0, downloadThroughput: -1, uploadThroughput: -1 });
    p = (await H.api(`/api/products/${pid}`)).body;
    H.check('triple-click Add on a slow network records the order once', p.sales.filter(s => s.order_ref === 'HAND-2').length === 1, `HAND-2 rows: ${p.sales.filter(s => s.order_ref === 'HAND-2').length}`, busyShot);
    // CSV import (via the button's chooser)
    const [ch] = await Promise.all([page.waitForFileChooser({ timeout: 4000 }), H.click(page, 'Import orders CSV')]);
    await ch.accept([path.join(FX, 'orders_demo.csv')]); await H.sleep(1500);
    t = await H.main(page);
    H.check('orders CSV import reports what it did', /Imported \d+ orders/.test(t), (t.match(/Imported[^\n]*/) || [''])[0]);
    // cost
    const costCard = await page.evaluateHandle(() => [...document.querySelectorAll('.card')].find(c => c.querySelector('h2')?.textContent === 'Costs'));
    const camt = await costCard.asElement().$('input[aria-label="Amount"]'); await camt.click(); await page.keyboard.type('12');
    await H.click(page, (await costCard.asElement().$('button.btn:not(.ghost)'))); await H.sleep(900);
    p = (await H.api(`/api/products/${pid}`)).body;
    H.check('cost added', p.costs.length === 1 && p.costs[0].amount === 12);
    // delete an order: dismiss first (kept), then accept (gone)
    page.removeAllListeners('dialog'); page.once('dialog', d => d.dismiss());
    await H.click(page, await page.$('button[aria-label="Delete order HAND-1"]')); await H.sleep(600);
    const kept = (await H.api(`/api/products/${pid}`)).body.sales.some(s => s.order_ref === 'HAND-1');
    page.once('dialog', d => d.accept());
    await H.click(page, await page.$('button[aria-label="Delete order HAND-1"]')); await H.sleep(900);
    p = (await H.api(`/api/products/${pid}`)).body;
    H.check('delete order: Cancel keeps it, OK removes it', kept && !p.sales.some(s => s.order_ref === 'HAND-1'));
    page.on('dialog', d => d.accept());
    await S('05-product-money', true);
    // creator page via crumb link
    await H.click(page, p.org_name, { sel: '.crumbs a' }); await page.waitForFunction(() => location.pathname.startsWith('/creators/'));
    const org = p.organization_id; await H.sleep(800);
    if (await H.find(page, 'Change terms')) await H.click(page, 'Change terms');   // re-run: a deal already exists
    await H.fill(page, 'Creator share (%)', '70');
    await H.click(page, 'Save deal'); await H.sleep(1000);
    let st = (await H.api(`/api/creators/${org}/statement`)).body;
    p = (await H.api(`/api/products/${pid}`)).body;
    // each product line: 70% of its own split base, floored at $0 (no loss carry-forward), rounded to the cent
    const exp = Math.round(st.lines.reduce((a, l) => a + Math.round(Math.max(0, l.split_base) * 70 + 1e-6) / 100, 0) * 100) / 100;
    const base = st.lines.reduce((a, l) => a + l.split_base, 0);
    H.check('70% of contribution computed', Math.abs(st.all_time_creator_share - exp) < 0.011, `base ${base.toFixed(2)} → creator ${st.all_time_creator_share} (expected ${exp})`);
    // abandoned edit must not leak into a later save
    await H.click(page, 'Change terms'); await H.fill(page, 'Creator share (%)', '60'); await H.click(page, 'Cancel', { within: 'main', sel: '.card button' }); await H.sleep(200);
    await H.click(page, 'Change terms');
    const reopened = await page.evaluate(() => [...document.querySelectorAll('label.field')].find(l => l.innerText.startsWith('Creator share')).querySelector('input').value);
    await H.fill(page, 'Notes', 'signed 2026-11-16'); await H.click(page, 'Save deal'); await H.sleep(1000);
    st = (await H.api(`/api/creators/${org}/statement`)).body;
    H.check('Cancel discards an abandoned 60% edit; a later notes-only save keeps 70%', reopened === '70' && st.deal.creator_share_pct === 70 && st.deal.notes === 'signed 2026-11-16', `reopened ${reopened}, saved ${st.deal.creator_share_pct}%`, await S('06-deal'));
    // two windows on the same deal
    const B = await browser.newPage(); await B.setViewport({ width: 1440, height: 900 }); B.on('dialog', d => d.accept());
    await B.goto(`${H.BASE}/creators/${org}`, { waitUntil: 'networkidle0' });
    await H.click(page, 'Change terms');                 // window A opens the editor (on 70%)
    await B.bringToFront(); await H.click(B, 'Change terms'); await H.fill(B, 'Creator share (%)', '65'); await H.click(B, 'Save deal'); await H.sleep(900);   // window B saves 65%
    await page.bringToFront(); await H.fill(page, 'Notes', 'edited in window A'); await H.click(page, 'Save deal'); await H.sleep(900);
    st = (await H.api(`/api/creators/${org}/statement`)).body;
    t = await H.main(page);
    H.check('stale window cannot overwrite newer deal terms; it says to reload', st.deal.creator_share_pct === 65 && /another window/.test(t), `saved ${st.deal.creator_share_pct}% · ${(t.match(/[^\n]*another window[^\n]*/) || ['no message'])[0]}`, await S('07-deal-conflict'));
    await page.reload({ waitUntil: 'networkidle0' });
    await H.click(page, 'Change terms'); await H.fill(page, 'Creator share (%)', '70'); await H.click(page, 'Save deal'); await H.sleep(900);
    st = (await H.api(`/api/creators/${org}/statement`)).body;
    H.check('after reload the change goes through', st.deal.creator_share_pct === 70);
    // payout: rapid double click on a slow network → one payout
    const owed0 = st.balance_owed; const pay0 = st.payouts.length;
    await page.click('input[aria-label="Amount"]'); await page.keyboard.type('10');
    await page.click('input[aria-label="Reference"]'); await page.keyboard.type('WISE-123');
    await cdp.detach().catch(() => {});
    const cdp2 = await page.target().createCDPSession(); await cdp2.send('Network.enable');
    await cdp2.send('Network.emulateNetworkConditions', { offline: false, latency: 1500, downloadThroughput: 50000, uploadThroughput: 50000 });
    const pb = await (await H.find(page, 'Record payout')).boundingBox();
    for (let i = 0; i < 3; i++) await page.mouse.click(pb.x + pb.width / 2, pb.y + pb.height / 2);
    await H.sleep(5500);
    await cdp2.send('Network.emulateNetworkConditions', { offline: false, latency: 0, downloadThroughput: -1, uploadThroughput: -1 });
    st = (await H.api(`/api/creators/${org}/statement`)).body;
    H.check('triple-click Record payout on a slow network records it once', st.payouts.length === pay0 + 1 && Math.abs(st.balance_owed - (owed0 - 10)) < 0.011, `payouts=${st.payouts.length} owed ${owed0} → ${st.balance_owed}`);
    await page.reload({ waitUntil: 'networkidle0' }); t = await H.main(page);
    const owedOnScreen = money((t.match(/Balance owed to creator\n([^\n]+)/) || [])[1]);
    const csv = await (await fetch(`${H.BASE}/api/creators/${org}/statement.csv`)).text();
    const portal = await (await fetch(`${H.BASE}/api/creators/${org}/portal`)).text();
    H.check('screen, CSV and creator view agree on the balance', Math.abs(owedOnScreen - st.balance_owed) < 0.006 && csv.includes(st.balance_owed.toFixed(2)) && portal.includes(st.balance_owed.toFixed(2)), `screen ${owedOnScreen} api ${st.balance_owed}`, await S('08-creator', true));
    // two windows on the same product: B changes price, A (stale) edits notes → price must survive
    await page.goto(`${H.BASE}/products/${pid}`, { waitUntil: 'networkidle0' });
    await B.goto(`${H.BASE}/products/${pid}`, { waitUntil: 'networkidle0' });
    await B.bringToFront(); await H.fill(B, 'Price ($)', '45'); await H.click(B, 'Save', { sel: '.card button', exact: true }); await H.sleep(900);
    await page.bringToFront(); await H.fill(page, 'Notes', 'A notes edit'); await H.click(page, 'Save', { sel: '.card button', exact: true }); await H.sleep(900);
    p = (await H.api(`/api/products/${pid}`)).body;
    H.check('stale product window saving notes does not revert the newer price', p.price === 45 && p.notes === 'A notes edit', `price ${p.price} notes "${p.notes}"`);
    H.check('price change sent the launched product back for approval', p.status === 'draft' && !!p.reapproval, p.status);
    // blank product name refused
    await page.reload({ waitUntil: 'networkidle0' });
    await H.fill(page, 'Name', ''); await H.click(page, 'Save', { sel: '.card button', exact: true }); await H.sleep(800);
    p = (await H.api(`/api/products/${pid}`)).body; t = await H.main(page);
    const nameErr = await page.evaluate(() => [...document.querySelectorAll('.notice.bad')].map(e => e.innerText).join(' | '));
    H.check('blank product name is refused with a message', p.name.trim() !== '' && /blank/i.test(nameErr), nameErr);
    await page.reload({ waitUntil: 'networkidle0' });
    // retire → reopen as draft
    await H.click(page, 'Retire'); await H.sleep(900);
    H.check('retire', (await H.api(`/api/products/${pid}`)).body.status === 'retired');
    await H.click(page, 'Reopen as draft'); await H.sleep(900);
    H.check('reopen as draft', (await H.api(`/api/products/${pid}`)).body.status === 'draft', '', await S('09-reopened', true));
    // dashboard reflects it
    await page.goto(H.BASE + '/', { waitUntil: 'networkidle0' }); await S('10-dashboard', true);
    await B.close();
  } catch (e) { H.check('journey ran without crash', false, e.stack.split('\n').slice(0, 2).join(' '), await H.shot(page, 'j3-crash', true)); }
  H.check('no console errors / unexpected failed API calls', problems.filter(p => !/http (400|409|422)|status of (400|409|422)/.test(p)).length === 0, problems.join(' ; '));
  await Promise.race([browser.close(), H.sleep(5000)]).catch(() => {});
  process.exit(H.save('8_live_money') ? 1 : 0);
})();
