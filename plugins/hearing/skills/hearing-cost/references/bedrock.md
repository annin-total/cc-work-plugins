# Bedrock の注意（確認日 2026-10-01）

- モデル ID は `anthropic.` や `us.anthropic.` のような接頭辞付きのことがある。ファミリーはトークン境界付きの規則で判別する（collect が行う）。
- ARN だとモデル名が読めないことがある。`foundation-model/` や `inference-profile/` 以降は読めるが、application-inference-profile などは「不明」にする。
- キャッシュ TTL の既定は 5 分と報告されている（二次情報・未確認）。長い休憩のあとは書き込みが増えやすい。
- `message.model` に実際に入る文字列（接頭辞付き ID か ARN か）と、キャッシュ書き込みの内訳が残るかは、実機で未確認。ここは仮置きで、確認できたら更新する。
- 実データと食い違ったら実データを優先する。
