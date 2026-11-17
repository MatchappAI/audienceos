// Live journey 4: interruptions. Stop a running analysis from the UI (and the next one still runs);
// the local AI engine dies mid-analysis (clear message, retry works after it's back); the app server goes away
// while a page is open (clear message, recovers without a reload). Needs OLLAMA_PID / SERVER_CMD from the runner
// (scratch processes only — it never touches anything it didn't start).
const H = require('./human');
const { execSync, spawn } = require('child_process');
const fs = require('fs');
async function activeJob(aid) { return ((await H.api('/api/jobs?active=1')).body || []).find(j => j.audience_id === aid && j.kind === 'analyze_audience'); }
(async () => {
  const { browser, page, problems } = await H.open();
  const S = (n, f) => H.shot(page, 'j4-' + n, f);
  try {
    const aud = (await H.api('/api/audiences')).body.find(a => a.is_demo);
    await page.goto(`${H.BASE}/audiences/${aud.id}`, { waitUntil: 'networkidle0' });
    // 1) Stop from the UI
    await H.click(page, 'Reanalyze'); await H.sleep(2500);
    let j = await activeJob(aud.id);
    H.check('reanalysis started', !!j, j && j.message, await S('01-running'));
    await H.click(page, 'Stop analysis'); await H.sleep(1500);
    const jj = (await H.api('/api/jobs/' + j.id)).body;
    let t = await H.main(page);
    H.check('Stop analysis cancels the job and the button goes back to Reanalyze', jj.status === 'cancelled' && /Reanalyze/.test(t), jj.status, await S('02-stopped'));
    const intel = (await H.api(`/api/audiences/${aud.id}/intelligence`)).body;
    H.check('previous results still shown after stopping', (intel.clusters || []).length > 0, `clusters=${(intel.clusters || []).length}`);
    // the single worker must be free again: a fresh start becomes the running job within ~1 min
    await H.click(page, 'Reanalyze'); await H.sleep(2000);
    const t0 = Date.now(); let j2;
    for (;;) { j2 = await activeJob(aud.id); if ((j2 && j2.status === 'running' && j2.progress > 0.02) || Date.now() - t0 > 240000) break; await H.sleep(3000); }
    H.check('after a stop, the next analysis actually runs (worker not stuck)', j2 && j2.status === 'running', j2 ? `${j2.message} after ${Math.round((Date.now() - t0) / 1000)}s` : 'no job');
    // 2) Engine dies mid-analysis
    if (process.env.OLLAMA_PID) {
      process.kill(Number(process.env.OLLAMA_PID), 'SIGTERM');
      H.log('stopped the scratch Ollama', process.env.OLLAMA_PID);
      const t1 = Date.now(); let jf;
      for (;;) { jf = (await H.api('/api/jobs/' + j2.id)).body; if (!/queued|running/.test(jf.status) || Date.now() - t1 > 600000) break; await H.sleep(5000); }
      await page.reload({ waitUntil: 'networkidle0' }); t = await H.main(page);
      H.check('engine stopped mid-analysis → the job ends (no endless spinner)', jf.status === 'failed', `${jf.status}: ${jf.error} (${Math.round((Date.now() - t1) / 1000)}s)`);
      H.check('the page explains what went wrong in plain words', /not running|Ollama|engine/i.test(t), (t.match(/[^\n]*(Ollama|engine)[^\n]*/i) || [''])[0], await S('03-engine-down', true));
      const btnDisabled = await page.evaluate(() => [...document.querySelectorAll('button')].find(b => /Reanalyze|Run analysis/.test(b.innerText))?.disabled);
      H.check('Reanalyze is disabled while the engine is down, with a link to Settings', btnDisabled === true && /Open Settings/.test(t));
      // bring the engine back (the runner restarts it) and check the page notices without a reload
      fs.writeFileSync(process.env.RESTART_FLAG, '1');
      const t2 = Date.now(); let back = false;
      for (; Date.now() - t2 < 90000;) { await H.sleep(3000); back = await page.evaluate(() => [...document.querySelectorAll('button')].some(b => /Reanalyze/.test(b.innerText) && !b.disabled)); if (back) break; }
      H.check('when the engine is back, Reanalyze becomes available again without reloading', back, `${Math.round((Date.now() - t2) / 1000)}s`);
      if (!back) { await page.reload({ waitUntil: 'networkidle0' }); back = await page.evaluate(() => [...document.querySelectorAll('button')].some(b => /Reanalyze/.test(b.innerText) && !b.disabled)); H.check('…after a reload it is available', back); }
    }
    // 3) App server goes away while the page is open
    if (process.env.SERVER_PID) {
      process.kill(Number(process.env.SERVER_PID), 'SIGTERM'); await H.sleep(1500);
      await H.click(page, 'Content & sources', { sel: '.tabs a' }); await H.sleep(2500);
      t = await H.main(page);
      H.check('server down → plain message, not a blank page', /Can't reach the AudienceOS engine/.test(t), (t.match(/[^\n]*reach[^\n]*/) || [t.slice(0, 80)])[0], await S('04-server-down'));
      fs.writeFileSync(process.env.RESTART_FLAG, 'server');
      for (let i = 0; i < 40; i++) { await H.sleep(500); if ((await H.api('/api/health').catch(() => ({}))).status === 200) break; }
      const retry = await H.find(page, 'Try again');
      if (retry) await H.click(page, retry); else await page.reload({ waitUntil: 'networkidle0' });
      await H.sleep(1500); t = await H.main(page);
      H.check('server back → "Try again" recovers the page', /Instagram comments export/.test(t), retry ? 'via Try again' : 'needed reload', await S('05-server-back'));
    }
  } catch (e) { H.check('journey ran without crash', false, e.stack.split('\n').slice(0, 2).join(' '), await H.shot(page, 'j4-crash', true)); }
  await browser.close();
  process.exit(H.save('10_live_interruptions') ? 1 : 0);
})();
