# templates

新しいプラグインの雛形。`plugin/` をコピーし、名前を置き換えればそのまま 1 つのプラグインになる。

## 使い方

1. `templates/plugin/` を `plugins/<name>/` にコピーする
2. `my-plugin`（プラグイン名）・`my-skill`（スキル名とディレクトリ名）を置き換え、`TODO:` を埋める。要らない skill・hook は消す
3. `.claude-plugin/marketplace.json` の `plugins` に `{"name": "<name>", "source": "./plugins/<name>", "description": "..."}` を足し、ルートの README の「収録プラグイン」に 1 行足す
4. `tests/<name>/` に unittest を置く（0 件だと検証が落ちる）
5. `python scripts/validate.py` がすべて PASS することを確かめる

## hook の Python の起動

`hooks/hooks.json` はシェル形式で、`python3` → `python` → `py` の順に実行ファイルの有無を `command -v` で確かめ、最初に見つかったものでスクリプトを 1 回だけ実行する。見つからなければ stderr に書いて終了コード 1 で終わる（プロンプトは止めない）。

- Windows で Git Bash が無いと、Claude Code は hook を PowerShell で実行するため、この記述は動かない
- Windows では `python3`・`python` が Microsoft Store を開くだけのスタブのことがあり、それを掴むと hook は失敗する
