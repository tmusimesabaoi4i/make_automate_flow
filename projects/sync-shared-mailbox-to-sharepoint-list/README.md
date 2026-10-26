# sync-shared-mailbox-to-sharepoint-list — 共有メールボックスのメールをSharePointリストへ同期

本案件には**3つのフロー**がある。

| フロー | 列 | 用途 | 実環境 |
|---|---|---|---|
| [sync-mail-to-list](flows/sync-mail-to-list/) | 5列 | メールをそのまま同期する基本形 | **インポート・実行 成功**（2026-08-03） |
| [sync-mail-to-list-with-examiner-detection](flows/sync-mail-to-list-with-examiner-detection/) | **7列** | 上記＋**審査官名・出願番号の推定** | **未実施**（静的検証0件・検出テスト108件合格） |
| [sync-mail-to-list-with-examiner-directory](flows/sync-mail-to-list-with-examiner-directory/) | **12列** | 上記＋**審査官名簿と突合**してメールアドレス・TeamsユーザーIDを取得 | **未実施**（静的検証0件・検出108＋突合17件合格） |

3つは独立している。用途で選ぶ。

- **審査官名・出願番号が不要** → 5列版
- **推定だけ必要**（名簿が無い） → 7列版
- **Teams投稿のためにメールアドレス・ユーザーIDまで欲しい** → 12列版
  （`projects/teams-channel-member-sync/` が作る名簿が必要）

| 仕様書 | 内容 |
|---|---|
| [spec/SyncMailToListWithExaminerDetection.md](flows/sync-mail-to-list-with-examiner-detection/spec/SyncMailToListWithExaminerDetection.md) | 7列版のフロー仕様 |
| [spec/SyncMailToListWithExaminerDirectory.md](flows/sync-mail-to-list-with-examiner-directory/spec/SyncMailToListWithExaminerDirectory.md) | 12列版のフロー仕様 |
| [docs/examiner_detection_spec.md](docs/examiner_detection_spec.md) | 検出アルゴリズム（7列版・12列版で共通） |
| [docs/examiner_directory_match_spec.md](docs/examiner_directory_match_spec.md) | 名簿突合（12列版のみ） |

> 後発の2つは前段を**逐語コピー**した土台に処理を足したもの。
> 先行フローのファイルは1つも変更していない（SHA-256で確認済み）。
> ただし12列版は、500アクション上限に収めるため**列処理をループ化**している（仕様書§2）。

---

## 5列版（sync-mail-to-list）

手動実行時に指定した共有メールボックスの最新メールを取得し、指定したSharePointサイト上のリストへ
**登録（新規）または更新（既存）** するインスタントクラウドフロー。

| 項目 | 値 |
|---|---|
| フロー論理名 | `SyncSharedMailboxToSharePointList` |
| フロー表示名 | 共有メールボックスのメールをSharePointリストへ同期 |
| トリガー | 手動（インスタントクラウドフロー / `manual` = Request + Button） |
| コネクタ | SharePoint / Office 365 Outlook / Content Conversion（すべて標準） |
| アクション総数 | 304（うち SharePoint REST 34・Outlook 1・Content Conversion 1） |
| パッケージ形式 | レガシーパッケージ（.zip・5ファイル構造） |
| 静的検証 | **エラー0・警告0** |
| オフラインテスト | **57件合格** |
| 実環境 | **インポート・保存・実行 成功**（2026-08-03）。**既存リスト経路で100件同期**（作成80・更新20・失敗0）。新規作成経路は未確認 |

> **実環境での確認状況（2026-08-03）**
> - ✅ インポート成功 / ✅ 保存成功 / ✅ **実行成功・出力は想定どおり**（`..._20260803233000.zip`）
>   （既存リスト経路・100件：作成80／更新20／失敗0／重複0）
> - ✅ 3コネクタ構成での接続再マッピング／入力検証・URL正規化／サイト疎通／リスト列挙
> - ✅ `GetEmailsV3` のパラメータ構成／`HtmlToText` 100件成功／アイテム作成・更新
> - ✅ **冪等性が実データで機能**（20件が既存判定→更新。重複登録なし）
> - ⏳ **新規作成経路（`status: Created`）は未確認** → 列作成・一意制約・既定ビューの並び順も未検証
>
> ⚠ **「1回の実行が通った」＝「全テストが通った」ではない。**
> どの経路（`Created` / `Existing`）が通ったか、テスト2〜10 の各ケースは
> [tests/validation_report.md](tests/validation_report.md) §9 の表で個別に管理する。
> 未実施のものは未実施のまま残している。

---

## 1. フローの目的

共有メールボックスに届いたメールを、SharePointリストで一覧・検索・共有できる形に同期する。

- 同名リストが**無い**場合だけリストを新規作成し、業務用の5列と既定ビュー（日時の降順）を設定する
- 同名リストが**ある**場合はリスト自体を一切変更せず、必要な列が揃っているかだけ確認して同期する
- 同じメールを再取得しても**アイテムは増えない**（メッセージIDで既存を検索し、あれば更新）
- **メールは読み取るだけ**。既読化・移動・削除・フラグ・送信は一切行わない

---

## 2. できること・しないこと

| する | しない |
|---|---|
| 同名リストが無いときの新規作成 | 既存リストの削除・上書き・改名 |
| 新規リストへの5列作成と既定ビュー設定 | 既存リストの列・ビュー・設定の変更 |
| メールの取得（受信トレイ・既読未読の両方） | メールの既読化・移動・削除・フラグ・送信 |
| メッセージIDによる重複判定と更新 | 既存アイテムの一括削除 |
| 本文のプレーンテキスト化 | HTMLのまま保存 / `Body Preview` だけの保存 |
| 上限超過時の事前エラー終了 | 指定件数の黙った切り捨て |

---

## 3. クイックスタート

1. `flows/sync-mail-to-list/release/SyncSharedMailboxToSharePointList_20260803233000.zip` を用意する

   > **古い2つのZIPは使用しないこと**（履歴として残しているだけ）。
   > - `..._20260803213000.zip` … 説明文の `@{tenant}` でインポート失敗（修正済み）
   > - `..._20260803224500.zip` … リスト列挙が 403 で実行失敗（修正済み）
   >
   > 詳細は [tests/validation_report.md](tests/validation_report.md) §3.3。

2. Power Automate →「マイフロー」→「インポート」→「パッケージのインポート（レガシー）」
3. ZIPをアップロードし、フローの**インポート設定を「新規作成として」**にする
4. **3つの接続参照**（SharePoint / Office 365 Outlook / Content Conversion）に実接続を割り当てる
5. インポート後、**フローを開いてそのまま一度保存**する（保存時にしか出ないエラーがある）
6. フローチェッカーを実行して警告0を確認する
7. まず**取得件数3件**で試験実行する

詳細は [docs/installation.md](docs/installation.md)。

---

## 4. 接続参照の割当

| 接続参照キー | コネクタ | 用途 |
|---|---|---|
| `shared_sharepointonline` | SharePoint | `HttpRequest`（REST）でリスト操作・アイテム登録／更新 |
| `shared_office365` | Office 365 Outlook | `GetEmailsV3` でメール取得（**読み取りのみ**） |
| `shared_conversionservice` | Content Conversion | `HtmlToText` で本文のプレーンテキスト化 |

パッケージ内の接続IDは**匿名GUID**で、特定ユーザーの接続に固定されていない。
インポート時に各接続参照へ、利用者自身の接続を割り当てる。

---

## 5. 必要な権限

### SharePoint
- 対象サイトへの**参照権限**（`_api/web` の疎通確認・リスト一覧の取得）
- 新規作成を行う場合: 対象サイトで**リストの作成**と**列・ビューの管理**ができる権限（サイトの所有者/フルコントロール相当）
- 既存リストを使う場合: 対象リストへの**アイテムの追加・編集**権限

### 共有メールボックス
- Outlook接続を作成したユーザーが、対象の共有メールボックスに**アクセスできる**こと（フルアクセス権限）
- **書き込み権限は不要**（本フローはメールを一切変更しない）
- アクセスできない場合は `ERR_PERMISSION_DENIED` として結果に記録される

### 【要実環境確認】
- Content Conversion コネクタが組織のDLPポリシーで許可されていること
- 共有メールボックスの権限付与形態（フルアクセスの委任方式）による差異

---

## 6. 手動トリガーの入力

| 内部名 | 表示名 | 型 | 必須 | 説明 |
|---|---|---|---|---|
| `SharePointUrl` | SharePointサイトまたはリスト一覧URL | string | ✓ | サイトURL・サイトのコンテンツ・`viewlsts.aspx` のいずれでも可 |
| `ListName` | 作成するリスト名 | string | ✓ | 前後の空白は除去される。同名があればそのリストを使う |
| `SharedMailboxAddress` | 共有メールボックスのアドレス | string | ✓ | 監視対象の共有メールボックス |
| `MailCount` | 取得件数 | integer | ✓ | **1〜100**。101以上は処理を行わずエラー終了 |

### 入力例

```text
SharePointUrl        : https://{tenant}.sharepoint.com/sites/{siteName}
                       https://{tenant}.sharepoint.com/sites/{siteName}/_layouts/15/viewlsts.aspx?view=14
                       （どちらも https://{tenant}.sharepoint.com/sites/{siteName} に正規化される）
ListName             : メール台帳
SharedMailboxAddress : shared-mailbox@{tenant}.example.com
MailCount            : 20
```

URL正規化の詳細と対応できない形式は [docs/url_parsing_spec.md](docs/url_parsing_spec.md)。

---

## 7. 新規リスト作成時の列構成

利用者から見える業務用の列は5列。既定の `Title` 列は**削除せず**、必須解除して既定ビューから外す。

| 表示名 | 内部名 | 型 | 設定 |
|---|---|---|---|
| メッセージID | `MessageId` | 1行テキスト | **必須・インデックス・一意** |
| 日時 | `ReceivedDateTime` | 日付と時刻 | インデックス |
| 送信元アドレス | `SenderAddress` | 1行テキスト | — |
| 件名 | `Subject` | 1行テキスト | — |
| 本文 | `BodyPlainText` | 複数行テキスト | プレーンテキスト（`RichText=FALSE`）・追記履歴なし |

内部名は**安定したASCII**で作成し、そのあと表示名だけを日本語へ変更する。
表示名を後から変えても内部名は変わらないため、フローの処理は壊れない。

既定ビューの列順は `メッセージID → 日時 → 送信元アドレス → 件名 → 本文`、
並び順は **日時の降順**（第2キーは `ID` の降順）。リストを開くと最新のメールが上に来る。

---

## 8. 既存リストを使う条件

同名リストが存在する場合、**リストは一切変更しない**。次をすべて満たすときだけ同期を行う。

- 5列が**内部名**（`MessageId` / `ReceivedDateTime` / `SenderAddress` / `Subject` / `BodyPlainText`）で存在する
- 型が互換である（`Text` / `DateTime` / `Text` / `Text` / `Note`）

満たさない場合は `ERR_SCHEMA_INCOMPATIBLE` で安全に終了し、
結果の `missingFields` / `incompatibleFields` に不足・不一致の内容を記録する。
**リストを勝手に修正することはしない。**

同名リストが**複数**見つかった場合、または**非表示リスト／システムリスト**だった場合も、
書き込みを行わず `ERR_LIST_AMBIGUOUS` / `ERR_LIST_NOT_GENERIC` で終了する。

---

## 9. 1回に取得できる件数の上限

| 項目 | 値 | 根拠 |
|---|---|---|
| 本フローの上限 | **100件** | 下記の制約から決定 |
| `GetEmailsV3` の `top` 公式上限 | 1000 | 公式コネクタリファレンス（参照日 2026-08-03） |
| Office 365 Outlook の調整制限 | 300コール/60秒/接続 | 同上 |
| フロー実行時間の目安上限 | 約30分 | Power Automate の一般的な制限 |

1件につき SharePoint REST が2〜3回（検索＋作成または更新）走るため、100件で約250コール。
1000件では調整制限と実行時間上限に確実に触れるため、**100件を上限とし、101以上は
リスト作成もメール取得も行わずに `ERR_COUNT_TOO_LARGE` で終了**する（黙って切り捨てない）。

指定件数より実際のメールが少ない場合は、存在する分だけを処理する。
結果には `requestedCount`（指定）と `fetchedCount`（実際）の**両方**が入る。

---

## 10. 本文変換の制約

- Content Conversion コネクタの `HtmlToText` でプレーンテキスト化する
- 変換に**失敗した場合はHTMLをそのまま登録せず**、その1件だけを失敗として記録して次のメールへ進む
- 本文が空でも処理は継続する
- 変換結果が複数行テキスト列の上限（63,999文字）を超える場合は、
  切り詰めたうえで結果の `truncatedItems[]` と `truncatedCount` に記録する（**黙って切り捨てない**）
- `Body Preview` は使用しない

### 【要実環境確認】
- Content Conversion が使えない環境（DLPで遮断されている等）では本フローは動作しない。
  代替として標準コネクタだけでHTMLタグを除去する方法は、タグ・エンティティ・改行の
  取り扱いが不完全になるため**採用していない**（詳細は [docs/troubleshooting.md](docs/troubleshooting.md)）
- `HtmlToText` の出力形（文字列そのものか、オブジェクトに包まれるか）は実機未確認

---

## 11. エラー時の確認方法

1. Power Automate の**実行履歴**を開く
2. 最後の `Compose_Flow_Output`（`Scope_Finalize` 内）の出力を見る。
   `resultObject.error.code` / `.message` / `.stage` に何がどこで失敗したかが入っている
3. `stage` が示すスコープの中で、赤くなっているアクションの「入力」「出力」を確認する
4. 件単位の失敗は `resultObject.itemErrors[]` に、重複異常は `duplicates[]` に入る

エラーコードの一覧と対処は [docs/json_schema.md](docs/json_schema.md) と
[docs/troubleshooting.md](docs/troubleshooting.md)。

---

## 12. テスト方法

### 開発側（実機不要・いつでも再現できる）

```powershell
cd D:\make_automate_flow
python projects/sync-shared-mailbox-to-sharepoint-list/flows/sync-mail-to-list/source/build_sync_flow.py
python projects/sync-shared-mailbox-to-sharepoint-list/flows/sync-mail-to-list/source/validate_sync_flow.py   # errors 0 / warnings 0
python projects/sync-shared-mailbox-to-sharepoint-list/tests/run_offline_tests.py                             # 57件合格
python projects/sync-shared-mailbox-to-sharepoint-list/flows/sync-mail-to-list/validation/extract_check.py    # errors 0
```

### 実環境側

[tests/test_cases.md](tests/test_cases.md) にテスト1〜10（新規リスト／再実行／既存互換／既存非互換／
不正URL／不正件数／HTML本文／空の値／特殊文字／重複異常）の手順と期待結果を設計してある。
**いずれも未実施**。実施状況は [tests/validation_report.md](tests/validation_report.md)。

---

## 13. フローを無効化・削除する方法

### 無効化
Power Automate →「マイフロー」→ 対象フローの「…」→「**オフにする**」。
手動トリガーのため、オフにすれば実行できなくなる。定義とデータは残る。

### 削除
「…」→「**削除**」。フロー定義と実行履歴が削除される。

> **注意**: フローを削除しても、**作成済みのSharePointリストと登録済みアイテムは残る**。
> リストが不要なら SharePoint 側で手動削除する（本フローはリストを削除しない）。
> 接続（SharePoint / Outlook / Content Conversion）は他のフローでも使われている可能性があるため、
> フロー削除時に自動では消えない。不要なら「データ」→「接続」から個別に削除する。

---

## 14. 成果物の場所

```text
projects/sync-shared-mailbox-to-sharepoint-list/
├── README.md                                   ← 本ファイル
├── docs/
│   ├── installation.md                         インポート手順・接続割当・権限
│   ├── usage.md                                入力例・実行方法・結果の読み方
│   ├── url_parsing_spec.md                     URL正規化と入力検証の仕様
│   ├── list_operations_spec.md                 存在確認／作成／列／ビュー／登録更新のREST仕様
│   ├── json_schema.md                          結果JSON・status・エラーコード一覧
│   ├── examiner_detection_spec.md              ★審査官名・出願番号の検出仕様（7列版・12列版共通）
│   ├── examiner_directory_match_spec.md        ★審査官名簿との突合仕様（12列版）
│   └── troubleshooting.md                      エラーコード別の対処
├── tests/
│   ├── run_offline_tests.py                    定義の式をそのまま評価する回帰テスト
│   ├── run_detection_tests.py                  検出ロジックの回帰テスト（108件）
│   ├── run_directory_match_tests.py            名簿突合の回帰テスト（検出108＋突合17件）
│   ├── test_cases.md                           指示§23 のテスト1〜10 の設計
│   ├── detection_test_cases.md                 検出テストの設計と発見した不具合
│   ├── offline_test_result.txt                 実行結果（57件合格）
│   ├── detection_test_result.txt               実行結果（108件合格）
│   └── validation_report.md                    実施済み／未実施の明示
└── flows/sync-mail-to-list/
    ├── spec/SyncSharedMailboxToSharePointList.md   フロー定義の説明
    ├── source/
    │   ├── build_sync_flow.py                  ★唯一の編集元
    │   ├── validate_sync_flow.py               静的検証（検証の正典）
    │   └── package/                            生成された展開形（5ファイル）
    ├── validation/
    │   ├── action_outline.txt                  実行順アウトライン（304アクション）
    │   ├── validate_result.txt                 静的検証の結果（0 errors / 0 warnings）
    │   ├── extract_check.py                    ZIP再展開＋SHA-256突合
    │   └── extract_check_result.txt            その結果（0 errors）
    └── release/
        ├── SyncSharedMailboxToSharePointList_20260803213000.zip   ✗ 不良（インポート不可）
        ├── SyncSharedMailboxToSharePointList_20260803224500.zip   ✗ 不良（実行時403）
        └── SyncSharedMailboxToSharePointList_20260803233000.zip   ★インポート用
```

**`definition.json` は生成物**。修正は必ず `source/build_sync_flow.py` を編集して再生成する
（[../../CLAUDE.md](../../CLAUDE.md) 不変則1）。

---

## 15. 安全設計（機械検査で担保している）

「気をつける」ではなく、**その経路を定義から消す**ことで担保している。
すべて `source/validate_sync_flow.py` が走査して0件／全件を確認する。

| # | 保証 | 検査結果 |
|---|---|---|
| A | リスト名で対象を特定する経路が存在しない（`GetByTitle(`） | 0件 |
| B | 書き込み系RESTのURIは必ず `varListId` を含む（新規作成POSTのみ例外） | 全件 |
| C | 破壊的REST（`deleteObject` / `recycle` / `DELETE`）が存在しない | 0件 |
| D | 列作成・表示名変更・Title変更・ビュー操作は `varCreatedInThisRun` ガード配下 | 18件すべて |
| E | `removeAllViewFields()` は1件のみ・ガード配下 | 1件 |
| F | Outlook の operationId は `GetEmailsV3` のみ（既読化・移動・削除・送信が無い） | 0件 |
| G | `mailboxAddress` は変数式・`fetchOnlyUnread=false`・`includeAttachments=false` | 全件 |
| H | 全 SharePoint アクションの `dataset` が `@variables('varSiteUrl')` | 34件すべて |
| I | `$filter` は `''` 2重化＋`uriComponent()` の両方を経由 | 2件すべて |
| J | 同名リスト判定は `equals`（完全一致）。`contains` を使わない | 3件すべて |
| K | 既定ビューの `ViewQuery` が `ReceivedDateTime` の降順 | 有 |
| L | 5列の SchemaXml が妥当（一意制約・`RichText=FALSE`） | 全件 |
| M | スコープの実行順が 検証→存在確認→作成→スキーマ確認→取得→同期 | 合致 |
| N | メール取得・同期は `varIsValid` / `varSchemaOk` ガード配下 | 全件 |

加えて汎用検査（GUID3点一致・runAfter兄弟整合・アクション名全体一意・SetVariable自己参照・
未初期化変数参照・コネクタ封筒参照・不正な`@`位置・関数許可リスト・Foreach並列オフ・
実値混入）もすべて0件。

---

## 16. 制約と未確認事項

### 制約
- 取得件数の上限は100件（§9）
- `MessageId` は1行テキスト列のため、255文字を超えるIDのメールは当該1件のみ失敗記録
- 本文は63,999文字で切り詰め（記録あり）
- 既存リストが非互換の場合、リストを直さずに終了する（自動修復はしない）
- 手動トリガーのため**トリガーレベルの同時実行制御は行えない**。競合対策は
  「作成直前の再確認」「`MessageId` の一意制約」「作成失敗時の再検索フォールバック」
  「`Apply to each` の並列オフ」による緩和にとどまる
- 個別リストのビューURL（`/Lists/<名前>/AllItems.aspx`）は `/_layouts/` を含まないため
  サイトURLとして切り出せない（[docs/url_parsing_spec.md](docs/url_parsing_spec.md) に限界として記載）

### 【要実環境確認】
- **インポート・保存・実行のいずれも未実施**
- `GetEmailsV3` のパラメータキー名（`folderPath` / `fetchOnlyUnread` / `includeAttachments` / `mailboxAddress` / `top`）
- `GetEmailsV3` の既定の並び順（自前で降順ソートするが、コネクタが古い順にN件返す場合は最新N件にならない）
- `createFieldAsXml` での `EnforceUniqueValues="TRUE"` の反映可否（作成後に検証して結果へ記録する設計）
- `HtmlToText` の出力形とDLP適合
- Outlook の `from` フィールドが文字列（アドレス）か、オブジェクトか
- 3コネクタ構成での接続再マッピング（本リポジトリの実績は**接続1本**の構成のみ）

---

## 17. 関連

- [handbook/rules/00_power_automate_core_rules.md](../../handbook/rules/00_power_automate_core_rules.md) — 最重要8ルール
- [handbook/knowledge/sharepoint_rest_list_provisioning.md](../../handbook/knowledge/sharepoint_rest_list_provisioning.md) — REST形式の正典
- [handbook/knowledge/error_catalog.md](../../handbook/knowledge/error_catalog.md) — 既知エラー
- [projects/create_initialized_sharepoint_list/](../create_initialized_sharepoint_list/) — 動的サイト＋RESTリスト作成の土台
- [projects/teams_post_url_flows/](../teams_post_url_flows/) — Scope Try/Catch と結果JSONの土台
