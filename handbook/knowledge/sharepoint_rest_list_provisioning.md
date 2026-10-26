# SharePoint REST によるリスト自動作成パターン集 (SharePoint REST List Provisioning Patterns)

Power Automateから SharePoint REST（`_api/web/lists`系）を呼び出し、リスト・列・ビューをフロー実行時に自動作成するための再利用可能なパターン集。リスト作成の半冪等化・列作成の冪等化・ビュー再構築・定数保持の4点が要点。

区分: 実働サンプル確認＋**2026-07-24 に実環境で実行確認済み**（create_initialized_sharepoint_list 案件。§11・§12 参照）。

実値は書かず `{siteUrl}` `{listName}` `{fieldName}` 等のプレースホルダーを使う。日本語名・英語名は併記する。

## 1. リスト作成（作成 / Create list）
```
Method: POST
Uri:    _api/web/lists
Headers: {"Accept": "application/json;odata=verbose", "Content-Type": "application/json;odata=verbose"}
Body:
{"__metadata": {"type": "SP.List"}, "AllowContentTypes": true, "BaseTemplate": 100, "ContentTypesEnabled": true, "Title": "{listName}"}
```
- 【事実】`BaseTemplate:100` はカスタムリスト（汎用リスト）。`odata=verbose` は `__metadata` を含めるため必須。

## 2. 半冪等パターン（作成失敗でも継続）【本案件の改善】
- 【推奨】リスト作成の直後（リストIDを取得するGetByTitleアクション）の `runAfter` を4状態すべてにする。

  ```
  runAfter: { "Create_{listName}List": ["Succeeded", "Skipped", "Failed", "TimedOut"] }
  ```

  リストが既存で作成が失敗しても、後続のGetByTitleで既存リストを取得し処理を継続できる（削除して作り直さない）。
- 【運用注記】2周目以降の実行では、リスト作成アクションが失敗表示のままでもフロー全体は **Succeeded** になる。「作成失敗＝異常」と誤解しないよう運用者へ周知する。

## 3. リストID取得（Get list by title）
```
Method: GET
Uri:    _api/web/lists/GetByTitle('{listName}')?$select=Id,Title&$expand=RootFolder
Headers: {"Accept": "application/json;odata=nometadata"}
```
- IDはComposeで保持: `@trim(string(body('Get_{listName}List')?['Id']))`

## 4. 列作成（createFieldAsXml）
```
Method: POST
Uri:    _api/web/lists/GetByTitle('{listName}')/fields/createFieldAsXml
Headers: {"Accept": "application/json;odata=verbose", "Content-Type": "application/json;odata=verbose"}
Body:
{"parameters": {"__metadata": {"type": "SP.XmlSchemaFieldCreationInformation"}, "Options": 0, "SchemaXml": "<Field .../>"}}
```
- 【事実】`Options:0` では内部名（InternalName）が表示名（DisplayName）から自動生成される。日本語表示名だと内部名がUnicodeエスケープ（`OData__xHHHH_`形式）になり、後続の`$filter`や参照が壊れやすい。実働サンプルは表示名でFilterして実InternalNameをその都度引く回避策を取っていた。
- 【推奨】`DisplayName=Name=ASCII`（半角英数字）にすれば内部名は指定名と一致し安定する。日本語で見せたい場合は別途表示名変更を検討する。
- 型別SchemaXml例（型に無関係な属性は混ぜない）:
  ```
  Text  : <Field Type="Text"  DisplayName="{fieldName}" Name="{fieldName}" Required="FALSE" MaxLength="255" />
  Note  : <Field Type="Note"  DisplayName="{fieldName}" Name="{fieldName}" Required="FALSE" RichText="FALSE" NumLines="6" />
  Number: <Field Type="Number" DisplayName="{fieldName}" Name="{fieldName}" Required="FALSE" />
  ```
  - Note型はMaxLength=255超（URL等）の対策に使う。**OData `$filter` 不可**な点に注意。
  - Number型は`Decimals`未指定で自動判定。

## 5. 列作成の冪等化【本案件の改善・参照フローに無い】
参照フローには存在しない改善。列を作る前に存在確認し、無いときだけ作成する。
1. `Get_{listName}Fields`: `GET .../fields?$select=Title,InternalName,TypeAsString`（`odata=nometadata`）
2. `Filter_{listName}_{fieldName}`（Filter array）: `from = @coalesce(body('Get_{listName}Fields')?['value'], json('[]'))`、`where = @equals(coalesce(item()?['InternalName'], ''), '{fieldName}')`
3. `If_Create_{listName}_{fieldName}`（If）: 条件式 `@equals(length(body('Filter_{listName}_{fieldName}')), 0)`（整数比較。実環境インポート実績のある形）
4. 条件成立時（0件＝未作成）のときだけ createFieldAsXml を実行する。**既存列の削除・再作成はしない。**

## 6. ビュー再構築（既定ビューの列を組み直す）
1. `removeAllViewFields`: `POST .../defaultView/viewfields/removeAllViewFields()`（`odata=nometadata`・ボディなし）
2. 列一覧を再取得（`Get_{listName}FinalFields`、手順3と同じGET）
3. `AddViewField`: 列ごとに1回

  ```
  Method: POST
  Uri:    _api/web/lists/GetByTitle('{listName}')/defaultView/viewfields/AddViewField('{internalName}')
  Headers: {"Accept":"application/json;odata=verbose","Content-Type":"application/json;odata=verbose","IF-MATCH":"*","X-HTTP-Method":"MERGE"}
  Body:   {"__metadata": {"type": "SP.View"}, "SetAsDefaultView": true}
  ```

- 【事実】タイトル列の再追加は `Title` ではなく **`LinkTitle`**（リンク・メニュー付き）で行う。
- システム列（`Author` / `Editor` / `Created` / `Modified`）も同じ`AddViewField`で追加できる。
- 手順4で内部名が化ける場合は、Filter＋Compose（`ComposeInternalName_...`）で表示名から実InternalNameを引いてから渡す。

## 7. Title列のRequired解除【必要な場合のみ】
```
Method: POST
Uri:    _api/web/lists/GetByTitle('{listName}')/fields/getbyinternalnameortitle('Title')
Headers: {"Accept":"application/json;odata=nometadata","Content-Type":"application/json;odata=nometadata","IF-MATCH":"*","X-HTTP-Method":"MERGE"}
Body:   {"Required": false}
```
利用側が項目作成時に常にTitleへ書き込むフロー設計なら不要。

## 8. EnableAttachments（添付ファイルの許可）【必要な場合のみ】
```
Method: POST
Uri:    _api/web/lists/GetByTitle('{listName}')
Headers: {"Accept":"application/json;odata=verbose","Content-Type":"application/json;odata=verbose","IF-MATCH":"*","X-HTTP-Method":"MERGE"}
Body:   {"__metadata": {"type": "SP.List"}, "EnableAttachments": true}
```
利用実績が無ければ実施しない。

## 9. 定数はComposeで保持する（SetVariableにしない）
- 【推奨】リスト名・リストIDなど使い回す定数は「変数を設定する」(SetVariable) ではなく **Compose** で保持する。
  ```
  Compose_{listName}ListTitle: 入力 = "{listName}"
  ```
  以降は `outputs('Compose_{listName}ListTitle')` で参照する。SetVariableは更新式が自身の変数を参照すると保存エラーになる（[03 変数・配列](../rules/03_variables_arrays_and_objects.md)、[エラーカタログ](error_catalog.md)）。Composeで保持すればこの自己参照事故を**構造的に**排除できる。

## 10. フォルダ作成REST（半冪等パターンの応用）
```
Method: POST
Uri:    _api/web/folders
Headers: {"Accept": "application/json;odata=verbose", "Content-Type": "application/json;odata=verbose"}
Body:   {"__metadata": {"type": "SP.Folder"}, "ServerRelativeUrl": "{sitePath}/{library}/{segments}"}
```
- 【推奨】1階層ずつ作成し`runAfter=[Succeeded,Failed]`で継続する（§2の半冪等パターンと同型の適用）。
  最後に`GET .../GetFolderByServerRelativeUrl('{fullPath}')`で実在検証する（作成失敗を握り潰さない）。
- 【事実・アンチパターン】`ServerRelativeUrl`は**フルサーバー相対**（テナントルート基準）で渡す。
  「ファイルの作成」(CreateFile) は中間フォルダを自動作成しないため、保存前にこのパターンで確保する
  （[../rules/05_sharepoint_and_teams_patterns.md](../rules/05_sharepoint_and_teams_patterns.md) /
  [error_catalog.md](error_catalog.md)参照）。

## 11. サイトを実行時に決める（dataset を式にする）【事実】
- 【事実】「SharePoint に HTTP 要求を送信」(`operationId=HttpRequest`) の `dataset`（サイトのアドレス）に
  **式（`@variables('varSiteUrl')` 等）を指定した状態で保存・実行できる**。
  確認日: 2026-07-24 / 根拠: create_initialized_sharepoint_list を実環境でインポート・実行し成功（16アクション全てが式指定）。
- 【背景】`PostItem`（項目の作成）は必須の動的ボディ `item` を持つため `dataset`/`table` が式だと保存に失敗する
  （[error_catalog.md](error_catalog.md)）。`HttpRequest` は動的ボディを持たないためこの制約を受けない。
  従来は演繹だったが、上記で実証された。
- 【推奨】任意サイトを対象にするフローでは、URLから抽出したサイトURLを変数に入れて `dataset` に渡す。
  サイトURLをフロー定義へ固定しない。

## 12. リストIDで対象を特定する（既存リストの誤操作を防ぐ）【推奨・実証済み】
- 【事実】次のRESTは、リスト名ではなく**リストIDで対象を指定**して動作する。
  確認日: 2026-07-24 / 根拠: create_initialized_sharepoint_list の実環境実行（`status: Created`）。

  **以下は実環境で成功した `definition.json` からの逐語コピー。`{listId}` `{viewId}` `{fieldId}`
  `{name}` `{internalName}` 以外は1文字も省略していない。** クエリを短くして使わないこと（理由は §15）。

  ```
  GET  _api/web?$select=Id,Title,Url                                   サイト疎通・参照権限の確認
  GET  _api/web/lists?$select=Id,Title,Hidden,BaseTemplate,RootFolder/ServerRelativeUrl&$expand=RootFolder&$top=5000
  GET  _api/web/lists(guid'{listId}')?$select=Id,Title&$expand=RootFolder
  GET  _api/web/lists(guid'{listId}')/ItemCount                        応答は {"value": 0} 形
  GET  _api/web/lists(guid'{listId}')/fields?$select=Id,Title,InternalName,StaticName,CanBeDeleted,Hidden,ReadOnlyField,Sealed,FromBaseType,Required,TypeAsString
  POST _api/web/lists(guid'{listId}')/fields(guid'{fieldId}')/deleteObject()     列削除（ボディなし）
  POST _api/web/lists(guid'{listId}')/fields/createFieldAsXml
  GET  _api/web/lists(guid'{listId}')/fields/getbyinternalnameortitle('{name}')?$select=Id,Title,InternalName,StaticName,TypeAsString,Required,Hidden,ReadOnlyField,SchemaXml
  GET  _api/web/lists(guid'{listId}')/views?$select=Id,Title,DefaultView,Hidden,ViewType,RowLimit
  POST _api/web/lists(guid'{listId}')/views(guid'{viewId}')/viewfields/removeAllViewFields()
  POST _api/web/lists(guid'{listId}')/views(guid'{viewId}')/viewfields/AddViewField('{internalName}')
  GET  _api/web/lists(guid'{listId}')/views(guid'{viewId}')/ViewFields   応答は {"Items": [...]} 形
  ```

- 【事実】ビュー操作は `defaultView/viewfields/...`（暗黙指定）だけでなく
  **`views(guid'{viewId}')/viewfields/...`（明示指定）でも動作する**。
- 【事実】既定ビューは**ビュー名ではなく `DefaultView` プロパティ**で特定する。
  「すべてのアイテム」「All Items」といった表示名を前提にしない。
- 【推奨】**破壊的操作（列削除・ビュー変更・リスト削除）のURIには必ずリストIDを使う。**
  `GetByTitle('{listName}')` を使うと、名前の取り違えで既存リストを壊しうる。
  検証スクリプトで「定義中に `GetByTitle(` が0件」「書き込み系URIに `{listId}` 変数を含む」を機械確認できる
  （実装例: `projects/create_initialized_sharepoint_list/flows/create-initialized-list/source/validate_list_flow.py`）。

## 13. 拡張リッチテキスト列（HTML・ハイパーリンク格納）【事実】
- 【事実】次の Field XML で、HTML とアンカータグ（`<a href="...">`）を保持できる複数行テキスト列を作成できる。
  確認日: 2026-07-24 / 根拠: create_initialized_sharepoint_list の実環境実行＋SharePoint画面での保存確認。

  ```xml
  <Field Type="Note" Name="{fieldName}" StaticName="{fieldName}" DisplayName="{fieldName}"
         Required="FALSE" NumLines="12" RichText="TRUE" RichTextMode="FullHtml"
         IsolateStyles="TRUE" RestrictedMode="FALSE" AppendOnly="FALSE" />
  ```

- 【事実】作成後の検証は
  `getbyinternalnameortitle('{fieldName}')?$select=Id,Title,InternalName,StaticName,TypeAsString,Required,Hidden,ReadOnlyField,SchemaXml`
  で行い、
  `TypeAsString == 'Note'` と `SchemaXml` に `RichTextMode="FullHtml"` を含むことを確認する。
- 【推奨】`DisplayName`=`Name`=**ASCII** にすれば内部名が指定どおりになる（§4参照）。

## 14. RESTボディは Compose オブジェクト＋`string()` で作る【推奨・実証済み】
- 【事実・アンチパターン】ボディを文字列連結で組み立てると、値に `"` 改行 `\` が含まれたときにJSONが壊れる。
- 【推奨】Compose で**オブジェクト**を組み立て、`parameters/body` に `@string(outputs('Compose_X'))` を渡す。
  `string()` が正しくエスケープするため、リスト名・説明・SchemaXml に特殊文字があっても壊れない。
  確認日: 2026-07-24 / 根拠: create_initialized_sharepoint_list の全RESTボディがこの方式で実環境動作。

## 15. `$expand` は `$select` に投影を書く／実証済みの形を短くしない【事実・実発生・修正実証済み】

- 【事実】**コレクション列挙で `$expand=RootFolder` を投影なしで書くと 403 になる**。
  SharePoint はナビゲーション先の全プロパティを実体化しようとし、
  アクセス権の無いリスト（カタログ等のシステムリスト）に当たって Access denied を返す。

  ```text wdl-lint:ignore
  # 403 になる（$select に RootFolder の投影が無い）
  _api/web/lists?$select=Id,Title,Hidden,BaseTemplate&$expand=RootFolder&$top=5000

  # 正（実環境で成功している形。§12 の逐語コピー）
  _api/web/lists?$select=Id,Title,Hidden,BaseTemplate,RootFolder/ServerRelativeUrl&$expand=RootFolder&$top=5000
  ```

- 【事実】**単一リソース**（`lists(guid'{listId}')` / `GetByTitle('{name}')`）への `$expand` は
  投影が無くても動く。実環境で成功した3実装がいずれも `?$select=Id,Title&$expand=RootFolder` で動作している。
  **危険なのはコレクション列挙のときだけ。**
- 【教訓・実発生】2026-08-03、本ファイル §12 の `$select=Id,Title,Hidden,` + 省略記号 という
  **`...` で省略された記載**を「そのまま使える形」と誤読し、`...` を自分の必要な列で埋め直した結果、
  元々あった `RootFolder/ServerRelativeUrl` を落として 403 を出した。
  → **要約は索引であって正典ではない。REST は必ず実証済みの `definition.json` から逐語コピーする。**
  §12 は逐語コピーに直し、`...` を排除した。
- 【事実】投影を足した形で **2026-08-03 に実環境の再実行に成功**した（403 解消）。
- 【推奨】機械検査で閉じる。`tools/wdl_lint.py` の **L04** が
  「コレクション列挙で `$expand=X` があるのに `$select` に `X/` の投影が無い」を検出する。

## 16. リストアイテムの作成・更新（REST）【実証済み】

動的なリストへ項目を作る場合、`PostItem`（項目の作成）は使えない（`dataset`/`table` を式にすると
保存に失敗する。[error_catalog.md](error_catalog.md)）。REST で行う。

### 事前にリストの型名を取得する

```
GET  _api/web/lists(guid'{listId}')?$select=Id,Title,ListItemEntityTypeFullName,RootFolder/ServerRelativeUrl&$expand=RootFolder
```

`ListItemEntityTypeFullName`（例 `SP.Data.MyListListItem`）を変数へ保持し、
以降のボディの `__metadata.type` に使う。テナントによって `__metadata` の型指定を要求される差異を
**構造的に回避**できる（推測で `odata=nometadata` に賭けない）。

### 作成

```
POST _api/web/lists(guid'{listId}')/items
Headers: {"Accept": "application/json;odata=verbose", "Content-Type": "application/json;odata=verbose"}
Body:    @string(outputs('Compose_Item_Body'))

Compose_Item_Body = {"__metadata": {"type": "@variables('varListEntityType')"},
                     "<内部名>": "<値の式>", ...}
```

### 更新（MERGE）

```
POST _api/web/lists(guid'{listId}')/items({itemId})
Headers: verbose ＋ "IF-MATCH": "*" ＋ "X-HTTP-Method": "MERGE"
Body:    @string(outputs('Compose_Update_Body'))   ※ 更新したい列だけ。他の列は消えない
```

- 【事実】**実環境で実証済み**（2026-08-03 / sync-shared-mailbox-to-sharepoint-list）。
  1回の実行で **作成80件・更新20件・失敗0件**。
- 【事実】日付列に値が無い場合は `null` を渡す（空文字を日付列に入れない）。
  `@if(empty(outputs('Compose_X')), null, outputs('Compose_X'))`。
- 【事実】重複判定は `$filter` ＋ 2段エスケープ
  （[expression_examples.md §16](expression_examples.md)）。
- 【推奨】0件→作成 / 1件→更新 / **2件以上→書き込まず記録**、の3分岐にする。
  検索が**失敗**したときは「0件」と誤認せず書き込みを見送る（重複作成の原因になる）。
- 【事実】100件（SharePoint REST 約250回＋Content Conversion 100回）が
  調整制限・実行時間上限に触れず完走した（2026-08-03）。

## パッケージ化する場合の注意
本パターンをレガシーZIPで配布する場合のGUID一致要件（3点一致）は[../rules/07_export_import_package_rules.md](../rules/07_export_import_package_rules.md)を参照。
接続参照は Invoker形式＋匿名GUIDで、**SharePointコネクタでも実接続へ再マッピングされることを実環境で確認済み**（2026-07-24）。

---
関連: [../rules/05_sharepoint_and_teams_patterns.md](../rules/05_sharepoint_and_teams_patterns.md) / [../rules/07_export_import_package_rules.md](../rules/07_export_import_package_rules.md) / [error_catalog.md](error_catalog.md)
