# CreateInitializedSharePointList — フロー定義の説明

実行時に指定された SharePoint サイトURLとリスト名を受け取り、**同名リストが存在しない場合に限って**新しい汎用リストを作成し、利用者から見えるデータ列を `sample_raw`（拡張リッチテキスト）だけに初期化する手動トリガーのクラウドフローです。

| 項目 | 値 |
|---|---|
| フロー名（論理名） | `CreateInitializedSharePointList` |
| 表示名 | SharePointリスト新規作成＋初期化（既存リスト保護） |
| トリガー | 手動でフローをトリガーします（`manual` / `Request` / `kind: Button`） |
| 使用コネクタ | SharePoint（`shared_sharepointonline`）1本のみ・プレミアム不要 |
| operationId | `HttpRequest` のみ（16アクション） |
| アクション総数 | 176 |
| 生成元 | `../source/build_list_flow.py` |
| 検証 | `../source/validate_list_flow.py`（エラー0 / 警告0） |
| パッケージ | `../release/CreateInitializedSharePointList_20260724211020.zip` |

**`definition.json` は生成物です。** 修正は必ず `../source/build_list_flow.py` を編集し、再生成 → 検証 → 再パッケージしてください（`CLAUDE.md` 不変則1）。

---

## 1. トリガー（§3）

| 内部名 | 表示名 | 型 | 必須 |
|---|---|---|---|
| `SharePointUrl` | SharePointサイトまたはリスト一覧URL | string | **はい** |
| `ListName` | 作成するリスト名 | string | **はい** |
| `ListDescription` | リストの説明 | string | いいえ |

`ListDescription` 省略時の既定値は「Power Automateにより作成された初期化済みリスト」です。

```text
Initialize_ListDescription の初期値
@if(empty(trim(coalesce(triggerBody()?['ListDescription'], ''))),
    'Power Automateにより作成された初期化済みリスト',
    trim(coalesce(triggerBody()?['ListDescription'], '')))
```

`if()` は両分岐を先行評価するため、**両方の分岐で `coalesce` を通して null 安全にしています**。

---

## 2. 変数（§28。すべてトップレベルで初期化）

`InitializeVariable` は Scope 内に置けないため、フロー冒頭に33個を直列で並べています（`handbook/rules/01`【事実】）。指示書§26 の `Scope_Initialize` はこの連鎖で代替しています。

### 指示書§28 の必須変数（23個）

```text
varInputSharePointUrl  varSiteUrl  varSiteId  varSiteTitle  varListName  varListDescription
varExistingLists  varMatchedLists  varListExists
varCreatedListId  varCreatedListTitle  varCreatedListRootFolder  varCreatedInThisRun
varDeletedFields  varSkippedFields  varFieldDeleteErrors
varDefaultViewId  varDefaultViewTitle  varFinalViewFields
varStatus  varResultObject  varResultJson  varErrorMessages
```

`validate_list_flow.py` がこの23個の存在を機械確認しています。

### 制御・診断用に追加した変数（10個）

| 変数 | 型 | 用途 |
|---|---|---|
| `varVerifiedUrl` | String | `_api/web` が返したサイトURL |
| `varIsValid` | Boolean | 処理を継続してよいか |
| `varStage` | String | 現在の処理段階（結果JSONの `stage`） |
| `varErrorCode` / `varErrorMessage` | String | 確定したエラー |
| `varLastStatusCode` | String | 直近のHTTPステータス（**失敗時もハンドラから読めるよう変数へ退避**） |
| `varRollbackPerformed` | Boolean | ロールバックを実施したか |
| `varItemCount` | Integer | 作成直後のアイテム件数 |
| `varSampleRawCreated` | Boolean | `sample_raw` の作成・検証に成功したか |
| `varExistingListInfo` | Object | 同名リストの情報（結果JSON用） |

---

## 3. 構成（Try / Catch / Finally）（§26）

```text
[トップレベル] Initialize_Input_SharePointUrl … Initialize_ExistingListInfo   (33変数)
Scope_Parse_And_Validate_Input   runAfter: 最後のInitialize [Succeeded]
Scope_Verify_SharePoint_Site     runAfter: 前 [Succeeded]
Scope_Check_Existing_List        runAfter: 前 [Succeeded]
Scope_Create_List                runAfter: 前 [Succeeded]
Scope_Initialize_List            runAfter: 前 [Succeeded]
Scope_Delete_Deletable_Fields    runAfter: 前 [Succeeded]
Scope_Create_SampleRaw_Field     runAfter: 前 [Succeeded]
Scope_Configure_Default_View     runAfter: 前 [Succeeded]
Scope_Validate_Result            runAfter: 前 [Succeeded]
Scope_Handle_AlreadyExists       runAfter: 前 [Succeeded]
Scope_Handle_Error               runAfter: Scope_Handle_AlreadyExists [Failed, Skipped, TimedOut]  ← Catch
Scope_Rollback_New_List          runAfter: Scope_Handle_Error [4状態]
Scope_Finalize                   runAfter: Scope_Rollback_New_List [4状態]                        ← Finally
```

### なぜ Catch の `runAfter` を1本だけにするのか

`runAfter` に複数のアクションを列挙すると **AND判定**になります。Try相当の全スコープを `[Failed, Skipped, TimedOut]` で列挙すると、「前段は成功・中段が失敗」というよくあるケースで前段が `Succeeded` のため条件を満たさず、**ハンドラが発火しません**。

スコープを直列に連鎖させておけば、途中で失敗した時点で後続がすべて `Skipped` になります。したがって**直前の1本だけを見れば、どの段階の失敗も確実に捕捉**できます。

### ハンドラの参照安全

`Scope_Handle_Error` 内の式は**変数だけ**を参照します。スコープ内の Compose の `outputs()` をハンドラで参照すると、その Compose が実行されなかった場合にハンドラ自体が壊れます（`handbook/rules/08`）。

HTTPステータスをハンドラで使うため、REST 呼び出しの直後に `runAfter: [Succeeded, Failed]` の SetVariable を置き、**失敗しても必ず実行される**形で変数へ退避しています。

---

## 4. 各スコープの処理

| スコープ | 内容 | 詳細 |
|---|---|---|
| `Scope_Parse_And_Validate_Input` | URL解析（フラグメント/`_layouts`/クエリ/末尾スラッシュの処理）とリスト名検証 | [url_parsing_spec.md](../../../docs/url_parsing_spec.md) |
| `Scope_Verify_SharePoint_Site` | `_api/web` で疎通・参照権限を確認。401/403/404 を区別 | [safety_mechanisms.md](../../../docs/safety_mechanisms.md) §7 |
| `Scope_Check_Existing_List` | 全リスト取得（非表示含む）＋ `toLower(trim())` での同名判定 | [list_operations_spec.md](../../../docs/list_operations_spec.md) §1 |
| `Scope_Create_List` | `varListExists == false` のときだけ作成。競合時は `AlreadyExistsOrConflict` | 同 §2 |
| `Scope_Initialize_List` | 空確認・添付無効化・Title 必須解除 | 同 §3.1〜3.3 |
| `Scope_Delete_Deletable_Fields` | `CanBeDeleted=true` の列を並列オフで削除。成功/失敗を配列に記録 | 同 §3.4〜3.7 |
| `Scope_Create_SampleRaw_Field` | `createFieldAsXml` で作成し、5項目で検証 | 同 §4 |
| `Scope_Configure_Default_View` | `DefaultView=true` で既定ビューを特定 → 列全除去 → `sample_raw` 追加 → 検証 | 同 §5 |
| `Scope_Validate_Result` | 6条件の最終判定 → `Created` / `InitializationFailed` | 同 §7 |
| `Scope_Handle_AlreadyExists` | 同名リストありのときの結果情報を組み立て | 同 §1.3 |
| `Scope_Handle_Error` | エラーコード・メッセージ・診断情報を**変数のみ**から確定 | §3 |
| `Scope_Rollback_New_List` | 4条件をすべて満たすときだけ、**作成応答のIDで** DELETE | [safety_mechanisms.md](../../../docs/safety_mechanisms.md) §6 |
| `Scope_Finalize` | 3形式の結果JSONを組み立て → `varResultJson` へシリアライズ | [json_schema.md](../../../docs/json_schema.md) |

初期化系の5スコープ（`Scope_Initialize_List` 〜 `Scope_Configure_Default_View`）は、いずれも先頭に同じガードを持ちます。

```text
Condition_*_Guard : varCreatedInThisRun == true かつ varIsValid == true
```

---

## 5. 安全設計（このフローの主眼）

既存リストを1つでも誤って初期化すれば業務データの列が消えます。安全性は設計だけでなく**機械検査で0件を保証**しています。

| 防御 | 実装 | 検査結果 |
|---|---|---|
| リスト名で対象を特定しない | 書き込みURIはすべて `lists(guid'<varCreatedListId>')` | `GetByTitle(` **0件** |
| 書き込みは今回作成したリストにのみ届く | 新規作成POST以外の全POSTが `varCreatedListId` を含む | 全件 |
| 作成は同名リストが無いときだけ | `varListExists == false` ガード | 確認済み |
| 初期化は今回作った物にだけ | `varCreatedInThisRun == true` ガード | 12件すべて |
| 確認は作成より先 | 位相順 | 確認済み |
| 作成失敗後にリストを取りに行かない | 失敗経路にREST呼び出し無し | 確認済み |
| 削除対象は `CanBeDeleted` でのみ判定 | フィルタ経由・列名リスト不使用 | 確認済み |
| ロールバックはID完全一致のみ | 4条件ガード＋ID指定 | 確認済み |

詳細は [safety_mechanisms.md](../../../docs/safety_mechanisms.md) を参照してください。

---

## 6. 使用しているREST（実証度）

REST形式は実働リファレンス `CreateKnowledgeList`（`references/extracted/reference_original/`。**実環境で動作実績あり**）から流用しています。

| 用途 | 実証度 |
|---|---|
| リスト作成 `POST _api/web/lists` | **実証済み** |
| 添付無効化 `MERGE {"EnableAttachments": false}` | 実証済み（値は `true` → `false` に変更） |
| Title 必須解除 `getbyinternalnameortitle('Title')` + `{"Required": false}` | **実証済み** |
| 列作成 `createFieldAsXml` | **実証済み**（Field XML の内容は本件固有） |
| ビュー列全削除 `removeAllViewFields()` | 実証済み（パスは `defaultView/...` → `views(guid'..')/...` に変更） |
| ビュー列追加 `AddViewField('..')` | 同上 |
| サイト確認 / 全リスト取得 / ItemCount / `deleteObject()` / views 取得 / `views(guid'..')` 形のビュー操作 / ViewFields | **本フローで実証**（2026-07-24 の `status: Created` 実行） |
| リストDELETE（ロールバック） | **要実環境確認**（失敗経路のため今回は通っていない） |

確認状況の全件は [validation_report.md](../../../tests/validation_report.md) §5 を参照してください。

---

## 7. アクション命名（§30）

`Compose` / `Compose 2` / `Condition 3` / `HTTP 4` / `変数を設定する 2` のような役割不明の名前は使っていません。全176アクションが役割の分かる名前を持ち、検証スクリプトで**フロー全体での一意性**も確認しています。

指示書§30 が例示した名前はすべて採用しています。

```text
Initialize_Input_SharePointUrl  Initialize_SiteUrl  Initialize_ListName
Parse_SiteUrl  Validate_SiteUrl  Validate_ListName  Verify_SharePoint_Web
Get_All_Lists  Filter_Matching_List_Names  Determine_List_Existence  Return_Already_Exists
Create_Generic_List  Store_Created_List_Id  Set_Created_In_This_Run
Verify_Empty_List  Disable_Attachments  Get_All_List_Fields  Filter_Deletable_Fields
Delete_Deletable_Field  Create_SampleRaw_Field  Verify_SampleRaw_Field
Get_Default_View  Remove_All_Default_View_Fields  Add_SampleRaw_To_Default_View
Verify_Default_View_Fields  Build_Result_Object  Serialize_Result_To_Json
Rollback_Newly_Created_List  Handle_Error
```

`Initialize_TargetMessageId` 相当の初期化用と更新用は名前を分けています（`handbook/rules/01`）。

実行順の全アクション一覧は [`../validation/action_outline.txt`](../validation/action_outline.txt) を参照してください。

### ネスト深さ

最深は `Scope_Delete_Deletable_Fields > Condition_Delete_Fields_Guard > Apply_to_each_DeleteField > Delete_Deletable_Field` の4段で、上限8段に十分収まっています（`handbook/rules/01`）。

---

## 8. 既知の制約

- 対応するURLは サイトルート／`viewlsts.aspx`／クエリ付き／サブサイト／テナントルート の5形式です。個別リストのビューURL（`.../Lists/<名前>/AllItems.aspx`）は対象外で、実行時に404で失敗します。
- リスト名の制御文字検出はタブ・CR・LF の3種類だけです。他の制御文字は SharePoint 側で拒否されます。
- 予約名の一覧は保守的な集合であり、SharePoint が拒否する名前の完全な一覧は非公開です。
- 削除不能なシステム列のフォーム非表示化は実装していません（制約として記録します）。
- **実環境でのインポート・実行には成功しています（2026-07-24・`status: Created`）。** `dataset` に式を指定した状態での保存という最大の懸案も解消されました。
- **ただし「同名リストが存在する場合」の経路は実機で発火していません。** 既存リスト保護は定義の構造から静的に保証されていますが、実機確認はまだです（[validation_report.md](../../../tests/validation_report.md) §5-1）。ロールバック・権限不足・競合などの失敗経路も未確認です。

---

関連: [url_parsing_spec.md](../../../docs/url_parsing_spec.md) / [list_operations_spec.md](../../../docs/list_operations_spec.md) / [safety_mechanisms.md](../../../docs/safety_mechanisms.md) / [json_schema.md](../../../docs/json_schema.md) / [validation_report.md](../../../tests/validation_report.md)
