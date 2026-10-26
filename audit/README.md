# audit — 文書監査の正本と成果物

文書・Skill・Agent・実装の整合を定期的に点検した記録と、**実行者本人にしか確定できない確認事項**を置く場所。
監査そのものの進め方は **doc-audit Skill**（`.claude/skills/doc-audit/SKILL.md`）を参照。

## なぜここに置くか

| 場所 | 役割 | ここに監査記録を置かない理由 |
|---|---|---|
| `handbook/` | 案件横断の**再利用知識** | 監査記録は再利用知識ではない（knowledge-update の管轄と混ざる） |
| `projects/` | 案件固有の資料 | 監査はリポジトリ全体が対象で、特定案件に属さない |
| `references/` | 受領原本・解析証跡 | **編集禁止**の読み取り専用領域 |

## 構成

```text
audit/
├── README.md            ← 本ファイル（監査の実行手順と正本の更新規則）
├── confirmations.json   ← 実行者への確認事項の【正本】。IDで継続追跡する
├── findings/            ← 回次ごとの監査記録の【正本】
│   └── YYYY-MM-DD.md
└── dist/                ← 生成物（報告DOCX）。直接編集しない
    └── markdown_audit_YYYYMMDDHHMMSS.docx
```

**正本は `confirmations.json` と `findings/*.md`。DOCXは生成物**であり、DOCXを直接編集しても次回の再生成で失われる。

## 実行手順

```powershell
# 1. 機械検査（修正前のベースラインを控える）
python tools/doc_audit.py

# 2. 乖離を修正する（doc-audit Skill の手順2〜4）
#    直したら再検査
python tools/doc_audit.py
python tools/wdl_lint.py --all .

# 3. 確認事項を更新する（audit/confirmations.json）
#    新規は連番で CONF-NNN を採番。解消したものは status と resolvedOn を更新（削除しない）

# 4. 今回の記録を書く
#    audit/findings/<YYYY-MM-DD>.md を新規作成（過去分は書き換えない）

# 5. 報告DOCXを生成
python tools/gen_audit_docx.py
```

`python tools/gen_audit_docx.py --help` で出力先・対象回次の指定方法が出る。

## confirmations.json の書式

```jsonc
{
  "schemaVersion": 1,
  "nextId": 15,                 // 次に採番するID。採番のたびに増やす（ID再利用の防止）
  "items": [
    {
      "id": "CONF-001",          // 一意。振り直さない
      "category": "動作確認",     // 動作確認 / 仕様判断 / 実環境確認 / 権限確認 / サンプル提供
      "target": "...",           // 関連するファイル・Skill・フロー・機能
      "question": "...",         // 確認してほしい具体的内容
      "reason": "...",           // Claude側だけでは確定できない理由
      "steps": ["..."],          // 利用者が実際に行う操作（手順）
      "expected": "...",         // 正常時に想定される動作・表示
      "returnToClaude": "...",   // 結果・スクリーンショット・エラー・JSON・式など
      "priority": "高",          // 高 / 中 / 低
      "status": "未確認",        // 未確認 / 確認待ち / 確認済み / 対応不要
      "foundOn": "2026-08-04",   // 発見日（監査日）
      "resolvedOn": null,        // 確認済み・対応不要になった日
      "relatedFinding": "F-01",  // 対応する不整合ID（findings/*.md の表と対応）
      "notes": ""                // 利用者からの回答・補足
    }
  ]
}
```

### 更新規則（重複登録を防ぐ）
1. **同じ趣旨の項目を二重に作らない**。同一対象・同一趣旨なら既存項目の `notes` / `status` を更新する。
2. **IDは再利用しない**。採番は必ず `nextId` から取り、採番後に `nextId` を増やす。
3. **確認済みでも削除しない**。`status` を更新し `resolvedOn` を入れる（追跡の連続性を保つため）。
4. 状態は `未確認`→`確認待ち`（利用者へ依頼済み）→`確認済み` / `対応不要` と遷移させる。
5. 利用者から回答をもらったら `notes` に要点を残す（次回監査で経緯を追えるようにする）。

## findings/*.md の書き方

- **1回の監査＝1ファイル**（`YYYY-MM-DD.md`）。過去回のファイルは書き換えない。
- 記載するのは**その回で新たに発見・更新した事項**。過去の全監査結果を毎回転記しない。
- 未解決の確認事項は `confirmations.json` 側で継続追跡されるため、findings に再掲しなくてよい。
- 不整合には `F-NN` の連番を振り、確認事項の `relatedFinding` から参照できるようにする。

## 状態の見方

確認事項の残件は次で確認できる。

```powershell
python -c "import json;d=json.load(open('audit/confirmations.json',encoding='utf-8'));print(sum(1 for i in d['items'] if i['status']=='未確認'),'件 未確認')"
```

関連: [../CLAUDE.md](../CLAUDE.md) / [../README.md](../README.md) / [../.claude/skills/doc-audit/SKILL.md](../.claude/skills/doc-audit/SKILL.md)
