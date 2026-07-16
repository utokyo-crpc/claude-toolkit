// 調整さん (chouseisan.com) adapter.
// Candidates parse reliably from the page's embedded JSON `choices` array.
// Answer flow: reveal input row -> name -> per-candidate ○/△/× -> submit.
export const supportsTriangle = true;

const WD = ['日', '月', '火', '水', '木', '金', '土'];
const weekdayOf = (y, mo, d) => {
  const dt = new Date(`${y}-${String(mo).padStart(2, '0')}-${String(d).padStart(2, '0')}T12:00:00+09:00`);
  return WD[['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']
    .indexOf(new Intl.DateTimeFormat('en-US', { timeZone: 'Asia/Tokyo', weekday: 'short' }).format(dt))];
};

// Chouseisan labels omit the year. Pick the nearest year (this-1 .. this+2) whose
// M/D matches the poll's stated weekday and is not far in the past.
function inferYear(month, day, statedWd) {
  const now = new Date();
  const base = now.getFullYear();
  const candidates = [base, base + 1, base + 2, base - 1];
  const matches = statedWd
    ? candidates.filter((y) => weekdayOf(y, month, day) === statedWd)
    : candidates;
  const pool = matches.length ? matches : candidates;
  const future = pool
    .map((y) => ({ y, t: new Date(`${y}-${String(month).padStart(2, '0')}-${String(day).padStart(2, '0')}T12:00:00+09:00`).getTime() }))
    .filter((x) => x.t >= now.getTime() - 2 * 86400000)
    .sort((a, b) => a.t - b.t);
  return (future[0] || pool.map((y) => ({ y })).sort((a, b) => b.y - a.y)[0]).y;
}

function parseChoice(raw) {
  // Handles "6/2(火) …" (no year) and "2026/7/22 …" (explicit year).
  const m = raw.match(/(?:(\d{4})\/)?(\d{1,2})\/(\d{1,2})/);
  if (!m) return null;
  const month = +m[2], day = +m[3];
  if (month < 1 || month > 12 || day < 1 || day > 31) return null;
  const wdMatch = raw.match(/\(([日月火水木金土])\)/);
  const year = m[1] ? +m[1] : inferYear(month, day, wdMatch ? wdMatch[1] : null);
  const date = `${year}-${String(month).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
  const t = raw.match(/(\d{1,2}:\d{2})\s*[〜~\-]\s*(\d{1,2}:\d{2})/);
  const t1 = raw.match(/(\d{1,2}:\d{2})/);
  return {
    date,
    start: t ? t[1] : (t1 ? t1[1] : null),
    end: t ? t[2] : null,
    label: raw.trim(),
  };
}

export async function scrape(page, url) {
  await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 30000 });
  await page.waitForTimeout(3000);
  const title = await page.title();
  const choices = await page.evaluate(() => {
    const m = document.documentElement.innerHTML.match(/"choices":\s*(\[.*?\])/s);
    if (!m) return null;
    try { return JSON.parse(m[1]).map((c) => c.choice); } catch { return null; }
  });
  // No choices = poll closed / deadline passed / stale link → soft-skip (empty).
  const candidates = (choices || []).map(parseChoice).filter(Boolean)
    .map((c, i) => ({ ...c, index: i }));
  return { title, candidates };
}

// Each candidate row has three <input type=image class=oax> buttons. Their ids are
// NOT unique (all "oax_0_0/0_1/0_2"); the reliable key is the alt text:
//   "<choice label>_<まる|さんかく|ばつ>". We select by alt (getByAltText).
const MARK_NAME = { '◯': 'まる', '△': 'さんかく', '✕': 'ばつ' };

// decisions: [{candidate, mark:'◯'|'△'|'✕'}] aligned to scrape order.
export async function answer(page, url, { displayName, decisions, dryRun }) {
  // Reveal the answer input form.
  const add = await page.$('.add-button-input') || await page.$('button:has-text("出欠を入力")');
  if (add) await add.click().catch(() => {});
  await page.waitForSelector('#f_name', { timeout: 8000 });
  await page.fill('#f_name', displayName);

  const marks = {};
  for (const d of decisions) {
    marks[d.candidate.index] = d.mark;
    const alt = `${d.candidate.label}_${MARK_NAME[d.mark]}`;
    try {
      await page.getByAltText(alt, { exact: true }).click({ timeout: 8000 });
    } catch (e) {
      console.error(`chousei: could not set ${d.mark} for「${d.candidate.label}」: ${e.message.split('\n')[0]}`);
    }
  }

  const reviewUrl = url; // 調整さんは名前リンクをクリックしてその場で編集
  if (dryRun) return { submitted: false, reviewUrl, marks, note: 'dry-run: 未送信（マーク設定のみ）' };

  await page.getByRole('button', { name: '入力する', exact: true }).click();
  await page.waitForTimeout(2500);
  return { submitted: true, reviewUrl, marks, note: '送信完了' };
}
