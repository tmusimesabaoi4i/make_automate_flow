# フロー設計テンプレート (Flow Design Template)

新規フロー設計時に埋める項目テンプレート。各項目の下に記入ガイドを1行添える。
記入例は[projects/migrate-chat-spo/flows/archive-meetings/spec/PA_Migrate_Teams_Meeting_Archive_To_SPO.txt](../../projects/migrate-chat-spo/flows/archive-meetings/spec/PA_Migrate_Teams_Meeting_Archive_To_SPO.txt)を参照。関連ルール: [../rules/00_power_automate_core_rules.md](../rules/00_power_automate_core_rules.md)

## 目的
（記入欄）
> ガイド: このフローが解決する業務課題を1〜2文で書く。

## 対象システム
（記入欄）
> ガイド: 連携するシステム・サービス名（例: Teams, SharePoint）を列挙する。

## トリガー
（記入欄）
> ガイド: 手動/自動、スケジュール、入力パラメータの種類と既定値を書く。

## 入力
（記入欄）
> ガイド: トリガー入力の内部名・表示名・型・既定値を一覧化する。

## 出力
（記入欄）
> ガイド: フローが最終的に作成・更新する成果物（ファイル・リスト項目等）を書く。

## 使用コネクタ
（記入欄）
> ガイド: コネクタ名・標準/プレミアムの別・使用するアクション（operationId）を列挙する。[../knowledge/connector_action_notes.md](../knowledge/connector_action_notes.md)参照。

## 権限
（記入欄）
> ガイド: 実行アカウントに必要な権限範囲を書く。管理者権限・アプリ登録が不要であることを確認して明記する。

## 変数
（記入欄）
> ガイド: 変数名・型・初期値・更新箇所・並列実行時の注意を一覧化する。

## Scope
（記入欄）
> ガイド: 処理をどうScope分割するか（例: 取得/処理/保存/ログ/例外処理）を書く。ネスト深さ上限8に注意。

## アクション
（記入欄）
> ガイド: 主要アクションを実行順に列挙する。詳細は[flow_action_definition_template.txt](flow_action_definition_template.txt)を1アクションずつ使う。

## 条件
（記入欄）
> ガイド: 分岐条件（Condition）とその判定式を書く。Boolean/数値の0を誤って未設定扱いしないか確認する。

## ループ
（記入欄）
> ガイド: Apply to each/Do untilの対象・終了条件・並列実行有無を書く。

## ページング
（記入欄）
> ガイド: 外部APIの1回あたり取得件数上限とページング方式（nextLink等）を書く。

## 冪等性
（記入欄）
> ガイド: 同じ入力で複数回実行しても重複が生じない仕組み（冪等キー等）を書く。

## エラー処理
（記入欄）
> ガイド: 全体catchと個別要素catchの2階層設計、失敗時の記録方法を書く。

## テスト
（記入欄）
> ガイド: 小期間・DryRun等でのテスト計画を書く。

## 制約
（記入欄）
> ガイド: 実行時間上限・Until上限・標準コネクタのみ等の制約事項を書く。
