// Live journey 1 (person-style): empty app → Load demo (real click) → sources ready → Run analysis (real click)
// → watch progress → refresh mid-run → back button mid-run → wait for results. Scratch server only.
const H = require('./human');
(async () => {
  const { browser, page, problems } = await H.open();
  try {
    await page.goto(H.BASE + '/', { waitUntil: 'networkidle0' });
    const { hit } = await H.click(page, 'Load demo project');
    H.check('mouse lands on the Load demo button', /Load demo/.test(hit || ''), hit);
    await page.waitForFunction(() => location.pathname.includes('/sources'), { timeout: 20000 });
    const t0 = Date.now();
    await H.shot(page, 'j1-01-demo-loading');
    await H.waitText(page, /ready\. Next: run the analysis/, 600000);
    H.check('demo sources ready', true, `${(Date.now() - t0) / 1000}s`, await H.shot(page, 'j1-02-sources-ready', true));
    await H.click(page, 'Go to analysis →');
    await H.sleep(1200);
    await H.shot(page, 'j1-03-before-run');
    await H.click(page, 'Run analysis');
    await H.sleep(2500);
    let t = await H.main(page);
    H.check('progress shown after Run analysis', /Stage \d|Starting/.test(t) && /\d+%/.test(t), t.slice(0, 200), await H.shot(page, 'j1-04-running'));
    // rapid second click (if the button still exists) must not start a second job
    const again = await H.find(page, 'Run analysis');
    if (again) { await H.click(page, again).catch(() => {}); }
    const jobs = (await H.api('/api/jobs')).body;
    const active = (Array.isArray(jobs) ? jobs : jobs.jobs || []).filter(j => /analy/i.test(j.kind || j.type || '') && /queued|running/.test(j.status));
    H.check('one analysis job after repeat click', active.length === 1, JSON.stringify(active.map(j => j.id)));
    await H.sleep(20000);
    await page.reload({ waitUntil: 'networkidle0' });
    t = await H.main(page);
    H.check('refresh mid-run keeps progress visible', /Stage \d/.test(t) && /\d+%/.test(t), t.slice(0, 200), await H.shot(page, 'j1-05-refresh-midrun'));
    await page.goBack({ waitUntil: 'networkidle0' }); await H.sleep(800);
    await H.shot(page, 'j1-06-back-midrun');
    await page.goForward({ waitUntil: 'networkidle0' }); await H.sleep(800);
    // side badge "1 task running"
    const side = await page.$eval('nav.side', e => e.innerText);
    H.check('sidebar shows task running', /task.* running/.test(side), side.replace(/\n/g, ' | ').slice(-80));
    const start = Date.now();
    const jobId = active[0] && active[0].id;
    let job;
    for (;;) {
      job = (await H.api('/api/jobs/' + jobId)).body;
      if (!/queued|running/.test(job.status) || Date.now() - start > 1800000) break;
      await H.sleep(15000);
      H.log('still running:', job.message, Math.round(job.progress * 100) + '%');
    }
    await page.reload({ waitUntil: 'networkidle0' });
    t = await H.main(page);
    const intel = (await H.api('/api/audiences/' + page.url().split('/audiences/')[1].split('/')[0] + '/intelligence')).body;
    H.check('analysis job finished (done)', job.status === 'done', `${job.status} after ${Math.round((Date.now() - start) / 1000)}s more; ${job.error || ''}`);
    H.check('problems tab lists the problem themes the analysis stored', (intel.clusters || []).length > 0 && (intel.clusters || []).every(c => t.includes(c.label || c.name || '')), `clusters=${(intel.clusters || []).length}`, await H.shot(page, 'j1-07-results', true));
  } catch (e) { H.check('journey ran without crash', false, e.message, await H.shot(page, 'j1-crash')); }
  H.check('no console errors / failed API calls', problems.length === 0, problems.join(' ; '));
  await browser.close();
  process.exit(H.save('5_live_first_run') ? 1 : 0);
})();
