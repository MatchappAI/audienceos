// Live journey 6: Library "Back up database", then Settings "Remove demo project" (asks first; Cancel keeps it).
const H = require('./human');
(async () => {
  const { browser, page, problems } = await H.open();
  try {
    await page.goto(H.BASE + '/library', { waitUntil: 'networkidle0' });
    await H.click(page, 'Back up database'); await H.sleep(2000);
    const t = await H.main(page);
    H.check('Back up database reports where the copy went', /backup|Backed up|saved/i.test(t), (t.match(/[^\n]*(backup|Backed)[^\n]*/i) || [''])[0], await H.shot(page, 'j6-01-backup'));
    await page.goto(H.BASE + '/settings', { waitUntil: 'networkidle0' });
    let asked = ''; page.removeAllListeners('dialog'); page.once('dialog', d => { asked = d.message(); d.dismiss(); });
    await H.click(page, 'Remove demo project'); await H.sleep(800);
    const still = (await H.api('/api/audiences')).body.some(a => a.is_demo);
    H.check('Remove demo project asks first; Cancel keeps it', !!asked && still, asked.slice(0, 120));
    page.once('dialog', d => d.accept());
    await H.click(page, 'Remove demo project'); await H.sleep(2500);
    const auds = (await H.api('/api/audiences')).body; const cr = (await H.api('/api/creators')).body.creators;
    H.check('demo audience, creator and its products are gone', !auds.some(a => a.is_demo) && !cr.some(c => c.is_demo), `audiences left: ${auds.map(a => a.name).join(', ') || 'none'}`);
    await page.goto(H.BASE + '/', { waitUntil: 'networkidle0' });
    H.check('dashboard offers the demo again', /Load demo project/.test(await H.main(page)), '', await H.shot(page, 'j6-02-after-remove'));
  } catch (e) { H.check('journey ran without crash', false, e.stack.split('\n').slice(0, 2).join(' ')); }
  H.check('no console errors / failed API calls', problems.length === 0, problems.join(' ; '));
  await Promise.race([browser.close(), H.sleep(5000)]).catch(() => {});
  process.exit(H.save('12_live_cleanup') ? 1 : 0);
})();
