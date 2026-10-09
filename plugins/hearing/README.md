# hearing

この端末の Claude Code の履歴から利用の重さ（モデル・effort・トークン量・頻度・セッションの長さなど）をおおまかに推定し、本人へのヒアリングと合わせた調書（Markdown 1 ファイル）を作る。金額は出さない。設定は変更しない。

## 導入

```text
/plugin marketplace add annin-total/cc-work-plugins
/plugin install hearing@cc-work-plugins
```

マーケットプレイスを追加済みなら 1 行目は要らない。次に起動したセッションから使える。

## 前提

- Python 3.9 以上（`python3` → `python` → `py -3` の順に探す。見つからなければ中止する）

## 使い方

```text
/hearing:hearing-cost [日数|開始日..終了日] [cleanup]
```

- 既定は直近 30 日。期間は `YYYY-MM-DD..YYYY-MM-DD`（両端の日を含む）
- 明示的に呼んだときだけ動く。集計の後、利用状況について数問ずつ質問する
- `cleanup` を付けると、最後に中間ファイル（`work/`）の削除を提案する

## 出力

- 起動したディレクトリの `hearing-cost/<日時>/` に調書 `claude-code-hearing_<氏名>_<YYYYMMDD>.md` を置く。中間ファイルは同じ場所の `work/` に残る
- `hearing-cost/.gitignore` を作り、git の管理から外す
- 氏名は OS のアカウント名が入る。送る前に調書の内容とファイル名を確認・修正する
- 調書は自動送信しない

## 動作確認の状況

Windows・macOS とも実機での確認は未完了。CI の自動テストは両 OS で実行している。チェックリストは[評価手順](https://github.com/annin-total/cc-work-plugins/blob/main/tests/hearing/README.md)にある。

## 詳細

手順と守ることは [SKILL.md](skills/hearing-cost/SKILL.md) にある。
