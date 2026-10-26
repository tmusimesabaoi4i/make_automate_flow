# テストケース

指示書§33 が要求する正常系14・同名確認5・異常系12 を網羅した一覧です。各ケースに確認方法と現在の確認状況を明記しています。

## 確認状況の凡例

| 記号 | 意味 |
|---|---|
| ✅ 静的検証済み | `tests/run_url_parse_tests.py` により、生成済み `definition.json` の式を実際に評価して確認済み（2026-07-24） |
| ✔ 実環境確認済み | **2026-07-24 の実環境実行（`status: Created`）または SharePoint 画面で確認済み** |
| 🔍 構造確認済み | 定義上その処理・ガードが存在することを `validate_list_flow.py` で確認済み。実データでの動作は未確認 |
| ⚠ 要実環境確認 | **まだ実機で通っていない。正常動作は断定していない** |

**重要**: 実環境で通ったのは**新規作成経路（`Created`）のみ**です。同名リスト経路と失敗経路（ロールバック・権限不足・競合）は未確認のままです。⚠ の項目はご自身の環境で確認してください。

---

## 1. 正常系（§33）

### 1-1. URL解析（オフラインで検証済み）

| # | 指示書の要求 | ケースID | 入力URL | 期待する `varSiteUrl` | 状況 |
|---|---|---|---|---|---|
| 1 | リスト一覧ページURLから新規リストを作成 | U01 | `.../sites/{site}/_layouts/15/viewlsts.aspx` | `.../sites/{site}` | ✅ |
| 2 | サイトルートURLから新規リストを作成 | U02 | `.../sites/{site}` | 同じ | ✅ |
| 3 | URL末尾に `/` がある | U03 | `.../sites/{site}/` | `.../sites/{site}` | ✅ |
| 4 | URLにクエリパラメーターがある | U04 | `.../viewlsts.aspx?view=14` | `.../sites/{site}` | ✅ |
| 5 | URLの前後に空白がある | U05 | `"   ...   "` | trim 後の値 | ✅ |
| — | サブサイト | U06 | `.../sites/{site}/subsite01/_layouts/...` | `.../sites/{site}/subsite01` | ✅ |
| — | サイトルート＋クエリのみ | U07 | `.../sites/{site}?foo=bar` | `.../sites/{site}` | ✅ |
| — | フラグメント付き | U08 | `.../viewlsts.aspx#top` | `.../sites/{site}` | ✅ |
| — | `_Layouts` の表記ゆれ | U09 | `.../_Layouts/15/viewlsts.aspx` | `.../sites/{site}` | ✅ |
| — | テナントルートサイト | U10 | `https://{tenant}.sharepoint.com` | 同じ | ✅ |
| — | 個別リストのビューURL（**対象外**） | U11 | `.../Lists/Existing/AllItems.aspx` | URL全体（実行時に404で失敗する） | ✅ |

### 1-2. リスト名（オフラインで検証済み）

| # | 指示書の要求 | ケースID | 入力 | 期待 | 状況 |
|---|---|---|---|---|---|
| 6 | 日本語のリスト名 | L01 | `サンプル台帳` | そのまま採用・エラーなし | ✅ |
| 7 | 英数字のリスト名 | L02 | `SampleList2026` | 同上 | ✅ |
| 8 | 空白を含むリスト名 | L03 | `Sample List 2026` | 同上 | ✅ |
| — | 前後の空白を除去して使用 | L04 | `"  SampleList  "` | `SampleList` | ✅ |
| — | ハイフン・アンダースコア | L05 | `sample-list_01` | そのまま採用 | ✅ |

### 1-3. 実データが必要なもの（実環境確認）

| # | 指示書の要求 | 確認方法 | 期待結果 | 状況 |
|---|---|---|---|---|
| 9 | `sample_raw` に通常テキストを保存 | 作成したリストに項目を追加 | 保存できる | **✔** |
| 10 | `sample_raw` にHTMLを保存 | `<b>太字</b>` 等を入力 | 書式が保持される | **✔** |
| 11 | `sample_raw` にアンカータグを保存 | `<a href="https://example.com">リンク</a>` | リンクとして機能する | **✔** |
| 12 | 既定ビューに `sample_raw` だけが表示される | 作成後にリストを開く | データ列が1列のみ | **✔** |
| 13 | 削除可能な不要列が残っていない | リスト設定 → 列 | `CanBeDeleted=true` の列が `sample_raw` 以外に無い | **✔** |
| 14 | 削除不能なシステム列が既定ビューに表示されない | 作成後にリストを開く | `Title` `ID` `Modified` 等が非表示 | **✔** |

> **2026-07-24 の実環境実行（`status: Created`）と SharePoint 画面での目視で確認済みです。**
>
> `status` が `Created` になるには `length(varFinalViewFields) == 1` かつ `first == 'sample_raw'` を満たす必要があるため、**`Created` が返った事実そのものが 12 の証拠**でもあります。同様に `varFieldDeleteErrors` が空であること（13）、`varSampleRawCreated == true`（`SchemaXml` に `RichTextMode="FullHtml"` を含むこと。10・11）も `Created` の前提条件です。

---

## 2. 同名確認（§33）

**すべてのケースで「既存リストが変更されていないこと」を確認してください。** これがこのフローの最重要の確認項目です。

| # | ケース | 確認方法 | 期待結果 | 状況 |
|---|---|---|---|---|
| 1 | 完全に同じリスト名が存在 | 既存リスト名を指定して実行 | `status: AlreadyExists` / `created: false` / `success: true`。`Create_Generic_List` がスキップ | ⚠（定義上は 🔍） |
| 2 | 大文字・小文字だけが異なるリストが存在 | 既存が `SampleList` のとき `samplelist` を指定 | 同上（`toLower` で同一視） | ⚠（定義上は 🔍） |
| 3 | 非表示の同名リストが存在 | 非表示リストと同名を指定 | 同上（`Hidden` で絞り込まないため検出される） | ⚠（定義上は 🔍） |
| 4 | ほぼ同時に2回実行 | 同じ入力で連続実行 | 後発は `AlreadyExists` または `AlreadyExistsOrConflict` | ⚠ |
| 5 | 存在確認後・作成前に別実行が同名リストを作成 | 意図的な再現は困難 | 作成が2xx以外 → `AlreadyExistsOrConflict` / `created: false`。**既存リストを取得しに行かない** | ⚠（定義上は 🔍） |

### 定義レベルで保証していること（`validate_list_flow.py` で確認済み・🔍）

| 保証 | 検査結果 |
|---|---|
| 定義に `GetByTitle(` が存在しない | **0件** |
| 書き込み系RESTのURIが `varCreatedListId` を含む（新規作成POSTを除く） | 全件 |
| `Create_Generic_List` が `varListExists == false` ガード配下 | 確認済み |
| 初期化・ロールバックの12アクションが `varCreatedInThisRun == true` ガード配下 | 12件すべて |
| 同名リスト確認がリスト作成より前 | `Scope_Check_Existing_List` < `Scope_Create_List` |
| 作成失敗経路にREST呼び出しが無い | 確認済み |

**ケース1〜3・5で既存リストが変更されないことは、実行時の振る舞いに依存せず定義の構造から保証されます。** ケース4（並列実行）だけは SharePoint 側の競合検出に依存するため実環境確認が必要です。

> **⚠ 実環境での確認状況（2026-07-24）**: 本節のケースは**1件も実機で発火していません**。今回通ったのは新規作成経路（`Created`）のみで、**同名リストが存在する状態での実行はしていません**。
>
> 既存リスト保護はこのフローの最重要機能です。`docs/installation.md` ステップ9（既存リスト名を指定 → `status: AlreadyExists` になること＋**既存リストが1文字も変わっていないこと**を目視）を**最優先で実施してください**。

---

## 3. 異常系（§33）

### 3-1. 入力検証（オフラインで検証済み）

| # | 指示書の要求 | ケースID | 入力 | 期待コード | 状況 |
|---|---|---|---|---|---|
| 1 | URLが空 | E01 | `""` | `ERR_URL_EMPTY` | ✅ |
| — | URLが空白のみ | E02 | `"    "` | `ERR_URL_EMPTY` | ✅ |
| 2 | リスト名が空 | N01 | `""` | `ERR_LIST_NAME_EMPTY` | ✅ |
| — | リスト名が空白のみ | N02 | `"   "` | `ERR_LIST_NAME_EMPTY` | ✅ |
| 3 | SharePoint以外のURL | E04 | `https://example.com/sites/x` | `ERR_NOT_SHAREPOINT_HOST` | ✅ |
| — | `http://`（非TLS） | E03 | `http://...sharepoint.com/sites/x` | `ERR_NOT_HTTPS` | ✅ |
| — | 紛らわしいホスト | E05 | `https://sharepoint.com.evil.example/...` | `ERR_NOT_SHAREPOINT_HOST` | ✅ |
| 7 | 不正なリスト名（禁止文字） | N03〜N06 | `Sample/List` / `Sample\List` / `Sample:List*` / `Sample"List` | `ERR_LIST_NAME_INVALID_CHARS` | ✅ |
| — | 不正なリスト名（制御文字） | N07・N08 | 改行・タブを含む | `ERR_LIST_NAME_INVALID_CHARS` | ✅ |
| — | 不正なリスト名（ピリオド） | N09・N10 | `.SampleList` / `SampleList.` | `ERR_LIST_NAME_INVALID_PERIOD` | ✅ |
| — | 予約名 | N11・N12 | `con` / `NUL` | `ERR_LIST_NAME_RESERVED` | ✅ |
| — | 長さ超過 | N13 | 256文字 | `ERR_LIST_NAME_TOO_LONG` | ✅ |
| — | URLもリスト名も不正 | P01 | 両方不正 | URL側のコードを優先 | ✅ |

いずれも**作成処理を開始する前に停止**します。SharePoint 側には何の変更も加わりません。

### 3-2. 実環境でのみ確認できるもの

| # | 指示書の要求 | 確認方法 | 期待コード | 状況 |
|---|---|---|---|---|
| 4 | 存在しないサイト | 実在しないサイト名のURLで実行 | `ERR_SITE_OR_RESOURCE_NOT_FOUND`（404） | ⚠ |
| 5 | 権限がないサイト | メンバーでないサイトのURLで実行 | `ERR_PERMISSION_DENIED`（403）または 404 | ⚠ |
| 6 | リスト作成権限がない | 閲覧権限のみのアカウントで実行 | `ERR_CREATE_CONFLICT` ＋ `httpStatusCode=403` | ⚠ |
| 8 | 列作成で失敗 | `sample_raw` 作成が失敗する状況 | stage=`CreateSampleRawField` のエラー → ロールバック | ⚠ |
| 9 | 列削除で失敗 | 削除できない列が `CanBeDeleted=true` を返す状況 | `ERR_FIELD_DELETE_FAILED` ＋ `varFieldDeleteErrors` に記録 | ⚠ |
| 10 | 既定ビュー取得で失敗 | `views` の GET が失敗する状況 | stage=`ConfigureDefaultView` のエラー | ⚠ |
| 11 | ViewFields初期化で失敗 | `removeAllViewFields()` が失敗する状況 | 同上 | ⚠ |
| 12 | `sample_raw` 追加後の検証で失敗 | `ViewFields` の応答形状が想定と異なる場合など | `ERR_VIEW_FIELDS_NOT_ONLY_SAMPLERAW` | ⚠ |

> 8〜12 のいずれでも、`varStatus` が `Created` にならないため**ロールバック（今回作成したリストのみ削除）が試みられます**。`rollbackPerformed` で結果を確認してください。
>
> **2026-07-24 の実環境実行は `Created` で完了したため、これら失敗経路とロールバックは一度も通っていません。** 特にロールバック（リスト削除）は未確認です。

---

## 4. パッケージ検証（実施済み）

| 観点（§36） | 確認方法 | 結果 |
|---|---|---|
| ZIPを正常に展開できる | `extract_check.py` | ✅ |
| 必須ファイルが存在する | 同上 | ✅ レガシー5ファイル構造 |
| JSONが構文エラーになっていない | 同上（全5ファイル） | ✅ |
| フロー名が正しい | 同上 | ✅ |
| 手動トリガーが存在する | `validate_list_flow.py` | ✅ manual / Button |
| URL入力が存在する | 同上 | ✅ `SharePointUrl`（必須） |
| リスト名入力が存在する | 同上 | ✅ `ListName`（必須） |
| SharePoint接続参照が存在する | 同上 | ✅ `shared_sharepointonline` のみ |
| 動的サイトURLが設定されている | 同上 | ✅ 全16アクションの `dataset` が `@variables('varSiteUrl')` |
| 同名リスト確認がリスト作成より前 | 同上 | ✅ 位相順で確認 |
| AlreadyExists分岐から作成処理へ進まない | 同上 | ✅ `varListExists == false` ガード |
| 既存リストを変更する処理がない | 同上 | ✅ `GetByTitle(` 0件・書き込みは全て `varCreatedListId` |
| 作成リストIDを保存している | 同上 | ✅ `Store_Created_List_Id` |
| 初期化が `varCreatedInThisRun=true` の場合だけ実行される | 同上 | ✅ 12アクションすべて |
| 列削除が `CanBeDeleted=true` だけを対象にしている | 同上 | ✅ フィルタ経由・列名リスト不使用 |
| `sample_raw` が拡張リッチテキストである | 同上 | ✅ SchemaXml をXMLパースして属性検証 |
| 既定ビューに `sample_raw` だけが設定される | 同上 | ✅ 定義上の検証式の存在を確認（実動作は⚠） |
| 配列変数の自己参照がない | 同上 | ✅ 0件（開発中に1件検出し修正） |
| Apply to each の並列処理が無効 | 同上 | ✅ 2ループとも `repetitions=1` |
| `runAfter` の参照先が存在する | 同上 | ✅ 全件が同一コンテナの兄弟 |
| 不正な式を使用していない | 同上 | ✅ 不正な `@` 0件・関数許可リスト外0件 |
| 存在しないSharePointアクションを使用していない | 同上 | ✅ `HttpRequest` のみ |
| 接続参照とマニフェストが一致する | 同上 ＋ `extract_check.py` | ✅ GUID3点一致 |

---

## 5. 再実行方法

```powershell
cd projects/create_initialized_sharepoint_list
python tests/run_url_parse_tests.py                                # 35件
python flows/create-initialized-list/source/validate_list_flow.py  # 静的検証
python flows/create-initialized-list/validation/extract_check.py   # ZIP再展開
```

テストケースを追加する場合は `tests/run_url_parse_tests.py` の `CASES` に
`(ID, 説明, SharePointUrl, ListName, 期待値dict)` を追記してください。

---

関連: [validation_report.md](validation_report.md) / [../docs/safety_mechanisms.md](../docs/safety_mechanisms.md) / [../docs/troubleshooting.md](../docs/troubleshooting.md)
