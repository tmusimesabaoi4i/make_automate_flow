# テストケース

区分:
- **[自動]** = `run_offline_tests.py` で実施済み（生成済み `definition.json` の式を評価）
- **[手動/未実施]** = 実環境が必要。**設計のみで未実施**

実施状況の総括は [validation_report.md](validation_report.md)。

---

## A. オフラインテスト（実施済み・57件合格）

`python projects/sync-shared-mailbox-to-sharepoint-list/tests/run_offline_tests.py`

| 群 | 件数 | 内容 |
|---|---|---|
| URL正規化・検証 | 18 | サイトURL / `viewlsts.aspx` / クエリ / フラグメント / 末尾スラッシュ / `_Layouts` `_LAYOUTS` の表記ゆれ / サブサイト / ルートサイト / 空 / 空白のみ / http / 非SharePoint / 偽装ホスト / userinfo |
| リスト名検証 | 13 | 英数字 / 日本語 / 空白入り / 前後空白除去 / 空 / 空白のみ / 禁止文字3種 / タブ / 255文字超 / 先頭ピリオド / 予約名 |
| メールアドレス検証 | 7 | 正常 / 空 / 空白のみ / `@`なし / `@`複数 / ドメインに`.`なし / ローカル部が空 |
| 取得件数検証 | 9 | 1 / 100 / 0 / 負数 / 小数 / 文字列 / 101 / 20桁 / null |
| 検証の優先順位 | 2 | URL > リスト名 > メールボックス > 件数 |
| ODataエスケープ | 8 | 通常ID / `'` / `&` / `<> `と空白 / 日本語 / 絵文字 / `"` と `%` / 250文字 |

各ケースは `varErrorCode` / `varIsValid` / `varSiteUrl` / `varRequestedCount` を突き合わせ、
さらに「エラーコードが空でないなら `varIsValid` が false」「エラーなら `varErrorMessages` が非空」
という整合性も検査している。

**確認できないこと**: Power Automate 実機での挙動、コネクタの実応答、
メールの降順整列（`sort`/`reverse` は `wdl_eval` 未実装）。

---

## B. パッケージ検証（実施済み）

| # | 検証 | 実行 | 結果 |
|---|---|---|---|
| B1 | 静的検証（保存可能性・安全要件） | `source/validate_sync_flow.py` | **0 errors / 0 warnings** |
| B2 | ZIP再展開・5ファイル構造・GUID3点一致・SHA-256突合 | `validation/extract_check.py` | **0 errors** |
| B3 | 実行順アウトラインの目視確認 | `tools/gen_outline.py` | 304アクション・想定どおり |

---

## C. 実環境テスト（**すべて未実施**）

以下は指示§23 のテスト1〜10 に対応する設計。実行していないため結果欄は空。

### テスト1: 新規リスト作成

| 項目 | 内容 |
|---|---|
| 前提 | 対象サイトに指定名のリストが**存在しない**。共有メールボックスに3件以上のメールがある |
| 入力 | サイトURL / 未使用のリスト名 / 共有メールボックス / 取得件数 **3** |
| 期待 | `status = Created` / `listCreated = true` / `createdCount = 3` / `updatedCount = 0` / `failedCount = 0` |
| 確認箇所 | ① 結果JSON ② SharePointでリストを開き、列が5つ（メッセージID・日時・送信元アドレス・件名・本文）③ 並びが**日時の降順** ④ アイテム3件 ⑤ 「タイトル」列が既定ビューに無いが、リスト設定の列一覧には**残っている** |
| 結果 | **未実施** |

### テスト2: 同一条件で再実行

| 項目 | 内容 |
|---|---|
| 前提 | テスト1の直後。同じメールが取得される |
| 入力 | テスト1と同一 |
| 期待 | `status = Existing` / `listCreated = false` / `createdCount = 0` / `updatedCount = 3` |
| 確認箇所 | ① アイテム数が**3件のまま増えていない** ② 「更新日時」列が更新されている ③ 列・ビューが変わっていない |
| 結果 | **未実施** |

### テスト3: 既存の互換リスト

| 項目 | 内容 |
|---|---|
| 前提 | 同名で、5列（内部名 `MessageId` / `ReceivedDateTime` / `SenderAddress` / `Subject` / `BodyPlainText`）を持つリストが**手動で**作成済み。ビューは既定のまま（列順や並び順は本フローの想定と異なってよい） |
| 入力 | そのリスト名 / 取得件数 3 |
| 期待 | `status = Existing` / `listCreated = false` / メールが登録される |
| 確認箇所 | ① **ビューの列順と並び順が変更されていない** ② 列が追加・変更・削除されていない ③ リスト設定が変わっていない ④ アイテムだけが増えている |
| 結果 | **未実施** |

### テスト4: 既存の非互換リスト

| 項目 | 内容 |
|---|---|
| 前提 | 同名だが `BodyPlainText` 列が無いリストが存在する |
| 入力 | そのリスト名 / 取得件数 3 |
| 期待 | `status = Error` / `error.code = ERR_SCHEMA_INCOMPATIBLE` / `missingFields = ["BodyPlainText"]` |
| 確認箇所 | ① **リストが一切変更されていない**（列・ビュー・設定・既存アイテム）② アイテムが追加されていない ③ `error.stage = VerifySchema` |
| 追加 | 型が違う場合（`ReceivedDateTime` を1行テキストで作成）も同様に `incompatibleFields` に記録され、リストが変更されないこと |
| 結果 | **未実施** |

### テスト5: 不正なURL

| 入力URL | 期待コード |
|---|---|
| （空） | `ERR_URL_EMPTY` |
| `http://{tenant}.sharepoint.com/sites/{site}` | `ERR_URL_NOT_HTTPS` |
| `https://example.com/sites/x` | `ERR_URL_NOT_SHAREPOINT` |
| `https://sharepoint.com.evil.example/sites/x` | `ERR_URL_NOT_SHAREPOINT` |
| `https://user@{tenant}.sharepoint.com/sites/{site}` | `ERR_URL_MALFORMED` |
| 存在しないサイトのURL（形式は正しい） | `ERR_SITE_OR_RESOURCE_NOT_FOUND`（stage=`CheckList`） |

| 項目 | 内容 |
|---|---|
| 確認箇所 | ① **リストが作成されていない** ② **メールが取得されていない**（実行履歴で `Get_Emails` が Skipped）③ エラーメッセージが日本語で具体的 |
| 結果 | **未実施** |

### テスト6: 不正な件数

| 入力 | 期待 |
|---|---|
| `0` | `ERR_COUNT_INVALID` |
| `-5` | `ERR_COUNT_INVALID` |
| `3.5` | トリガーのスキーマ（`integer`）が拒否。回避して渡った場合は `ERR_COUNT_INVALID` |
| `abc` | 同上 |
| `101` | `ERR_COUNT_TOO_LARGE` |
| `1000` | `ERR_COUNT_TOO_LARGE`（公式上限は1000だが本フローの上限は100） |

| 項目 | 内容 |
|---|---|
| 確認箇所 | ① **リスト作成もメール取得も行われていない** ② `error.stage = ValidateInput` ③ **黙って100件に切り詰められていない** |
| 備考 | デザイナー上で小数・文字列がどう扱われるかは**要実環境確認**（スキーマ型 `integer` による拒否のメッセージ内容は未確認） |
| 結果 | **未実施** |

### テスト7: HTML本文

| 項目 | 内容 |
|---|---|
| 前提 | 共有メールボックスに、太字・リンク・箇条書き・表を含むHTMLメールがある |
| 入力 | 取得件数 3（該当メールを含む） |
| 期待 | 本文列にHTMLタグが**含まれない** |
| 確認箇所 | ① 本文列に `<p>` `<div>` `<a href` 等が無い ② `&nbsp;` `&amp;` 等のエンティティが文字になっている ③ 改行がある程度保たれている ④ 本文が冒頭だけでない（`Body Preview` ではない） |
| 結果 | **未実施** |

### テスト8: 空の値

| 項目 | 内容 |
|---|---|
| 前提 | 件名が空のメール / 本文が空のメール / 送信元が正常取得できないメール（システム通知など） |
| 期待 | いずれもフロー全体を失敗させず、アイテムが登録される |
| 確認箇所 | ① `failedCount = 0` ② 件名が空のアイテムが登録されている ③ 本文が空のアイテムが登録されている ④ 送信元が空文字でも登録されている |
| 結果 | **未実施** |

### テスト9: 特殊文字

| 項目 | 内容 |
|---|---|
| 前提 | 件名またはメッセージIDに次を含むメール: `'` `"` 日本語 絵文字 URL `<` `>` 長い件名（200文字超） |
| 期待 | 検索・登録・更新がすべて成功する |
| 確認箇所 | ① `failedCount = 0` ② `duplicateCount = 0`（エスケープ不備で誤マッチしていない）③ 件名が欠けずに保存されている ④ 再実行して `createdCount = 0` / `updatedCount` が該当件数（＝検索が正しくヒットしている） |
| 備考 | ④が最重要。エスケープが壊れていると再実行時に**重複登録**される |
| 結果 | **未実施**（式レベルは [自動] O01〜O08 で検証済み） |

### テスト10: 重複異常

| 項目 | 内容 |
|---|---|
| 前提 | 同じ `MessageId` のアイテムを**手動で2件**作成しておく（一意制約を一時的に外す必要がある） |
| 入力 | そのメッセージIDに対応するメールを含む取得 |
| 期待 | `duplicateCount = 1` / `duplicates[0].count = 2` |
| 確認箇所 | ① **アイテムが追加されていない** ② **既存2件が更新されていない**（更新日時が変わらない）③ **削除されていない** ④ `duplicates[]` にメッセージIDと件数とアイテムIDが記録されている |
| 結果 | **未実施** |

---

## D. 追加で確認したい事項（実環境）

指示§23 には無いが、設計上のリスクとして確認しておきたいもの。

| # | 内容 | 理由 |
|---|---|---|
| D1 | `Get_Emails` が保存できるか（`OpenApiOperationParameterValidationFailed` が出ないか） | `GetEmailsV3` のパラメータキー名が公式資料で確定できていない |
| D2 | 取得したメールが**本当に最新のN件**か（最古／最新の受信日時をOutlookと突合） | `GetEmailsV3` の既定並び順が未確認。自前ソートでは補正できないケースがある |
| D3 | `MessageId` 列の「一意の値を適用」が有効になっているか | `createFieldAsXml` での `EnforceUniqueValues` 反映が未確認 |
| D4 | 既定ビューの並び順が実際に日時降順になっているか | `ViewQuery` による設定が本フロー初 |
| D5 | アイテム作成が `__metadata.type` 付きで通るか | テナントによる `__metadata` 要求差異への対策が有効か |
| D6 | 100件実行時の所要時間と調整制限（429）の有無 | 上限値の妥当性確認 |
| D7 | 3コネクタ構成で接続が正しく再マッピングされるか | 本リポジトリの実績は接続1本の構成のみ |
| D8 | Content Conversion がDLPで許可されているか | 遮断されていると全件が変換失敗になる |
| D9 | Outlook の `from` が文字列（アドレス）か | オブジェクトの場合、送信元列にJSONが入る |

---

## E. 再実行手順（開発側）

```powershell
cd D:\make_automate_flow
$p = "projects/sync-shared-mailbox-to-sharepoint-list"
python "$p/flows/sync-mail-to-list/source/build_sync_flow.py"
python "$p/flows/sync-mail-to-list/source/validate_sync_flow.py"
python "$p/tests/run_offline_tests.py"
python "$p/flows/sync-mail-to-list/validation/extract_check.py"
```
