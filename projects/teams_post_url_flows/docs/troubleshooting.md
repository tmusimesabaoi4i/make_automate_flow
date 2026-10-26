# トラブルシューティング

症状から原因と対処を引くための一覧です。段階（インポート時 / 保存時 / 実行時 / 結果の中身）で分けています。

---

## 1. 結果JSONのエラーコード別の対処

`Compose_Flow_Output` の出力に `"success": false` が出た場合、`error.code` から対処を引いてください。

| コード | 原因 | 対処 |
|---|---|---|
| `ERR_URL_EMPTY` | 「Teams投稿URL」が空のまま実行された | URLを入力して再実行する |
| `ERR_NOT_TEAMS_URL` | `teams.microsoft.com` / `teams.cloud.microsoft` を含まない | Teamsの「リンクをコピー」で取得したURLか確認する。**手入力で大文字化していないか確認する**（判定は大文字小文字を区別します） |
| `ERR_NOT_CHANNEL_MESSAGE_URL` | パスに `/l/message/` が無い | チャネル**投稿**のURLか確認する。チャネル自体のリンク（`/l/channel/`）やチャットのリンク（`/l/chat/`）は対象外 |
| `ERR_CHAT_URL_NOT_SUPPORTED` | チャット（1対1・グループ・会議）のスレッド | 本フローの対象外。チャネル投稿のURLを使う |
| `ERR_GROUPID_NOT_FOUND` | クエリに `groupId` が無い | URLを途中で切っていないか確認する。`?` 以降を含めて全体を貼り付ける |
| `ERR_CHANNELID_NOT_FOUND` | パスからチャネルIDが取れない | `/l/message/` の直後にチャネルIDがあるか確認する |
| `ERR_MESSAGEID_NOT_FOUND` | パスからメッセージIDが取れない | `/l/message/{channelId}/{messageId}` の形式か確認する |
| `ERR_MESSAGE_DELETED` | 投稿が削除済み（`deletedDateTime` あり） | 別の投稿を指定する。削除済み投稿の本文は取得できません |
| `ERR_PERMISSION_DENIED` | HTTP 401 / 403 | §4-1 を参照 |
| `ERR_MESSAGE_NOT_FOUND` | HTTP 404 | §4-2 を参照 |
| `ERR_GRAPH_BAD_REQUEST` | HTTP 400 | §4-3 を参照 |
| `ERR_UNEXPECTED_FAILURE` | 上記以外 | `error.details` の `httpStatusCode` と `stage` を確認する。§4-4 を参照 |

---

## 2. インポート時のエラー

### 「パッケージのインポート (レガシー)」が見つからない

「インポート」ボタンの選択肢を確認してください。テナントのバージョンによって「レガシーのインポート」等の表記になります。「ソリューションのインポート」では本ZIPは取り込めません。

### インポート自体が失敗する / 接続が反映されない

1. ブラウザを再読み込みし、ZIPのアップロードからやり直します。
2. ステップ4で「新規作成として (Create as new)」が選ばれているか確認します。
3. 接続行にチェックマークが付いているか確認します。

### `'@' at position … is not expected` のような式パースエラー

式の中でネストした関数に `@` が付いている場合に出ます（`handbook/knowledge/error_catalog.md`）。**本パッケージは `flows/*/source/validate_flow*.py` の「不正な `@` 位置検査」で0件を確認済み**のため、配布状態では発生しないはずです。デザイナーで手動編集した後に発生した場合は、編集した式から余分な `@` を除いてください。

---

## 3. 保存時のエラー

### `WorkflowRunActionInputsInvalidProperty` / `Self reference is not supported`

「変数を設定する」の値式が自分自身を参照している場合に出ます。**本パッケージは自己参照0件を機械検証済み**です（`validate_result.txt` の「自己参照 0」）。蓄積はすべて `AppendToArrayVariable` で行っています。手動でアクションを追加した場合は、配列の蓄積を `union(variables('自身'), …)` ではなく Apply to each ＋「配列変数に追加」に変えてください。

### `OpenApiOperationParameterValidationFailed`

動的スキーマの必須ボディを持つアクション（SharePointの `PostItem` 等）で出るエラーです。**本フローはTeamsの `HttpRequest` しか使っていない**ため該当しません。発生した場合は追加したアクションを確認してください。

### 変数の重複初期化・アクション名の重複

いずれも機械検証で0件です。手動でアクションを複製した場合、Power Automate はフロー全体でアクション名の一意性を要求する点に注意してください。

---

## 4. 実行時のエラー

### 4-1. `ERR_PERMISSION_DENIED`（HTTP 401 / 403）

**403 の場合**

1. Teams接続を作成したアカウントが、**対象チームのメンバーかどうか**を確認します。メンバーでない場合、チャネルメッセージは読み取れません。
2. プライベートチャネルの場合、そのチャネル自体のメンバーである必要があります。
3. テナントのAPIアクセス許可・条件付きアクセスポリシーでGraphのチャネルメッセージ読み取りが制限されていないか、管理者に確認します（**要実環境確認**）。

**401 の場合**

Teams接続の認証が切れている可能性があります。Power Automate の「接続」画面で該当の接続を開き、「修正」または削除して作り直してください。その後フローの各Teamsアクションで接続を選び直します。

### 4-2. `ERR_MESSAGE_NOT_FOUND`（HTTP 404）

考えられる原因を確度順に:

1. **共有チャネルの投稿である**（**要実環境確認**）。共有チャネルはURLの `groupId` が投稿の実体があるチームと一致しないことがあり、`/teams/{groupId}/channels/{channelId}/messages/{id}` が404になり得ます。対処: 投稿元のチーム（ホストチーム）側でリンクを取り直して試してください。
2. **投稿が完全に削除されている**。ソフト削除なら `ERR_MESSAGE_DELETED` になりますが、完全削除では404になります。
3. **`targetMessageId` が誤っている**。`Determine_TargetMessageId` の出力を確認してください。13桁の数値でない場合はURLの形式が想定外です。
4. **チームまたはチャネルにアクセスできない**。4-1 と同じ確認をしてください。

`Get_Parent_Message` アクションの「入力」タブで、組み立てられた `Uri` の実値を確認するのが最短の切り分けです。

### 4-3. `ERR_GRAPH_BAD_REQUEST`（HTTP 400）

URLから取り出した識別子の形式が不正です。`Get_Parent_Message` の「入力」で `Uri` を確認し、次を点検してください。

- `channels/` の直後が `19%3A…%40thread.tacv2` の形（`uriComponent()` でエンコード済み）になっているか
- `messages/` の直後が13桁の数値になっているか
- `teams/` の直後がGUID形式になっているか

### 4-4. `ERR_UNEXPECTED_FAILURE`

`error.details` を確認してください。

```json
["stage=GetTeamsData", "httpStatusCode=429", "collectedReplies=150", "nextLinkAtFailure=https://…"]
```

| `httpStatusCode` | 意味と対処 |
|---|---|
| `429` | Graphのスロットリング。しばらく待って再実行する |
| `503` / `504` | Graph側の一時障害。再実行する |
| `0` | ステータスコードを取得できなかった（**要実環境確認**の項目）。実行履歴で失敗したアクションの「出力」を直接確認する |

`nextLinkAtFailure` が入っている場合は、返信のページング途中で失敗しています。`collectedReplies` がそこまでの取得件数です。

---

## 5. 結果は返るが中身がおかしい

### `replyCount` が 50 で止まる（Flow2）

ページングが機能していません。実行履歴で確認してください。

1. `Do_Until_Replies_Paging` の反復回数が1回で終わっていないか
2. `Set_ReplyNextLink` の出力が2回目以降も空文字になっていないか
3. `Get_All_Replies` の出力に `@odata.nextLink` が含まれているか

`@odata.nextLink` が返っているのにループが回らない場合は、`Set_ReplyNextLink` の式 `@coalesce(body('Get_All_Replies')?['@odata.nextLink'], '')` が編集されていないか確認してください。

### `replies` が入れ子配列になる（`[[…]]`）

ページ配列をそのまま「配列変数に追加」した場合に起きます。本パッケージは Apply to each（`Process_Retrieved_Replies`）で1件ずつ追加しているため発生しませんが、手動で改修した場合は注意してください。

### 返信の件数が実際と合わない

- **並列実行がオンになっていないか確認してください。** `Process_Retrieved_Replies` / `Apply_To_Each_Raw_Reply` の「設定」で「同時実行制御」がオフ（degree of parallelism = 1）である必要があります。本パッケージは `concurrency.repetitions = 1` を設定済みで、機械検証もしています。
- Graphが返す返信には、システムメッセージ（メンバー追加など）が含まれる場合があります。`messageType` が `message` 以外のものを除きたい場合は利用側でフィルタしてください。

### `from.displayName` が空になる

投稿者がアプリ・ボット・システムの場合、Graphは `from.user` ではなく `from.application` / `from.device` を返します。この場合 `displayName` は空になります。`raw.from` に元の情報が残っているのでそちらを参照してください。

### `from.email` が常に空

**仕様です。** Graph の `chatMessage.from.user` はメールアドレスを返しません（`json_schema.md` §1）。値を捏造しないため空文字にしています。必要な場合は `userId` から別途 Graph の `/users/{id}` を呼ぶ改修が必要です。

### 本文がHTMLタグだらけ

**仕様です。** Graphは `body.contentType: "html"` で本文を返すことが多く、情報を落とさないためそのまま保持しています。プレーンテキストが必要な場合は後続で変換してください（`usage.md` §5）。

### `Scope_ErrorHandler` がスキップされている

**正常です。** 失敗時にのみ実行されるハンドラです。逆に実行されている場合は前段のどこかが失敗しています。

---

## 6. 開発側での再検証

パッケージを作り直したい場合、または改修後に検証したい場合の手順です。

```powershell
cd projects/teams_post_url_flows

# 生成 → 静的検証 → URL解析テスト
python flows/flow1-get-channel-post/source/build_flow1.py
python flows/flow1-get-channel-post/source/validate_flow1.py     # errors 0 / warnings 0 が条件
python flows/flow2-get-post-replies/source/build_flow2.py
python flows/flow2-get-post-replies/source/validate_flow2.py
python tests/run_url_parse_tests.py                              # 40件すべて合格が条件

# アウトライン → ZIP化 → 再展開検査
python ../../tools/gen_outline.py flows/flow1-get-channel-post/source/package/Microsoft.Flow/flows/<GUID>/definition.json flows/flow1-get-channel-post/validation/action_outline.txt
python ../../tools/pack_package.py flows/flow1-get-channel-post/source/package flows/flow1-get-channel-post/release/Flow1_GetTeamsChannelPostFromUrl_<YYYYMMDDHHMMSS>.zip
python flows/flow1-get-channel-post/validation/extract_check.py
```

**`definition.json` を直接編集しないでください。** 生成物です。必ず `source/build_flow*.py` を編集して再生成してください（`CLAUDE.md` 不変則1）。

---

関連: [json_schema.md](json_schema.md) / [url_parsing_spec.md](url_parsing_spec.md) / [connector_requirements.md](connector_requirements.md) / `handbook/knowledge/error_catalog.md`
