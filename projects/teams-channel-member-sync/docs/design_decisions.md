# 設計判断と根拠

本案件で「なぜその形にしたか」を、公式資料の出典つきで残す。
表記は handbook の約束に従う（【事実】＝公式または実機で確認済み / 【推奨】＝判断 / 【要実環境確認】＝未検証）。

---

## 1. 永続設定の保存方式

### 1.1 4方式の比較

| 観点 | Dataverse 専用テーブル | 環境変数 | **管理サイトの SharePoint 設定リスト（採用）** | OneDrive の固定パスJSON |
|---|---|---|---|---|
| 手動実行直後に定期フローが読めるか | 読める | **読めない**（後述 1.2） | 読める | 読める |
| 定期フローが保存場所を特定する方法 | 環境で一意 | 環境で一意 | インポート後に管理サイトURLを1回設定 | 接続オーナーの OneDrive で一意 |
| 循環依存 | 無し | 無し | **無し**（管理サイトは対象サイトと独立） | 無し |
| ソリューションとして移送できるか | できる | できる | ZIP（レガシー）で移送 | ZIP（レガシー）で移送 |
| ライセンス | **Premium 必須** | Dataverse 必須 | **追加不要（標準コネクタのみ）** | 追加不要 |
| 接続参照との関係 | Dataverse 接続が増える | 接続不要 | SharePoint 接続を流用 | OneDrive 接続が増える |
| セキュリティ | Dataverse のロール | 環境メーカー権限 | サイト権限で分離できる | 接続オーナー個人に紐づく |
| 保守性（値を目で見て直せるか） | 一覧で見える | 一覧で見える | **リスト画面で見える・履歴も残る** | JSONを開く必要がある |
| 複数設定への拡張 | 行を増やす | 変数が増える | **行を増やす（有効列で個別制御）** | 配列を持たせる |
| 更新反映の遅延 | 即時 | **最大1時間** | 即時 | 即時 |
| インポート先での再設定 | インポートウィザードで入力 | インポートウィザードで入力 | Compose を1箇所書き換え | 不要 |
| 本リポジトリでの実績 | 無し | 無し | **SharePoint REST は実環境実証済み** | 無し |

### 1.2 【事実】環境変数を「実行時に書き換える保存先」として使うことは公式に成立しない

これが本要件の核心（要件§6.1 が指摘した論点）で、公式に明確な記述がある。

> **When environment variable values are changed directly within an environment instead of through an ALM operation like solution import, flows will continue using the previous value until the flow is either saved or turned off and turned on again.**
> — [Use environment variables in Power Automate solution cloud flows](https://learn.microsoft.com/en-us/power-apps/maker/data-platform/environmentvariables-power-automate)

> **It might take up to an hour to fully publish updated environment variables because the value is pushed into the apps and flows asynchronously.**
> — [Use environment variables in Power Platform solutions](https://learn.microsoft.com/en-us/power-apps/maker/data-platform/environmentvariables)

「手動フローで書いた設定を、次の定期実行がそのまま読む」という本要件の中心動作が、フローの保存かオフ→オン、加えて最大1時間の非同期公開を待たないと成立しない。**候補から除外した。**

なお `environmentvariablevalue` テーブル自体は `Update` メッセージと書き込み可能な `Value` 列を持つ（[テーブルリファレンス](https://learn.microsoft.com/en-us/power-apps/developer/data-platform/reference/entities/environmentvariablevalue)）ので「技術的に書けない」わけではない。公式も「コードから変更する場合は妥当な値かを自分で確かめること」と注意している。問題は書けるかどうかではなく、**書いた値がいつ読まれるか**にある。

### 1.3 【事実】Dataverse 設定テーブルは追加ライセンスが必要

Dataverse コネクタは Power Automate で **Premium** 分類（[コネクタリファレンス](https://learn.microsoft.com/en-us/connectors/commondataserviceforapps/)）。
標準ライセンス（Microsoft 365 に含まれる Power Automate、Power Automate Free）では premium/on-premises/custom コネクタを使えない（[ライセンスFAQ](https://learn.microsoft.com/en-us/power-platform/admin/powerapps-flow-licensing-faq)）。
本案件は標準コネクタだけで要件を満たせるため、ライセンス条件を増やす選択はしなかった。

### 1.4 循環依存をどう断ち切ったか

要件が指摘するとおり、「対象 SharePoint サイト内の設定リストにURLを保存する」だけでは、定期フローが最初にそのサイトURLを知らない。

**この循環は、手動フローと定期フローで非対称である**という点が要点。

| フロー | 設定リストの場所を知る手段 | 必要な設定 |
|---|---|---|
| フローA（手動） | **実行時の入力から分かる** | **無し** |
| フローB（Recurrence） | 入力が無く、環境変数も無いので実行時には分からない | `Compose_AdminSiteUrl` 1箇所 |

したがって設定が要るのは**フローB だけ**。フローA は次の優先順位で解決し、未設定でも必ず動く。

1. トリガー入力「設定リストを置くサイトのURL」（任意）
2. `Compose_AdminSiteUrl`（任意。複数チャネルを1か所で管理したいときだけ使う）
3. **入力された同期先サイト**（既定。ここへ設定リストを作る）

フローA は使ったサイトを結果の `adminSiteUrl` に出し、`nextAction` に「フローB の `Compose_AdminSiteUrl` へこの値を貼り付けてください」と値ごと提示する。

- ZIP にテナント固有の値を入れないので、リポジトリの実値混入検査を通る（`Compose_AdminSiteUrl` が空文字であることを `flow_checks.py` P11 が機械確認する）。
- 「未設定でも動く」ことは検査 S05（退避経路の存在と、`ERR_ADMIN_SITE_NOT_SET` を手動フローが持たないこと）と回帰テスト R24・R25 で機械的に固定してある。

> 【2026-08-04 の反省】当初は**両フロー**に `Compose_AdminSiteUrl` を必須にしていた。
> 結果として「インポート後に手で設定しないと1回も動かない」設計になり、実行が2回続けて
> `ERR_ADMIN_SITE_NOT_SET` で止まった。**手作業を前提にした設計は、その手作業が抜けた状態が
> 既定になる。** 安全な既定値を置けるところには必ず置き、置けないところ（フローB）では
> 「何を・どこへ・どの値を」入れるのかをシステム側から提示する。
> → `handbook/knowledge/lessons_learned.md` §37

---

## 2. フロー構成（なぜ子フローを使わないか）

### 2.1 【事実】子フローは Dataverse ソリューション必須

> **You need a solution with two flows.**
> **Known issue** — You should create the parent flow and all child flows directly in the same solution.
> **Child flows must also have the Manually trigger a flow trigger.**
> — [Create child flows](https://learn.microsoft.com/en-us/power-automate/create-child-flows)

ソリューションは Dataverse の機能なので、子フローを使うには Dataverse が要る。さらに「親フローから子フローへ接続を渡すことはできず、子フロー側で埋め込み接続を使う設定が必要」とも公式に書かれている。

### 2.2 【事実】フロー入りソリューションZIPの手組みは公式にサポートされていない

> **Unsupported tasks** — Defining any other solution components by editing the exported customizations.xml file isn't supported. Other solution components include, but aren't limited to, the following: … **Processes (Workflows)** …
> — [When to edit the customizations file](https://learn.microsoft.com/en-us/power-platform/alm/when-edit-customization-file)

公式のルートは `pac solution pack`。本リポジトリにはソリューション形式の生成・検証ツールも実績も無く、「インポートできない成果物」になるリスクが高い。

### 2.3 【推奨】重複は生成時に排除する

そこで **実行時ではなく生成時に共通化**した。`shared/sync_blocks.py` が同期処理のアクション辞書を生成し、フローAとフローBの `build_*.py` がそれを埋め込む。

- 同期ロジックが書かれている場所は1箇所だけ。修正はそこを直して両方を再生成する。
- これはリポジトリの不変則1（「definition.json は生成物。修正は build_*.py を編集して再生成」）と完全に整合する。
- 生成された2つの definition.json が同じ内容を持つことは、`validate_*.py` が両方で同じ検査（P01〜P15）を通すことで担保する。

【トレードオフ】同期ロジックを直したら**両方を再生成して両方を配り直す**必要がある。子フローなら子だけ直せばよい。README の変更手順に両方のビルドを並べているのはこのため。

---

## 3. 認証方式（Embedded を採用）

レガシーパッケージの接続参照には2つの形がある（handbook/rules/07）。

| 形 | `authentication` | `connectionReferences[].source` |
|---|---|---|
| Embedded | `@parameters('$authentication')` | `Embedded` |
| Invoker | `X-MS-APIM-Tokens` を復号する式 | `Invoker` |

**本案件は Embedded を採用した。**

Invoker 形式は `triggerOutputs().headers['X-MS-APIM-Tokens']` に依存する。このヘッダーは「フローを起動した人」の文脈があるときに載るもので、**Recurrence（定期実行）トリガーには起動者がいない**。本リポジトリで Invoker の実績があるのはボタントリガーのフロー（teams_post_url_flows）だけで、定期実行フローでの実績は無い。

一方 Embedded 形式は `references/extracted/` にある Microsoft の実エクスポート3本すべてが採用しており、そのうち `shared-mailbox-to-teams-notify-20260803` は **ポーリングトリガー（起動者のいない自動フロー）**、`reference_original`（CreateKnowledgeList）は **ボタントリガー＋SharePoint REST**。つまり Embedded だけが**両方のトリガー種別で実エクスポートの裏付けがある**。

【要実環境確認】実機で差異が出た場合は `shared/sync_blocks.py` の `AUTH_MODE` を `"invoker"` に変えて再生成すれば切り替わる（`connectionReferences[].source` も連動する）。

---

## 4. メンバー取得の経路

### 4.1 【事実】`ListMembers` の `threadType` は `"channel"`（小文字）

公式ドキュメント（[Microsoft Teams コネクタ](https://learn.microsoft.com/en-us/connectors/teams/)）は `threadType` を "Choose message type" としか書いておらず、**許可値の列挙が無い**。実値は shared_teams のコネクタ swagger 現物で確定した。

```json
"listMembersThreadType__in_path": {
  "name": "threadType", "in": "path", "required": true,
  "type": "string",
  "enum": [ "groupchat", "channel" ],
  "x-ms-enum-values": [
    { "displayName": "Group chat", "value": "groupchat" },
    { "displayName": "Channel",    "value": "channel"   }
  ]
}
```

出典（swagger 現物）:
- 現行版: `https://github.com/wyattdave/Power-Platform/blob/main/Code%20Apps/SharePoint%20Page%20to%20MD/.power/schemas/teams/teams.Schema.json`
- Microsoft 公式リポジトリの旧版: `https://github.com/microsoft/Power-Fx/blob/main/src/tests/Microsoft.PowerFx.Connectors.Tests.Shared/Swagger/Teams.json`

公式ドキュメント側の間接的な裏づけ（`RemoveMemberFromChannel` の説明文）:
> Use the 'List chat or channel members' action with thread type **'Channel'** to look up the membership ID for a user.

`Channel`（大文字始まり）は**UIラベル**であって、定義に書く値ではない。ここを取り違えると保存時に `OpenApiOperationParameterValidationFailed` になる。

### 4.2 【事実】`ListMembers` の返り値プロパティ

公式ドキュメントの Definitions（`ListMembersResponseSchema`）と swagger 現物が一致している。

| パス | 型 | 説明 |
|---|---|---|
| `value` | array of object | メンバーの配列 |
| `value.displayName` | string | 表示名 |
| `value.email` | string | メールアドレス |
| `value.id` | string | 会話内のメンバーシップID |
| `value.roles` | array of string | ロール |
| `value.tenantId` | string | テナントID |
| `value.userId` | string | Entra のユーザーID |
| `value.visibleHistoryStartDateTime` | string | 履歴共有の開始時刻 |

**`userPrincipalName` は存在しない。** Graph の `conversationMember` / `aadUserConversationMember` にも無い（[conversationMember](https://learn.microsoft.com/en-us/graph/api/resources/conversationmember?view=graph-rest-1.0) / [aadUserConversationMember](https://learn.microsoft.com/en-us/graph/api/resources/aaduserconversationmember?view=graph-rest-1.0)）。要件§8の優先順位2（userPrincipalName）は、`GET /users/{userId}` を追加で引かないと得られない。

Graph の `/members` も同じプロパティ名（`id` / `roles` / `displayName` / `userId` / `email` / `tenantId`）を返すため、**正規化処理は両経路で共通のものが使える**。

### 4.3 【要実環境確認】`body` 配下のキー名

`ListMembers` の `body` は `x-ms-dynamic-schema`（threadType で形が変わる）で、公式ドキュメントは子プロパティを展開表示しない。`ListMembers` を `threadType=channel` で使った**実エクスポート定義は公開例が存在しない**（英語圏・日本語圏・GitHub コード検索いずれもゼロ件）。

そこで、次の2つから推論した。

1. 兄弟アクション `GetMessageDetails`（`ListMembers` と同じ threadType 駆動の dynamic-body パターン）を `threadType=channel` で使った**実エクスポート定義**:
   ```json
   "parameters": {
     "messageId": "...", "threadType": "channel",
     "body/recipient/groupId": "...", "body/recipient/channelId": "..."
   }
   ```
2. Microsoft 公式リポジトリのテストフィクスチャ `Teams_GetMessageDetails_InputType.json` — dynamic input schema の実レスポンスで、`recipient` オブジェクトが `required: ["groupId","channelId"]` を持つことを示している。
   `https://github.com/microsoft/Power-Fx/blob/main/src/tests/Microsoft.PowerFx.Connectors.Tests.Shared/Responses/Teams_GetMessageDetails_InputType.json`

採用した形:
```json
"parameters": {
  "threadType": "channel",
  "body/recipient/groupId": "@variables('varTeamId')",
  "body/recipient/channelId": "@variables('varChannelId')"
}
```

`body/groupId` / `body/channelId`（`recipient` なし）の可能性は完全には排除できない。**実機で確認が必要**。差異が出た場合は `shared/sync_blocks.py` の `LISTMEMBERS_KEY_TEAM` / `LISTMEMBERS_KEY_CHANNEL` の2定数を直して再生成すれば足りる。

### 4.4 【推奨】Graph 経路を併設した理由

`ListMembers` を主経路にしたうえで、次の場合に Teams コネクタの `HttpRequest` 経由の Graph へ自動的に切り替わるようにした（`runAfter` を `["Failed","Skipped","TimedOut"]` にしてある）。

1. `ListMembers` のパラメータ形状が実機と違って**実行時**に失敗した場合
2. `ListMembers` に `x-ms-pageable` が無く**ページング設定が使えない**ため、大規模チャネルで取りこぼしが疑われる場合

Graph 経路は `@odata.nextLink` を Do until で追跡するので件数上限が無い。
`ListMembers` が**保存時**に落ちる（パラメータ形状の誤り）場合はフォールバックでは救えないので、その場合は `MEMBER_SOURCE_MODE` を `"graph_only"` に変えて再生成する（docs/troubleshooting.md）。

要件§7の「提示された `ListMembers` アクションを理由なく削除・置換しない」に沿って、`ListMembers` は主経路として定義に残してある。

### 4.5 【事実】共有チャネルの直接メンバーと間接メンバー

> Get a list of members in a channel, including **direct members** of standard, private, and shared channels. **Use the List allMembers API to retrieve both direct and indirect members of a shared channel.**
> — [List members of a channel](https://learn.microsoft.com/en-us/graph/api/channel-list-members?view=graph-rest-1.0)

> For shared channels, the response includes: **Direct members** … **Indirect members**: Users who are members of a team with which the channel is shared … The **@microsoft.graph.originalSourceMembershipUrl** property identifies the original source team and indicates that the user is an indirect member.
> — [List allMembers](https://learn.microsoft.com/en-us/graph/api/channel-list-allmembers?view=graph-rest-1.0)

本フローは、`GET /teams/{teamId}/channels/{channelId}` で取得した `membershipType` が `shared` のときだけ `/allMembers` も取得し、同期キーで合流させる（要件§7.1 の選択肢2）。`@microsoft.graph.originalSourceMembershipUrl` の有無で `direct` / `indirect` を記録する。

---

## 5. SharePoint への書き込みを REST にした理由

【事実】`PostItem`（項目の作成）は必須の動的ボディ `item` を持つため、`dataset` / `table` を式にすると保存時に `OpenApiOperationParameterValidationFailed` になる（handbook/knowledge/error_catalog.md #6）。本要件はサイトもリストも実行時に決まるので、この経路は使えない。

【事実】`HttpRequest`（SharePoint に HTTP 要求を送信）は動的ボディを持たないためこの制約を受けず、**`dataset` を式にした状態で保存・実行できることが実環境で実証済み**（2026-07-24 / handbook/knowledge/sharepoint_rest_list_provisioning.md §11）。

REST の断片は handbook の §12 / §16 から**逐語コピー**している。要約から書き起こすと投影が落ちて 403 になる実例があるため（同 §15）。

### 5.1 【推奨】`$filter` を使わず全件ページング＋Filter array にした

既存アイテムの取得は `$filter` を使わず、`$select` + `$top=1000` + 継続リンクで全件取得してから Filter array で絞り込む。

- OData の2段エスケープ（`''` 二重化 + `uriComponent()`）の取り違えによる事故を、経路ごと排除できる。
- 非インデックス列への `$filter` は5,000件のビューしきい値で失敗するが、ID順の素のページングはしきい値に触れない。

【トレードオフ】リストの全アイテムを毎回取得する。同期先リストを本用途に専用化するか、チャネル数を絞ることを前提にしている。

### 5.2 継続リンクの形

SharePoint REST の継続リンクは受理ヘッダーによって `odata.nextLink`（v3形）・`@odata.nextLink`（v4形）・`d.__next`（verbose）のいずれかで返る。テナント差で取り違えると2ページ目以降が落ちるため、**3形すべてを `coalesce` で受ける**。取得した絶対URLは `_api/` 以降を切り出してサイト相対に直す（`parameters/uri` はサイト相対を期待するため）。

Graph の `@odata.nextLink` は**完全URLをそのまま次の要求に使う**（handbook/rules/05）。

---

## 6. 安全性の作り込み方

「気をつける」ではなく「**その経路を定義から消す**」で担保している（handbook/knowledge/lessons_learned.md §24-B）。

| 要件で禁止されていること | 定義上どう不可能にしたか | 機械検査 |
|---|---|---|
| 既存リストの無条件削除 | DELETE 系 REST を1件も生成しない | P03 |
| 既存列の無条件削除 | `deleteObject` を1件も生成しない。列は不足分の追加のみ | P03 |
| 対象外アイテムの削除 | 書き込み対象は `SyncSource` と `ChannelId` で二重に絞る | P09・テスト Q01〜Q03 |
| リスト全体の初期化 | ビュー操作・`removeAllViewFields` を1件も生成しない | P03 |
| リスト名だけを根拠にした破壊的再作成 | 書き込みURIは必ずリストID。`GetByTitle(` を1件も使わない | P04 |
| Teams取得失敗時に全件無効化 | 4条件のガードを通らないと無効化スコープが動かない | P09・テスト G01〜G06 |
| 接続IDの埋め込み | 匿名GUIDのみ。実値混入を正規表現で検出 | P12 |
| Teams / SharePoint 以外のホスト | 入力検証でホストを明示的に照合。Graph 宛先を固定 | P08・テスト T08・S04 |

これらの検査が**本当に発火するか**は `tests/run_check_regression_tests.py` が証明する（定義をわざと壊して22件すべての発火を確認）。「検査が通った」は「自分が思いついた観点は通った」でしかないため（lessons_learned §27）。

---

## 7. 実行時刻を 07:00 JST にした理由

- 業務開始前に前日までの異動が反映されている状態にするため。
- `timeZone: "Tokyo Standard Time"` を明示し、`startTime` に `Z` を付けない。`Z` を付けると UTC 扱いになり `timeZone` が無視される（[公式](https://learn.microsoft.com/en-us/azure/connectors/connectors-native-recurrence)）。UTCオフセットを定義に直接書かないことで、意図しない日に実行される事故を防いでいる。
- Tokyo Standard Time は夏時間を持たないため、季節による時刻移動は起きない。
- 【事実】実行時刻は公式に**最大1分程度ずれる**ことがある。

---

## 8. 参照した公式資料

- [Microsoft Teams コネクタ](https://learn.microsoft.com/en-us/connectors/teams/) — `ListMembers` / `ListTeamMembers` / `HttpRequest` / 制限
- [List members of a channel（Graph）](https://learn.microsoft.com/en-us/graph/api/channel-list-members?view=graph-rest-1.0)
- [List allMembers（Graph）](https://learn.microsoft.com/en-us/graph/api/channel-list-allmembers?view=graph-rest-1.0)
- [conversationMember](https://learn.microsoft.com/en-us/graph/api/resources/conversationmember?view=graph-rest-1.0) / [aadUserConversationMember](https://learn.microsoft.com/en-us/graph/api/resources/aaduserconversationmember?view=graph-rest-1.0)
- [Microsoft Graph アクセス許可リファレンス](https://learn.microsoft.com/en-us/graph/permissions-reference) — `ChannelMember.Read.All` は委任でも管理者同意必須
- [SharePoint コネクタ](https://learn.microsoft.com/en-us/connectors/sharepointonline/)
- [Get items / Get files の詳細](https://learn.microsoft.com/en-us/sharepoint/dev/business-apps/power-automate/guidance/working-with-get-items-and-get-files) — 既定100件・5,000件しきい値
- [Recurrence トリガー](https://learn.microsoft.com/en-us/azure/connectors/connectors-native-recurrence)
- [Power Automate の制限](https://learn.microsoft.com/en-us/power-automate/limits-and-config) — アクション500 / ネスト8 / 変数250 / 式8,192文字
- [子フローの作成](https://learn.microsoft.com/en-us/power-automate/create-child-flows)
- [環境変数（Power Automate）](https://learn.microsoft.com/en-us/power-apps/maker/data-platform/environmentvariables-power-automate) / [環境変数（Power Platform）](https://learn.microsoft.com/en-us/power-apps/maker/data-platform/environmentvariables)
- [接続参照](https://learn.microsoft.com/en-us/power-apps/maker/data-platform/create-connection-reference)
- [ソリューションのインポート](https://learn.microsoft.com/en-us/power-apps/maker/data-platform/import-update-export-solutions) / [customizations.xml の編集](https://learn.microsoft.com/en-us/power-platform/alm/when-edit-customization-file)
- [非ソリューションフローのエクスポート・インポート](https://learn.microsoft.com/en-us/power-automate/export-import-flow-non-solution) — レガシーパッケージ
- [Dataverse コネクタ](https://learn.microsoft.com/en-us/connectors/commondataserviceforapps/) / [ライセンスFAQ](https://learn.microsoft.com/en-us/power-platform/admin/powerapps-flow-licensing-faq)
- [Default Time Zones](https://learn.microsoft.com/en-us/windows-hardware/manufacture/desktop/default-time-zones) — `Tokyo Standard Time`

---
関連: [../README.md](../README.md) / [known_limitations.md](known_limitations.md) / [../../../handbook/rules/00_power_automate_core_rules.md](../../../handbook/rules/00_power_automate_core_rules.md)
