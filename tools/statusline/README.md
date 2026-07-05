# statusline

Claude Codeのターミナル下部に、現在のモデル・コンテキスト使用率・レート制限・作業フォルダ・ログインアカウントをリアルタイム表示するステータスライン。

```
  Sonnet 5  ctx ○ 10%  5h(14:40) ○ 1%  7d(4/29) ○ 12%  my-project  work
```

| 項目 | 内容 |
|---|---|
| `Sonnet 5` | 現在使用中のモデル名 |
| `ctx ○ 10%` | コンテキストウィンドウの使用率 |
| `5h(14:40) ○ 1%` | 5時間レート制限の使用率（リセット時刻） |
| `7d(4/29) ○ 12%` | 7日間レート制限の使用率（リセット日） |
| `my-project` | 現在の作業フォルダ名（basename） |
| `work` | 現在のClaudeログインアカウント（`~/.claude/.current-account` 等から取得したメールをラベル変換） |

インジケーター（○◔◑◕●）は使用率に応じて変化し、色も緑→黄→赤のグラデーションで変わる。

## セットアップ

Python標準ライブラリのみ使用（追加インストール不要）。日付フォーマット・キャッシュ更新方式はスクリプト内で自動的にOS判定するため、Mac/Windowsとも同じファイルでよい。

**Mac / Linux：**

```bash
ln -sf <このディレクトリ>/statusline.py ~/.claude/statusline.py
chmod +x ~/.claude/statusline.py
```

**Windows（PowerShell、Windows Terminal推奨）：**

```powershell
Copy-Item "<このディレクトリ>\statusline.py" "$env:USERPROFILE\.claude\statusline.py"
```

`~/.claude/settings.json`（Windowsは `%USERPROFILE%\.claude\settings.json`）のトップレベルに `statusLine` キーを追加する（既存のキーは保持）：

```json
{
  "statusLine": {
    "type": "command",
    "command": "python3 ~/.claude/statusline.py"
  }
}
```

Windowsで `python3` コマンドがない場合は `"command": "python ~/.claude/statusline.py"` にする。

## アカウント表示のラベル設定

任意設定。

`~/.claude/.account-labels.json` にメール→表示ラベルのマッピングを定義すると、フルアドレスの代わりに短いラベルが表示される：

```json
{
  "example@work-domain.example.com": "work",
  "example@gmail.com": "personal"
}
```

マッピングにないメールは `@` 前の部分をそのまま表示する。

## 動作しない場合のチェックリスト

- `~/.claude/statusline.py` が存在するか（Mac/Linuxは実行権限も）：`ls -la ~/.claude/statusline.py`
- Python 3 が使えるか：`python3 --version`（Windowsは `python --version` または `py --version`）
- `settings.json` が正しい JSON か：`python3 -m json.tool ~/.claude/settings.json`
- ターミナルがステータスライン表示に対応しているか（Mac: iTerm2推奨。Windows: Windows Terminal必須、cmd.exeは非対応）
- 記号が文字化けする場合、ターミナルのフォント設定でNerd Fontまたは等幅フォントを使用する
