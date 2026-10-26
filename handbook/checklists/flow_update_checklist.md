# 既存フロー修正チェックリスト

既に本番投入済み・検証済みのフローを修正するときに確認する項目。1箇所の修正で満足せず、影響範囲と同型パターンを全数洗い出すことを目的とする。関連ルール: [../rules/00_power_automate_core_rules.md](../rules/00_power_automate_core_rules.md)

## 修正前
- [ ] 修正はsource/配下のbuild_*.py（生成スクリプト）側で行うことを確認し、definition.jsonを直接編集していないか確認した
- [ ] 変更前のvalidate_*.py実行結果と、tools/gen_outline.pyで生成したアウトラインを保存した（変更後の差分比較の基準にする）

## 影響範囲の洗い出し
- [ ] 変更する式・アクション名・変数がフロー全体で参照されている箇所をすべてgrep等で洗い出した
- [ ] 同型パターン（同じ処理・同じ誤りが他にもないか）を全数検索した（1箇所直して終わりにする「もぐら叩き」を防止した）

## 修正後
- [ ] 変更後にvalidate_*.pyを実行し、エラー・警告とも0件（全緑）であることを確認した
- [ ] tools/gen_outline.pyのアウトライン差分が、意図した変更のみであることを確認した（意図しない箇所の変化が無い）
- [ ] spec/配下の事実シート・ガイド（SINGLE_FLOW_FACTS.md等）を修正内容に合わせて更新した

## パッケージ化・配置
- [ ] build_*.pyを再実行して再パックし、生成ZIPを再展開して内容を確認した
- [ ] 確認済みZIPをrelease/へ日時付きファイル名で配置した

関連: [../rules/00_power_automate_core_rules.md](../rules/00_power_automate_core_rules.md) / [../knowledge/error_catalog.md](../knowledge/error_catalog.md) / [import_save_validation_checklist.md](import_save_validation_checklist.md)
