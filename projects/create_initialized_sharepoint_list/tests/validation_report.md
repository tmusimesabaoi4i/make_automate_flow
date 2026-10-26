# 検証レポート

- 対象: `CreateInitializedSharePointList`
- 検証日: **2026-07-24**
- 検証ZIP: `flows/create-initialized-list/release/CreateInitializedSharePointList_20260724211020.zip`

## 総括

| 区分 | 結果 |
|---|---|
| 静的検証（構造・式・参照整合・**安全要件**） | **エラー0 / 警告0** |
| URL解析・リスト名検証のオフライン検証 | **35件中35件合格** |
| ZIP再展開検査 | **エラー0** |
| **実環境でのインポート** | **成功**（2026-07-24・利用者報告） |
| **実環境での実行** | **成功**（`status: Created`。2026-07-24・利用者報告） |
| SharePoint画面での確認 | **既定ビューが `sample_raw` の1列だけ／不要な列が消えている／`sample_raw` にHTML・リンクを保存できた** |

**新規作成から初期化完了までの主経路が実環境で通りました。** これにより §5 に挙げていた未確認RESTの大半が実証されています（§5-0 参照）。

ただし、**同名リストが存在する場合の経路（`AlreadyExists`）は実機で発火していません。** このフローの最重要の安全機構がその経路にあるため、依然として最優先の残課題です（§5-1）。

---

## 1. 実行した検証コマンドと結果

```powershell
cd projects/create_initialized_sharepoint_list
python flows/create-initialized-list/source/build_list_flow.py
python flows/create-initialized-list/source/validate_list_flow.py
python tests/run_url_parse_tests.py
python ../../tools/gen_outline.py <definition.json> <validation/action_outline.txt>
python ../../tools/pack_package.py <source/package> <release/*.zip>
python flows/create-initialized-list/validation/extract_check.py
```

出力の全文は次に保存しています。

| 証跡 | パス |
|---|---|
| 静的検証 | `flows/create-initialized-list/validation/validate_result.txt` |
| アクションアウトライン（176件） | `flows/create-initialized-list/validation/action_outline.txt` |
| ZIP再展開検査 | `flows/create-initialized-list/validation/extract_check_result.txt` |
| URL解析・リスト名テスト | `tests/url_parse_test_result.txt` |
| 展開したZIPの中身 | `flows/create-initialized-list/validation/extracted/` |

---

## 2. 静的検証（`validate_list_flow.py`）

### 集計

| 項目 | 値 |
|---|---|
| パッケージフォルダGUID | `d07c8e5a-3f92-4b61-a8d4-15e69c2f0b73` |
| アクション総数 | 176 |
| HTTP要求アクション | 16（すべて SharePoint `HttpRequest`） |
| 初期化変数 | 33 |
| SetVariable | 58（**自己参照 0**） |
| AppendToArrayVariable | 8 |
| Foreach | 2（いずれも並列オフ） |
| connectionReferences | `shared_sharepointonline` のみ |
| **エラー / 警告** | **0 / 0** |

### トップレベル実行順

```text
Scope_Parse_And_Validate_Input → Scope_Verify_SharePoint_Site → Scope_Check_Existing_List
→ Scope_Create_List → Scope_Initialize_List → Scope_Delete_Deletable_Fields
→ Scope_Create_SampleRaw_Field → Scope_Configure_Default_View → Scope_Validate_Result
→ Scope_Handle_AlreadyExists → Scope_Handle_Error → Scope_Rollback_New_List → Scope_Finalize
```

指示書§26 の14スコープのうち `Scope_Initialize` だけは、`InitializeVariable` が Scope 内に置けない仕様のため**トップレベルの `Initialize_*` 連鎖**に置き換えています（§6 参照）。

### 安全検査の結果（本フローの主眼）

```text
GetByTitle( の出現            : 0 件
書き込みRESTのID指定          : 新規作成POSTを除き全件 varCreatedListId 使用
初期化ガード配下のアクション  : 12 件すべて varCreatedInThisRun 配下
同名確認→作成の順序           : Scope_Check_Existing_List(35) < Scope_Create_List(36)
```

### 実施した検査項目

雛形（`teams_post_url_flows` / `provision-archive-lists`）から継承:

JSON構文／runAfter兄弟整合・状態値の妥当性／アクション名の全体重複／変数の初期化⇔参照／`InitializeVariable` トップレベル／`body`・`outputs` 参照先実在／**SetVariable自己参照**／重複初期化／Append対象の初期化済み／接続参照突合／コネクタ封筒参照／不正な `@`／**関数許可リスト**／Foreach並列オフ／トリガー検査／GUID3点一致／`apisMap`・`connectionsMap`・`dependsOn` 整合

本件向けに追加（§36 の安全要件を機械化）:

| # | 検査 | 目的 |
|---|---|---|
| A | 定義中の `GetByTitle(` が0件 | リスト名で対象を特定する経路を構造的に排除 |
| B | 書き込み系POSTのURIに `varCreatedListId` が含まれる | 書き込みが今回作成したリストにしか届かないことの保証 |
| C | `Create_Generic_List` が `varListExists == false` ガード配下 | 同名リストがあるときに作成しない |
| D | 初期化・ロールバック12アクションが `varCreatedInThisRun == true` ガード配下 | 既存リストが初期化対象にならない |
| E | 同名確認スコープが作成スコープより runAfter 順で前 | 確認前に作らない |
| F | 作成失敗経路（`runAfter` に `Failed`）にREST呼び出しが無い | 作成失敗後に同名リストを取りに行かない |
| G | 列削除が `CanBeDeleted` 判定のフィルタ経由 | 列名の固定リストで判定しない |
| H | ロールバックのガードに `varListExists` と `varCreatedListId` の判定を含む | 誤削除の防止 |
| I | `dataset` が全アクションで `@variables('varSiteUrl')` | サイトURLの固定禁止 |
| J | `sample_raw` の SchemaXml をXMLパースし属性を検証 | 拡張リッチテキスト設定の担保 |
| K | 実値混入（サイトURL・テナント名・GUID・メール）0件 | 匿名化 |
| L | MERGE/DELETE ヘッダーに `IF-MATCH:*`／`__metadata` ボディは verbose／GETにボディ無し | SharePoint REST の形式 |
| M | §28 の必須変数23個がすべて定義されている | 仕様充足 |

### 検証スクリプトが実際に検出した不具合（開発中）

| # | 検出内容 | 対処 |
|---|---|---|
| 1 | **`Set_Final_Error_Code` が `varErrorCode` を自己参照**（保存時 `WorkflowRunActionInputsInvalidProperty` の原因） | `Compose_Final_Error_Code` を挟んで解消 |
| 2 | 関数許可リスト検査が REST の URI 片（`lists(` `AddViewField(` 等）を関数名と誤検出 | 文字列リテラルを除去してから走査するよう検査側を修正 |
| 3 | `X-HTTP-Method: DELETE` のPOSTが「bodyが無い」と判定された | メソッド呼び出しとDELETEを例外に追加 |

1件目は実際のバグで、実環境なら**インポートは成功したのち保存で落ちていた**種類のものです（`handbook/knowledge/error_catalog.md` の既知エラー2と同型）。

---

## 3. URL解析・リスト名検証のオフライン検証

`tests/run_url_parse_tests.py` は、生成済み `definition.json` から `Scope_Parse_And_Validate_Input` を読み出し、`tools/wdl_eval.py`（案件横断のWDL式ミニ評価器）で**定義に実際に書かれている式そのもの**を評価します。設計書の再実装ではなく成果物そのものを対象にしている点が要点です。

```text
合格 35 / 不合格 0（全 35 件）
```

内訳: URL正常系11・URL異常系5・リスト名正常系5・リスト名異常系13・判定順序1。

各ケースでは期待値の照合に加えて、**`varErrorCode` と `varIsValid` の整合**（エラーコードが空でなければ `varIsValid` は false）も検査しています。

**この検証で確認できないこと**: Power Automate 実機での関数の挙動差、SharePoint REST の応答、保存時検証、実行時エラー。

---

## 4. ZIP再展開検査（`extract_check.py`）

**エラー0**。

| 検査項目 | 結果 |
|---|---|
| ZIPが破損なく開ける | ✅ |
| エントリ数 | 5 |
| レガシー5ファイル構造がZIPルート直下から始まる | ✅ |
| `__MACOSX` / `.DS_Store` / ディレクトリエントリの混入 | 無し |
| 全JSONのパース | ✅ 5/5 |
| パッケージGUID3点一致 | ✅ |
| `apisMap` / `connectionsMap` が `resources`・`dependsOn` に実在 | ✅ |
| `connectionReferences` とキー一致 | ✅ `shared_sharepointonline` |
| 展開結果が `source/package` とバイト一致（SHA-256） | ✅ |
| トリガー入力（`SharePointUrl` / `ListName` 必須、`ListDescription` 任意） | ✅ |
| SharePoint `HttpRequest` アクションの実在 | ✅ |
| **`GetByTitle(` 0件**（ZIP側でも再確認） | ✅ |
| 主要スコープ・`createFieldAsXml`・`removeAllViewFields()`・`AddViewField('sample_raw')` の実在 | ✅ |
| `RichTextMode="FullHtml"` の実在 | ✅ |
| サイトURL実値の埋め込み | 0件 |

---

## 5. 実環境での確認状況

### 5-0. 実証済み（2026-07-24・`status: Created` の実行で確認）

`varStatus` が `Created` になるのは、`Compose_Final_Validation_Code` の6条件を**すべて**満たしたときだけです。したがって `Created` が返ったこと自体が、次の連鎖を証明します。

```text
varItemCount == 0                                  → ItemCount の GET と応答形状が正しい
varSampleRawCreated == true                        → sample_raw の作成と5項目検証が通過
length(varFieldDeleteErrors) == 0                  → 列削除が全件成功
varDefaultViewId が非空                             → views の GET と DefaultView 判定が成功
length(varFinalViewFields) == 1                    → ViewFields の GET と応答形状が正しい
first(varFinalViewFields) == 'sample_raw'          → ビュー再構築が意図どおり
```

加えて SharePoint 画面で「既定ビューが `sample_raw` の1列だけ」「不要な列が消えている」「`sample_raw` にHTML・リンクを保存できた」を確認済みです。

| # | 事項 | 判定 |
|---|---|---|
| **1** | **`dataset`（サイトのアドレス）に式 `@variables('varSiteUrl')` を指定した状態で保存・実行できる** | **✅ 実証**（保存を通らなければ実行できない）。**本件最大のリスクが解消** |
| 2 | `GET _api/web?$select=Id,Title,Url` | ✅ 実証 |
| 3 | `GET _api/web/lists?$select=Id,Title,Hidden,BaseTemplate,RootFolder/ServerRelativeUrl&$expand=RootFolder&$top=5000` | ✅ 実証 |
| 4 | `POST _api/web/lists`（`AllowContentTypes` / `ContentTypesEnabled` とも `false`） | ✅ 実証 |
| 5 | `GET lists(guid'..')?$select=..&$expand=RootFolder` | ✅ 実証 |
| 6 | `GET lists(guid'..')/ItemCount`（応答 `{"value": 0}` 形） | ✅ 実証 |
| 7 | `MERGE {"__metadata":{"type":"SP.List"},"EnableAttachments": false}` | ✅ 実証 |
| 8 | `getbyinternalnameortitle('Title')` ＋ `{"Required": false}` | ✅ 実証 |
| 9 | `GET lists(guid'..')/fields?$select=..,CanBeDeleted,..` | ✅ 実証 |
| 10 | `POST lists(guid'..')/fields(guid'..')/deleteObject()` | ✅ 実証（不要列が消えていた） |
| 11 | `createFieldAsXml` で `Type="Note"` ＋ `RichText="TRUE"` ＋ `RichTextMode="FullHtml"` | ✅ 実証（HTML・リンクを保存できた） |
| 12 | `getbyinternalnameortitle('sample_raw')?$select=..,SchemaXml` による検証 | ✅ 実証 |
| 13 | `GET lists(guid'..')/views?$select=..,DefaultView,..` | ✅ 実証 |
| 14 | `POST lists(guid'..')/views(guid'..')/viewfields/removeAllViewFields()`（**guid指定形**） | ✅ 実証 |
| 15 | `POST lists(guid'..')/views(guid'..')/viewfields/AddViewField('sample_raw')`（**guid指定形**） | ✅ 実証 |
| 16 | `GET lists(guid'..')/ViewFields` の応答形状（`body(..)?['Items']` で読める） | ✅ 実証 |
| 17 | Invoker形式＋匿名GUIDの接続参照が SharePoint コネクタでも実接続へ再マッピングされる | ✅ 実証 |
| 18 | `Compose` オブジェクト＋`string()` によるRESTボディ生成 | ✅ 実証 |

### 5-1. 最優先の残課題（**未確認**）

| # | 事項 | 補足 |
|---|---|---|
| **19** | **同名リストが存在する場合の経路（`AlreadyExists`）** | 今回の実行は `Created` のみ。**このフローの最重要の安全機構がこの経路にある**にもかかわらず、実機で発火していない。確認手順は `docs/installation.md` ステップ9（既存リスト名を指定し、`status: AlreadyExists` になること＋**既存リストが1文字も変わっていないこと**を目視） |

> 定義の構造としては `varCreatedInThisRun` ガード・`GetByTitle(` 0件・書き込みURIの `varCreatedListId` 固定により**静的に保証**されています（§2の安全検査 A〜H）。ただし「静的に保証されている」ことと「実機で確認した」ことは別です。

### 5-2. その他の未確認事項

| # | 事項 |
|---|---|
| 20 | ロールバック（`POST lists(guid'..')` ＋ `X-HTTP-Method: DELETE`）— `Created` だったため実行されていない |
| 21 | 権限不足時に SharePoint が 403 を返すか 404 を返すか |
| 22 | 失敗したアクションで `outputs(..)?['statusCode']` が取得できるか |
| 23 | 並列実行時の競合検出（同時2回実行 → `AlreadyExistsOrConflict`） |
| 24 | 列削除が失敗した場合の記録（`varFieldDeleteErrors`）— 今回は全件成功したため未発火 |
| 25 | サブサイトURLから抽出したサイトURLが実サイトとして解決されるか |
| 26 | OneDrive 個人サイト（`-my.sharepoint.com`）での動作 |
| 27 | 予約名リストの網羅性（SharePoint が拒否する名前の完全な一覧は非公開） |
| 28 | 制御文字の検出範囲（タブ・CR・LF 以外は式で検出していない） |

---

## 6. 設計上の判断と、指示書からの逸脱

いずれも理由を明記したうえで意図的に採用したものです。

| # | 指示書の記載 | 実装 | 理由 |
|---|---|---|---|
| 1 | §26 `Scope_Initialize` を作る | 変数初期化を**トップレベルの `Initialize_*` 連鎖**にした | `InitializeVariable` は Scope 内に置けない（`handbook/rules/01`【事実】）。Try/Catch/Finally 構造自体は残りの13スコープで実現している |
| 2 | §17 削除不能列をフォームから非表示化する | **実装していない**。制約として記録する | `SetShowInNewForm` 等のRESTに本リポジトリ内の実在確認の証跡が無く、推測実装は§31の禁止事項に当たる。§17が許容する「制約として記録」を選択し、「非表示化できた」とは報告しない |
| 3 | §21・§22 `ViewFields`（大文字）のパス | `viewfields`（小文字）を使用。検証GETのみ `ViewFields` | 実証済みリファレンスの表記に合わせた。SharePoint REST のパスセグメントは大文字小文字を区別しない |
| 4 | §11.2 ヘッダーは verbose | そのまま採用 | リファレンス `createList` と同一 |
| 5 | §11.3 動的値の埋め込み | Compose のオブジェクト＋`string()` | 「文字列連結だけで生成しない」「引用符・改行・円記号でJSONを壊さない」という要求を満たす最も確実な方法 |
| 6 | §34 配置 | `projects/create_initialized_sharepoint_list/flows/create-initialized-list/{spec,source,validation,release}` | §34は「既存ルールと整合する場所へ」を第一に指示。`CLAUDE.md` の構成マップに従った |

### 共通ツールの変更（報告事項）

ユーザー指示「既存の初期化処理が存在すれば重複なく実行する」に対応し、`teams_post_url_flows/tests/wdl_eval.py`（WDL式ミニ評価器）を **`tools/wdl_eval.py` へ移動**して共有化しました。`toLower` / `toUpper` / `greaterOrEquals` / `lessOrEquals` / `mul` / `lastIndexOf` を追加しています。`teams_post_url_flows` 側の import も更新し、移動後も同案件のテストが**40件合格**であることを確認済みです。

---

## 7. 確認済みの範囲と、まだ確認されていない範囲

### 確認済み（2026-07-24・利用者報告）

- **実環境へのインポートに成功した。**
- **実環境での実行に成功し、`status: Created` が返った。**
- SharePoint 画面で「既定ビューが `sample_raw` の1列だけ」「不要な列が消えている」「`sample_raw` にHTML・リンクを保存できた」を確認した。
- これにより、**新規作成から初期化完了までの主経路（§5-0 の18項目）が実証**されました。特に本件最大のリスクだった「`dataset` に式を指定した状態で保存できるか」が解消されています。

### まだ確認されていないこと

- **同名リストが存在する場合の経路（`AlreadyExists`）が実機で発火していません。** このフローの最重要の安全機構がその経路にあるため、**次に確認すべき最優先項目**です。
- ロールバック（リスト削除）・権限不足時の挙動・競合・列削除失敗時の記録は、いずれも**失敗経路であるため今回は通っていません**。
- サブサイトURL・OneDrive 個人サイトでの動作。

> **「Created が返った」と「あらゆる入力で安全」は別です。** 既存リスト保護は定義の構造から静的に保証されていますが（§2 の安全検査 A〜H）、実機での確認はまだです。`docs/installation.md` ステップ9 を実施し、**既存リストが1文字も変わっていないこと**を目視してください。

実環境で問題が見つかった場合は `source/build_list_flow.py` を修正して再生成し、本レポートを更新してください。得られた知見は `knowledge-update` Skill で `handbook/` に還元してください。

---

関連: [test_cases.md](test_cases.md) / [../docs/installation.md](../docs/installation.md) / [../docs/safety_mechanisms.md](../docs/safety_mechanisms.md) / [../docs/troubleshooting.md](../docs/troubleshooting.md)
