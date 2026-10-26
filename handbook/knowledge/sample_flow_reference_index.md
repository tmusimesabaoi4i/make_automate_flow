# サンプルフロー参照インデックス

過去に参照した雛形・実働サンプルの所在と、参考にした点・流用してはいけない点をまとめる。
**「実際のエクスポートだから正しい」とはみなさない。** 実働サンプルにも設計バグが含まれていた（下記参照）。関連ルール: [../rules/07_export_import_package_rules.md](../rules/07_export_import_package_rules.md)

参照資料はすべて**リポジトリ直下の `references/`** にある（2026-07-24 に `projects/migrate-chat-spo/references/` から移動。案件をまたいで参照するため）。原本は `references/raw/`、読み取り専用の展開は `references/extracted/`。いずれも**編集禁止**。

## tmp_20260716051507.zip（雛形サンプル）

- サンプル名: tmp_20260716051507.zip
- 保存場所: 原本 `references/raw/`、展開 `references/extracted/sample_extracted_ref/`。
- パッケージ形式: レガシーPower Automateパッケージ（ルートmanifest.json＋`Microsoft.Flow/flows/{guid}/(definition|apisMap|connectionsMap).json`）。ソリューション形式ではない。
- 主なコネクタ: Microsoft Teams（HttpRequestによるGraph呼び出し）／SharePoint
- 参考になる処理: パッケージのフォルダ構成・manifest.jsonの構造・connectionReferencesの形式（Invoker形式＋X-MS-APIM-Tokens参照式の認証）。ZIP直下階層をこの雛形と一致させることでインポート可能な構造を確保した。
- そのまま流用してはいけない処理: 案件固有の実値（Team ID・サイトURL等）は流用しない。雛形自体の設計ロジックの当否は個別確認していない。
- 確認済みエラー: 直接起因のエラーなし（構造参照のみに使用）。
- 利用時の注意: 匿名化（メールアドレス・creator.id・tenantId・接続GUID）を必ず行ってから流用する。
- 関連案件: migrate_chat_spo

## create_meeting_list_sample_20260716105612.zip（実働サンプル）とそのdefinition.json

- サンプル名: create_meeting_list_sample_20260716105612.zip
- 保存場所: 原本 `references/raw/`、展開 `references/extracted/create_meeting_list_sample_ref/`、整形済み定義 `references/extracted/sample2_definition_pretty.json`。実環境で作成・動作実績のあるエクスポートファイル。
- パッケージ形式: レガシーPower Automateパッケージ。connectionReferencesはEmbedded形式＋`authentication="@parameters('$authentication')"`（雛形のInvoker形式とは別の正当な形式）。
- 主なコネクタ: Microsoft Teams（HttpRequest）／SharePoint（PostItem等）／Content Conversion（HtmlToText）
- 参考になる処理:
  - Graph URLの`uriComponent()`エンコード構成（チャネルID・メッセージIDに`:`や`@`を含む場合の実際の動作例）
  - `body('Teams HttpRequest')`がGraph応答JSONそのものである実例（Apply to eachの入力が`body('ParseJson')?['value']`で動作しており、ParseJsonのcontentがGraph応答であることの根拠になる）
  - HtmlToTextのパラメータキーが`Content`であることの実例
  - SharePoint PostItemの内部列名の形式（日本語表示名列が`OData__xHHHH_`形式になる例）
  - connectionReferencesのEmbedded形式の実例
- そのまま流用してはいけない処理:
  - `SetVariable`による`union(createArray(item()), coalesce(...))`の毎回上書き（配列蓄積ではなく上書きになり、複数返信の添付が最後の1件しか残らないバグ）。加えて返信オブジェクト自体が添付配列へ混入していた（後段のFilterで偶然除去されていただけ）。
  - **取得前に既存SharePoint項目を全削除する順序**（Graph取得が失敗・0件でも削除済みでロールバック不能。破壊的処理は新規データ取得の成功後にのみ行う）。
  - ページング処理が無い（1ページ分＝`$top=50`のみ取得。50件超のデータは取得漏れになる）。
  - Parse JSONのスキーマが封筒形（`statusCode`/`headers`/`body`）である一方、実際の参照パスは`?['value']`で不一致（トップレベルの`required`が無いため偶然エラーにならず素通りしていた「デッドスキーマ」）。
  - SharePointへ渡す値式の末尾に`\n`が混入し、列値にそのまま改行が保存されていた。
  - トリガーのスキーマが空、URL・リストGUIDがハードコードされていた。
  - タイトル列はlastModifiedDateTimeのJST変換、投稿日時列はcreatedDateTimeのUTCそのまま、というように同一項目内でタイムゾーン基準が不整合だった。
  - メンション情報を`mentions?[0]?['mentionText']`のように先頭決め打ちで参照していた（複数メンション時の妥当性の検証なし）。
- 確認済みエラー: このサンプル自体のインポート・保存エラーは確認していないが、上記の設計バグ（累積ロジック・タイムゾーン不整合・デッドスキーマ等）を機械解析で発見した。
- 利用時の注意: 「実環境で作成された＝正しい実装」ではない。個々のロジックは必ず機械解析・レビューしてから流用する。
- 関連案件: migrate_chat_spo

## CreateKnowledgeList_20260716161116.zip（実働サンプル・SharePointリスト作成の正典）

- サンプル名: CreateKnowledgeList_20260716161116.zip
- 保存場所: 原本 `references/raw/`、展開 `references/extracted/reference_original/`。
- パッケージ形式: レガシーパッケージ。connectionReferences は Embedded 形式＋`authentication="@parameters('$authentication')"`。
- 主なコネクタ: SharePoint（`HttpRequest` による REST 構築のみ）。33アクション・変数不使用（Compose で定数保持）。
- 実績: **実環境で作成・動作実績のあるエクスポート**。
- 参考になる処理（**SharePoint REST の形式はここが正典**）:
  - リスト作成 `POST _api/web/lists`（verbose・`{"__metadata":{"type":"SP.List"},"BaseTemplate":100,...}`）
  - リスト取得 `GET _api/web/lists/GetByTitle('..')?$select=Id,Title&$expand=RootFolder`（nometadata）
  - 添付設定 `POST GetByTitle('..')` ＋ `IF-MATCH:*` ＋ `X-HTTP-Method:MERGE`（`{"EnableAttachments": true}`）
  - 列作成 `POST .../fields/createFieldAsXml`（`SP.XmlSchemaFieldCreationInformation`・`Options:0`）
  - ビュー列全削除 `POST .../defaultView/viewfields/removeAllViewFields()`（**nometadata・ボディなし**）
  - ビュー列追加 `POST .../viewfields/AddViewField('<内部名>')`（verbose＋MERGE＋`{"__metadata":{"type":"SP.View"},"SetAsDefaultView":true}`）
  - **Title の Required 解除** `POST .../fields/getbyinternalnameortitle('Title')`（**nometadata**＋MERGE、`{"Required": false}`）
  - パターン集として整理済み: [sharepoint_rest_list_provisioning.md](sharepoint_rest_list_provisioning.md)
- そのまま流用してはいけない処理:
  - `dataset`（サイトのアドレス）は**静的リテラル**。動的サイトを扱う場合の実績にはならない。
  - Lookup 列（`KnowledgePrimaryTag`）は別リスト依存。汎用化しない。
  - 実接続名（`connectionName` の実値）を流用しない。**匿名化してから使う**。
- 関連案件: migrate-chat-spo（provision-archive-lists の雛形）／create_initialized_sharepoint_list（REST形式の出典）

## test_flow_20260724121852.zip（最小構成・接続なしの実エクスポート）

- サンプル名: test_flow_20260724121852.zip
- 保存場所: 原本 `references/raw/`（展開は未作成。必要なら `references/extracted/` 配下へ）。
- パッケージ形式: レガシーパッケージ（5ファイル構造）。
- 実績: **2026-07-24 に実環境で作成・エクスポートされた実物**。
- 内容: 手動トリガー（`manual` / `Request` / `kind: Button`、入力スキーマは空）＋ Compose 1件のみ。
- 参考になる点:
  - 【事実】**コネクタを1つも使わないフローでは `apisMap.json` / `connectionsMap.json` がともに `{}`、
    ルート `manifest.json` の `resources` はフロー1件のみで `dependsOn` は `[]`、
    `connectionReferences` も `{}`** になる。接続なしパッケージの最小形の正典。
  - 【事実】`definition` は `metadata` / `$schema` / `contentVersion` / `parameters` / `triggers` /
    `actions` / `outputs` / `description` を持つ。`outputs` は `{}`、`description` に説明文が入る。
  - 【事実】`parameters` は接続が無くても `$authentication`（SecureObject）と `$connections`（Object）を持つ。
  - 【事実】**アクション名に日本語（`作成`）が使える**（実エクスポートで確認）。ただし本リポジトリの
    命名規則は英数字＋アンダースコア（[../rules/01_flow_architecture_rules.md](../rules/01_flow_architecture_rules.md)）。
- 利用時の注意: `definition.metadata` に実エクスポート特有の値
  （`creator.id` / `creator.tenantId` / `lastModifiedBy` / `clientLastModifiedTime` 等）が含まれる。
  **流用時は必ず匿名化する**（[../rules/07_export_import_package_rules.md](../rules/07_export_import_package_rules.md)）。
- 関連案件: 共通（新規フローの最小雛形）

## test_scheduled_flow_20260724121802.zip（Recurrence トリガーの実エクスポート）

- サンプル名: test_scheduled_flow_20260724121802.zip
- 保存場所: 原本 `references/raw/`。
- パッケージ形式: レガシーパッケージ（5ファイル構造）。接続なし（`apisMap`/`connectionsMap` とも `{}`）。
- 実績: **2026-07-24 に実環境で作成・エクスポートされた実物**。
- 参考になる点: 【事実】**スケジュール実行（繰り返し）トリガーの定義形式**。本リポジトリで
  Recurrence トリガーの実物を確認できる唯一の資料。

  ```json
  "triggers": {
    "Recurrence": {
      "type": "Recurrence",
      "recurrence": {
        "frequency": "Hour",
        "interval": "5",
        "startTime": "2026-07-01T01:00:00.000Z",
        "timeZone": "Tokyo Standard Time"
      },
      "evaluatedRecurrence": { ...recurrence と同一... }
    }
  }
  ```

  - 【事実】トリガー名は `Recurrence`、`type` も `Recurrence`。
  - 【事実】`interval` は**数値ではなく文字列**（`"5"`）でエクスポートされる。
  - 【事実】`timeZone` に Windows 標準のタイムゾーン名（`Tokyo Standard Time`）を指定できる。
  - 【事実】`evaluatedRecurrence` が `recurrence` と同内容で併記される。
  - 【要実環境確認】`evaluatedRecurrence` を省略したパッケージがインポートできるかは未確認。
    自作する場合は実エクスポートに倣って**両方書く**のが安全。
- 関連案件: 共通（スケジュール実行フローを作る場合の雛形）

## sample_function_20260803105312.zip（共有メールボックス→Teams投稿。**コネクタのポーリングトリガーの唯一の実例**）

- サンプル識別名: `shared-mailbox-to-teams-notify-20260803`
- 保存場所: 原本 `references/raw/sample_function_20260803105312.zip`、展開 `references/extracted/shared-mailbox-to-teams-notify-20260803/`。
- 解析文書: [../../references/shared-mailbox-to-teams-notify-20260803_analysis.md](../../references/shared-mailbox-to-teams-notify-20260803_analysis.md)
- 登録日: 2026-08-03（パッケージ生成 2026-08-03）。
- パッケージ形式: レガシーパッケージ（5ファイル構造）。connectionReferences は Embedded 形式＋`authentication="@parameters('$authentication')"`。
- 主なコネクタ: **Office 365 Outlook**（`shared_office365`。当リポジトリ初出）／**Microsoft Teams**（`shared_teams`。`PostMessageToConversation` は初出）。4アクション・変数不使用。
- フローの用途: 共有メールボックスの新着メールを起点に、メール取得→既読化→Teams投稿を行う**試作フロー**。フロー表示名は自動生成の既定名のまま。
- 実環境での動作確認状況: **本リポジトリではインポート・保存・実行のいずれも未実施**。エクスポート元環境で保存された形跡（`creationSource: Portal`）はあるが、**動作の正しさは確認していない**。
- 参考にできる主要パターン:
  - 【事実】**コネクタのポーリングトリガー形式**（`type: OpenApiConnection` ＋ トリガー直下の `recurrence`/`evaluatedRecurrence` ＋ `splitOn`）。本リポジトリで確認できる唯一の実例
    → [../rules/01_flow_architecture_rules.md](../rules/01_flow_architecture_rules.md)
  - 【事実】2コネクタ構成の `dependsOn` 4件・`apisMap`/`connectionsMap` 各2エントリの整合例。
    ただし**同規模の実例は `tmp_20260716051507.zip` に既にある**ため、構造面での新規性は無い（整合の取れた追加検体）。
  - 【事実】`GetEmailsV3` / `MarkAsRead_V3` / `PostMessageToConversation` の operationId と入力キーの実例
    → [connector_action_notes.md](connector_action_notes.md)
  - 【事実】必須パラメータの無いアクションは `inputs.parameters` キーごと省略されてエクスポートされる。
  - 【事実】`definition` に `outputs` / `description` キーが無くても成立する。
- そのまま流用してはいけない処理:
  - **トリガー出力がどのアクションからも参照されていない**。`triggerOutputs()` の出現は `splitOn` のみで、新着メールの内容は一切使われない。「新着を受けてそのメールを処理する」結線の参考にはならない。
  - **Apply to each の入力に配列保証が無い**（`coalesce(..., json('[]'))` 不使用）。[../rules/00_power_automate_core_rules.md](../rules/00_power_automate_core_rules.md) コアルール5に違反。
  - **エラー処理・再試行・タイムアウトが皆無**（Scope・失敗系 `runAfter`・`retryPolicy`・`limit` すべて0件）。
  - **匿名化されていない**。共有メールボックスアドレス・個人メールアドレス・作成者GUID・テナントID・接続GUIDが素のまま残る。流用時は必ず匿名化する（[../rules/07_export_import_package_rules.md](../rules/07_export_import_package_rules.md)）。
  - Teams投稿の `location` 実値は `"Chat with Flow bot"`。公式リファレンスの許可値表記（`Channel`/`Chat`）と一致しないため、**チャネル投稿にそのまま流用できない**。
  - アクション内部名が日本語。本リポジトリの命名規則は英数字＋アンダースコア（[../rules/01_flow_architecture_rules.md](../rules/01_flow_architecture_rules.md)）。
- 確認済みエラー: なし（未インポートのため）。上記は**機械解析で検出した設計上の指摘**であり、発生済みエラーではない。
- 利用時の注意: **実環境で作られたエクスポートだが「正しい実装」ではない**。`create_meeting_list_sample`（累積ロジックのバグ）に続く3例目として、本索引冒頭の原則を補強する事例。
  **パッケージ構造とトリガー形式のみを参考にし、フロー設計は参考にしない。**
- 推奨される利用場面: 共有メールボックス監視フロー／Teams通知フローの**トリガー定義とコネクタ入力キーの雛形**。2コネクタ構成パッケージの構造雛形。
- 関連案件: 共通（未着手。共有メールボックス解析＋Teams投稿フローの検討資料）

## create_initialized_sharepoint_list（自作・実環境インポート/実行実績あり）

- サンプル名: `CreateInitializedSharePointList`
- 保存場所: `projects/create_initialized_sharepoint_list/flows/create-initialized-list/`
- パッケージ形式: レガシーパッケージ。connectionReferences は Invoker形式＋匿名GUID。
- 主なコネクタ: **SharePoint 1本のみ**（`HttpRequest` による REST。176アクション・16HTTP要求）。
- 実績: **2026-07-24 に実環境でインポート・実行に成功**（`status: Created`。SharePoint画面でも確認）。
- 参考になる処理:
  - **`dataset`（サイトのアドレス）に式を指定して任意サイトを対象にする**実装。実環境で保存・実行の実績あり。
  - **リストIDのみで対象を特定する**破壊的操作の書き方（`GetByTitle(` を1件も使わない）。
  - **拡張リッチテキスト列**（`Type="Note"` ＋ `RichTextMode="FullHtml"`）の作成と検証。
  - 既定ビューの再構築（`views(guid'..')/viewfields/removeAllViewFields()` → `AddViewField()` → `ViewFields` 検証）。
  - **安全要件の機械検査**（`source/validate_list_flow.py`）: `GetByTitle(` 0件／書き込みURIのID固定／
    ガード配下の確認／同名確認と作成の順序／作成失敗経路にRESTが無いこと。
    **破壊的操作を伴うフローを作るときの検査テンプレートとして流用できる。**
  - REST形式のパターン集: [sharepoint_rest_list_provisioning.md](sharepoint_rest_list_provisioning.md) §11〜§14
- そのまま流用してはいけない処理:
  - 結果JSONの構造・エラーコード体系は本案件の要件に合わせたもの。
  - フォームからの列非表示化は**実装していない**（REST の実在確認が取れなかったため制約として記録する方針）。
- 利用時の注意: **同名リストが存在する場合の経路（`AlreadyExists`）は実機で未発火**。
  既存リスト保護は定義の構造から静的に保証されているが、実機確認は未実施。
- 関連案件: create_initialized_sharepoint_list

## teams_post_url_flows の2フロー（自作・実環境インポート/実行実績あり）

- サンプル名: `Flow1_GetTeamsChannelPostFromUrl` / `Flow2_GetAllTeamsChannelPostRepliesFromUrl`
- 保存場所: `projects/teams_post_url_flows/flows/<フロー>/`（`source/` に生成スクリプト、`release/` にZIP）
- パッケージ形式: レガシーPower Automateパッケージ。connectionReferencesはInvoker形式＋X-MS-APIM-Tokens参照式。
- 主なコネクタ: **Microsoft Teams 1本のみ**（`HttpRequest`によるGraph呼び出し）。SharePoint等は不使用。
- 実績: **2026-07-24に実環境でインポート・実行に成功**（Flow1で投稿本文、Flow2で返信の取得を確認）。
- 参考になる処理:
  - **Teamsコネクタ1本だけで完結する最小構成**のレガシーパッケージ（API1＋接続1、`dependsOn`は2要素）。
    コネクタ数が少ない構成の雛形として、migrate-chat-spo（3コネクタ）より単純。
  - **Teams投稿URLの解析**（名前アンカー方式のクエリ抽出・パス分割・`decodeUriComponent()`）。
    → [expression_examples.md](expression_examples.md) 15-A〜15-C
  - **Graph の単一メッセージ取得** `/messages/{messageId}` の実装と動作実績。
  - **Scope による Try/Catch/Finally**。Catch用Scopeの`runAfter`を最終Scope1本だけに張る形
    （複数列挙のAND判定でハンドラが発火しない問題を回避）。
  - **想定内エラーと想定外エラーで結果生成の経路を分ける**構成。成功側だけが`body('<コネクタ>')`を
    参照し、失敗側・ハンドラは変数のみを参照するため、コネクタ未実行でも式が壊れない。
  - **検証スクリプトの拡張例**（`source/validate_flow*.py`）: 不正な`@`位置検査・**関数許可リスト検査**・
    コネクタ必須パラメータ検査・Foreach並列オフ検査・トリガー検査・実値混入検査・GUID3点一致。
  - **ZIP再展開検査**（`validation/extract_check.py`）: 展開結果と`source/package`のSHA-256一致まで確認する。
  - **WDL式のミニ評価器による回帰テスト**（`tools/wdl_eval.py` ＋ 各案件の `tests/run_url_parse_tests.py`）:
    `definition.json`の式そのものをオフライン評価し、URL解析を実機なしで検証する。
    評価器は案件横断の共通ツール（`tools/`）で、案件ごとに複製しない。
- そのまま流用してはいけない処理:
  - 結果JSONの構造（`identifiers`/`message`/`replies`等）は本案件の要件に合わせたもの。用途に応じて設計し直す。
  - `from.email`を空文字で埋めている点は「Graphが返さないため捏造しない」判断であり、
    メールアドレスが必要なら`/users/{id}`の追加取得が要る。
- 確認済みエラー: 本パッケージ起因のインポート・保存エラーは発生していない。
- 利用時の注意: **返信51件超の`@odata.nextLink`追跡（複数ページ）は未確認**。
  ページング部分を流用する場合は、1ページに収まらないデータで必ず実機確認する
  （1ページで収まると、ページングが壊れていても正常に見える）。
- 関連案件: teams_post_url_flows

---
関連: [connector_action_notes.md](connector_action_notes.md) / [expression_examples.md](expression_examples.md) / [../checklists/design_review_checklist.md](../checklists/design_review_checklist.md)
