# 出力JSON仕様

フローは結果を `varResultObject`（Object型）と `varResultJson`（String型）に格納します。

- `varResultObject` … 構造化オブジェクト。後続処理で `variables('varResultObject')?['list']?['id']` のように参照できます。
- `varResultJson` … `@string(variables('varResultObject'))` で文字列化したもの。

結果の組み立ては `Scope_Finalize` の1箇所に集約しています。**すべての状態（ロールバックの実施有無を含む）が確定した後**に作るため、`rollbackPerformed` も正しく反映されます。参照するのは変数だけなので、途中のアクションがスキップされていても式が壊れません。

実行履歴では `Scope_Finalize` → `Compose_Flow_Output` で確認できます。

```json
{ "success": true, "status": "Created", "resultObject": { … }, "resultJson": "{…}" }
```

---

## 1. status の一覧

| status | success | created | 意味 |
|---|---|---|---|
| `Created` | true | true | 新規作成し、初期化まで成功した |
| `AlreadyExists` | true | false | 同名リストが既にあったため何もしなかった（**正常終了**） |
| `AlreadyExistsOrConflict` | false | false | 作成時に競合エラー。既存リストには一切触れていない |
| `InitializationFailed` | false | true | 作成はできたが初期化に失敗した（ロールバックを試みる） |
| `Failed` | false | false | 入力検証・サイト疎通などで失敗した（作成前） |

---

## 2. 新規作成成功（§29.1）

```json
{
  "success": true,
  "status": "Created",
  "created": true,
  "message": "リストを新規作成し、初期化しました。",
  "site": {
    "id": "",
    "title": "",
    "url": ""
  },
  "list": {
    "id": "",
    "title": "",
    "rootFolder": "",
    "itemCount": 0
  },
  "initialization": {
    "deletedFields": [],
    "skippedSystemFields": [],
    "sampleRawCreated": true,
    "sampleRawInternalName": "sample_raw",
    "sampleRawType": "EnhancedRichText",
    "defaultViewId": "",
    "defaultViewTitle": "",
    "defaultViewFields": ["sample_raw"]
  }
}
```

| フィールド | 由来 |
|---|---|
| `site.*` | `_api/web` の応答（`varSiteId` / `varSiteTitle` / `varVerifiedUrl`） |
| `list.id` | 作成応答の `d.Id`（**この値だけがすべての書き込み対象を決める**） |
| `list.rootFolder` | 作成したリストIDで取得した `RootFolder.ServerRelativeUrl` |
| `list.itemCount` | `lists(guid'..')/ItemCount` の値 |
| `initialization.deletedFields[]` | 削除に成功した列（`id` / `internalName` / `title` / `typeAsString`） |
| `initialization.skippedSystemFields[]` | `CanBeDeleted=false` で削除しなかった列＋その理由 |
| `initialization.defaultViewFields` | 設定後に再取得した既定ビューの表示列 |

`sampleRawType` は `"EnhancedRichText"` という**呼称**です（SharePoint の `TypeAsString` は `Note`、リッチテキスト設定は `SchemaXml` の `RichTextMode="FullHtml"` に現れます）。実際の検証は §4 の5項目で行っています。

### skippedSystemFields の記載例

```json
{
  "internalName": "Title",
  "title": "タイトル",
  "typeAsString": "Text",
  "reason": "CanBeDeleted=false のため削除しない（既定ビューからは除外済み。フォームからの非表示化は未実施）"
}
```

**「非表示化できた」とは書きません。** 実施していない処理を実施したとは報告しない方針です（[list_operations_spec.md](list_operations_spec.md) §3.7）。

---

## 3. 同名リストあり（§29.2）

```json
{
  "success": true,
  "status": "AlreadyExists",
  "created": false,
  "message": "同名のリストが既に存在するため、作成処理を実行しませんでした。",
  "siteUrl": "",
  "listName": "",
  "existingList": {
    "id": "",
    "title": "",
    "hidden": false,
    "serverRelativeUrl": ""
  }
}
```

`existingList` は**存在確認（`Get_All_Lists`）で取得済みの情報**から組み立てます。既存リストに対して追加の GET すら発行しません。

`hidden` が `true` なら、非表示リストと名前が衝突していたことを意味します。

---

## 4. エラー（§29.3）

```json
{
  "success": false,
  "status": "Failed",
  "created": false,
  "message": "",
  "stage": "",
  "siteUrl": "",
  "listName": "",
  "createdListId": "",
  "rollbackPerformed": false,
  "errors": []
}
```

| フィールド | 内容 |
|---|---|
| `status` | `Failed` / `AlreadyExistsOrConflict` / `InitializationFailed` |
| `stage` | 失敗した段階。§5 参照 |
| `createdListId` | 作成まで到達していた場合のリストID（ロールバックできなかったときの手掛かり） |
| `rollbackPerformed` | 今回作成したリストを削除できたか |
| `errors[]` | 発生したエラーの説明＋診断情報 |

`errors[]` には、エラーハンドラを経由した場合に診断情報が追加されます。

```json
[
  "ERR_LIST_NAME_INVALID_CHARS: リスト名にSharePointで使用できない文字…",
  "stage=CreateList",
  "httpStatusCode=403",
  "createdInThisRun=false",
  "createdListId="
]
```

---

## 5. stage の一覧

`varStage` は各スコープの先頭で設定され、失敗時にどこまで進んでいたかを示します。

| stage | 意味 |
|---|---|
| `Initialize` | 変数初期化（ここで失敗することはほぼない） |
| `ParseAndValidateInput` | URL解析・入力検証 |
| `VerifySharePointSite` | サイトへの疎通・参照権限の確認 |
| `CheckExistingList` | 同名リストの確認 |
| `CreateList` | リストの新規作成 |
| `InitializeList` | 空確認・添付無効化・Title必須解除 |
| `DeleteDeletableFields` | 削除可能な列の削除 |
| `CreateSampleRawField` | `sample_raw` の作成・検証 |
| `ConfigureDefaultView` | 既定ビューの再構築・検証 |
| `ValidateResult` | 最終判定 |
| `HandleAlreadyExists` | 同名リストありの結果組み立て |

---

## 6. エラーコード一覧

### 入力検証（作成前・既存リストへの影響なし）

| コード | 意味 |
|---|---|
| `ERR_URL_EMPTY` | SharePoint URL が空 |
| `ERR_NOT_HTTPS` | `https://` で始まっていない |
| `ERR_NOT_SHAREPOINT_HOST` | ホスト名が `.sharepoint.com` で終わらない |
| `ERR_SITE_URL_NOT_EXTRACTED` | サイトURLを抽出できない |
| `ERR_LIST_NAME_EMPTY` | リスト名が空（trim 後） |
| `ERR_LIST_NAME_TOO_LONG` | 255文字を超える |
| `ERR_LIST_NAME_INVALID_CHARS` | 禁止文字または制御文字を含む |
| `ERR_LIST_NAME_INVALID_PERIOD` | 先頭または末尾がピリオド |
| `ERR_LIST_NAME_RESERVED` | 予約名に該当 |

### サイト・作成（HTTPステータス由来）

| コード | 意味 |
|---|---|
| `ERR_PERMISSION_DENIED` | 401 / 403。認証失敗または権限不足 |
| `ERR_SITE_OR_RESOURCE_NOT_FOUND` | 404。サイトが存在しない、またはURLがサイトURLでない |
| `ERR_BAD_REQUEST` | 400。要求が不正 |
| `ERR_CREATE_CONFLICT` | リスト作成が 2xx 以外。競合または権限不足 |

### 初期化（作成後）

| コード | 意味 |
|---|---|
| `ERR_LIST_NOT_EMPTY` | 作成直後なのにアイテムが存在する |
| `ERR_FIELD_DELETE_FAILED` | 列削除に1件以上失敗した |
| `ERR_SAMPLERAW_VERIFICATION_FAILED` | `sample_raw` の検証に失敗した |
| `ERR_SAMPLERAW_MISSING` | `sample_raw` が作成されていない |
| `ERR_DEFAULT_VIEW_NOT_FOUND` | `DefaultView=true` のビューが見つからない |
| `ERR_VIEW_FIELDS_NOT_ONLY_SAMPLERAW` | 既定ビューのデータ列が `sample_raw` だけになっていない |
| `ERR_UNEXPECTED_FAILURE` | 上記以外の想定外エラー |

指示書§32 の区別との対応:

| 指示書の要求 | 対応 |
|---|---|
| サイトを参照できない | `ERR_PERMISSION_DENIED`（stage=VerifySharePointSite） |
| サイトは参照できるがリストを作成できない | `ERR_CREATE_CONFLICT` ＋ `httpStatusCode=403`（stage=CreateList） |
| リストは作成できるが列を作成できない | stage=CreateSampleRawField のエラー |
| ビューを変更できない | stage=ConfigureDefaultView のエラー |
| リストを削除できないためロールバックできない | `rollbackPerformed: false` ＋ `createdListId` を報告 |

**権限不足を「URL不正」や「同名リスト存在」として扱いません。**

---

## 7. 後続処理での参照例

```text
成功判定         @variables('varResultObject')?['success']
状態             @variables('varResultObject')?['status']
作成したリストID @variables('varResultObject')?['list']?['id']
既定ビューの列   @variables('varResultObject')?['initialization']?['defaultViewFields']
既存リストID     @variables('varResultObject')?['existingList']?['id']
エラーコード     @variables('varResultObject')?['error']?['code']   ← §4 では errors[] に集約
JSON文字列       @variables('varResultJson')
```

> エラー時の形式には `error` オブジェクトではなく、`message` / `stage` / `errors[]` をトップレベルに置いています（指示書§29.3 の構造どおり）。

---

関連: [list_operations_spec.md](list_operations_spec.md) / [safety_mechanisms.md](safety_mechanisms.md) / [troubleshooting.md](troubleshooting.md)
