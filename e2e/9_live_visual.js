// Visual pass: every populated route at phone (390) and desktop (1440), light + dark; full-page screenshots
// for a human/agent to look at, plus layout checks (sideways scroll, off-screen controls, clipped buttons).
const H = require('./human');
(async () => {
  const g = async p => (await H.api(p)).body;
  const aud = (await g('/api/audiences')).find(a => a.is_demo);
  const opp = (await g(`/api/opportunities?audience_id=${aud.id}`))[0];
  const x = (await g('/api/experiments'))[0];
  const prod = (await g('/api/products'))[0];
  const cr = (await g('/api/creators')).creators.find(c => c.deal) || (await g('/api/creators')).creators[0];
  const routes = { dash: '/', research: '/audiences', newcreator: '/audiences?new=1', overview: `/audiences/${aud.id}`, sources: `/audiences/${aud.id}/sources`,
    problems: `/audiences/${aud.id}/problems`, signals: `/audiences/${aud.id}/signals`, intel: `/intelligence/${aud.id}`, opps: '/opportunities', opp: `/opportunities/${opp.id}`,
    lab: '/validation', exp: `/validation/${x.id}`, library: '/library', creators: '/creators', creator: `/creators/${cr.id}`, product: `/products/${prod.id}`, settings: '/settings' };
  const only = process.env.ONLY ? process.env.ONLY.split(',') : null;
  let issues = 0;
  for (const [w, h, tag] of [[390, 844, 'phone'], [1440, 900, 'desk']]) for (const theme of ['light', 'dark']) {
    const { browser, page, problems } = await H.open({ w, h });
    await page.goto(H.BASE + '/', { waitUntil: 'networkidle0' });
    await page.evaluate(t => localStorage.setItem('aos-theme', t), theme);
    for (const [k, r] of Object.entries(routes)) {
      if (only && !only.includes(k)) continue;
      problems.length = 0;
      await page.goto(H.BASE + r, { waitUntil: 'networkidle0' }); await H.sleep(250);
      const li = await H.layoutIssues(page);
      const ev = await H.shot(page, `v-${tag}-${theme}-${k}`, true);
      const ok = H.check(`${tag} ${theme} ${k}: no layout problems or errors`, li.length === 0 && problems.length === 0, [...li, ...problems].join(' ; '), ev);
      if (!ok) issues++;
    }
    await browser.close();
  }
  process.exit(H.save('9_live_visual') ? 1 : 0);
})();
