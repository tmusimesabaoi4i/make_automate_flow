# サンプルフロー解析 — shared-mailbox-to-teams-notify-20260803

共有メールボックスの新着メールをトリガーに、メール取得・既読化・Teams投稿を行うサンプルフローの解析。
本サンプルは**参照専用**であり、案件フローとして採用したものではない。原本・展開結果とも**編集していない**。

## 表記の約束

| 記号 | 意味 |
|---|---|
| 【事実】 | **ファイルから直接確認できた**内容。definition.json / manifest.json の実データ |
| 【推定】 | ファイルの内容から解析者が導いた推論。実データによる裏付けは無い |
| 【要実環境確認】 | 実環境で動かさないと確定できない事項。**「動く」と断定しない** |
| 【公式・要再確認】 | 公式コネクタリファレンスを参照したが、**本セッションでは正確な読み取りに失敗**した事項（後述 §12-B） |

実値（メールアドレス・接続GUID・テナントID）は本文書に**転記しない**。所在のみ §3.6 に記す。
関連ルール: [../handbook/rules/07_export_import_package_rules.md](../handbook/rules/07_export_import_package_rules.md) /
[../handbook/knowledge/sample_flow_reference_index.md](../handbook/knowledge/sample_flow_reference_index.md)

---

## 1. 原本情報

| 項目 | 値 |
|---|---|
| 受領ファイル名 | `sample_function_20260803105312.zip` |
| 登録先（原本・編集禁止） | `references/raw/sample_function_20260803105312.zip` |
| 展開先（読み取り専用） | `references/extracted/shared-mailbox-to-teams-notify-20260803/` |
| サンプル識別名 | `shared-mailbox-to-teams-notify-20260803` |
| ZIPサイズ | 3,496 bytes（5エントリ） |
| 登録日 | 2026-08-03 |
| パッケージ表示名 (`details.displayName`) | `sample_function` |
| パッケージ生成時刻 (`details.createdTime`) | `2026-08-03T10:53:12Z` |
| フロー最終編集時刻 (`clientLastModifiedTime`) | `2026-08-03T10:52:40Z` |
| 出所 | 【推定】実環境（Portal）で作成されたフローのエクスポート。`creationSource`/`modifiedSources` とも `Portal`、`provisioningMethod` は `FromDefinition` |

【事実】同名ファイルは `references/raw/` に存在しなかったため、**上書き・改名は発生していない**。
【事実】原本は移動ではなくコピーで登録し、`C:\Users\yohei\Downloads\` の元ファイルは残存している。

---

## 2. SHA-256

| 対象 | SHA-256 |
|---|---|
| 原本ZIP（Downloads 側 / `references/raw/` 側とも同一） | `7F7A3638D4CD2B2DBE563BE658033EAE8C6FE3D9FC3C841D15D01A81AF43F112` |

展開後5ファイルの SHA-256（先頭16桁）:

| ファイル | サイズ | SHA-256（先頭16桁） |
|---|---|---|
| `manifest.json` | 2,384 | `F89F0F69D8B162CC` |
| `Microsoft.Flow/flows/manifest.json` | 99 | `9645C6667DCFD2DB` |
| `Microsoft.Flow/flows/{flowAssetGuid}/definition.json` | 3,807 | `2D43BCBF6A404C29` |
| `Microsoft.Flow/flows/{flowAssetGuid}/apisMap.json` | 113 | `3D5F4E4EC8343002` |
| `Microsoft.Flow/flows/{flowAssetGuid}/connectionsMap.json` | 113 | `3FC00A6365E1AA7C` |

---

## 3. パッケージ構造

### 3.1 形式判定【事実】

**レガシーPower Automateパッケージ**（Dataverseソリューション形式ではない）。
`solution.xml` / `customizations.xml` / `[Content_Types].xml` は存在しない。
`__MACOSX` / `.DS_Store` の混入なし。ファイル数はちょうど5。

```text
manifest.json                                        （ルート: schema / details / resources）
Microsoft.Flow/flows/manifest.json                   （packageSchemaVersion / flowAssets.assetPaths）
Microsoft.Flow/flows/{flowAssetGuid}/definition.json （フロー本体）
Microsoft.Flow/flows/{flowAssetGuid}/apisMap.json    （論理名→APIリソースGUID）
Microsoft.Flow/flows/{flowAssetGuid}/connectionsMap.json（論理名→接続リソースGUID）
```

[07 エクスポート/インポートルール](../handbook/rules/07_export_import_package_rules.md) の5ファイル構造と**完全一致**。

### 3.2 GUID の3点一致【事実】

| 観点 | 値 |
|---|---|
| ルート `manifest.json` の `hierarchy:"Root"` リソースキー | `3439fdd0-…` |
| `Microsoft.Flow/flows/` 配下のフォルダ名 | `3439fdd0-…` |
| `Microsoft.Flow/flows/manifest.json` の `flowAssets.assetPaths[0]` | `3439fdd0-…` |

→ **3点一致（合格）**。
【事実】`definition.json` の `name` / `id` は別GUID（`ccbb1e7d-…`）。既知の**二重GUID構造**どおりで、一致不要。

### 3.3 接続参照の対応【事実】

| 論理名 | apisMap（APIリソースGUID） | connectionsMap（接続リソースGUID） | manifest上の表示名 |
|---|---|---|---|
| `shared_office365` | `45a8c6d6-…` | `5cb1402c-…` | Office 365 Outlook |
| `shared_teams` | `149c74ad-…` | `e1fddde6-…` | Microsoft Teams |

- 【事実】`apisMap` / `connectionsMap` の値は、ルート `manifest.json` の `resources` キーと**全件一致**。
- 【事実】Rootリソースの `dependsOn` は **4件**（API2＋接続2）で過不足なし。順序は API→接続→API→接続。
- 【事実】APIリソースは `configurableBy: "System"` / `dependsOn: []`、接続リソースは `configurableBy: "User"` / `creationType: "Existing"` / `dependsOn: [対応するAPIリソース]`。
- 【事実】`definition.json` の `properties.connectionReferences`（※`definition` の中ではなく `properties` 直下）のキーは `shared_office365` / `shared_teams` の2件で、全アクションの `host.connectionName` と**完全一致**。連番サフィックス（`-2` 等）は付いていない。
- 【事実】接続参照は **Embedded 形式**（`source: "Embedded"`）＋ `authentication: "@parameters('$authentication')"`。
  これは [07](../handbook/rules/07_export_import_package_rules.md) の方式(a)。当リポジトリの自作フローが採用している Invoker 形式（方式(b)）とは**別方式**。

### 3.4 definition のトップレベル【事実】

| フィールド | 値 |
|---|---|
| `properties.apiId` | `/providers/Microsoft.PowerApps/apis/shared_logicflows` |
| `properties.displayName` | `新しいメールが共有メールボックスに届いたとき (V2) -> メールを取得する (V3),For each,チャットまたはチャネルでメ...`（末尾は `...` で切れている） |
| `properties.flowFailureAlertSubscribed` | `false` |
| `properties.isManaged` | `false` |
| `$schema` | `.../2016-06-01/workflowdefinition.json#` |
| `contentVersion` | `"undefined"`（リテラル文字列） |
| `parameters` | `$authentication`（SecureObject）/ `$connections`（Object） |
| `definition` のキー | `metadata` / `$schema` / `contentVersion` / `parameters` / `triggers` / `actions` |

- 【事実】**`outputs` キーと `description` キーが存在しない**。`test_flow_20260724121852.zip` では両方存在していたため、**この2キーは必須ではない**ことが実エクスポートで確認できた。
- 【推定】`displayName` はアクション名から自動生成される既定名がそのまま残っている（`->` 連結・`...` 切り詰め）。**フロー名を一度も付け替えていない**＝試作・検証目的のフローと考えられる。

### 3.5 インポート時に置換・再設定が必要な設定

| 対象 | 内容 | 必要な操作 |
|---|---|---|
| Office 365 Outlook 接続 | 匿名化されていない実接続GUIDを保持 | インポート時に接続を選択し直す |
| Microsoft Teams 接続 | 同上 | インポート時に接続を選択し直す |
| トリガー `mailboxAddress` | 特定の共有メールボックスアドレスがハードコード | 監視対象メールボックスに変更 |
| `body/recipient`（Teams投稿先） | 特定個人のメールアドレスがハードコード | 投稿先に変更 |
| `body/messageBody` | `<p class="editor-paragraph">message</p>` 固定 | 実際の通知本文に変更 |
| `metadata.creator` / `lastModifiedBy` / `tenantId` | 実値を保持 | 【推奨】流用時は空オブジェクト・新規GUIDへ |
| `packageTelemetryId` | エクスポート回ごとの識別子 | 流用しない（新規発行） |

### 3.6 センシティブな実値の所在【事実】※値は転記しない

| 種別 | 件数 | 所在（JSONパス） |
|---|---|---|
| メールアドレス（共有メールボックス） | 1 | `definition.json` → `properties.definition.triggers.<トリガー>.inputs.parameters.mailboxAddress` |
| メールアドレス（個人） | 3箇所 | `definition.json` → Teams投稿アクションの `inputs.parameters['body/recipient']`／`manifest.json` → 接続リソース2件の `details.displayName` |
| 作成者ユーザーGUID | 2箇所 | `definition.json` → `properties.definition.metadata.creator.id` / `.lastModifiedBy` |
| テナントID | 1 | `definition.json` → `properties.definition.metadata.creator.tenantId` |
| 接続GUID（ハイフン無し32桁） | 2 | `definition.json` → `properties.connectionReferences.*.connectionName` |
| 接続リソースGUID | 2 | `manifest.json` `resources` キー ／ `connectionsMap.json` の値 |

- 【事実】ルート `manifest.json` の `details.creator` は `"N/A"`（エクスポート機構が既定で伏せる箇所）。
  一方で**接続リソースの `details.displayName` にはユーザーのメールアドレスがそのまま入る**。
  `creator: "N/A"` を見て「匿名化済み」と誤認してはならない。
- 【事実】`definition.metadata.creator` は**実値を保持**しており、匿名化されていない。
- 【判定】**本パッケージをそのまま第三者へ配布してはならない。** 流用時は [07](../handbook/rules/07_export_import_package_rules.md) の匿名化手順を必ず通す。

### 3.7 パッケージとしての不足・不整合【事実】

機械走査の結果、**パッケージ構造上の不足・不整合は検出されなかった**。

| 検査観点 | 結果 |
|---|---|
| JSON構文（5ファイル） | 全件パース成功 |
| 5ファイル構造 / ルート階層 | 合格 |
| `__MACOSX` / `.DS_Store` | なし |
| フロー資産GUIDの3点一致 | 合格 |
| apisMap / connectionsMap ↔ manifest resources | 全件一致 |
| `dependsOn` の過不足 | なし（4件） |
| connectionReferences ↔ `host.connectionName` | 全件一致 |
| アクション名の重複 | 0件 |
| `runAfter` の兄弟整合 | 合格 |
| 不正な位置の `@` | 0件 |
| SetVariable 自己参照 | 0件（SetVariable自体が0件） |
| 変数の初期化＝参照 | N/A（変数を使用していない） |
| コネクタ出力の `body/` 欠落 | 0件（§7 参照） |
| 匿名化リーク | **検出あり（§3.6）** — 構造の不整合ではなく取り扱い上の問題 |

---

## 4. フローの目的

### 4.1 表示名から読み取れる意図【推定】

共有メールボックスに新着メールが届いたことを起点に、
**メールを取得 → 各メールを既読にする → Teams で通知する**という流れを意図したもの。

### 4.2 定義から確認できる実際の挙動【事実】

**トリガーの出力は、後続のどのアクションからも参照されていない。**
`definition.json` 中の `triggerOutputs()` の出現は `splitOn` の1箇所のみで、
アクションの入力には1件も現れない。

したがって定義上、以下が成立する。

- 【事実】新着メールの内容（件名・本文・送信者・ID）は**一切使われていない**。
- 【事実】既読化の対象は、トリガーが受け取ったメールではなく `メールを取得する_(V3)` の戻り値。
- 【事実】`メールを取得する_(V3)` には `inputs.parameters` が**存在しない**（`host` と `authentication` のみ）。
  すなわち取得対象メールボックス・フォルダ・件数はすべて**コネクタ既定値まかせ**。
- 【事実】Teams投稿の本文は固定文字列で、メール由来の情報を含まない。

【推定】結果として本フローは「共有メールボックスに新着があるたびに、**別の（接続アカウント自身の）メールボックスの**
既定件数のメールを既読にし、固定文言をTeamsへ投げる」という挙動になる。
これは 4.1 の意図とは異なる。**作りかけ、または各アクションの配置だけを試した検証用フロー**と判断する。

【要実環境確認】`GetEmailsV3` を `parameters` なしで実行したときの実際の対象メールボックス・
フォルダ・取得件数。上記は「トリガー出力への参照が無い」という**定義上の事実**からの推定であり、
コネクタ既定値の実挙動は実機で確認する必要がある。

### 4.3 基本情報

| 項目 | 内容 |
|---|---|
| フローの表示名 | 自動生成の既定名（§3.4）。**実質的な命名なし** |
| トリガー | Office 365 Outlook / `SharedMailboxOnNewEmailV2`（ポーリング型・1分間隔・`splitOn` あり） |
| 使用コネクタ | Office 365 Outlook（`shared_office365`）／Microsoft Teams（`shared_teams`） |
| 主な入力 | トリガーの `mailboxAddress`（固定値）。ユーザー入力パラメータは無し |
| 主な出力 | なし（`definition.outputs` キー自体が無い）。副作用としてメールの既読化とTeams投稿 |
| 外部依存 | Exchange Online（共有メールボックス）／Microsoft Teams |
| 接続・権限上の前提 | 【推定】共有メールボックスへのアクセス権、Teams のチャット送信権限。【要実環境確認】共有メールボックスの権限付与形態（フルアクセス/送信可否）とDLPポリシー適合 |

---

## 5. 使用コネクタ

### 5.1 コネクタ一覧【事実】

| 論理名 | apiId | 表示名 | 標準/プレミアム |
|---|---|---|---|
| `shared_office365` | `/providers/Microsoft.PowerApps/apis/shared_office365` | Office 365 Outlook | 【推定】標準（`Microsoft.PowerApps/apis` 配下・プレミアム表記なし） |
| `shared_teams` | `/providers/Microsoft.PowerApps/apis/shared_teams` | Microsoft Teams | 【事実】標準（当リポジトリで実環境実績あり） |

- 【事実】**Office 365 Outlook コネクタは当リポジトリ初出**。既存の記録は Teams / SharePoint / Content Conversion のみ。
- 【事実】**Teams の `PostMessageToConversation` も当リポジトリ初出**。既存の Teams 使用実績は `HttpRequest`（Graph呼び出し）のみ。

### 5.2 operationId と英語名の対応

ユーザー依頼により英語名を併記する。**日本語名はファイルから確認した事実**、英語名は公式コネクタリファレンス由来。

| # | 種別 | operationId【事実】 | 日本語表示名【事実】（アクション内部名から復元） | 英語表示名【公式・要再確認】 |
|---|---|---|---|---|
| T | トリガー | `SharedMailboxOnNewEmailV2` | 新しいメールが共有メールボックスに届いたとき (V2) | When a new email arrives in a shared mailbox (V2) |
| 1 | アクション | `GetEmailsV3` | メールを取得する (V3) | Get emails (V3) |
| 2 | アクション | `MarkAsRead_V3` | 開封済みまたは未読としてマークする (V3) | Mark as read or unread (V3) |
| 3 | アクション | `PostMessageToConversation` | チャットまたはチャネルでメッセージを投稿する | Post message in a chat or channel |

- 【事実】日本語表示名は、アクション内部名（`メールを取得する_(V3)` 等）の `_` を空白に戻したもの。
  Power Automate は**表示名の空白を `_` に置換して内部名を作る**（本サンプルで4件とも一貫）。
- 【公式・要再確認】英語表示名は 2026-08-03 に learn.microsoft.com のコネクタリファレンスを参照して得たもの。
  ただし同一ページへの再取得で**パラメータ表の内容が2回とも食い違った**ため（§12-B）、
  **表示名以外（パラメータのキー名・必須/任意）は本文書では公式資料由来の情報を採用しない**。

### 5.3 パラメータのフラット化キー【事実】

Teams投稿アクションの入力キーは `body/recipient` / `body/messageBody`。
これは動的スキーマを持つ `body` パラメータを**スラッシュでフラット化**した形式で、
既知の `item/Title`（SharePoint PostItem）・`parameters/uri`（SharePoint HttpRequest）と**同じ規則**。

---

## 6. 処理アウトライン

### 6.1 実行順（`tools/gen_outline.py` の出力）

```text
trigger: 新しいメールが共有メールボックスに届いたとき_(V2) (OpenApiConnection)
  1 メールを取得する_(V3)  <OpenApiConnection> [shared_office365/GetEmailsV3]  runAfter: -
  2 For_each  <Foreach> [in: @outputs('メールを取得する_(V3)')?['body/value']]  runAfter: メールを取得する_(V3)(Succeeded)
  3   開封済みまたは未読としてマークする_(V3)  <OpenApiConnection> [shared_office365/MarkAsRead_V3]  runAfter: -
  4 チャットまたはチャネルでメッセージを投稿する  <OpenApiConnection> [shared_teams/PostMessageToConversation]  runAfter: For_each(Succeeded)
--- total actions: 4 ---
```

【事実】総アクション数4／最大ネスト深さ2／分岐（Condition・Switch）なし／Scope なし／Do until なし／変数なし。

### 6.2 トリガー詳細【事実】

```json
"新しいメールが共有メールボックスに届いたとき_(V2)": {
  "recurrence":          {"frequency": "Minute", "interval": 1},
  "evaluatedRecurrence": {"frequency": "Minute", "interval": 1},
  "splitOn": "@triggerOutputs()?['body/value']",
  "type": "OpenApiConnection",
  "inputs": {
    "parameters": {
      "mailboxAddress": "{sharedMailboxAddress}",
      "importance": "Any",
      "hasAttachments": false,
      "includeAttachments": false,
      "folderId": "Inbox"
    },
    "host": {"apiId": ".../shared_office365", "connectionName": "shared_office365",
             "operationId": "SharedMailboxOnNewEmailV2"},
    "authentication": "@parameters('$authentication')"
  }
}
```

当リポジトリで**初めて確認できたトリガー形式**であり、以下は再利用価値が高い。

- 【事実】**コネクタのポーリングトリガーは `type: "OpenApiConnection"`** であり、`type: "Recurrence"` ではない。
  ポーリング間隔は**トリガーオブジェクト直下の `recurrence`** で指定し、`evaluatedRecurrence` が同内容で併記される。
  → 既存記録（`manual`/`Request` と `Recurrence`/`Recurrence`）に次ぐ**第3のトリガー形式**。
- 【事実】`recurrence.interval` は**数値 `1`**。`test_scheduled_flow_20260724121802.zip` の `Recurrence` トリガーでは
  **文字列 `"5"`** だった。トリガー種別により型が異なる（n=1同士の比較のため一般化はしない）。
- 【事実】`startTime` / `timeZone` は**無い**（`Recurrence` トリガーの例には両方あった）。省略可能。
- 【事実】`splitOn: "@triggerOutputs()?['body/value']"` を持つ。
- 【事実】フォルダ指定のキーは **`folderId`**（値 `"Inbox"`）。
- 【事実】`importance: "Any"` は文字列、`hasAttachments` / `includeAttachments` は真偽値（文字列ではない）。

### 6.3 アクション詳細（実行順）

#### 1. `メールを取得する_(V3)`

| 項目 | 内容 |
|---|---|
| 内部名 | `メールを取得する_(V3)` |
| 表示名 | メールを取得する (V3) / Get emails (V3) |
| 種別 | `OpenApiConnection`（`shared_office365` / `GetEmailsV3`） |
| 入力 | 【事実】**`inputs.parameters` キーが存在しない**。`host` と `authentication` のみ |
| 出力 | コネクタ封筒 `{statusCode, headers, body}`。`body.value` がメール配列【推定】 |
| runAfter | `{}`（トリガー直後の先頭アクション） |
| 後続依存 | `For_each` が `Succeeded` で follow |
| 例外処理 | なし |
| 再試行設定 | 【事実】`retryPolicy` の指定なし＝コネクタ既定 |
| タイムアウト | 【事実】`limit.timeout` の指定なし＝既定 |

- 【事実】**必須パラメータを1つも持たないコネクタアクションは、`parameters` キーごと省略された状態でエクスポートされる。**
  これは既知エラー5（`PostItem` の `item` 欠落で保存失敗）と対照的な事例で、
  「`parameters` が無い＝壊れている」とは限らないことを示す。
- 【要実環境確認】`parameters` 省略時の既定の対象メールボックス／フォルダ／取得件数。

#### 2. `For_each`

| 項目 | 内容 |
|---|---|
| 内部名 | `For_each` |
| 表示名 | For each（Apply to each / それぞれに適用する） |
| 種別 | `Foreach` |
| 入力 | `@outputs('メールを取得する_(V3)')?['body/value']` |
| runAfter | `{"メールを取得する_(V3)": ["Succeeded"]}` |
| ネスト | 子アクション1件（深さ2） |
| 並列制御 | 【事実】`runtimeConfiguration.concurrency` の**指定なし**＝コネクタ既定（並列） |
| 配列保証 | 【事実】`coalesce(..., json('[]'))` による保証は**無い** |

#### 3. `開封済みまたは未読としてマークする_(V3)`（For_each 内）

| 項目 | 内容 |
|---|---|
| 内部名 | `開封済みまたは未読としてマークする_(V3)` |
| 表示名 | 開封済みまたは未読としてマークする (V3) / Mark as read or unread (V3) |
| 種別 | `OpenApiConnection`（`shared_office365` / `MarkAsRead_V3`） |
| 入力 | `messageId: "@items('For_each')?['id']"` の**1件のみ** |
| runAfter | 【事実】**`runAfter` キー自体が存在しない** |
| 例外処理 / 再試行 / タイムアウト | いずれも指定なし |

- 【事実】ルート直下の先頭アクションは `"runAfter": {}` を明示するが、
  **Foreach の子として先頭に置かれたアクションは `runAfter` キーごと省略される。**
  [01 フロー構成ルール](../handbook/rules/01_flow_architecture_rules.md) は
  「コンテナの起点アクションでも `"runAfter": {}` を明示する（標準エクスポート形式）」と記しているが、
  **Foreach 配下では省略形も実エクスポートで生成される**。→ §11 で整理。
- 【要実環境確認】既読/未読を切り替えるパラメータ（Read Status）が指定されていない状態で
  保存・実行できるか。§12-B のとおり公式資料でキー名を確定できなかった。

#### 4. `チャットまたはチャネルでメッセージを投稿する`

| 項目 | 内容 |
|---|---|
| 内部名 | `チャットまたはチャネルでメッセージを投稿する` |
| 表示名 | チャットまたはチャネルでメッセージを投稿する / Post message in a chat or channel |
| 種別 | `OpenApiConnection`（`shared_teams` / `PostMessageToConversation`） |
| 入力 | `poster: "Flow bot"` / `location: "Chat with Flow bot"` / `body/recipient: "{userEmail}"` / `body/messageBody: "<p class=\"editor-paragraph\">message</p>"` |
| runAfter | `{"For_each": ["Succeeded"]}` |
| 例外処理 / 再試行 / タイムアウト | いずれも指定なし |

- 【事実】`poster` の実値は `"Flow bot"`、`location` の実値は **`"Chat with Flow bot"`**。
- 【公式・要再確認】公式リファレンスで読み取れた `location` の許可値は `Channel` / `Chat` の2つで、
  **`"Chat with Flow bot"` は含まれていなかった**。実エクスポートの値を正とし、公式表記は参考に留める。
- 【事実】`body/messageBody` は `<p class="editor-paragraph">…</p>` という HTML 断片。
  【推定】デザイナーのリッチテキストエディタが生成する既定マークアップで、`editor-paragraph` はエディタ側のクラス名。
  【推定】本文 `message` はプレースホルダのまま。

### 6.4 例外処理・再試行・タイムアウト（総括）【事実】

| 観点 | 状況 |
|---|---|
| Scope による Try/Catch/Finally | **なし** |
| `runAfter` に `Failed` / `Skipped` / `TimedOut` を持つアクション | **0件**（全て既定の `Succeeded` のみ） |
| `retryPolicy` の明示 | **0件** |
| `limit`（タイムアウト）の明示 | **0件** |
| `trackedProperties` / `operationOptions` | **0件** |

→ 途中のどのアクションが失敗しても、そこで実行が停止し、Teams通知も行われない構成。
[08 エラー処理と冪等性](../handbook/rules/08_error_handling_and_idempotency.md) の観点は一切実装されていない。

---

## 7. 主要な式

定義中の式は**4本のみ**（全件を以下に掲載）。

| # | 式 | 使用箇所 | 評価 |
|---|---|---|---|
| 1 | `@parameters('$authentication')` | トリガー＋全アクションの `authentication` | 【事実】Embedded形式の標準形。秘密情報ではない |
| 2 | `@triggerOutputs()?['body/value']` | トリガーの `splitOn` | 【事実】封筒の `body` 経由。正しい形 |
| 3 | `@outputs('メールを取得する_(V3)')?['body/value']` | `For_each` の入力 | 【事実】封筒の `body/` を経由しており**既知エラー4には該当しない**。ただし当リポジトリ推奨形は `body('X')?['value']` |
| 4 | `@items('For_each')?['id']` | `MarkAsRead_V3` の `messageId` | 【事実】Foreach内の要素参照。`?[]` による null 安全アクセス |

### 7.1 式の観点別チェック【事実】

| 観点 | 結果 |
|---|---|
| `@` の付与位置 | **合格**。4本とも先頭1個のみ。ネスト関数への `@` は0件 |
| `outputs()` と `body()` の使い分け | `outputs()` を封筒 `body/` 経由で使用。**動作上は正**だが推奨形ではない（§9） |
| `items()` / `item()` / `variables()` | `items('For_each')` のみ使用。`item()` と `variables()` は**不使用** |
| `coalesce()` / `trim()` / `empty()` 等のnull安全性 | **1件も使用していない**（§10-B） |
| 型整合（配列/オブジェクト/文字列/数値/真偽値） | トリガーの `hasAttachments`/`includeAttachments` は真偽値リテラル、`interval` は数値。型は整合 |
| SetVariable の自己参照 | **N/A**（SetVariable が0件） |
| Apply to each 内外の参照 | `items('For_each')` は Foreach 内でのみ使用。**越境参照なし** |
| 動的コンテンツと式の混在 | `@{…}` 補間は**0件**。混在なし |
| 固定値として埋め込まれたID・URL | メールアドレス2種（§3.6）。**URL・GUIDの式内埋め込みは0件** |
| 使用関数 | `parameters` / `triggerOutputs` / `outputs` / `items` の4つのみ。全て[02](../handbook/rules/02_expression_and_type_safety.md)の実績集合内 |

---

## 8. 再利用可能な実装

**そのまま参考にできる実装**（構造・形式として信頼できるもの）。

| # | 内容 | 根拠 |
|---|---|---|
| 8-1 | **2コネクタ構成のレガシーパッケージの骨格**（API2＋接続2＝`dependsOn` 4件、`apisMap`/`connectionsMap` 各2エントリ） | 【事実】機械走査で全対応が一致。ただし**同規模の実例は既存の `tmp_20260716051507.zip`（2コネクタ・4アクション）にもある**ため、構造面での新規性は無い。整合の取れた追加検体という位置付け |
| 8-2 | **コネクタのポーリングトリガー形式**（`type: OpenApiConnection` ＋ 直下の `recurrence` / `evaluatedRecurrence`） | 【事実】§6.2。当リポジトリ初の実例 |
| 8-3 | **`splitOn` によるデバッチ指定の書式**（`@triggerOutputs()?['body/value']`） | 【事実】当リポジトリ初の実例。ただし意味論は§9-4 |
| 8-4 | **Embedded形式の接続参照 ＋ `@parameters('$authentication')` の組み合わせ** | 【事実】既存の実働サンプル2件と同一。方式(a)の再確認 |
| 8-5 | **動的ボディのフラット化キー `body/xxx`** | 【事実】§5.3。`item/` `parameters/` と同じ規則であることの追加実例 |
| 8-6 | **必須パラメータが無いアクションは `parameters` キーごと省略される** | 【事実】§6.3-1。自作パッケージの検証スクリプトが `parameters` の存在を無条件に必須としないための根拠 |
| 8-7 | **Foreach 子の先頭アクションは `runAfter` キーを省略した形でもエクスポートされる** | 【事実】§6.3-3 |
| 8-8 | **`definition` に `outputs` / `description` が無くても成立する** | 【事実】§3.4 |
| 8-9 | **Teams `PostMessageToConversation` の入力キー構成**（`poster` / `location` / `body/recipient` / `body/messageBody`） | 【事実】キー名と実値の形は確認済み。ただし §9-5 の制約あり |

---

## 9. 条件付きで利用可能な実装

| # | 内容 | 条件 |
|---|---|---|
| 9-1 | `@outputs('X')?['body/value']` によるコネクタ出力参照 | **動作上は正しい**（`body/` を経由しているため既知エラー4ではない）。ただし当リポジトリの推奨形は `body('X')?['value']`。**新規作成では推奨形に統一し、本サンプルの形は「デザイナーが生成する形」として理解に留める** |
| 9-2 | ポーリング間隔 `frequency: Minute` / `interval: 1` | 1分間隔は最短クラス。【要実環境確認】ライセンスによる実行回数上限・API調整（スロットリング）の影響。**業務要件が許す最長間隔にすること** |
| 9-3 | `Foreach` の並列既定のまま使用 | 変数更新・順序依存が**無い**場合に限る。既読化のような状態変更を含む場合は [01](../handbook/rules/01_flow_architecture_rules.md) に従い `concurrency.repetitions = 1` を検討する |
| 9-4 | `splitOn` によるデバッチ | `splitOn` を付けると配列の各要素が**別々のフロー実行**になる。すなわち `triggerOutputs()?['body']` は「1件のメール」を指す。本サンプルはこの出力を使っていないため、**この形からデバッチ後の参照方法は学べない**。【要実環境確認】 |
| 9-5 | Teams投稿の `location: "Chat with Flow bot"` | 【事実】実エクスポートの値だが、公式リファレンスの許可値一覧（`Channel` / `Chat`）と表記が一致しない。**チャネル投稿を行う場合はこの値をそのまま流用できない**。実機のデザイナーで値を確認すること |
| 9-6 | `body/messageBody` の `<p class="editor-paragraph">` ラッパー | 【推定】デザイナー生成の既定マークアップ。**必須かどうかは未確認**。プレーンテキストやシンプルな `<p>` で足りる可能性がある。【要実環境確認】 |

---

## 10. 流用禁止又は注意が必要な実装

### 10-A. トリガー出力を使わない結線【流用禁止・最重要】

【事実】トリガーの出力がどのアクションからも参照されていない（§4.2）。
【事実】`GetEmailsV3` に `parameters` が無いため、取得対象が**トリガーの共有メールボックスと一致する保証が定義上どこにも無い**。

- 「新着メールを受けて、そのメールを処理する」フローを作る場合、**この結線をそのまま真似してはならない。**
- 既読化（`MarkAsRead_V3`）は**状態を変更する副作用**であり、対象を取り違えると
  意図しないメールボックスのメールが既読になる。
- 【教訓】既存の教訓「実行成功≠結果が正しい」と同型。本フローは**エラーなく完走しても目的を達成しない**構造。

### 10-B. Apply to each 入力の配列保証が無い【流用禁止】

【事実】`For_each` の入力は `@outputs('メールを取得する_(V3)')?['body/value']` で、
`coalesce(..., json('[]'))` による配列保証が無い。
[00 コアルール5](../handbook/rules/00_power_automate_core_rules.md)（Apply to each の入力は必ず配列を保証する）に**違反**。
メールが0件のときや `body` が返らないときに null が渡る。

【要実環境確認】null が渡ったときに Foreach がスキップされるか実行時エラーになるか。
**どちらであれ、当リポジトリの新規フローでは配列保証を入れる。**

### 10-C. エラー処理・再試行・タイムアウトが皆無【流用禁止】

【事実】§6.4。Scope なし、`runAfter` の失敗系なし、`retryPolicy` なし、`limit` なし。
【帰結】`MarkAsRead_V3` が1件でも失敗すると Foreach ごと失敗し、Teams通知に到達しない。
「処理は失敗したが通知だけは飛ぶ」という設計にすらなっていない。
[08](../handbook/rules/08_error_handling_and_idempotency.md) に従い、Scope分離・失敗経路の通知を別途設計すること。

### 10-D. 実値のハードコードと未匿名化【流用禁止（そのままの配布）】

【事実】§3.5 / §3.6。共有メールボックスアドレス・個人メールアドレス・作成者GUID・テナントID・接続GUIDが素のまま。
**匿名化せずに流用・配布してはならない。**

### 10-E. 命名【注意】

【事実】アクション内部名が日本語（`メールを取得する_(V3)` 等）。
【事実】フロー表示名が自動生成の既定名のまま。
当リポジトリの命名規則は英数字＋アンダースコア（[01](../handbook/rules/01_flow_architecture_rules.md)）。
→ 英語命名案は §15。

### 10-F. Teams投稿本文が固定文字列【注意】

【事実】`body/messageBody` はメール由来の情報を1文字も含まない固定文言。
通知フローとしての体を成していないため、**本文組み立てのパターンとしては参考にならない**。

---

## 11. 既存ルールとの照合結果

### 11.1 既知エラー7件との同型パターン全数チェック【事実】

definition.json 全体を機械走査した結果。

| # | 既知エラー | 本サンプルでの該当 | 判定 |
|---|---|---|---|
| 1 | ネストした関数への誤った `@` | 式4本すべて先頭 `@` のみ | **該当なし（0件）** |
| 2 | SetVariable の自己参照 | SetVariable アクション自体が0件 | **該当なし（0件）** |
| 3 | アクション内部名の重複 | 4アクション＋トリガー1、重複0 | **該当なし（0件）** |
| 4 | `outputs()` によるコネクタ出力の封筒参照 | `outputs('X')?['body/value']` 1件。`body/` を経由しており誤りではない | **該当なし（0件）**。§9-1 の注記のみ |
| 5 | 動的なサイト/リスト指定による保存時エラー（`PostItem`） | SharePoint 不使用。`PostItem` 0件 | **N/A** |
| 6 | サイトとファイルURLの不一致（クロスサイト404） | SharePoint 不使用 | **N/A** |
| 7 | フォルダ未作成による Create file 失敗 | SharePoint 不使用 | **N/A** |

### 11.2 コアルール8項目との照合

| ルール | 判定 |
|---|---|
| 1. SetVariable 自己参照禁止 | ✅ 該当なし |
| 2. 累積は専用アクションで | ✅ 該当なし（累積処理なし） |
| 3. `@` は先頭または `@{}` の中のみ | ✅ 合格 |
| 4. 型規律 `trim(coalesce(...))` | ⚠️ **null安全化を一切していない**（§10-B）。ただし文字列処理自体が無いため実害は限定的 |
| 5. Apply to each の入力は配列保証 | ❌ **違反**（§10-B） |
| 6. インポート成功＝完成ではない | ― 本サンプルは未インポート（§12） |
| 7. コネクタ出力は `body('X')?['field']` | ⚠️ `outputs('X')?['body/value']`。**誤りではないが推奨形ではない**（§9-1） |
| 8. 未検証事項は「要実環境確認」／実値はプレースホルダー | ❌ **実値がそのまま埋め込まれている**（§3.6） |

### 11.3 その他ルールとの照合

| ルール | 判定 |
|---|---|
| [01] 並列オフ（変数更新ループの逐次化） | ― 変数更新は無いため直接の違反ではない。ただし状態変更（既読化）を含むため §9-3 の注意 |
| [01] 命名規則（英数字＋アンダースコア） | ❌ 日本語命名（§10-E） |
| [01] ネスト8段以内 | ✅ 最大2段 |
| [02] 実在確認済み関数のみ使用 | ✅ 使用4関数すべて実績集合内 |
| [04] 標準コネクタで完結 | ✅【推定】プレミアム・カスタムコネクタ不使用 |
| [07] 5ファイル構造・GUID3点一致 | ✅ 合格 |
| [07] 匿名化 | ❌ 未実施（§3.6） |
| [08] エラー処理・冪等性 | ❌ 皆無（§10-C）。再実行時の冪等性も担保なし |

### 11.4 既存 handbook と矛盾する実装【重要】

| # | handbook の記述 | 本サンプルの実態 | 整理 |
|---|---|---|---|
| 11-4-1 | [01] トリガー種別は `manual`（Request/Button）と `Recurrence`（Recurrence）の2形式を記載 | **`type: OpenApiConnection` のポーリングトリガー**が存在し、`recurrence` をトリガー直下に持つ | **矛盾ではなく未記載**。第3の形式として追記すべき（§13） |
| 11-4-2 | [01]「`runAfter` はコンテナ（Scope等）の起点アクションでも `"runAfter": {}` を明示する（Power Automate 標準エクスポート形式）」 | **Foreach 子の先頭アクションは `runAfter` キーごと省略**されている（ルート直下の先頭は `{}` 明示） | **部分的に矛盾**。実エクスポートは「ルート直下＝`{}` 明示／Foreach配下＝省略」。既存記述は Scope を対象にしており本サンプルに Scope は無いため**直接の反証ではない**が、断定の範囲を狭める必要がある（§13） |
| 11-4-3 | [01] `Recurrence` トリガーの `interval` は**文字列**（`"5"`） | 本サンプルの `interval` は**数値**（`1`） | **矛盾ではない**（トリガー種別が異なる）。ただし「interval は常に文字列」と一般化してはならない根拠になる |

### 11.5 既存 handbook に未記録の可能性がある知見

| # | 知見 | 反映先候補 |
|---|---|---|
| 11-5-1 | Office 365 Outlook コネクタ（`shared_office365`）と3つの operationId | `connector_action_notes.md` |
| 11-5-2 | Teams `PostMessageToConversation` の入力キー構成 | `connector_action_notes.md` |
| 11-5-3 | コネクタのポーリングトリガー形式（`OpenApiConnection` ＋ `recurrence`/`evaluatedRecurrence`） | `rules/01_flow_architecture_rules.md` |
| 11-5-4 | `splitOn` の書式とデバッチの意味論 | `rules/01_flow_architecture_rules.md` |
| 11-5-5 | 必須パラメータの無いアクションは `parameters` キーごと省略される | `connector_action_notes.md` |
| 11-5-6 | Foreach 子の先頭アクションの `runAfter` 省略 | `rules/01_flow_architecture_rules.md` |
| 11-5-7 | `definition` に `outputs`/`description` が無くても成立する | `rules/01_flow_architecture_rules.md` または索引 |
| 11-5-8 | 動的ボディのフラット化キー `body/xxx` | `connector_action_notes.md` |
| 11-5-9 | ルート manifest の `details.creator: "N/A"` を見て匿名化済みと誤認しない（接続リソースの `displayName` にメールが残る） | `rules/07_export_import_package_rules.md` または本文書のみ |

---

## 12. 要実環境確認事項

### 12-A. フロー実装に関するもの

| # | 事項 | 理由 |
|---|---|---|
| 12-1 | `GetEmailsV3` を `parameters` 省略で実行したときの対象メールボックス・フォルダ・件数 | 定義に情報が無く、コネクタ既定値に依存する |
| 12-2 | `MarkAsRead_V3` を `messageId` のみで保存・実行できるか（Read Status 未指定） | 既知エラー5と同型の「必須パラメータ欠落による保存時エラー」の可能性がある。§12-B のとおり公式資料で確定できず |
| 12-3 | `splitOn` 有効時の `triggerOutputs()` の実際の形状 | デバッチ後の参照方法は本サンプルからは学べない |
| 12-4 | `Foreach` に null（`body/value` 不在）が渡ったときの挙動 | スキップか実行時エラーか |
| 12-5 | `Foreach` の既定並列度と、状態変更アクションを含む場合の実害 | `concurrency` 未指定 |
| 12-6 | `location: "Chat with Flow bot"` の正確な意味と、`body/recipient` の受け取り形式（メールアドレス以外を受けるか） | 公式の許可値一覧と実値が一致しない |
| 12-7 | `body/messageBody` の `<p class="editor-paragraph">` ラッパーが必須か | プレーン文字列で足りるかは未確認 |
| 12-8 | 共有メールボックス監視に必要な権限（フルアクセス等）とDLPポリシー適合 | 環境依存 |
| 12-9 | 1分間隔ポーリングのライセンス上の実行回数上限・スロットリング | 環境依存 |

### 12-B. 公式資料の参照可否について【重要・手続き上の記録】

2026-08-03 に learn.microsoft.com のコネクタリファレンス（`connectors/office365/` / `connectors/teams/`）を参照した。

- 【事実】Teams `PostMessageToConversation` の表示名・パラメータ表（`poster` / `location` / `body`）は取得できた。
- 【事実】Office 365 Outlook 側は、**同一URL・同一設問に対する2回の取得でパラメータ表の内容が食い違った**
  （`MarkAsRead_V3` の Read Status のキー名が1回目と2回目で別の値になった。
  トリガーの節は2回目に「取得内容に存在しない」と返った＝ページが切り詰められている）。
- 【判定】この状況で公式資料由来のパラメータキー名を「確認済み」として記録すると、
  [02](../handbook/rules/02_expression_and_type_safety.md)「実在確認済みの関数・パラメータのみ使う」の趣旨に反する。
  よって**本文書ではパラメータのキー名・必須/任意について公式資料由来の記述を採用していない。**
  記録しているのは**すべて definition.json から読み取った実値のキー名**である。
- 【推奨】Office 365 Outlook のパラメータ仕様を確定させる必要が生じた時点で、
  デザイナー上で該当アクションを開いて実際の入力欄を確認する（実機が最も確実）。

### 12-C. パッケージとしての未確認事項

| # | 事項 |
|---|---|
| 12-10 | **本パッケージのインポートは未実施**。「インポートできる」とは主張しない |
| 12-11 | 2コネクタ・Embedded形式・実接続GUID保持のまま**別環境**へインポートした場合の接続再マッピング挙動。当リポジトリで実証済みなのは「**匿名化した**接続GUID・**Invoker**形式・接続1本」の構成のみ |

---

## 13. handbookへの反映候補

| # | 内容 | 反映先 | 判定 |
|---|---|---|---|
| 13-1 | サンプル索引エントリ | `handbook/knowledge/sample_flow_reference_index.md` | **反映する**（本作業で実施） |
| 13-2 | コネクタのポーリングトリガー形式（第3のトリガー種別）／`splitOn`／Foreach子の `runAfter` 省略／`definition` の `outputs`・`description` 省略 | `handbook/rules/01_flow_architecture_rules.md` | **反映する**（本作業で実施）。パッケージ構造の一般知識であり案件固有ではない |
| 13-3 | Office 365 Outlook コネクタ3操作／Teams `PostMessageToConversation`／`parameters` キー省略／`body/` フラット化 | `handbook/knowledge/connector_action_notes.md` | **反映する**（本作業で実施）。**確認根拠は「サンプル定義に実在」までであり、パラメータ仕様の網羅ではない**旨を明記する |
| 13-4 | 新しいエラーパターン | `handbook/knowledge/error_catalog.md` | **反映しない**。本サンプルで**実際に発生したエラーは1件も無い**（未インポート）。§10 は設計上の指摘であって発生済みエラーではない |
| 13-5 | 再利用可能な式 | `handbook/knowledge/expression_examples.md` | **反映しない**。式4本はいずれも既存記載（封筒参照・`items()`）の範囲内で、新規性のある式が無い |
| 13-6 | 一般化可能な教訓 | `handbook/knowledge/lessons_learned.md` | **反映しない**。`lessons_learned.md` は**案件単位**の構成であり、参照サンプル1件の指摘を案件教訓として混ぜると単一情報源の原則が崩れる。§10 は本文書と索引に置く |
| 13-7 | `details.creator: "N/A"` を匿名化済みと誤認しない | `handbook/rules/07_export_import_package_rules.md` | **保留**。既存の匿名化節に「接続GUID・メールアドレスを除去」と記載済みで実質重複。本文書 §3.6 に留める |

---

## 14. 総合評価

### 14.1 一言でいうと

**パッケージ構造の参考資料としては価値が高いが、フロー実装の参考資料としては流用してはならないサンプル。**

### 14.2 評価の内訳

| 観点 | 評価 | 理由 |
|---|---|---|
| パッケージ構造 | **中（整合の取れた追加検体）** | 5ファイル構造・GUID3点一致・`dependsOn`・`apisMap`/`connectionsMap` の対応がすべて整合。ただし2コネクタ構成の実例は `tmp_20260716051507.zip` に既にあり、構造面での新規性は無い |
| トリガー形式 | **高い（そのまま参考可）** | コネクタのポーリングトリガー＋`splitOn` の実物は当リポジトリ初。**本サンプル最大の収穫** |
| コネクタ操作の書式 | **中（キー名の実例として有用）** | operationId とパラメータキーの実例は使える。ただし網羅的な仕様ではない |
| フロー設計 | **低い（流用禁止）** | トリガー出力を使っていない（§10-A）、配列保証なし（§10-B）、エラー処理皆無（§10-C） |
| 配布可能性 | **不可（要匿名化）** | 実メールアドレス・接続GUID・テナントIDが素のまま（§3.6） |

### 14.3 「実働＝正しい」ではないことの再確認

【推定】本サンプルは実環境で作成・保存・エクスポートされたものである（`creationSource: Portal`）。
しかし §10-A のとおり、**トリガーで受け取ったメールと後続処理の間にデータの結線が存在しない**。
これは既存サンプル `create_meeting_list_sample`（実働だが累積ロジックにバグ）と同型の事例であり、
[索引](../handbook/knowledge/sample_flow_reference_index.md)冒頭の
「実際のエクスポートだから正しいとはみなさない」という原則を**3例目として補強**する。

### 14.4 想定される利用場面

| 場面 | 使い方 |
|---|---|
| 共有メールボックス監視フローを作る | **トリガー定義（§6.2）のみ**を雛形にする。後続の結線は自分で設計する |
| Teams へ通知を投げるフローを作る | `PostMessageToConversation` の**キー名（§6.3-4）のみ**を参考にする。`location` の値は実機で確認 |
| 2コネクタ構成のパッケージを自作する | `manifest.json` / `apisMap` / `connectionsMap` の**対応関係の雛形**として使う |
| フローレビューの教材 | 「エラーなく完走するが目的を達成しない設計」の実例として使える |

---

## 15. 英語アクション名対応表と命名案（追加依頼分）

共有メールボックス解析＋Teams投稿のフローを新規作成する前提で、英語名と当リポジトリ命名規則に沿った内部名案を示す。

### 15.1 表示名の対応【§5.2 の再掲＋内部名案】

| 実行順 | 日本語表示名【事実】 | 英語表示名【公式・要再確認】 | operationId【事実】 | **推奨する英語内部名【推奨】** |
|---|---|---|---|---|
| トリガー | 新しいメールが共有メールボックスに届いたとき (V2) | When a new email arrives in a shared mailbox (V2) | `SharedMailboxOnNewEmailV2` | `When_New_Email_In_Shared_Mailbox` |
| 1 | メールを取得する (V3) | Get emails (V3) | `GetEmailsV3` | `Get_Emails` |
| 2 | （Apply to each） | Apply to each | ― | `For_Each_Email` |
| 3 | 開封済みまたは未読としてマークする (V3) | Mark as read or unread (V3) | `MarkAsRead_V3` | `Mark_Email_As_Read` |
| 4 | チャットまたはチャネルでメッセージを投稿する | Post message in a chat or channel | `PostMessageToConversation` | `Post_Notification_To_Teams` |

【事実】内部名は表示名の空白を `_` に置換したもの。したがって**アクション名を英語にすれば内部名も英語になる**。
【推奨】当リポジトリの [01 命名規則](../handbook/rules/01_flow_architecture_rules.md)（英数字＋アンダースコア）に従い、
デザイナー上でアクションを**英語名にリネームしてから**エクスポートすると、`build_*.py` での再現・検証が容易になる。

### 15.2 フロー名の案【推奨】

本サンプルの表示名は自動生成の既定名（§3.4）であり、そのまま参考にはできない。
当リポジトリの既存フロー名（`PA_Migrate_Teams_Meeting_Archive_To_SPO` /
`Flow1_GetTeamsChannelPostFromUrl` / `CreateInitializedSharePointList`）に倣った案:

| 用途 | フロー名案 | 案件フォルダ名案（ケバブケース） |
|---|---|---|
| 共有メールボックスの新着を Teams に通知 | `PA_SharedMailbox_Notify_To_Teams` | `shared-mailbox-teams-notify` |
| 共有メールボックスのメールを解析・分類 | `PA_SharedMailbox_Analyze_Emails` | `shared-mailbox-analyze` |
| 上記2つを1本にまとめる場合 | `PA_SharedMailbox_Triage_And_Notify` | `shared-mailbox-triage` |

### 15.3 新規実装時に本サンプルから引き継ぐ／引き継がない切り分け【推奨】

| 引き継ぐ | 引き継がない（自分で設計する） |
|---|---|
| トリガーの形式（`OpenApiConnection` ＋ `recurrence` ＋ `evaluatedRecurrence`） | ポーリング間隔（1分は要件次第で見直す。§9-2） |
| `splitOn` の書式 | `splitOn` を使うか否か（デバッチの要否は要件次第。§9-4） |
| `PostMessageToConversation` のキー名 | `location` の値・本文の組み立て（§9-5 / §10-F） |
| パッケージ構造・`apisMap`/`connectionsMap` の対応 | 接続GUID・メールアドレス（必ず匿名化。§10-D） |
| ― | **トリガー出力と後続処理の結線**（§10-A。本サンプルには存在しない） |
| ― | **Apply to each の配列保証**（§10-B） |
| ― | **エラー処理・再試行・冪等性**（§10-C） |

---

## 付録. 検証に使用した手段

| 手段 | 内容 |
|---|---|
| 機械走査 | 5ファイル構造 / GUID3点一致 / 接続参照突合 / アクション名重複 / `runAfter` 兄弟整合 / 不正な `@` / SetVariable自己参照 / `outputs()` 封筒 / Foreach配列保証・並列 / 実値検出 の各観点をスクリプトで走査（結果は §3.7・§7.1・§11） |
| `tools/gen_outline.py` | 実行順アウトライン生成（§6.1） |
| 既存サンプルとの構造比較 | `references/extracted/` の既存3サンプル＋`projects/` 配下の自作5パッケージと `connectionReferences` の位置・`source` 方式・`definition` キー構成を比較 |

**本作業では原本ZIP・展開結果を一切変更していない。Git操作も行っていない。**
