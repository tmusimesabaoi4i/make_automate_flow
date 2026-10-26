# 利用手順書

インポート済みの Flow1 / Flow2 を実際に使う手順です。インポート自体は [installation.md](installation.md) を参照してください。

---

## 1. 2つのフローの使い分け

| | Flow1 | Flow2 |
|---|---|---|
| フロー名 | `Flow1_GetTeamsChannelPostFromUrl` | `Flow2_GetAllTeamsChannelPostRepliesFromUrl` |
| 表示名 | Flow1 Teams投稿URLから投稿を取得 | Flow2 Teams投稿URLから全返信を取得 |
| 取得するもの | 対象の**親投稿1件** | 対象の**親投稿＋その全返信** |
| 出力の主フィールド | `message` | `parentMessage` / `replies` / `replyCount` |
| 実行時間の目安 | 数秒 | 返信件数に比例（1ページ50件） |

どちらも独立して実行できます。投稿本文だけが欲しいなら Flow1、スレッド全体が欲しいなら Flow2 を使ってください。

---

## 2. 入力

両フローとも入力は1つだけです。

| 項目 | 値 |
|---|---|
| 入力名 | `TeamsPostUrl` |
| 表示名 | **Teams投稿URL** |
| 型 | テキスト（文字列） |
| 必須 | はい |

### URLの取得方法

1. Teamsで対象のチャネル投稿にマウスを合わせ、右上の「…」（その他のオプション）をクリックします。
2. 「リンクをコピー」を選びます。
3. コピーされたURLをそのまま貼り付けます。

**注意点**

- **コピーした値をそのまま貼り付けてください。** 手で編集したり大文字化したりすると解析に失敗することがあります（`url_parsing_spec.md` §5 既知の制限）。
- 前後に空白が入っていても自動で除去されます。
- **返信のURLを貼っても構いません。** その場合はURLの `parentMessageId` から親投稿を特定し、親投稿（Flow2 なら親投稿＋その全返信）を取得します。
- **チャットのURLは使えません。** 1対1チャット・グループチャット・会議チャットは対象外で、`ERR_CHAT_URL_NOT_SUPPORTED` または `ERR_NOT_CHANNEL_MESSAGE_URL` を返します。

---

## 3. 実行方法

### 3-1. Power Automate 画面から実行する

1. 「マイフロー」でフローを開きます。
2. 「実行」（またはデザイナーの「テスト」→「手動」）をクリックします。
3. 「Teams投稿URL」欄にURLを貼り付けます。
4. 「実行」（フローの実行）をクリックします。

### 3-2. モバイルアプリ／ボタンから実行する

手動トリガー（ボタン）のフローなので、Power Automate モバイルアプリの「ボタン」タブからも実行できます。URLの入力欄が表示されます。

---

## 4. 結果の確認方法

### 4-1. 実行履歴で見る

1. フローの詳細画面の「28日間の実行履歴」から該当の実行をクリックします。
2. 一番下の **`Scope_Finalize` → `Compose_Flow_Output`** を開き、「出力」タブを見ます。

`Compose_Flow_Output` の出力は次の形です。

```json
{
  "success": true,
  "resultObject": { ...構造化された結果... },
  "resultJson": "{\"success\":true,...}"
}
```

Flow2 では `replyCount` も含まれます。

個別に見たい場合は次のアクションの出力を確認してください。

| 見たいもの | アクション |
|---|---|
| URL解析の結果（識別子） | `Set_ChannelId` / `Set_TeamId` / `Determine_TargetMessageId` |
| 解析エラーの有無 | `Validate_ParsedIdentifiers`（空なら正常） |
| Graphの生応答 | `Get_Parent_Message` / `Get_All_Replies` |
| 最終オブジェクト | `Set_ResultObject` |
| JSON文字列 | `Serialize_Result_To_Json` |

### 4-2. 変数の値

| 変数 | 型 | 内容 |
|---|---|---|
| `varResultObject` | Object | 構造化された結果（`json_schema.md`） |
| `varResultJson` | String | 上記のJSON文字列 |
| `varReplies` | Array | 正規化済みの返信配列（Flow2のみ） |
| `varErrorMessages` | Array | 発生したエラーの説明（正常時は空） |

---

## 5. 出力の主な項目

詳細は [json_schema.md](json_schema.md) を参照してください。よく使う項目だけ抜き出すと次のとおりです。

### Flow1

```text
成功したか       resultObject.success
投稿の本文       resultObject.message.body.content        （HTML形式のことが多い）
本文の形式       resultObject.message.body.contentType    （html / text）
投稿者名         resultObject.message.from.displayName
投稿日時         resultObject.message.createdDateTime     （UTC）
投稿へのリンク   resultObject.message.webUrl
添付ファイル     resultObject.message.attachments[]
メンション       resultObject.message.mentions[]
Graphの生データ  resultObject.raw
```

### Flow2

```text
成功したか       resultObject.success
返信の件数       resultObject.replyCount
返信の配列       resultObject.replies[]
  各返信の本文   resultObject.replies[i].body.content
  各返信の投稿者 resultObject.replies[i].from.displayName
  各返信の日時   resultObject.replies[i].createdDateTime
親投稿の本文     resultObject.parentMessage.body.content
```

> **本文はHTMLで返ることが多い点に注意してください。** `<div>` や `<at>`（メンション）を含む文字列がそのまま入ります。プレーンテキストが必要な場合は、後続で Content Conversion コネクタの「HTML をテキストに変換」を使うか、利用側で変換してください。本フローは情報を落とさないため変換していません。
>
> **日時はすべてUTCです。** JSTで表示したい場合は `convertFromUtc(…, 'Tokyo Standard Time')` を後続で使ってください。

---

## 6. 後続フローで使う

本フローは結果を変数に格納するところまでを担当します。他のフローから呼び出したい場合や、結果を別の場所に保存したい場合は、次のいずれかを検討してください。

- **同じフローにアクションを追加する**: `Scope_Finalize` の後ろに、SharePointへの保存・メール送信・Teams投稿などを追加します。`variables('varResultJson')` をそのまま渡せます。
- **HTTP応答を返す**: トリガーを「HTTP要求の受信時」に変更し、末尾に「応答」アクションを追加して `varResultJson` を本文にします（プレミアムライセンスが必要です）。
- **子フローとして呼ぶ**: 手動トリガーのままでは他フローから呼べません。呼び出したい場合はトリガーを変更する改修が必要です。

改修する場合は `flows/*/source/build_flow*.py` を編集して再生成してください（`definition.json` を直接編集しないでください）。

---

## 7. エラーが出たとき

フローは**エラーでも最後まで実行され**、結果はエラー形式のJSONとして `varResultObject` / `varResultJson` に格納されます。実行履歴が赤くならない場合もあるため、必ず `Compose_Flow_Output` の `success` を確認してください。

```json
{
  "success": false,
  "error": { "code": "ERR_GROUPID_NOT_FOUND", "message": "…", "stage": "ParseUrl", "details": [...] }
}
```

`error.code` ごとの対処は [troubleshooting.md](troubleshooting.md) を参照してください。

---

関連: [installation.md](installation.md) / [json_schema.md](json_schema.md) / [troubleshooting.md](troubleshooting.md)
