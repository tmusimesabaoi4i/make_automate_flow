# Flow1_GetTeamsChannelPostFromUrl — フロー定義の説明

Teams投稿URLを解析し、そのURLが示すチャネル投稿の内容を取得して、Object型変数とJSON文字列型変数に格納する手動トリガーのクラウドフローです。

| 項目 | 値 |
|---|---|
| フロー名（論理名） | `Flow1_GetTeamsChannelPostFromUrl` |
| 表示名 | Flow1 Teams投稿URLから投稿を取得 |
| トリガー | 手動でフローをトリガーします（`manual` / `Request` / `kind: Button`） |
| 使用コネクタ | Microsoft Teams（`shared_teams`）1本のみ・プレミアム不要 |
| アクション総数 | 67 |
| 生成元 | `../source/build_flow1.py` |
| 検証 | `../source/validate_flow1.py`（エラー0 / 警告0） |
| パッケージ | `../release/Flow1_GetTeamsChannelPostFromUrl_20260724190952.zip` |

**`definition.json` は生成物です。** 修正は必ず `../source/build_flow1.py` を編集し、再生成 → 検証 → 再パッケージしてください（`CLAUDE.md` 不変則1）。

---

## 1. トリガー

| 入力名 | 表示名 | 型 | 必須 |
|---|---|---|---|
| `TeamsPostUrl` | Teams投稿URL | string | **はい**（`required` に登録） |

---

## 2. 変数（すべてトップレベルで初期化）

`InitializeVariable` は Scope 内に置けないため、フロー冒頭に直列で並べています（`handbook/rules/01`【事実】）。指示書§8の `Scope_Initialize` はこの連鎖で代替しています。

### 指示書§6.3の必須変数

| 変数名 | 型 | 初期値 | 用途 |
|---|---|---|---|
| `varInputUrl` | String | `@trim(coalesce(triggerBody()?['TeamsPostUrl'], ''))` | 前後の空白を除いた入力URL |
| `varTenantId` | String | `''` | URLから取得した `tenantId` |
| `varTeamId` | String | `''` | URLの `groupId`（＝チームID） |
| `varChannelId` | String | `''` | URLデコード済みのチャネルID |
| `varUrlMessageId` | String | `''` | URLパス上のメッセージID |
| `varParentMessageId` | String | `''` | URLクエリの `parentMessageId` |
| `varTargetMessageId` | String | `''` | Graphに渡す最終的な投稿ID |
| `varResultObject` | Object | `@json('{}')` | 最終結果（構造化） |
| `varResultJson` | String | `''` | 最終結果（JSON文字列） |
| `varErrorMessages` | Array | `@json('[]')` | 発生したエラーの説明 |

### 制御・診断用に追加した変数

| 変数名 | 型 | 初期値 | 用途 |
|---|---|---|---|
| `varIsValid` | Boolean | `true` | 解析・取得が正常かどうか。Graph呼び出しと結果組み立ての分岐に使う |
| `varStage` | String | `'Initialize'` | 現在の処理段階。エラー時の `error.stage` になる |
| `varErrorCode` | String | `''` | 確定したエラーコード |
| `varErrorMessage` | String | `''` | エラーの説明文 |
| `varLastStatusCode` | String | `'0'` | 直近のGraph応答のHTTPステータス。**失敗時もハンドラから安全に読めるようにするため変数に退避する** |

---

## 3. 構成（Try / Catch / Finally）

```text
[トップレベル] Initialize_InputUrl … Initialize_LastStatusCode   (15変数)
Scope_ParseUrl        runAfter: Initialize_LastStatusCode [Succeeded]
Scope_GetTeamsData    runAfter: Scope_ParseUrl            [Succeeded]
Scope_CreateResult    runAfter: Scope_GetTeamsData        [Succeeded]
Scope_ErrorHandler    runAfter: Scope_CreateResult        [Failed, Skipped, TimedOut]   ← Catch
Scope_Finalize        runAfter: Scope_ErrorHandler        [Succeeded, Failed, Skipped, TimedOut]  ← Finally
```

### なぜ `Scope_ErrorHandler` の `runAfter` を最終Scope1本だけにするのか

`runAfter` に複数のアクションを列挙すると **AND判定**になります。仮に `Scope_ParseUrl` と `Scope_GetTeamsData` の両方を `[Failed, Skipped, TimedOut]` で列挙すると、「ParseUrl は成功、GetTeamsData は失敗」というよくあるケースで `Scope_ParseUrl` が `Succeeded` のため条件を満たさず、**ハンドラが発火しません**。

Scopeを直列に連鎖させておけば、途中で失敗したとき後続のScopeはすべて `Skipped` になります。したがって**最終Scope（`Scope_CreateResult`）の `Skipped` / `Failed` / `TimedOut` を見るだけで、どの段階の失敗も確実に捕捉**できます。

### ハンドラの参照安全

`Scope_ErrorHandler` 内の式は**変数だけ**を参照します。Scope内のComposeの `outputs()` をハンドラで参照すると、そのCompose自体が実行されなかった場合にハンドラが自壊します（`handbook/rules/08`「失敗ハンドラの参照安全」）。

HTTPステータスをハンドラで使うために、`Set_LastStatusCode` を `runAfter: {Get_Parent_Message: [Succeeded, Failed]}` で配置しています。**Graph呼び出しが失敗しても必ず実行される**ため、ハンドラは `variables('varLastStatusCode')` を安全に読めます。

---

## 4. Scope_ParseUrl（URL解析）

アクション構成（実行順）:

```text
Set_Stage_ParseUrl                  varStage = 'ParseUrl'
Compose_Url_Without_Fragment        # を切り捨て
Compose_Url_Path_Raw                ? より前
Compose_Url_Path_Part               末尾スラッシュを除去
Compose_Url_Query_Part              ? より後ろ
Compose_Query_Normalized            前後に & を付与
Compose_Message_Path_Tail           /l/message/ 以降
Parse_ChannelId_From_Path           デコードしたチャネルID
Parse_MessageId_From_Path           パス上の messageId
Parse_TenantId_From_Query           tenantId
Parse_TeamId_From_Query             groupId
Parse_ParentMessageId_From_Query    parentMessageId
Set_ChannelId / Set_UrlMessageId / Set_TenantId / Set_TeamId / Set_ParentMessageId
Determine_TargetMessageId           parentMessageId 優先（'0' は値なし扱い）
Validate_ParsedIdentifiers          エラーコードを1つ返す（空なら正常）
Set_ErrorCode_From_Validation / Set_IsValid / Set_ErrorMessage_From_Validation
Condition_Has_Parse_Error           → Append_Parse_Error_Message
```

式の全文と設計根拠は [`../../../docs/url_parsing_spec.md`](../../../docs/url_parsing_spec.md) を参照してください。要点のみ:

- **固定文字数・固定位置に依存しません。** すべて区切り文字による分割です。
- **クエリは順不同で解析できます。** 前後に `&` を付けた正規化クエリを `'&<名前>='` で分割する名前アンカー方式です。これにより `parentMessageId` が `messageId` に部分一致する問題も起きません。
- **チャネルIDは `decodeUriComponent()` で復号します**（`%3A` → `:` / `%40` → `@`）。非エンコードのURLでも無害に素通りします。
- **`substring` による長さ計算を使っていません。** Logic Apps の `if()` は両分岐の引数を先行評価するため、空文字入力で `substring(s, 0, -1)` が実行時エラーになり得ます。`split → take → join` に置き換えています。

---

## 5. Scope_GetTeamsData（投稿の取得）

```text
Set_Stage_GetTeamsData              varStage = 'GetTeamsData'
Condition_Is_Valid                  If varIsValid == true
  Get_Parent_Message                Teams / HttpRequest / GET
  Set_LastStatusCode                runAfter [Succeeded, Failed]
  Condition_Message_Deleted         runAfter [Succeeded]
    Set_ErrorCode_Message_Deleted / Set_ErrorMessage_Message_Deleted
    Set_IsValid_Message_Deleted / Append_Message_Deleted_Error
```

### Get_Parent_Message

| パラメータ | 値 |
|---|---|
| コネクタ | `shared_teams`（Microsoft Teams） |
| operationId | `HttpRequest`（Send a Microsoft Graph HTTP request） |
| Method | `GET` |
| ContentType | `application/json` |
| Uri | 下記 |

```text
@concat('https://graph.microsoft.com/v1.0/teams/', variables('varTeamId'),
        '/channels/', uriComponent(variables('varChannelId')),
        '/messages/', variables('varTargetMessageId'))
```

チャネルIDは `:` と `@` を含むため `uriComponent()` で必ずエンコードします（`handbook/rules/05`【事実】）。`teamId` はGUIDなのでエンコード不要です。

### 削除済み判定

`Condition_Message_Deleted` は `@coalesce(body('Get_Parent_Message')?['deletedDateTime'], '')` が空でない場合に真となり、`ERR_MESSAGE_DELETED` を設定して `varIsValid` を false にします。結果は §6 のエラー経路で組み立てられます。

> **要実環境確認**: 削除済み投稿がこの経路を通るか、Graphが404を返すかは未確認です。404の場合は `Scope_ErrorHandler` が `ERR_MESSAGE_NOT_FOUND` を返します（両方に対応済み）。

---

## 6. Scope_CreateResult（結果の組み立て）

```text
Set_Stage_CreateResult              varStage = 'CreateResult'
Condition_Build_Result              If varIsValid == true
  [true]  Create_Result_Object      → Set_ResultObject
  [false] Create_Error_Result_Object → Set_ResultObject_Error
Serialize_Result_To_Json            varResultJson = @string(variables('varResultObject'))
```

**true側だけが `body('Get_Parent_Message')` を参照します。** false側は変数のみを参照するため、Graph呼び出しがスキップされていても式が壊れません。これが「解析エラーでもフローが完走し、エラー形式のJSONが得られる」ことの担保です。

`Create_Result_Object` が組み立てる構造は指示書§6.4のとおりです（[`../../../docs/json_schema.md`](../../../docs/json_schema.md) §2）。

- 取得できない項目は `coalesce(…, '')` / `coalesce(…, json('[]'))` で埋め、**捏造しません**。
- `from.email` は Graph が返さないため常に空文字です。
- `raw` に `@coalesce(body('Get_Parent_Message'), json('{}'))` を丸ごと保持し、正規化で情報を失わないようにしています。

JSON文字列化は指示書§6.5のとおり `@string(variables('varResultObject'))` です。

---

## 7. Scope_ErrorHandler（Catch）

```text
Compose_Handler_Error_Code          varErrorCode 優先。無ければHTTPステータスから推定
Compose_Handler_Error_Message       同上（日本語の説明文）
Compose_Handler_Error_Details       varErrorMessages + stage + httpStatusCode
Handle_Error                        エラー形式のオブジェクトを組み立て
Set_ResultObject_Handler            varResultObject へ
Serialize_Handler_Result_To_Json    varResultJson へ
```

HTTPステータス → エラーコードの対応:

| ステータス | コード |
|---|---|
| 401 / 403 | `ERR_PERMISSION_DENIED` |
| 404 | `ERR_MESSAGE_NOT_FOUND` |
| 400 | `ERR_GRAPH_BAD_REQUEST` |
| その他 | `ERR_UNEXPECTED_FAILURE` |

**エラー時も `varResultObject` / `varResultJson` に結果を格納します**（指示書§8の要求）。

---

## 8. Scope_Finalize（Finally）

`Compose_Flow_Output` が成否に関わらず実行され、実行履歴から最終結果を1箇所で確認できるようにします。

```json
{ "success": …, "resultObject": …, "resultJson": "…" }
```

---

## 9. アクション命名

`Compose` / `Compose 2` / `変数を設定する 3` のような役割不明の名前は使っていません。全67アクションが役割の分かる名前を持ち、検証スクリプトで**フロー全体での一意性**も確認しています。

初期化用とループ内更新用は名前を分ける規約（`handbook/rules/01`）に従っています（本フローにループはありませんが、Flow2 では `Set_ReplyNextLink_First` / `Set_ReplyNextLink` として分けています）。

実行順の全アクション一覧は [`../validation/action_outline.txt`](../validation/action_outline.txt) を参照してください。

---

## 10. 既知の制約

- 対応するのは Teams チャネル投稿のURLのみです。チャット（1対1・グループ・会議）は対象外で、明示的にエラーを返します。
- `contains()` は大文字小文字を区別するため、URLを手入力で大文字化すると `ERR_NOT_TEAMS_URL` になります。「リンクをコピー」の値をそのまま使ってください。
- 共有チャネルでは、URLの `groupId` が投稿の実体があるチームと一致せず404になる可能性があります（**要実環境確認**）。
- **実環境でのインポート・実行には成功しています（2026-07-24）。** ただし添付・メンションを含む投稿や異常系（存在しない／削除済み／権限なし）の実挙動は未確認です。[`../../../tests/validation_report.md`](../../../tests/validation_report.md) §5・§7 を参照してください。

---

関連: [`../../../docs/url_parsing_spec.md`](../../../docs/url_parsing_spec.md) / [`../../../docs/json_schema.md`](../../../docs/json_schema.md) / [`../../../docs/connector_requirements.md`](../../../docs/connector_requirements.md) / [`Flow2`](../../flow2-get-post-replies/spec/Flow2_GetAllTeamsChannelPostRepliesFromUrl.md)
