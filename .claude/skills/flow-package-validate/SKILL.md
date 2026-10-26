---
name: flow-package-validate
description: 作成済みのZIP／展開済みPower Automateパッケージが保存・インポート可能かを検証するときに使う。「このパッケージを検証」「ZIPをチェック」「保存できるか確認して」等がトリガー。source/validate_*.py 実行とチェックリスト照合、package-auditor Agent 委任を行い、検証レポートを所定書式で出力する。
---

# flow-package-validate — パッケージ／展開形の検証

## 不変則（全Skill共通・厳守）
definition.json は生成物。修正は必ず source/ の build_*.py を編集→再生成→検証。source/package/ の直接編集、references/・release/ 内の既存ZIPの上書き、原本（references/raw/・spec/の受領docx）の変更は禁止。Git操作は一切行わない。

## いつ使うか
生成済みの `source/package/` や配布ZIPが「Power Automateにインポート後、開いて保存できるか」を検証したいとき。
修正はこのSkillでは行わず、検出したら flow-error-fix / flow-update へ回す。

## 使う資材（すべて実在）
- ルート `README.md` §3 の**フロー対応表**（対象フローと `validate_*.py` を特定する正本）。
- `source/validate_*.py`（保存可能性の機械検査の正典）。
- `tools/wdl_lint.py`（案件横断の共通リンター。各 `validate_*.py` もこれを import する）。
- `handbook/checklists/import_save_validation_checklist.md`。
- `handbook/templates/package_validation_report_template.txt`（出力書式）。
- `tools/gen_outline.py`。
- `projects/migrate-chat-spo/check_compat.py`（**migrate-chat-spo 専用**。同案件の2フローのリスト列突合にのみ使う。他案件には適用しない）。
- `references/extracted/`（構造差分の基準・編集禁止）。

## 手順

### 1. 対象確認
検証対象（`source/package/` か `release/` のZIP）と、対応する `source/` の生成スクリプトを特定する。
ZIPは展開して構造を見る（既存ZIPは上書きしない）。

### 2. 機械検証（正典）
`python source/validate_*.py`（README のフロー対応表で特定したもの）を引数なしで実行し、全緑を確認する。
- いずれも `source/package/` を検証する。
- 併せて `python tools/wdl_lint.py --all .` を実行し、指摘0件を確認する（定義とMarkdownの共通検査）。
- 対象の `validate_*.py` が `tools/wdl_lint.py` を import していない場合は、それ自体が指摘事項（チェックリスト §A 違反）。

### 3. 構造確認
- `python tools/gen_outline.py <definition.json> <出力txt>` でアクション構造を出力し、想定と一致するか確認する。
- **migrate-chat-spo の2フロー**（provision-archive-lists ⇔ archive-meetings）のリスト列互換を突合するときのみ `python projects/migrate-chat-spo/check_compat.py`（引数なし）を使う。他案件には対応する突合スクリプトは無い。

### 4. チェックリスト照合
`handbook/checklists/import_save_validation_checklist.md` の「パッケージ作成後（機械検証）」節を通す。

### 5. 深い監査を委任（package-auditor Agent）
実行検査（validate_*.py の観点）＋手動検査を実施させる。
- レガシー5ファイル構造。
- GUID3点一致。
- `references/extracted/` のサンプルとの構造差分。

### 6. レポート出力
`handbook/templates/package_validation_report_template.txt` の書式（§10 保存可能性監査の集計を含む）でまとめる。
検証していない項目を「成功済み」と書かない。

## 検証観点（package-auditor に委ねる機械検査の列挙）
汎用検査は `tools/wdl_lint.py`（L01〜L13）が機械的に閉じている。以下はその観点を含む監査項目の全体像。

- runAfter の参照先が同一コンテナ内の兄弟として実在する。
- アクション表示名がフロー全体で一意（重複0）。
- 変数の初期化数＝式内参照数の整合。未参照変数が無い。
- Initialize がトップレベルにある（ループ内初期化でない）。
- `body('X')` / `outputs('X')` の参照先アクションが実在し、コネクタ出力は `body` 系参照。
- SetVariable に自己参照が無い（0件必須）。
- 変数の重複初期化が無い。
- 接続参照（connectionReferences）と apisMap/connectionsMap/manifest resources のキーが整合。
- `operationId: PostItem` が残っていない（動的サイト/リスト併用の保存不可を排除）。
- REST（HttpRequest）のキー・封筒参照が正しい。
- コレクション列挙の `$expand` に `$select` の投影がある（無いと実行時403）。
- 変数を更新する Apply to each が並列オフ（concurrency=1）。
- プラットフォーム上限（アクション500 / ネスト8 / 変数250 / 1式8,192文字）に収まる。
- 匿名化トークン（実値ID・URL・メール混入なし）。

## 手動検査（package-auditor が併せて行う）
- レガシー5ファイル構造の充足。
- GUID3点一致: manifest の resources キー ＝ パッケージ内フォルダ名 ＝ assetPaths。
- `references/extracted/` の実働サンプルとの構造差分（余分ファイル混入・欠落）。

## 静的検査 vs 実環境（判定の考え方）
- **静的検査で判定できる**: 自己参照・重複名・runAfter 切れ・未参照変数・`PostItem` 残存・封筒参照・匿名化漏れ・構造差分。ここは validate_*.py と package-auditor で確定させる。
- **静的検査で判定できない（要実環境確認）**: クロスサイト参照の404、テナント設定に依存する `__metadata` 要求、実データでしか出ない null。これらは実行時検証が必須であり、レポートに「要実環境確認」と明記する。
- 「保存可能性の静的緑」を「実環境で保存・実行できる」と読み替えない。

## 停止条件
- 保存不可・破損が判明したら修正はこのSkillで行わず、原因節（`handbook/knowledge/error_catalog.md`）を添えて flow-error-fix / flow-update へ引き継ぐ。
- 実環境でしか判定できない項目（クロスサイト404・テナント設定依存等）は「要実環境確認」として残し、勝手に「検証済み」としない。

## 連携（他Skill/Agentとの関係）
- 深い監査は package-auditor Agent に委任する。
- 検出した保存不可・破損の修正は flow-error-fix / flow-update Skill へ引き継ぐ。
- 全緑を確認したら flow-release Skill でリリースへ進める。
- 検証で得た新しい知見は knowledge-update Skill で還元する。

## 完了報告
検証したパッケージ、validate_*.py の結果、レポート出力先、未検証事項と残リスクを報告する。
