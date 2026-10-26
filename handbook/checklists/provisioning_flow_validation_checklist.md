# リスト作成フロー検証チェックリスト

SharePoint REST（`_api/web/lists`系）でリスト・列・ビューを自動作成するフローを検証するときに確認する項目。パターンの詳細は[../knowledge/sharepoint_rest_list_provisioning.md](../knowledge/sharepoint_rest_list_provisioning.md)を参照。

## パッケージ構造
- [ ] フロー資産GUID（ルートmanifest.jsonのresourcesキー＝Microsoft.Flow/flowsのフォルダ名＝assetPaths）が3点一致していることを確認した

## SchemaXml・列定義
- [ ] 全SchemaXmlがXMLとしてパース可能であることを確認した
- [ ] 型純度を確認した（Text/Note/Numberそれぞれに他型専用の属性が混在していないか）
- [ ] SchemaXmlのDisplayNameとNameが一致していることを確認した
- [ ] Name属性がASCII英数字のみであることを確認した（内部名の安定化のため）

## 消費側フローとの列突合
- [ ] projects/migrate-chat-spo/check_compat.pyを実行し、消費側フロー（このリストを使うフロー）との列・型・サイトが完全互換であることを確認した

## 冪等性
- [ ] 列作成がFilter＋Ifガード（該当列が0件のときのみ作成）で、2回実行しても列が重複しないことを確認した
- [ ] リストが既存の場合でもGetByTitleで処理を継続できるよう、直後アクションのrunAfterが4ステータス（Succeeded/Skipped/Failed/TimedOut）すべてに設定されていることを確認した

## 匿名化・固有トークン
- [ ] 参照元フロー由来のKnowledge固有トークン（サンプル名・列名等）の残存が0件であることを確認した

## 実環境確認
- [ ] 初回実行でリストが想定件数作成され、列・既定ビューが期待どおりであることを確認した（本案件はリスト2・列22）
- [ ] 2回目実行で冪等性を確認した（列の重複が無いこと。リスト作成アクションの失敗表示は正常な挙動であることを運用者に周知した）

関連: [../knowledge/sharepoint_rest_list_provisioning.md](../knowledge/sharepoint_rest_list_provisioning.md) / [../knowledge/error_catalog.md](../knowledge/error_catalog.md) / [import_save_validation_checklist.md](import_save_validation_checklist.md)
