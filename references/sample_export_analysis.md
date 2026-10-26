# Power Automate レガシーエクスポートZIP（雛形）解析ドキュメント

対象: `extracted/sample_extracted_ref/`（`Microsoft.Flow/flows/582ee26e-4e16-44dc-a679-bef89908b2c5/` を含む展開済みディレクトリ）

本ドキュメントは、雛形として提供された展開済みZIPの中身を全ファイル読了のうえ、事実ベースで解析したものである。JSON中の実値はそのまま引用し、メールアドレス等のユーザー固有情報には「（匿名化対象）」を明示する。

---

## 1. ZIPの種類（レガシーPower Automateパッケージ形式である根拠）

以下の特徴から、本雛形は **Power Automate（Flow）のレガシー「パッケージとしてエクスポート／インポート」形式**（Dataverseソリューションではない、単体クラウドフロー用の旧エクスポート形式）であると判断できる。

- ルート直下に `manifest.json` が存在し、`"schema":"1.0"` と `"resources"` ツリー（各リソースに `type` / `suggestedCreationType` / `creationType` / `configurableBy` / `hierarchy` / `dependsOn` を持つ）を持つ。これはDataverseソリューションZIP（`solution.xml` / `customizations.xml` / `[Content_Types].xml` を持つ形式）とは異なる、フロー単体の「レガシーパッケージ」に特有の構造である。
- `Microsoft.Flow/flows/manifest.json` に `packageSchemaVersion` と `flowAssets.assetPaths`（フローGUIDフォルダ名の配列）を持つ、フロー資産の入れ物専用マニフェストが存在する。
- 各フローは `Microsoft.Flow/flows/{フローパッケージGUID}/` フォルダの下に `definition.json`（フロー定義本体）・`apisMap.json`（コネクタ論理名→APIリソースGUID対応表）・`connectionsMap.json`（コネクタ論理名→接続リソースGUID対応表）の3点セットで格納される。
- `solution.xml`、`customizations.xml`、`[Content_Types].xml` など Dataverse ソリューション特有のファイルは一切存在しない。
- `__MACOSX/` や `.DS_Store` 等のアーカイブ副産物も存在しない（クリーンな展開）。

以上より、これはDataverse環境を介さない、クラシックな「フローをパッケージとしてエクスポート（.zip）」機能が生成する **レガシー形式のZIP** であると確認できる。

---

## 2. ルート構造（ファイル一覧・ツリー）

```
sample_extracted_ref/
├─ manifest.json                                                          (2,288 bytes)
└─ Microsoft.Flow/
   └─ flows/
      ├─ manifest.json                                                    (99 bytes)
      └─ 582ee26e-4e16-44dc-a679-bef89908b2c5/
         ├─ definition.json                                               (6,300 bytes)
         ├─ apisMap.json                                                  (120 bytes)
         └─ connectionsMap.json                                           (120 bytes)
```

ファイル総数: 5個（すべてJSON）。フォルダ名 `582ee26e-4e16-44dc-a679-bef89908b2c5` は「フローパッケージGUID」であり、後述のとおり `definition.json` 内部の実フローGUIDとは **別の値** である点に注意（§9参照）。

---

## 3. ルート `manifest.json` の解析

```json
{
  "schema": "1.0",
  "details": {
    "displayName": "tmp",
    "description": "",
    "createdTime": "2026-07-16T05:15:07.8659338Z",
    "packageTelemetryId": "789b5493-c0c7-4a16-b2fb-cbcad4c605d5",
    "creator": "N/A",
    "sourceEnvironment": ""
  },
  "resources": { ... }
}
```

`details.displayName` が `"tmp"`、`description` が空文字であることから、この雛形はエクスポート時にパッケージ名を明示的に付けなかった（もしくは一時的な検証目的の）エクスポートである可能性が高い。`creator` は `"N/A"`、`sourceEnvironment` は空文字。

### `resources` 内訳（5リソース）

| リソースキー(GUID) | type | suggestedCreationType | creationType | configurableBy | hierarchy | dependsOn |
|---|---|---|---|---|---|---|
| `582ee26e-4e16-44dc-a679-bef89908b2c5` | `Microsoft.Flow/flows` | `New` | `Existing, New, Update` | `User` | `Root` | `c32368a7-...`, `bc99ff66-...`, `e4f31fdf-...`, `f1e38ae6-...` |
| `c32368a7-113e-497e-990f-aab3642f4011` | `Microsoft.PowerApps/apis` | `Existing` | （なし） | `System` | `Child` | `[]` |
| `bc99ff66-7006-40a6-b085-024409eb42bf` | `Microsoft.PowerApps/apis/connections` | `Existing` | `Existing` | `User` | `Child` | `c32368a7-...` |
| `e4f31fdf-c13c-4607-8af5-06baa431158d` | `Microsoft.PowerApps/apis` | `Existing` | （なし） | `System` | `Child` | `[]` |
| `f1e38ae6-6c4b-4670-9e29-c58312fbd2fb` | `Microsoft.PowerApps/apis/connections` | `Existing` | `Existing` | `User` | `Child` | `e4f31fdf-...` |

各リソースの詳細:

**① `582ee26e-4e16-44dc-a679-bef89908b2c5`（フロー本体・Root）**
- `id` フィールドなし（Rootリソースのみ `id` を持たない形。他の4リソースは `id` を持つ）
- `details.displayName`: `"Button -> Microsoft Graph HTTP 要求を送信する"`
- `dependsOn`: 4件（Teams API・Teams接続・SharePoint API・SharePoint接続の全て）

**② `c32368a7-113e-497e-990f-aab3642f4011`（Teams API）**
- `id`: `/providers/Microsoft.PowerApps/apis/shared_teams`
- `name`: `shared_teams`
- `details.displayName`: `"Microsoft Teams"`
- `details.iconUri`: `https://static.powerapps.com/resource/ppcr/releases/v1.0.1818/1.0.1818.4788/teams/icon.png`

**③ `bc99ff66-7006-40a6-b085-024409eb42bf`（Teams接続）**
- `details.displayName`: `"iihoshi-yohei@jpo.go.jp"` **（匿名化対象＝ユーザーのメールアドレス）**
- `details.iconUri`: 上記Teamsと同一

**④ `e4f31fdf-c13c-4607-8af5-06baa431158d`（SharePoint API）**
- `id`: `/providers/Microsoft.PowerApps/apis/shared_sharepointonline`
- `name`: `shared_sharepointonline`
- `details.displayName`: `"SharePoint"`
- `details.iconUri`: `https://static.powerapps.com/resource/ppcr/releases/v1.0.1813/1.0.1813.4769/sharepointonline/icon.png`

**⑤ `f1e38ae6-6c4b-4670-9e29-c58312fbd2fb`（SharePoint接続）**
- `details.displayName`: `"iihoshi-yohei@jpo.go.jp"` **（匿名化対象＝同上のメールアドレス）**

補足: `Microsoft.PowerApps/apis`（コネクタ種別自体）は `configurableBy:"System"` かつ `dependsOn:[]`、一方 `.../connections`（実際の接続インスタンス）は `configurableBy:"User"` かつ対応するAPIリソースに `dependsOn` する、という階層関係が明確。これは「コネクタ種別はシステム側が固定、実際の接続はインポート時にユーザーが選び直す」というレガシーパッケージの標準的な依存構造。

---

## 4. `Microsoft.Flow/flows/manifest.json` の解析

```json
{"packageSchemaVersion":"1.0","flowAssets":{"assetPaths":["582ee26e-4e16-44dc-a679-bef89908b2c5"]}}
```

- `packageSchemaVersion`: `"1.0"`
- `flowAssets.assetPaths`: フォルダ名（フローパッケージGUID）の配列。本雛形は1要素のみ＝フロー1本の単純パッケージ。

---

## 5. フロー定義ファイル `definition.json` の解析

### 5.1 トップレベル

| フィールド | 値 |
|---|---|
| `name` | `56f7fa9e-ed61-4e56-bc88-b9c759084a70` ← **フォルダ名／manifestリソースキー（`582ee26e-...`）とは別のGUID**（§9参照） |
| `id` | `/providers/Microsoft.Flow/flows/56f7fa9e-ed61-4e56-bc88-b9c759084a70` |
| `type` | `Microsoft.Flow/flows` |
| `properties.apiId` | `/providers/Microsoft.PowerApps/apis/shared_logicflows` |
| `properties.displayName` | `"Button -> Microsoft Graph HTTP 要求を送信する"` |
| `properties.flowFailureAlertSubscribed` | `false` |
| `properties.isManaged` | `false` |

### 5.2 `properties.definition.metadata`

```json
{
  "workflowEntityId": null,
  "processAdvisorMetadata": null,
  "flowChargedByPaygo": null,
  "flowclientsuspensionreason": "None",
  "flowclientsuspensiontime": null,
  "flowclientsuspensionreasondetails": null,
  "creator": {
    "id": "641b02f0-caf2-4b76-826c-c757d0cd98f4",
    "type": "User",
    "tenantId": "b6d94148-69a6-487a-8a69-88236d09260a"
  },
  "provisioningMethod": "FromDefinition",
  "failureAlertSubscription": true,
  "clientLastModifiedTime": "2026-07-16T05:13:28.4782639Z",
  "lastModifiedBy": "641b02f0-caf2-4b76-826c-c757d0cd98f4",
  "connectionKeySavedTimeKey": "2026-07-16T05:13:28.4782639Z",
  "creationSource": "Portal",
  "modifiedSources": "Portal"
}
```

`creator.id` / `lastModifiedBy` = `641b02f0-caf2-4b76-826c-c757d0cd98f4` **（匿名化対象＝作成者ユーザーGUID）**、`creator.tenantId` = `b6d94148-69a6-487a-8a69-88236d09260a` **（匿名化対象＝テナントID）**。

### 5.3 スキーマ・パラメータ

| フィールド | 値 |
|---|---|
| `$schema` | `https://schema.management.azure.com/providers/Microsoft.Logic/schemas/2016-06-01/workflowdefinition.json#` |
| `contentVersion` | `"undefined"`（リテラル文字列。実際のバージョン番号ではない点に注意） |
| `parameters.$authentication` | `{"defaultValue":{},"type":"SecureObject"}` |
| `parameters.$connections` | `{"defaultValue":{},"type":"Object"}` |

### 5.4 トリガー定義

```json
"triggers":{"manual":{"type":"Request","kind":"Button","inputs":{"schema":{"type":"object","properties":{},"required":[]}}}}
```

- トリガー名: `manual`
- `type`: `Request`、`kind`: `Button`（ボタン起動の手動トリガー）
- `inputs.schema.properties` は空オブジェクト＝入力パラメータなし（ボタン押下のみで起動する最小構成）。

### 5.5 アクション定義（4アクション・直列）

| # | アクションキー | type | runAfter | 概要 |
|---|---|---|---|---|
| 1 | `Microsoft_Graph_HTTP_要求を送信する` | `OpenApiConnection` | `{}`（先頭） | Teamsコネクタ経由でMicrosoft Graphへ直接HTTPリクエスト |
| 2 | `JSON_の解析` | `ParseJson` | ①Succeeded | ①のレスポンスボディをJSONスキーマでパース |
| 3 | `作成` | `Compose` | ②Succeeded | パース結果をそのままComposeで出力 |
| 4 | `SharePoint_に_HTTP_要求を送信します` | `OpenApiConnection` | ③Succeeded | SharePointコネクタ経由でHTTPリクエスト（フォルダ取得） |

**① Microsoft Graph HTTP要求（Teams経由）**
```json
{
  "type": "OpenApiConnection",
  "inputs": {
    "parameters": {
      "Uri": "https://graph.microsoft.com/v1.0/groups/a7ac0c68-87ba-4613-8960-13660f0f5f56/team",
      "Method": "GET",
      "ContentType": "application/json"
    },
    "host": {
      "apiId": "/providers/Microsoft.PowerApps/apis/shared_teams",
      "connectionName": "shared_teams",
      "operationId": "HttpRequest"
    },
    "authentication": {
      "value": "@json(decodeBase64(triggerOutputs().headers['X-MS-APIM-Tokens']))['$ConnectionKey']",
      "type": "Raw"
    }
  }
}
```
- `host.operationId` = `HttpRequest`、`host.apiId` = `shared_teams` → いわゆる **「Microsoft Graph HTTP要求を送信します（Send an HTTP request to Microsoft Graph）」** アクション。
- URI内の `a7ac0c68-87ba-4613-8960-13660f0f5f56` はGraph対象のグループ（チーム）ID（環境依存値。新パッケージでは同一値が既定定数として引き継がれている。§末尾考察参照）。
- 認証は `X-MS-APIM-Tokens` ヘッダーをデコードして `$ConnectionKey` を取り出す標準の `Raw` 認証パターン（トークン自体は埋め込まれていない）。

**② JSON の解析（ParseJson）**
- `content`: `@body('Microsoft_Graph_HTTP_要求を送信する')`
- `schema`: Graph の Teamsチャネルメッセージ一覧レスポンス（`statusCode` / `headers` / `body.@odata.context` / `@odata.count` / `@odata.nextLink` / `value[]` の各メッセージオブジェクト = `id`, `replyToId`, `etag`, `messageType`, `createdDateTime`, `lastModifiedDateTime`, `from.user`, `body.content`, `channelIdentity.teamId/channelId`, `attachments`, `mentions`, `reactions` 等）を詳細に定義したスキーマ。

**③ 作成（Compose）**
- `inputs`: `@body('JSON_の解析')`（②の結果をそのまま出力するだけの単純Compose）

**④ SharePointへHTTP要求を送信します**
```json
{
  "type": "OpenApiConnection",
  "inputs": {
    "parameters": {
      "dataset": "https://metijapan.sharepoint.com/teams/pjteam_220400119",
      "parameters/method": "GET",
      "parameters/uri": "_api/web/GetFolderByServerRelativeUrl('/sites/mROOM_240600018/Shared%20Documents/123_伝送システム/00_共用フォルダ/60_庶務担当/99_過去の課内会議')"
    },
    "host": {
      "apiId": "/providers/Microsoft.PowerApps/apis/shared_sharepointonline",
      "connectionName": "shared_sharepointonline",
      "operationId": "HttpRequest"
    },
    "authentication": {
      "value": "@json(decodeBase64(triggerOutputs().headers['X-MS-APIM-Tokens']))['$ConnectionKey']",
      "type": "Raw"
    }
  }
}
```
- `host.operationId` = `HttpRequest`、`host.apiId` = `shared_sharepointonline` → **「SharePointへHTTP要求を送信します（Send an HTTP request to SharePoint）」** アクション。
- `dataset` は `https://metijapan.sharepoint.com/teams/pjteam_220400119`（環境依存・テナント固有）だが、`parameters/uri` の `GetFolderByServerRelativeUrl` パスは `/sites/mROOM_240600018/...` という**別サイト**を参照しており、`dataset`（接続先サイトコレクション）と実際に問い合わせるパスのサイトが一致していない点は雛形の特徴として記録しておく（動作上はSharePointオンライン接続がテナント内サイトへの相対パスアクセスを許容するため必ずしもエラーにはならない）。

### 5.6 `connectionReferences`

```json
{
  "shared_teams": {
    "connectionName": "c101e3dbe885457f8485de11c5e28a5e",
    "source": "Invoker",
    "id": "/providers/Microsoft.PowerApps/apis/shared_teams",
    "tier": "NotSpecified",
    "apiName": "teams",
    "isProcessSimpleApiReferenceConversionAlreadyDone": false
  },
  "shared_sharepointonline": {
    "connectionName": "054920e5a92b48b6b53f62b01b3cb354",
    "source": "Invoker",
    "id": "/providers/Microsoft.PowerApps/apis/shared_sharepointonline",
    "tier": "NotSpecified",
    "apiName": "sharepointonline",
    "isProcessSimpleApiReferenceConversionAlreadyDone": false
  }
}
```

- `connectionName` はハイフン無し32桁の接続GUID: `c101e3dbe885457f8485de11c5e28a5e`（Teams）／`054920e5a92b48b6b53f62b01b3cb354`（SharePoint）— **いずれも匿名化対象**（インポート先環境で作り直される値）。
- `source`: `"Invoker"`（実行者の接続を使う、標準的な設定）。

---

## 6. `apisMap.json` / `connectionsMap.json`

**`apisMap.json`**（コネクタ論理名 → APIリソースGUID＝ルートmanifest.jsonのAPIリソースキー）
```json
{"shared_teams":"c32368a7-113e-497e-990f-aab3642f4011","shared_sharepointonline":"e4f31fdf-c13c-4607-8af5-06baa431158d"}
```

**`connectionsMap.json`**（コネクタ論理名 → 接続リソースGUID＝ルートmanifest.jsonの接続リソースキー）
```json
{"shared_teams":"bc99ff66-7006-40a6-b085-024409eb42bf","shared_sharepointonline":"f1e38ae6-6c4b-4670-9e29-c58312fbd2fb"}
```

この2ファイルは、`definition.json` の `host.apiId`/`connectionReferences` が使う **論理名**（`shared_teams` 等の文字列キー）と、ルート `manifest.json` の `resources` が使う **GUIDキー** とを対応付ける橋渡し役である。すなわち:

```
definition.json の "shared_teams"
   ├─ apisMap.json        → c32368a7-...（ルートmanifest上のAPIリソース = Microsoft.PowerApps/apis）
   └─ connectionsMap.json → bc99ff66-...（ルートmanifest上の接続リソース = Microsoft.PowerApps/apis/connections）
```

---

## 7. API参照まとめ

| コネクタ論理名 | apiId | 表示名 | operationId（本雛形で使用） |
|---|---|---|---|
| `shared_teams` | `/providers/Microsoft.PowerApps/apis/shared_teams` | Microsoft Teams | `HttpRequest`（Microsoft Graph HTTP要求） |
| `shared_sharepointonline` | `/providers/Microsoft.PowerApps/apis/shared_sharepointonline` | SharePoint | `HttpRequest`（SharePoint HTTP要求） |

2コネクタとも標準コネクタ（`Microsoft.PowerApps/apis` 配下）であり、プレミアムコネクタやカスタムコネクタは使用されていない。

---

## 8. 内部フローIDの二重構造（重要）

本雛形には **2種類の異なるフローGUID** が存在する。

| GUID | 出現箇所 |
|---|---|
| `582ee26e-4e16-44dc-a679-bef89908b2c5` | フォルダ名 `Microsoft.Flow/flows/582ee26e-.../`、`Microsoft.Flow/flows/manifest.json` の `flowAssets.assetPaths[0]`、ルート `manifest.json` の `resources` トップレベルキー（`type:"Microsoft.Flow/flows"`, `hierarchy:"Root"`） |
| `56f7fa9e-ed61-4e56-bc88-b9c759084a70` | `definition.json` の `name` フィールドおよび `id`（`/providers/Microsoft.Flow/flows/56f7fa9e-...`） |

すなわち「パッケージ構造上でフローを識別するGUID（フォルダ名／manifestリソースキー）」と「フロー定義自身が内部的に保持するフローGUID（Azure Logic Apps系リソース名）」は**別物**であり、一致しない。これはレガシーパッケージのエクスポート機構が、パッケージ側の資産管理用GUIDとは独立に、フロー自身のリソースIDを `definition.json` にそのまま保持しているためと考えられる。新パッケージ作成時にどちらのGUIDを新規発行するか（あるいは両方を新規発行するか）を混同しないよう、この二重構造は明示的に記録しておく必要がある。

---

## 9. 環境依存ID・ユーザー固有情報

| 項目 | 値 | 出現箇所 | 匿名化要否 |
|---|---|---|---|
| ユーザーメールアドレス | `iihoshi-yohei@jpo.go.jp` | ルートmanifest.json（Teams接続・SharePoint接続の `details.displayName`、2箇所） | **匿名化対象** |
| テナントID | `b6d94148-69a6-487a-8a69-88236d09260a` | definition.json `metadata.creator.tenantId` | **匿名化対象** |
| 作成者ユーザーGUID | `641b02f0-caf2-4b76-826c-c757d0cd98f4` | definition.json `metadata.creator.id` / `metadata.lastModifiedBy`（2箇所） | **匿名化対象** |
| Teams接続GUID | `c101e3dbe885457f8485de11c5e28a5e` | definition.json `connectionReferences.shared_teams.connectionName` | **匿名化対象** |
| SharePoint接続GUID | `054920e5a92b48b6b53f62b01b3cb354` | definition.json `connectionReferences.shared_sharepointonline.connectionName` | **匿名化対象** |
| パッケージテレメトリID | `789b5493-c0c7-4a16-b2fb-cbcad4c605d5` | ルートmanifest.json `details.packageTelemetryId` | 環境/エクスポート回ごとに変わる識別子（機微情報ではないが再利用しない） |
| Teams グループ（チーム）ID | `a7ac0c68-87ba-4613-8960-13660f0f5f56` | definition.json アクション①の `Uri` | 環境固有の設定値（個人情報ではないが対象チーム識別子） |
| SharePointサイト（テナント名含む） | `metijapan.sharepoint.com`（`/teams/pjteam_220400119`、`/sites/mROOM_240600018/...`） | definition.json アクション④の `dataset`/`uri` | 環境固有の設定値 |

---

## 10. GUID一覧

| GUID | 役割 |
|---|---|
| `582ee26e-4e16-44dc-a679-bef89908b2c5` | フローパッケージGUID（フォルダ名／ルートmanifestのRootリソースキー／flows-manifestのassetPaths） |
| `56f7fa9e-ed61-4e56-bc88-b9c759084a70` | definition.json内 `name`/`id` の実フローGUID（§8参照、上記とは別物） |
| `c32368a7-113e-497e-990f-aab3642f4011` | ルートmanifestの Teams APIリソースキー（apisMap.jsonの値と一致） |
| `bc99ff66-7006-40a6-b085-024409eb42bf` | ルートmanifestの Teams接続リソースキー（connectionsMap.jsonの値と一致） |
| `e4f31fdf-c13c-4607-8af5-06baa431158d` | ルートmanifestの SharePoint APIリソースキー（apisMap.jsonの値と一致） |
| `f1e38ae6-6c4b-4670-9e29-c58312fbd2fb` | ルートmanifestの SharePoint接続リソースキー（connectionsMap.jsonの値と一致） |
| `789b5493-c0c7-4a16-b2fb-cbcad4c605d5` | packageTelemetryId |
| `641b02f0-caf2-4b76-826c-c757d0cd98f4` | 作成者ユーザーGUID（匿名化対象） |
| `b6d94148-69a6-487a-8a69-88236d09260a` | テナントID（匿名化対象） |
| `c101e3dbe885457f8485de11c5e28a5e` | Teams接続GUID（ハイフン無し32桁形式。匿名化対象） |
| `054920e5a92b48b6b53f62b01b3cb354` | SharePoint接続GUID（ハイフン無し32桁形式。匿名化対象） |
| `a7ac0c68-87ba-4613-8960-13660f0f5f56` | Graph URIに埋め込まれたTeamsグループ（チーム）ID |

注: リソースキー系のGUID（`582ee26e-...`, `56f7fa9e-...`, `c32368a7-...` 等）は標準的な8-4-4-4-12ハイフン付き形式だが、`connectionReferences.*.connectionName` の2件のみハイフン無し32桁の16進文字列という別形式である点に注意。

---

## 11. タイムスタンプ

| フィールド | 値 | 出現箇所 |
|---|---|---|
| `createdTime` | `2026-07-16T05:15:07.8659338Z` | ルートmanifest.json `details.createdTime`（パッケージ生成時刻） |
| `clientLastModifiedTime` | `2026-07-16T05:13:28.4782639Z` | definition.json `metadata.clientLastModifiedTime`（フロー最終編集時刻） |
| `connectionKeySavedTimeKey` | `2026-07-16T05:13:28.4782639Z` | definition.json `metadata.connectionKeySavedTimeKey`（`clientLastModifiedTime`と同一値） |

`createdTime`（パッケージ生成）が `clientLastModifiedTime`（フロー編集）より約1分40秒後になっており、時系列として整合している（フローを編集 → 直後にエクスポート）。

---

## 12. バージョン情報

| フィールド | 値 | 出現箇所 |
|---|---|---|
| `schema` | `"1.0"` | ルートmanifest.json |
| `packageSchemaVersion` | `"1.0"` | Microsoft.Flow/flows/manifest.json |
| `$schema`（ワークフロー定義） | `https://schema.management.azure.com/providers/Microsoft.Logic/schemas/2016-06-01/workflowdefinition.json#` | definition.json |
| `contentVersion` | `"undefined"`（文字列リテラル） | definition.json |

`contentVersion` が実際のバージョン番号ではなく文字列 `"undefined"` になっている点は、この雛形固有の特徴（おそらく手動/簡易エクスポート経路でバージョンが実採番されなかったケース）として記録しておく。

---

## 13. チェックサムの有無

**チェックサム（ハッシュ値）は一切存在しない。** 5ファイルのいずれにも、また各マニフェストの `resources` 定義内にも、SHA256等のハッシュ値やチェックサム用フィールドは含まれていない。整合性検証はJSONパース可否・GUID/参照の突合でのみ行う必要がある。

---

## 14. 考察

### 14.1 この雛形の意義：Graph経由取得が実機で使える証拠

本雛形には、以下の2アクションが **実際にエクスポートされた実機のフロー** として含まれている。

- `Microsoft_Graph_HTTP_要求を送信する`（`shared_teams` コネクタ、`operationId:"HttpRequest"`）＝Teamsコネクタの「Microsoft Graph HTTP要求を送信します」アクションで `https://graph.microsoft.com/v1.0/groups/{groupId}/team` を直接呼び出している。
- `SharePoint_に_HTTP_要求を送信します`（`shared_sharepointonline` コネクタ、`operationId:"HttpRequest"`）＝SharePointコネクタの「HTTP要求を送信します」アクションで `_api/web/GetFolderByServerRelativeUrl(...)` を呼び出している。

これは、標準コネクタ（プレミアム不要）のTeamsコネクタ経由でMicrosoft Graph APIへ任意のHTTPリクエストを送信するという方式が、**仮説ではなく実際に動作するフローとして構築・エクスポート可能**であることを裏付けている。今回の新パッケージがTeamsのメッセージ／返信取得にGraph直叩き（`shared_teams` の `HttpRequest`）を採用している設計判断は、この雛形の実例によって裏付けられる。

### 14.2 新パッケージが本構造をどう踏襲・拡張したか

新パッケージ（`../flows/archive-meetings/source/package/Microsoft.Flow/flows/fcca0e31-6d8b-40a8-8d63-2441c979a2c7/`）は、パッケージの骨格（ルートmanifest.json＋flows/manifest.json＋definition.json＋apisMap.json＋connectionsMap.jsonの5点セット、`schema/packageSchemaVersion:"1.0"`、`resources`のtype/creationType/configurableBy/hierarchy/dependsOn構造）を**そのまま踏襲**しつつ、以下の点を拡張・変更している。

| 観点 | 雛形（sample_extracted_ref） | 新パッケージ（build） |
|---|---|---|
| コネクタ数 | 2（Teams, SharePoint） | **3**（Teams, SharePoint, **Content Conversion**=`shared_conversionservice` を追加。`HtmlToText`をHTML本文のテキスト変換に使用） |
| アクション命名 | 日本語表示名ベース（`Microsoft_Graph_HTTP_要求を送信する`、`JSON_の解析`、`作成`、`SharePoint_に_HTTP_要求を送信します`） | **英語＋アンダースコア**命名に統一（`Initialize_RunId`、`Scope_10_Get_Channel_Messages` 等） |
| アクション規模 | 4アクション・直列1本 | トップレベル**34アクション**（Initialize系25＋Scope系9段階：`Scope_10/20/30(ネスト)/40/50/60/70/90/99`）で構成 |
| トリガー入力 | 入力パラメータなし（空スキーマ） | `LookbackDays`/`DryRun`/`ForceReprocess` の3入力を定義 |
| フローGUID（definition.json name） | `56f7fa9e-ed61-4e56-bc88-b9c759084a70` | `2fe554b1-6ba6-4ce0-962c-07bde4bdb6ee`（新規匿名GUID） |
| フローパッケージGUID（フォルダ名） | `582ee26e-4e16-44dc-a679-bef89908b2c5` | `fcca0e31-6d8b-40a8-8d63-2441c979a2c7`（新規匿名GUID） |
| 接続参照GUID（connectionName） | 2件（`c101e3db...`, `054920e5...`） | **3件**（`a4d41dc2...`, `85cb9340...`, `0c025702...`。いずれも新規匿名GUID） |
| packageTelemetryId | `789b5493-c0c7-4a16-b2fb-cbcad4c605d5` | `dcf93182-0d8a-4f2e-b064-e0ed68b818d9`（新規） |
| `metadata.creator` | `{id, type:"User", tenantId}` の実値を保持 | `{}`（**空オブジェクト**。tenantId等一切なし） |
| ルートmanifest `details.creator` | `"N/A"` | `"N/A"`（同一パターンを踏襲） |
| ルートmanifest `details.displayName/description` | `"tmp"` / `""`（プレースホルダ） | `"PA_Migrate_Teams_Meeting_Archive_To_SPO"` / `"Teams課内会議アーカイブ（単一フロー）"`（実内容を記載） |
| 接続リソースの `details.displayName` | ユーザーのメールアドレス（実値） | `"Microsoft Teams への接続を選択してください"` 等の**汎用案内文言**（メール等の実値を完全排除） |
| `contentVersion` | `"undefined"`（リテラル文字列） | `"1.0.0.0"`（意味のあるバージョン文字列） |
| `connectionReferences.*.isProcessSimpleApiReferenceConversionAlreadyDone` | あり（`false`） | なし（不要フィールドを削除） |

なお、新パッケージの初期化変数 `varTeamId`（`a7ac0c68-87ba-4613-8960-13660f0f5f56`）は雛形のGraph URIに埋め込まれたグループIDと**同一値**であり、`varSiteAddress`（`https://metijapan.sharepoint.com/sites/mROOM_240600018`）や `varDestinationPath`（`123_伝送システム/00_共用フォルダ/60_庶務担当/99_過去の課内会議`）も雛形のSharePointアクションURIに現れる値と一致する。これらは個人情報ではなく実行対象を指す運用上の設定値であるため匿名化の対象とはせず、雛形から実値をそのまま既定値として引き継ぎ、インポート後に利用者が確認・変更する前提としている（インポート後の再設定ポイントとして別途手順書に明記済み）。

### 14.3 匿名化対象一覧（新パッケージから除去した値）

| 除去した値 | 種別 | 雛形での出現箇所 |
|---|---|---|
| `iihoshi-yohei@jpo.go.jp` | ユーザーメールアドレス | ルートmanifest.json 接続リソース `details.displayName`（2箇所） |
| `641b02f0-caf2-4b76-826c-c757d0cd98f4` | 作成者ユーザーGUID | definition.json `metadata.creator.id` / `lastModifiedBy` |
| `b6d94148-69a6-487a-8a69-88236d09260a` | テナントID | definition.json `metadata.creator.tenantId` |
| `c101e3dbe885457f8485de11c5e28a5e` | Teams接続GUID | definition.json `connectionReferences.shared_teams.connectionName` |
| `054920e5a92b48b6b53f62b01b3cb354` | SharePoint接続GUID | definition.json `connectionReferences.shared_sharepointonline.connectionName` |
| `56f7fa9e-ed61-4e56-bc88-b9c759084a70` | フローGUID（definition.json name） | 新規GUID（`2fe554b1-...`）に置換 |
| `582ee26e-4e16-44dc-a679-bef89908b2c5` | フローパッケージGUID（フォルダ名） | 新規GUID（`fcca0e31-...`）に置換 |
| `789b5493-c0c7-4a16-b2fb-cbcad4c605d5` | packageTelemetryId | 新規GUID（`dcf93182-...`）に置換 |

これらに加え、`metadata` 内の `workflowEntityId`/`processAdvisorMetadata`/`flowChargedByPaygo`/`flowclientsuspension*`/`clientLastModifiedTime`/`connectionKeySavedTimeKey` 等、雛形固有のランタイム付随情報も新パッケージでは保持していない（`provisioningMethod`/`creationSource`/`modifiedSources` のみ踏襲）。

---

以上。参照元: `extracted/sample_extracted_ref/`（全5ファイル読了）、`../flows/archive-meetings/source/package/`（`manifest.json`、`Microsoft.Flow/flows/manifest.json`、`Microsoft.Flow/flows/fcca0e31-6d8b-40a8-8d63-2441c979a2c7/{definition.json,apisMap.json,connectionsMap.json}`）、`SINGLE_FLOW_FACTS.md`。

---

## 追加サンプル: create_meeting_list_sample_20260716105612.zip（実働フロー）

本章は、上記の「雛形」（4アクションのみの検証用フロー）とは別に入手した、**実環境で作成・動作実績のある**フロー `create_meeting_list_sample`（パッケージ作成時刻`2026-07-16T10:56:12Z`）の解析結果である。展開先は`extracted/create_meeting_list_sample_ref/`（読み取り専用で参照）、整形済み定義は `extracted/sample2_definition_pretty.json`。以下は同ファイルを全読了したうえでの事実ベースの記載であり、`../_legacy/knowledge_base_brief.md`「実働サンプルの機械解析での追加発見」節の内容と整合させている。

### パッケージ形式

雛形・当方の`../flows/archive-meetings/source/package/`と同じ**レガシー5エントリ形式**である（実ファイルで確認済み）。

```
manifest.json（ルート。displayName="create_meeting_list_sample"）
Microsoft.Flow/flows/manifest.json
Microsoft.Flow/flows/70faf892-7257-40e8-b86e-17a8ad8c2b75/definition.json
Microsoft.Flow/flows/70faf892-7257-40e8-b86e-17a8ad8c2b75/apisMap.json
Microsoft.Flow/flows/70faf892-7257-40e8-b86e-17a8ad8c2b75/connectionsMap.json
```

フローパッケージGUID（フォルダ名）`70faf892-7257-40e8-b86e-17a8ad8c2b75`と、`definition.json`内の`name`（`b27d4b3e-9972-4fdb-8ae3-d1905febfd9f`）は別値であり、雛形（§8）と同じ二重GUID構造が確認できる。コネクタは3種（Teams／SharePoint／Content Conversion）で当方フローと同一。

### フロー構造（18アクション）

トリガーは雛形と同じ`manual`（Request/Button、入力なし）。トップレベル6アクション＋ネスト内訳で、機械カウントで**総18アクション**（トリガー除く）。

| # | アクション名 | type | 位置 |
|---|---|---|---|
| 1 | Initialize_ChildAttachments | InitializeVariable | ルート |
| 2 | GetItems_MeetingList | OpenApiConnection(GetItems) | ルート |
| 3 | ForEach_ExistingMeetingItem | Foreach | ルート |
| 4 | └ DeleteItem_MeetingItem | OpenApiConnection(DeleteItem) | ForEach_ExistingMeetingItem内 |
| 5 | Graph_GetChannelMessages_Top50 | OpenApiConnection(HttpRequest) | ルート |
| 6 | ParseJson_ChannelMessages | ParseJson | ルート |
| 7 | ForEach_ChannelMessage | Foreach | ルート |
| 8 | └ If_IsChannelMessage | If | ForEach_ChannelMessage内 |
| 9 |   └ HtmlToText_MessageBody | OpenApiConnection(HtmlToText) | If_IsChannelMessage内 |
| 10 |   └ CreateItem_MeetingDetail | OpenApiConnection(PostItem) | If_IsChannelMessage内 |
| 11 |   └ Graph_GetMessageReplies_Top50 | OpenApiConnection(HttpRequest) | If_IsChannelMessage内 |
| 12 |   └ ParseJson_MessageReplies | ParseJson | If_IsChannelMessage内 |
| 13 |   └ ForEach_Reply | Foreach | If_IsChannelMessage内 |
| 14 |     └ SetVar_ChildAttachments_Append | SetVariable | ForEach_Reply内 |
| 15 |     └ Compose_ReplyAttachments | Compose | ForEach_Reply内 |
| 16 |   └ SetVar_ChildAttachments_Clear | SetVariable | If_IsChannelMessage内 |
| 17 |   └ Select_AttachmentLinks | Select | If_IsChannelMessage内 |
| 18 |   └ Filter_AttachmentLinks | Query | If_IsChannelMessage内 |

実行順は「①既存のSharePointリスト項目を全件削除→②Graphから親投稿を取得→③投稿ごとに本文変換・返信取得・添付リンク組み立て→④SharePointリストへ新規項目として作成」という一本道の直列フローで、当方フローのようなDo untilページングやScope分割は無い。

### 参考にした実装（実環境で動作実績のある実装として採用）

- **Graph URL構成**: `https://graph.microsoft.com/v1.0/teams/{teamId}/channels/{channelId}/messages?$top=50`（`Graph_GetChannelMessages_Top50`のUri）。当方の親投稿・返信取得URLと同型。
- **`%3A`/`%40`エンコード**: 上記Uri内の`channelId`部分が`19%3A53e5d619e45b4fda8d0dc7f2858a9d64%40thread.tacv2`とURLエンコード済みの状態でハードコードされている（`:`→`%3A`、`@`→`%40`）。チャネルIDのURLエンコードが実際に必要であることの直接的な証拠。
- **`uriComponent(メッセージID)`**: `Graph_GetMessageReplies_Top50`のUriで、返信取得URLの`messageId`部分だけを`uriComponent(items('ForEach_ChannelMessage')?['id'])`で動的にエンコードしている（teamId・channelIdは文字列連結のまま）。
- **HtmlToTextの`Content`キー**: `HtmlToText_MessageBody`の`parameters`が`{"Content": "..."}`。パラメータキー名`Content`の実例。
- **PostItemの`item/`内部列名**: `CreateItem_MeetingDetail`（operationId=PostItem）が`item/Title`、`item/OData__x30d5__x30a1__x30a4__x30eb_`のような`item/`＋内部列名の形式で列値を渡している。日本語列名（例:「ファイル」）の内部名が`OData__x30d5__x30a1__x30a4__x30eb_`という`OData__xHHHH_`形式のUnicodeエスケープになることを実例で確認できる。
- **`connectionReferences`のEmbedded形式と`shared_teams-2`サフィックス**: `connectionReferences`は3件とも`"source": "Embedded"`（雛形・当方採用の`Invoker`とは異なる形式）。Teamsのキーのみ`shared_teams-2`と連番サフィックスが付き、対応する`host.connectionName`もこのキーと一致させている。

### 移植しなかった設計バグ（動作実績はあるが設計上劣位）

- **SetVariable上書き蓄積＝最後の返信の添付しか残らない**: `SetVar_ChildAttachments_Append`は`ForEach_Reply`の反復ごとに`varChildAttachments`を`union(createArray(item()), 当該返信のattachments)`で**上書き**しており、前の反復の内容を累積しない。ループ終了後に残るのは最後の返信の添付だけになる。
- **`createArray(item())`の型混入**: 上記の式は返信オブジェクト自身（`item()`）も配列に含めてしまい、「添付一覧」のはずの配列に投稿オブジェクトが混入する。後続の`Select_AttachmentLinks`が`item()?['contentUrl']`の有無で判定し、`Filter_AttachmentLinks`が空要素を除去するため、たまたま実害が表面化していないだけである。
- **取得前に全削除する危険な実行順序**: `runAfter`を辿ると、`GetItems_MeetingList`→`ForEach_ExistingMeetingItem`（`DeleteItem_MeetingItem`で既存項目を全件削除）が**先**に実行され、その後で`Graph_GetChannelMessages_Top50`が実行される。Graph側の取得が失敗・0件だった場合でも、SharePointリストは既に削除済みでロールバックできない。「新規データの取得に成功したことを確認してから破壊的処理を行う」という順序が正しい。
- **ページング無し**: `$top=50`のみで`@odata.nextLink`を追跡する仕組みが無く、親投稿・返信とも51件目以降は取得漏れになる。
- **封筒形ParseJsonのデッドスキーマ**: `ParseJson_ChannelMessages`・`ParseJson_MessageReplies`のスキーマは`{statusCode, headers, body:{value:[...]}}`という封筒形だが、実際に流し込まれる`content`（`body('Graph_...')`＝Graphのフラットな応答）は封筒を持たない。JSON Schemaはトップレベルに`required`が無く、`properties`は「キーが存在する場合のみ」検証される仕様のため、この不一致はエラーとして表面化しない（実害の無い"デッドスキーマ"）。スキーマの形と実際の参照パスは一致させておくべき、という教訓として記録する。
- **値式末尾の`\n`混入**: `item/OData__x6295__x7a3f__x65e5__x6642_`・`item/OData__x5b9b__x5148_`・`item/URL`の式はいずれも`"@{...}\n"`という形で、閉じ括弧の外側に改行文字がそのまま置かれており、SharePoint列の値に改行が混入する。
- **UTC・JSTのタイムゾーン基準不整合**: `item/Title`は`lastModifiedDateTime`を`convertTimeZone(...,'UTC','Tokyo Standard Time')`でJST変換しているが、投稿日時列（`item/OData__x6295__x7a3f__x65e5__x6642_`）は`createdDateTime`を`formatDateTime`するだけでタイムゾーン変換していない。同一項目内でタイムゾーンの基準が列ごとに食い違っている。
- **`mentions[0]`の決め打ち**: `items('ForEach_ChannelMessage')?['mentions']?[0]?['mentionText']`のように、メンション配列の先頭だけを無条件に採用しており、複数メンションや空配列に対する妥当性検討がない。

### 当方への反映

- **uriComponent化の直接的な根拠**: 本サンプルの`uriComponent(メッセージID)`の実例が、当方v5での`Set_NextLink_First`／`Set_ReplyNextLink_First`へのuriComponent導入（実装手順書11章・12章）の裏付けになっている。
- **`body('Teams HttpRequest')`はGraph応答そのものという確証**: `Graph_GetChannelMessages_Top50`（`type: OpenApiConnection`）の出力を`ParseJson_ChannelMessages`の`content`に`@body('Graph_GetChannelMessages_Top50')`として渡しており、これは当方の`body('Get_Channel_Messages')?['value']`という参照パターンと同一の使い方である。少なくともTeamsのHttpRequestアクションについて`body()`がGraphの応答JSONを正しく返すことを、動作実績のある実例で確認できた。
- **封筒構造の理解→v6の`body/`修正の根拠**: 本サンプルの`ParseJson`スキーマが`{statusCode, headers, body}`という封筒形を明示的に定義していたことが、「`type: OpenApiConnection`のアクションは封筒を返す」という構造の再確認につながった。この理解をもとに当方定義を見直した結果、SharePointコネクタ（`Create_Attachment_File`・`Get_Saved_File_Properties`等）の出力を`outputs(...)`で直接参照していた5箇所が誤りだったと判明し、v6で`body(...)`参照に修正した（実装手順書16章・27章）。
