# CLAUDE.md — このリポジトリでの作業規範

Power Automateクラウドフローの開発基盤。**新規フロー作成・既存フロー修正・エラー対応・パッケージ検証・知識蓄積**を定型的に繰り返すためのリポジトリ。

## 構成マップ

| 場所 | 役割 | 書き込み |
|---|---|---|
| `handbook/` | 案件横断の再利用知識（rules / knowledge / checklists / templates） | knowledge-update経由 |
| `tools/` | 汎用スクリプト（gen_outline.py / pack_package.py / wdl_eval.py / wdl_lint.py / doc_audit.py / gen_audit_docx.py） | 原則変更しない |
| `audit/` | 文書監査の正本（確認事項 confirmations.json・回次ごとの findings/）と生成DOCX | doc-audit経由 |
| `projects/<案件>/flows/<フロー>/spec/` | 設計資料（仕様書原本・設計TXT・ガイド・事実シート） | 仕様変更時に更新 |
| `projects/<案件>/flows/<フロー>/source/` | **唯一の編集元**（build_*.py・validate_*.py・生成された package/） | ここだけを編集 |
| `projects/<案件>/flows/<フロー>/validation/` | 検証結果・実行証跡 | 検証時に更新 |
| `projects/<案件>/flows/<フロー>/release/` | インポート用最終ZIP（日時付き）のみ | flow-release経由のみ |
| `references/` | **リポジトリ共通**の受領原本ZIP（raw/）と参照展開（extracted/）・解析証跡 | **編集禁止** |
| `_legacy/` | 旧構成・歴史的資料・スナップショット | 退避のみ |

## 不変則（すべての作業で厳守）

1. **definition.json は生成物**。修正は必ず `source/build_*.py` を編集 → 再生成 → `source/validate_*.py` で検証。`source/package/` の直接編集は禁止
2. `references/`（原本ZIP・展開）と `spec/` の受領docxは**読み取り専用**。上書き・改変禁止
3. `release/` には検証済みZIPのみ。既存releaseの上書き禁止（新しい日時付きファイルを追加）
4. **Git操作（commit/push/branch等）は一切行わない**
5. エラー修正は1件直して終わりにしない——**同型パターンの全数検索**（もぐら叩き防止）まで行う
6. 実環境で未検証の事項は「要実環境確認」と明記し、「成功済み」と主張しない
7. 実値（Team ID・サイトURL・接続GUID・メール）を `handbook/` に書かない（プレースホルダー使用）

## エラー対応の入口

エラーが貼り付けられたら **flow-error-fix Skill** を使う。既知10エラーは `handbook/knowledge/error_catalog.md` の冒頭索引から該当節へ（自己参照 / ネスト@ / 表示テキストの`@{` / 重複名 / 封筒参照 / PostItem検証 / クロスサイト404 / 添付全件Failed / `$expand`投影欠落の403 / 空文字へのsubstring）。

## Skill索引（.claude/skills/）

| Skill | 用途 |
|---|---|
| flow-error-fix | エラー貼付→調査→source修正→検証→知識化 |
| flow-create | 新規フロー作成（設計→source→検証→release） |
| flow-update | 既存フロー修正（差分・影響範囲・前後比較） |
| flow-package-validate | ZIP/展開形パッケージの検証 |
| flow-release | 検証済みsourceから日時付きrelease ZIP生成 |
| knowledge-update | 知見のhandbook反映（固有/汎用の分離） |
| doc-audit | 文書・Skill・Agent・実装の整合監査（確認事項の更新とDOCX生成まで） |

Agent: flow-architect（設計）/ flow-debugger（原因調査・同型全数リスト必須）/ package-auditor（構造検証）/ knowledge-curator（知識整理。書込はhandbook/のみ）

**Skill と Agent の役割分担**: Skill が工程の手順と責任範囲を持ち、掘り下げが要る部分だけを Agent へ委任する（flow-create→flow-architect / flow-error-fix→flow-debugger / flow-package-validate→package-auditor / knowledge-update→knowledge-curator）。doc-audit は決定的なスクリプト検査が主体のため Agent を持たない。

## ルールの正本

Power Automate 開発ルールの正本は `handbook/rules/00_power_automate_core_rules.md`〜`08_error_handling_and_idempotency.md` の**9本**（00がハブ）。
**`.claude/rules/` は設けない**——同じルールが2箇所に異なる表現で並ぶ二重管理を避けるため。Skill/Agent からはこの9本を参照する。

## 運用メモ

- 検証の正典は各フローの `validate_*.py`（文章の観点表と二重管理しない）。汎用検査は `tools/wdl_lint.py` に集約し、各 `validate_*.py` はこれを import する（`handbook/checklists/import_save_validation_checklist.md` §A）
- `handbook/knowledge/error_catalog.md` は単一ファイル運用。**12エラー超または60KB超で分割を再検討**（現在10エラー・約44KB。`tools/doc_audit.py` の C05 が閾値到達を検出する）
- 既存handbookファイルは改名しない（相互リンク保全）。新規ファイルはケバブケース
- 旧構成（dist/・build/・doc/・flow/等）のパスが古い文書に残る場合は `_legacy/2026-07-reorg-survey.md` の対応表で読み替える
- **案件・フローの一覧の正本はルート `README.md`**（案件表とフロー対応表）。Skill/Agent 側にフロー一覧を複製せず、READMEを参照させる

### Skill / Agent を追加・廃止したときの更新手順
1. `.claude/skills/<名前>/SKILL.md`（frontmatter の `name` はディレクトリ名と一致させる）または `.claude/agents/<名前>.md` を追加・削除する
2. 本ファイルの「Skill索引」表と、`README.md` §5「よくある作業の入口」の対応表を更新する
3. 他Skillの「連携（他Skill/Agentとの関係）」節から、責務の重複・参照切れが無いか確認する
4. `python tools/doc_audit.py` を実行し、C03（Skill名・Agent名の整合）が0件であることを確認する

## 文書監査

文書・Skill・Agent・実装の整合は **doc-audit Skill** で定期監査する（手順は `audit/README.md`）。
機械検査は `python tools/doc_audit.py`、確認事項の正本は `audit/confirmations.json`、報告DOCXは `python tools/gen_audit_docx.py` で再生成する。**DOCXを直接編集しない**（正本から生成し直す）。
