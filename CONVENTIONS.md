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

## hook

- `hooks/hooks.json` に置く hook は OS ごとの分岐を書けない。両 OS で同じ記述が通るようにする
- exec 形式（`args` に引数を並べる）ならシェルを経由しないので、クォートやシェルの違いの影響を受けない

## テスト

- テストは `tests/<plugin>/` に置き、`python -m unittest discover -s tests/<plugin>` で通す。プラグインの中には置かない（配布物に入るため）
- CI（`.github/workflows/test.yml`）の macOS・Windows の両方で通す
- Windows 実機で確認していない点は README の該当プラグインの節に明記する

## プラグインの構成

- `plugins/<name>/.claude-plugin/plugin.json` に `name`・`version`・`description`・`author`・`license` を書く
- `.claude-plugin/marketplace.json` の `plugins` に登録する
- 次がすべて通ること

  ```bash
  claude plugin validate . --strict
  claude plugin validate plugins/<name> --strict
  ```

- README の「収録プラグイン」に使い方と前提を数行で書く

## 変更の手順

- `main` へ直接 push しない。変更は PR を通し、CI が通ってからマージする
- プラグインの中身を変えたら `plugin.json` の `version` を上げる（上げないと利用者に届かない）
