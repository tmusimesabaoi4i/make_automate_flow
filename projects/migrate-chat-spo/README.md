# migrate-chat-spo — Teams課内会議のSharePointアーカイブ

## 案件の目的

大規模システム移行を前に、Teamsチャネル「03_課内会議」の**過去2年分の会議投稿・返信・添付ファイル**を一括取得し、
添付をSharePointへ保存、会議ごとの総括Word（HTMLベース.doc）を生成、処理台帳・実行ログを記録する。
定期実行ではなく**一回性の移行処理**（LookbackDaysで期間指定・段階テスト 7→30→365→730日）。

## 含まれるフロー（2本）

| フロー | 表示名 | 役割 | 実行順 |
|---|---|---|---|
| [flows/provision-archive-lists/](flows/provision-archive-lists/) | CreateMeetingArchiveLists | 台帳 `MeetingArchiveLedger`・実行ログ `MeetingArchiveRunLog` の2リストを自動作成（列・既定ビュー含む。冪等） | **1番目** |
| [flows/archive-meetings/](flows/archive-meetings/) | Teams課内会議アーカイブ | 本体。Teams投稿取得→添付保存→Word生成→台帳・ログ記録 | 2番目 |

両フローの互換性（リスト名・列名・型・サイト）は [check_compat.py](check_compat.py) で機械突合できる（完全互換を検証済み）。

## 各フローの編集対象・成果物

| | archive-meetings | provision-archive-lists |
|---|---|---|
| 編集用ソース | `flows/archive-meetings/source/build_package.py` | `flows/provision-archive-lists/source/build_list_package.py` |
| 静的検証 | 同 `source/validate_definition.py` | 同 `source/validate_list_definition.py` |
| 設計資料 | `flows/archive-meetings/spec/`（仕様書docx原本・設計TXT・実装/インポートガイド・SINGLE_FLOW_FACTS.md） | `flows/provision-archive-lists/spec/` |
| 検証結果 | `flows/archive-meetings/validation/`（検証レポート・アウトライン・実行証跡run-evidence/） | `flows/provision-archive-lists/validation/` |
| **完成ZIP** | `flows/archive-meetings/release/`（日時付き） | `flows/provision-archive-lists/release/` |

**definition.jsonは生成物**。修正は必ず `source/build_*.py` → 再生成 → 検証（ルートの [CLAUDE.md](../../CLAUDE.md) 不変則）。

## 参照サンプル（[`references/`](../../references/)・編集禁止）

参照資料は **2026-07-24 にリポジトリ直下の [`references/`](../../references/) へ移動**しました（案件をまたいで参照するため）。本案件で使ったのは次の3件です。

| 原本（`references/raw/`） | 内容 | 展開（`references/extracted/`） |
|---|---|---|
| tmp_20260716051507.zip | レガシー雛形（Teams Graph HTTP＋SPO HTTPの実例） | sample_extracted_ref/ |
| create_meeting_list_sample_20260716105612.zip | 実働サンプル（参考にした点と設計バグは [sample_export_analysis.md](../../references/sample_export_analysis.md)） | create_meeting_list_sample_ref/ |
| CreateKnowledgeList_20260716161116.zip | リスト自動作成の参照フロー（SharePoint RESTの正典） | reference_original/ |

公式資料の調査結果は [references/official_reference_findings.md](../../references/official_reference_findings.md)。
各サンプルの「参考にできる点／流用してはいけない点」は [handbook/knowledge/sample_flow_reference_index.md](../../handbook/knowledge/sample_flow_reference_index.md) に集約しています。

## 検証方法

1. `python flows/<フロー>/source/validate_*.py` → 全緑（保存可能性の機械検査）
2. `python check_compat.py` → 完全互換・不一致0件
3. `python ../../tools/gen_outline.py flows/archive-meetings/source/package/Microsoft.Flow/flows/fcca0e31-6d8b-40a8-8d63-2441c979a2c7/definition.json flows/archive-meetings/validation/action_outline.txt` → 設計TXTと139アクション突合（validation/のextract_check.py＋compare_outline.py）
4. 工程別チェック: [../../handbook/checklists/README.md](../../handbook/checklists/README.md)

## インポート手順（実施順）

1. **リスト作成フローを先に**: provision-archive-listsのrelease ZIPをインポート→SharePoint接続→開いて保存→実行→pjteamサイトに2リスト・列・ビューを確認→**2回目実行で冪等確認**（「リスト作成」失敗表示は既存のためで正常）
2. **本体フロー**: archive-meetingsのrelease ZIPをインポート→3接続（Teams/SharePoint/Content Conversion）→開いて**すぐ保存**→フローチェッカー→`LookbackDays=7・DryRun=はい`でテスト→`DryRun=いいえ`で添付保存とURL取得を確認→段階的に期間拡大
3. 詳細は [flows/archive-meetings/spec/power_automate_import_guide.md](flows/archive-meetings/spec/power_automate_import_guide.md)

## 環境依存事項（インポート後に確認・変更する値）

| 項目 | 値 | 変更箇所 |
|---|---|---|
| リスト所在サイト | pjteam_220400119 | varListSiteAddress ＋ REST4アクションの静的dataset |
| ファイル保存サイト | mROOM_240600018 | varSiteAddress（添付・総括docの保存先） |
| Team ID / Channel ID | varTeamId / varChannelId | 初期化変数 |
| 保存先フォルダー | 123_伝送システム/…/99_過去の課内会議 | varDestinationPath |
| リスト名 | MeetingArchiveLedger / MeetingArchiveRunLog | varLedgerList / varRunLogList |
| 添付の取得元 | contentUrlから自動導出（設定不要） | — |

※Teamsチャネルの添付は**チームのサイト**（pjteam）に保存される。ファイル保存先（mROOM）とは別サイトである点が本案件の重要な構成（詳細: spec/実装ガイド10章）。

## 実環境での確認状況（正直な記載）

現行版は **v10**（`source/build_package.py` が生成する版）。

- v8: インポート・保存・実行・RESTによるログ書き込み（201）まで**実環境で到達済み**
- v9（添付取得のクロスサイト404修正・添付有無分岐）: **実環境でエンドツーエンド実行に成功したが、添付が全件 `Status=Failed`** になった（エラー7の出所）
- **v10（現行版）**: v9の全件Failedへの対処（保存先フォルダの事前確保・`GetFileItem` 廃止・保存後URLの決定的構築）。
  **静的検証は全緑だが、実環境での再実行は未実施**（要実環境確認）
- 経緯の詳細は [flows/archive-meetings/spec/power_automate_import_guide.md](flows/archive-meetings/spec/power_automate_import_guide.md) 冒頭の注意書き
- 未検証事項の全リストは [flows/archive-meetings/validation/package_validation_report.txt](flows/archive-meetings/validation/package_validation_report.txt) 末尾

## 履歴資料

- [_legacy/multiflow_design/](_legacy/multiflow_design/) — 旧5フロー構成の設計（単一フロー化前）
- [_legacy/CANONICAL_REFERENCE.md](_legacy/CANONICAL_REFERENCE.md) / [_legacy/knowledge_base_brief.md](_legacy/knowledge_base_brief.md) — 旧正典・handbook執筆の出所記録
