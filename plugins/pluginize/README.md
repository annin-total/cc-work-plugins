# pluginize

手元で作った hook やスキルを、マーケットプレイスの規約に合わせて調整し、1 つのプラグインとして取り込む PR を作る。調整するのは主に次の 3 点。

- Windows・macOS の両方で動く書き方にする
- 絶対パス・ユーザー名・ホームの場所・社内の名前など、端末固有の値を設定か自動検出に置き換える
- マーケットプレイスの構成（マニフェスト・README・登録・テスト・version）に合わせる

既定の取り込み先はこのマーケットプレイス（annin-total/cc-work-plugins）。別のマーケットプレイスも指定できる。

## 導入

```text
/plugin marketplace add annin-total/cc-work-plugins
/plugin install pluginize@cc-work-plugins
```

マーケットプレイスを追加済みなら 1 行目は要らない。次に起動したセッションから使える。
このリポジトリを clone して Claude Code で開き、フォルダを信頼した場合は、導入しなくても有効になる。

## 前提

- `git` と、PR を作るための `gh`（GitHub CLI、ログイン済み）
- 取り込み先のリポジトリに push できること（fork からの PR は想定していない）

## 使い方

```text
/pluginize:pluginize <取り込む hook・スキルの場所>
```

「この hook をプラグインにして」と頼んでもよい。取り込み先・調整の案・プラグイン名は選択式で確認してから書き込む。

- 元の hook・スキルのファイルは変更しない。コピーを調整する
- トークンなどの秘密の値は取り込まず、見つけた場所を知らせる
- 取り込み先の既定ブランチから作業ブランチを切り、PR を作るところまで行う。マージはしない
- 作業ツリーに未コミットの変更があれば、触らずに止めて扱いを尋ねる

プラグインを導入した後は、元の hook の登録を利用者の settings から外す（残すと二重に動く）。

## 動作確認の状況

macOS で、架空の hook を使った試走（PR 作成の直前まで）を確認した。Windows 実機では未確認。

## 詳細

手順は [SKILL.md](skills/pluginize/SKILL.md)、調整の要点は [references/conventions.md](skills/pluginize/references/conventions.md) にある。
