const { open, sleep, clickText, text, api, BASE } = require('./lib');
(async () => {
  const { browser, page, problems } = await open();
  await page.goto(BASE + '/', { waitUntil: 'networkidle0' });
  console.log('DASH EMPTY:', (await text(page)).slice(0, 300).replace(/\n/g, ' | '));
  await clickText(page, 'Load demo project');
  await page.waitForFunction(() => location.pathname.includes('/sources'), { timeout: 20000 });
  console.log('URL', page.url());
  const t0 = Date.now();
  for (;;) { const t = await text(page); if (/ready\. Next: run the analysis/.test(t)) break; if (Date.now() - t0 > 600000) throw new Error('sources timeout'); await sleep(3000); }
  console.log('sources ready in', (Date.now() - t0) / 1000, 's');
  console.log((await text(page)).slice(0, 1500));
  await clickText(page, 'Go to analysis →');
  await sleep(1500);
  console.log('PROBLEMS TAB:', (await text(page)).slice(0, 800));
  await clickText(page, 'Run analysis');
  await sleep(3000);
  console.log('AFTER RUN:', (await text(page)).slice(0, 600));
  console.log('PROBLEMS', JSON.stringify(problems));
  await browser.close();
})().catch(e => { console.error('FAIL', e); process.exit(1); });
