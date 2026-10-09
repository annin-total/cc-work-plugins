# retitle

作業の趣旨が変わるたびに、セッションタイトルを「要約 · ブランチ」へ付け直す hook（`UserPromptSubmit`）と、手動で付け直す `/retitle [要約]` を導入する。

- 判定の結果は次の送信でタイトルに反映される。15 字未満の入力と `/` で始まる入力は判定しない。main・master のブランチ名は付けない
- 要約の先頭に作業ディレクトリ名（ハイフンを含むもの）が入ったら、後ろへ移して「要約 · ディレクトリ名 · ブランチ」にする

## 前提

- Python 3.8 以上で、仮想環境（venv）の外にあるもの（hook はこの Python で起動するよう登録される）
- `PATH` に `claude` があること
- Claude Code 2.1.139 以上

## 導入

```text
/plugin marketplace add annin-total/cc-work-plugins
/plugin install retitle@cc-work-plugins
```

マーケットプレイスを追加済みなら 1 行目は要らない。プラグインを入れただけでは hook は動かない。次に起動したセッションで `/retitle:setup-retitle` を呼ぶか、「セッション名を自動で付け直す仕組みを入れて」と頼む。導入スクリプトが次を行う。

- 設定ディレクトリ（`CLAUDE_CONFIG_DIR` か `~/.claude`）の `settings.json` に hook を 1 件登録する（書き換え前に `settings.json.bak-retitle-<日時>` を残す）
- hook 本体を `hooks/retitle.py`、`/retitle` を `skills/retitle/` に置く

hook は次に起動したセッションから確実に効く。

## 費用と送信

- 15 字以上の送信のたびに、利用者自身の認証で `claude -p --model haiku` を 1 回呼ぶ（本文の先頭 2000 字を送る）
- 状態は `~/.cache/cc-retitle/` に溜まる（macOS・Linux では所有者だけが読める権限にする）

## 更新と削除

- 更新: プラグインを更新しても、導入済みの hook と `/retitle` は変わらない。更新後にもう一度 `/retitle:setup-retitle` を呼ぶ
- 削除: **プラグインを削除する前に**、`/retitle:setup-retitle` で削除を頼む（hook と `/retitle` を除く）。プラグインを削除しても、登録済みの hook は残る。`~/.cache/cc-retitle/` は自動では消えない

## 動作確認の状況

Windows 実機では未確認。CI の自動テストは Windows でも実行している。

## 詳細

導入の手順とうまく動かないときの確認は [SKILL.md](skills/setup-retitle/SKILL.md) にある。
