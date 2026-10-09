# gitignore-sync

`.gitignore` で無視しているのに Git がまだ追跡しているファイルを、作業ツリーのファイルは残したまま追跡解除する。誤って commit・push した `.env` や認証情報ファイルを、作業ツリーを変えずに履歴から消すこともできる。

## 導入

```text
/plugin marketplace add annin-total/cc-work-plugins
/plugin install gitignore-sync@cc-work-plugins
```

マーケットプレイスを追加済みなら 1 行目は要らない。次に起動したセッションから使える。

## 前提

- Python 3.9 以上（`python3` → `python` → `py -3` の順に探す）
- Git
- 履歴からの機密消去を使うときだけ、`git-filter-repo` 2.47 以上（macOS は `brew install git-filter-repo`、Windows は `pip install git-filter-repo` など）。`PATH` 上で `git-filter-repo` として見つかる必要がある

## 使い方

```text
/gitignore-sync:gitignore-sync
```

- **通常同期**: 追跡中の無視対象を `git rm --cached` で index から外す。作業ツリーのファイルは変えない。HEAD やリモートに残っていれば、外したパスだけを通常の commit と push で揃える（force push はしない）
- **履歴からの機密消去**: 秘密ファイルを履歴から消すと明示したときだけ動く。origin の一時クローンで `git-filter-repo` を実行し、同意を得てから `git push --force --mirror` する。秘密ではないファイルの履歴改変は断る

## 注意

- 通常同期の結果を他のクローンで pull すると、そちらでは無視対象のファイルが消える
- 履歴を消しても、漏れた認証情報は失効しない。先にローテーションする
- 履歴を消した後、共同作業者は pull せず clone し直す。fork や GitHub の PR 参照には残りうる
- 送信先は、そのリポジトリの `origin` だけ

## 動作確認の状況

macOS で、一時リポジトリに対する通常同期（`--check`・`--untrack`）と `plan` を確認した。`rewrite`・`push`・`adopt` は実際のリモートでは確認していない。Windows は実機で未確認（CI の自動テストは両 OS で実行する）。

## 詳細

手順と守ることは [SKILL.md](skills/gitignore-sync/SKILL.md) にある。
