# リスト操作・メール同期のREST仕様

SharePoint 側はすべて「SharePoint に HTTP 要求を送信」（`operationId=HttpRequest`）＋ REST。
理由: リスト名が実行時入力のため、`PostItem`（項目の作成）等では `dataset`/`table` を式にできず
保存時に `OpenApiOperationParameterValidationFailed` になる
（[error_catalog.md](../../../handbook/knowledge/error_catalog.md) 既知エラー5）。

- `dataset` は全34アクションとも `@variables('varSiteUrl')`（**サイトURLを定義に固定しない**）
- 対象は必ず**リストID**で指定する。`GetByTitle(` は1件も使わない
- ボディは Compose のオブジェクト＋`@string(outputs('Compose_X'))`（文字列連結で組み立てない）

区分の表記: 【実証済み】= 本リポジトリの他案件が実環境で動作確認済みの形式 /
【要実環境確認】= 本フローで初めて使う形式。

---

## 1. サイト疎通の確認

```text
GET  _api/web?$select=Id,Title,Url
Headers: {"Accept": "application/json;odata=nometadata"}
```

【実証済み】書き込みの前に必ず通す。接続のスコープ外サイト・存在しないサイトはここで失敗し、
以降のRESTに到達しない。応答の `Id` を `varSiteId` に保持して結果に載せる。

---

## 2. 同名リストの確認（指示§6）

```text
GET  _api/web/lists?$select=Id,Title,Hidden,BaseTemplate,RootFolder/ServerRelativeUrl&$expand=RootFolder&$top=5000
Headers: {"Accept": "application/json;odata=nometadata"}
```

【実証済み】`Hidden` を含めて**非表示リストも取得**する。見落とすと二重作成になる。

> **`$select` から `RootFolder/ServerRelativeUrl` を落とさないこと。**
> `$expand=RootFolder` を投影なしで書くと、SharePoint がアクセス権の無いシステムリストまで
> 実体化しようとして **403 Access denied** になる（2026-08-03 に実発生）。
> → [sharepoint_rest_list_provisioning.md §15](../../../handbook/knowledge/sharepoint_rest_list_provisioning.md)

```text
Filter_Matching_Lists (Query)
  from  : coalesce(body('Get_All_Lists')?['value'], json('[]'))
  where : equals(toLower(trim(coalesce(item()?['Title'], ''))), toLower(variables('varListName')))
```

- **正規化後の完全一致**。`contains(` は使わない（部分一致による誤検出の排除）
- 前後の空白（`trim`）と大文字小文字（`toLower`）を吸収する

| 一致件数 | 判定 |
|---|---|
| 0件 | 新規作成経路へ |
| 1件 かつ `Hidden=false` かつ `BaseTemplate=100` | 既存経路へ（`varListExists=true`） |
| 1件 だが 非表示 または `BaseTemplate≠100` | `ERR_LIST_NOT_GENERIC` で安全終了 |
| 2件以上 | `ERR_LIST_AMBIGUOUS` で安全終了 |

`BaseTemplate=100` はカスタムリスト（汎用リスト）。ドキュメントライブラリ等のシステムリストへ
アイテムを書き込まないための関門。

---

## 3. リストの新規作成（指示§7）

### 3.1 作成直前の再確認

```text
GET  _api/web/lists?$select=Id,Title,Hidden,BaseTemplate,RootFolder/ServerRelativeUrl&$expand=RootFolder&$top=5000
     （§2 と完全に同じURI。短くしないこと）
Filter_Recheck_Lists (Query)     （§2と同じ判定）
```

ここで見つかった場合は**作成せず既存経路へ合流**する（同時実行で他方が先に作成したケース）。
そのリストを削除も上書きもしない。`schemaWarnings` に記録する。

### 3.2 作成

```text
POST _api/web/lists
Headers: {"Accept": "application/json;odata=verbose",
          "Content-Type": "application/json;odata=verbose"}
Body   : @string(outputs('Compose_Create_List_Body'))

Compose_Create_List_Body = {
  "__metadata": {"type": "SP.List"},
  "AllowContentTypes": false,
  "BaseTemplate": 100,
  "ContentTypesEnabled": false,
  "Description": "Power Automateにより作成されたメール同期用リスト",
  "Title": "@variables('varListName')"
}
```

【実証済み】`__metadata` を含めるため `odata=verbose` が必須。

### 3.3 成功／失敗の判定（**失敗を成功として扱わない**）

```text
Set_Create_Status_Code          runAfter: Create_List [Succeeded, Failed]
Condition_Create_Succeeded      200 <= status <= 299 のときのみ ID を採用
  → varListId = trim(string(coalesce(body('Create_List')?['d']?['Id'], '')))
    varCreatedInThisRun = true
```

`odata=verbose` の応答は `{"d": {...}}` で包まれるため `?['d']?['Id']` で参照する。

### 3.4 作成失敗時の再確認

```text
Retry_Get_Lists_After_Failure   runAfter: Create_List [Failed, TimedOut]
Filter_Retry_Lists              （§2と同じ判定）
Condition_Create_Failed_But_Exists
  一致あり → 既存リストとして処理（競合。削除も上書きもしない）
  一致なし → ERR_LIST_CREATE_FAILED
```

---

## 4. 列の作成（指示§9・§10）

**`varCreatedInThisRun == true` のガード配下でのみ実行**する。既存リストの列は絶対に触らない。

### 4.1 冪等化（存在しない列だけ作る）

```text
GET  _api/web/lists(guid'{listId}')/fields?$select=Id,Title,InternalName,TypeAsString&$top=5000
Filter_Existing_Field_<内部名> (Query)
  where : equals(coalesce(item()?['InternalName'], ''), '<内部名>')
Condition_Create_Field_<内部名>
  length == 0 のときだけ createFieldAsXml を実行する（既存列の削除・再作成はしない）
```

### 4.2 作成

```text
POST _api/web/lists(guid'{listId}')/fields/createFieldAsXml
Headers: verbose
Body   : {"parameters": {"__metadata": {"type": "SP.XmlSchemaFieldCreationInformation"},
                         "Options": 0, "SchemaXml": "<Field ... />"}}
```

【実証済み】`Options: 0` かつ `DisplayName=Name=StaticName=ASCII` にすると、
内部名が指定どおりになる（日本語表示名で作ると `OData__xHHHH_` 形式になり後続が壊れる）。
→ [sharepoint_rest_list_provisioning.md §4](../../../handbook/knowledge/sharepoint_rest_list_provisioning.md)

### 4.3 SchemaXml

```xml
<Field Type="Text" Name="MessageId" StaticName="MessageId" DisplayName="MessageId"
       Required="TRUE" MaxLength="255" Indexed="TRUE" EnforceUniqueValues="TRUE" />

<Field Type="DateTime" Name="ReceivedDateTime" StaticName="ReceivedDateTime"
       DisplayName="ReceivedDateTime" Required="FALSE" Format="DateTime" Indexed="TRUE" />

<Field Type="Text" Name="SenderAddress" StaticName="SenderAddress"
       DisplayName="SenderAddress" Required="FALSE" MaxLength="255" />

<Field Type="Text" Name="Subject" StaticName="Subject"
       DisplayName="Subject" Required="FALSE" MaxLength="255" />

<Field Type="Note" Name="BodyPlainText" StaticName="BodyPlainText"
       DisplayName="BodyPlainText" Required="FALSE" NumLines="10"
       RichText="FALSE" AppendOnly="FALSE" />
```

- `MessageId`: 重複判定のキー。`Indexed="TRUE"` は `EnforceUniqueValues="TRUE"` の前提
- `BodyPlainText`: `RichText="FALSE"` でリッチテキスト無効、`AppendOnly="FALSE"` で追記履歴なし
- 【要実環境確認】`EnforceUniqueValues` が `createFieldAsXml` で反映されるかは未確認。
  作成後に検証し、反映されていなければ `schemaWarnings` に記録する設計にしてある

### 4.4 表示名の日本語化

```text
POST _api/web/lists(guid'{listId}')/fields/getbyinternalnameortitle('MessageId')
Headers: {"Accept": "...nometadata", "Content-Type": "...nometadata",
          "IF-MATCH": "*", "X-HTTP-Method": "MERGE"}
Body   : {"Title": "メッセージID"}
```

内部名（`InternalName`）は変わらないため、後続の `$filter` や `item` のキーは壊れない。
**表示名を後から人が変更しても処理が壊れない**構造にするための一手間。

### 4.5 Title 列（指示§9）

```text
POST _api/web/lists(guid'{listId}')/fields/getbyinternalnameortitle('Title')
Headers: nometadata + IF-MATCH:* + X-HTTP-Method: MERGE
Body   : {"Required": false}
```

【実証済み】Title 列は**削除しない**（既定列を削除するとリストが壊れうる）。
必須解除して既定ビューから外すことで、利用者から見える業務用列を5列にする。

---

## 5. 既定ビュー（指示§11）

**`varCreatedInThisRun == true` のガード配下でのみ実行**する。

```text
GET  _api/web/lists(guid'{listId}')/views?$select=Id,Title,DefaultView&$top=100
Filter_Default_View (Query)
  where : equals(coalesce(item()?['DefaultView'], false), true)
```

【実証済み】既定ビューは**ビュー名ではなく `DefaultView` プロパティ**で特定する。
「すべてのアイテム」「All Items」という表示名を前提にしない。

```text
POST .../views(guid'{viewId}')/viewfields/removeAllViewFields()
Headers: nometadata（ボディなし）

POST .../views(guid'{viewId}')/viewfields/AddViewField('MessageId')   … 5列を順に
Headers: verbose + IF-MATCH:* + X-HTTP-Method: MERGE
Body   : {"__metadata": {"type": "SP.View"}, "SetAsDefaultView": true}
```

追加順が表示順になる: `MessageId → ReceivedDateTime → SenderAddress → Subject → BodyPlainText`。

### 並び順（日時の降順）

```text
POST .../views(guid'{viewId}')
Headers: verbose + IF-MATCH:* + X-HTTP-Method: MERGE
Body   : {"__metadata": {"type": "SP.View"},
          "ViewQuery": "<OrderBy><FieldRef Name='ReceivedDateTime' Ascending='FALSE' />
                        <FieldRef Name='ID' Ascending='FALSE' /></OrderBy>"}
```

【要実環境確認】`ViewQuery` による並び順設定は公式のCAMLスキーマに沿った形式だが、
本リポジトリでの実行実績は無い。

第2ソートキーに `ID` の降順を入れて、受信日時が同一のときの順序を安定させる（指示§11）。
アイテムの作成順序には依存していない。

```text
GET  .../views(guid'{viewId}')/ViewFields    列順の検証
```

---

## 6. 既存リストのスキーマ確認（指示§8）

既存経路・新規経路のどちらも通る最後の関門。**列は一切変更しない。**

```text
GET  _api/web/lists(guid'{listId}')?$select=Id,Title,ListItemEntityTypeFullName,RootFolder/ServerRelativeUrl&$expand=RootFolder
GET  _api/web/lists(guid'{listId}')/fields?$select=Id,Title,InternalName,TypeAsString&$top=5000
```

内部名ごとに Filter → 存在しなければ `missingFields` へ、型が違えば `incompatibleFields` へ積む。

| 内部名 | 互換とみなす `TypeAsString` |
|---|---|
| `MessageId` | `Text` |
| `ReceivedDateTime` | `DateTime` |
| `SenderAddress` | `Text` |
| `Subject` | `Text` |
| `BodyPlainText` | `Note` |

両方が空のときだけ `varSchemaOk = true` になり、メール取得へ進む。
不足・不一致があれば `ERR_SCHEMA_INCOMPATIBLE` で終了し、**メール取得も行わない**。

`ListItemEntityTypeFullName` は次節のアイテム登録で `__metadata.type` に使う。
テナントによって `__metadata` の型指定を要求される差異を**構造的に回避**するため、
実リストから取得した値を必ず添える。

`RootFolder.ServerRelativeUrl` と `varSiteOrigin` から `listUrl` を決定的に組み立てる
（`GetFileItem` 等の名前解決に依存しない）。

---

## 7. メールの取得（指示§12）

```text
Get_Emails  shared_office365 / GetEmailsV3
  mailboxAddress     = @variables('varMailbox')
  folderPath         = "Inbox"
  top                = @variables('varRequestedCount')
  fetchOnlyUnread    = false      既読・未読の両方
  includeAttachments = false      添付の内容は取得しない
```

- **既読化・移動・削除・フラグ・送信のアクションは定義に1件も存在しない**（検証スクリプトで0件確認）
- 出力順は公式に保証されていないため、**自前で降順に並べ替えて上位N件を採用**する

```text
Compose_Sorted_Emails =
  take(reverse(sort(coalesce(body('Get_Emails')?['value'], json('[]')), 'receivedDateTime')),
       variables('varRequestedCount'))
```

`sort` は昇順のみのため `reverse` を併用する
（[expression_examples.md §14](../../../handbook/knowledge/expression_examples.md)）。
`coalesce(..., json('[]'))` で Apply to each の入力に配列を保証している
（[コアルール5](../../../handbook/rules/00_power_automate_core_rules.md)）。

### 【要実環境確認】
- パラメータキー名（`folderPath` / `fetchOnlyUnread` / `includeAttachments` / `mailboxAddress` / `top`）
- `GetEmailsV3` の既定の並び順。**コネクタが古い順にN件返す場合、自前の並べ替えでは最新N件にならない**。
  実機で `fetchedCount` と最古／最新の受信日時を確認する

---

## 8. 本文のプレーンテキスト化（指示§13）

```text
Condition_Item_Has_Body   length(Compose_Body_Html) > 0 のときだけ変換する
  Convert_Body_To_Text    shared_conversionservice / HtmlToText
    Content = @outputs('Compose_Body_Html')
  Set_Convert_Status_Code           runAfter [Succeeded, Failed]
  Set_Item_Body_Text                runAfter [Succeeded]
  Set_Item_Error_Convert_Failed     runAfter [Failed, TimedOut] → ERR_BODY_CONVERSION_FAILED
```

変換に失敗した場合、**HTMLをそのまま登録せず**その1件だけを失敗として記録し次へ進む。

```text
Condition_Body_Too_Long   length > 63999
  true : substring で切り詰め、truncatedItems[] と truncatedCount に記録
  else : そのまま
```

---

## 9. 重複判定と登録／更新（指示§14・§15）

### 9.1 メッセージID

```text
Compose_Message_Id =
  trim(string(coalesce(items('Foreach_Email')?['internetMessageId'],
                       items('Foreach_Email')?['id'], '')))
```

`Internet Message Id` を優先し、無ければコネクタのメッセージIDを使う（指示§10.1）。
空または255文字超なら `ERR_ITEM_MESSAGE_ID_UNUSABLE` として当該1件のみ失敗記録。

### 9.2 検索（ODataエスケープ）

```text
GET  @concat('_api/web/lists(guid''', variables('varListId'),
             ''')/items?$select=Id&$top=2&$filter=MessageId eq ''',
             uriComponent(replace(outputs('Compose_Message_Id'), '''', '''''')), '''')
```

2段のエスケープ:

1. `replace(x, '''', '''''')` — シングルクォートを2重化し、OData のリテラル境界を守る
2. `uriComponent(...)` — `& < > # ? 空白 " 日本語 絵文字` をURLエンコードする。
   サーバ側で `%27%27` が `''` に復号され、エスケープ済みクォートとして解釈される

**文字列連結だけのクエリは作らない。** `$top=2` にしているのは「2件以上か」を判定するため。

### 9.3 分岐

| 一致件数 | 動作 |
|---|---|
| 検索が失敗 | `ERR_ITEM_SEARCH_FAILED` を記録。**一致0件と誤認して作成しない** |
| 0件 | 新規作成 |
| 1件 | `IF-MATCH:*` + `X-HTTP-Method: MERGE` で更新（日時・送信元・件名・本文） |
| 2件以上 | **書き込まず** `duplicates[]` に記録 |

### 9.4 登録

```text
POST _api/web/lists(guid'{listId}')/items
Headers: verbose
Body   : {"__metadata": {"type": "@variables('varListEntityType')"},
          "MessageId": "@outputs('Compose_Message_Id')",
          "ReceivedDateTime": "@if(empty(outputs('Compose_Received')), null, outputs('Compose_Received'))",
          "SenderAddress": "@outputs('Compose_Sender')",
          "Subject": "@outputs('Compose_Subject')",
          "BodyPlainText": "@variables('varItemBodyFinal')"}
```

日時は Outlook が返す ISO 8601（UTC）をそのまま渡す。文字列として整形しないため
タイムゾーン情報を失わない。SharePoint はUTCで保持し、サイトのタイムゾーン設定で表示する。
受信日時が取れない場合は `null` を渡す（空文字を日付列に入れない）。

### 9.5 更新

```text
POST _api/web/lists(guid'{listId}')/items({itemId})
Headers: verbose + IF-MATCH:* + X-HTTP-Method: MERGE
Body   : MessageId を除いた4項目
```

### 9.6 作成失敗時のフォールバック（指示§17）

```text
Set_Item_Create_Failed   runAfter: Create_List_Item [Failed, TimedOut]
Condition_Create_Failed_Fallback  varItemCreateFailed == true
  Research_After_Create_Failure   （§9.2と同じ検索）
  一致あり → 更新して updatedCount を加算（他の実行が先に作成したケース）
  一致なし → ERR_ITEM_CREATE_FAILED を記録して failedCount を加算
```

`MessageId` 列の一意制約と組み合わせることで、
「一時的な検索結果0件による重複作成」を吸収する。

---

## 10. 同時実行対策のまとめ（指示§17）

| 対策 | 実装 |
|---|---|
| 同名リストの二重作成 | 作成**直前**の再確認＋作成失敗時の再確認（見つかれば既存として合流） |
| 同一メールの二重登録 | `MessageId` の一意制約＋作成失敗時の再検索フォールバック |
| 一時的な検索結果0件 | 検索失敗を「0件」と誤認せず `ERR_ITEM_SEARCH_FAILED` として書き込みを見送る |
| 反復間の競合 | `Apply to each` の `concurrency.repetitions = 1`（並列オフ） |
| 他方の実行による上書き | 更新は MERGE（指定した列だけ更新。他の列を消さない） |

【要実環境確認】手動トリガーのため**トリガーレベルの同時実行制御は行えない**。
上記は緩和であって完全な排他ではない。
