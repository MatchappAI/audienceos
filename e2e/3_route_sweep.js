const { open, sleep, api, BASE } = require('./lib');
(async () => {
  const aud = (await api('/api/audiences')).body.find(a => a.is_demo);
  const opp = (await api(`/api/opportunities?audience_id=${aud.id}`)).body[0];
  const x = (await api('/api/experiments')).body[0];
  const prod = (await api('/api/products')).body[0];
  const routes = ['/', '/audiences', '/audiences?new=1', `/audiences/${aud.id}`, ...['sources', 'problems', 'signals', 'opportunities', 'experiments', 'products', 'reports', 'bogus'].map(t => `/audiences/${aud.id}/${t}`),
    '/intelligence', `/intelligence/${aud.id}`, '/opportunities', `/opportunities/${opp.id}`, '/validation', `/validation/${x.id}`, '/library', '/library?q=starter', '/creators', `/creators/${(await api('/api/creators')).body.creators[0].id}`, `/products/${prod.id}`, '/settings', '/nope', '/products/pr_missing', '/opportunities/op_missing'];
  const out = [];
  for (const [w, h] of [[1440, 900], [390, 844]]) for (const theme of ['light', 'dark']) {
    const { browser, page, problems } = await open({ w, h });
    await page.goto(BASE + '/', { waitUntil: 'networkidle0' });
    await page.evaluate(t => localStorage.setItem('aos-theme', t), theme);
    for (const r of routes) {
      problems.length = 0;
      const t0 = Date.now();
      await page.goto(BASE + r, { waitUntil: 'networkidle0' });
      const ms = Date.now() - t0;
      const a = await page.evaluate(() => {
        const vis = e => e.offsetParent !== null;
        const nameless = [...document.querySelectorAll('button, a[href]')].filter(vis).filter(e => !(e.innerText.trim() || e.getAttribute('aria-label') || e.getAttribute('title'))).map(e => e.outerHTML.slice(0, 80));
        const unlabeled = [...document.querySelectorAll('input:not([type=hidden]):not([type=file]), select, textarea')].filter(vis).filter(e => !(e.closest('label') || e.getAttribute('aria-label') || e.id && document.querySelector(`label[for="${e.id}"]`) || e.getAttribute('placeholder'))).map(e => e.outerHTML.slice(0, 80));
        const hscroll = document.documentElement.scrollWidth > window.innerWidth + 1;
        const h1 = document.querySelectorAll('h1').length;
        const blank = (document.querySelector('main')?.innerText || '').trim().length < 20;
        return { nameless, unlabeled, hscroll, h1, blank, path: location.pathname };
      });
      if (theme === 'light' && w === 1440) await page.screenshot({ path: `${__dirname}/shots/sweep${r.replace(/[\/?=]/g, '_')}.png` });
      if (w === 390 && theme === 'dark') await page.screenshot({ path: `${__dirname}/shots/narrow${r.replace(/[\/?=]/g, '_')}.png` });
      out.push({ w, theme, r, ms, problems: [...problems], ...a });
    }
    await browser.close();
  }
  const bad = out.filter(o => o.problems.length || o.nameless.length || o.unlabeled.length || o.hscroll || o.blank || o.h1 !== 1);
  for (const b of bad) console.log(JSON.stringify(b));
  const ms = out.map(o => o.ms).sort((a, b) => a - b);
  console.log(`checked ${out.length} page loads; flagged ${bad.length}; median ${ms[ms.length >> 1]} ms, max ${ms[ms.length - 1]} ms`);
})();
