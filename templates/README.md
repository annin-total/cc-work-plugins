# templates

新しいプラグインの雛形。`plugin/` をコピーし、名前を置き換えればそのまま 1 つのプラグインになる。

## 使い方

1. `templates/plugin/` を `plugins/<name>/` にコピーする
2. `my-plugin`（プラグイン名）・`my-skill`（スキル名とディレクトリ名）を置き換え、`TODO:` を埋める。要らない skill・hook・mod は消す
3. `.claude-plugin/marketplace.json` の `plugins` に `{"name": "<name>", "source": "./plugins/<name>", "description": "..."}` を足し、ルートの README の「収録プラグイン」に 1 行足す
4. `tests/<name>/` に unittest を置く（0 件だと検証が落ちる）
5. `python scripts/validate.py` がすべて PASS することを確かめる

## hook の Python の起動

`hooks/hooks.json` はシェル形式で、`python3` → `python` → `py` の順に実行ファイルの有無を `command -v` で確かめ、最初に見つかったものでスクリプトを 1 回だけ実行する。見つからなければ stderr に書いて終了コード 1 で終わる（プロンプトは止めない）。

- Windows で Git Bash が無いと、Claude Code は hook を PowerShell で実行するため、この記述は動かない
- Windows では `python3`・`python` が Microsoft Store を開くだけのスタブのことがあり、それを掴むと hook は失敗する

## mod（任意）

`hooks/register.ts` は mod（Claude Code の関数フック）の最小の例で、`hooks/hooks.json` の `modules` に書くとプラグインの有効化で読み込まれる。セッション開始でスラッシュコマンド `/my-plugin-hello` を登録し、実行されたら 1 行答える。書き方の正本は Claude Code 同梱の `plugin-authoring` スキル（`/plugin-authoring`）。

- 要らなければ `hooks/register.ts` と `hooks/hooks.json` の `modules` を消す。使うならコマンド名（`my-plugin-hello`）も置き換える
- テストは `tests/templates/mod/*.test.ts`。`tests/templates/test_mod.py` がプラグインの複製に入れて `claude plugin test` で走らせる（配布物に入れないため）

既知の制約（実測）:

- VS Code 拡張のパネルでは mod の UI（toast・バンド）が出ない
- managed settings のある端末や Team・Enterprise の利用者では、利用者側の mod に `classic.*` などが届かない
- git 型マーケットプレイスから入れた mod は cache の版ディレクトリから実行される。変えたら `version` を上げないと届かない
- フォルダ信頼の承認前は mod を読み込まない
