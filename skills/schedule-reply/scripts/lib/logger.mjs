// Terminal summary + persistent log file.
import { appendFileSync, mkdirSync } from 'node:fs';
import { dirname } from 'node:path';

const hm = (t) => (t.endsWith(':00') ? String(+t.slice(0, 2)) : t); // "08:00"->"8", "10:30"->"10:30"

export function candidateLabel(c) {
  const d = new Date(`${c.date}T12:00:00+09:00`);
  const [, m, day] = c.date.split('-');
  const jwd = new Intl.DateTimeFormat('ja-JP', { timeZone: 'Asia/Tokyo', weekday: 'short' }).format(d);
  const t = c.start ? ` ${hm(c.start)}${c.end ? '-' + hm(c.end) : ''}` : '';
  return `${+m}/${+day}(${jwd})${t}`;
}

export function printSummary({ tool, subject, rows, outcome }) {
  const lines = [];
  lines.push(`ツール: ${tool} | 候補数: ${rows.length} | 件名: ${subject}`);
  lines.push(`[候補日時]              [判定]  [根拠]`);
  for (const r of rows) {
    lines.push(`${r.label.padEnd(22, ' ')}${r.mark}      ${r.reason}`);
  }
  for (const l of outcome) lines.push(`→ ${l}`);
  const block = lines.join('\n');
  process.stdout.write('\n' + block + '\n');
  return block;
}

export function makeFileLogger(logPath) {
  mkdirSync(dirname(logPath), { recursive: true });
  return (obj) => {
    const line = JSON.stringify({ ts: new Date().toISOString(), ...obj });
    appendFileSync(logPath, line + '\n');
  };
}
