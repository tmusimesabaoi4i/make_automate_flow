# Flow3_ListTeamsChannelPostReactorsFromUrl — フロー定義の説明

Teams投稿URLを解析し、そのチャネル投稿に**リアクションした人を一覧化**して、Object型変数とJSON文字列型変数に格納する手動トリガーのクラウドフローです。
表示名とメールアドレスは、チャネルメンバー一覧とユーザーIDで突き合わせて補います。

| 項目 | 値 |
|---|---|
| フロー名（論理名） | `Flow3_ListTeamsChannelPostReactorsFromUrl` |
| 表示名 | Flow3 Teams投稿URLからリアクションした人を一覧化 |
| トリガー | 手動でフローをトリガーします（`manual` / `Request` / `kind: Button`） |
| 使用コネクタ | Microsoft Teams（`shared_teams`）1本のみ・プレミアム不要 |
| アクション総数 | 110 |
| 生成元 | `../source/build_flow3.py`（雛形: `flow1-get-channel-post/source/build_flow1.py`） |
| 検証 | `../source/validate_flow3.py`（エラー0 / 警告0） |
| パッケージ | `../release/Flow3_ListTeamsChannelPostReactorsFromUrl_20261026121818.zip` |
| 実環境 | **未実施**（インポート・保存・実行いずれも要実環境確認） |

**`definition.json` は生成物です。** 修正は必ず `../source/build_flow3.py` を編集し、再生成 → 検証 → 再パッケージしてください（`CLAUDE.md` 不変則1）。

---

## 1. 目的

チャネル投稿（例: 「確認したらリアクションしてください」という連絡）に**誰がリアクションしたか**を、表示名・メールアドレス付きのJSONとして取り出す。

## 2. トリガーと入力

| 入力名 | 表示名 | 型 | 必須 |
|---|---|---|---|
| `TeamsPostUrl` | Teams投稿URL | string | **はい** |

URLは Teams の投稿の「…」→「リンクをコピー」で得たものをそのまま貼り付けます。URL解析は Flow1 と同一の式です（仕様は [docs/url_parsing_spec.md](../../../docs/url_parsing_spec.md)）。

- **対象は親投稿です。** 返信のURLを貼った場合も `parentMessageId` から親投稿へ解決し、親投稿のリアクションを集計します（Flow1 と同じ挙動）。返信へのリアクションは対象外です。

## 3. 出力（JSON）

`varResultObject`（Object）と `varResultJson`（その文字列化）に同じ内容が入ります。実行履歴の `Scope_Finalize` → `Compose_Flow_Output` で確認できます。

### 成功時

```json
{
  "success": true,
  "flowName": "Flow3_ListTeamsChannelPostReactorsFromUrl",
  "sourceUrl": "<入力URL>",
  "retrievedAt": "2026-10-26T03:00:00.0000000Z",
  "identifiers": { "tenantId": "…", "teamId": "…", "channelId": "19:…@thread.tacv2",
                   "urlMessageId": "…", "parentMessageId": "…", "targetMessageId": "…" },
  "message": { "id": "…", "createdDateTime": "…", "subject": "…",
               "from": { "displayName": "…", "userId": "…" }, "webUrl": "…" },
  "memberLookup": { "loaded": true, "httpStatusCode": "200", "memberCount": 42 },
  "reactorCount": 2,
  "reactionCount": 3,
  "reactors": [
    {
      "userId": "{userObjectId}",
      "displayName": "山田 太郎",
      "email": "{user@example.com}",
      "userIdentityType": "aadUser",
      "memberLookup": "found",
      "reactionCount": 2,
      "reactions": [
        { "reactionType": "like",  "reactionDisplayName": "Like",  "createdDateTime": "…" },
        { "reactionType": "heart", "reactionDisplayName": "Heart", "createdDateTime": "…" }
      ]
    }
  ],
  "reactions": [ { "userId": "…", "displayName": "…", "email": "…", "userIdentityType": "…",
                   "memberLookup": "…", "reactionType": "…", "reactionDisplayName": "…",
                   "createdDateTime": "…" } ],
  "warnings": []
}
```

| キー | 内容 |
|---|---|
| `reactors` | **1人1件**の一覧（重複排除済み・初めてリアクションした順）。同じ人の複数リアクションは `reactions` にまとまる |
| `reactions` | リアクション1件ごとの一覧（重複排除なし。集計の元データ） |
| `memberLookup`（各人） | `found`＝メンバー一覧で一致 / `notFound`＝一覧に居ない（退出者・ゲスト等。表示名・メールは空） / `unavailable`＝一覧自体を取得できなかった |
| `memberLookup`（全体） | メンバー一覧を取得できたか・HTTPステータス・件数。リアクション0件のときは取得しないため `loaded: false`・`httpStatusCode: "0"` |
| `warnings` | 一覧取得に失敗したときの `WARN_MEMBER_LOOKUP_FAILED` など。**警告があっても `success` は true** |

### 失敗時

Flow1 と同じ形式（`success: false` と `error.code` / `error.message` / `error.stage` / `error.details`）です。エラーコードは [docs/json_schema.md](../../../docs/json_schema.md) §5 と共通です。

## 4. 処理の流れ（Scope）

```text
Initialize_*（25変数・トップレベル）
→ Scope_ParseUrl            URL解析（Flow1と同一）
→ Scope_GetTeamsData        GET /teams/{teamId}/channels/{channelId}/messages/{messageId}
                            → reactions を varRawReactions へ退避
→ Scope_GetChannelMembers   リアクションが1件以上のときだけ
                            GET /teams/{teamId}/channels/{channelId}/members を nextLink 追跡
→ Scope_BuildReactors       ① リアクション1件ごとにメンバーを Filter して正規化（初出の userId を記録）
                            ② userId ごとに Filter / Select して1人1件にまとめる
→ Scope_CreateResult        結果JSONの作成
→ Scope_ErrorHandler        Scope_CreateResult が Failed/Skipped/TimedOut のときだけ（変数のみ参照）
→ Scope_Finalize            常に実行。Compose_Flow_Output に結果を出す
```

## 5. 設計上の判断

| 判断 | 理由 |
|---|---|
| 表示名・メールは**チャネルメンバー一覧**で補う | Graph の `reactions[].user.user` は `id` と `userIdentityType` だけで、`displayName` が null のことが多く、メールは含まれない。`/members` は `aadUserConversationMember` の `userId` / `displayName` / `email` を返す。`/users/{id}` は Teams コネクタの Graph HTTP 要求で許可されるパスの範囲外になる可能性があるため使わない |
| メンバー一覧の取得失敗で**フローを失敗させない** | 一覧取得には投稿の読み取りとは別の権限が要る可能性がある（§8）。失敗時もユーザーIDの一覧は有用なので、`memberLookup: "unavailable"` と警告を付けて返す |
| Do until 内で取得失敗時に nextLink を空にする | 反復が失敗した後も Do until が続くかは実機の挙動に依存する。どちらでも1回で止まるようにする（テストで両方を評価） |
| リアクション0件なら一覧を取得しない | 不要な Graph 呼び出しと権限エラーを避ける |
| `body('Get_Parent_Message')` を後続 Scope から参照しない | 解析エラーで取得が Skipped のとき、条件式から参照すると壊れる。リアクションは取得直後に変数へ退避する（`validate_flow3.py` §8 で機械検査） |
| 重複排除は「初出の userId を配列変数に追加」で行う | `SetVariable` の自己参照を使わない（`handbook/rules/03`）。配列の `contains()` で判定し、`AppendToArrayVariable` で追加する |
| ループ内で外側の要素は `items('<ループ名>')` で参照する | Filter array の `where` 内の `item()` はフィルタ対象側を指すため、取り違えを防ぐ |

## 6. ループとページング

| ループ | 対象 | 並列 | 上限 |
|---|---|---|---|
| `Do_Until_Members_Paging` | メンバー一覧（`@odata.nextLink` が空になるまで） | — | 5,000反復・1時間 |
| `Process_Retrieved_Members` | 1ページ分のメンバー | オフ | — |
| `Apply_To_Each_Reaction` | 親投稿のリアクション | オフ | — |
| `Apply_To_Each_Reactor` | 重複排除した userId | オフ | — |

リアクション1件ごとにメンバー配列を Filter するため、計算量は「リアクション数 × メンバー数」です。通常のチャネル（数百人・リアクション数十件）なら問題ありません。

## 7. 冪等性

読み取り専用（GETのみ）で外部に何も書き込まないため、何度実行しても副作用はありません。

## 8. 要実環境確認

| 項目 | 内容 |
|---|---|
| インポート・保存・実行 | **すべて未実施**。インポート後は 開く → 即保存 → 小規模テスト（`handbook/rules/07`） |
| `/members` の権限 | Graph の委任スコープ `ChannelMember.Read.All` 相当が Teams コネクタの既存同意で満たされるか。満たされない場合は 403 → `memberLookup: "unavailable"` と警告で続行する（フロー自体は成功） |
| リアクションの応答形 | `reactions[].user.user.id` が Entra ID のオブジェクトIDで、`/members` の `userId` と一致する前提。カスタム絵文字のリアクションでの `reactionType` の値 |
| `/members` の `email` | ゲスト・外部ユーザーで空になる可能性 |
| `/members` のページング | 大規模チームで `@odata.nextLink` が返るか（返らなければ1回で終わる） |
| チャネル種別 | 標準・プライベートは動作する想定。共有チャネルは Flow1 と同じく `groupId` 不一致で 404 の可能性 |
| メンバー取得失敗時の実行履歴の見え方 | `Scope_GetChannelMembers` が「失敗」と表示されたうえで後続が続行し、実行全体は成功になる想定 |

## 9. 検証

| 区分 | 結果 |
|---|---|
| 静的検証（`validate_flow3.py`。Flow1 の全検査＋Flow3 固有の配線検査） | **エラー0 / 警告0** |
| 共通リンター（`python tools/wdl_lint.py --all .`） | **指摘0件** |
| URL解析の回帰テスト（`tests/run_url_parse_tests.py flow3`） | **20件中20件合格** |
| 通し回帰テスト（`tests/run_reactor_flow_tests.py`。ダミー応答で definition.json の式を評価） | **12件中12件合格**（6ケース × Do until の2つの挙動仮定） |
| ZIP再展開検査（`validation/extract_check.py`） | **エラー0** |
| 実環境 | **未実施** |

通し回帰テストのケース: 同一人物の複数リアクションの集約と2ページのメンバー一覧 / メンバー一覧が 403 / リアクション0件 / メンバー一覧に居ない人 / URL解析エラー / 投稿取得 404。
