#!/usr/bin/env python3
"""Pattern 3: Ring meter - pie-like circle segments"""
import json, sys, os, subprocess, time
from datetime import datetime

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

data = json.load(sys.stdin)

R = '\033[0m'
DIM = '\033[2m'
BOLD = '\033[1m'

RINGS = ['○', '◔', '◑', '◕', '●']

def gradient(pct):
    if pct < 50:
        r = int(pct * 5.1)
        return f'\033[38;2;{r};200;80m'
    else:
        g = int(200 - (pct - 50) * 4)
        return f'\033[38;2;255;{max(g, 0)};60m'

def ring(pct):
    idx = min(int(pct / 25), 4)
    return RINGS[idx]

def fmt_ctx(pct):
    p = round(pct)
    return f'{DIM}ctx{R} {gradient(pct)}{ring(pct)} {p}%{R}'

def fmt_rate(label, pct, resets_at, time_fmt):
    p = round(pct)
    if resets_at:
        reset_str = datetime.fromtimestamp(resets_at).strftime(time_fmt)
        label_str = f'{DIM}{label}({reset_str}){R}'
    else:
        label_str = f'{DIM}{label}{R}'
    return f'{label_str} {gradient(pct)}{ring(pct)} {p}%{R}'

model = data.get('model', {}).get('display_name', 'Claude')
# Remove "Claude " prefix if present for compactness
model = model.removeprefix('Claude ')
parts = [f'{BOLD}{model}{R}']

ctx = data.get('context_window', {}).get('used_percentage')
if ctx is not None:
    parts.append(fmt_ctx(ctx))

five_data = data.get('rate_limits', {}).get('five_hour', {})
five = five_data.get('used_percentage')
if five is not None:
    parts.append(fmt_rate('5h', five, five_data.get('resets_at'), '%H:%M'))

week_data = data.get('rate_limits', {}).get('seven_day', {})
week = week_data.get('used_percentage')
if week is not None:
    parts.append(fmt_rate('7d', week, week_data.get('resets_at'), '%-m/%-d'))

cwd = data.get('cwd') or data.get('workspace', {}).get('current_dir', '')
folder = os.path.basename(cwd) if cwd else '-'
parts.append(f'{BOLD}{folder}{R}')

CACHE_FILE = os.path.expanduser('~/.claude/.auth-cache')
LABELS_FILE = os.path.expanduser('~/.claude/.account-labels.json')
CACHE_TTL = 600  # 10分

def get_account_label():
    try:
        labels = json.load(open(LABELS_FILE))
    except (FileNotFoundError, json.JSONDecodeError):
        labels = {}

    # キャッシュが有効なら即返す
    try:
        if time.time() - os.path.getmtime(CACHE_FILE) < CACHE_TTL:
            email = open(CACHE_FILE).read().strip()
            return labels.get(email, email.split('@')[0] if email else '-')
    except FileNotFoundError:
        pass

    # キャッシュ期限切れ/なし → バックグラウンドで更新
    subprocess.Popen(
        ['sh', '-c',
         'claude auth status 2>/dev/null'
         ' | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get(\'email\',\'\'), end=\'\')"'
         ' > ~/.claude/.auth-cache'],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )

    # 古いキャッシュがあればそれを返す、なければ '-'
    try:
        email = open(CACHE_FILE).read().strip()
        return labels.get(email, email.split('@')[0] if email else '-')
    except FileNotFoundError:
        return '-'

parts.append(f'{DIM}{get_account_label()}{R}')

print('  '.join(parts), end='')
