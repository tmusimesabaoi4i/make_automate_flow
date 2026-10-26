# フロー構成ルール（単一/分割・Scope・命名）

フロー全体の骨組みに関するルールです。単一フローにするか分割するかの判断、Scope（スコープ）による Try-Catch-Finally 構成、変数初期化の位置、ネスト深さ、並列オフ、命名規則を扱います。式・型の詳細は [02](./02_expression_and_type_safety.md)、変数更新の詳細は [03](./03_variables_arrays_and_objects.md) を参照。

## 単一フローか分割か
- 【推奨】1つの目的（例: Teams会議のアーカイブ）を1フローで完結できるなら単一フローにする。
  子フロー呼び出しは接続・権限・エラー伝播が増え、レガシーパッケージでの取り回しも複雑になる。
- 【案件固有】今回は取得→整形→保存→台帳→ログを1つのインスタントクラウドフロー（手動トリガー）に集約した。
  当初は複数フロー案だったが、状態受け渡しと運用の単純さを優先して単一フローへ変更した
  （経緯は [教訓集](../knowledge/lessons_learned.md)）。
- 【推奨】分割を検討する目安: 実行時間上限（後述）に収まらない、再利用したい共通処理がある、
  権限境界が異なる、トリガー種別が異なる、のいずれか。

## トリガー種別【事実】
- 【事実】**手動（インスタントクラウドフロー）**: トリガー名 `manual`、`type: Request`、`kind: Button`。
  入力は `inputs.schema`（JSON Schema）で定義し、`required` 配列で必須を指定する。
  入力が無い場合も `{"type":"object","properties":{},"required":[]}` を持つ。

  ```json
  "triggers": {"manual": {"type": "Request", "kind": "Button",
    "inputs": {"schema": {"type": "object", "properties": {...}, "required": [...]}}}}
  ```

- 【事実】**スケジュール（繰り返し）**: トリガー名 `Recurrence`、`type: Recurrence`。
  `recurrence` と `evaluatedRecurrence` が**同内容で併記**される。

  ```json
  "triggers": {"Recurrence": {"type": "Recurrence",
    "recurrence":          {"frequency": "Hour", "interval": "5",
                            "startTime": "2026-07-01T01:00:00.000Z",
                            "timeZone": "Tokyo Standard Time"},
    "evaluatedRecurrence": {"frequency": "Hour", "interval": "5",
                            "startTime": "2026-07-01T01:00:00.000Z",
                            "timeZone": "Tokyo Standard Time"}}}
  ```

  - 【事実】`interval` は**数値ではなく文字列**（`"5"`）でエクスポートされる。
  - 【事実】`timeZone` は Windows 標準のタイムゾーン名（`Tokyo Standard Time` 等）。
  - 【要実環境確認】`evaluatedRecurrence` を省略したパッケージがインポートできるかは未確認。
    自作時は実エクスポートに倣って両方書くのが安全。
  - 出典: `references/raw/test_scheduled_flow_20260724121802.zip`（2026-07-24 の実エクスポート）
    → [../knowledge/sample_flow_reference_index.md](../knowledge/sample_flow_reference_index.md)

- 【事実】**コネクタのポーリング（自動）トリガー**: トリガー名はアクション表示名由来、`type` は
  **`OpenApiConnection`**（`Recurrence` ではない）。ポーリング間隔は**トリガーオブジェクト直下の
  `recurrence`** で指定し、`evaluatedRecurrence` が同内容で併記される。
  コネクタの操作は `inputs.host`（`apiId`/`connectionName`/`operationId`）で指定する。

  ```json
  "triggers": {"<表示名の空白を_に置換した名前>": {
    "recurrence":          {"frequency": "Minute", "interval": 1},
    "evaluatedRecurrence": {"frequency": "Minute", "interval": 1},
    "splitOn": "@triggerOutputs()?['body/value']",
    "type": "OpenApiConnection",
    "inputs": {"parameters": {...}, "host": {"apiId": "...", "connectionName": "...",
               "operationId": "..."}, "authentication": "@parameters('$authentication')"}}}
  ```

  - 【事実】`interval` は**数値**（`1`）。`Recurrence` トリガーでは文字列（`"5"`）だったため、
    **「interval は常に文字列」と一般化しない**。トリガー種別ごとに実エクスポートに倣う。
  - 【事実】`startTime` / `timeZone` は**省略できる**（ポーリング型では両方とも無い実例がある）。
  - 出典: `references/raw/sample_function_20260803105312.zip`（2026-08-03 の実エクスポート）
    → [../knowledge/sample_flow_reference_index.md](../knowledge/sample_flow_reference_index.md)

## splitOn（デバッチ）【事実】
- 【事実】トリガーに `splitOn` を指定すると、指定した配列の**各要素ごとに別々のフロー実行**が起動する
  （デバッチ）。書式は `"splitOn": "@triggerOutputs()?['body/value']"`。
- 【事実】`splitOn` の式もコネクタ封筒を経由する（`body/` を挟む）。→ [02](./02_expression_and_type_safety.md)
- 【要実環境確認】`splitOn` 有効時に後続アクションから `triggerOutputs()?['body']` を参照した場合の
  実際の形状（1件のオブジェクトになるか）は未検証。参照実装が無い状態で組まない。

## definition の必須キー【事実】
- 【事実】`properties.definition` に **`outputs` / `description` は無くてもよい**。
  必ずあるのは `metadata` / `$schema` / `contentVersion` / `parameters` / `triggers` / `actions` の6キー
  （両方を持つ実エクスポートと、両方を持たない実エクスポートの双方を確認済み）。
- 【事実】`connectionReferences` は `properties` 直下（`definition` の**中ではない**）。
  本リポジトリの実エクスポート4件・自作パッケージ5件すべてでこの位置。

## コネクタを使わないフローのパッケージ【事実】
- 【事実】コネクタを1つも使わないフローでは、レガシーパッケージの
  `apisMap.json` / `connectionsMap.json` がともに **`{}`**、
  ルート `manifest.json` の `resources` は**フロー1件のみ**で `dependsOn` は **`[]`**、
  `properties.connectionReferences` も **`{}`** になる。
  5ファイル構造自体は変わらない。
- 【事実】接続が無くても `definition.parameters` には `$authentication`（SecureObject）と
  `$connections`（Object）が入る。
- 出典: `references/raw/test_flow_20260724121852.zip`（2026-07-24 の実エクスポート）

## Scope（スコープ）による Try-Catch-Finally
- 【推奨】危険操作（外部呼び出し・ファイル作成・削除）は Scope で隔離する。
- 【事実】後続ハンドラは、前段 Scope の失敗時にも動くよう `runAfter` を
  `Failed` / `Skipped` / `TimedOut` に設定する。成功のみを継続する通常のアクションは既定（`Succeeded`）。
  - Catch 相当: メインScopeの `runAfter` に `Failed` `Skipped` `TimedOut` を指定。
  - Finally 相当: 成否に関わらず動かすため、直前アクションの全終了状態
    （`Succeeded` `Failed` `Skipped` `TimedOut`）を `runAfter` に列挙。
- 【事実】**ルート直下**の起点アクションは `"runAfter": {}` を明示する（Power Automate 標準エクスポート形式）。
  - 【事実】ただし **`Foreach` の子として先頭に置かれたアクションは `runAfter` キーごと省略された形**でも
    エクスポートされる（`references/raw/sample_function_20260803105312.zip`。2026-08-03 の実エクスポート）。
    「起点は必ず `{}` を明示」はルート直下について成り立つ事実であり、コンテナ内部まで一般化しない。
  - 【推奨】自作パッケージでは**位置を問わず `"runAfter": {}` を明示**する（両形式とも実在するため、
    明示側に統一するのが検証スクリプトを単純にできる）。
- 具体的なエラー継続・Status記録の設計は [08 エラー処理と冪等性](./08_error_handling_and_idempotency.md)。

## 変数初期化（Initialize variable）
- 【事実】「変数を初期化する（Initialize variable）」はフローの**トップレベル必須**。Scope の中には置けない。
- 【推奨】初期化はフロー先頭にまとめる。派生値（例: 有効日数）を Compose（作成）で先に算出し、
  それを参照して初期化する場合は、Compose→Initialize の順序を守る。
- 【推奨】同じ変数を二重に初期化しない（重複初期化はインポート/保存で問題になり得る）。

## ネスト深さ
- 【事実/案件固有】今回の最深ネストは7段（Scope > それぞれに適用する > Scope > それぞれに適用する > 条件 > 条件 > Scope、
  その中のリーフが8段目でちょうど上限）。深いネストは可読性と保守性を下げる。
- 【推奨】ネストは8段を超えない設計にする。超えそうなら Scope や子処理へ分解する。

## 並列オフ（変数更新ループの逐次化）
- 【事実】変数を更新する「それぞれに適用する（Apply to each）」「Do until（〜になるまで）」は**並列オフ必須**。
  定義上は `runtimeConfiguration.concurrency.repetitions` を `1` にする。
  並列のままだと Append/Increment の競合で件数が壊れる。
- 【推奨】ページング（nextLink 追跡）を含むループは特に逐次化する。

## 命名規則
- 【推奨】アクション名・変数名は英数字とアンダースコアのみ（空白・記号を避ける）。
- 【事実】アクション名は**フロー全体で一意**でなければならない。重複するとインポートが壊れる。
  今回 `Set_ReplyNextLink` が初期化用とループ更新用で重複し、外側を `Set_ReplyNextLink_First` に改名して解消した。
- 【推奨】**初期化用と更新用を名前で分ける**。初期化用に `_First` を付け（例 `Set_NextLink_First` と `Set_NextLink`）、
  役割を名前で判別できるようにする。
- 【推奨】変数名は役割が分かる接頭辞を付ける（例 `var`）。案件固有の実値は名前に埋め込まない。

関連: [00 コアルール](./00_power_automate_core_rules.md) / [02 式と型](./02_expression_and_type_safety.md) / [03 変数・配列](./03_variables_arrays_and_objects.md) / [08 エラー処理](./08_error_handling_and_idempotency.md) / [エラーカタログ](../knowledge/error_catalog.md)
