# Power Automate コア開発ルール（最重要ルール集約・入口）

このファイルは Power Automate クラウドフローを設計・実装するときに最初に読む「入口」です。**複数案件**で実際に起きたエラーと確定知見から抽出した最重要ルールだけを要点でまとめ、詳細は各ルールファイルへリンクします。同じ内容は各ファイル1箇所にのみ書き、ここでは重複させません。

出所は当初 migrate-chat-spo（Teams課内会議アーカイブ単一フロー）の経験でしたが、その後の案件で得た知見も反映しています（例: エラー9は sync-shared-mailbox-to-sharepoint-list で発生）。案件の一覧はルート [README.md](../../README.md) を参照。

## 表記の約束
- 【事実】= 案件で実証済み、または公式資料で確認済み。
- 【推奨】= 上記事実から導いた設計上の推奨。
- 【案件固有】= その案件だけの判断。他案件にそのまま持ち込まない。
- 【要実環境確認】= 実環境で未検証。断定しない。
- 公式資料の参照日は原則 2026-07-16。以降に追記した項目は各節に参照日を明記する（例: プラットフォーム上限は 2026-08-03）。

## 絶対に守る8つのコアルール

1. 【事実】**SetVariable（変数の設定）で更新対象の変数自身を値式に含めない**。
   `union(variables('自身'), …)` / `concat(variables('自身'), …)` / `add(variables('自身'), 1)` は
   保存時に `WorkflowRunActionInputsInvalidProperty`（Self reference is not supported）で失敗する。
   → 詳細と修正パターン: [03 変数・配列・オブジェクト](./03_variables_arrays_and_objects.md)

2. 【事実】**累積は専用アクションで行う**。配列は「配列変数に追加（Append to array variable）」、
   文字列は「文字列変数に追加（Append to string variable）」、カウンターは「変数を増分する（Increment variable）」。
   ページ配列を1要素としてAppendせず、Apply to each（それぞれに適用する）で1件ずつ追加する。
   → 詳細: [03 変数・配列・オブジェクト](./03_variables_arrays_and_objects.md)

3. 【事実】**式の `@` は文字列の先頭、または `@{…}` 補間の中でのみ有効**。
   ネストした内側の関数に `@` を付けると（例 `@coalesce(...)`）インポート時に式パースエラーになる。
   さらに **`@{…}` の中身は関数呼び出しでなければならない**。式ではない表示テキスト
   （入力の説明文など）に `@{tenant}` のような記述があるとインポートが失敗する
   （`{tenant}` 単体は安全。`@` と `{` が隣接する場合だけが危険）。
   → 詳細: [02 式と型の安全性](./02_expression_and_type_safety.md)

4. 【事実/推奨】**型規律を守る**。基本形は `trim(coalesce(<文字列 or null>, ''))`。
   null・空文字・空配列は別物。Boolean の false / 数値の 0 を「未設定」と誤判定しない。
   → 詳細: [02 式と型の安全性](./02_expression_and_type_safety.md)

5. 【事実】**Apply to each（それぞれに適用する）の入力は必ず配列を保証する**。
   `coalesce(x, json('[]'))` か、Filter/Select/Query アクションの出力を渡す。
   → 詳細: [02 式と型の安全性](./02_expression_and_type_safety.md)

6. 【事実】**インポート成功＝完成ではない**。今回インポートは通ったが保存で失敗した。
   インポート後は必ず (1)開く (2)即保存 (3)フローチェッカー (4)小期間テスト を行う。
   → 詳細: [07 エクスポート/インポート](./07_export_import_package_rules.md)

7. 【事実】**コネクタ出力のフィールドは `body('X')?['field']` で参照する**。
   コネクタ（OpenApiConnection）の `outputs('X')` は封筒 `{statusCode, headers, body}` を返すため、
   `outputs('X')?['field']` は**常に null**（使うなら `outputs('X')?['body/field']`）。
   Compose の `outputs('Compose_X')` は封筒を持たないためそのままでよい。
   本案件では監査で5箇所の潜在バグ（本番経路でのみ発火）として検出した。
   → 詳細: [05 SharePoint / Teams パターン](./05_sharepoint_and_teams_patterns.md)

8. 【推奨】**未検証事項は「要実環境確認」と明記する**。公式資料で確認できない挙動を断定しない。
   実値（Team ID / Channel ID / サイトURL / リストGUID / メール / 接続GUID）は文書に書かず、
   プレースホルダー `{teamId} {channelId} {siteUrl} {listId} {destinationPath}` を使う。

## 起きた10のエラー（時系列・要約）
| # | いつ | 症状 | 根本原因 | 一次情報 |
|---|---|---|---|---|
| 1 | インポート時 | 式パースエラー（`@` 位置不正） | ネスト関数に `@` を付けた | [02](./02_expression_and_type_safety.md) |
| 2 | 保存時 | Self reference is not supported | SetVariable が自身を参照 | [03](./03_variables_arrays_and_objects.md) |
| 3 | インポート前に検出 | アクション名重複 | 初期化用と更新用が同名 | [01](./01_flow_architecture_rules.md) |
| 4 | 実行時（監査で事前検出） | コネクタ出力の参照が常に null | `outputs('X')?['f']` は封筒。`body('X')?['f']` が正 | [05](./05_sharepoint_and_teams_patterns.md) |
| 5 | 保存時 | `item` 欠落（missing required property 'item'） | PostItem×式のサイト/リスト（列スキーマ未解決） | [05](./05_sharepoint_and_teams_patterns.md) |
| 6 | 実行時 | `404 File not found` | 添付の `contentUrl` と `dataset` のサイト不一致 | [05](./05_sharepoint_and_teams_patterns.md) |
| 7 | 実行時（データとして顕在化） | 台帳が全件 Failed | CreateFile が中間フォルダを作らない／GetFileItem の名前解決 | [05](./05_sharepoint_and_teams_patterns.md) |
| 8 | インポート時 | `Unable to parse template language expression` | **表示テキスト**中の `@{tenant}` が式として解釈された | [02](./02_expression_and_type_safety.md) |
| 9 | 実行時 | リスト列挙だけが 403（`_api/web` は200） | コレクション列挙の `$expand` に `$select` の投影が無く、権限の無いシステムリストを実体化した | [05](./05_sharepoint_and_teams_patterns.md) |
| 10 | 実行時 | `substring parameter is out of range` | 開始位置は文字列長より**小さい**必要があり、空文字には `substring('', 0, 0)` すら適用できない | [02](./02_expression_and_type_safety.md) |

段階の教訓: 1・3・8は**インポート**で、2・5は**保存**で、4・6・7・9・10は**実行**で初めて現れた。
「インポートできた＝完成」でも「保存できた＝完成」でも「完走した＝結果が正しい」でもない。
エラー9は**文書に載せた誤ったREST断片をコピーしたこと**が発端だった（`handbook` の要約は索引であって正典ではない）。
この教訓から `tools/wdl_lint.py` に定義とMarkdownの両方を検査する共通リンター（L04 / M02）を置いている。
エラー10は**オフライン評価器が実機より緩かったこと**で見逃された（空文字のテストは存在したのに合格していた）。
`tools/wdl_eval.py` を実機の文言どおりに厳密化した結果、別案件の同型バグ3件が即座に検出された。
→ [../knowledge/lessons_learned.md](../knowledge/lessons_learned.md) §36

エラーの全文・再現・回避は [エラーカタログ](../knowledge/error_catalog.md) を参照。

## ルールファイル一覧（詳細はこちら）
- [01 フロー構成ルール](./01_flow_architecture_rules.md) — 単一/分割、Scope、命名、並列オフ、ネスト上限。
- [02 式と型の安全性](./02_expression_and_type_safety.md) — `@`規則、trim/coalesce、型規律、Compose分割。
- [03 変数・配列・オブジェクト](./03_variables_arrays_and_objects.md) — 自己参照禁止、型別更新、初期値。
- [04 コネクタ・権限・DLP](./04_connectors_permissions_and_dlp.md) — 標準/プレミアム、operationId、権限。
- [05 SharePoint / Teams パターン](./05_sharepoint_and_teams_patterns.md) — Graph HTTP、ページング、列内部名。
- [06 Word/HTML ドキュメント生成](./06_word_html_document_generation.md) — .docx生成不可、HTMLエスケープ。
- [07 エクスポート/インポート](./07_export_import_package_rules.md) — レガシーパッケージ、匿名化、検査。
- [08 エラー処理と冪等性](./08_error_handling_and_idempotency.md) — Scope分離、Status、冪等キー、段階テスト。

## 検証は機械走査で（0件になるまで）
【推奨】JSON構文 / runAfter兄弟整合 / 変数初期化＝参照 / 重複アクション名 / SetVariable自己参照 /
重複初期化 / 接続参照突合 / 不正な`@` / operationId実在 / コネクタ出力のbody/欠落 / 匿名化リーク
の各観点を機械走査し、すべて0件にする。

関連: [01](./01_flow_architecture_rules.md) / [02](./02_expression_and_type_safety.md) / [03](./03_variables_arrays_and_objects.md) / [教訓集](../knowledge/lessons_learned.md) / [エラーカタログ](../knowledge/error_catalog.md)
