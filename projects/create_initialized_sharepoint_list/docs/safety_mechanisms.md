# 安全機構の説明

このフローの最大の関心事は「**既存リストを絶対に壊さないこと**」です。同名リストを1つでも誤って初期化すれば、業務データの列が消えます。

そのため安全性は設計だけに頼らず、**`source/validate_list_flow.py` の機械検査で0件を保証**しています。設計意図と検査を1対1で対応させているのがこの文書の主旨です。

---

## 1. 5つの構造的な防御

| # | 防御 | どう実現しているか | 機械検査 |
|---|---|---|---|
| A | **リスト名で対象を特定しない** | 書き込み系RESTのURIはすべて `_api/web/lists(guid'<varCreatedListId>')` 形式。`GetByTitle('<名前>')` を一度も使わない | 定義中の `GetByTitle(` が **0件** |
| B | **書き込みは今回作成したリストにしか届かない** | 新規作成POST（`_api/web/lists`）を除く全POSTのURIに `variables('varCreatedListId')` が含まれる | 全POSTを走査して確認 |
| C | **作成は同名リストが無いときだけ** | `Create_Generic_List` は `varListExists == false` の Condition 配下にある | ガード文脈を走査して確認 |
| D | **初期化は今回作った物にだけ** | 初期化・ロールバックの12アクションすべてが `varCreatedInThisRun == true` の Condition 配下にある | 12件すべてのガード文脈を確認 |
| E | **確認は作成より先** | `Scope_Check_Existing_List` が `Scope_Create_List` より runAfter 順で前 | 位相順で位置を比較 |

Aが効いている限り、**リスト名を取り違えても既存リストは変更されません**。`varCreatedListId` は今回の作成応答からしか設定されず、作成が失敗すれば空のままだからです。

---

## 2. 同名リストの確認（§9）

```text
Get_All_Lists
  GET _api/web/lists?$select=Id,Title,Hidden,BaseTemplate,RootFolder/ServerRelativeUrl
      &$expand=RootFolder&$top=5000
  Accept: application/json;odata=nometadata
```

- **非表示リストも対象**です。`Hidden` で絞り込まず全件取得し、非表示の同名リストがあっても新規作成しません。
- `$top=5000` でサイト内のリストをまとめて取得します。

比較は `Filter_Matching_List_Names`（配列のフィルター処理）で行います。

```text
from  : @variables('varExistingLists')
where : @equals(toLower(trim(coalesce(item()?['Title'], ''))),
                toLower(trim(variables('varListName'))))
```

- **大文字・小文字だけが異なる名前も同一とみなします**（`toLower`）。
- **先頭・末尾の空白だけが異なる名前も同一とみなします**（`trim`）。
- 1件でも一致すれば `varListExists = true` となり、以降 `Scope_Create_List` の Condition が false になるため、作成も初期化も一切実行されません。

このとき返す結果は `status: "AlreadyExists"` / `created: false` / `success: true`（**正常終了**扱い）です。既存リストに対しては GET 以外を一度も呼びません。

---

## 3. 競合状態への対策（§10）

存在確認から作成までの間に、別の実行が同名リストを作る可能性があります。

```text
Create_Generic_List           POST _api/web/lists
Set_Create_Status_Code        runAfter: [Succeeded, Failed]  ← 失敗しても必ず実行
Condition_Create_Succeeded    HTTPステータスが 200〜299 か
  ├ true  : リストID・タイトルを保存し varCreatedInThisRun = true
  └ false : varStatus = 'AlreadyExistsOrConflict' / created = false で終了
```

**作成に失敗したら、そこで終わります。** 同名リストを取得し直して初期化する経路は定義に存在しません。

これは検査項目 F で機械的に保証しています — `Create_Generic_List` に対して `Failed` を含む `runAfter` を持つアクションが REST 呼び出しであってはならない、という走査です。現在この位置にあるのは `Set_Create_Status_Code`（変数への退避）だけです。

並列に2回実行された場合も、後発の実行は作成に失敗して `AlreadyExistsOrConflict` で終わるため、先発が作ったリストを初期化することはありません。

---

## 4. 初期化のガード（§12）

初期化系の5スコープは、いずれも先頭に同じ Condition を持ちます。

```text
Condition_*_Guard :
  varCreatedInThisRun == true  かつ  varIsValid == true
```

`varCreatedInThisRun` が `true` になるのは、`Create_Generic_List` が 2xx を返した直後の1箇所だけです。**既存リストの経路ではこの変数は `false` のまま**なので、初期化系のRESTは1本も発行されません。

ガード対象（機械検査で12件すべて確認）:

```text
Verify_Empty_List / Disable_Attachments / Deactivate_Title_Required
Get_All_List_Fields / Delete_Deletable_Field
Create_SampleRaw_Field / Verify_SampleRaw_Field
Get_Default_View / Remove_All_Default_View_Fields
Add_SampleRaw_To_Default_View / Verify_Default_View_Fields
Rollback_Newly_Created_List
```

---

## 5. 列削除の対象限定（§15・§17）

削除対象は `Filter_Deletable_Fields`（配列のフィルター処理）でのみ決まります。

```text
where : @and(equals(coalesce(item()?['CanBeDeleted'], false), true),
             not(equals(coalesce(item()?['InternalName'], ''), 'sample_raw')))
```

- **列名の固定リストは使いません。** SharePoint が返す `CanBeDeleted` の値だけで判定します。`Title` などの削除不能列を「名前が Title だから」という理由で削除しようとすることはありません。
- `CanBeDeleted=false` の列は削除せず、`varSkippedFields` に**制約として記録**します。

削除ループ `Apply_to_each_DeleteField` は**並列オフ**（`concurrency.repetitions = 1`）です。配列変数への追加順序の乱れと競合を避けるためで、機械検査で確認しています。

1件でも削除に失敗すると `varFieldDeleteErrors` に記録され、最終判定で `InitializationFailed` になります（**初期化全体を成功扱いにしません**）。

### 削除不能なシステム列について（正直な記載）

`Title` の必須解除（`Required=false`）だけは実施します（実働リファレンス `CreateKnowledgeList` の `deactivateSPOTitle` と同一形式）。

**新規作成／編集／表示フォームからの非表示化は実装していません。** `SetShowInNewForm` 等のRESTは本リポジトリに実在確認の証跡がなく、推測で実装することは禁止事項に当たるためです。指示書§17が許容するとおり、これらの列は「非表示化できなかった制約」として結果JSONの `initialization.skippedSystemFields` に記録します。**「非表示化できた」とは報告しません。**

利用者から見える**データ列**が `sample_raw` だけになっていれば目的は満たされます（既定ビューからは除外済みです）。

---

## 6. ロールバックの対象限定（§27）

初期化に失敗した場合、今回作成したリストだけを削除します。

```text
Condition_Rollback_Allowed :
  varCreatedInThisRun == true
  かつ varListExists == false          ← 存在確認時に無かった
  かつ length(varCreatedListId) > 0    ← 作成応答からIDを取得できた
  かつ varStatus != 'Created'          ← 初期化が完了していない

Rollback_Newly_Created_List :
  POST _api/web/lists(guid'<varCreatedListId>')
  X-HTTP-Method: DELETE / IF-MATCH: *
```

- **削除対象は `varCreatedListId` と完全一致するリストだけです。**
- **リスト名での再検索は行いません**（`GetByTitle` が定義に存在しないため、構造的に不可能です）。
- 4条件のいずれかが欠ければ削除は実行されず、`InitializationFailed` としてリストIDを報告します。

---

## 7. 権限不足の区別（§32）

権限の問題を「URL不正」や「同名リスト存在」として扱いません。HTTPステータスを変数へ退避し、専用のエラーコードに振り分けます。

| 状態 | 検出方法 | エラーコード |
|---|---|---|
| サイトを参照できない | `Verify_SharePoint_Web` が 401/403 | `ERR_PERMISSION_DENIED` |
| サイトが存在しない／URLがサイトURLでない | 同 404 | `ERR_SITE_OR_RESOURCE_NOT_FOUND` |
| リストを作成できない | `Create_Generic_List` が 403 | `ERR_CREATE_CONFLICT` ＋ `httpStatusCode=403` を `errors` に記録 |
| 列を作成できない／ビューを変更できない | 各 REST の失敗 → Catch | `ERR_PERMISSION_DENIED` ＋ `stage` で段階を特定 |
| リストを削除できない（ロールバック不可） | ロールバック失敗 | `rollbackPerformed: false` のまま `createdListId` を報告 |

ステータス退避は `runAfter: [Succeeded, Failed]` の SetVariable で行うため、**REST が失敗しても必ず実行**されます。エラーハンドラは変数だけを参照するので、未実行アクションを参照して自壊することがありません。

> **要実環境確認**: 権限不足時に SharePoint が 403 を返すか 404 を返すかはテナント設定に依存します。両方に対応する実装ですが、実際にどちらを通るかは未確認です。

---

## 8. エラー時も結果を返す（§29.3）

Scope を直列に連鎖させ、`Scope_Handle_Error` の `runAfter` は**直前の1本だけ**に張っています。

```text
… → Scope_Validate_Result → Scope_Handle_AlreadyExists
  → Scope_Handle_Error [Failed, Skipped, TimedOut]
  → Scope_Rollback_New_List [4状態]
  → Scope_Finalize [4状態]
```

複数の Scope を `runAfter` に列挙すると **AND 判定**になり、「前段成功・中段失敗」でハンドラが発火しません。直列連鎖なら途中で失敗した時点で後続がすべて `Skipped` になるため、最終 Scope の `Skipped` を見るだけで確実に捕捉できます。

結果JSONの組み立ては `Scope_Finalize` の1箇所に集約し、**すべての状態が確定した後**に行います。これにより `rollbackPerformed` も正しく反映されます。

---

## 9. 禁止事項への対応表（§31）

| 指示書§31 の禁止事項 | 対応 |
|---|---|
| 同名リストが存在する場合に既存リストを初期化する | `varCreatedInThisRun` ガードにより構造的に不可能。機械検査あり |
| 既存リストの列を削除する | 削除URIは `varCreatedListId` 固定。機械検査あり |
| 既存リストの既定ビューを変更する | ビュー操作URIも `varCreatedListId` 固定。機械検査あり |
| 既存リストのアイテムを削除する | アイテム削除アクションを実装していない（`ItemCount` の GET のみ） |
| 作成失敗後に同名リストを取得して初期化する | 作成失敗経路にREST呼び出しが無いことを機械検査 |
| リスト名だけを根拠にロールバック削除する | `GetByTitle` が0件。削除はID完全一致のみ |
| `CanBeDeleted=false` の列を強制削除する | `CanBeDeleted=true` のフィルタ経由のみ。機械検査あり |
| Title列を削除できる前提で実装する | Title は `CanBeDeleted=false` なので自動的に除外。必須解除のみ実施 |
| HTTPエラーを無視して次へ進む | ステータスを退避し、2xx以外は分岐で停止。失敗は Catch で捕捉 |
| URL内のサイト名を固定値にする | `dataset` は全アクションで `@variables('varSiteUrl')`。機械検査あり |
| 特定テナント専用のフローにする | 定義にサイトURLの実値0件。機械検査あり |
| リスト名をフロー定義へ固定する | リスト名はトリガー入力のみ由来 |
| 削除可能／不能を列名だけで判定する | `CanBeDeleted` プロパティのみで判定 |
| Set Variable で配列変数を自己参照する | 蓄積はすべて `AppendToArrayVariable`。自己参照0件を機械検査 |
| Apply to each で列削除を並列実行する | `concurrency.repetitions = 1`。機械検査あり |
| ZIPを検証せず完成扱いにする | `extract_check.py` で再展開・GUID一致・SHA-256一致まで確認 |
| Git操作 | 一切行っていない |

---

関連: [list_operations_spec.md](list_operations_spec.md) / [json_schema.md](json_schema.md) / [../tests/validation_report.md](../tests/validation_report.md)
