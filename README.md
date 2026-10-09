# cc-work-plugins

業務で使う Claude Code の小さなツールを集めたプラグインマーケットプレイス。収録ツールはすべて Windows と macOS で動くことを目標にしている（[CONVENTIONS.md](CONVENTIONS.md)）。

## 導入

Claude Code の中では `/plugin`、シェルでは `claude plugin` で操作する。`<name>` は下の「収録プラグイン」の名前。

| 操作 | Claude Code の中 | シェル |
| --- | --- | --- |
| マーケットプレイスの追加 | `/plugin marketplace add annin-total/cc-work-plugins` | `claude plugin marketplace add annin-total/cc-work-plugins` |
| プラグインの導入 | `/plugin install <name>@cc-work-plugins` | `claude plugin install <name>@cc-work-plugins` |
| 更新 | `/plugin marketplace update cc-work-plugins` の後、`/plugin` の画面から更新する | `claude plugin marketplace update cc-work-plugins` → `claude plugin update <name>@cc-work-plugins` |
| 削除 | `/plugin uninstall <name>@cc-work-plugins` | `claude plugin uninstall <name>@cc-work-plugins` |

導入・更新は、次に起動したセッションから効く。

## 収録プラグイン

| 名前 | 内容 |
| --- | --- |
| [hearing](plugins/hearing/README.md) | Claude Code の履歴から利用の重さを推定し、本人へのヒアリングと合わせた調書を作る |
| [retitle](plugins/retitle/README.md) | 作業の趣旨が変わるたびにセッションタイトルを「要約 · ブランチ」へ付け直す hook を導入する |

前提・使い方・費用・更新と削除の注意は、各プラグインの README に書く。

## 対応 OS

Windows・macOS。CI（GitHub Actions）で両 OS × Python 3.9 / 3.13 のテストを実行する。実機での確認状況は各プラグインの README に書く。

## 規約

収録ツールの作り方と変更の手順は [CONVENTIONS.md](CONVENTIONS.md) に従う。

## ライセンス

[MIT](LICENSE)
