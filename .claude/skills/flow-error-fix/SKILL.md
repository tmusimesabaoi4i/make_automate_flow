---
name: flow-error-fix
description: ユーザーがPower Automateのエラー（保存エラー・インポートエラー・実行時エラー）を貼り付けた/報告したときに使う。エラーコードやメッセージ（WorkflowRunActionInputsInvalidProperty、'@' at position、OpenApiOperationParameterValidationFailed、404 File not found 等）から原因を特定し、source/ の build_*.py を直して再生成・検証・同型全数対策・再パッケージまで行う。
---

# flow-error-fix — Power Automate エラー修正

## 不変則（全Skill共通・厳守）
definition.json は生成物。修正は必ず source/ の build_*.py を編集→再生成→検証。source/package/ の直接編集、references/・release/ 内の既存ZIPの上書き、原本（references/raw/・spec/の受領docx）の変更は禁止。Git操作は一切行わない。

## いつ使うか
Power Automateの保存・インポート・実行でエラーが出て、その全文または要約を渡されたとき。
既知エラーはカタログ照合で即修正、未知エラーは flow-debugger Agent へ調査委任する。
純粋な新規作成は flow-create、仕様変更は flow-update を使う。

## 使う資材（すべて実在）
- ルート `README.md` §3 の**フロー対応表**（対象フローと build / validate スクリプトを特定する正本）。
- `projects/<案件>/flows/<フロー>/{spec,source,validation,release}/`。
- `handbook/knowledge/error_catalog.md`（既知エラーの原因・修正方針・確認箇所）。
- `handbook/checklists/import_save_validation_checklist.md`（§A source検証・§B 再パッケージ後の機械検証）。
- `tools/wdl_lint.py`（案件横断の共通リンター）・`tools/gen_outline.py`・`tools/pack_package.py`。

## 対応手順（11ステップ）

### 1. 抽出
エラー全文から次を抽出する。原文は逐語で保持し、要約で置き換えない（GUID・URL・メール等の機密実値のみプレースホルダ化）。
- エラーコード（例: `WorkflowRunActionInputsInvalidProperty`）。
- メッセージ本文。
- 発生局面（インポート時 | 保存時 | 実行時）。
- 対象アクション名（メッセージ中の `'Set_...'` 等）。

### 2. 対象特定
ルート `README.md` §3 の**フロー対応表**から、対象フローと `build_*.py` / `validate_*.py` を特定する。
- 対象は `projects/<案件>/flows/<フロー>/source/`（全案件・全フローが対象。特定の案件に限定しない）。
- どのフローか不明なら、エラーメッセージ中のアクション名を**全フローの `source/` に対してGrep**して絞り込む。
- 事実確認は各 `spec/`（例: `projects/migrate-chat-spo/flows/archive-meetings/spec/SINGLE_FLOW_FACTS.md`）。

### 3. カタログ照合
`handbook/knowledge/error_catalog.md` をコード・メッセージ断片でGrepする。
- 該当節の「原因」「修正方針」「ZIP定義上の確認箇所」を採用する。
- 該当すれば下の「既知エラー対応表」の節に直行する。

### 4. 未知エラーは委任
カタログに無ければ flow-debugger Agent へ委任する。委任時に必ず要求する成果物:
- 原因仮説と、definition.json / build_*.py からの根拠引用。
- **同型パターンの全数リスト**（欠けた報告は不完全とみなす）。
- `source/` の build_*.py 修正案。

### 5. 箇所特定
該当する式・アクションを `source/` の `build_*.py` 内でGrepして特定する。
- 生成物である definition.json 側は直さない。
- 生成ロジック（式テンプレート・アクション定義）を突き止める。

### 6. 最小修正
生成スクリプトへ最小の修正を入れる。
- 修正前の該当行を引用してこの報告に記録する。
- 業務的意味（列・判定条件・保存先・期間）を変えない範囲に留める。

### 7. 再生成
`python source/build_*.py`（引数なし。`source/package/` を再生成）を実行する。

### 8. 検証
- `python source/validate_*.py`（対応表で特定したもの）を全緑にする。
- `python tools/wdl_lint.py --all .` を指摘0件にする（共通リンター。定義とMarkdownの両方を検査する）。
- `python tools/gen_outline.py <definition.json> <出力txt>` で構造を確認する。

### 9. 同型全数検索（もぐら叩き防止）
同じ誤りパターンを、**全案件・全フロー**の `source/package/*/definition.json` と `build_*.py` に機械走査し、0件を確認する。
- 対象は対応表の全フロー。今回エラーが出たフローだけを見て終わらせない。
- 例: `"operationId": "PostItem"` の残数、SetVariable 自己参照、不正な `@`、重複アクション名、`outputs('X')?['field']` の封筒参照。
- 検査そのものが汎用化できるなら、**`tools/wdl_lint.py` に検査を追加**して以後の再発を機械的に閉じる（案件ごとの手書きにしない）。
- 1件でも検出したら (6)〜(8) を反復する。1件直して満足しない。

### 10. 再パッケージ・配置
- `python tools/pack_package.py <package_dir> <output.zip>` でZIPを再生成する。
- `handbook/checklists/import_save_validation_checklist.md` の §B「パッケージ作成後（機械検証）」を通す。
- `<フロー名>_YYYYMMDDHHMMSS.zip` を対象フローの `release/` へ配置する（既存ZIPは上書きしない）。
- 配布物として確定させる場合は flow-release Skill に委ねる（リリース可否の判断はそちらが正本）。

### 11. 知見還元・報告
- 新規エラーなら `error_catalog.md` 末尾「追記方法」の書式で追記する（knowledge-update Skill / knowledge-curator Agent 経由も可）。
- 修正箇所・原因・検証結果・残リスクを報告する。

## 既知エラー対応表（照合の入口・詳細は error_catalog.md 該当節）
error_catalog.md の**9件**と対応する（索引の正は同ファイル冒頭の表）。

| # | メッセージ/コードの断片 | 局面 | error_catalog.md の該当節 |
|---|---|---|---|
| 1 | `the string character '@' at position` | インポート時 | ネストした@（インポート時式パース）節 |
| 2 | `WorkflowRunActionInputsInvalidProperty` / Self reference | 保存時 | SetVariable自己参照（保存時）節 ★最重要 |
| 3 | （事前検出）同一表示名の重複 | インポート前 | アクション名の全体重複節 |
| 4 | 実行時に値が null / `outputs('X')?['field']` | 実行時 | outputs封筒 → body/ パス欠落節 |
| 5 | `OpenApiOperationParameterValidationFailed` / missing 'item' | 保存時 | PostItem item欠落（保存時）節 |
| 6 | `404 File not found` / `GetFileContentByPath` | 実行時 | クロスサイト参照（実行時）節 |
| 7 | 完走するが台帳が全件 Failed | 実行時 | 添付保存の全件Failed節（CreateFileの中間フォルダ／GetFileItemの名前解決） |
| 8 | `Unable to parse template language expression` / `expected token 'LeftParenthesis'` | インポート時 | 表示テキスト中の `@{...}` が式として解釈される節 |
| 9 | リスト列挙だけが403（`_api/web` は200） | 実行時 | コレクション列挙の `$expand` に `$select` の投影が無く403 節 |

**局面で切り分ける**: インポート＝式パース・構造／保存＝コネクタのパラメータ検証／実行＝参照パス・権限・実データ。
7と9は「**完走した／200が返った＝正しい**」ではない型なので、出力の中身まで確認する。

## 停止条件（ユーザーへ確認する）
- 原本（`references/raw/`・`spec/` の受領docx）の変更が必要に見えるとき。
- 業務的意味を変える修正（列構成・判定条件・保存先の変更等）になるとき。
- 実環境でしか確認できない（クロスサイトの404・テナント設定依存等）とき。

いずれも勝手に進めず、判断材料を添えてユーザーへ確認する。
情報が不足して原因を確定できない場合も同じ——**推測で修正を適用せず**、何が分かれば確定できるか（エラー全文・実行履歴・対象アクションの入出力）を示して確認する。

## 連携（他Skill/Agentとの関係）
- 未知エラー・単一アクションに閉じない原因の調査は flow-debugger Agent に委任する（同型全数リスト必須）。
- 深いパッケージ検証は flow-package-validate Skill / package-auditor Agent へ。
- 最終ZIPの確定・配置は flow-release Skill へ。
- 新規エラーの知識化は knowledge-update Skill（書込は knowledge-curator Agent 経由でも可）。
- 仕様変更を伴う修正は flow-update、新規作成は flow-create へ切り替える。
