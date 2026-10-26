# SyncSharedMailboxToSharePointList — フロー定義の説明

| 項目 | 値 |
|---|---|
| 論理名 | `SyncSharedMailboxToSharePointList` |
| 表示名 | 共有メールボックスのメールをSharePointリストへ同期 |
| トリガー | `manual`（Request / Button）＋ 入力4項目 |
| コネクタ | `shared_sharepointonline`（HttpRequest）/ `shared_office365`（GetEmailsV3）/ `shared_conversionservice`（HtmlToText） |
| アクション総数 | 304（SharePoint REST 34・Outlook 1・Content Conversion 1） |
| 変数 | 41（すべてトップレベルで初期化） |
| 最大ネスト深さ | 7（上限8） |
| 生成元 | `../source/build_sync_flow.py` |
| 検証 | `../source/validate_sync_flow.py`（エラー0・警告0） |
| パッケージ | レガシー5ファイル構造・接続参照は Invoker形式＋匿名GUID |

**`definition.json` は生成物**。修正は必ず `build_sync_flow.py` を編集して再生成する。

---

## 1. トリガー

```json
"manual": {"type": "Request", "kind": "Button", "inputs": {"schema": {
  "type": "object",
  "properties": {
    "SharePointUrl":        {"title": "SharePointサイトまたはリスト一覧URL", "type": "string"},
    "ListName":             {"title": "作成するリスト名",                   "type": "string"},
    "SharedMailboxAddress": {"title": "共有メールボックスのアドレス",        "type": "string"},
    "MailCount":            {"title": "取得件数",                           "type": "integer"}
  },
  "required": ["SharePointUrl", "ListName", "SharedMailboxAddress", "MailCount"]
}}}
```

`MailCount` を `integer` にしているため、デザイナー上で数値以外は入力できない。
それに加えて**フロー内でも数字だけかを検査**している（多層防御。[docs/url_parsing_spec.md](../../../docs/url_parsing_spec.md) §6）。

---

## 2. 変数（41個・すべてトップレベル）

`InitializeVariable` は Scope 内に置けない（[handbook/rules/01](../../../../../handbook/rules/01_flow_architecture_rules.md)）ため、
トップレベルで41個を直列に連鎖させている。

| 区分 | 変数 |
|---|---|
| 入力 | `varInputSharePointUrl` `varListName` `varMailbox` `varRawCount` `varRequestedCount` |
| 検証・制御 | `varIsValid` `varStage` `varErrorCode` `varErrorMessage` `varErrorMessages` `varLastStatusCode` |
| サイト | `varSiteUrl` `varSiteOrigin` `varSiteId` |
| リスト | `varListExists` `varListId` `varListEntityType` `varListServerRelativeUrl` `varListUrl` `varCreatedInThisRun` `varDefaultViewId` |
| スキーマ | `varSchemaOk` `varMissingFields` `varIncompatibleFields` `varSchemaWarnings` |
| 集計 | `varFetchedCount` `varCreatedCount` `varUpdatedCount` `varDuplicateCount` `varFailedCount` `varTruncatedCount` |
| 記録 | `varDuplicates` `varItemErrors` `varTruncatedItems` |
| ループ作業 | `varItemBodyText` `varItemBodyFinal` `varItemError` `varItemCreateFailed` |
| 結果 | `varStatus` `varResultObject` `varResultJson` |

ループ作業変数は各反復の先頭で定数を代入してリセットする。**自己参照はしない**
（値式に自身の `variables('...')` を書かない）。

累積が必要なものは `AppendToArrayVariable`（26件）と `IncrementVariable`（10件）を使う。
`SetVariable` + `union`/`concat`/`add` による自己参照は1件も無い（検証スクリプトで確認）。

---

## 3. 構成（Try / Catch / Finally）

```text
Initialize_* ×41                （トップレベル直列）
Scope_Validate_Input            入力検証・URL正規化
Scope_Check_List                サイト疎通・同名リストの完全一致判定
Scope_Create_List               未存在時のみ：作成直前再確認 → 作成 → 失敗時の再確認
Scope_Init_List_Schema          今回作成したリストにだけ列を作成・表示名変更・Title必須解除
Scope_Configure_View            既定ビューの列と並び順（日時降順）
Scope_Verify_Schema             必要な列の実在と型互換の確認（最後の関門）
Scope_Get_Emails                共有メールボックスからの取得
Scope_Sync_Items                メール1件ずつの登録／更新
Scope_Create_Result             正常系の結果確定（想定内エラーもここ）
Scope_Handle_Error              Catch。runAfter は Scope_Create_Result 1本だけ
Scope_Finalize                  結果JSONの組み立て。runAfter は4状態すべて
```

### なぜ Catch の `runAfter` を1本だけにするのか

`runAfter` に複数のアクションを列挙すると **AND判定**になる。Try相当の全Scopeを
`[Failed, Skipped, TimedOut]` で列挙すると、「前段は成功・中段が失敗」という
よくあるケースで前段が `Succeeded` のため条件を満たさず、**ハンドラが発火しない**。

Scopeを直列に連鎖させておけば、途中で失敗した時点で後続Scopeが `Skipped` になるため、
**最終Scope 1本の `Skipped/Failed/TimedOut`** でどの段階の失敗も確実に捕捉できる。
（[lessons_learned.md §21](../../../../../handbook/knowledge/lessons_learned.md)）

### 想定内エラーと想定外エラーの分離

| 区分 | 例 | 経路 |
|---|---|---|
| 想定内 | 入力不正・同名リスト複数・スキーマ非互換・重複異常 | `varIsValid` / `varErrorCode` で**正常系のまま分岐**。Catch には落とさない |
| 想定外 | コネクタの失敗・タイムアウト | `Scope_Handle_Error` が HTTPステータスから分類 |

この分離により、**成功側の式だけが `body(...)` を参照する**形にできる。
失敗側・ハンドラは変数だけを参照するため、コネクタがスキップされていても式が壊れない。

### ハンドラの参照安全

各コネクタ呼び出しの直後に `runAfter: [Succeeded, Failed]` の SetVariable を置き、
HTTPステータスを `varLastStatusCode` へ**退避**している
（[expression_examples.md 15-D](../../../../../handbook/knowledge/expression_examples.md)）。
ハンドラは `outputs()` を一切参照せず、変数だけを読む。

---

## 4. 各スコープの処理

| スコープ | 主な処理 | ガード |
|---|---|---|
| `Scope_Validate_Input` | URL正規化（フラグメント→クエリ→`/_layouts/`→末尾スラッシュ）、リスト名・アドレス・件数の検証 | なし |
| `Scope_Check_List` | `GET _api/web` 疎通 → `GET _api/web/lists` → Query で完全一致判定 | `varIsValid == true` |
| `Scope_Create_List` | 作成直前の再確認 → `POST _api/web/lists` → 2xx判定 → 失敗時の再確認 | `varIsValid == true` かつ `varListExists == false` |
| `Scope_Init_List_Schema` | 列の冪等作成（5列）→ 表示名の日本語化 → Title必須解除 → 一意制約の検証 | **`varCreatedInThisRun == true`** |
| `Scope_Configure_View` | 既定ビュー特定（`DefaultView` プロパティ）→ 列全削除 → 5列追加 → `ViewQuery` で降順 → 検証 | **`varCreatedInThisRun == true`** |
| `Scope_Verify_Schema` | リスト情報取得（`ListItemEntityTypeFullName` / `RootFolder`）→ 5列の実在と型の照合 | `varIsValid == true` かつ `varListExists == true` |
| `Scope_Get_Emails` | `GetEmailsV3` → 降順ソート → 上位N件 | `varIsValid` かつ `varSchemaOk` |
| `Scope_Sync_Items` | `Foreach_Email`（並列オフ）→ 本文変換 → 検索 → 登録／更新／重複記録 | `varIsValid` かつ `varSchemaOk` |
| `Scope_Create_Result` | `varStatus` を `Created` / `Existing` / `Error` に確定 | なし |
| `Scope_Handle_Error` | HTTPステータスからコード・メッセージ・診断情報を生成 | （runAfter で発火） |
| `Scope_Finalize` | 結果オブジェクト生成 → 文字列化 → `Compose_Flow_Output` | なし |

### `Foreach_Email` の中（1メールあたり）

```text
Set_Item_*_Reset ×4                     作業変数のリセット
Compose_Message_Id / Subject / Sender / Received / Body_Html
Condition_Item_Has_Body                 本文があるときだけ HtmlToText
Condition_Item_Ready                    ID が使え、変換に失敗していないとき
  Condition_Body_Too_Long               63999文字超なら切り詰めて記録
  Search_Existing_Item                  $filter で既存を検索（'' 2重化＋uriComponent）
  Append_Search_Error                   検索失敗を「0件」と誤認しない
  Condition_Item_Is_Duplicate           2件以上 → 書き込まず記録
  Condition_Item_Exists                 1件 → MERGE で更新
  Condition_Item_Is_New                 0件 → 作成
  Condition_Create_Failed_Fallback      作成失敗 → 再検索 → あれば更新
Condition_Item_Message_Id_Unusable      ID が空/255文字超 → 失敗記録
Condition_Item_Convert_Failed           変換失敗 → 失敗記録
```

`concurrency.repetitions = 1`（並列オフ）。変数を更新するループのため必須
（[handbook/rules/01](../../../../../handbook/rules/01_flow_architecture_rules.md)）。

---

## 5. 安全設計（このフローの主眼）

「気をつける」ではなく**その経路を定義から消す**ことで担保し、検証スクリプトで走査する。

| # | 保証 | 実装 |
|---|---|---|
| A | リスト名で対象を特定しない | `GetByTitle(` を1件も使わない。URIは `lists(guid'{id}')` 形式 |
| B | 書き込み先を取り違えない | POST のURIに必ず `varListId`。新規作成 `_api/web/lists` のみ例外 |
| C | 何も削除しない | `deleteObject` / `recycle` / `X-HTTP-Method: DELETE` を1件も持たない |
| D | 既存リストを変更しない | 列作成・表示名変更・Title変更・ビュー操作は `varCreatedInThisRun` ガード配下（18件） |
| E | 既存ビューを壊さない | `removeAllViewFields()` は1件のみ・同ガード配下 |
| F | メールを変更しない | Outlook の operationId は `GetEmailsV3` のみ。既読化・移動・削除・送信が定義に無い |
| G | サイトを固定しない | 全34アクションの `dataset` が `@variables('varSiteUrl')` |
| H | クエリを壊さない | `$filter` は `''` 2重化＋`uriComponent()` の両方を経由 |
| I | 部分一致で誤検出しない | 同名判定は `equals`。`contains` を使わない |
| J | 検証前に何もしない | メール取得・同期は `varIsValid` / `varSchemaOk` ガード配下 |
| K | 黙って切り捨てない | 件数上限超過は事前エラー、本文切り詰めは `truncatedItems[]` に記録 |

---

## 6. 使用しているREST（実証度）

| REST | 用途 | 区分 |
|---|---|---|
| `GET _api/web?$select=Id,Title,Url` | サイト疎通 | 【実証済み】 |
| `GET _api/web/lists?$select=Id,Title,Hidden,BaseTemplate,RootFolder/ServerRelativeUrl&$expand=RootFolder&$top=5000` | 同名リスト確認 | 【実証済み】 |
| `POST _api/web/lists`（verbose・`SP.List`） | リスト作成 | 【実証済み】 |
| `GET _api/web/lists(guid'{listId}')?$select=Id,Title,ListItemEntityTypeFullName,RootFolder/ServerRelativeUrl&$expand=RootFolder` | リスト情報 | 【実証済み】（`ListItemEntityTypeFullName` の取得は本フロー初） |
| `GET _api/web/lists(guid'{listId}')/fields?$select=Id,Title,InternalName,TypeAsString&$top=5000` | 列一覧 | 【実証済み】 |
| `POST .../fields/createFieldAsXml`（`Options:0`） | 列作成 | 【実証済み】 |
| `POST .../fields/getbyinternalnameortitle('..')`（MERGE・nometadata） | 表示名変更・Title必須解除 | 【実証済み】（Title必須解除のみ。表示名変更は本フロー初） |
| `GET .../views?$select=Id,Title,DefaultView` | 既定ビュー特定 | 【実証済み】 |
| `POST .../views(guid'..')/viewfields/removeAllViewFields()` | ビュー列全削除 | 【実証済み】 |
| `POST .../views(guid'..')/viewfields/AddViewField('..')`（MERGE・verbose） | ビュー列追加 | 【実証済み】 |
| `POST .../views(guid'..')`（MERGE・`ViewQuery`） | 並び順の設定 | **【要実環境確認】本フロー初** |
| `GET .../views(guid'..')/ViewFields` | ビュー列の検証 | 【実証済み】 |
| `GET .../items?$select=Id&$top=2&$filter=MessageId eq '..'` | 重複検索 | **【要実環境確認】本フロー初** |
| `POST .../items`（verbose・`__metadata.type`） | アイテム作成 | **【要実環境確認】本フロー初** |
| `POST .../items({id})`（MERGE・verbose） | アイテム更新 | **【要実環境確認】本フロー初** |

「【実証済み】」は `create_initialized_sharepoint_list`（2026-07-24 実環境実行成功）または
`CreateKnowledgeList`（実働サンプル）で確認された形式。

---

## 7. アクション命名

- 英数字とアンダースコアのみ（[handbook/rules/01](../../../../../handbook/rules/01_flow_architecture_rules.md)）
- フロー全体で一意（検証スクリプトで確認）
- 接頭辞で役割が分かる: `Scope_` / `Condition_` / `Compose_` / `Set_` / `Append_` /
  `Increment_` / `Filter_` / `Get_` / `Create_` / `Update_` / `Verify_` / `Validate_`
- 列ごとに繰り返す処理は内部名をサフィックスにする（`Create_Field_MessageId` 等）

### ネスト深さ

最深7段（`Scope_Sync_Items` > `Condition_Sync_Allowed` > `Foreach_Email` >
`Condition_Item_Ready` > `Condition_Create_Failed_Fallback` > `Condition_Retry_Found` > リーフ）。
上限8を超えていない。

---

## 8. 既知の制約

- 取得件数の上限は100件（調整制限と実行時間上限から決定）
- `MessageId` は1行テキスト列（255文字上限）。超えるIDのメールは当該1件のみ失敗記録
- 本文は63,999文字で切り詰め（`truncatedItems[]` に記録）
- 既存リストが非互換でも自動修復しない
- 手動トリガーのためトリガーレベルの同時実行制御は行えない
- 個別リストのビューURL（`/Lists/../AllItems.aspx`）はサイトURLとして切り出せない

## 9. 未確認事項

**実環境でのインポート・保存・実行はいずれも未実施。**

- `GetEmailsV3` のパラメータキー名と既定の並び順
- `createFieldAsXml` での `EnforceUniqueValues` の反映可否
- `ViewQuery` による並び順設定の動作
- `__metadata.type` を添えたアイテム作成の動作
- `HtmlToText` の出力形とDLP適合
- Outlook の `from` フィールドが文字列（アドレス）かオブジェクトか
- 3コネクタ構成での接続再マッピング（本リポジトリの実績は接続1本の構成のみ）
