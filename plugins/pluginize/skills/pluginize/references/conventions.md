# プラグイン化の要点

対象リポジトリに規約文書があれば、そちらが優先する。ここは規約文書が無いときの拠り所と、判断に要る事実だけを置く。

## Windows と macOS の両方で動かす

- スクリプトは Python 3 の標準ライブラリで書く（最低版は 3.9 を目安）。`.sh`・`.ps1` に依存しない
- `open()`・`read_text()`・`write_text()`・`subprocess` には `encoding="utf-8"` を明示する。Windows の既定は cp932 で、日本語や絵文字で落ちる
- パスは `pathlib` で組む。`/` や `\` を文字列で連結しない
- `find`・`grep`・`sed`・`curl` などの外部コマンドを呼ばない。Python で書く（HTTP は `urllib`）
- 通知など OS 固有の機能（`osascript` など）しか手段が無いものは、`sys.platform` で分けた付加機能にとどめ、無い OS では静かに何もしない。OS によって機能が欠けることは利用者に確かめ、README に書く
- Windows だけの定数は `getattr(subprocess, "CREATE_NO_WINDOW", 0)` のように参照する
- ホームは `Path.home()`、設定ディレクトリは `CLAUDE_CONFIG_DIR` があればそれ、無ければ `~/.claude`、一時ディレクトリは `tempfile`

## 端末固有の値の置き換え

| 元の書き方 | 置き換え先 |
| --- | --- |
| プラグイン自身のファイルへの絶対パス | `${CLAUDE_PLUGIN_ROOT}`（hook の `command`・`args`）、スキルからは `${CLAUDE_SKILL_DIR}` |
| 状態・キャッシュの置き場所 | `${CLAUDE_PLUGIN_DATA}`（更新しても残り、削除で消える） |
| 作業中のプロジェクトのパス | hook の入力（stdin の `cwd`）か `CLAUDE_PROJECT_DIR` |
| 利用者ごとに違う値（社内の URL・チーム名など） | `plugin.json` の `userConfig`（下記） |
| ユーザー名・ホームの場所・Python の場所 | 実行時に検出する |

`userConfig` は、有効化のときに利用者へ入力を求める設定。キーは英数字と `_`。各項目に `type`（`string`・`number`・`boolean`・`directory`・`file`）・`title`・`description` が必須で、`default`・`required`・`sensitive` などを足せる（知らないキーがあるとプラグインが読み込まれない）。
hook には環境変数 `CLAUDE_PLUGIN_OPTION_<KEY>`（キーは大文字）で届く。exec 形式なら `args` に `${user_config.KEY}` も書けるが、シェル形式の `command` には書けない。

秘密の値（トークン・Webhook の URL・パスワードなど）はリポジトリに入れない。機能に要るなら `userConfig` の `sensitive: true` にして各利用者に入れてもらう（`settings.json` ではなく安全な保管先に入る）。

## hook の Python の起動

起動名は OS で違う。Windows には `python3` が無いことがあり、`python` が Microsoft Store を開くだけのスタブのこともある。

- `hooks/hooks.json` は OS ごとに分岐できない。両 OS で同じ記述が通る必要がある
- 対象リポジトリに hook の雛形があれば、その起動の書き方をそのまま使う。無ければ次のシェル形式が両 OS で通る（Windows は Git Bash があるとき）

  ```text
  for p in python3 python py; do if command -v "$p" >/dev/null 2>&1; then exec "$p" "${CLAUDE_PLUGIN_ROOT}/hooks/<script>.py"; fi; done; echo "<name>: Python が見つからない" >&2; exit 1
  ```

- Windows で Git Bash が無いと hook は PowerShell で実行され、上の書き方は動かない。確実に動かしたい hook は、導入スキル＋導入スクリプトで「見つけた Python の絶対パス」を exec 形式（`command` に実行ファイル、`args` に引数）で利用者の `settings.json` に登録する方式にする。代わりに、更新・削除の手順を利用者に負わせる
- スキルから同梱スクリプトを呼ぶときは `python3` → `python` → `py -3` の順に `--version` を試し、`Python 3.` を返したものを使う

## 取り込み方の選び方

- 既定は `hooks/hooks.json`。入れるだけで動き、更新も削除もプラグインの操作で済む
- 導入スクリプト方式を選ぶのは、Git Bash の無い Windows でも確実に動かしたいとき、プラグインの有効・無効と切り離したいときなど。理由を README に書く
- スキルは `skills/<name>/SKILL.md` にそのまま置く。呼び出しは `/<plugin>:<skill>` になる。本文中のパスは `${CLAUDE_SKILL_DIR}` からの相対にする

## プラグインの構成

- `plugins/<name>/.claude-plugin/plugin.json` に `name`・`version`・`description`・`author`・`license`
- `plugins/<name>/README.md` に前提・使い方・費用や送信先・Windows 実機での確認状況。配布物に入るので、プラグインの外へのリンクは絶対 URL にする
- マーケットプレイスの `.claude-plugin/marketplace.json` の `plugins` に `name`・`source`（`./plugins/<name>`）・`description` を足す。`name` は plugin.json・ディレクトリ名と揃える
- テストはプラグインの外（`tests/<name>/` など）に置く。配布物に入れない
- 中身を変えたら `version` を上げる。上げないと利用者に届かない
- 検証は対象リポジトリの検証スクリプトがあればそれ、無ければ `claude plugin validate <plugin のディレクトリ> --strict` とマーケットプレイスのルートでの同じコマンド。上流の検証はマニフェストしか見ないので、hook の実行とテストは別に確かめる
