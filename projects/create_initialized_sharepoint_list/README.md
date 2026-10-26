# create_initialized_sharepoint_list — 初期化済みSharePointリストを安全に作成するフロー

実行時に指定された SharePoint サイトURLとリスト名を受け取り、**同名リストが存在しない場合に限って**新しい汎用リストを作成し、利用者から見えるデータ列を `sample_raw`（拡張リッチテキスト）だけに初期化する手動トリガーのクラウドフローです。

| 項目 | 内容 |
|---|---|
| フロー名（論理名） | `CreateInitializedSharePointList` |
| 表示名 | SharePointリスト新規作成＋初期化（既存リスト保護） |
| トリガー | 手動でフローをトリガーします（ボタン） |
| 使用コネクタ | **SharePoint 1本のみ**（`shared_sharepointonline` / `HttpRequest`）・プレミアム不要 |
| アクション総数 | 176 |
| HTTP要求 | 16件（すべて SharePoint REST） |

> **状態: 静的検証を通過し、実環境でのインポートと実行に成功しました（2026-07-24・`status: Created`）。**
> SharePoint 画面で「既定ビューが `sample_raw` の1列だけ」「不要な列が消えている」「`sample_raw` にHTML・リンクを保存できた」も確認済みです。最大の懸案だった **`dataset` に式を指定した状態での保存**も解消されました。
>
> ただし **同名リストが存在する場合の経路（`AlreadyExists`）は実機で発火していません。** このフローの最重要の安全機構がその経路にあるため、次に確認すべき最優先項目です（[tests/validation_report.md](tests/validation_report.md) §5-1）。

---

## このフローが何をするか

```text
1. SharePointのURLとリスト名を受け取る
2. URLからサイトURLを抽出する（/_layouts/ の直前まで。クエリ・末尾スラッシュ・空白を除去）
3. 入力を検証する（URL形式・リスト名の禁止文字・予約名・長さ）
4. _api/web でサイトへの疎通と参照権限を確認する
5. サイト上の全リスト（非表示含む）を取得し、同名リストの有無を判定する
   ├─ 存在する → 何もせず AlreadyExists で正常終了（既存リストには一切触れない）
   └─ 存在しない → 6 へ
6. 汎用リスト（BaseTemplate=100）を新規作成する
   └─ 作成に失敗（競合）→ AlreadyExistsOrConflict で終了（同名リストを取りに行かない）
7. 以降、作成したリストのIDに対してのみ初期化を行う
   ├─ アイテム0件を確認（0件でなければ中止。削除はしない）
   ├─ 添付ファイル機能を無効化
   ├─ Title の必須を解除
   ├─ CanBeDeleted=true の列をすべて削除（並列オフ・失敗は記録）
   ├─ sample_raw 列を作成（Note/RichText/FullHtml）して検証
   └─ 既定ビューの列を全削除し、sample_raw だけを追加して検証
8. 最終判定 → 結果JSONを varResultObject / varResultJson に格納
   └─ 初期化に失敗した場合は、今回作成したリストIDのみを削除（ロールバック）
```

---

## 安全設計（最重要）

既存リストを1つでも誤って初期化すれば業務データの列が消えます。そのため安全性は設計だけに頼らず、**`validate_list_flow.py` の機械検査で0件を保証**しています。

| 防御 | 機械検査の結果 |
|---|---|
| リスト名で対象を特定しない | 定義中の `GetByTitle(` が **0件** |
| 書き込みは今回作成したリストにのみ届く | 新規作成POSTを除く全POSTのURIが `varCreatedListId` を含む |
| 作成は同名リストが無いときだけ | `Create_Generic_List` が `varListExists == false` ガード配下 |
| 初期化・ロールバックは今回作った物にだけ | 対象12アクションすべてが `varCreatedInThisRun == true` ガード配下 |
| 確認は作成より先 | `Scope_Check_Existing_List` が `Scope_Create_List` より前 |
| 削除対象は `CanBeDeleted` でのみ判定 | 列名の固定リストを使っていない |
| ロールバックはID完全一致のみ | リスト名での再検索が構造的に不可能 |

詳細は [docs/safety_mechanisms.md](docs/safety_mechanisms.md) を参照してください。

---

## クイックスタート

1. [docs/installation.md](docs/installation.md) の手順でZIPをインポートする（「パッケージのインポート **(レガシー)**」）
2. SharePoint接続を選択する（必要な接続は1つだけ）
3. フローを開いて**すぐ保存**する（保存でしか出ないエラーの早期発見）
4. フローを実行し、「SharePointサイトまたはリスト一覧URL」と「作成するリスト名」を入力する
5. 実行履歴の `Scope_Finalize` → `Compose_Flow_Output` で結果を確認する

インポート用ZIP: `flows/create-initialized-list/release/CreateInitializedSharePointList_20260724211020.zip`

---

## 成果物の場所

```text
projects/create_initialized_sharepoint_list/
├── README.md                       ← このファイル
├── docs/
│   ├── installation.md             インポート手順・接続参照の設定手順
│   ├── usage.md                    実行方法・入力・出力の読み方
│   ├── url_parsing_spec.md         URL解析仕様・リスト名検証仕様
│   ├── list_operations_spec.md     同名確認／リスト作成／列初期化／sample_raw／既定ビュー
│   ├── safety_mechanisms.md        安全機構の説明（既存リストを壊さない仕組み）
│   ├── json_schema.md              出力JSON仕様（Created / AlreadyExists / Failed）
│   └── troubleshooting.md          症状別の対処
├── tests/
│   ├── test_cases.md               正常系14・同名確認5・異常系12
│   ├── validation_report.md        検証レポート（実施済み検証と未確認事項）
│   ├── run_url_parse_tests.py      URL解析・リスト名検証の回帰テスト
│   └── url_parse_test_result.txt   テスト実行結果（35件合格）
└── flows/create-initialized-list/
    ├── spec/CreateInitializedSharePointList.md   フロー定義の説明
    ├── source/                     ← 唯一の編集元
    │   ├── build_list_flow.py      definition.json / manifest 群の生成
    │   ├── validate_list_flow.py   静的検証（検証の正典・安全要件の機械化）
    │   └── package/                生成物（レガシー5ファイル構造）
    ├── validation/                 検証証跡
    │   ├── action_outline.txt      実行順のアクション一覧（176件）
    │   ├── validate_result.txt     静的検証の出力
    │   ├── extract_check.py        ZIP再展開検査
    │   ├── extract_check_result.txt 検査結果
    │   └── extracted/              展開したZIPの中身（検証用コピー）
    └── release/                    インポート用ZIP（日時付き）
```

`source/package/` と `release/*.zip` は**生成物**です。`definition.json` を直接編集せず、`source/build_list_flow.py` を編集して再生成してください（`CLAUDE.md` 不変則1）。

WDL式評価器は案件横断の共通ツール [`tools/wdl_eval.py`](../../tools/wdl_eval.py) を使います（案件ごとに複製しません）。

---

## 指示書§35 の必須成果物との対応

| # | required | 場所 |
|---|---|---|
| 1 | Power Automateインポート用ZIP | `flows/create-initialized-list/release/*.zip` |
| 2 | ZIP展開後のフロー定義 | `flows/create-initialized-list/source/package/` ／ `validation/extracted/` |
| 3 | フロー処理説明 | [flows/create-initialized-list/spec/CreateInitializedSharePointList.md](flows/create-initialized-list/spec/CreateInitializedSharePointList.md) |
| 4 | URL解析仕様 | [docs/url_parsing_spec.md](docs/url_parsing_spec.md) |
| 5 | 同名リスト確認仕様 | [docs/list_operations_spec.md](docs/list_operations_spec.md) §1 |
| 6 | リスト作成仕様 | 同 §2 |
| 7 | 列初期化仕様 | 同 §3 |
| 8 | `sample_raw` 列仕様 | 同 §4 |
| 9 | 既定ビュー設定仕様 | 同 §5 |
| 10 | 安全機構の説明 | [docs/safety_mechanisms.md](docs/safety_mechanisms.md) |
| 11 | インポート手順 | [docs/installation.md](docs/installation.md) |
| 12 | 接続参照の設定手順 | 同 ステップ5 |
| 13 | テストケース | [tests/test_cases.md](tests/test_cases.md) |
| 14 | 検証レポート | [tests/validation_report.md](tests/validation_report.md) |

---

## 検証状況

| 区分 | 結果 |
|---|---|
| 静的検証（`validate_list_flow.py`） | **エラー0 / 警告0** |
| URL解析・リスト名検証テスト | **35件中35件合格** |
| ZIP再展開検査（`extract_check.py`） | **エラー0** |
| 実環境のインポート | **成功**（2026-07-24） |
| 実環境の実行（新規作成経路） | **成功**（`status: Created`。SharePoint画面でも確認） |
| 実環境の実行（同名リスト経路・失敗経路） | **未確認** |

再検証:

```powershell
cd projects/create_initialized_sharepoint_list
python flows/create-initialized-list/source/build_list_flow.py
python flows/create-initialized-list/source/validate_list_flow.py     # errors 0 / warnings 0
python tests/run_url_parse_tests.py                                   # 35件合格
python flows/create-initialized-list/validation/extract_check.py      # errors 0
```

---

## 制約と未確認事項

| 項目 | 内容 |
|---|---|
| 対応するURL | サイトルート／`viewlsts.aspx`／クエリ付き／サブサイト／テナントルート |
| 対応しないURL | 個別リストのビューURL（`/Lists/<名前>/AllItems.aspx`）・`http://`・SharePoint以外 |
| 必要なコネクタ | SharePoint 1本（標準・プレミアム不要） |
| 必要な権限 | 対象サイトでリスト・列・ビューを管理できること（**要実環境確認**） |
| 既存リストへの影響 | **なし**（GET 以外を発行しない） |
| インポート後の追加設定 | **不要**（環境固有の値を保持する変数がない） |

**最大の未確認事項**: **同名リストが存在する場合の経路（`AlreadyExists`）が実機で発火していません。** 既存リスト保護は定義の構造から静的に保証されていますが（`GetByTitle(` 0件・書き込みURIの `varCreatedListId` 固定・`varCreatedInThisRun` ガード）、実機での確認はまだです。[docs/installation.md](docs/installation.md) ステップ9 を実施し、**既存リストが1文字も変わっていないこと**を目視してください。

> `dataset` に式を指定した状態での保存は **2026-07-24 に解消済み**です（実行に成功したため）。

その他の未確認事項（ロールバックのリスト削除・権限不足時の挙動・競合・列削除失敗時の記録など、いずれも失敗経路）は [tests/validation_report.md](tests/validation_report.md) §5-2 に全件列挙しています。

---

## 関連

- 案件横断の共通知識: [`handbook/`](../../handbook/)（[SharePoint REST リスト作成パターン集](../../handbook/knowledge/sharepoint_rest_list_provisioning.md)）
- REST形式の実働リファレンス: [`references/extracted/reference_original/`](../../references/extracted/reference_original/)（`CreateKnowledgeList`。**編集禁止**）
- 生成スクリプトの雛形: [`projects/migrate-chat-spo/flows/provision-archive-lists/source/build_list_package.py`](../migrate-chat-spo/flows/provision-archive-lists/source/build_list_package.py)
- リポジトリ全体の作業規範: [`CLAUDE.md`](../../CLAUDE.md)
