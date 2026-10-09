# CLAUDE.md

Claude Code のプラグインマーケットプレイス。作業は [CONVENTIONS.md](CONVENTIONS.md) に従う（全ツールが Windows と macOS の両方で動くこと）。

- テスト: `python3 -m unittest discover -s tests/<plugin>`（Windows は `python`）
- マニフェスト検証: `claude plugin validate . --strict` と `claude plugin validate plugins/<plugin> --strict`
- 変更は PR を通す。`main` へ直接 push しない。プラグインを変えたら `plugin.json` の `version` を上げる
