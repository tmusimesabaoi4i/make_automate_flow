# リリース前チェックリスト

本番リリース前に確認する項目。テスト用設定・実データへの影響・機密情報の混入を中心に確認する。関連ルール: [../rules/08_error_handling_and_idempotency.md](../rules/08_error_handling_and_idempotency.md)

- [ ] 実データを削除する処理が本番リリース前提で正しく動作するか確認した（取得前に全削除するアンチパターンになっていないか。[../knowledge/sample_flow_reference_index.md](../knowledge/sample_flow_reference_index.md)参照）
- [ ] テスト用に入れていた仮の値・仮のスキップ処理・デバッグ用アクションを除去したか確認した
- [ ] DryRun等のテスト実行トリガー入力の既定値が、本番運用として適切か確認した
- [ ] 接続先（Teams/SharePoint等）・保存先（サイト・ライブラリ・フォルダパス）が実際の本番環境を指しているか確認した
- [ ] フロー定義・ドキュメント・ログ出力に認証情報・トークン・パスワードが含まれていないか確認した
- [ ] エラーログ・実行ログの出力内容に、個人情報・機密情報がそのまま記録されないか確認した
- [ ] 実環境で未検証の事項（インポート挙動・URL取得式・添付取得パス解析等）を運用者に明記して引き継いだか確認した
- [ ] 大量データ実行時のフロー実行時間上限・段階的テスト（小期間→大期間）の実施計画を確認した
- [ ] 冪等性（再実行しても重複しないこと）を本番相当データで確認したか確認した
- [ ] 個別要素の失敗が全体を止めず、失敗記録（Status=Failed等）が残ることを確認した

関連: [import_save_validation_checklist.md](import_save_validation_checklist.md) / [../knowledge/error_catalog.md](../knowledge/error_catalog.md)
