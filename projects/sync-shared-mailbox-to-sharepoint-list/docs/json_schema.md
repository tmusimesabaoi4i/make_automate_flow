# 結果JSON・status・エラーコード一覧

フローの最後（`Scope_Finalize` の `Compose_Flow_Output`）に出力される結果の仕様。
実行履歴でこの1アクションを見れば、何が起きたか判断できるように設計している。

## 1. 出力の形

```json
{
  "success": true,
  "status": "Created",
  "resultObject": { ... },
  "resultJson": "{...}"
}
```

| キー | 型 | 内容 |
|---|---|---|
| `success` | boolean | 全体として成功したか |
| `status` | string | `Created` / `Existing` / `Error` |
| `resultObject` | object | 結果本体（下記） |
| `resultJson` | string | `resultObject` を文字列化したもの（後続フローへの受け渡し用） |

## 2. `resultObject`

```json
{
  "success": true,
  "status": "Created",
  "message": "リストを新規作成し、メールを同期しました。",
  "flowName": "SyncSharedMailboxToSharePointList",
  "completedAt": "2026-08-03T12:34:56.7890000Z",

  "siteUrl": "https://{tenant}.sharepoint.com/sites/{siteName}",
  "siteId": "{webId}",
  "listName": "メール台帳",
  "listCreated": true,
  "listId": "{listId}",
  "listUrl": "https://{tenant}.sharepoint.com/sites/{siteName}/Lists/メール台帳",

  "mailbox": "shared-mailbox@{tenant}.example.com",
  "requestedCount": 20,
  "fetchedCount": 17,

  "createdCount": 15,
  "updatedCount": 2,
  "duplicateCount": 0,
  "failedCount": 0,
  "truncatedCount": 0,

  "duplicates": [],
  "itemErrors": [],
  "truncatedItems": [],
  "schemaWarnings": [],
  "missingFields": [],
  "incompatibleFields": []
}
```

エラー時は上記に加えて `error` が入る。

```json
{
  "success": false,
  "status": "Error",
  "error": {
    "code": "ERR_SCHEMA_INCOMPATIBLE",
    "message": "同名リストは存在しますが、必要な列が不足しているか型が互換ではありません。リストは変更していません。",
    "stage": "VerifySchema",
    "details": ["ERR_SCHEMA_INCOMPATIBLE: missing=[\"BodyPlainText\"] incompatible=[]"]
  }
}
```

### 件数フィールドの読み方

| フィールド | 意味 |
|---|---|
| `requestedCount` | トリガーで指定した件数 |
| `fetchedCount` | 実際に処理対象となったメールの件数 |
| `createdCount` | 新規登録したアイテム数 |
| `updatedCount` | 既存アイテムを更新した数 |
| `duplicateCount` | 同じメッセージIDのアイテムが2件以上あり、**書き込みを見送った**数 |
| `failedCount` | 件単位で失敗した数 |
| `truncatedCount` | 本文が列上限を超えて切り詰められた数 |

`requestedCount > fetchedCount` は「メールがその件数だけ無かった」ことを意味する（異常ではない）。
`createdCount + updatedCount + duplicateCount + failedCount` が `fetchedCount` に一致しない場合は、
実行履歴で `Foreach_Email` の反復を確認する。

## 3. `status` 一覧

| status | success | 意味 |
|---|---|---|
| `Created` | true | リストを新規作成し、メールを同期した |
| `Existing` | true | 既存リストへメールを同期した（リスト自体は変更していない） |
| `Error` | false | どこかで停止した。`error.code` / `error.stage` を見る |

## 4. `stage` 一覧（`error.stage`）

失敗した位置を示す。スコープの先頭で設定される。

| stage | スコープ | 何をしていたか |
|---|---|---|
| `Initialize` | （変数初期化） | 変数の初期化中 |
| `ValidateInput` | `Scope_Validate_Input` | 入力検証とURL正規化 |
| `CheckList` | `Scope_Check_List` | サイト疎通と同名リストの確認 |
| `CreateList` | `Scope_Create_List` | リストの新規作成 |
| `InitListSchema` | `Scope_Init_List_Schema` | 列の作成と表示名変更 |
| `ConfigureView` | `Scope_Configure_View` | 既定ビューの列と並び順 |
| `VerifySchema` | `Scope_Verify_Schema` | 必要な列が揃っているかの確認 |
| `GetEmails` | `Scope_Get_Emails` | 共有メールボックスからの取得 |
| `SyncItems` | `Scope_Sync_Items` | メール1件ずつの登録／更新 |
| `CreateResult` | `Scope_Create_Result` | 結果の確定 |

## 5. エラーコード一覧（`error.code`）

### 入力検証（SharePoint・Outlook へ一切アクセスしていない段階）

| コード | 原因 | 対処 |
|---|---|---|
| `ERR_URL_EMPTY` | URLが空（空白のみを含む） | サイトURLを入力する |
| `ERR_URL_NOT_HTTPS` | `https://` で始まっていない | `https://` から入力する |
| `ERR_URL_NOT_SHAREPOINT` | ホスト名が `.sharepoint.com` で終わらない | SharePoint Online のURLを入力する |
| `ERR_URL_MALFORMED` | URLの形式が不正（`@` を含む・セグメント不足） | ブラウザのアドレスバーからコピーし直す |
| `ERR_LISTNAME_EMPTY` | リスト名が空（前後の空白を除くと空） | リスト名を入力する |
| `ERR_LISTNAME_TOO_LONG` | リスト名が255文字超 | 短くする |
| `ERR_LISTNAME_INVALID_CHARS` | `" # % * : < > ? / \ \| { } ~ &` または制御文字を含む | 使用できない文字を除く |
| `ERR_LISTNAME_INVALID_PERIOD` | リスト名の先頭または末尾がピリオド | ピリオドを除く |
| `ERR_LISTNAME_RESERVED` | SharePointの予約名（`forms` / `_catalogs` 等） | 別の名前にする |
| `ERR_MAILBOX_EMPTY` | 共有メールボックスのアドレスが空 | アドレスを入力する |
| `ERR_MAILBOX_INVALID` | メールアドレスの形式でない | `name@domain.tld` の形式で入力する |
| `ERR_COUNT_INVALID` | 取得件数が0以下・小数・数値以外 | 1以上の整数を入力する |
| `ERR_COUNT_TOO_LARGE` | 取得件数が101以上 | 100以下にする（上限の理由は README §9） |

### リスト操作

| コード | 原因 | 対処 |
|---|---|---|
| `ERR_LIST_AMBIGUOUS` | 同名リストが複数見つかった | SharePoint側でリスト名を整理する |
| `ERR_LIST_NOT_GENERIC` | 同名リストが非表示リストまたはシステムリストだった | 別のリスト名にする |
| `ERR_LIST_CREATE_FAILED` | リスト作成に失敗し、同名リストも存在しなかった | 権限とリスト名を確認する |
| `ERR_SCHEMA_INCOMPATIBLE` | 既存リストに必要な列が無い／型が違う | `missingFields` / `incompatibleFields` を確認して列を追加するか、別のリスト名にする |

### 実行時（ハンドラが HTTPステータスから判定）

| コード | 契機 | 対処 |
|---|---|---|
| `ERR_PERMISSION_DENIED` | 401 / 403 | 接続を作り直す。サイトの編集権限と共有メールボックスへのアクセス権を確認する |
| `ERR_SITE_OR_RESOURCE_NOT_FOUND` | 404 | サイトURL・リスト・メールボックスの実在を確認する |
| `ERR_BAD_REQUEST` | 400 | リスト名・アドレス・件数を確認する |
| `ERR_THROTTLED` | 429 | 待ってから件数を減らして再実行する |
| `ERR_UNEXPECTED_FAILURE` | 上記以外 | 実行履歴で失敗したアクションを確認する |

## 6. 件単位のエラー（`itemErrors[]`）

フロー全体は継続し、失敗したメールだけを記録する。

```json
{"messageId": "<...>", "code": "ERR_ITEM_CREATE_FAILED", "httpStatusCode": "409"}
```

| コード | 意味 |
|---|---|
| `ERR_ITEM_MESSAGE_ID_UNUSABLE` | メッセージIDが空、または255文字超（`MessageId` 列に入らない） |
| `ERR_BODY_CONVERSION_FAILED` | 本文のプレーンテキスト変換に失敗した（**HTMLはそのまま登録していない**） |
| `ERR_ITEM_SEARCH_FAILED` | 既存アイテムの検索に失敗した（**一致0件と誤認せず、書き込みを見送っている**） |
| `ERR_ITEM_CREATE_FAILED` | 新規作成に失敗し、再検索でも見つからなかった |
| `ERR_ITEM_UPDATE_FAILED` | 既存アイテムの更新に失敗した |

## 7. 重複異常（`duplicates[]`）

同じメッセージIDのアイテムが2件以上あった場合。**書き込みは行わない**（作成も更新もしない）。

```json
{"messageId": "<...>", "count": 2, "itemIds": [{"Id": 12}, {"Id": 34}]}
```

`MessageId` 列に一意制約がかかっていれば本来発生しない。
発生した場合は、リストを手動で調べて重複アイテムを整理する。
一意制約が適用されなかったときは `schemaWarnings` にその旨が入る。

## 8. 切り詰め（`truncatedItems[]`）

```json
{"messageId": "<...>", "originalLength": 80000, "storedLength": "63999"}
```

本文が複数行テキスト列の上限を超えたため切り詰めた記録。**黙って切り捨てていない**証跡。

## 9. スキーマ警告（`schemaWarnings[]`）

処理は継続するが知らせておくべき事項。

- `MessageId 列に一意制約が適用されませんでした。…`
- `同時実行により別の実行がリストを作成済みでした。既存リストとして処理します。`
- `作成は失敗しましたが同名リストが存在したため、既存リストとして処理します。`
- `既定ビューが特定できなかったため、ビューの列と並び順を設定できませんでした。`

## 10. 後続処理での参照例

```text
成功判定          : outputs('Compose_Flow_Output')?['success']
リストURL         : outputs('Compose_Flow_Output')?['resultObject']?['listUrl']
新規登録件数      : outputs('Compose_Flow_Output')?['resultObject']?['createdCount']
エラーコード      : outputs('Compose_Flow_Output')?['resultObject']?['error']?['code']
```

`Compose_Flow_Output` は Compose のため封筒を持たない。`outputs(...)` を直接参照してよい
（コネクタアクションの場合は `body(...)` を使う。[handbook/rules/05](../../../handbook/rules/05_sharepoint_and_teams_patterns.md)）。
