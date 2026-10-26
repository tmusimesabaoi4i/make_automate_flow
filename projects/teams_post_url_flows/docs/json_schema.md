# JSON出力仕様

Flow1 / Flow2 が `varResultObject`（Object型）と `varResultJson`（String型）に格納するJSONの構造です。

- `varResultObject` … 構造化されたオブジェクト。後続処理で `variables('varResultObject')?['identifiers']?['teamId']` のように直接参照できます。
- `varResultJson` … 上記を `@string(variables('varResultObject'))` で文字列化したもの。HTTP応答本文やファイル保存にそのまま使えます。

両フローとも `Scope_Finalize` の `Compose_Flow_Output` で、実行履歴から結果を確認できるようにしています。

---

## 1. 値が取得できない項目の扱い

**取得できない項目は捏造しません。** 次の規則で埋めます。

| 状況 | 値 |
|---|---|
| 文字列項目が取得できない | `""`（空文字。`coalesce(…, '')`） |
| 配列項目が取得できない | `[]`（空配列。`coalesce(…, json('[]'))`） |
| オブジェクト全体が取得できない | `{}`（`coalesce(…, json('{}'))`） |

### `from.email` が常に空文字である理由

Microsoft Graph の `chatMessage.from.user` が返すのは `id` / `displayName` / `userIdentityType` の3つで、**メールアドレスは含まれません**。指示書§6.4の構造に `email` フィールドがあるためキー自体は残していますが、値の捏造を避けて常に `""` を格納します。メールアドレスが必要な場合は、`userId` を使って別途 Graph の `/users/{id}` を呼ぶ設計追加が必要です（本フローには含めていません）。

### `raw` について

コネクタ応答（Graphの生JSON）をそのまま保持します。正規化で情報が欠落しないようにするためのもので、正規化フィールドに無い項目（`policyViolation`、`eventDetail`、`channelIdentity` など）もここから取り出せます。

---

## 2. Flow1 の成功時JSON

```json
{
  "success": true,
  "flowName": "Flow1_GetTeamsChannelPostFromUrl",
  "sourceUrl": "https://teams.microsoft.com/l/message/19%3A...%40thread.tacv2/1706000000000?...",
  "retrievedAt": "2026-07-24T10:00:00.0000000Z",
  "identifiers": {
    "tenantId": "",
    "teamId": "",
    "channelId": "19:...@thread.tacv2",
    "urlMessageId": "",
    "parentMessageId": "",
    "targetMessageId": ""
  },
  "message": {
    "id": "",
    "replyToId": "",
    "etag": "",
    "messageType": "message",
    "createdDateTime": "",
    "lastModifiedDateTime": "",
    "subject": "",
    "summary": "",
    "importance": "normal",
    "from": { "displayName": "", "userId": "", "email": "" },
    "body": { "contentType": "html", "content": "<div>…</div>" },
    "webUrl": "",
    "attachments": [],
    "mentions": [],
    "reactions": []
  },
  "raw": {}
}
```

| フィールド | 由来 |
|---|---|
| `success` | 常に `true`（失敗時は §4 の形式になる） |
| `sourceUrl` | `varInputUrl`（trim済みの入力URL） |
| `retrievedAt` | `utcNow()`（UTC） |
| `identifiers.*` | URL解析結果（`url_parsing_spec.md`） |
| `identifiers.channelId` | **URLデコード済み**の値（`19:...@thread.tacv2`） |
| `message.*` | `body('Get_Parent_Message')` の各フィールド |
| `message.body.contentType` | Graphの値（通常 `html` または `text`）。HTML本文はそのまま保持 |
| `message.attachments/mentions/reactions` | Graphの配列をそのまま。無い場合は `[]` |
| `raw` | Graph応答の全体 |

---

## 3. Flow2 の成功時JSON

```json
{
  "success": true,
  "flowName": "Flow2_GetAllTeamsChannelPostRepliesFromUrl",
  "sourceUrl": "",
  "retrievedAt": "2026-07-24T10:00:00.0000000Z",
  "identifiers": {
    "tenantId": "", "teamId": "", "channelId": "",
    "urlMessageId": "", "parentMessageId": "", "targetMessageId": ""
  },
  "parentMessage": {
    "id": "",
    "createdDateTime": "",
    "from": { "displayName": "", "userId": "", "email": "" },
    "body": { "contentType": "", "content": "" },
    "webUrl": ""
  },
  "replyCount": 0,
  "replies": [
    {
      "id": "",
      "replyToId": "",
      "etag": "",
      "messageType": "",
      "createdDateTime": "",
      "lastModifiedDateTime": "",
      "from": { "displayName": "", "userId": "", "email": "" },
      "body": { "contentType": "", "content": "" },
      "webUrl": "",
      "attachments": [],
      "mentions": [],
      "reactions": [],
      "raw": {}
    }
  ]
}
```

- `replyCount` は `@length(variables('varReplies'))`。**実際に `varReplies` へ格納された件数**から算出します（Graphの申告値ではありません）。
- 返信が0件なら `replyCount: 0` / `replies: []` になります。
- `replies[]` の並び順は **Graphが返した順序のまま**です（`connector_requirements.md` §6 参照）。時系列に並べたい場合は利用側で `createdDateTime` によりソートしてください。
- 各返信の `raw` に、その返信のGraph応答オブジェクトをそのまま保持します。
- 指示書§7.6の構造に `etag` / `messageType` を追加しています（Graphが返す情報を落とさないため）。

---

## 4. エラー時JSON（両フロー共通）

```json
{
  "success": false,
  "flowName": "Flow1_GetTeamsChannelPostFromUrl",
  "sourceUrl": "",
  "retrievedAt": "2026-07-24T10:00:00.0000000Z",
  "error": {
    "code": "ERR_GROUPID_NOT_FOUND",
    "message": "URLのクエリに groupId が見つかりません。…",
    "stage": "ParseUrl",
    "details": ["ERR_GROUPID_NOT_FOUND: URLのクエリに groupId が見つかりません。…"]
  },
  "identifiers": {
    "tenantId": "", "teamId": "", "channelId": "",
    "urlMessageId": "", "parentMessageId": "", "targetMessageId": ""
  }
}
```

`error.stage` は失敗した段階を示し、`Initialize` / `ParseUrl` / `GetTeamsData` / `CreateResult` のいずれかです。

Flow2 のエラー時JSONには、`Scope_ErrorHandler` を経由した場合のみ追加フィールドが付きます。

```json
  "partialReplyCount": 37
```

ページング途中で失敗したときに、**何件まで取得できていたか**を示します（`varRepliesRaw` の件数）。

### エラー生成の2経路

| 経路 | いつ | 生成アクション | 特徴 |
|---|---|---|---|
| 想定内エラー | URL検証NG・投稿が削除済み | `Create_Error_Result_Object`（`Scope_CreateResult`） | Graph呼び出しをスキップして正常終了。`error.code` は検証時に確定した値 |
| 想定外エラー | Graph呼び出しの失敗・タイムアウト等 | `Handle_Error`（`Scope_ErrorHandler`） | HTTPステータスからコードを推定。`details` に診断情報を追加 |

`Scope_ErrorHandler` 経由の場合、`error.details` には次が追加されます。

```json
["stage=GetTeamsData", "httpStatusCode=403", "collectedReplies=0", "nextLinkAtFailure=https://…"]
```

（`collectedReplies` / `nextLinkAtFailure` は Flow2 のみ）

---

## 5. エラーコード一覧

| コード | 意味 | 発生段階 |
|---|---|---|
| `ERR_URL_EMPTY` | URLが空 | ParseUrl |
| `ERR_NOT_TEAMS_URL` | Teams のURLではない | ParseUrl |
| `ERR_NOT_CHANNEL_MESSAGE_URL` | チャネル投稿URLではない（`/l/message/` が無い） | ParseUrl |
| `ERR_CHAT_URL_NOT_SUPPORTED` | チャット（1対1・グループ・会議）のURL | ParseUrl |
| `ERR_GROUPID_NOT_FOUND` | `groupId` が取得できない | ParseUrl |
| `ERR_CHANNELID_NOT_FOUND` | チャネルIDが取得できない | ParseUrl |
| `ERR_MESSAGEID_NOT_FOUND` | メッセージIDが取得できない | ParseUrl |
| `ERR_MESSAGE_DELETED` | 投稿が削除済み（`deletedDateTime` あり） | GetTeamsData |
| `ERR_PERMISSION_DENIED` | 権限不足・認証失敗（HTTP 401 / 403） | GetTeamsData |
| `ERR_MESSAGE_NOT_FOUND` | 投稿が存在しない／チーム・チャネルにアクセスできない（HTTP 404） | GetTeamsData |
| `ERR_GRAPH_BAD_REQUEST` | Graph要求が不正（HTTP 400） | GetTeamsData |
| `ERR_UNEXPECTED_FAILURE` | 上記以外の想定外エラー（ページング途中の失敗を含む） | 任意 |

指示書§8が求める区別との対応:

| 指示書の要求 | 対応するコード |
|---|---|
| URLが空 | `ERR_URL_EMPTY` |
| Teams URLではない | `ERR_NOT_TEAMS_URL` |
| チャネル投稿URLではない | `ERR_NOT_CHANNEL_MESSAGE_URL` / `ERR_CHAT_URL_NOT_SUPPORTED` |
| `groupId` が取得できない | `ERR_GROUPID_NOT_FOUND` |
| `channelId` が取得できない | `ERR_CHANNELID_NOT_FOUND` |
| `messageId` が取得できない | `ERR_MESSAGEID_NOT_FOUND` |
| Teamsコネクタの権限不足 | `ERR_PERMISSION_DENIED` |
| 投稿が削除済み | `ERR_MESSAGE_DELETED`（`deletedDateTime` で判定） |
| 投稿が存在しない | `ERR_MESSAGE_NOT_FOUND`（HTTP 404） |
| チーム・チャネルへアクセスできない | `ERR_PERMISSION_DENIED` / `ERR_MESSAGE_NOT_FOUND` |
| 返信の取得に失敗 | `ERR_UNEXPECTED_FAILURE` ほか（`stage=GetTeamsData`） |
| ページネーション途中で失敗 | `ERR_UNEXPECTED_FAILURE` + `partialReplyCount` |

> **要実環境確認**: 削除済み投稿にGraphが `deletedDateTime` 付きで応答するのか 404 を返すのかは、テナント・削除方法（ソフト削除／完全削除）によって異なる可能性があります。本フローは両方に対応できるよう、`deletedDateTime` チェックと 404 判定の両方を実装しています。実際にどちらの経路を通るかは実環境で確認してください。
>
> **要実環境確認**: 失敗したコネクタアクションの `outputs(...)?['statusCode']` が実際に取得できるかは未確認です。取得できない場合は `coalesce(…, 0)` により `'0'` となり、`ERR_UNEXPECTED_FAILURE` に落ちます（`error.details` の `httpStatusCode=0` で判別できます）。

---

## 6. 後続処理での参照例

```text
成功判定           @variables('varResultObject')?['success']
チームID           @variables('varResultObject')?['identifiers']?['teamId']
本文（Flow1）      @variables('varResultObject')?['message']?['body']?['content']
返信件数（Flow2）  @variables('varResultObject')?['replyCount']
返信の配列（Flow2）@variables('varResultObject')?['replies']
エラーコード       @variables('varResultObject')?['error']?['code']
JSON文字列         @variables('varResultJson')
```

---

関連: [url_parsing_spec.md](url_parsing_spec.md) / [usage.md](usage.md) / [troubleshooting.md](troubleshooting.md)
