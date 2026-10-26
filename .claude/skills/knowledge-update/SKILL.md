---
name: knowledge-update
description: 案件で得た知見を handbook の共通知識へ反映するときに使う。「error_catalogに追記」「教訓をまとめて」「知識を還元」「lessons_learnedに書いて」等がトリガー。案件固有と汎用を分離し、実値をプレースホルダ化して error_catalog・lessons_learned・rules・checklists へ追記し、README 索引を更新する。
---

# knowledge-update — 知見の共通知識反映

## 不変則（全Skill共通・厳守）
definition.json は生成物。修正は必ず source/ の build_*.py を編集→再生成→検証。source/package/ の直接編集、references/・release/ 内の既存ZIPの上書き、原本（references/raw/・spec/の受領docx）の変更は禁止。Git操作は一切行わない。

## いつ使うか
案件を完了/大きく修正したあと、または新しいエラー・教訓・式・サンプルを得たときに、それを次案件へ再利用できる形で `handbook/` に還元する。
実際の書き込みは knowledge-curator Agent へ委任してよい（書込範囲は `handbook/` 配下のみ）。

## 使う資材（すべて実在）
- `handbook/knowledge/error_catalog.md`・`lessons_learned.md`・`expression_examples.md`・`sample_flow_reference_index.md`。
- `handbook/rules/00_power_automate_core_rules.md`〜`08_error_handling_and_idempotency.md`。
- `handbook/checklists/`（design_review / expression_type / import_save_validation / release）。
- ルート `README.md`（索引）。

## 手順

### 1. 切り分け
得た知見を分ける。
- 案件固有（実ID・実URL・列構成・判定条件・期間など）→ `projects/` 側。
- 汎用（複数案件で通用する一般則）→ `handbook/` 側のみ。

### 2. プレースホルダ化
汎用側に実値を残さない。
- `{teamId}` `{channelId}` `{siteUrl}` `{listId}` `{destinationPath}` 等に置換する。
- 認証情報・トークン・接続固有IDは書かない。

### 3. error_catalog 追記
新規エラーは `handbook/knowledge/error_catalog.md` 末尾「追記方法」の書式で追記する。
- 発生メッセージ / 発生条件 / 原因 / 誤った実装例 / 修正方針 / 修正例。
- ZIP定義上の確認箇所 / Power Automate画面上の確認箇所 / 再発防止チェック / 初出案件。

### 4. lessons_learned 追記
一般化できる教訓は `handbook/knowledge/lessons_learned.md` へ追記する。
- `【事実】`/`【推奨】`/`【案件固有】`/`【要実環境確認】` の表記を守る。
- 「今回たまたま動いた」だけの方法を根拠なく一般ルール化しない。

### 5. rules / checklists 追記
- ルールに昇格すべき事項は `handbook/rules/00〜08` の該当ファイルへ。
- 検査観点の不足は `handbook/checklists/` の該当表へ。
- 既存ルールと矛盾しないか確認する。

### 6. 式・サンプル
- 再利用可能な式は `handbook/knowledge/expression_examples.md`。
- 新しいサンプルZIPは `handbook/knowledge/sample_flow_reference_index.md` へ登録する。

### 7. 索引更新
ルートの `README.md` のリンク・構成・代表エラー一覧を更新する。
詳細は1箇所に書き、他はリンクで参照させる（肥大化させない）。

## 追記先の早見表
得た知見の種類ごとに、還元先を選ぶ。
| 知見の種類 | 還元先（handbook/ 配下） |
|---|---|
| 新しいエラーと修正 | `knowledge/error_catalog.md` |
| 一般化した教訓・判断理由 | `knowledge/lessons_learned.md` |
| 再利用可能な式 | `knowledge/expression_examples.md` |
| 参考にできるサンプルZIP | `knowledge/sample_flow_reference_index.md` |
| 恒久ルールへの昇格 | `rules/00〜08` の該当ファイル |
| 検査観点の不足 | `checklists/` の該当表 |
| **機械化できる検査** | `tools/wdl_lint.py`（文章のチェックリストに足すだけで終わらせない） |
| 上記の索引 | ルート `README.md` |

**還元先が handbook/ でないもの**（誤って handbook へ書かない）:
- 文書の食い違い・確認事項 → `audit/`（doc-audit Skill）
- 案件の実値・実環境の確認状況 → `projects/<案件>/`

## 分離の原則（正本: ルート `README.md` §2「共通知識と案件固有資料の違い」）
- **汎用（handbook/ 直下）**: 実値を書かず、プレースホルダを使う。複数案件で再利用できる一般則・パターン・教訓のみ。
- **案件固有（projects/ 配下）**: 実ID・URL・列構成・判定条件・期間などの実値と、その案件だけの設計判断。案件資料単独で構築できる完結性を保つ。
- **監査記録（audit/ 配下）**: 文書整合の監査結果と実行者への確認事項。**handbook/ には書かない**（再利用知識ではないため）。doc-audit Skill の管轄。

## 肥大化防止
- 同一内容は統合し、重複を作らない。
- `error_catalog.md` は 12エラー超 または 60KB超 で分割を検討する。
- 公式資料で確認できない内容は「要実環境確認」と明記する。

## 委任
書き込みは knowledge-curator Agent（tools: Read, Grep, Glob, Edit, Write / 書込範囲=handbook/ のみ）へ委任できる。
書式遵守・プレースホルダ化・重複統合・索引更新を必須要件として渡す。

## 連携（他Skill/Agentとの関係）
- 実際の書き込みは knowledge-curator Agent に委任できる（書込範囲=handbook/ のみ）。
- flow-error-fix / flow-update / flow-create / flow-package-validate で得た知見の受け皿になる。
- 案件固有として除外した項目は、projects 側の spec/ に残す判断を依頼元へ返す。
- **doc-audit との境界**: 本Skillは「再利用できる知識」を handbook へ書く。文書間の食い違いの検出・修正と確認事項の管理は doc-audit Skill（`audit/` 配下）が担当する。両者で同じ内容を二重に持たない。

## 完了報告
追記・更新したファイルのパス、案件固有/汎用の切り分け結果、プレースホルダ化の確認、README 索引の更新内容を報告する。
