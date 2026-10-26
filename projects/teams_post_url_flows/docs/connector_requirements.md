# コネクタ・権限要件

Flow1 / Flow2 / Flow3 が使用するコネクタ、必要な権限、取得件数の上限、および「なぜGraphを使うのか」の説明です。

---

## 1. 結論（要点）

| 項目 | 内容 |
|---|---|
| 使用コネクタ | **Microsoft Teams（`shared_teams`）1本のみ** |
| 使用アクション | **Send a Microsoft Graph HTTP request**（Microsoft Graph HTTP 要求を送信します / operationId=`HttpRequest`） |
| プレミアムコネクタ | **不要** |
| Azure AD アプリ登録 | **不要** |
| 管理者同意 | **不要** |
| HTTPコネクタ（プレミアム） | **不使用** |
| Azure Functions / 独自API / 外部サーバー / Python実行環境 | **不使用** |
| 接続の数 | 各フロー1接続（インポート時に選択または新規作成） |

両フローとも SharePoint も Content Conversion も使いません。ZIP内の `apisMap.json` / `connectionsMap.json` / `manifest.json` はいずれも `shared_teams` 1件だけを参照します。

---

## 2. なぜ標準Teamsコネクタの「ネイティブ投稿取得アクション」だけで済ませないのか

指示書§5の優先順位（① Teams標準コネクタ → ② Power Automate標準機能 → ③ やむを得ない場合のみGraph）に対する回答です。

**採用したアクションは①の Teams標準コネクタそのものです。** 「Send a Microsoft Graph HTTP request」は Microsoft Teams 標準コネクタに含まれるアクションであり、Graphを呼ぶからといってプレミアムになるわけではありません。したがって「①を飛ばして③にした」わけではなく、**①の中でGraph到達手段を持つアクションを選んだ**という位置づけです。

そのうえで、ネイティブの投稿取得アクション（`GetMessageDetails` / `ListRepliesToMessage` など）を採らなかった理由は次の2点です。

1. **URLから得た任意のメッセージIDで単一投稿を取得するネイティブアクションについて、本リポジトリ内に実在確認の証跡がありません。** `references/extracted/`（実働サンプル3本）を全走査した結果、Teamsコネクタで実際に使われている operationId は `HttpRequest` のみでした。実在が不確かな operationId を推測で定義に書くことは、指示書§14および `CLAUDE.md` 不変則6で禁止されています。
2. **`ListRepliesToMessage` は `$top` の最大が50で、Power Automate上での全件ページングを保証できません。** 指示書§7.5の「全返信」要件（先頭N件で打ち切らない）を満たせません。

Graph HTTP要求であれば `@odata.nextLink` を `Do until` で追跡でき、取得漏れなく全返信を取得できます。この方式は `handbook/knowledge/connector_action_notes.md` および `handbook/rules/05_sharepoint_and_teams_patterns.md` に、実働サンプルでの動作実績とともに【事実】として記録されています。

> なお `handbook/knowledge/connector_action_notes.md` には `GetMessagesFromChannel` / `ListRepliesToMessage` が「参考・未使用」として整理されています（出典は公式のTeamsコネクタリファレンス）。存在自体は公式資料で確認されていますが、本リポジトリ内に定義としての使用実績が無いため、今回は採用していません。

---

## 3. 呼び出すGraphエンドポイント

いずれも読み取り（GET）のみです。書き込み・削除は一切行いません。

| 用途 | メソッドとURL |
|---|---|
| 親投稿の取得（Flow1 / Flow2 / Flow3） | `GET https://graph.microsoft.com/v1.0/teams/{teamId}/channels/{channelId}/messages/{messageId}` |
| 返信の取得（Flow2・1ページ目） | `GET https://graph.microsoft.com/v1.0/teams/{teamId}/channels/{channelId}/messages/{messageId}/replies?$top=50` |
| 返信の取得（Flow2・2ページ目以降） | `GET {@odata.nextLink}`（Graphが返す完全URLをそのまま使用） |
| チャネルメンバー一覧（Flow3・表示名とメールの補完） | `GET https://graph.microsoft.com/v1.0/teams/{teamId}/channels/{channelId}/members`（2ページ目以降は `@odata.nextLink`）。リアクションが1件以上あるときだけ呼ぶ |

フロー内では次の式でURLを組み立てています。

```text
@concat('https://graph.microsoft.com/v1.0/teams/', variables('varTeamId'),
        '/channels/', uriComponent(variables('varChannelId')),
        '/messages/', variables('varTargetMessageId'))
```

**チャネルIDは `uriComponent()` で必ずURLエンコードします。** チャネルIDは `19:xxxxx@thread.tacv2` の形式で `:` と `@` を含むためです（`handbook/rules/05` に【事実】として記録）。`teamId` はGUIDなのでエンコード不要です。

`@odata.nextLink` はGraphが返す完全URLなので、そのまま次リクエストの `Uri` に渡します（再エンコード不要）。

### 応答の参照方法

`body('<アクション名>')` は **Graph応答JSONそのもの**です（`{statusCode, headers, body}` の封筒ではありません）。一方 `outputs('<アクション名>')` は封筒を返すため、HTTPステータスコードは `outputs('<アクション名>')?['statusCode']` で参照しています。

- 返信一覧: `body('Get_All_Replies')?['value']`
- 次ページ: `body('Get_All_Replies')?['@odata.nextLink']`

---

## 4. 認証方法

- パッケージの `connectionReferences` は **Invoker形式**（`source: "Invoker"`）で、アクションの `authentication` は次の標準参照式です。

  ```text
  @json(decodeBase64(triggerOutputs().headers['X-MS-APIM-Tokens']))['$ConnectionKey']
  ```

  これは参照式であって秘密情報ではありません。**ZIPには認証情報（トークン・サインイン情報）は一切含まれていません。**
- 実際の認証は、**インポート時に選択（または新規作成）したTeams接続の所有者としての委任アクセス**で行われます。フローを実行するアカウントの権限でGraphが呼ばれます。
- 接続GUID・テナントID・作成者情報は匿名化済みです（`manifest.json` の `creator` は `"N/A"`、`sourceEnvironment` は空）。

---

## 5. 必要な権限

| 対象 | 必要な権限 | 確認状況 |
|---|---|---|
| 対象のTeamsチーム | **メンバーであること**（またはチャネルメッセージの読み取り権限を持つこと） | **要実環境確認** |
| チャネルメンバー一覧（Flow3） | Graph の委任スコープ `ChannelMember.Read.All` 相当が Teams コネクタの既存同意で満たされること。満たされない場合は 403 になり、Flow3 は表示名・メールを空にして警告付きで続行する（フロー自体は失敗しない） | **要実環境確認** |
| Power Automate環境 | フローのインポート・作成権限 | **要実環境確認** |
| Teamsコネクタ接続 | 上記チームにアクセスできるアカウントで作成された接続 | **要実環境確認** |

**要実環境確認である理由**: Graphのチャネルメッセージ読み取りに実際に要求される委任スコープ（`ChannelMessage.Read.All` 等）が、Teamsコネクタの既存同意の範囲で満たされるかは、テナントの設定（条件付きアクセス・APIアクセス許可のカスタマイズ）に依存します。本リポジトリには、同一方式（`shared_teams` + `HttpRequest` によるチャネルメッセージ取得）が実働サンプルで動作した記録がありますが、**本フローを実環境で実行して確認した記録はありません。**

追加のAzure ADアプリ登録・管理者同意を前提にした設計にはしていません。もし403が返る場合は、接続アカウントが対象チームのメンバーであるかをまず確認してください（`troubleshooting.md`）。

---

## 6. 取得件数の上限（Flow2）

「全返信」を取得するため、**先頭N件で打ち切る処理は入れていません**。`$top=50` は1ページあたりの取得件数であり、取得の打ち切り位置ではありません。

| 制約 | 値 | 備考 |
|---|---|---|
| 1ページの取得件数 | 50件（`$top=50`） | Graphが返す件数。上限はGraph側の仕様に従う |
| ページ追跡 | `@odata.nextLink` が空になるまで | `Do until` で追跡。取得漏れなし |
| `Do until` の反復上限 | **5,000回** | `limit.count`。理論上 5,000ページ × 50件 = 250,000件 |
| `Do until` のタイムアウト | **1時間**（`PT1H`） | `limit.timeout` |
| フロー実行時間の上限 | 目安 **30分** | Power Automate側の制約。実務上はこちらが先に効く |

したがって**実務上の上限は「30分以内に取得しきれる件数」**です。通常のチャネル投稿の返信数（数件〜数百件）であれば余裕があります。

- Power Automateの「ページネーションを有効にする」設定は、コネクタ側がページングに対応しているアクションで使うものです。本フローは `@odata.nextLink` を `Do until` で明示的に追跡する方式のため、この設定に依存しません（設定不要）。
- **要実環境確認**: 返信の並び順（Graphが返す順序）は保証されていません。本フローは取得順のまま `varReplies` に格納します。時系列で並べたい場合は、受け取ったJSONを利用側で `createdDateTime` によりソートしてください。

---

## 7. 対応するURL / 対応しないURL

### 対応する

- Teamsチーム内の**チャネル投稿**のURL（`https://teams.microsoft.com/l/message/…` / `https://teams.cloud.microsoft/l/message/…`）
- 上記の**返信**のURL（`parentMessageId` から親投稿へ解決）

### 対応しない（明示的にエラーを返す）

| 種別 | 判定 | 返すエラーコード |
|---|---|---|
| 1対1チャット・グループチャット | チャネルIDに `unq.gbl.spaces` | `ERR_CHAT_URL_NOT_SUPPORTED` |
| `/l/chat/` 形式のチャットURL | パスに `/l/message/` が無い | `ERR_NOT_CHANNEL_MESSAGE_URL` |
| 会議チャット | 上記いずれかで捕捉 | 同上 |
| Viva Engage の投稿 | Teamsホストでない | `ERR_NOT_TEAMS_URL` |
| Teams以外のMicrosoft 365 URL | Teamsホストでない | `ERR_NOT_TEAMS_URL` |

### チャネル種別（要実環境確認）

| 種別 | 想定 | 確認状況 |
|---|---|---|
| 標準チャネル | 動作する想定 | **要実環境確認** |
| プライベートチャネル | アクセス権があれば動作する想定 | **要実環境確認** |
| 共有チャネル | **動作しない可能性がある** | **要実環境確認** |

**共有チャネルの懸念**: 共有チャネルはホストチームと共有先チームの双方から参照でき、URLの `groupId` が投稿の実体があるチームと一致しない場合があります。その場合 `GET /teams/{groupId}/channels/{channelId}/messages/{id}` が 404 になる可能性があります。実環境で確認し、対応できない場合は `troubleshooting.md` の対処（投稿元チームでリンクを取り直す）を試してください。

---

## 8. DLP（データ損失防止）ポリシー

Teamsコネクタは一般に「業務データ」グループに分類されます。本フローは Teams 1コネクタのみを使うため、**複数コネクタをまたぐDLP違反は原理的に発生しません**。ただしテナントのDLPポリシーでTeamsコネクタ自体がブロックされている場合はインポート・実行できません（**要実環境確認**）。

---

関連: [url_parsing_spec.md](url_parsing_spec.md) / [installation.md](installation.md) / [troubleshooting.md](troubleshooting.md)
