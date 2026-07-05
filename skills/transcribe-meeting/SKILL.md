---
name: transcribe-meeting
description: 会議・打ち合わせの録音ファイルから議事録を作りたいとき（「文字起こしして」「議事録にして」等）に使うスキル。話者名付きトランスクリプト・ケバ取り版・凝縮版の3ファイルを自動生成する。
---

# 会議録音 → 議事録3点セット

音声ファイル1つから以下の3ファイルを自動生成するスキル。すべて音声ファイルと同じフォルダに出力する。

| ファイル | 内容 |
|---------|------|
| `<stem>_transcript.txt` | 話者名付きトランスクリプト（原文） |
| `<stem>_verbatim.txt` | ケバ取り版（フィラー除去・全内容保持） |
| `<stem>_summary.md` | 凝縮版（重複排除・小見出し付き段落再構成） |

**このSKILL.mdが置かれているディレクトリを基準に、`scripts/audio-transcribe.py` を実行すること。**

## 使い方

```
/transcribe-meeting
```

引数なしで起動し、対話形式で情報を収集して処理を進める。

## Step 1: 情報収集

以下の情報をユーザーから収集する。

| 項目 | 必須 | 説明 |
|------|------|------|
| 音声ファイルパス | ○ | `.m4a` / `.mp3` / `.wav` 等 |
| 発表者リスト（発表順） | △ | 苗字のみ。省略時は話者A/B のまま |
| 質問者氏名 | △ | 発表者リストを省略した場合は不要 |
| スライドファイル | △ | PDF 推奨。話者推定精度が上がる |

出力先は音声ファイルと同じフォルダに固定（確認不要）。情報が揃ったら確認なしで処理を開始する。

## Step 2: 文字起こし

GEMINI_API_KEY が未設定なら「初回セットアップ」を先に案内する。

PPT ファイルが渡された場合は先に PDF 変換を試みる：

```bash
libreoffice --headless --convert-to pdf --outdir /tmp/ <ppt_file>
```

文字起こしを実行する（音声ファイルを丸ごと送信→品質不良時に自動分割）：

```bash
python3 <このSKILL.mdのディレクトリ>/scripts/audio-transcribe.py \
    <audio_file> --output <stem>_transcript.txt
```

## Step 3: 話者ラベルの整形

Gemini が話者名と発言内容を別行に分けることがある。以下のスクリプトで1行に統合する。`speaker_only` の正規表現には Step 1 で収集した実際の発表者名・質問者名を組み込む（ハードコードしない）。

```python
import re
path = '<stem>_transcript.txt'
with open(path, encoding='utf-8') as f:
    lines = f.readlines()
# 例: 発表者=["田中","鈴木"]、質問者="佐藤" の場合
names = ["田中", "鈴木", "佐藤"]  # Step 1 で収集した実際の名前に置き換える
speaker_only = re.compile(r'^(話者[A-Z]|' + '|'.join(names) + r'|[^\s:]{1,6}):\s*$')
result = []
i = 0
while i < len(lines):
    if speaker_only.match(lines[i]) and i + 1 < len(lines):
        name = lines[i].rstrip()
        content = lines[i + 1].rstrip('\n')
        result.append(f"{name} {content}\n")
        i += 2
    else:
        result.append(lines[i])
        i += 1
with open(path, 'w', encoding='utf-8') as f:
    f.writelines(result)
```

## Step 4: 話者推定・置換

発表者リストが提供された場合のみ実施。省略された場合はこの Step をスキップする。

スライドと文字起こしを読み込み、各チャンク（`## Part N`）の 話者A/B と実際の発表者を対応づける。

推定の手がかり（優先順）：
1. 明示的な呼びかけ — 「○○先生？」のやりとり
2. スライド内容との照合 — 研究テーマ・薬剤名・固有名詞
3. 第三者呼称 — 「○○さんと一緒に」と言えばその人は○○ではない
4. 人称・文体 — 「私の研究は」→ 発表者、「どういう病態？」→ 質問者

各パートの対応が決まったら Python で一括置換し、Part ヘッダーと区切りを除去する：

```python
import re
PART_MAPPING = {
    # 例: 1: {'話者A': '田中', '話者B': '鈴木'},
}
path = '<stem>_transcript.txt'
with open(path, encoding='utf-8') as f:
    content = f.read()
parts = re.split(r'(?=## Part \d+)', content)
result = []
for section in parts:
    m = re.match(r'## Part (\d+)', section)
    if m:
        mapping = PART_MAPPING.get(int(m.group(1)), {})
        for speaker, name in mapping.items():
            section = section.replace(f'{speaker}:', f'{name}:')
    result.append(section)
content = ''.join(result)
content = re.sub(r'\n*---\n*', '\n', content)
content = re.sub(r'\n*## Part \d+ — [^\n]+\n*', '\n', content)
content = content.strip() + '\n'
with open(path, 'w', encoding='utf-8') as f:
    f.write(content)
```

確信度が低い箇所は `[要確認: 推定 ○○]` と残す。

## Step 5: ケバ取り版・凝縮版

`scripts/audio-transcribe.py` が文字起こし完了後に自動で `<stem>_verbatim.txt`・`<stem>_summary.md` を生成する（Step 4 で話者置換をした場合は、置換後の内容で再生成すること）。

## Step 6: 完了報告

3ファイルが生成されたことを確認し、以下を報告する：

- 各ファイルのパスと行数
- 話者対応表（Step 4 を実施した場合）
- `[要確認]` マークがある場合はその箇所

```bash
open <stem>_transcript.txt
open <stem>_verbatim.txt
open <stem>_summary.md
```

## 初回セットアップ

依存パッケージ：

```bash
pip3 install google-genai
```

Gemini APIキーの取得と設定：

1. Google アカウントで [Google AI Studio](https://aistudio.google.com/apikey) にアクセスし「Create API key」
2. 表示されたキー（`AIza...`）を環境変数に設定：`export GEMINI_API_KEY="..."`（`~/.zshrc` 等に追記して永続化）
3. または `~/.config/claude-toolkit/gemini-api-key` にキーだけを書いたファイルを置く（環境変数が未設定の場合のフォールバックとして読まれる）

音声分割には `ffmpeg`／`ffprobe` が必要（`brew install ffmpeg`）。GUI選択モード（`--gui`）を使う場合は `tkinter` が必要（多くのPython配布に同梱）。
