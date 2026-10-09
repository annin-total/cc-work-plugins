# 規約

**収録するツールは、すべて Windows と macOS の両方で動くこと。**以下はそのための具体則。

## スクリプト

- Python 3 の標準ライブラリだけで書く。最低版は 3.9（CI で確認する最低版）。シェルスクリプト（`.sh`・`.ps1`）に依存しない
- `open()`・`read_text()`・`write_text()`・`subprocess` には `encoding="utf-8"` を明示する（Windows の既定は cp932）
- パスは `pathlib` で扱う。区切り文字を文字列で組み立てない
- `find`・`grep`・`sed` などの外部コマンドを呼ばない。Python で書く
- `subprocess.CREATE_NO_WINDOW` など Windows だけにある定数は `getattr(subprocess, "CREATE_NO_WINDOW", 0)` のように参照する

## Python の起動

起動名は OS で違う。Windows には `python3` が無いことがあり、`python` が Microsoft Store を開くだけのスタブのこともある。

- スキルから呼ぶときは `python3` → `python` → `py -3` の順に `--version` を試し、`Python 3.` を返したものを使う
- hook のように毎回起動するものは、導入時に見つけた Python の絶対パスを登録してもよい
- `hooks/hooks.json` から直接起動する書き方と制約は [templates/README.md](templates/README.md) にある

## hook

- `hooks/hooks.json` に置く hook は OS ごとの分岐を書けない。両 OS で同じ記述が通るようにする
- exec 形式（`args` に引数を並べる）ならシェルを経由しないので、クォートやシェルの違いの影響を受けない

## テスト

- テストは `tests/<plugin>/` に置き、`python -m unittest discover -s tests/<plugin>` で通す。プラグインの中には置かない（配布物に入るため）
- テストが 0 件のディレクトリは検証で失敗になる
- CI（`.github/workflows/test.yml`）は macOS・Windows の両方で `scripts/validate.py` を実行する
- Windows 実機で確認していない点は、そのプラグインの README に明記する

## プラグインの構成

- 雛形は `templates/plugin/`（手順は [templates/README.md](templates/README.md)）
- `plugins/<name>/.claude-plugin/plugin.json` に `name`・`version`・`description`・`author`・`license` を書く
- `.claude-plugin/marketplace.json` の `plugins` に登録する
- `python scripts/validate.py` がすべて PASS すること（`claude plugin validate --strict`・marketplace.json との整合・必須項目・全テストを確かめる）

- `plugins/<name>/README.md` に前提・使い方・注意を書き、ルートの README の「収録プラグイン」に 1 行で登録する。プラグインの README は配布物に入るので、プラグインの外へのリンクは GitHub の絶対 URL にする

## 変更の手順

- `main` へ直接 push しない。変更は PR を通し、CI が通ってからマージする
- プラグインの中身を変えたら `plugin.json` の `version` を上げる（上げないと利用者に届かない）
