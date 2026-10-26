# TeamsChannelMemberSync_Daily 設計

日次同期フロー（Recurrence）。
テンプレート: `handbook/templates/flow_design_template.md`

## 目的

管理サイトの設定リストから有効な設定を読み、設定ごとに Teams チャネルのメンバーを
SharePoint リストへ同期して、結果を設定リストへ書き戻す。
有効な設定が1件も無いときは、無効なURLで処理を続けず「初回設定が未完了」であることを出力して安全に終了する。

## 対象システム

| システム | 用途 | コネクタ |
|---|---|---|
| Microsoft Teams | チャネル情報とメンバーの取得 | `shared_teams`（標準） |
| SharePoint Online | 設定リストとメンバーリストの読み書き | `shared_sharepointonline`（標準） |

## トリガー

```json
"Recurrence": {
  "type": "Recurrence",
  "recurrence": {
    "frequency": "Day",
    "interval": 1,
    "schedule": { "hours": [7], "minutes": [0] },
    "timeZone": "Tokyo Standard Time",
    "startTime": "2026-08-05T07:00:00"
  }
}
```

毎日 **07:00（日本時間）**。`timeZone` を指定するときは `startTime` に `Z` を付けない
（付けるとUTC扱いになり `timeZone` が無視される）。UTCオフセットを定義に直接書かないことで、
意図しない日に実行される事故を防いでいる。実行時刻は公式に最大1分程度ずれる。

時刻の変更は `source/build_daily_flow.py` の `SCHEDULE_HOUR` / `SCHEDULE_MINUTE` を直して再生成する。

## 出力

`Scope_Finalize` の `Compose_Result_Summary`。

| 項目 | 内容 |
|---|---|
| `status` | `NOT_CONFIGURED` / `OK` / `FAILED` |
| `enabledConfigCount` / `processedConfigCount` | 有効な設定の数と処理した数 |
| `configResults` | 設定ごとの結果（設定キー・チームID・チャネルID・リスト名・件数・成否） |
| `failedStage` / `errorCode` / `errorMessage` / `httpStatusCode` | 失敗の所在 |
| `adminSiteUrl` / `configListTitle` | 設定の読み元 |

**氏名・メールアドレスは含めない**（要件§12）。設定リストの `最終同期結果` 列にも件数だけを書く。

## Scope 構成

| Scope | 役割 | 要件§12の単位 |
|---|---|---|
| `Scope_00_Bootstrap` | 管理サイトURLの正規化と検証 | 永続設定の読込み |
| `Scope_01_LocateConfigList` | 設定リストの位置と型名を特定（**作成しない**） | 永続設定の読込み |
| `Scope_02_ReadConfig` | 有効な設定の読込み・0件の判定 | 永続設定の読込み／入力検証 |
| `Foreach_Config` | 設定ごとのループ（トップレベル） | — |
| └ `Scope_04_CheckTeamsAccess` | チャネルへのアクセス確認・種別判定 | Teamsメンバー取得（前段） |
| └ `Scope_05_EnsureMemberList` | 対象リストの確認・作成・不足列の追加 | SharePoint対象リスト確認 |
| └ `Scope_06_GetMembers` | メンバー取得 | Teamsメンバー取得 |
| └ `Scope_07_NormalizeMembers` | 正規化・重複排除・メール補完 | メンバー情報の正規化 |
| └ `Scope_08_GetExistingItems` | 既存アイテムの取得と絞り込み | SharePointアイテム取得 |
| └ `Scope_09_SyncItems` | 新規作成・更新 | 新規作成／更新 |
| └ `Scope_10_DeactivateLeft` | 離脱者の論理無効化（ガード付き） | 無効化又は削除 |
| └ `Scope_11_RecordResult` | 設定リストへ結果を書き戻す | 設定保存 |
| `Scope_ErrorHandler` | Catch 相当 | — |
| `Scope_Finalize` | Finally 相当・結果出力 | — |

### 設定ごとの独立性

`Scope_11_RecordResult` の `runAfter` は `["Succeeded","Failed","Skipped","TimedOut"]` の4状態すべて。
1件の設定で失敗しても繰り返しは成功として終わり、次の設定へ進む。
この形になっていることは静的検査 D05 が確認する。

### `Foreach_Config` をトップレベルに置いている理由

ネスト深さの上限（8）に収めるため、`If` でくるまずトップレベルに置いている。
有効な設定が0件なら `varConfigs` が空配列になり、ループは1回も回らない。
「未設定」の判定と出力は `Scope_02_ReadConfig` の中で別に行う。

## 変数

`shared/sync_blocks.py` の `SHARED_VARIABLES`（43個）＋ 本フロー固有4個
（`varConfigs` / `varNoConfig` / `varConfigResults` / `varProcessedConfigCount`）。

`InitializeVariable` はトップレベルにしか置けないため、設定ごとの初期化は
`Reset_*_PerConfig`（`SetVariable` 31本）で行う。初期化用と更新用をアクション名で区別している
（handbook/rules/01 の命名規則）。

## 設定の検証

保存済みの値であっても素通りさせない。次のいずれかに該当したらその設定はスキップする。

| 条件 | エラーコード |
|---|---|
| チームIDが空 | `ERR_CONFIG_TEAMID_MISSING` |
| チャネルIDが空 | `ERR_CONFIG_CHANNELID_MISSING` |
| サイトURLが空 | `ERR_CONFIG_SITEURL_MISSING` |
| リスト名が空 | `ERR_CONFIG_LISTNAME_MISSING` |
| サイトURLのホストが `*.sharepoint.com` でない | `ERR_CONFIG_SITEURL_NOT_SHAREPOINT` |

## 冪等性・エラー処理・制約

フローAと同じ（同じ `shared/sync_blocks.py` から生成されるため）。

- アクション 310 / 上限 500、ネスト深さ 7 / 上限 8、最長の式 812文字 / 上限 8,192。
- 設定リストは**作らない**。無ければ「初回設定が未完了」として終了する（静的検査 D02）。
- 離脱者の無効化は4条件のガードを通ったときだけ実行する。

---
関連: [../../../README.md](../../../README.md) / [../../../docs/design_decisions.md](../../../docs/design_decisions.md)
