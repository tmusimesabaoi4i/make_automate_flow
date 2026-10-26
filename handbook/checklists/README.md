# チェックリスト索引

Power Automateフロー開発の8工程それぞれで、どのチェックリスト（またはその節）を使うかの対応表。各項目の詳細は個別ファイルを参照。

| 工程 | 参照先 |
|---|---|
| 1. 設計開始前 | [design_review_checklist.md](design_review_checklist.md) |
| 2. 実装後 | [expression_type_checklist.md](expression_type_checklist.md) ＋ [import_save_validation_checklist.md](import_save_validation_checklist.md) §A |
| 3. ZIP生成前 | [import_save_validation_checklist.md](import_save_validation_checklist.md) §A（source検証: validate_*.py全緑・gen_outline突合・匿名化トークン0） |
| 4. ZIP展開後 | 同ファイル §B |
| 5. インポート前 | 同ファイル §C（環境準備） |
| 6. インポート後 | 同ファイル §D |
| 7. リスト作成フロー検証 | [provisioning_flow_validation_checklist.md](provisioning_flow_validation_checklist.md) |
| 8. 既存フロー修正 | [flow_update_checklist.md](flow_update_checklist.md) |

本番リリース直前は、工程6の後に[release_checklist.md](release_checklist.md)も通す。

関連: [../rules/00_power_automate_core_rules.md](../rules/00_power_automate_core_rules.md) / [../knowledge/error_catalog.md](../knowledge/error_catalog.md)
