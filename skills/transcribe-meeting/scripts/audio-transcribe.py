#!/usr/bin/env python3
"""音声を Gemini で文字起こしする。

使い方:
  audio-transcribe.py <音声ファイル>          # 単一ファイルで送信、品質不良なら自動分割
  audio-transcribe.py <_parts/ ディレクトリ>  # 分割済みチャンクをそのまま処理
  audio-transcribe.py <音声ファイル> --split   # 最初から分割モード
"""

import argparse, os, re, subprocess, sys, time
from pathlib import Path
from google import genai
from google.genai import errors, types


def generate_with_retry(client, max_attempts: int = 5, **kwargs):
    """generate_content を一時的なサーバーエラー（503/429等）でリトライする。"""
    for attempt in range(1, max_attempts + 1):
        try:
            return client.models.generate_content(**kwargs)
        except (errors.ServerError, errors.ClientError) as e:
            transient = getattr(e, "code", None) in (429, 500, 503)
            if not transient or attempt == max_attempts:
                raise
            wait = min(60, 5 * 2 ** (attempt - 1))
            print(f"\n  一時的なエラー（{e.code}）。{wait}秒後にリトライします... ({attempt}/{max_attempts})",
                  end="", flush=True)
            time.sleep(wait)


def _load_api_key_from_config() -> str:
    """~/.config/claude-toolkit/gemini-api-key からキーを読む（セットアップスクリプトが保存する場所）。"""
    config_file = Path.home() / ".config" / "claude-toolkit" / "gemini-api-key"
    if config_file.exists():
        return config_file.read_text(encoding="utf-8").strip()
    return ""


def _run_gui() -> tuple:
    """tkinter でファイル・出力先を選択し (audio_path, output_path) を返す。"""
    import tkinter as tk
    from tkinter import filedialog

    root = tk.Tk()
    root.withdraw()
    root.lift()

    audio = filedialog.askopenfilename(
        title="文字起こしする音声ファイルを選択してください",
        filetypes=[
            ("音声ファイル", "*.m4a *.mp3 *.wav *.aac *.ogg *.flac"),
            ("すべてのファイル", "*.*"),
        ],
    )
    if not audio:
        root.destroy()
        sys.exit("ファイルが選択されませんでした。")

    out_dir = filedialog.askdirectory(
        title="保存先フォルダを選択してください（キャンセルで音声ファイルと同じ場所）",
    )
    root.destroy()

    stem = Path(audio).stem
    folder = out_dir if out_dir else str(Path(audio).parent)
    output = str(Path(folder) / f"{stem}_transcript.txt")
    return audio, output


PROMPT = """この音声ファイルを文字起こししてください。
- 話者が複数いる場合は「話者A:」「話者B:」のように区別する
- 聞き取れない部分は [不明] と記載する
- 相槌・フィラー（「えー」「あの」等）は適宜省略して読みやすくする
- 出力は文字起こしテキストのみ（説明文不要）"""

AUDIO_SUFFIXES = {".m4a", ".mp3", ".wav", ".aac", ".ogg", ".flac"}

AUDIO_MIME_TYPES = {
    ".m4a": "audio/mp4",
    ".mp3": "audio/mpeg",
    ".wav": "audio/wav",
    ".aac": "audio/aac",
    ".ogg": "audio/ogg",
    ".flac": "audio/flac",
}

VERBATIM_PROMPT = """以下の会議文字起こしから、フィラー（えー、あのー、そのー、えっと、あの、まあ（文頭の意味のない使用）、なんか（意味のない使用）など）と明らかな言い淀み（同じ語の直後の繰り返し）のみを除去してください。

ルール：
- フィラーと言い淀み以外の内容は一切省略しない
- 話者ラベル（「話者A:」等、または実名に置換済みの場合はその名前）と発言順序を保持する
- 各発言は「話者名: 発言内容」の1行形式を維持する
- 出力は処理後のテキストのみ（説明文不要）

---
{text}"""

CONDENSED_PROMPT = """以下の会議文字起こしを凝縮してください。

ルール：
- 発言の本質（事実・意見・意思決定・背景）を完全に保ちつつ、重複や冗長な表現を排除する
- 具体的な数値・固有名詞・技術的課題・提案内容は省略厳禁
- 口語特有の繰り返し・言い直し・無意味な相槌・冗長な説明を削ぎ落とし、事務的で洗練された文章に再構成する
- 断片的な発言を文脈ごとに一貫性のある段落として統合する（発言者が混在してよい）
- 話題の切り替わりごとに ## レベルの小見出しを付ける
- 話者名は段落冒頭または文中で自然に示す（例：「田中より：...」「鈴木が指摘：...」）
- 意味のない相槌のみの行は削除する
- 出力はMarkdownのみ（説明文不要）

---
{text}"""


def upload_and_transcribe(client, path: Path) -> str:
    print(f"  アップロード中: {path.name}", end="", flush=True)
    # ファイル名に非ASCII文字（日本語等）が含まれると、google-genai がアップロード用の
    # HTTPヘッダーに生のファイル名をセットしてしまい ASCII エンコードに失敗するため、
    # パス文字列ではなくファイルオブジェクトを渡してこの経路を回避する。
    mime_type = AUDIO_MIME_TYPES.get(path.suffix.lower(), "application/octet-stream")
    with open(path, "rb") as fh:
        uploaded = client.files.upload(
            file=fh,
            config=types.UploadFileConfig(mime_type=mime_type, display_name=path.name),
        )

    # ファイルが ACTIVE になるまで待機（大きなファイルは時間がかかる）
    print(" → 待機中", end="", flush=True)
    for _ in range(60):
        f = client.files.get(name=uploaded.name)
        if f.state.name == "ACTIVE":
            break
        print(".", end="", flush=True)
        time.sleep(3)
    else:
        client.files.delete(name=uploaded.name)
        raise RuntimeError(f"タイムアウト: {path.name} が ACTIVE になりませんでした")

    print(" → 文字起こし中...", end="", flush=True)
    response = generate_with_retry(
        client,
        model="gemini-2.5-flash",
        contents=[PROMPT, f],
    )
    client.files.delete(name=uploaded.name)
    print(" 完了")
    return response.text


def check_quality(text: str) -> tuple[bool, str]:
    """文字化け検出。(ok, reason) を返す。"""
    # 同一文字が 10 回以上連続（「あああああ...」パターン）
    m = re.search(r'(.)\1{9,}', text)
    if m:
        sample = m.group(0)[:20]
        return False, f"同一文字の連続を検出: {sample!r}"

    # 3 文字以下の短行が全行の 50% 超かつ 20 行以上
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    if len(lines) > 20:
        short = sum(1 for l in lines if len(l) <= 3)
        ratio = short / len(lines)
        if ratio > 0.5:
            return False, f"短行が {short}/{len(lines)} 行 ({ratio:.0%}) を占める"

    return True, ""


def split_audio(audio: Path, chunk_minutes: int) -> Path:
    """ffmpeg で分割し、_parts/ ディレクトリを返す。"""
    parts_dir = audio.parent / f"{audio.stem}_parts"
    parts_dir.mkdir(exist_ok=True)
    print(f"音声を {chunk_minutes} 分チャンクに分割中: {audio.name} → {parts_dir.name}/")
    subprocess.run([
        "ffmpeg", "-i", str(audio),
        "-f", "segment", "-segment_time", str(chunk_minutes * 60),
        "-c", "copy", "-reset_timestamps", "1", "-loglevel", "error",
        str(parts_dir / f"{audio.stem}_part%02d{audio.suffix}"),
    ], check=True)
    chunks = sorted(parts_dir.glob(f"{audio.stem}_part*{audio.suffix}"))
    for c in chunks:
        print(f"  {c.name}  ({c.stat().st_size / 1e6:.1f} MB)")
    return parts_dir


def transcribe_chunks(client, parts_dir: Path) -> str:
    """チャンクを順次文字起こしして Part ヘッダー付きで結合する。"""
    chunks = sorted(
        f for f in parts_dir.iterdir()
        if f.suffix in AUDIO_SUFFIXES and "_part" in f.name
    )
    if not chunks:
        raise FileNotFoundError(f"音声ファイルが見つかりません: {parts_dir}")

    print(f"{len(chunks)} チャンクを処理します")
    parts = []
    for i, chunk in enumerate(chunks):
        print(f"[{i + 1}/{len(chunks)}]", end=" ")
        text = upload_and_transcribe(client, chunk)
        parts.append(f"## Part {i + 1} — {chunk.name}\n\n{text}")
    return "\n\n---\n\n".join(parts)


def main():
    p = argparse.ArgumentParser(
        description="音声を Gemini で文字起こし（単一ファイル優先、品質不良時は自動分割）"
    )
    p.add_argument("audio", nargs="?", help="音声ファイル（.m4a/.mp3/.wav 等）または _parts/ ディレクトリ")
    p.add_argument("--output", "-o", help="出力ファイルパス（省略時は自動命名）")
    p.add_argument("--api-key", default=os.environ.get("GEMINI_API_KEY") or _load_api_key_from_config())
    p.add_argument("--chunk-minutes", type=int, default=10, metavar="N",
                   help="分割時のチャンク長（分）。デフォルト: 10")
    p.add_argument("--split", action="store_true",
                   help="最初から分割モードで実行（品質チェックをスキップ）")
    p.add_argument("--gui", action="store_true",
                   help="ファイル選択ダイアログを表示して実行（Windows / GUI環境向け）")
    a = p.parse_args()

    if a.gui or not a.audio:
        a.audio, a.output = _run_gui()

    if not a.api_key:
        sys.exit("エラー: Gemini API キーが未設定。環境変数 GEMINI_API_KEY を設定するか、"
                 "~/.config/claude-toolkit/gemini-api-key にキーを保存してください。"
                 "（取得方法: https://aistudio.google.com/apikey）")

    target = Path(a.audio).expanduser().resolve()
    client = genai.Client(api_key=a.api_key)

    # 出力パスを決定
    if a.output:
        out = Path(a.output).expanduser().resolve()
    elif target.is_dir():
        stem = target.stem.removesuffix("_parts")
        out = target.parent / f"{stem}_transcript.txt"
    else:
        out = target.parent / f"{target.stem}_transcript.txt"

    # ── ディレクトリが渡された場合: チャンクモード直行 ──────────────────
    if target.is_dir():
        print(f"チャンクディレクトリ: {target}")
        result = transcribe_chunks(client, target)
        out.write_text(result, encoding="utf-8")
        print(f"\n文字起こし完了: {out}")
        return

    # ── 単一ファイルの場合 ──────────────────────────────────────────────
    if not target.exists():
        sys.exit(f"エラー: ファイルが見つかりません: {target}")
    if target.suffix not in AUDIO_SUFFIXES:
        sys.exit(f"エラー: 対応していない形式: {target.suffix}")

    if a.split:
        # --split フラグ: 最初から分割
        print(f"分割モード: {target.name}")
        parts_dir = split_audio(target, a.chunk_minutes)
        result = transcribe_chunks(client, parts_dir)
    else:
        # デフォルト: 単一ファイルで送信 → 品質チェック → 必要なら自動分割
        print(f"単一ファイルモード: {target.name}")
        text = upload_and_transcribe(client, target)
        ok, reason = check_quality(text)

        if ok:
            result = text
            print("品質チェック: OK")
        else:
            print(f"\n⚠ 品質チェック失敗 — {reason}")
            print("自動で分割モードに切り替えます...")
            parts_dir = split_audio(target, a.chunk_minutes)
            result = transcribe_chunks(client, parts_dir)

    out.write_text(result, encoding="utf-8")
    print(f"\n文字起こし完了: {out}")

    # ── ケバ取り版・凝縮版を自動生成 ─────────────────────────────
    file_stem = target.stem if target.is_file() else target.stem.removesuffix("_parts")
    verbatim_out = out.parent / f"{file_stem}_verbatim.txt"
    condensed_out = out.parent / f"{file_stem}_summary.md"

    print("\nケバ取り版を生成中...", end="", flush=True)
    verbatim_text = generate_with_retry(
        client, model="gemini-2.5-flash", contents=VERBATIM_PROMPT.format(text=result),
    ).text
    verbatim_out.write_text(verbatim_text, encoding="utf-8")
    print(f" 完了: {verbatim_out.name}")

    print("凝縮版を生成中...", end="", flush=True)
    condensed_text = generate_with_retry(
        client, model="gemini-2.5-flash", contents=CONDENSED_PROMPT.format(text=result),
    ).text
    condensed_out.write_text(condensed_text, encoding="utf-8")
    print(f" 完了: {condensed_out.name}")

    print(f"\n生成ファイル:")
    print(f"  {out}")
    print(f"  {verbatim_out}")
    print(f"  {condensed_out}")


if __name__ == "__main__":
    main()
