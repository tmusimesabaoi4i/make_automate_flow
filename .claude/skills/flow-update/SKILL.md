---
name: flow-update
description: 既存のPower Automateフローの仕様・アクション・式を変更するときに使う。「フローを修正」「アクションを追加」「式を変えたい」「保存先を変えたい」等がトリガー。変更前後の検証結果とアウトラインを比較し、同型検索と spec 更新まで行う。
---

# flow-update — 既存フロー修正

## 不変則（全Skill共通・厳守）
definition.json は生成物。修正は必ず source/ の build_*.py を編集→再生成→検証。source/package/ の直接編集、references/・release/ 内の既存ZIPの上書き、原本（references/raw/・spec/の受領docx）の変更は禁止。Git操作は一切行わない。

## いつ使うか
既に存在するフローの仕様・アクション・式・保存先などを変更するとき。
エラー修正が主目的なら flow-error-fix、新規作成なら flow-create を使う。

## 駆動チェックリスト
主表は `handbook/checklists/flow_update_checklist.md`（既存フロー修正の専用チェックリスト）。加えて:
- 変更が式・型に及ぶとき: `handbook/checklists/expression_type_checklist.md`。
- 再パッケージ時の機械検証: `handbook/checklists/import_save_validation_checklist.md`。
- リリースに進むとき: `handbook/checklists/release_checklist.md`。
- 設計に踏み込む変更: `handbook/checklists/design_review_checklist.md`。

## 手順

### 1. 対象特定
ルート `README.md` §3 の**フロー対応表**から、対象フローと `build_*.py` / `validate_*.py` を特定する（全案件・全フローが対象）。
- 対象は `projects/<案件>/flows/<フロー>/source/`。

### 2. 変更前の記録（ベースライン）
変更前に、後段の前後比較の基準を保存する。
- `python source/validate_*.py`（対応表で特定したもの）の結果。
- `python tools/wdl_lint.py --all .` の結果。
- `python tools/gen_outline.py <definition.json> <出力txt>` のアウトライン。

### 3. 要件確認
変更が業務的意味（列構成・判定条件・保存先・期間）を変えるかを見極める。変えるなら停止条件へ。

### 4. source修正
変更を `source/` の `build_*.py` に入れる。
- 定義（definition.json）や `source/package/` を直接編集しない。
- 変更前の該当行を引用記録する。

### 5. 再生成
`python source/build_*.py`（引数なし）で `source/package/` を再生成する。

### 6. 前後比較
変更後の `validate_*.py`（全緑）・`tools/wdl_lint.py --all .`（指摘0件）・`gen_outline.py` の結果を、(2) のベースラインと差分比較する。
- 意図した差分のみか。
- 意図しない副作用（アクション名の重複・runAfter 切れ・未参照変数）が出ていないか。

### 7. 同型検索
今回の変更と同じパターン（同種の式・同種のアクション）が、**全案件・全フロー**の定義・生成スクリプトに他にも無いか機械走査し、必要なら同時に整合させる。
- 対象は対応表の全フロー。修正したフローだけを見て終わらせない。
- 汎用化できる検査なら `tools/wdl_lint.py` へ追加して再発を機械的に閉じる。

### 8. spec更新
変更が事実（仕様）に及ぶ場合、`projects/<案件>/flows/<フロー>/spec/` を更新する。
- 例: archive-meetings の `spec/SINGLE_FLOW_FACTS.md`。
- 案件の `README.md` / `docs/` に同じ事実（列構成・件数・実環境確認状況）が書かれていれば併せて更新する。
- 定義と資料の乖離を残さない。

### 9. パッケージ・リリース
必要なら `python tools/pack_package.py <package_dir> <output.zip>` で再ZIP化する。
- 機械検証節を通し、`<フロー名>_YYYYMMDDHHMMSS.zip` を `release/` へ配置する。
- 正式なリリースは flow-release Skill に委ねる。

## 変更の型と着眼点
よくある変更ごとに、特に確認すべき点を挙げる。
- **アクション追加**: 表示名がフロー全体で一意か、runAfter を既存の兄弟に正しくつないだか。
- **式の変更**: `@` の位置（先頭・`@{}` 補間のみ）、trim/coalesce の対象型、`body('X')?['field']` 参照か。
- **保存先/リスト変更**: 業務的意味の変更に当たるため停止条件を確認。`PostItem` を動的サイト/リストと併用していないか。
- **変数の追加/更新方式変更**: トップレベル初期化か、蓄積が Append/Increment 系か（自己参照でないか）。
- **ページング/期間変更**: 実行時間30分制限に収まるか、nextLink 追跡が保たれているか。

## 守る点（詳細は handbook 参照）
- 変数はトップレベル初期化、蓄積は Append/Increment 系（SetVariable自己参照禁止）。
- コネクタ出力は `body('X')?['field']`。式の `@` はネスト関数に付けない。
- 標準コネクタのみ。プレミアム・アプリ登録・管理者同意を新たに前提化しない。
- 検証は「静的緑」で完成としない。実環境確認が必要な項目は残リスクとして明記する。

## 停止条件（ユーザーへ確認する）
- 変更が業務的意味を変える（列・判定条件・保存先・対象期間の変更等）とき。
- 原本（`references/raw/`・`spec/` の受領docx）の変更が必要に見えるとき。
- 実環境でしか妥当性を確認できない変更のとき。
- 要件が曖昧で複数の解釈が成り立つとき。**推測で仕様を確定させず**、解釈の候補と影響を示して確認する。

## 連携（他Skill/Agentとの関係）
- 変更の主目的がエラー解消なら flow-error-fix、新規作成なら flow-create へ切り替える。
- 変更後の深い検証は flow-package-validate Skill / package-auditor Agent へ。
- 最終ZIPの確定・配置は flow-release Skill へ。
- 一般化できる知見は knowledge-update Skill で handbook へ還元する。

## 完了報告
変更前後の差分要約、同型検索の結果、更新した spec、検証結果、残リスクを報告する。
一般化できる知見は knowledge-update Skill で還元する。
