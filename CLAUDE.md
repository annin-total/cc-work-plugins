# CLAUDE.md

Claude Code のプラグインマーケットプレイス。作業は [CONVENTIONS.md](CONVENTIONS.md) に従う（全ツールが Windows と macOS の両方で動くこと）。

- 検証: `python3 scripts/validate.py`（Windows は `python`）。マニフェスト検証・marketplace.json の整合・全テストをまとめて実行する
- 新しいプラグインは `templates/plugin/` から作る（[templates/README.md](templates/README.md)）
- 変更は PR を通す。`main` へ直接 push しない。プラグインを変えたら `plugin.json` の `version` を上げる
