# make_automate_flow — Power Automate開発基盤

Power Automateクラウドフローを**作る・直す・検証する・知識を貯める**ためのリポジトリ。
migrate-chat-spo案件（Teams課内会議アーカイブ）の実経験——インポートエラー・保存エラー・実行時エラー計7件の解決を含む——を土台に構築し、以降の案件で得た知見を随時 handbook へ還元している。

## 1. 全体構成

```text
make_automate_flow/
├── README.md            ← 本ファイル（入口）
├── CLAUDE.md            ← Claude Code向け作業規範（不変則・Skill索引）
├── .claude/             ← Skill（定型作業）と Agent（専門役割）
├── handbook/            ← 案件横断の再利用知識
│   ├── rules/           ← 必ず守る開発ルール（00が入口）
│   ├── knowledge/       ← エラーカタログ・Tips・式例・教訓・パターン集
│   ├── checklists/      ← 工程別チェックリスト（READMEに8工程対応表）
│   └── templates/       ← 新規案件・フロー用の雛形
├── tools/               ← 案件横断の汎用スクリプト
│   ├── gen_outline.py   ← definition.json → 実行順アウトライン
│   ├── pack_package.py  ← 展開形パッケージ → インポートZIP
│   ├── wdl_eval.py      ← WDL式のミニ評価器（式ロジックをオフライン検証）
│   ├── wdl_lint.py      ← **案件横断の共通リンター**（定義とMarkdownの汎用検査。`--all .` で一括）
│   ├── doc_audit.py     ← **文書整合性の監査**（リンク・参照・数値・Skill名の突合）
│   └── gen_audit_docx.py ← 監査の正本 → 報告DOCX
├── audit/               ← 文書監査の正本と成果物（→ [audit/README.md](audit/README.md)）
│   ├── confirmations.json ← 実行者への確認事項の正本（ID・状態を継続追跡）
│   ├── findings/        ← 回次ごとの監査記録
│   └── dist/            ← 生成された報告DOCX
├── references/          ← **リポジトリ共通**の参照資料（編集禁止）
│   ├── raw/             ← 受領・実環境エクスポートの原本ZIP
│   ├── extracted/       ← 読み取り専用の展開結果
│   └── *.md             ← 解析証跡（公式資料調査・サンプル解析・参照メモ）
├── projects/            ← 案件固有資料（1案件=1フォルダ、フローごとに分離）
│   ├── migrate-chat-spo/                  ← Teams課内会議アーカイブ（SharePoint保存）
│   ├── teams_post_url_flows/              ← Teams投稿URLから投稿／全返信／リアクションした人を取得（独立3フロー）
│   ├── create_initialized_sharepoint_list/ ← 初期化済みSharePointリストを安全に作成
│   ├── sync-shared-mailbox-to-sharepoint-list/ ← 共有メールボックスのメールをSPOリストへ同期
│   └── teams-channel-member-sync/         ← Teamsチャネルのメンバーを毎日SPOリストへ同期
└── _legacy/             ← 旧構成の退避・再編記録・スナップショット
```

案件の一覧と実環境での確認状況:

| 案件 | 内容 | コネクタ | 実環境 |
|---|---|---|---|
| [migrate-chat-spo](projects/migrate-chat-spo/) | Teams会議投稿をSharePointへアーカイブ／台帳リスト作成 | Teams・SharePoint・Content Conversion | インポート・保存・実行 成功（v10の再実行は未確認） |
| [teams_post_url_flows](projects/teams_post_url_flows/) | Teams投稿URLから投稿（Flow1）／全返信（Flow2）を取得／リアクションした人を表示名・メール付きで一覧化（Flow3） | Teams | Flow1・Flow2 は**インポート・実行 成功**（2026-07-24。返信51件超のページングは未確認）。**Flow3 は未実施**（オフライン検証は全緑。メンバー一覧の権限は要実環境確認） |
| [create_initialized_sharepoint_list](projects/create_initialized_sharepoint_list/) | 同名リストが無い場合だけリストを作成し `sample_raw` のみに初期化 | SharePoint | **インポート・実行 成功**（2026-07-24・`status: Created`。同名リスト経路と失敗経路は未確認） |
| [sync-shared-mailbox-to-sharepoint-list](projects/sync-shared-mailbox-to-sharepoint-list/) | 共有メールボックスの最新メールをSharePointリストへ登録／更新（メッセージIDで冪等）。**3フロー: 5列版／審査官名・出願番号の推定付き7列版／審査官名簿と突合してメールアドレス・TeamsユーザーIDまで取得する12列版** | SharePoint・Office 365 Outlook・Content Conversion | 5列版は**インポート・実行 成功**（2026-08-03。100件同期＝作成80/更新20/失敗0）。**7列版・12列版は未実施** |
| [teams-channel-member-sync](projects/teams-channel-member-sync/) | Teamsチャネルのメンバーを毎日SharePointリストへ同期（同期キーで冪等・離脱は論理無効化）。**2フロー: 初期設定＋テスト同期（手動）と日次実行（Recurrence 07:00 JST）**。同期処理は `shared/sync_blocks.py` から両フローへ生成 | Teams・SharePoint | **未実施**（オフライン検証は全緑。`ListMembers` の body キー名は要実環境確認） |

## 2. 共通知識と案件固有資料の違い（**分離の原則の正本**）

- **handbook/** = どの案件でも通用する知識。実値（Team ID・サイトURL・接続GUID・メール）は書かず `{teamId}` 等のプレースホルダーを使う
- **projects/** = 案件の実値・設計・ソース・成果物。案件資料だけでフローを構築できる完結性を保つ（一般論はhandbookへのリンク）

この節が汎用／案件固有の切り分けの正本。knowledge-update Skill と knowledge-curator Agent はここを基準に判断する。

## 3. 各フローの標準構成（projects/<案件>/flows/<フロー>/）

| フォルダ | 中身 | 扱い |
|---|---|---|
| `spec/` | 仕様書原本・設計TXT・実装/インポートガイド・事実シート | 人間が読む設計資料 |
| `source/` | `build_*.py`（生成）・`validate_*.py`（検証）・`package/`（生成された展開形） | **唯一の編集元** |
| `validation/` | 検証レポート・アウトライン・実行証跡 | 検証のたびに更新 |
| `release/` | インポート用の日時付きZIPのみ | 検証済みのみ配置 |

参照資料はリポジトリ直下の [`references/`](references/) に集約している（`raw/` に原本ZIP、`extracted/` に展開結果。いずれも**編集禁止**）。案件配下には置かない。

### フロー対応表（**Skill／Agentが対象を特定するときの正本**）

各Skillはこの表を参照してフローと生成・検証スクリプトを特定する。**この表を他ファイルへ複製しない**（フロー追加時の更新漏れを防ぐため、正本はここ1箇所）。

| 案件 | フロー | build（編集元） | validate（検証の正典） |
|---|---|---|---|
| migrate-chat-spo | archive-meetings | `build_package.py` | `validate_definition.py` |
| migrate-chat-spo | provision-archive-lists | `build_list_package.py` | `validate_list_definition.py` |
| teams_post_url_flows | flow1-get-channel-post | `build_flow1.py` | `validate_flow1.py` |
| teams_post_url_flows | flow2-get-post-replies | `build_flow2.py` | `validate_flow2.py` |
| teams_post_url_flows | flow3-list-post-reactors | `build_flow3.py` | `validate_flow3.py` |
| create_initialized_sharepoint_list | create-initialized-list | `build_list_flow.py` | `validate_list_flow.py` |
| sync-shared-mailbox-to-sharepoint-list | sync-mail-to-list | `build_sync_flow.py` | `validate_sync_flow.py` |
| sync-shared-mailbox-to-sharepoint-list | sync-mail-to-list-with-examiner-detection | `build_examiner_flow.py` | `validate_examiner_flow.py` |
| teams-channel-member-sync | setup-and-test-sync | `build_setup_flow.py` | `validate_setup_flow.py` |
| teams-channel-member-sync | daily-member-sync | `build_daily_flow.py` | `validate_daily_flow.py` |

いずれも `projects/<案件>/flows/<フロー>/source/` 配下。フローを追加したらこの表を更新し、`python tools/doc_audit.py` で整合を確認する。

## 4. ソースからrelease ZIPを作る流れ

```text
source/build_*.py を編集
  → python source/build_*.py        （package/ を再生成）
  → python source/validate_*.py     （静的検証。全緑が必須。共通検査は tools/wdl_lint.py を import）
  → python tools/wdl_lint.py --all . （案件横断の共通リンター。指摘0件が必須）
  → python tools/gen_outline.py source/package/.../definition.json validation/action_outline.txt
  → python tools/pack_package.py source/package release/<フロー名>_YYYYMMDDHHMMSS.zip
  → handbook/checklists/import_save_validation_checklist.md で確認
```

完成ZIPを直接編集する運用はしない。definition.jsonはすべて生成物。

## 5. よくある作業の入口

| やりたいこと | 使うもの |
|---|---|
| エラーが出た | **flow-error-fix Skill**（貼り付けるだけ）→ [handbook/knowledge/error_catalog.md](handbook/knowledge/error_catalog.md) の索引 |
| 新しいフローを作る | **flow-create Skill** → [handbook/templates/flow_design_template.md](handbook/templates/flow_design_template.md) |
| 既存フローを直す | **flow-update Skill** → [handbook/checklists/flow_update_checklist.md](handbook/checklists/flow_update_checklist.md) |
| ZIPを検証する | **flow-package-validate Skill** |
| ZIPを配布する | **flow-release Skill** |
| 知見を残す | **knowledge-update Skill** → [handbook/checklists/README.md](handbook/checklists/README.md) |
| 文書の食い違いを直す | **doc-audit Skill** → [audit/README.md](audit/README.md) |

Agentの役割: flow-architect（設計）/ flow-debugger（エラー原因調査。同型全数リスト必須）/ package-auditor（パッケージ構造検証）/ knowledge-curator（知識整理）。
doc-audit はスクリプト検査が主体のため専用Agentを持たない。

## 6. 新規案件・新規フローの追加方法

1. `projects/<案件名>/` を作成し、[handbook/templates/](handbook/templates/) の雛形で README と設計書を起こす
   - 案件フォルダ名はケバブケースを既定とする（例 `migrate-chat-spo`）。依頼側で名称が指定されている場合はそれに従ってよい（実例: `teams_post_url_flows` / `create_initialized_sharepoint_list`）
   - **フローフォルダ名はケバブケースに統一する**（例 `archive-meetings` / `flow1-get-channel-post` / `create-initialized-list`）
2. フローごとに `flows/<フロー名>/{spec,source,validation,release}/` を作成（§3の標準構成）
3. 生成スクリプトの雛形を複製・改修する。コネクタが複数なら `projects/migrate-chat-spo/flows/archive-meetings/source/build_package.py`、**単一コネクタの単純構成なら `projects/teams_post_url_flows/flows/flow1-get-channel-post/source/build_flow1.py`**（Teams1本・実環境インポート/実行実績あり）
4. 設計時に [handbook/rules/00_power_automate_core_rules.md](handbook/rules/00_power_automate_core_rules.md) と [handbook/checklists/design_review_checklist.md](handbook/checklists/design_review_checklist.md) を通す

## 7. 最初に読むルール

| 優先 | ファイル | 内容 |
|---|---|---|
| ★ | [handbook/rules/00_power_automate_core_rules.md](handbook/rules/00_power_automate_core_rules.md) | 最重要8ルール＋既知エラー表 |
| ★ | [handbook/rules/03_variables_arrays_and_objects.md](handbook/rules/03_variables_arrays_and_objects.md) | SetVariable自己参照禁止と型別更新 |
| ★ | [handbook/rules/02_expression_and_type_safety.md](handbook/rules/02_expression_and_type_safety.md) | @規則・trim/coalesce・null安全 |
| 　 | [handbook/rules/07_export_import_package_rules.md](handbook/rules/07_export_import_package_rules.md) | パッケージ構造・インポート後の即保存テスト |
| 　 | [handbook/knowledge/sample_flow_reference_index.md](handbook/knowledge/sample_flow_reference_index.md) | 参照サンプルの索引と注意（「実働=正しい」ではない） |

実際に発生した既知エラー**10件**（全文・再現・回避策は[エラーカタログ](handbook/knowledge/error_catalog.md)の冒頭索引から該当節へ）:

| # | 発生局面 | 症状 | 根本原因 |
|---|---|---|---|
| 1 | インポート時 | `'@' at position ... is not expected` | ネストした関数に `@` を付けた |
| 2 | **保存時** | `Self reference is not supported` | SetVariable が自身の変数を参照 |
| 3 | インポート前（事前検出） | アクション名の全体重複 | 初期化用とループ更新用が同名 |
| 4 | 実行時（監査で事前検出） | コネクタ出力の参照が常に null | `outputs('X')?['f']` は封筒。`body('X')?['f']` が正 |
| 5 | **保存時** | `OpenApiOperationParameterValidationFailed`（`item` 欠落） | PostItem のサイト/リストを式にした |
| 6 | 実行時 | `404 File not found` | 添付の `contentUrl` と `dataset` のサイト不一致 |
| 7 | 実行時（データとして顕在化） | 台帳が全件 Failed | CreateFile が中間フォルダを作らない／GetFileItem のライブラリ名前解決 |
| 8 | インポート時 | `Unable to parse template language expression ...: expected token 'LeftParenthesis'` | **表示テキスト**（入力の説明文）中の `@{tenant}` が式として解釈された |
| 9 | 実行時 | リスト列挙だけが 403（`_api/web` は200） | コレクション列挙の `$expand` に `$select` の投影が無く、権限の無いシステムリストを実体化した |
| 10 | 実行時 | `substring parameter is out of range: 'start index' ...` | 開始位置は文字列長より**小さい**必要があり、空文字には `substring('', 0, 0)` すら適用できない |

エラー2・5は「**インポートは成功したが保存で落ちる**」型、エラー6・7は「**保存も成功したが実行で落ちる**」型。§8の2つの原則はこの経験から来ている。
エラー1・8は「**式は全部正しいのにインポートで落ちる**」型。8は式ですらない説明文が原因で、
「`@` の直後が `{` なら正当な補間」とみなす検査の穴から漏れた（検査を追加済み）。

## 8. 検証方法

- 静的検証: 各フローの `source/validate_*.py`（保存可能性の機械検査の**正典**。エラー0・警告0が完成条件）
- 共通リンター: [tools/wdl_lint.py](tools/wdl_lint.py)（`python tools/wdl_lint.py --all .` で定義とMarkdownを一括検査。各 `validate_*.py` からも import する）
- 文書整合: [tools/doc_audit.py](tools/doc_audit.py)（`python tools/doc_audit.py`。リンク・参照先・数値・Skill名の突合）
- ZIP再展開検査: 各フローの `validation/extract_check.py`（5ファイル構造・GUID3点一致・`source/package` とのSHA-256一致）
- 式ロジックの回帰テスト: 各案件の `tests/run_url_parse_tests.py` ＋ [tools/wdl_eval.py](tools/wdl_eval.py)
  （**生成済み `definition.json` の式そのもの**をオフライン評価する。設計書の再実装を検証しない）
- フロー間整合: `projects/migrate-chat-spo/check_compat.py`（リスト作成⇔アーカイブの列突合）
- 工程別: [handbook/checklists/README.md](handbook/checklists/README.md) の8工程対応表
- 原則: **インポート成功≠完成**。インポート後は 開く→即保存→フローチェッカー→小規模テスト
- 原則: **実行成功≠結果が正しい**。完走しても対象データが全件失敗していた事例がある（[エラーカタログ](handbook/knowledge/error_catalog.md)）。出力の中身まで確認する

## 9. 参照サンプルと_legacyの扱い

- [`references/raw/`](references/raw/) の原本ZIPは**編集・上書き禁止**。展開が必要なら [`references/extracted/`](references/extracted/) 配下のみ
- 参照資料は**リポジトリ直下の `references/` に集約**する（2026-07-24 に `projects/migrate-chat-spo/references/` から移動。案件をまたいで参照するため）
- サンプルに含まれる実装を「実働だから正しい」とみなさない（[索引](handbook/knowledge/sample_flow_reference_index.md)に流用禁止箇所を記載）
- `_legacy/` は旧構成・歴史資料の退避場所。旧パス（dist/・build/・doc/・flow/等）の読み替えは [_legacy/2026-07-reorg-survey.md](_legacy/2026-07-reorg-survey.md) の対応表を参照

## 10. 知識を更新する方法

案件完了・エラー解決のたびに **knowledge-update Skill** で還元する：
新規エラー→[error_catalog.md](handbook/knowledge/error_catalog.md)（追記書式あり）／教訓→[lessons_learned.md](handbook/knowledge/lessons_learned.md)／再利用式→[expression_examples.md](handbook/knowledge/expression_examples.md)／新サンプル→[sample_flow_reference_index.md](handbook/knowledge/sample_flow_reference_index.md)。
同じ内容は統合し、詳細は1箇所＋リンク。「今回たまたま動いた」を根拠なく一般化しない。

## 11. 文書の整合を保つ（定期監査）

文書・Skill・Agent・実装のズレは **doc-audit Skill** で定期的に検出・修正する。詳しい手順と正本の更新規則は [audit/README.md](audit/README.md)。

```text
python tools/doc_audit.py           # 機械検査（リンク・参照先・数値・Skill名・wdl_lint採用）
python tools/wdl_lint.py --all .    # 定義とMarkdownの共通リンター
python tools/gen_audit_docx.py      # 正本 → 報告DOCX を audit/dist/ へ生成
```

- 実行者本人にしか確定できない事項は [audit/confirmations.json](audit/confirmations.json) に `CONF-NNN` で登録し、状態（未確認／確認待ち／確認済み／対応不要）を継続追跡する
- 報告DOCXは**直接編集しない**。正本（confirmations.json ＋ `audit/findings/<日付>.md`）を直してから再生成する
