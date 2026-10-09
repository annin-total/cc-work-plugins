---
name: setup-retitle
description: Claude Code のセッションタイトルを、作業の趣旨が変わるたびに「要約 · ブランチ」へ自動で付け直す hook と、手動で付け直す /retitle コマンドを、利用者の環境（macOS・Windows・Linux）に導入・確認・削除する。「セッション名を自動で変えたい」「タブやセッションを見分けたい」「retitle を入れて」「自動リネームの hook をセットアップして」「/retitle を消したい」など、セッションタイトルの自動付け直しの導入・更新・動作確認・アンインストールを頼まれたら、名前を挙げられていなくても使う。
---

# セッションタイトル自動リネームの導入

作業の趣旨が変わったら、Claude Code のセッションタイトルを「要約 · ブランチ」に付け直す仕組みを入れる。

- **hook**（`UserPromptSubmit`）: 送信のたびに、裏で `claude -p --model haiku` に「主題が変わったか」を判定させる。結果は**次の送信**でタイトルに反映される。
  15 字未満の入力と `/` で始まる入力は判定しない。main・master のブランチ名は付けない
- **/retitle [要約]**: 要約を指定して付け直す（引数なしなら会話から要約を決める）

導入の中身は `scripts/install.py` が一括で行う。hook の本体は `scripts/retitle.py`、/retitle の雛形は `assets/retitle-skill.md`。
これらのパスは、このスキルのディレクトリ（読み込み時に示される Base directory）からの相対パスである。

## 手順

### 1. Python を決める

hook は、導入に使った Python で起動するよう登録される。だから**普段から使える、仮想環境（venv）の外の Python 3.8 以上**を選ぶ。
候補を順に試し、`3.8` 以上の版を返した最初のものを使う。

```bash
python3 -c "import sys; print(sys.version)"
python -c "import sys; print(sys.version)"
py -3 -c "import sys; print(sys.version)"   # Windows の Python ランチャー
```

Windows の `python3`・`python` は、Microsoft Store を開くだけの偽物のことがある（何も出ないか Store の案内が出る）。その場合は次の候補へ進む。
どれも使えなければ、利用者に Python の導入を頼んで止める。

### 2. 導入前に伝える

利用者に次を短く伝えてから進める。費用と送信先は利用者が知っておくべきことだから。

- 15 字以上の送信のたびに haiku を 1 回呼ぶ（利用者自身の Claude Code の認証で、本文の先頭 2000 字を送る）
- `settings.json` の `hooks.UserPromptSubmit` に 1 件足す。書き換える前に同じ場所へ `settings.json.bak-retitle-<日時>` を残す
- 状態は `~/.cache/cc-retitle/` に溜まる（自動では消えない）

### 3. 導入する

```bash
<python> "<スキルのディレクトリ>/scripts/install.py"
```

- 設定ディレクトリは、環境変数 `CLAUDE_CONFIG_DIR` があればそこ、なければ `~/.claude`。別の場所なら `--config-dir <パス>` を付ける
- 何度実行してもよい。前に入れた retitle の hook は置き換えられ、二重には登録されない（更新もこれで行う）
- 「中止しました」と出たら、`settings.json` は書き換わっていない。理由（JSON の誤り、古い Claude Code、venv の Python など）を利用者に伝えて直してもらう

### 4. 確かめる

```bash
<python> "<スキルのディレクトリ>/scripts/install.py" --check
```

全部 `OK` なら導入できている。`NG` が出たら、その行を利用者に伝える。

### 5. 結果を伝える

- 次に起動したセッションから確実に効く（起動中のセッションにも反映されることはあるが、当てにしない）
- タイトルは、判定の数秒後の**次の送信**で変わる。すぐ変えたいときは `/retitle <要約>`、または組み込みの `/rename`
- VS Code・Cursor の統合ターミナルでタブにタイトルを出したい場合は、エディタの設定 `terminal.integrated.tabs.title` に
  `${progress}${separator}${workspaceFolderName}${separator}${sequence}` を入れるとよい、と案内する。エディタの設定は利用者に任せ、勝手に書き換えない

## 削除

```bash
<python> "<スキルのディレクトリ>/scripts/install.py" --uninstall
```

`settings.json` から retitle の hook だけを除き、hook 本体と /retitle を消す。`~/.cache/cc-retitle/` は残すので、不要なら利用者に消してもらう。

## うまく動かないとき

- タイトルが変わらない: `~/.cache/cc-retitle/error.log` を見る。`claude -p failed` なら、ターミナルで `claude -p --model haiku "hi"` が通るかを確かめる
- `claude` が見つからない: hook は `PATH` の `claude` で判定する。`claude` を `PATH` に通す
- Claude Code が古い: hook をシェルを介さずに起動する登録（`args`）は 2.1.139 以降で使える。`claude update` で更新する
