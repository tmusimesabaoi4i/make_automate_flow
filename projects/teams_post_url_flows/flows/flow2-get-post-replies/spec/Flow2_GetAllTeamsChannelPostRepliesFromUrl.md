# Flow2_GetAllTeamsChannelPostRepliesFromUrl — フロー定義の説明

Teams投稿URLを解析し、その投稿に対する**すべての返信**を取得して、Array型変数に蓄積したうえで Object型変数とJSON文字列型変数に格納する手動トリガーのクラウドフローです。

| 項目 | 値 |
|---|---|
| フロー名（論理名） | `Flow2_GetAllTeamsChannelPostRepliesFromUrl` |
| 表示名 | Flow2 Teams投稿URLから全返信を取得 |
| トリガー | 手動でフローをトリガーします（`manual` / `Request` / `kind: Button`） |
| 使用コネクタ | Microsoft Teams（`shared_teams`）1本のみ・プレミアム不要 |
| アクション総数 | 81 |
| 生成元 | `../source/build_flow2.py` |
| 検証 | `../source/validate_flow2.py`（エラー0 / 警告0） |
| パッケージ | `../release/Flow2_GetAllTeamsChannelPostRepliesFromUrl_20260724190952.zip` |

Flow1 とは**独立したフロー**です。単独でインポート・実行できます。URL解析部分（`Scope_ParseUrl`）は Flow1 と**完全に同一のアクション名・式**です。

**`definition.json` は生成物です。** 修正は必ず `../source/build_flow2.py` を編集してください。

---

## 1. トリガー

Flow1 と同じです。

| 入力名 | 表示名 | 型 | 必須 |
|---|---|---|---|
| `TeamsPostUrl` | Teams投稿URL | string | **はい** |

---

## 2. 変数（すべてトップレベルで初期化）

### 指示書§7.3の必須変数

| 変数名 | 型 | 初期値 | 用途 |
|---|---|---|---|
| `varInputUrl` | String | `@trim(coalesce(triggerBody()?['TeamsPostUrl'], ''))` | trim済みの入力URL |
| `varTenantId` | String | `''` | `tenantId` |
| `varTeamId` | String | `''` | `groupId`（＝チームID） |
| `varChannelId` | String | `''` | デコード済みチャネルID |
| `varUrlMessageId` | String | `''` | URLパス上のメッセージID |
| `varParentMessageId` | String | `''` | クエリの `parentMessageId` |
| `varTargetMessageId` | String | `''` | Graphに渡す最終的な投稿ID |
| **`varReplies`** | **Array** | `@json('[]')` | **正規化済みの返信を蓄積する配列** |
| `varResultObject` | Object | `@json('{}')` | 最終結果（構造化） |
| `varResultJson` | String | `''` | 最終結果（JSON文字列） |
| `varErrorMessages` | Array | `@json('[]')` | エラーの説明 |

### 返信取得の作業用・制御用に追加した変数

| 変数名 | 型 | 初期値 | 用途 |
|---|---|---|---|
| `varRepliesRaw` | Array | `@json('[]')` | Graph応答の生の返信を蓄積（ページング中） |
| `varReplyNextLink` | String | `''` | 次ページのURL。空になったらループ終了 |
| `varIsValid` | Boolean | `true` | 解析・取得が正常かどうか |
| `varStage` | String | `'Initialize'` | 処理段階（`error.stage`） |
| `varErrorCode` / `varErrorMessage` | String | `''` | エラーコードと説明 |
| `varLastStatusCode` | String | `'0'` | 直近のGraph応答のHTTPステータス |

`varRepliesRaw`（生データ）と `varReplies`（正規化済み）を分けているのは、ページング中は素早く蓄積し、正規化は取得完了後に一括で行うためです。ページング失敗時に「何件まで取れていたか」を `varRepliesRaw` から報告できる利点もあります。

---

## 3. 構成（Try / Catch / Finally）

Flow1 と同じ骨格です。

```text
[トップレベル] Initialize_InputUrl … Initialize_LastStatusCode   (18変数)
Scope_ParseUrl        runAfter: Initialize_LastStatusCode [Succeeded]
Scope_GetTeamsData    runAfter: Scope_ParseUrl            [Succeeded]
Scope_CreateResult    runAfter: Scope_GetTeamsData        [Succeeded]
Scope_ErrorHandler    runAfter: Scope_CreateResult        [Failed, Skipped, TimedOut]   ← Catch
Scope_Finalize        runAfter: Scope_ErrorHandler        [Succeeded, Failed, Skipped, TimedOut]  ← Finally
```

`runAfter` を最終Scope1本だけに張る理由、ハンドラが変数のみを参照する理由は [`Flow1の説明`](../../flow1-get-channel-post/spec/Flow1_GetTeamsChannelPostFromUrl.md) §3 と同じです。

---

## 4. Scope_ParseUrl（URL解析）

**Flow1 と完全に同一**です。アクション名・式ともに同じで、`tests/run_url_parse_tests.py` は両フローの `definition.json` に対して同じ20ケースを実行し、いずれも合格しています。

詳細は [`../../../docs/url_parsing_spec.md`](../../../docs/url_parsing_spec.md) を参照してください。

返信のURLを入力した場合は `parentMessageId` から親投稿が特定されるため、**返信のURLからでも「親投稿＋その全返信」が取得できます**（指示書§3の意図どおり）。

---

## 5. Scope_GetTeamsData（親投稿の取得 → 全返信の取得 → 正規化）

```text
Set_Stage_GetTeamsData                    varStage = 'GetTeamsData'
Condition_Is_Valid                        If varIsValid == true
  Get_Parent_Message                      Teams / HttpRequest / GET（親投稿）
  Set_LastStatusCode                      runAfter [Succeeded, Failed]
  Condition_Message_Deleted               runAfter [Succeeded]
    Set_ErrorCode_Message_Deleted / Set_ErrorMessage_Message_Deleted
    Set_IsValid_Message_Deleted / Append_Message_Deleted_Error
  Condition_Parent_Available              If varIsValid == true（親が取れた場合のみ返信を取る）
    Set_ReplyNextLink_First               1ページ目のURL
    Do_Until_Replies_Paging               @empty(variables('varReplyNextLink')) まで
      Get_All_Replies                     Teams / HttpRequest / GET（1ページ）
      Set_Replies_Status_Code             runAfter [Succeeded, Failed]
      Process_Retrieved_Replies           Foreach（並列オフ）
        Append_Raw_Reply                  varRepliesRaw へ item() を1件ずつ
      Set_ReplyNextLink                   @odata.nextLink（無ければ空文字）
    Apply_To_Each_Raw_Reply               Foreach（並列オフ）
      Compose_Normalized_Reply            1件分のオブジェクトを組み立て
      Append_Normalized_Reply             varReplies へ追加
```

### 5-1. 全返信の取得（ページング）

**1ページ目のURL**（`Set_ReplyNextLink_First`）:

```text
@concat('https://graph.microsoft.com/v1.0/teams/', variables('varTeamId'),
        '/channels/', uriComponent(variables('varChannelId')),
        '/messages/', variables('varTargetMessageId'), '/replies?$top=50')
```

**2ページ目以降** は `Get_All_Replies` の応答に含まれる `@odata.nextLink`（Graphが返す完全URL）をそのまま `Uri` に渡します（再エンコード不要）。

```text
Set_ReplyNextLink の値
@coalesce(body('Get_All_Replies')?['@odata.nextLink'], '')
```

**`$top=50` は「1ページあたりの件数」であって、取得の打ち切り位置ではありません。** `Do_Until_Replies_Paging` は `varReplyNextLink` が空文字になるまで反復するため、返信は全件取得されます。定義中に「先頭N件で打ち切る」処理はありません。

| 制約 | 値 |
|---|---|
| `Do until` の反復上限 | 5,000回（`limit.count`） |
| `Do until` のタイムアウト | 1時間（`limit.timeout: PT1H`） |
| フロー実行時間の上限 | 目安30分（Power Automate側。実務上はこちらが先に効く） |

Power Automateの「ページネーションを有効にする」設定には依存しません（`@odata.nextLink` を明示的に追跡する方式のため、設定不要）。

> **要実環境確認**: 返信が50件を超えるスレッドで実際に全件取得できるかは未検証です。確認方法は [`../../../docs/installation.md`](../../../docs/installation.md) §10、位置づけは [`../../../tests/test_cases.md`](../../../tests/test_cases.md) ケース8を参照してください。

### 5-2. 自己参照を使わない蓄積（指示書§7.4）

**指示書が禁止する自己参照は一切使っていません。**

```text
禁止（使っていない）: SetVariable  varReplies = union(variables('varReplies'), 新要素)
                     → WorkflowRunActionInputsInvalidProperty / Self reference is not supported
```

代わりに、取得ページの `value` 配列を `Process_Retrieved_Replies`（Apply to each）で回し、`Append_Raw_Reply`（配列変数に追加）で **1件ずつ** `@item()` を追加します。

**ページ配列をそのまま Append しない**のが要点です。50件の配列を1要素として追加すると `[[…50件…]]` と入れ子になります（`handbook/rules/03`）。

検証結果: SetVariable 24件中、**自己参照0件**（`../validation/validate_result.txt`）。

### 5-3. 並列処理の無効化（指示書§7.4）

配列変数へ追加する Apply to each は、追加順序の乱れと競合を避けるため**並列オフ**にしています。

```json
"runtimeConfiguration": { "concurrency": { "repetitions": 1 } }
```

`Process_Retrieved_Replies` と `Apply_To_Each_Raw_Reply` の両方に設定済みで、`validate_flow2.py` が全 Foreach について機械的に確認しています。

### 5-4. 正規化

`Apply_To_Each_Raw_Reply` の中で `Compose_Normalized_Reply` が1件分のオブジェクトを組み立て、`Append_Normalized_Reply` が `varReplies` に追加します。オブジェクトは「自身に足す」概念が無いため、Compose で新規構築してから配列に Append する方式です（`handbook/rules/03`）。

各返信の `raw` に元のGraphオブジェクトをそのまま保持し、正規化で情報を失わないようにしています。

---

## 6. Scope_CreateResult（結果の組み立て）

```text
Set_Stage_CreateResult
Condition_Build_Result              If varIsValid == true
  [true]  Create_Result_Object      → Set_ResultObject
  [false] Create_Error_Result_Object → Set_ResultObject_Error
Serialize_Result_To_Json            varResultJson = @string(variables('varResultObject'))
```

構造は指示書§7.6のとおりです（[`../../../docs/json_schema.md`](../../../docs/json_schema.md) §3）。

**`replyCount` は `@length(variables('varReplies'))`** で、実際に `varReplies` へ格納された件数から算出します（Graphの申告値ではありません。指示書§7.6の要求どおり）。

返信0件の場合は `replyCount: 0` / `replies: []` になります。

---

## 7. Scope_ErrorHandler（Catch）

Flow1 と同じ構成に加え、返信取得の進捗を残します。

```text
Compose_Handler_Error_Details
@union(variables('varErrorMessages'),
       createArray(concat('stage=', variables('varStage')),
                   concat('httpStatusCode=', variables('varLastStatusCode')),
                   concat('collectedReplies=', string(length(variables('varRepliesRaw')))),
                   concat('nextLinkAtFailure=', variables('varReplyNextLink'))))
```

エラー時のJSONには `partialReplyCount`（`@length(variables('varRepliesRaw'))`）が追加され、**ページング途中で失敗した場合に何件まで取得できていたか**が分かります（指示書§8の「ページネーション途中で失敗」への対応）。

参照しているのはすべて変数です。`Do until` の中のアクションを参照していないため、ループが1回も回らずに失敗した場合でもハンドラは壊れません。

---

## 8. Scope_Finalize（Finally）

```json
{ "success": …, "replyCount": …, "resultObject": …, "resultJson": "…" }
```

成否に関わらず実行され、実行履歴から最終結果と返信件数を1箇所で確認できます。

---

## 9. アクション命名

全81アクションが役割の分かる名前を持ちます。ループ外の初期化用とループ内更新用は名前を分けています（`handbook/rules/01` の `_First` 規約）。

```text
Set_ReplyNextLink_First   … ループ外（1ページ目のURLを設定）
Set_ReplyNextLink         … ループ内（毎回nextLinkで更新）
```

同名アクションの重複はフロー全体で0件です（検証済み）。実行順の全アクション一覧は [`../validation/action_outline.txt`](../validation/action_outline.txt) を参照してください。

### ネスト深さ

最深は `Scope_GetTeamsData > Condition_Is_Valid > Condition_Parent_Available > Do_Until_Replies_Paging > Process_Retrieved_Replies > Append_Raw_Reply` の6段で、上限8段に収まっています（`handbook/rules/01`）。

---

## 10. 既知の制約

- Flow1 と同じURL制約（チャネル投稿のみ。チャット類は対象外）。
- 返信の並び順は Graph が返す順序のままです。時系列に並べたい場合は利用側で `createdDateTime` によりソートしてください（**要実環境確認**）。
- 返信件数が非常に多い場合、フロー実行時間（目安30分）に収まらない可能性があります。
- 共有チャネルでは404になる可能性があります（**要実環境確認**）。
- **実環境でのインポート・実行には成功しています（2026-07-24）。** ただし**「返信51件以上での全件取得」は依然として未確認**であり、最重要の残課題です。1ページ（50件）に収まるスレッドでは、ページングが機能していなくても正常に見えてしまいます（[`../../../tests/validation_report.md`](../../../tests/validation_report.md) §5-3・§7）。

---

関連: [`Flow1`](../../flow1-get-channel-post/spec/Flow1_GetTeamsChannelPostFromUrl.md) / [`../../../docs/url_parsing_spec.md`](../../../docs/url_parsing_spec.md) / [`../../../docs/json_schema.md`](../../../docs/json_schema.md) / [`../../../docs/connector_requirements.md`](../../../docs/connector_requirements.md)
