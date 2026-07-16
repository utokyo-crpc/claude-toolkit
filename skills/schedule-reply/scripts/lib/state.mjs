// Dedupe store: message ids we've already handled (belt-and-suspenders alongside
// the INBOX->Scheduling relabel, which is the primary re-detection guard).
import { readFileSync, appendFileSync, existsSync, mkdirSync } from 'node:fs';
import { dirname } from 'node:path';

export function loadProcessed(path) {
  const seen = new Set();
  if (!existsSync(path)) return seen;
  for (const line of readFileSync(path, 'utf8').split('\n')) {
    if (!line.trim()) continue;
    try { seen.add(JSON.parse(line).id); } catch {}
  }
  return seen;
}

export function markProcessed(path, id, meta = {}) {
  mkdirSync(dirname(path), { recursive: true });
  appendFileSync(path, JSON.stringify({ id, ts: new Date().toISOString(), ...meta }) + '\n');
}
