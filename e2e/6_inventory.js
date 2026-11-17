// Discovery: every route → every visible control (buttons, links, inputs, tabs) with its accessible name.
// Output: qa/inventory.json (used to build the test inventory in LIVE_QA_REPORT.md). Read-only (no clicks).
const H = require('./human');
const fs = require('fs');
(async () => {
  const aud = (await H.api('/api/audiences')).body.find(a => a.is_demo) || (await H.api('/api/audiences')).body[0];
  const g = async p => (await H.api(p)).body;
  const opp = aud && (await g(`/api/opportunities?audience_id=${aud.id}`))[0];
  const x = (await g('/api/experiments'))[0];
  const prod = (await g('/api/products'))[0];
  const cr = (await g('/api/creators')).creators[0];
  const routes = ['/', '/audiences', '/audiences?new=1', '/intelligence', '/opportunities', '/validation', '/library', '/creators', '/settings'];
  if (aud) routes.push(...['sources', 'problems', 'signals', 'opportunities', 'experiments', 'products', 'reports'].map(t => `/audiences/${aud.id}/${t}`), `/intelligence/${aud.id}`);
  if (opp) routes.push(`/opportunities/${opp.id}`);
  if (x) routes.push(`/validation/${x.id}`);
  if (prod) routes.push(`/products/${prod.id}`);
  if (cr) routes.push(`/creators/${cr.id}`);
  const { browser, page } = await H.open();
  const inv = {};
  for (const r of routes) {
    await page.goto(H.BASE + r, { waitUntil: 'networkidle0' });
    inv[r] = await page.evaluate(() => {
      const vis = e => { const b = e.getBoundingClientRect(); return b.width > 0 && b.height > 0; };
      const name = e => ((e.getAttribute('aria-label') || e.innerText || e.value || e.placeholder || e.title || '') + '').replace(/\s+/g, ' ').trim().slice(0, 50);
      const scope = document.querySelector('main') || document.body;
      const out = [];
      for (const e of scope.querySelectorAll('button, a[href], input, select, textarea, summary, [role=button], [onclick], .dropzone, tr.click')) {
        if (!vis(e)) continue;
        let lab = name(e);
        if (/INPUT|SELECT|TEXTAREA/.test(e.tagName)) { const l = e.closest('label'); lab = (l ? (l.querySelector('span')?.innerText || l.innerText) : '').replace(/\s+/g,' ').trim().slice(0,40) + ' [' + (e.type || e.tagName.toLowerCase()) + ']' + (lab ? ' ' + lab : ''); }
        const focusable = e.tabIndex >= 0;
        out.push((e.tagName === 'A' ? 'link' : e.tagName.toLowerCase() + (e.className && typeof e.className === 'string' && e.className.includes('dropzone') ? '.dropzone' : '')) + ': ' + lab + (focusable ? '' : ' (NOT keyboard-focusable)') + (e.disabled ? ' (disabled)' : ''));
      }
      return [...new Set(out)];
    });
  }
  await browser.close();
  fs.mkdirSync(__dirname + '/../qa', { recursive: true });
  fs.writeFileSync(__dirname + '/../qa/inventory.json', JSON.stringify(inv, null, 1));
  for (const [r, c] of Object.entries(inv)) console.log(r, c.length, 'controls');
})();
