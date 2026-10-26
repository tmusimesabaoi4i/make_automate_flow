---
name: flow-release
description: 検証済みの source から配布用の最終ZIPを作るときに使う。「リリースZIPを作成」「本番用パッケージを出力」「release に配置して」等がトリガー。validation/ に緑の検証結果があることを確認したうえで pack_package.py を実行し、日時付きZIPを release/ へ配置する。未検証のものは release に置かない。
---

# flow-release — 検証済み source から最終ZIP

## 不変則（全Skill共通・厳守）
definition.json は生成物。修正は必ず source/ の build_*.py を編集→再生成→検証。source/package/ の直接編集、references/・release/ 内の既存ZIPの上書き、原本（references/raw/・spec/の受領docx）の変更は禁止。Git操作は一切行わない。

## いつ使うか
検証を終えたフローを配布ZIPとして確定・配置するとき。
生成や修正が未完なら flow-create / flow-update / flow-error-fix を先に完了させる。
検証自体は flow-package-validate を使う。

## 使う資材（すべて実在）
- ルート `README.md` §3 の**フロー対応表**（対象フローと `validate_*.py` を特定する正本）。
- 対象フローの `validation/`（緑の検証結果の所在）。
- `source/validate_*.py`（緑の再確認）・`tools/wdl_lint.py`（共通リンターの再確認）。
- `handbook/checklists/release_checklist.md`。
- `tools/pack_package.py`。
- 配置先: `projects/<案件>/flows/<フロー>/release/`（下の「命名・配置規則」を正とする）。

## 前提（満たさなければ中止）
- 対象フローの `validation/` に**緑（合格）の検証結果がある**こと。無ければリリースしない。
- 未検証・要修正のパッケージは release に置かない（未検証のrelease配置禁止）。

## 手順

### 1. 検証の確認
対象フローの `validation/` を確認し、最新の `source/package/` に対して検証が全緑であることを再確認する。
- `python source/validate_*.py`（README のフロー対応表で特定したもの。引数なし）。
- `python tools/wdl_lint.py --all .`（指摘0件）。
- 緑でなければ中止し、flow-package-validate / flow-error-fix へ差し戻す。

### 2. リリース前チェック
`handbook/checklists/release_checklist.md` を通す。
- テスト用の仮値・デバッグアクションの除去。
- 保存先が本番相当か。
- 機密情報の混入なし。
- 実環境未検証事項の明記。

### 3. 最終ZIP生成
`python tools/pack_package.py <package_dir> <output.zip>` を実行する。
- `<package_dir>` は対象フローの `source/package/`。
- 出力名は `<フロー名>_YYYYMMDDHHMMSS.zip`（`<フロー名>` はフローの論理名。既存 `release/` の命名に合わせる）。
- 例: `PA_Migrate_Teams_Meeting_Archive_To_SPO_YYYYMMDDHHMMSS.zip` / `CreateMeetingArchiveLists_YYYYMMDDHHMMSS.zip` / `Flow1_GetTeamsChannelPostFromUrl_YYYYMMDDHHMMSS.zip` / `SyncSharedMailboxToSharePointList_YYYYMMDDHHMMSS.zip`。

### 4. 配置
生成ZIPを対象フローの `release/` へ置く。
- **既存のZIPは上書きしない**（日時サフィックスで別名になる）。

### 5. 記録
どの `source/package/` から、どの検証結果を根拠に、いつ生成したかを報告に残す。

## リリース可否の判断
次をすべて満たすときのみリリースする。1つでも欠けたら中止し、差し戻す。
- `validation/` に対象パッケージの緑の検証結果がある。
- その検証が最新の `source/package/`（build_*.py 経由で再生成した現物）に対するものである。
- `release_checklist.md` を通過している。
- 機密情報（実ID・URL・メール・トークン）の混入が無い。
- 実環境未検証事項が残る場合、それが「要実環境確認」として引き継がれている。

## 命名・配置規則
- ファイル名: `<フロー名>_YYYYMMDDHHMMSS.zip`（日時はJST・生成時刻）。
- 配置先: `projects/<案件>/flows/<フロー>/release/`。
- 既存ZIPは履歴として保持し、上書き・削除しない。

## 禁止・注意
- 検証が緑でないパッケージのリリース。
- `source/package/` を手直ししてからZIP化する（必ず build_*.py 経由で再生成した package を使う）。
- `references/` 内のサンプルや原本ZIPをリリース成果物として流用する。

## 連携（他Skill/Agentとの関係）
- リリース前の検証は flow-package-validate Skill / package-auditor Agent に委ねる。
- 検証が緑でない・修正が要るなら flow-error-fix / flow-update Skill へ差し戻す。
- リリース後に得た運用上の知見は knowledge-update Skill で還元する。

## 引き継ぎ事項（運用者向け）
実環境へのインポート・接続再選択・保存・小規模テストは運用者が行う。
- インポート成功≠完成である点を伝える（`handbook/checklists/import_save_validation_checklist.md`）。
- 実環境未検証の項目（クロスサイト参照・テナント設定依存等）を明記して引き継ぐ。

## 完了報告
生成したZIPのパス、根拠にした検証結果、release 配置状況、実環境インポートは運用者が行う旨の残注意を報告する。
