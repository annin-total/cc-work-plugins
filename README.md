# cc-work-plugins

業務で使う Claude Code の小さなツールを集めたプラグインマーケットプレイス。収録ツールはすべて Windows と macOS で動くことを目標にしている（[CONVENTIONS.md](CONVENTIONS.md)）。

## 導入

Claude Code の中では `/plugin`、シェルでは `claude plugin` で操作する。

| 操作 | Claude Code の中 | シェル |
| --- | --- | --- |
| マーケットプレイスの追加 | `/plugin marketplace add annin-total/cc-work-plugins` | `claude plugin marketplace add annin-total/cc-work-plugins` |
| プラグインの導入 | `/plugin install hearing@cc-work-plugins` | `claude plugin install hearing@cc-work-plugins` |
| 更新 | `/plugin marketplace update cc-work-plugins` の後、`/plugin` の画面から更新する | `claude plugin marketplace update cc-work-plugins` → `claude plugin update hearing@cc-work-plugins` |
| 削除 | `/plugin uninstall hearing@cc-work-plugins` | `claude plugin uninstall hearing@cc-work-plugins` |

導入・更新は、次に起動したセッションから効く。

## 収録プラグイン

### hearing

この端末の Claude Code の履歴から利用の重さ（モデル・effort・トークン量・頻度・セッションの長さなど）をおおまかに推定し、本人へのヒアリングと合わせた調書（Markdown 1 ファイル）を作る。金額は出さない。設定は変更しない。

- 前提: Python 3.9 以上（`python3` → `python` → `py -3` の順に探す）
- 使い方: `/hearing:hearing-cost [日数|開始日..終了日] [cleanup]`（既定は直近 30 日）。明示的に呼んだときだけ動く
- 出力: 起動したディレクトリの `hearing-cost/<日時>/` に調書を置く（`hearing-cost/.gitignore` で git から外す）。調書は自動送信しない
- 詳細: [SKILL.md](plugins/hearing/skills/hearing-cost/SKILL.md)、評価手順は [tests/hearing/README.md](tests/hearing/README.md)
- **Windows・macOS とも実機での確認は未完了**（チェックリストは評価手順にある。CI の自動テストは両 OS で実行している）

### retitle

作業の趣旨が変わるたびに、セッションタイトルを「要約 · ブランチ」へ付け直す hook（`UserPromptSubmit`）と、手動で付け直す `/retitle [要約]` を導入する。

- 前提: Python 3.8 以上で、仮想環境（venv）の外にあるもの（hook はこの Python で起動するよう登録される）。`PATH` に `claude` があること。Claude Code 2.1.139 以上
- 導入: プラグインを入れた後、`/retitle:setup-retitle` を呼ぶか「セッション名を自動で付け直す仕組みを入れて」と頼む。導入スクリプトが次を行う
  - 設定ディレクトリ（`CLAUDE_CONFIG_DIR` か `~/.claude`）の `settings.json` に hook を 1 件登録する（書き換え前に `settings.json.bak-retitle-<日時>` を残す）
  - hook 本体を `hooks/retitle.py`、`/retitle` を `skills/retitle/` に置く
- 費用と送信: 15 字以上の送信のたびに、利用者自身の認証で `claude -p --model haiku` を 1 回呼ぶ（本文の先頭 2000 字を送る）。状態は `~/.cache/cc-retitle/` に溜まる
- 更新: プラグインを更新しても、導入済みの hook と `/retitle` は変わらない。更新後にもう一度 `/retitle:setup-retitle` を呼ぶ
- 削除: **プラグインを削除する前に**、`/retitle:setup-retitle` で削除を頼む（hook と `/retitle` を除く）。プラグインを削除しても、登録済みの hook は残る。`~/.cache/cc-retitle/` は自動では消えない
- 詳細: [SKILL.md](plugins/retitle/skills/setup-retitle/SKILL.md)
- **Windows 実機では未確認**（CI の自動テストは Windows でも実行している）

## 対応 OS

Windows・macOS。CI（GitHub Actions）で両 OS × Python 3.9 / 3.13 のテストを実行する。実機での確認状況は各プラグインの節に書く。

## 規約

収録ツールの作り方と変更の手順は [CONVENTIONS.md](CONVENTIONS.md) に従う。

## ライセンス

[MIT](LICENSE)
