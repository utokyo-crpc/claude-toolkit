// tonton (tonton.amaneku.com) adapter.
//
// The timeline cells are NOT reliably clickable (zero-size spans; the MT_* JS has
// opaque indirection and defaults every proposed slot to ○). So instead of driving
// the UI, we POST the answer form directly to /add.php, which is deterministic.
//
// Wire format (verified): one field mtgtime_flg_<N> per candidate day (N = day index+1),
// a 48-char string where char position p = time p*30min from 00:00 (so 10:00 = pos 20).
//   '5' = ○ (available), '1' = × (unavailable), '2' = △, '-' = not a proposed slot.
// Proposed slots default to '5'. We set free in-hours slots to '5' (○) and every other
// proposed slot (busy or outside 08:00–17:00) to '1' (×) — so no blank cells remain.
import { judge } from '../availability.mjs';
export const supportsTriangle = true;

const pad = (n) => String(n).padStart(2, '0');
const posToTime = (p) => `${pad(Math.floor(p / 2))}:${pad((p % 2) * 30)}`;
const pollIdOf = (url) => (url.match(/[?&]id=([^&]+)/) || [])[1];

export async function scrape(page, url) {
  await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 30000 });
  await page.waitForTimeout(3000);
  const title = await page.title();
  const dates = await page.evaluate(() => {
    const found = document.body.innerText.match(/(?:20)?\d{2}\/\d{1,2}\/\d{1,2}\([日月火水木金土]\)/g) || [];
    return [...new Set(found)];
  });
  const candidates = dates.map((raw, i) => {
    const m = raw.match(/((?:20)?\d{2})\/(\d{1,2})\/(\d{1,2})/);
    let y = +m[1]; if (y < 100) y += 2000;
    const date = `${y}-${String(+m[2]).padStart(2, '0')}-${String(+m[3]).padStart(2, '0')}`;
    return { date, start: null, end: null, label: raw, index: i };
  });
  return { title, candidates }; // empty => poll closed / stale => soft-skip upstream
}

// Delete existing entries matching displayName (needs the edit password), so a re-answer
// overwrites instead of duplicating (tonton adds a new row per submit and never dedupes).
async function deleteExisting(page, url, displayName, password) {
  let removed = 0;
  for (let guard = 0; guard < 12; guard++) {
    await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 30000 });
    await page.waitForTimeout(2500);
    const idx = await page.evaluate((name) => {
      const a = [...document.querySelectorAll('a[onclick]')].find((e) => {
        const m = e.getAttribute('onclick').match(/deleteMember\(this, '(\d+)', '([^']*)'\)/);
        return m && m[2] === name;
      });
      return a ? a.getAttribute('onclick').match(/deleteMember\(this, '(\d+)'/)[1] : null;
    }, displayName);
    if (idx === null) break;
    await page.evaluate((i) => {
      const a = [...document.querySelectorAll('a[onclick]')].find((e) =>
        e.getAttribute('onclick').includes(`deleteMember(this, '${i}'`));
      if (a) a.click();
    }, idx);
    await page.waitForTimeout(1500);
    await page.fill('#password', password).catch(() => {});
    const ok = await page.evaluate(() => {
      if (typeof window.DeleteForm?.onDeleteSubmit === 'function') { window.DeleteForm.onDeleteSubmit(); return true; }
      return false;
    });
    if (!ok) break;
    await page.waitForTimeout(2500);
    removed++;
  }
  return removed;
}

export async function answer(page, url, { displayName, decisions, dryRun, editPassword, busy, cfg }) {
  const dateByDay = {};
  for (const d of decisions) dateByDay[d.candidate.index] = d.candidate.date;

  // Read the proposed slot positions per day from the "予定を追加" form.
  const link = await page.$('text=あなたの予定を追加する');
  if (!link) throw new Error('tonton: 「あなたの予定を追加する」リンクが見つかりません');
  await link.click();
  await page.waitForTimeout(1800);
  const proposed = await page.evaluate(() => {
    const byDay = {};
    for (const e of document.querySelectorAll('span[id^="mtgtime_"]')) {
      if (e.className.includes('timesel_disabled')) continue;
      const m = e.id.match(/^mtgtime_(\d+)_(\d{2})(\d{2})$/);
      if (!m) continue;
      const day = +m[1], pos = (+m[2]) * 2 + (+m[3]) / 30;
      (byDay[day] ||= new Set()).add(pos);
    }
    const out = {};
    for (const [k, s] of Object.entries(byDay)) out[k] = [...s].sort((a, b) => a - b);
    return out;
  });

  // Build one 48-char flag per day: free in-hours proposed → '5'(○), else → '1'(×).
  const FLAGLEN = 48;
  const flags = {};
  const perDay = {};
  for (let day = 0; day < decisions.length; day++) {
    const date = dateByDay[day];
    const arr = Array(FLAGLEN).fill('-');
    perDay[date] = { on: 0, off: 0 };
    for (const pos of proposed[day] || []) {
      const { mark } = judge({ date, start: posToTime(pos), end: posToTime(pos + 1) }, busy, cfg, { supportsTriangle: false });
      if (mark === '◯') { arr[pos] = '5'; perDay[date].on++; }
      else { arr[pos] = '1'; perDay[date].off++; }
    }
    flags[day + 1] = arr.join('');
  }

  // Day-level marks for the log, derived from the exact slots submitted.
  const dayDecision = {};
  for (const d of decisions) dayDecision[d.candidate.date] = d;
  const dayMarks = {};
  for (const [date, pd] of Object.entries(perDay)) {
    const total = pd.on + pd.off;
    if (total === 0) continue;
    if (pd.on === 0) dayMarks[date] = { mark: '✕', reason: dayDecision[date]?.reason === '週末・休日' ? '週末・休日' : '空き枠なし' };
    else if (pd.off === 0) dayMarks[date] = { mark: '◯', reason: `全${total}枠が空き` };
    else dayMarks[date] = { mark: '△', reason: `${pd.on}/${total}枠が空き` };
  }
  const totalOn = Object.values(perDay).reduce((a, b) => a + b.on, 0);

  if (dryRun) {
    return { submitted: false, reviewUrl: url, dayMarks, painted: { on: totalOn }, removed: 0,
      note: `dry-run: 空き${totalOn}枠を○（未送信）` };
  }

  // Overwrite: remove prior same-name entries, then POST the answer directly.
  let removed = 0;
  if (editPassword) removed = await deleteExisting(page, url, displayName, editPassword);
  await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 30000 });
  await page.waitForTimeout(2000);

  const params = new URLSearchParams();
  params.set('username', displayName);
  params.set('usernote', '');
  params.set('userpassword', editPassword || '');
  params.set('mtgdate_counter', String(decisions.length));
  for (let n = 1; n <= decisions.length; n++) params.set(`mtgtime_flg_${n}`, flags[n]);

  const pollId = pollIdOf(url);
  const status = await page.evaluate(async ({ body, pollId }) => {
    const r = await fetch(`https://tonton.amaneku.com/add.php?id=${pollId}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body,
      credentials: 'include',
    });
    return r.status;
  }, { body: params.toString(), pollId });
  if (status < 200 || status >= 400) throw new Error(`tonton: add.php returned ${status}`);
  await page.waitForTimeout(1500);

  return { submitted: true, reviewUrl: url, dayMarks, painted: { on: totalOn }, removed,
    note: `送信完了（空き${totalOn}枠○・不可枠×${removed ? `・旧${removed}件上書き` : ''}）` };
}
