# TeamsChannelMemberSync_Setup 設計

初期設定・テスト同期フロー（手動ボタン）。
テンプレート: `handbook/templates/flow_design_template.md`

## 目的

TeamsチャネルURL・SharePointサイトURL・SharePointリスト名を受け取り、実際に同期できることを確かめたうえで、
**成功したときだけ**その設定を管理サイトの設定リストへ永続保存する。日次フローはこの設定を読んで動く。

## 対象システム

| システム | 用途 | コネクタ |
|---|---|---|
| Microsoft Teams | チャネル情報とメンバーの取得 | `shared_teams`（標準） |
| SharePoint Online | 設定リストとメンバーリストの読み書き | `shared_sharepointonline`（標準） |

## トリガー

`Request` / `kind: Button`（手動でトリガーを実行する）

| 入力 | 型 | 必須 | 説明 |
|---|---|---|---|
| `TeamsChannelUrl` | string | ○ | チャネルの「チャネルへのリンクを取得」で得られるURL |
| `SharePointSiteUrl` | string | ○ | 同期先サイトのURL（管理画面URLでも可） |
| `SharePointListName` | string | ○ | メンバーを書き込むリストの表示名 |
| `DisableOtherConfigs` | boolean | — | 他チャネルの設定を無効化して置き換えるか |
| `AdminSiteUrl` | string | — | 設定リストを置くサイト。**空なら同期先サイトへ作る** |

> トリガーの `title` / `description` に `@` を書かない。`@{` は式の補間として解釈され、インポート時に
> `Unable to parse template language expression` になる（handbook 既知エラー #3。共通リンター L03 が検出）。

## 出力

`Scope_Finalize` の `Compose_Result_Summary`（Compose の出力を実行履歴で参照する）。
Response アクション（プレミアム）には依存しない。

| 項目 | 内容 |
|---|---|
| `success` / `configSaved` | 全体の成否と、設定を保存したか |
| `teamId` / `channelId` / `tenantId` / `channelType` | URLから取り出した識別子とチャネル種別 |
| `siteUrl` / `listName` / `listId` | 正規化したサイトと対象リスト |
| `memberSource` / `allMembersFetched` / `memberCount` | 取得経路と件数 |
| `createdCount` / `updatedCount` / `unchangedCount` / `deactivatedCount` / `errorCount` | 同期の内訳 |
| `failedStage` / `errorCode` / `errorMessage` / `httpStatusCode` / `itemErrors` | 失敗の所在 |
| `runId` / `executedAt` | 実行の識別 |

**氏名・メールアドレスは含めない**（要件§12）。

## Scope 構成

| Scope | 役割 | 要件§12の単位 |
|---|---|---|
| `Scope_00_Bootstrap` | 管理サイトURL候補の正規化と検証（**空は失敗にしない**） | 永続設定の読込み |
| `Scope_01_ValidateInput` | 入力3項目の形式検証・ホスト照合 | 入力検証 |
| `Scope_02_ParseTeamsUrl` | チームID・チャネルID・テナントIDの抽出 | Teams URL解析 |
| `Scope_03_ParseSharePointUrl` | サイトルートURLへの正規化 | SharePoint URL解析 |
| `Scope_03A_ResolveConfigSite` | 設定リストを置くサイトを確定（未指定なら同期先サイト） | 永続設定の読込み |
| `Scope_03B_EnsureConfigList` | 設定リストを確保 | 永続設定の読込み |
| `Scope_04_CheckTeamsAccess` | チャネルへのアクセス確認・種別判定 | Teamsメンバー取得（前段） |
| `Scope_05_EnsureMemberList` | 対象リストの確認・作成・不足列の追加 | SharePoint対象リスト確認 |
| `Scope_06_GetMembers` | メンバー取得（ListMembers／Graph／allMembers） | Teamsメンバー取得 |
| `Scope_07_NormalizeMembers` | 正規化・重複排除・メール補完 | メンバー情報の正規化 |
| `Scope_08_GetExistingItems` | 既存アイテムのページング取得と絞り込み | SharePointアイテム取得 |
| `Scope_09_SyncItems` | 新規作成・更新・変更なし・重複記録 | 新規作成／更新 |
| `Scope_10_DeactivateLeft` | 離脱者の論理無効化（ガード付き） | 無効化又は削除 |
| `Scope_11_SaveConfig` | 全段成功時のみ設定を保存 | 設定保存 |
| `Scope_ErrorHandler` | Catch 相当 | — |
| `Scope_Finalize` | Finally 相当・結果出力 | — |

`Scope_ErrorHandler` の `runAfter` は**直前の `Scope_11_SaveConfig` 1本にだけ**張る。
複数の Scope を列挙すると AND 判定になり「前段成功・中段失敗」でハンドラが発火しない
（handbook/knowledge/lessons_learned.md §22）。

## 変数

`shared/sync_blocks.py` の `SHARED_VARIABLES`（43個）＋ 本フロー固有6個。
`InitializeVariable` は Scope 内に置けないため、すべてトップレベルの `Initialize_*` 連鎖に展開する（handbook/rules/01）。

本フロー固有: `varInputChannelUrl` / `varInputSiteUrl` / `varInputListName` /
`varDisableOtherConfigs` / `varConfigKey` / `varConfigSaved`

## 条件・ループ

- 各 Scope の本体は `Condition_Can_*`（`varIsValid == true`）で包む。前段が失敗したら後段は何もしない。
- `Foreach_Required_Field_*` / `Foreach_Raw_Member` / `Foreach_Member` / `Foreach_Left_Member` /
  `Foreach_Other_Config` はすべて **並列オフ**（`repetitions: 1`）。変数を更新するため。
- ページングは `Do_Until_Existing_Paging` / `Do_Until_Graph_Members_Paging` /
  `Do_Until_Graph_AllMembers_Paging`。終了条件は「継続リンクが空」。

## 冪等性

- 設定は `設定キー`（`<チームID>_<チャネルID>`）で **0件→作成 / 1件→更新 / 2件以上→書き込まず記録**。
- メンバーは `同期キー` で同じ3分岐。変更がなければ書き込まない。
- リストと列は「無ければ作る・不足分だけ足す」。既存には触れない。

## エラー処理

- 想定内のエラーは `varIsValid=false` ＋ `varFailedStage` ＋ `varErrorCode` に記録して安全に流す。
- 想定外の失敗は Scope が失敗し、後段が Skipped になって `Scope_ErrorHandler` が発火する。
- ハンドラ内の式は**変数だけ**を参照する（未実行アクションの `outputs` を参照するとハンドラ自体が壊れる）。

## 制約

- アクション 368 / 上限 500、ネスト深さ 6 / 上限 8、最長の式 812文字 / 上限 8,192。
- 同期処理は `shared/sync_blocks.py` が生成する。日次フローと**同一の定義**が埋め込まれる。
- 詳細な制限と未確認事項は `docs/known_limitations.md`。

---
関連: [../../../README.md](../../../README.md) / [../../../docs/design_decisions.md](../../../docs/design_decisions.md)
