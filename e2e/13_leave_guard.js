// Pass 3 regression: typed edits on the product setup and the deal form are no longer lost silently when you click
// a sidebar link. Cancel keeps you on the page with the edits; OK leaves. Needs a scratch server with one creator
// (BASE=http://127.0.0.1:8771). Headless only.
const H = require('./human');
(async () => {
  const cr = (await H.api('/api/audiences', { method: 'POST', body: JSON.stringify({ org_name: 'Guard Co ' + Date.now() }) })).body;
  const pr = (await H.api('/api/products', { method: 'POST', body: JSON.stringify({ audience_id: cr.id, name: 'Guarded kit', price: 29, checkout_url: 'https://x.example' }) })).body;
  const { browser, page, problems } = await H.open();
  let answer = false;
  page.removeAllListeners('dialog');
  page.on('dialog', d => (answer ? d.accept() : d.dismiss()));
  await page.goto(H.BASE + '/products/' + pr.id, { waitUntil: 'networkidle0' });
  await H.fill(page, 'Notes', 'typed but not saved');
  await H.click(page, 'Creators & Revenue', { sel: 'nav a, aside a' });
  await H.sleep(400);
  H.check('product: Cancel on the leave question keeps the page and the edit', page.url().includes('/products/') &&
    await page.evaluate(() => [...document.querySelectorAll('textarea')].some(t => t.value === 'typed but not saved')));
  answer = true;
  await H.click(page, 'Creators & Revenue', { sel: 'nav a, aside a' });
  await H.sleep(400);
  H.check('product: OK leaves', page.url().endsWith('/creators'));
  await page.goto(H.BASE + '/creators/' + cr.organization_id, { waitUntil: 'networkidle0' });
  answer = false;
  await H.fill(page, 'Creator share (%)', '55');
  await H.click(page, 'Settings', { sel: 'nav a, aside a' });
  await H.sleep(400);
  H.check('deal: Cancel keeps the half-typed terms', page.url().includes('/creators/'));
  answer = true;
  await H.click(page, 'Settings', { sel: 'nav a, aside a' });
  await H.sleep(400);
  H.check('deal: OK leaves, nothing saved', page.url().endsWith('/settings') &&
    (await H.api(`/api/creators/${cr.organization_id}/statement`)).body.deal === null);
  H.check('no console errors', problems.filter(p => !/http 4/.test(p)).length === 0, problems.join('; '));
  const bad = H.save('13_leave_guard');
  await Promise.race([browser.close(), H.sleep(5000)]);
  process.exit(bad ? 1 : 0);
})();
