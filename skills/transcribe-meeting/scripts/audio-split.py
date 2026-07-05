#!/usr/bin/env python3
"""音声ファイルを ~10 分チャンクに分割する（Gemini 文字起こし用）"""

import argparse, json, math, subprocess, sys
from pathlib import Path


def main():
    p = argparse.ArgumentParser(description="音声を一定時間ごとに分割")
    p.add_argument("input")
    p.add_argument("--minutes", type=int, default=10, help="チャンク長（分）。デフォルト: 10")
    p.add_argument("--output-dir")
    a = p.parse_args()

    src = Path(a.input).expanduser().resolve()
    if not src.exists():
        sys.exit(f"エラー: {src}")

    dst = Path(a.output_dir).expanduser().resolve() if a.output_dir else src.parent / f"{src.stem}_parts"
    dst.mkdir(parents=True, exist_ok=True)

    r = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", str(src)],
        capture_output=True, text=True, check=True,
    )
    secs = float(json.loads(r.stdout)["format"]["duration"])
    n = math.ceil(secs / (a.minutes * 60))
    print(f"{src.name}  {secs/60:.1f}分 → {n}チャンク → {dst}/")

    subprocess.run([
        "ffmpeg", "-i", str(src),
        "-f", "segment", "-segment_time", str(a.minutes * 60),
        "-c", "copy", "-reset_timestamps", "1", "-loglevel", "error",
        str(dst / f"{src.stem}_part%02d{src.suffix}"),
    ], check=True)

    for f in sorted(dst.glob(f"{src.stem}_part*{src.suffix}")):
        print(f"  {f.name}  ({f.stat().st_size/1e6:.1f} MB)")


if __name__ == "__main__":
    main()
