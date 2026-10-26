# リスト操作仕様（同名確認・作成・列初期化・sample_raw・既定ビュー）

指示書§9・§11・§13〜§24 に対応する仕様です。REST形式は実働リファレンス `CreateKnowledgeList`（`references/extracted/reference_original/`。実環境で動作実績あり）から流用しています。

すべての HTTP 要求は SharePoint コネクタ「SharePoint に HTTP 要求を送信します」（`shared_sharepointonline` / `operationId=HttpRequest`）で、`dataset`（サイトのアドレス）は全アクション共通で `@variables('varSiteUrl')` です。

> **`dataset` に式を指定した状態での保存・実行は 2026-07-24 に実環境で確認済み**です（本件最大のリスクだった項目。既存SPフロー2本はいずれも静的リテラルでしたが、式指定でも保存・実行できることが実証されました）。

実証度の凡例:
- **【実証済み】** = 実働リファレンス `CreateKnowledgeList` に同一形式が存在する
- **【本フローで実証】** = 2026-07-24 の実環境実行（`status: Created`）で動作を確認した
- **【要実環境確認】** = まだ実機で通っていない（主に失敗経路）

詳細な確認状況は [../tests/validation_report.md](../tests/validation_report.md) §5 を参照してください。

---

## 1. 同名リストの確認（§9）

### 1.1 全リストの取得 【本フローで実証】

```text
Method  : GET
Uri     : _api/web/lists?$select=Id,Title,Hidden,BaseTemplate,RootFolder/ServerRelativeUrl
          &$expand=RootFolder&$top=5000
Headers : Accept: application/json;odata=nometadata
```

`Hidden` で絞り込まず全件を取得します。**非表示リストも同名判定の対象**です（§9）。

### 1.2 比較方法（§9.2）

`Filter_Matching_List_Names`（配列のフィルター処理）:

```text
from  : @variables('varExistingLists')
where : @equals(toLower(trim(coalesce(item()?['Title'], ''))),
                toLower(trim(variables('varListName'))))
```

- **大文字・小文字だけが異なる名前も同一**とみなす（`toLower`）
- **先頭・末尾の空白だけが異なる名前も同一**とみなす（`trim`）

`Determine_List_Existence` が `varListExists = @greater(length(variables('varMatchedLists')), 0)` を設定します。

### 1.3 同名リストが存在する場合（§9.3）

`Scope_Create_List` 以降のすべてが Condition で false になり、**新規作成も既存リストへの変更も一切行いません**。

- 新しいリストを作成しない ✅
- 既存リストを変更しない ✅（GET 以外を発行しない）
- 既存リストの列を削除しない ✅
- 既存リストのビューを変更しない ✅
- 既存リストを初期化しない ✅
- 正常終了扱い ✅（`success: true`）
- 結果は `status: "AlreadyExists"` ✅

`Return_Already_Exists`（Compose）が、存在確認で得た情報から `existingList` を組み立てます（新たな GET は行いません）。

---

## 2. リストの新規作成（§11）と競合対策（§10）

### 2.1 HTTP 要求 【実証済み】

```text
Method  : POST
Uri     : _api/web/lists
Headers : Accept: application/json;odata=verbose
          Content-Type: application/json;odata=verbose
Body    : @string(outputs('Compose_Create_List_Body'))
```

### 2.2 ボディの組み立て（§11.3）

**文字列連結では作りません。** `Compose_Create_List_Body`（作成アクション）でオブジェクトを組み立て、`string()` でJSON化します。

```json
{
  "__metadata": { "type": "SP.List" },
  "AllowContentTypes": false,
  "BaseTemplate": 100,
  "ContentTypesEnabled": false,
  "Description": "@variables('varListDescription')",
  "Title": "@variables('varListName')"
}
```

`string()` が値を正しくエスケープするため、**リスト名や説明に二重引用符・改行・円記号が含まれてもJSONが壊れません**。この方式は `archive-meetings` の REST 呼び出しで実証済みのパターンです。

`BaseTemplate: 100` は汎用リスト（カスタムリスト）。`odata=verbose` は `__metadata` を含めるため必須です。

### 2.3 作成結果の保持（§11.4）

作成応答（verbose 形式なので `d` でラップされます）から取得します。

```text
varCreatedListId    ← @trim(string(coalesce(body('Create_Generic_List')?['d']?['Id'], '')))
varCreatedListTitle ← @trim(string(coalesce(body('Create_Generic_List')?['d']?['Title'], '')))
varCreatedInThisRun ← true      ← ここだけが true を設定する箇所
```

`RootFolder` は作成応答に実体が含まれないため、**作成したリストIDで**改めて取得します 【本フローで実証】。

```text
GET _api/web/lists(guid'<varCreatedListId>')?$select=Id,Title&$expand=RootFolder
varCreatedListRootFolder ← body(...)?['RootFolder']?['ServerRelativeUrl']
```

**リスト名での再取得は行いません**（§10・§31）。

### 2.4 競合エラーへの対応（§10）

```text
Set_Create_Status_Code       runAfter: [Succeeded, Failed]  ← 失敗しても必ず実行
Condition_Create_Succeeded   HTTPステータスが 200〜299 か
  ├ true  : 上記 2.3 を実行
  └ false : varStatus = 'AlreadyExistsOrConflict' / created = false / varIsValid = false
```

作成に失敗したら**そこで終わります**。既存リストを取得して初期化する処理は定義に存在しません（[safety_mechanisms.md](safety_mechanisms.md) §3）。

---

## 3. 列の初期化（§12〜§17）

以下はすべて `varCreatedInThisRun == true` のガード配下でのみ実行されます。

### 3.1 アイテムが空であることの確認（§13）【本フローで実証】

```text
GET _api/web/lists(guid'<varCreatedListId>')/ItemCount
Accept: application/json;odata=nometadata
varItemCount ← @int(coalesce(body('Verify_Empty_List')?['value'], 0))
```

作成直後なので通常は 0 件です。**0件でない場合は異常として初期化を停止**します。**既存アイテムを削除する処理は実装していません**（§13）。

### 3.2 添付ファイル機能の無効化（§14）【実証済み】

```text
Method  : POST
Uri     : _api/web/lists(guid'<varCreatedListId>')
Headers : Accept/Content-Type: application/json;odata=verbose
          IF-MATCH: *
          X-HTTP-Method: MERGE
Body    : {"__metadata": {"type": "SP.List"}, "EnableAttachments": false}
```

`__metadata.type` は `SP.List` です（リファレンス `EnableAttachments` が `true` で成功している形式と同一。値だけ `false` にしています）。

### 3.3 Title の必須解除（§17）【実証済み】

```text
Method  : POST
Uri     : _api/web/lists(guid'<varCreatedListId>')/fields/getbyinternalnameortitle('Title')
Headers : Accept/Content-Type: application/json;odata=nometadata
          IF-MATCH: * / X-HTTP-Method: MERGE
Body    : {"Required": false}
```

リファレンスの `deactivateSPOTitle` と同一形式です（**nometadata** で `__metadata` 不要）。

### 3.4 列定義の取得（§15）【本フローで実証】

```text
GET _api/web/lists(guid'<varCreatedListId>')/fields
    ?$select=Id,Title,InternalName,StaticName,CanBeDeleted,Hidden,ReadOnlyField,
             Sealed,FromBaseType,Required,TypeAsString
```

### 3.5 削除対象の決定（§15.1）

```text
Filter_Deletable_Fields (配列のフィルター処理)
where : @and(equals(coalesce(item()?['CanBeDeleted'], false), true),
             not(equals(coalesce(item()?['InternalName'], ''), 'sample_raw')))
```

**列名の固定リストでは判定しません。** SharePoint が返す `CanBeDeleted` の値だけを根拠にします。

`CanBeDeleted=false` の列は `Filter_System_Fields` で別に集め、`varSkippedFields` に制約として記録します。

### 3.6 列の削除（§16）【本フローで実証】

```text
Apply_to_each_DeleteField   （並列オフ: concurrency.repetitions = 1）
  Delete_Deletable_Field
    POST _api/web/lists(guid'<varCreatedListId>')/fields(guid'<item Id>')/deleteObject()
    Accept: application/json;odata=nometadata   （ボディなし）
  Append_Deleted_Field        runAfter: [Succeeded]        → varDeletedFields
  Append_Field_Delete_Error   runAfter: [Failed, TimedOut] → varFieldDeleteErrors
```

- 蓄積はすべて「配列変数に追加」。**Set Variable による自己参照は使いません**（§16）。
- 1件でも失敗すれば `varFieldDeleteErrors` に残り、最終判定で `InitializationFailed` になります。**初期化全体を成功扱いにしません。**

### 3.7 削除不能なシステム列（§17）

| 方針 | 実装 |
|---|---|
| `CanBeDeleted=false` の列は削除しない | ✅ フィルタで対象外 |
| 既定ビューには追加しない | ✅ `sample_raw` しか追加しない |
| 既定ビューに存在する場合は除去する | ✅ `removeAllViewFields()` で全除去 |
| `Title` は可能であれば `Required=false` にする | ✅ 3.3 で実施 |
| 新規/編集/表示フォームから非表示化する | ❌ **未実施**（下記） |
| 非表示化できない列は制約として記録する | ✅ `varSkippedFields` に記録 |

**フォームからの非表示化は実装していません。** `SetShowInNewForm` 等の REST は本リポジトリに実在確認の証跡がなく、推測での実装は禁止事項に当たるためです。指示書§17 が許容するとおり制約として記録し、**「非表示化できた」とは報告しません**。

利用者から見える**データ列**が `sample_raw` だけであれば目的は満たされます（既定ビューからは除外済み）。

---

## 4. sample_raw 列の仕様（§18・§19）

### 4.1 列の仕様

| 項目 | 値 |
|---|---|
| 表示名 / 内部名 / StaticName | `sample_raw` |
| 型 | 複数行テキスト（`Note`） |
| リッチテキスト | 有効（`RichText="TRUE"`） |
| 拡張リッチテキスト | 有効（`RichTextMode="FullHtml"`） |
| HTML保存 | 可（FullHtml のため） |
| ハイパーリンク | 利用可能（`<a href="...">` を保存できる） |
| 必須 | いいえ（`Required="FALSE"`） |
| 追記専用 | いいえ（`AppendOnly="FALSE"`） |
| 行数 | 12（`NumLines="12"`） |

**単純なURL型ではありません。** HTML文字列を格納し、`<a href="https://example.com">リンク</a>` のようなアンカータグを保存できる列です。

### 4.2 Field XML（§18.2）

```xml
<Field Type="Note" Name="sample_raw" StaticName="sample_raw" DisplayName="sample_raw"
       Required="FALSE" NumLines="12" RichText="TRUE" RichTextMode="FullHtml"
       IsolateStyles="TRUE" RestrictedMode="FALSE" AppendOnly="FALSE" />
```

JSON への埋め込みは Compose のオブジェクト内に素の文字列として置き、`string()` でシリアライズします。**手動エスケープをしないため、XML・JSON とも壊れません。** `validate_list_flow.py` が `ET.fromstring()` でXMLとしてパースし、各属性値まで検証しています。

### 4.3 HTTP 要求（§18.3）【実証済み】

```text
Method  : POST
Uri     : _api/web/lists(guid'<varCreatedListId>')/fields/createFieldAsXml
Headers : Accept/Content-Type: application/json;odata=verbose
Body    : @string(outputs('Compose_SampleRaw_Field_Body'))
```

```json
{
  "parameters": {
    "__metadata": { "type": "SP.XmlSchemaFieldCreationInformation" },
    "SchemaXml": "<Field ... />",
    "Options": 0
  }
}
```

`Options: 0` では内部名が表示名から生成されます。`sample_raw` は ASCII なので**内部名は指定どおり `sample_raw` になります**（日本語表示名だと `OData__xHHHH_` 形式に化けるため、本フローでは ASCII 固定にしています）。

`AddToDefaultView` 相当のオプションには依存せず、§5 で既定ビューを明示的に再構築します（§18.3）。

### 4.4 作成確認（§19）【本フローで実証】

```text
GET _api/web/lists(guid'<varCreatedListId>')/fields/getbyinternalnameortitle('sample_raw')
    ?$select=Id,Title,InternalName,StaticName,TypeAsString,Required,Hidden,ReadOnlyField,SchemaXml
```

`Compose_SampleRaw_Verification` が次を**すべて**満たすかを判定します。

```text
InternalName == 'sample_raw'
Required     == false
Hidden       == false
TypeAsString == 'Note'                        （複数行テキスト系）
SchemaXml に RichTextMode="FullHtml" を含む   （リッチテキスト設定の反映）
```

1つでも欠ければ `ERR_SAMPLERAW_VERIFICATION_FAILED` を設定し、**初期化成功扱いにしません**。

---

## 5. 既定ビューの設定（§20〜§24）

### 5.1 既定ビューの特定（§20）【本フローで実証】

```text
GET _api/web/lists(guid'<varCreatedListId>')/views
    ?$select=Id,Title,DefaultView,Hidden,ViewType,RowLimit

Filter_Default_View : @equals(coalesce(item()?['DefaultView'], false), true)
varDefaultViewId    ← first(...)?['Id']
varDefaultViewTitle ← first(...)?['Title']
```

**ビュー名では判定しません。** 「すべてのアイテム」「All Items」といった表示名を前提にせず、`DefaultView` プロパティだけで特定します（§20）。

特定できなかった場合は `ERR_DEFAULT_VIEW_NOT_FOUND` で初期化を失敗させます。

### 5.2 表示列の全除去（§21）【実証済み（パスのみ新規）】

```text
Method  : POST
Uri     : _api/web/lists(guid'<varCreatedListId>')/views(guid'<varDefaultViewId>')
          /viewfields/removeAllViewFields()
Headers : Accept: application/json;odata=nometadata   （ボディなし）
```

既定ビュー自体は削除しません（列だけを除去します）。

> **【本フローで実証】**: リファレンスにあるのは `defaultView/viewfields/removeAllViewFields()`（既定ビューを暗黙に指す形）でしたが、§20〜§22 が既定ビューIDでの操作を指示しているため `views(guid'..')/viewfields/...` を採用しました。**この guid 指定形が動作することを 2026-07-24 の実環境実行で確認済み**です（既定ビューが `sample_raw` の1列だけになった）。

### 5.3 sample_raw だけを追加（§22）【実証済み（パスのみ新規）】

```text
Method  : POST
Uri     : _api/web/lists(guid'<varCreatedListId>')/views(guid'<varDefaultViewId>')
          /viewfields/AddViewField('sample_raw')
Headers : Accept/Content-Type: application/json;odata=verbose
          IF-MATCH: * / X-HTTP-Method: MERGE
Body    : {"__metadata": {"type": "SP.View"}, "SetAsDefaultView": true}
```

最終的に既定ビューのデータ列は `sample_raw` の1列だけになります。`Title` / `ID` / `Created` / `Modified` / `Created By` / `Modified By` / `Attachments` / `Edit` / `LinkTitle` などは追加しません（§23）。

選択チェックボックス・行メニュー・編集操作など SharePoint の UI が自動表示する操作要素は「列」に数えません（§22）。

### 5.4 ビュー設定の検証（§24）【本フローで実証】

```text
GET _api/web/lists(guid'<varCreatedListId>')/views(guid'<varDefaultViewId>')/ViewFields
varFinalViewFields ← @coalesce(body('Verify_Default_View_Fields')?['Items'], json('[]'))
```

最終判定（§25 の一部）で次を確認します。

```text
length(varFinalViewFields) == 1
first(varFinalViewFields)  == 'sample_raw'
```

これにより `sample_raw` 以外のデータ列・`Title`・`ID`・`Modified` 等が含まれていないことを機械的に確認します。

> **【本フローで実証】**: `odata=nometadata` での応答が `{"Items": ["sample_raw"]}` の形であり、`body(..)?['Items']` で読めることを 2026-07-24 の実環境実行で確認済みです（この参照が正しくないと `varFinalViewFields` が空になり `status` が `Created` にならないため、`Created` が返った事実そのものが応答形状の証拠になります）。

---

## 6. 一行表示に関する要件（§23）

「一行で表示する」とは**既定ビューに表示するデータ列が `sample_raw` の1列だけ**であることを意味します。

- `sample_raw` の内容自体を一行テキスト型には**変更していません**。
- `sample_raw` は HTML とハイパーリンクを格納できる**複数行の拡張リッチテキスト列のまま**です（`Type="Note"` / `RichTextMode="FullHtml"`）。

---

## 7. 最終的な列構成の検証（§25）

`Compose_Final_Validation_Code` が次を順に確認し、最初に該当したエラーコードを返します。空文字なら `varStatus = 'Created'` です。

| 順 | 条件 | エラーコード |
|---|---|---|
| 1 | アイテム件数が 0 でない | `ERR_LIST_NOT_EMPTY` |
| 2 | `sample_raw` が作成・検証されていない | `ERR_SAMPLERAW_MISSING` |
| 3 | 列削除に失敗したものがある | `ERR_FIELD_DELETE_FAILED` |
| 4 | 既定ビューIDが空 | `ERR_DEFAULT_VIEW_NOT_FOUND` |
| 5 | 既定ビューのデータ列が1件でない | `ERR_VIEW_FIELDS_NOT_ONLY_SAMPLERAW` |
| 6 | その1件が `sample_raw` でない | `ERR_VIEW_FIELDS_NOT_ONLY_SAMPLERAW` |

### 許容される状態（§25）

- 削除不能なシステム列が内部的に残っている
- SharePoint の UI 操作要素がビュー上に表示される
- 削除不能列がリスト設定画面に存在する

---

関連: [url_parsing_spec.md](url_parsing_spec.md) / [safety_mechanisms.md](safety_mechanisms.md) / [json_schema.md](json_schema.md) / [../../../handbook/knowledge/sharepoint_rest_list_provisioning.md](../../../handbook/knowledge/sharepoint_rest_list_provisioning.md)
