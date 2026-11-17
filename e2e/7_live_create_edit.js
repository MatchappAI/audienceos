// Live journey 2 (person-style): keyboard-only create creator → validation → channels → paste text → drag/drop + file
// chooser upload → edit details (save, refresh, cancel-discards) → channel edit/remove → delete audience.
const H = require('./human');
const path = require('path');
const FX = path.join(__dirname, '..', 'fixtures', 'demo');
(async () => {
  const { browser, page, problems } = await H.open();
  const S = (n, f) => H.shot(page, 'j2-' + n, f);
  try {
    await page.goto(H.BASE + '/audiences', { waitUntil: 'networkidle0' });
    // --- keyboard only: Tab to "New creator or business", Enter
    let found = false;
    for (let i = 0; i < 25; i++) {
      await page.keyboard.press('Tab');
      const a = await page.evaluate(() => document.activeElement?.innerText?.trim());
      if (a === 'New creator or business') { found = true; break; }
    }
    H.check('keyboard: Tab reaches "New creator or business"', found);
    const ring = await page.evaluate(() => getComputedStyle(document.activeElement).outlineStyle + ' ' + getComputedStyle(document.activeElement).boxShadow);
    H.check('keyboard: focused button shows a focus ring', !/^none none$/.test(ring), ring, await S('01-focus-ring'));
    await page.keyboard.press('Enter'); await H.sleep(400);
    const focusIn = await page.evaluate(() => document.activeElement?.closest('.modal') ? document.activeElement.placeholder || document.activeElement.tagName : 'outside');
    H.check('modal opens with focus on the name field', /Maya/.test(focusIn), focusIn);
    // Tab through the whole modal: focus must stay inside the dialog
    const escaped = [];
    for (let i = 0; i < 16; i++) { await page.keyboard.press('Tab'); const inside = await page.evaluate(() => !!document.activeElement?.closest('.modal')); if (!inside) escaped.push(await page.evaluate(() => document.activeElement?.innerText?.slice(0, 30) || document.activeElement?.tagName)); }
    H.check('keyboard: Tab stays inside the open dialog', escaped.length === 0, 'escaped to: ' + escaped.slice(0, 3).join(', '), await S('02-modal-tab'));
    // submit disabled with blank name
    const dis = await page.$eval('.modal button.primary', b => b.disabled);
    H.check('Create disabled while name is blank', dis);
    // type name via keyboard
    await page.focus('.modal input[placeholder="e.g. Maya Chen"]');
    await page.keyboard.type('Test Baker Ünïcode ✓', { delay: 10 });
    await H.fill(page, 'Niche', 'Gluten-free baking');
    await page.type('.modal input[aria-label="Handle"]', '@testbaker');
    await page.type('.modal input[aria-label="Followers"]', '12,5k');   // a mistake a person makes
    await H.click(page, 'Create and add content'); await H.sleep(900);
    let t = await page.evaluate(() => document.querySelector('.modal')?.innerText || 'modal closed: ' + location.pathname);
    H.check('bad follower count ("12,5k") is refused with a readable message, form kept', /follower|number|valid/i.test(t) && /modal/.test(await page.evaluate(() => document.querySelector('.modal') ? 'modal' : '')), t.slice(0, 200).replace(/\n/g, ' | '), await S('03-bad-followers'));
    // fix it
    await page.click('.modal input[aria-label="Followers"]', { clickCount: 3 }); await page.keyboard.type('12500');
    // overlay click by mistake must not throw the typed form away
    await page.mouse.click(5, 5); await H.sleep(300);
    const still = await page.$('.modal');
    H.check('stray click outside the dialog does not discard typed form', !!still, still ? '' : 'modal closed, typing lost');
    if (!still) { await H.click(page, 'New creator or business'); await page.type('.modal input[placeholder="e.g. Maya Chen"]', 'Test Baker Ünïcode ✓'); await H.fill(page, 'Niche', 'Gluten-free baking'); await page.type('.modal input[aria-label="Handle"]', '@testbaker'); await page.type('.modal input[aria-label="Followers"]', '12500'); }
    await H.click(page, 'Create and add content');
    await page.waitForFunction(() => /\/audiences\/aud_[^/]+\/sources/.test(location.pathname), { timeout: 10000 });
    const aid = page.url().split('/audiences/')[1].split('/')[0];
    H.check('creator created → lands on Content & sources', true, aid, await S('04-new-sources'));
    // --- paste text (audience comments)
    await H.click(page, 'Paste text'); await H.sleep(300);
    await H.fill(page, 'Title', 'DM questions');
    await page.focus('textarea'); await page.keyboard.type('Where can I buy a gluten-free starter?\nI would pay for a GF loaf course\nMy GF bread is always zebrafluff gummy, help', { delay: 2 });
    await H.click(page, 'Each line is a separate audience comment', { sel: 'label' });
    await H.click(page, 'Add text'); await H.sleep(1200);
    t = await H.main(page);
    H.check('pasted text appears in the source list', /DM questions/.test(t), '', await S('05-text-added'));
    // same text again → duplicate notice
    await H.click(page, 'Paste text').catch(() => {});
    await H.fill(page, 'Title', 'DM questions');
    await page.focus('textarea'); await page.keyboard.type('Where can I buy a gluten-free starter?\nI would pay for a GF loaf course\nMy GF bread is always zebrafluff gummy, help', { delay: 1 });
    // the "each line is a comment" box stays ticked after the first paste
    if (!(await page.$eval('label.check input[type=checkbox]', e => e.checked))) await H.click(page, 'Each line is a separate audience comment', { sel: 'label' });
    await H.click(page, 'Add text');
    // the first paste's "Text added" toast may still be on screen; wait for the new one
    const toast = await page.waitForFunction(() => /already/.test(document.querySelector('.toast')?.innerText || ''), { timeout: 4000 }).then(() => page.$eval('.toast', x => x.innerText)).catch(async () => page.$eval('.toast', x => x.innerText).catch(() => ''));
    H.check('re-pasting the same text says it was already imported', /already/.test(toast), toast);
    // --- drag & drop upload (a real DataTransfer with files, dropped on the dropzone)
    await H.click(page, 'Upload files');
    const fs = require('fs');
    const files = [['newsletter_issue_42.md', 'text/markdown'], ['comments_instagram_export.csv', 'text/csv']].filter(([n]) => fs.existsSync(path.join(FX, n)));
    const payload = files.map(([n, ty]) => ({ name: n, type: ty, data: fs.readFileSync(path.join(FX, n), 'base64') }));
    const dz = await page.$('.dropzone'); const box = await dz.boundingBox();
    await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
    await page.evaluate(async (payload) => {
      const dt = new DataTransfer();
      for (const f of payload) dt.items.add(new File([Uint8Array.from(atob(f.data), c => c.charCodeAt(0))], 'dnd_' + f.name, { type: f.type }));
      const z = document.querySelector('.dropzone');
      z.dispatchEvent(new DragEvent('dragover', { dataTransfer: dt, bubbles: true, cancelable: true }));
      await new Promise(r => setTimeout(r, 150));
      z.dispatchEvent(new DragEvent('drop', { dataTransfer: dt, bubbles: true, cancelable: true }));
    }, payload);
    await H.sleep(400);
    t = await H.main(page);
    H.check('dropped files are listed before import', payload.every(f => t.includes('dnd_' + f.name)), payload.map(p => p.name).join(','), await S('06-dropped'));
    // remove one, then choose a file via the chooser (keyboard: Enter on the drop zone)
    await H.click(page, 'Remove'); await H.sleep(200);
    await page.focus('.dropzone').catch(() => {});
    const dzFocused = await page.evaluate(() => document.activeElement?.classList.contains('dropzone'));
    H.check('keyboard: drop zone can be focused (to open the file chooser)', dzFocused);
    const [chooser] = await Promise.all([page.waitForFileChooser({ timeout: 4000 }).catch(() => null), dzFocused ? page.keyboard.press('Enter') : H.click(page, 'Drop files here')]);
    H.check('file chooser opens', !!chooser, dzFocused ? 'via Enter key' : 'via mouse');
    if (chooser) await chooser.accept([path.join(FX, 'experiment_results_demo.csv')]);
    else await (await page.$('input[type=file]')).uploadFile(path.join(FX, 'experiment_results_demo.csv'));
    await H.sleep(300);
    const btnLabel = await page.evaluate(() => [...document.querySelectorAll('button')].find(b => /^Import \d/.test(b.innerText))?.innerText);
    H.check('import button counts files', /Import 2 files/.test(btnLabel || ''), btnLabel);
    await H.click(page, btnLabel || 'Import'); await H.sleep(2500);
    t = await H.main(page);
    H.check('import results shown per file', /queued|already imported/.test(t), (t.match(/dnd_[^\n]*/g) || []).join(' ; '), await S('07-imported'));
    // --- Overview: edit details → cancel must discard → edit → save → refresh persists
    await H.click(page, 'Overview', { sel: '.tabs a' }); await H.sleep(800);
    // the Details card Edit (last "Edit" on page that isn't a channel row)
    await page.evaluate(() => { const c = [...document.querySelectorAll('.card')].find(c => c.querySelector('h2')?.innerText === 'Details'); c.querySelector('button.btn.sm').scrollIntoView(); });
    const detailsEdit = await page.evaluateHandle(() => [...document.querySelectorAll('.card')].find(c => c.querySelector('h2')?.innerText === 'Details').querySelector('.card-head button'));
    if (await detailsEdit.evaluate(b => b && b.innerText === 'Edit')) await H.click(page, detailsEdit.asElement());
    await H.fill(page, 'Niche', 'ABANDONED EDIT');
    await H.click(page, 'Cancel', { within: '.main' }); await H.sleep(300);
    const reopen = await page.evaluateHandle(() => [...document.querySelectorAll('.card')].find(c => c.querySelector('h2')?.innerText === 'Details').querySelector('.card-head button'));
    await H.click(page, reopen.asElement()); await H.sleep(200);
    const nicheVal = await page.evaluate(() => [...document.querySelectorAll('label.field')].find(l => l.innerText.startsWith('Niche')).querySelector('input').value);
    H.check('Cancel discards an abandoned edit (reopening shows saved value)', nicheVal === 'Gluten-free baking', `reopened with "${nicheVal}"`, await S('08-cancel-discard'));
    await H.fill(page, 'Niche', 'GF sourdough');
    await H.click(page, 'Save', { sel: 'button', exact: true }); await H.sleep(800);
    await page.reload({ waitUntil: 'networkidle0' });
    t = await H.main(page);
    H.check('edited niche persists after refresh', /GF sourdough/.test(t));
    // blank org name must be refused
    const re2 = await page.evaluateHandle(() => [...document.querySelectorAll('.card')].find(c => c.querySelector('h2')?.innerText === 'Details').querySelector('.card-head button'));
    await H.click(page, re2.asElement()); await H.fill(page, 'Creator / business', '');
    await H.click(page, 'Save', { sel: 'button', exact: true }); await H.sleep(800);
    t = await H.main(page);
    const a1 = (await H.api(`/api/audiences/${aid}`)).body;
    H.check('blank creator name is refused (not saved)', a1.org_name && a1.org_name.trim() !== '', `org_name="${a1.org_name}" screen: ` + ((t.match(/[^\n]*(required|empty|blank|at least)[^\n]*/i) || [''])[0]), await S('09-blank-name'));
    await page.reload({ waitUntil: 'networkidle0' });
    // --- channel: edit followers, then remove (should ask first)
    await H.click(page, 'Edit', { sel: '.card table button', exact: true }); await H.sleep(300);
    await H.fill(page, 'Followers / subscribers', '13000');
    await H.click(page, 'Save', { within: '.modal', sel: 'button' }); await H.sleep(800);
    t = await H.main(page);
    H.check('channel follower edit saved', /13,000/.test(t));
    let asked = false; page.removeAllListeners('dialog'); page.on('dialog', d => { asked = true; d.dismiss(); });
    await H.click(page, 'Remove', { sel: '.card table button' }); await H.sleep(800);
    const chs = (await H.api(`/api/audiences/${aid}`)).body.channels.length;
    H.check('removing a channel asks first (dismiss keeps it)', asked && chs === 1, `asked=${asked} channels=${chs}`);
    page.removeAllListeners('dialog'); page.on('dialog', d => d.accept());
    // --- delete audience (confirm) → back to list, gone
    await H.click(page, 'Delete audience'); await page.waitForFunction(() => location.pathname === '/audiences', { timeout: 8000 });
    t = await H.main(page);
    H.check('deleted audience disappears from the list', !/Test Baker/.test(t), '', await S('10-after-delete'));
    const lib = (await H.api('/api/library?q=zebrafluff')).body;
    H.check('its material is gone from the library search', !JSON.stringify(lib).includes('zebrafluff'), JSON.stringify(lib).slice(0, 120));
  } catch (e) { H.check('journey ran without crash', false, e.stack.split('\n').slice(0, 2).join(' '), await H.shot(page, 'j2-crash')); }
  H.check('no console errors / failed API calls (excluding deliberate 4xx)', problems.filter(p => !/http 4(00|22)|status of 4(00|22)/.test(p)).length === 0, problems.join(' ; '));
  await Promise.race([browser.close(), H.sleep(5000)]).catch(() => {});
  process.exit(H.save('7_live_create_edit') ? 1 : 0);
})();
