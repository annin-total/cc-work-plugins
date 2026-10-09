# 履歴の読み方の覚え書き

確認日: 2026-10-01（文脈の区切り・切り替え操作・自動実行の記録は 2026-10-02）。形を確かめたのは Claude Code 2.1.286 の実機 1 台（履歴には 2.1.219 以降の版が混在）だけ。ほかの OS は未確認。
スクリプトの入口は `scripts/collect.py`（CLI）。集計の本体は同じフォルダの `_` で始まるモジュール（走査・行の処理・出力の組み立て・区切り・切り替え操作の集計など）に分かれる。数値の集計（重複排除・期間・トークン種別・ファミリー判別）は `collect` が決定的に行う。実行ごとの作業フォルダは `_workspace.py`（`init`）が作る。

## 保存先

- 設定ディレクトリは `CLAUDE_CONFIG_DIR`、なければホームの `.claude`（Windows は `%USERPROFILE%\.claude`）。
- transcript は `<設定ディレクトリ>/projects/<作業ディレクトリをエンコードした名前>/<sessionId>.jsonl`。
  フォルダ名は cwd の区切り文字を `-` に置き換えた形。
- サブエージェントは `<sessionId>/subagents/agent-<agentId>.jsonl`（隣に `.meta.json`。読まない）。行の `sessionId` は親と同じで、`agentId` と `isSidechain: true` が付く。
- workflows は `<sessionId>/workflows/` 以下にあるとされる（実機では未観測）。`collect` は `projects/` 以下を再帰で読むので、置き場所が変わっても拾える。
- 大きな tool 結果は `tool-results/` に退避されることがある（実機では未観測）。`collect` はファイル数と合計バイトだけ数える。
- `.orphaned*`・`*.superseded*` を名前に含むファイルは集計に入れず、件数だけ数える。

## 行の種類（トップレベルの `type`）

実機で見えたもの: `assistant`・`user`・`attachment`・`system`・`cost-state`・`queue-operation`・`last-prompt`・`ai-title`・`atis-latch`・`mode`。
ほかに `summary`・`file-history-snapshot` などがあるとされる。未知の型は `_other` として件数だけ数える。

- `assistant` 行だけ全体を JSON として読む。1 回の API 応答が content ブロックごとに複数行に分かれて書かれ、各行に同じ `message.id`・`requestId` と `usage` が付く。`stop_reason` が入る本体の行は最終値だが、サブエージェント（sidechain）の行は `stop_reason` が null のまま `output_tokens` が応答の開始時の値（数〜十数）で止まり、後から更新されない（実機 2.1.286 で確認）。
- `assistant` 以外の行は全体を読まず、深さ 1 のキー（`type`・`timestamp`・`sessionId`・`agentId`・`uuid`・`isSidechain`・`isMeta` 等）だけを抜く。`attachment` の中身にも `type` キーがあるので、深さを見て取り違えないようにしている。
- `user` 行のうち tool 結果を含むものは `message` だけ読んで文字数を数える。スラッシュ起動は `<command-name>` の名前だけを正規表現で抜く。
- `timestamp` は UTC の ISO8601（例 `2026-09-10T10:00:00.000Z`）。`cost-state`・`ai-title` 等には無い。

## usage の項目（`message.usage`）

| 項目 | 意味 |
|---|---|
| `input_tokens` | 新規入力（キャッシュ外） |
| `output_tokens` | 出力（thinking を含む。内訳は `output_tokens_details.thinking_tokens` だが読まない） |
| `cache_creation_input_tokens` | キャッシュ書き込み |
| `cache_read_input_tokens` | キャッシュ読み込み |
| `cache_creation.ephemeral_5m_input_tokens` / `ephemeral_1h_input_tokens` | 書き込みの TTL 別内訳 |
| `iterations` | 読まない（二重計上になる） |

ほかに `service_tier`・`server_tool_use`・`output_tokens_details` などがあるが読まない。`model` が `<synthetic>` の行は API 呼び出しではないので除く。

## 重複排除

- キーは `message.id` と `requestId` の組。どちらも無ければ `uuid`（フォールバックとして件数を数える）。
- 同じキーの行は、トークン項目ごとに最大値を取ってまとめる（値が小さい行が先に来ても、順序に関係なく同じ結果になる）。
- ファイル・サブエージェント・sidechain をまたいで 1 回だけ数える。実機では assistant 行のおよそ 3 分の 2 が重複だった。
- 既知の限界: ストリーミング途中の行で `requestId` が片方にしか無いと別キー扱いになり、二重に数えうる。`coverage.dedup_*` で件数だけ見える。
- 再開したセッション: 元の会話が新しいセッションの jsonl に複製され、重複排除で本体の行が片方（先に見た側）に寄る。合計は正しいが、元のセッションが `turns: 0` かつ `sidechain_ratio: 1.0` になる。元の jsonl に user 行があれば再開を疑い、「人の入力がない自動実行」と読まない。

## 巨大行

- 1 行が既定 50,000,000 バイト（`--max-line-bytes`）を超えたら読まずに飛ばし、件数だけ数える。
- 壊れた行（JSON として読めない・オブジェクトでない・途中で切れている・`type` が無い）は種類別に件数だけ数える。

## cost-state

- `{"type":"cost-state","sessionId":…,"modelUsage":{<モデル ID>:{inputTokens,outputTokens,cacheReadInputTokens,cacheCreationInputTokens,thinkingTokens,webSearchRequests,costUSD}},"totalCostUSD":…,…}`。timestamp は無い。
- セッション内の累積値のスナップショットが何度も書かれる。`collect` は sessionId ごとに合計が最大のもの（＝最後）を採る。
- assistant 行に出ない補助モデル（実機では Haiku）がここにだけ出る。金額フィールド（`costUSD`・`totalCostUSD`）は読んでも出力しない。
- 再開・分岐での累積の振る舞いは未確認。進行中のセッションでは transcript より古いことがあり、差が負になる。
- `outside_transcript` の出力差の読み方（推定）: `thinkingTokens` は `outputTokens` の内数で、assistant 行の `output_tokens` も thinking を含むので、thinking の別カウントは原因ではない。実機では opus で cost-state が transcript の約 60 倍あったが、最終値の行が残る本体のセッションでは両者が近く、差は sidechain の行の開始時の値（上記）に集中していた。サブエージェントが多いセッションでは output の差が大きく出るのが普通で、「transcript が過小」「transcript の外で消費」と断定せず、`by_role.sidechain.output_unfinalized_calls` と合わせて読む。input・cache は開始時にほぼ確定するので差は小さい。

## effort

- `assistant` 行のトップレベルに `effort`（例 `medium`）と `perTurnEffort` がある（2.1.286）。古い版には無い。
- 無い行は「記録なし」であり、0 や低いという意味ではない。`collect` は版ごとに「読めた行数／全行数」を出す。

## スキル・MCP の記録

- Skill ツール: assistant 行の content にある `{"type":"tool_use","name":"Skill","input":{"skill":"<名前>"}}`。
- スラッシュ起動: user 行の本文に `<command-name>/<名前></command-name>` が入る。`/clear` などの組み込みコマンドも同じ形。
- `attributionSkill`: assistant 行のトップレベル。スキルの実行中は行ごとに付くので、行数は呼び出し回数ではない。(sessionId, スキル名) の distinct で数える。
- MCP ツール名は `mcp__<サーバ名>__<ツール名>`。assistant 行には `attributionMcpServer` もある（未使用）。
- 分類は `collect` が付ける: 名前に `:` を含む＝plugin、`<設定ディレクトリ>/skills/` の個人定義と一致＝personal、それ以外＝builtin_or_unknown。

## 文脈の区切り・切り替え操作

確認日 2026-10-02。実機の履歴で形を確かめたもの:
- compact: `type:"system"`・`subtype:"compact_boundary"` の行に `compactMetadata` がある。`trigger` は `manual` / `auto`、`preTokens`（圧縮直前の文脈量）、`postTokens` ほか。手動 `/compact` の `<command-name>` の数と manual の件数が一致した。`collect` は trigger で分け、`preTokens` は auto だけ中央値・最大を出す。
- `/clear`・`/resume`・`/model`: user 行の `<command-name>/clear</command-name>` 等（上記「スキル・MCP の記録」と同じ形）。`/clear` は新しいセッション（新しい jsonl）の先頭付近に現れる。`/model` の起動は切り替えなしでも記録されるので、`message.model` が本体の隣り合う記録で変わった回数（`model_change`）も別に数える。
- 分岐・再開で別ファイルへ行がコピーされると、同じ `uuid` の行が複数のファイルに現れる（`forkedFrom` が付く）。`collect` は `uuid` で 1 回だけ数える。

確認できなかったもの（検出しない）:
- `/rewind`: 専用の行・コマンド記録が見つからない。同じ `parentUuid` に user 行が複数ぶら下がる例はあるが、巻き戻し以外（割り込み・やり直し）との区別がつかない。公式ドキュメントにも記録の形の記載がない。
- `--continue`・`--resume`（起動オプション）による再開: 目印が見つからない。数えるのはセッション内の `/resume` の起動だけ。
- `/branch`・`--fork-session`: `forkedFrom` の行コピーは見えるが、操作の回数としては数えない。
- compact の記録が無い古い版: 版別に「セッション数」と各操作の件数を並べ（`context_ops.by_version`）、記録の有無を読み分ける。件数 0 でセッションがある版は「0 件」か「記録なし」かを断定できない。
- 設定: `env.CLAUDE_AUTOCOMPACT_PCT_OVERRIDE`（1〜100 の整数だけを採る）と `autoCompactEnabled`（真偽）を `settings.json` から読む。実機の設定には両方とも無かった（値なし＝既定）。`autoCompactEnabled` は公式では `settings.json` 以外（グローバル設定）に置く可能性があり、`settings.json` に無くても無効とは限らない。

## 無人・自動実行の記録

確認日 2026-10-02。実機 1 台の履歴（2.1.219〜2.1.287）で形を確かめたもの:
- `entrypoint`: assistant・user・system・attachment のすべての行のトップレベルにあり、全行に付いていた。値は `cli`（対話）・`sdk-cli`（`claude -p`）・`sdk-py`（Agent SDK）・`claude-desktop`。確認した範囲ではセッション内で値は変わらなかった。セッションの値は期間内で最も早い行の値とし、混在したセッション数を `mixed_sessions` に出す。記録の無いセッションは `not_recorded`。
- `turnOrigin`・`promptSource`: user 行のトップレベルだけ（assistant・system には無い）。tool 結果の行・sidechain の行には付かず、一部の user 行にだけ付く。`turnOrigin` は 2.1.278 以降、`promptSource` は 2.1.219 以降の版で見えた。`turnOrigin` の値は `human`・`sdk`・`peer`・`task_notification`・`scheduled`、`promptSource` の値は `typed`・`sdk`・`system`・`queued`・`suggestion_accepted`。同じセッションの中で値は変わる。
- 定期実行系: assistant 行の tool_use の `name` が `ScheduleWakeup`（`/loop` の自己ペース）・`CronCreate`・`CronList`・`CronDelete`。user 行の `<command-name>/loop</command-name>`。
- `collect` は user 行のうち tool 結果でも sidechain でもないものを対象に、記録のある行（`observed_n`）とない行（`absent_n`）を分けて数える。版別に対象行数と記録のある行数を `turn_origin.by_version` に出す。

確認できなかったもの（意味は決めない）:
- `turnOrigin`・`promptSource` の各値が何を指すか（`scheduled` が `ScheduleWakeup`・cron のどちら起点か、`system` や `peer` が何か）。値のとおりに数えるだけで、「無人」と断定しない。
- user 行の `origin`（`kind` などを持つオブジェクト）。本文を含みうるので読まない。
- `/schedule` の起動（この履歴には記録が無かった。形は `/loop` と同じ `<command-name>` と想定）。
- `Monitor` ツール（見えたが、自動実行かどうかは決められないので数えない）。
- `entrypoint` が記録されない版（この履歴では全行にあった）。ほかの OS・版は未確認。
- 端末の外（CI・クラウドの定期実行・ほかの端末・Web 版・別アカウント）の実行は履歴に残らないので、固定質問で聞く。OS のスケジューラ（crontab・launchd・タスク スケジューラ）やプロセスは確認しない。

## OS 差

- 文字コードは UTF-8 で読み、BOM・不正バイト・CRLF を許容する。出力も UTF-8 を明示する（日本語 Windows の既定 cp932 を避ける）。標準出力には ASCII だけを出す。
- パスは標準 API で扱い、区切り文字を決め打ちしない。WSL とネイティブの履歴は別の設定ディレクトリになる。
- 日別・時間帯は `--local-tz` のとき端末のローカル時刻で数える（調書には書かない）。

## 集計 JSON のスキーマ（schema_version 1.0）

キーは英小文字のスネークケース。トークンは種別ごとに `input`（新規入力）・`output`（出力）・`cache_creation`（キャッシュ書き込み）・`cache_read`（キャッシュ読み込み）・`cache_creation_5m`／`cache_creation_1h`（書き込みの内訳）で持ち、種別を合算した値は持たない。
「期間内」は assistant 行の timestamp が [start, end) に入ること。ラベル `S-xxxxxxxx` はセッション、`P-xxxxxxxx` は cwd の sha256 先頭 8 桁。

| キー | 意味 |
|---|---|
| `schema_version` / `generated_at` | スキーマの版 / 生成時刻（UTC） |
| `params` | `start`・`end`（UTC）、`timezone`（local/utc）、`utc_offset_minutes`、`exclude_session_given`、`max_line_bytes` |
| `coverage.files_total` / `files_processed` / `files_unreadable` | 見つけた jsonl 系ファイル数 / 読んだ数 / 開けなかった数 |
| `coverage.files_orphaned` / `files_superseded` | 集計から外したファイル数 |
| `coverage.lines_total` / `lines_processed` | 全行数 / 処理できた行数 |
| `coverage.lines_unreadable` | 読めなかった行の種類別件数（`json_decode`・`not_object`・`truncated`・`no_type`・`empty`・`error_<例外名>`） |
| `coverage.lines_oversize_skipped` / `lines_invalid_utf8` | 巨大行で飛ばした数 / 不正バイトを含んだ行数（置換して処理） |
| `coverage.assistant_lines` | assistant 行の数（synthetic を含む） |
| `coverage.records_before_dedup` / `records_after_dedup` / `dedup_removed` | 重複排除の前後の件数と差 |
| `coverage.dedup_fallback_uuid` / `dedup_no_key` | uuid で代用した行数 / キーが無く 1 行 1 件とした数 |
| `coverage.synthetic_lines` / `usage_missing_lines` | 除外した `<synthetic>` 行 / usage が無い・壊れた行（0 とみなす） |
| `coverage.records_out_of_period` / `records_timestamp_missing` | 期間外の件数 / timestamp が無い・読めない件数 |
| `coverage.excluded_session_lines` / `excluded_session_records` | `--exclude-session` で外した行数・件数（スキルの手順では使わない） |
| `coverage.user_lines_duplicate` | 同じ uuid の user 行の重複 |
| `coverage.records_timestamp_out_of_range` | 2020 年より前・現在の翌日より後の timestamp を採らず、不明扱いにした行数 |
| `coverage.projects_dir_found` / `walk_errors` | `projects/` の有無 / 歩けなかったフォルダ数 |
| `coverage.coverage_ratio` | 処理できた行／全行（巨大行・壊れた行を除いた割合）。目安 0.9 未満なら「部分的な集計」 |
| `history_range` | `oldest_ts`・`newest_ts`（期間内外を問わず履歴全体）と `files_with_lines` |
| `retention` | `cleanup_period_days`（設定値、無ければ既定 30 と仮定し `cleanup_period_days_source` に `default_assumed`）、`history_starts_after_period_start`、`oldest_near_cleanup_cutoff`、`suspected_gap`（両方真のとき。断定ではない） |
| `settings` | `settings.json` の `found`・`cleanup_period_days`・`model`（`alias`・`bucket`・`generation` のみ）・`effort_level`・`always_thinking_enabled`・`mcp_servers_count`・`auto_compact_pct_override`（数値。無ければ null）・`auto_compact_enabled`（真偽。無ければ null） |
| `line_types` / `versions` | 行の種類別件数 / assistant 行の版別件数 |
| `totals` | 期間内の `api_calls`（重複排除後の件数）、`sidechain_api_calls`、`tokens_by_type`、`active_days` |
| `models.buckets.<名前>` | 名前はファミリー（`opus` 等や新しい語）・`other_claude`・`non_claude`・`unknown`。各々 `api_calls`、`generations`（世代別件数、例 `5-5`）、`tokens`、`by_role.main` / `by_role.sidechain`（本体 / サブエージェントごとの `api_calls`・`output_unfinalized_calls`（`stop_reason` が無く output が開始時の値の可能性がある件数）・`tokens`（5m/1h 内訳を含む）） |
| `effort.effort` / `effort.per_turn_effort` | `observed_n`（記録あり）、`absent_n`（記録なし。0 ではない）、`values`（値別件数） |
| `effort.by_version.<版>` | `records`、`effort_observed`、`per_turn_effort_observed` |
| `sessions.count` / `subagents_distinct` | 期間内のセッション数（sessionId）/ サブエージェント数（agentId） |
| `sessions.active_minutes` / `length_buckets` | 稼働分の合計・中央値・p90・最大 / 長さの分布。定義は `length_definition`（間隔 30 分超で分割し稼働時間を足す） |
| `sessions.top_by_output` ほか | `top_by_output`・`top_by_cache_creation`・`top_by_input`・`top_by_cache_read`。各 5 件まで `{session, session_id, file, value, share}`（`session_id` は生の ID、`file` は設定ディレクトリからの相対パスで親セッションの jsonl（サブエージェントのファイルではない。複数ファイルなら最大寄与のもの）、share は種別の全体に対する寄与率） |
| `sessions.details.<S-ラベル>` | 上位に出たセッションの `project`、`api_calls`、`turns`（人の入力）、`active_minutes`、`segments`、`subagents`、`sidechain_ratio`、`tokens`、`model_buckets`、`effort`、`tools`、`file_extensions` |
| `context_ops.ops.<操作>` | 操作は `compact_manual`・`compact_auto`・`clear`・`resume_command`・`model_command`・`model_change`。各々 `total`（期間内の合計）・`sessions`（発生したセッション数）・`per_session`（合計／期間内のセッション数） |
| `context_ops.auto_compact_pre_tokens` | `observed_n`・`median`・`max`（自動 compact の直前の文脈量。無ければ null） |
| `context_ops.longest_sessions` | 稼働分が長い順の上位 5 件 `{session, active_minutes, ops}`（`ops` は操作別の回数） |
| `context_ops.by_version` | 版ごとの `sessions` と操作別の件数。件数 0 の版は「記録なし」と「0 件」を区別できない |
| `context_ops.not_detected` | 検出していない操作（`rewind`・`resume_cli_flags`・`branch`） |
| `automation.entrypoint` | `by_entrypoint.<値>`（`sessions`・`api_calls`・`tokens`（種別ごと、合算しない））。値は `cli`・`sdk-cli`・`sdk-py`・`claude-desktop` ほか、記録の無いセッションは `not_recorded`。`mixed_sessions`（期間内で値が混在したセッション数） |
| `automation.turn_origin` | `turn_origin`・`prompt_source` それぞれの `observed_n`・`absent_n`（記録なし。0 ではない）・`values`（user 行単位）、`by_version.<版>`（`user_lines`・`turn_origin_observed`・`prompt_source_observed`） |
| `automation.schedule` | `tools.<ScheduleWakeup・CronCreate・CronDelete・CronList>` の `calls`・`sessions`（発生したセッション数）、`commands.<loop・schedule>`（`<command-name>` の起動回数） |
| `projects` | `count` と `top_by_output`（`label`・`sessions`・`api_calls`・`tokens`） |
| `tools.calls_by_name` / `file_extensions` | tool 名別の呼び出し数 / 入力に `file_path`・`notebook_path` を持つツールすべて（Read・Write・Edit など）の拡張子別件数。読み込みと書き込みを区別しない（`(none)`・`(other)` あり） |
| `tools.result_chars` | tool 結果の文字数: `count`・`chars_total`・`chars_max`・`buckets`・`by_tool`（`count`・`chars`）・`top_max_by_tool`（最大文字数の上位 5 ツール `{tool, chars_max}`） |
| `tools.tool_results_dir` | `tool-results/` のファイル数と合計バイト |
| `skills.skill_tool.<名前>` | Skill ツールの呼び出し数と `classification` |
| `skills.slash_commands.<名前>` | `<command-name>` の件数と `classification`（組み込みコマンドを含む） |
| `skills.attribution_skill.<名前>` | `sessions`（distinct 数）、`lines`（行数。呼び出し回数ではない）、`classification` |
| `skills.installed` | `personal`・`plugin` ごとの `count`、SKILL.md のバイト数、description の文字数（合計・最大） |
| `mcp` | `servers_used`、`configured_servers_count`、`servers.<名前>` の `calls`・`distinct_tools` |
| `cost_state` | `confidence`（常に `estimate`）、`sessions_with_snapshot`、`by_family.<名前>` の `cost_state`・`transcript`・`outside_transcript`（差。負もありうる）・`only_in_cost_state` |
| `timeline` | `by_day`・`by_hour`（件数。調書には書かない） |

スキル名・MCP サーバ名・tool 名は名前のまま入っている。集計 JSON は簡潔さのため本文・コマンド・cwd の生文字列を含めない。

## 履歴の読み方

LLM は必要に応じて履歴の jsonl を直接読んでよい（本文を含む）。ただし重さへの寄与が大きいセッション（`top_by_*` の `file`）を中心に、必要な範囲だけを読み、全文は読まない。
数値は `collect` の集計を正とし、LLM が履歴から数え直さない。

実データと食い違ったら実データを優先し、必要なら Web 検索する。
