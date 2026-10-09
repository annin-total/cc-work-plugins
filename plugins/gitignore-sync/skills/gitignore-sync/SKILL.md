---
name: gitignore-sync
description: .gitignore で無視しているのに Git がまだ追跡しているファイルを、手元の作業ツリーは残したまま追跡解除するとき、または誤って commit や push した .env や認証情報ファイルを履歴から消すときだけ使う。/gitignore-sync:gitignore-sync、無視したのにリモートに残っている、追跡だけ外してローカルファイルは残したい、push 済みの env や秘密ファイルを履歴から消去する、が対象。.gitignore の作成やルール編集、通常の commit、未追跡ファイルの削除、秘密ではないファイルの履歴改変、鍵の失効やローテーションだけでは使わない。
---

# gitignore と追跡状態の同期

依頼がどちらかを先に決める。通常同期の途中で秘密ファイルを見つけても、履歴消去へ自動では切り替えない。

- 追跡だけを `.gitignore` に揃える: 通常同期
- 誤って push した `.env` や認証情報ファイルを履歴から消す: 履歴からの機密消去

Python は `python3` → `python` → `py -3` の順に `--version` を試し、`Python 3.` を返した最初のものを使う。以下の `python3` は見つけたものに読み替える。

## 通常同期

検査と追跡解除は同梱スクリプトに任せる。`git rm` を手で組み立てない。

### 影響範囲

- **ローカルファイル（作業ツリー）は一切変更しない。** 作成・編集・削除・上書き・`git clean` / `git restore` / `--cached` なしの `git rm` をしない。Write / Edit などのファイル編集ツールもリポジトリ内ファイルに使わない。
- **Git の追跡情報とリモートは更新してよい。** index からの追跡解除と、それを載せる通常の commit / push は行ってよい。
- `.gitignore` の内容は、ユーザーが明示しない限り編集しない。

`git pull` で作業ツリーから消える操作は、このスキルでは行わない。他クローンが pull すると、そちらではファイルが消える点だけ報告する。

### エージェントの役割

1. Git 作業ツリーか確認する。違えば中止する。
2. 可能なら `git fetch --prune` する。失敗しても検査は続ける。作業ツリーは触らない。
3. `--check` で index / HEAD / リモート追跡ブランチの不一致を出す。
4. index に無視対象の追跡が残っていれば `--untrack` する。
5. もう一度 `--check` する。スクリプトが作業ツリー変更を検出したら、そこで止める。
6. HEAD やリモートに無視対象が残っていれば、追跡解除だけを通常の commit と `git push` する。force は付けない。`git add -A` は使わない。ステージしてよいのは今回外したパスと、ユーザーが既に変更している `.gitignore` だけ。無関係な変更が混ざるなら commit せず報告する。
7. 結果を報告する。

### 実行

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/sync_gitignore_tracking.py" --check
```

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/sync_gitignore_tracking.py" --untrack
```

### スクリプトが保証すること

- 判定は `git ls-files -ci --exclude-standard` と `git check-ignore --no-index`
- 追跡解除は常に `git rm --cached -f`
- 解除前後で、存在していたローカルファイルの種別・内容が同じであること
- commit / push / reset / clean / 作業ツリー書き込みはしない

## 履歴からの機密消去

ユーザーが、誤って commit または push した秘密ファイルを履歴から消すと明示したときだけ使う。対象は `.env`、認証情報、鍵ファイルのように、ファイル全体が秘密であるパスに限る。調査メモや生成物を履歴から消す依頼は拒否する。

履歴を書き換えても、既に漏れた認証情報は失効しない。先にローテーションが必要だと伝え、それだけで足りるなら書き換えない。ソースファイルの中の文字列だけを消す置換は、このスキルでは実行しない。

作業ツリーでは `git-filter-repo` を走らせない。秘密ファイルのバイト列は残す。force push は、一時クローンからの `git push --force --mirror` だけで、結果を見せたあとの明示確認がいる。

1. リポジトリ相対の対象パスをユーザーと確定する。改名前のパスも対象に含める。
2. `plan` を実行する。表示された対象パスが、消す履歴のすべてである。終了コード 2 ならリモート履歴に無いので、rewrite しない。内容が大きく変わった移動は改名として出ないので、ユーザーが知る旧パスがあれば `--path` に足してから進む。
3. 確認事項を伝えて、rewrite の同意を待つ。全コミットハッシュが変わりうること、共同作業者は pull せず clone し直すこと、fork や GitHub の PR キャッシュには残りうること、作業中にリモートへ入った更新は mirror push で捨てられること、手元の秘密ファイルは残ること。
4. 同意後に `rewrite --confirm-rewrite` を実行する。`STATE_DIR` を控える。
5. 一時クローンの履歴から対象が消えたことと、`NOTE: First Changed Commit`、影響する PR 数をユーザーに見せ、mirror push の同意を待つ。
6. 同意後に `push --confirm-push` を実行する。`refs/pull/` など読み取り専用 ref の拒否だけなら続行する。それ以外の失敗では止める。
7. `adopt` を実行し、現在のブランチだけを書き換え後の `origin` に合わせる。未 push のコミットや対象外のステージがあるときは、スクリプトが止める。その指示に従い、このクローンから push しない。
8. `gitignore に無いパス` と出たパスだけを `.gitignore` に追記する。それ以外のファイルは書かない。
9. 結果を報告する。他のローカルブランチと他クローンは古い履歴を持つので push しない。手元の reflog には秘密が残ることがある。`git gc` や `git reflog expire` は、ユーザーが明示したときだけ別途行う。GitHub 上のキャッシュや PR 参照まで消すには、GitHub Support への連絡が要る。

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/purge_secret_history.py" plan --path .env
```

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/purge_secret_history.py" rewrite --confirm-rewrite --path .env
```

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/purge_secret_history.py" push --confirm-push --state "$STATE_DIR"
```

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/purge_secret_history.py" adopt --state "$STATE_DIR"
```

`git-filter-repo` が無い、または 2.47 より古いときは、利用者に導入を頼んでからやり直す（macOS は `brew install git-filter-repo`、Windows は `pip install git-filter-repo` など）。`filter-branch` と BFG には切り替えない。

## 禁止

- ローカルファイルを変える操作全般。機密消去で許すのは、対象パスだけの `.gitignore` 追記と、`adopt` が行う `git reset --mixed` だけ
- `--cached` なしの `git rm`
- `git clean`、`git reset --hard`、作業ツリーを捨てる `git restore`
- 通常同期での `git push --force` と `--force-with-lease`
- 作業ツリー上での `git filter-repo` / `filter-branch` / BFG
- 秘密ではないファイルの履歴改変
- 確認前の mirror push、確認なしの `git reflog expire` と `git gc --prune=now`
- `.gitignore` の無断編集。機密消去で追記してよいのは、履歴から外したパスだけ

## 報告

- 追跡解除したパス、または履歴から外したパス
- ローカルファイルを変更していないこと
- commit / push / mirror push の有無
- 他クローンでは pull せず clone し直すこと（履歴消去をしたとき）
- 認証情報のローテーションが別途必要であること（履歴消去をしたとき）
- 他クローンで pull すると無視対象が消えること（通常同期で必要なときだけ）

## 使用方法

```text
/gitignore-sync:gitignore-sync
```
