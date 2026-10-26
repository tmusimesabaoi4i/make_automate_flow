# トラブルシューティング

症状から原因と対処を引くための一覧です。

---

## 1. エラーコード別の対処

`Compose_Flow_Output` の `resultObject.errors[]` に出たコードから引いてください。

### 入力検証（リストは作成されていません）

| コード | 原因 | 対処 |
|---|---|---|
| `ERR_URL_EMPTY` | URLが空 | URLを入力する |
| `ERR_NOT_HTTPS` | `https://` で始まらない | `http://` ではなく `https://` のURLを使う |
| `ERR_NOT_SHAREPOINT_HOST` | ホスト名が `.sharepoint.com` で終わらない | SharePoint のURLか確認する。ブラウザのアドレスバーからコピーし直す |
| `ERR_SITE_URL_NOT_EXTRACTED` | サイトURLを抽出できない | URLを途中で切っていないか確認する |
| `ERR_LIST_NAME_EMPTY` | リスト名が空（trim 後） | リスト名を入力する（空白だけは不可） |
| `ERR_LIST_NAME_TOO_LONG` | 255文字超 | 短くする |
| `ERR_LIST_NAME_INVALID_CHARS` | 禁止文字・制御文字を含む | `" # % * : < > ? / \ | { } ~` とタブ・改行を除く |
| `ERR_LIST_NAME_INVALID_PERIOD` | 先頭/末尾がピリオド | ピリオドを外す |
| `ERR_LIST_NAME_RESERVED` | 予約名 | 別の名前にする（`con` `nul` `forms` 等は使えません） |

いずれも**作成処理を開始する前に停止**しています。SharePoint 側には何の変更も加わっていません。

### サイト・権限

| コード | 原因 | 対処 |
|---|---|---|
| `ERR_PERMISSION_DENIED`（401） | 接続の認証が切れている | Power Automate の「接続」画面で SharePoint 接続を修正、または削除して作り直す |
| `ERR_PERMISSION_DENIED`（403） | 対象サイトへのアクセス権が無い | 接続を作成したアカウントが対象サイトのメンバーか確認する。リスト作成には「編集」以上の権限が必要 |
| `ERR_SITE_OR_RESOURCE_NOT_FOUND`（404） | サイトが存在しない／URLがサイトURLでない | §2 を参照 |
| `ERR_BAD_REQUEST`（400） | 要求が不正 | `Verify_SharePoint_Web` の「入力」で `dataset` の実値を確認する |

### 作成・初期化

| コード | 原因 | 対処 |
|---|---|---|
| `ERR_CREATE_CONFLICT` | 作成が 2xx 以外 | `errors[]` の `httpStatusCode` を見る。403 なら権限不足、409/400 なら競合または名前の問題 |
| `ERR_LIST_NOT_EMPTY` | 作成直後なのにアイテムがある | 想定外。実行履歴で `Verify_Empty_List` の出力を確認する |
| `ERR_FIELD_DELETE_FAILED` | 列削除に1件以上失敗 | `varFieldDeleteErrors` の `internalName` と `httpStatusCode` を確認する |
| `ERR_SAMPLERAW_VERIFICATION_FAILED` | `sample_raw` の検証に失敗 | §5 を参照 |
| `ERR_DEFAULT_VIEW_NOT_FOUND` | `DefaultView=true` のビューが無い | `Get_Default_View` の出力を確認する |
| `ERR_VIEW_FIELDS_NOT_ONLY_SAMPLERAW` | 既定ビューの列が `sample_raw` だけになっていない | §6 を参照 |

---

## 2. `ERR_SITE_OR_RESOURCE_NOT_FOUND`（404）が出る

確度の高い順:

1. **個別リストのビューURLを入れた。** `.../Lists/<名前>/AllItems.aspx` は `/_layouts/` を含まないため、URL全体がサイトURLとして扱われます。→ サイトのトップページか `.../_layouts/15/viewlsts.aspx` のURLを使ってください。
2. **サイトが存在しない、または名前が違う。** ブラウザで `varSiteUrl` の値をそのまま開いて確認してください。
3. **アクセス権が無い（テナント設定によっては 403 ではなく 404 が返る）。** 対象サイトをブラウザで開けるか確認してください。

切り分けは `Parse_SiteUrl` と `Verify_SharePoint_Web` の「入力」で、抽出されたサイトURLの実値を見るのが最短です。

---

## 3. 保存時に「サイトのアドレス」関連のエラーが出る

> **配布状態では発生しません。** 全16アクションの「サイトのアドレス」に式（`@variables('varSiteUrl')`）を指定した状態で、**2026-07-24 に実環境でインポート・保存・実行できることを確認済み**です。`HttpRequest` は必須の動的ボディを持たないため `dataset` が式でも保存検証を通る、という `handbook/knowledge/error_catalog.md` の記述が実証されました。
>
> 以下はデザイナーで手を加えた後に発生した場合の切り分け手順です。

**症状**: フローを保存しようとすると SharePoint アクションのパラメータ検証でエラーになる。

**切り分け**:

1. エラーメッセージにアクション名が出ます。そのアクションをデザイナーで開き、「サイトのアドレス」欄が式になっているか確認してください。
2. 試しに1つのアクションだけ「サイトのアドレス」をドロップダウンから静的に選び、保存できるか確認します。
   - **保存できた** → 式指定が原因です。この場合、フローの目的（任意サイトへの作成）を保つには「サイトのアドレス」をカスタム値として受け付けさせる必要があります。デザイナーで「カスタム値の入力」を選び、式を貼り直してください。
   - **保存できない** → 別の原因です。エラーコードを `handbook/knowledge/error_catalog.md` の索引で引いてください。
3. どうしても式指定が通らない環境では、**サイトを固定した運用**（`dataset` を静的値にし、リスト名だけを可変にする）へ設計変更が必要です。その場合は `source/build_list_flow.py` の `DATASET` 定数を書き換えて再生成してください（`validate_list_flow.py` の `dataset` 検査も併せて緩める必要があります）。

**この結果は必ず記録してください。** 実環境で確認できれば、`handbook` の該当記述を「演繹」から「事実」または「反証」に更新できます。

---

## 4. 既存リストが変更されていないか不安なとき

このフローは既存リストに対して **GET 以外を発行しません**。確認方法:

1. 実行履歴で `Scope_Create_List` を開き、`Create_Generic_List` が**スキップ**になっていることを確認します。
2. `Scope_Initialize_List` 以降の各スコープで、中の処理がすべてスキップされていることを確認します。
3. `Compose_Flow_Output` の `status` が `AlreadyExists` であることを確認します。

定義レベルの保証は `python flows/create-initialized-list/source/validate_list_flow.py` で再確認できます。次がすべて0件・全件合格であることが出力されます。

```text
GetByTitle( の出現            : 0
書き込みRESTのID指定          : 新規作成を除き全件 varCreatedListId 使用
初期化ガード配下のアクション  : 12 件すべて varCreatedInThisRun 配下
同名確認→作成の順序           : Scope_Check_Existing_List < Scope_Create_List
```

---

## 5. `sample_raw` の検証に失敗する

`Verify_SampleRaw_Field` の出力を開き、どの条件が外れているか確認してください。

| 条件 | 期待 | 外れる原因 |
|---|---|---|
| `InternalName` | `sample_raw` | 同名の列が既にあり連番が付いた（作成直後のリストでは通常起きない） |
| `Required` | `false` | SchemaXml の `Required="FALSE"` が反映されていない |
| `Hidden` | `false` | — |
| `TypeAsString` | `Note` | SchemaXml の `Type="Note"` が反映されていない |
| `SchemaXml` に `RichTextMode="FullHtml"` | 含む | 拡張リッチテキストが有効になっていない |

`Create_SampleRaw_Field` の「入力」で送信した `SchemaXml` の実値を確認し、`Verify_SampleRaw_Field` の出力と突き合わせてください。

---

## 6. 既定ビューに `sample_raw` 以外が残る

1. `Remove_All_Default_View_Fields` が成功しているか確認します。
2. `Verify_Default_View_Fields` の出力の形を確認します。

> `ViewFields` の応答形状（`{"Items": ["sample_raw"]}` を `body(...)?['Items']` で読む）と、`views(guid'..')/viewfields/...` という guid 指定のパス形式は、**いずれも 2026-07-24 の実環境実行で確認済み**です。配布状態では発生しません。
>
> 万一この症状が出た場合、**ビュー自体は正しく設定できている**可能性があります（SharePoint 画面で確認してください）。その場合は検証式の参照パスを `source/build_list_flow.py` の `Store_Final_View_Fields` で調整し、再生成してください。パス形式が受け付けられない環境では `view_uri()` を `list_uri("/defaultView")` ベースに変更する回避策もあります。

---

## 7. 初期化に失敗し、中途半端なリストが残った

`status: "InitializationFailed"` のとき、`rollbackPerformed` を確認してください。

| `rollbackPerformed` | 意味 | 対処 |
|---|---|---|
| `true` | 今回作成したリストを削除できた | 不要な残骸はありません。原因を直して再実行してください |
| `false` | 削除できなかった | `createdListId` のリストが残っています。SharePoint 画面で手動削除してください |

ロールバックが実行されない条件（**安全のための制限**）:

```text
varCreatedInThisRun == true         今回の実行で作成した
かつ varListExists == false          存在確認時には無かった
かつ varCreatedListId が非空          作成応答からIDを取得できた
かつ varStatus != 'Created'          初期化が完了していない
```

1つでも満たさなければ削除しません。**リスト名での検索削除は行いません**（既存リストの誤削除を防ぐため）。

---

## 8. インポート時のエラー

### 「パッケージのインポート (レガシー)」が見つからない

「インポート」ボタンの選択肢を確認してください。テナントのバージョンにより「レガシーのインポート」等の表記になります。「ソリューションのインポート」では本ZIPは取り込めません。

### `'@' at position … is not expected`

式のネスト関数に `@` が付いている場合に出ます。**本パッケージは `validate_list_flow.py` の「不正な `@` 位置検査」で0件を確認済み**のため、配布状態では発生しないはずです。デザイナーで手動編集した後に発生した場合は、編集した式から余分な `@` を除いてください。

### `Self reference is not supported`（保存時）

「変数を設定する」の値式が自分自身を参照している場合に出ます。**本パッケージは自己参照0件を機械検証済み**です（開発中に1件検出し、Compose を挟んで解消しました）。手動でアクションを追加した場合は、蓄積を `AppendToArrayVariable` に置き換えてください。

---

## 9. 開発側での再検証

```powershell
cd projects/create_initialized_sharepoint_list

python flows/create-initialized-list/source/build_list_flow.py
python flows/create-initialized-list/source/validate_list_flow.py     # errors 0 / warnings 0 が条件
python tests/run_url_parse_tests.py                                   # 35件合格が条件

python ../../tools/gen_outline.py flows/create-initialized-list/source/package/Microsoft.Flow/flows/<GUID>/definition.json flows/create-initialized-list/validation/action_outline.txt
python ../../tools/pack_package.py flows/create-initialized-list/source/package flows/create-initialized-list/release/CreateInitializedSharePointList_<YYYYMMDDHHMMSS>.zip
python flows/create-initialized-list/validation/extract_check.py
```

**`definition.json` を直接編集しないでください。** 生成物です（`CLAUDE.md` 不変則1）。

---

関連: [safety_mechanisms.md](safety_mechanisms.md) / [json_schema.md](json_schema.md) / [list_operations_spec.md](list_operations_spec.md) / `handbook/knowledge/error_catalog.md`
