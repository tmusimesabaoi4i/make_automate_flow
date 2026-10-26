---
name: flow-create
description: 新しいPower Automateクラウドフローをゼロから作成するときに使う。「新しいフローを作って」「フローを新規作成」等がトリガー。要件整理→類似サンプル確認→flow-architect による設計→新フローの {spec,source,validation,release} 構築→生成・検証・パッケージ化・リリース配置までを担う。
---

# flow-create — 新規フロー作成

## 不変則（全Skill共通・厳守）
definition.json は生成物。修正は必ず source/ の build_*.py を編集→再生成→検証。source/package/ の直接編集、references/・release/ 内の既存ZIPの上書き、原本（references/raw/・spec/の受領docx）の変更は禁止。Git操作は一切行わない。

## いつ使うか
既存フローの修正ではなく、新しいフローを一から起こすとき。
エラー修正は flow-error-fix、既存改修は flow-update を使う。

## 使う資材（すべて実在）
- `handbook/templates/flow_design_template.md`（設計書の書式）。
- `handbook/knowledge/sample_flow_reference_index.md`（類似サンプルと注意点）。
- `handbook/checklists/design_review_checklist.md`・`handbook/checklists/expression_type_checklist.md`。
- ルート `README.md` §3 の**フロー対応表**（既存フローの build / validate 一覧＝雛形の選択肢）。
- `tools/wdl_lint.py`（新規 `validate_*.py` が import する共通リンター）。
- `references/extracted/`（展開済みサンプル。構造参照のみ・編集禁止）。

### 雛形の選び方（構成に近いものを複製する）
| 新フローの構成 | 複製元の case | build / validate |
|---|---|---|
| 複数コネクタ・大規模（Scope/ループ/台帳） | migrate-chat-spo / archive-meetings | `build_package.py` / `validate_definition.py` |
| 単一コネクタ・単純（実環境インポート/実行実績あり） | teams_post_url_flows / flow1-get-channel-post | `build_flow1.py` / `validate_flow1.py` |
| SharePoint REST 主体・破壊的操作の安全検査が要る | create_initialized_sharepoint_list / create-initialized-list | `build_list_flow.py` / `validate_list_flow.py` |
| コネクタのポーリングトリガー・メール同期 | sync-shared-mailbox-to-sharepoint-list / sync-mail-to-list | `build_sync_flow.py` / `validate_sync_flow.py` |

いずれも `projects/<案件>/flows/<フロー>/source/` 配下。パスの正本は README のフロー対応表。

## 手順

### 1. 要件整理
次を、ユーザー入力と `spec/` の受領資料から整理する。不足はユーザーへ質問して埋める。
- 目的・トリガー（手動/自動/スケジュール）・入出力。
- 使用コネクタ・保存先・冪等キー。
- 期間 / DryRun パラメータ・想定データ量。

### 2. 類似サンプル確認
- `handbook/knowledge/sample_flow_reference_index.md` で似た実働サンプルと既知の注意点を確認する。
- 構造の実物は `references/extracted/` を参照する（編集禁止）。

### 3. 設計委任（flow-architect Agent）
flow-architect へ設計を委任し、`handbook/templates/flow_design_template.md` の書式で出力させる。
必ず観点に含めさせる:
- 単一/分割判断・Scope try-catch-finally。
- 変数のトップレベル初期化・標準コネクタのみ。
- 冪等キー・ページング（nextLink 追跡）・実行時間30分制限。

### 4. 設計レビュー
- `handbook/checklists/design_review_checklist.md` で設計を自己レビューする。
- 式は `handbook/checklists/expression_type_checklist.md` も併せて確認する。

### 5. ディレクトリ構築
`projects/<案件>/flows/<新フロー>/` 配下に `{spec, source, validation, release}` を作成する。
- フローフォルダ名は**ケバブケース**に統一する（README §6）。
- `source/` は上の「雛形の選び方」で選んだ `build_*.py` を複製し、新フロー向けに改修する（definition.json を手書きしない）。
- 検証スクリプトも対応する `validate_*.py` を雛形に複製する。
- **新規 `validate_*.py` は `tools/wdl_lint.py` を import する**（汎用検査を案件ごとに手書きしない。`handbook/checklists/import_save_validation_checklist.md` §A）:
  ```python
  # HERE = projects/<案件>/flows/<フロー>/source なので、リポジトリ直下まで5階層上る
  sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..", "..", "..", "..", "..", "tools")))
  from wdl_lint import lint_definition   # noqa: E402
  for msg in lint_definition(definition, raw):
      fail("[wdl_lint] " + msg)
  ```

### 6. 生成
`python source/build_*.py`（引数なし）で `source/package/` を生成する。

### 7. 検証
- `python source/validate_*.py` を全緑にする。
- `python tools/wdl_lint.py --all .` を指摘0件にする。
- `python tools/gen_outline.py <definition.json> <出力txt>` で構造を確認する。
- 深い検証は flow-package-validate Skill / package-auditor Agent へ回す。

### 8. パッケージ・リリース
- `python tools/pack_package.py <package_dir> <output.zip>` でZIP化する。
- `handbook/checklists/import_save_validation_checklist.md` の機械検証節を通す。
- `<フロー名>_YYYYMMDDHHMMSS.zip` を `release/` へ配置する（正式配置は flow-release Skill に委ねてよい）。

## 作成する4フォルダの役割
新フロー `flows/<新フロー>/` の直下は既存フローと同じ4区画で構成する。
- `spec/`: 受領資料・設計書・SINGLE_FLOW_FACTS 等の事実。原本の受領docxは変更しない。
- `source/`: 生成スクリプト（build_*.py / validate_*.py）と、生成物 `source/package/`。真実の源はスクリプト側。
- `validation/`: 検証の証跡（validate 結果・アウトライン・レポート）。緑の証跡はリリースの前提。
- `release/`: 配布ZIP（`<フロー名>_YYYYMMDDHHMMSS.zip`）。既存ZIPは上書きしない。

## 設計・生成で必ず守る点（詳細は handbook 参照）
- 変数はフローのトップレベルで Initialize する。ループ内で初期化しない。
- 蓄積は SetVariable 自己参照を使わず、配列=AppendToArrayVariable / 文字列=AppendToStringVariable / カウンター=IncrementVariable にする（`handbook/rules/03_variables_arrays_and_objects.md`）。
- コネクタ出力は `body('X')?['field']` で参照する（`outputs('X')?['field']` は封筒のため null）。
- 標準コネクタのみを使う。プレミアムコネクタ・アプリ登録・管理者同意を前提にしない。
- ネストは深くしすぎない。式の `@` はネスト関数に付けない（`handbook/rules/02_expression_and_type_safety.md`）。

## 停止条件（ユーザーへ確認する）
- 要件を満たすのにプレミアムコネクタ・管理者権限・アプリ登録が必要と判明した時点で停止して確認する（環境制約に反する可能性が高い）。
- 受領資料（`spec/` の docx 等・原本）の内容と要件が食い違うとき。

## 連携（他Skill/Agentとの関係）
- 設計は flow-architect Agent に委任する。
- 生成物の深い検証は flow-package-validate Skill / package-auditor Agent へ回す。
- 最終ZIPの確定・配置は flow-release Skill に委ねる。
- 得た知見の共通化は knowledge-update Skill を使う。
- 完成後の修正は flow-update、エラー対応は flow-error-fix へ。

## 新フロー追加後に更新する索引（忘れると文書が古くなる）
- ルート `README.md` §3 の**フロー対応表**に1行追加する（Skillが対象を特定する正本）。
- ルート `README.md` §1 の案件一覧（新案件の場合）と実環境確認状況。
- 案件の `README.md`（フロー一覧・検証方法）。
- `python tools/doc_audit.py` を実行し、指摘0件を確認する。

## 完了報告
作成したフローのパス、複製元にした雛形、設計上の主要判断、検証結果、更新した索引、残リスクを報告する。
**実環境で未検証の項目は「要実環境確認」と明記する**（静的検証が緑でも「動作確認済み」とは書かない）。
得た知見は knowledge-update Skill で還元する。
