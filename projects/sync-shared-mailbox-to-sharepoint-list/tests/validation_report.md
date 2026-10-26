# 検証レポート

作成日: 2026-08-03
対象: `SyncSharedMailboxToSharePointList`（`flows/sync-mail-to-list/`）

---

## 1. 総括

| 区分 | 状態 |
|---|---|
| 静的検証（保存可能性・安全要件） | **合格**（0 errors / 0 warnings） |
| 共通リンター `tools/wdl_lint.py --all` | **合格**（0 findings） |
| オフラインテスト（式の評価） | **合格**（57件 / 57件） |
| ZIP再展開検査（構造・SHA-256突合） | **合格**（0 errors） |
| 実行順アウトラインの確認 | **合格**（304アクション・想定どおり） |
| **実環境 インポート → 保存 → 実行** | **成功**（2026-08-03・`..._20260803233000.zip`） |
| **実環境 100件同期（既存リスト経路）** | **成功**（`fetchedCount:100` / `createdCount:80` / `updatedCount:20` / `failedCount:0`） |
| 実環境テスト1〜10（指示§23） | テスト3相当が**合格**。他は §9・§11 で管理 |

### 実環境実行の実測（2026-08-03 13:41 完了）

| 項目 | 値 | 意味 |
|---|---|---|
| `status` / `listCreated` | `Existing` / `false` | **既存リスト経路**を通った（新規作成経路は未通過） |
| `requestedCount` / `fetchedCount` | 100 / 100 | 上限いっぱいの100件を取得できた |
| `createdCount` / `updatedCount` | 80 / 20 | **20件が既存と判定され更新された＝冪等性が実データで機能** |
| `failedCount` / `duplicateCount` / `truncatedCount` | 0 / 0 / 0 | 件単位の失敗なし |
| `missingFields` / `incompatibleFields` | `[]` / `[]` | 既存リストのスキーマ確認を通過 |
| `listUrl` | 正しく組み立て | `varSiteOrigin` ＋ `RootFolder/ServerRelativeUrl` の決定的構築が動作 |

**この1回で実証されたこと**

- `__metadata.type` を付けたアイテム作成（80件）と MERGE 更新（20件）が動作する
- `$filter` の `''` 2重化＋`uriComponent()` が**実データで正しくヒット**している
  （20件が既存と判定された。エスケープが壊れていれば全件が新規扱いになり重複登録される）
- Content Conversion（`HtmlToText`）が100件すべて成功（DLPで遮断されていない）
- **100件（SharePoint REST 約250回＋Content Conversion 100回）が調整制限・実行時間上限に触れず完走**
  → 上限を100件に設定した判断が実測で裏付けられた
- 既存リスト経路では**列・ビューを一切触らない**設計どおりに動作した

> ⚠ **`schemaWarnings: []` を「一意制約が確認できた」と読まないこと。**
> 一意制約の検証（`Condition_Unique_Not_Enforced`）は `varCreatedInThisRun == true` の
> ガード配下にあり、今回は `listCreated: false` のため**実行されていない**。
> 空なのは「合格」ではなく「未実行」。同様に `ViewQuery` の並び順設定も未通過。
> （本リポジトリの原則「実行成功≠結果が正しい」の具体例）

### 実環境での到達までの経緯（3回）

| 回 | ZIP | 結果 |
|---|---|---|
| 1 | `..._20260803213000.zip` | ❌ インポート失敗（式パースエラー。§3.3 #2） |
| 2 | `..._20260803224500.zip` | ❌ 実行失敗（リスト列挙 403。§3.3 #3） |
| 3 | `..._20260803233000.zip` | ✅ **インポート・保存・実行 成功** |

> **「1回の実行が通った」＝「全テストが通った」ではない。**
> 3回目の ZIP でインポート・保存・実行に成功し、出力も想定どおりだったが、
> どの経路（`Created` / `Existing`）を通ったか、テスト2〜10 の各ケースがどうなるかは別問題。
> §9 の表で1項目ずつ管理し、確認できたものだけを確認済みにする
> （[lessons_learned.md §18](../../../handbook/knowledge/lessons_learned.md) の教訓）。

---

## 2. 実行したコマンドと結果

```powershell
cd D:\make_automate_flow
$p = "projects/sync-shared-mailbox-to-sharepoint-list"

python "$p/flows/sync-mail-to-list/source/build_sync_flow.py"
#   built: .../source/package （5ファイル）

python "$p/flows/sync-mail-to-list/source/validate_sync_flow.py"
#   (0 errors) / (0 warnings)

python tools/gen_outline.py "$p/flows/sync-mail-to-list/source/package/Microsoft.Flow/flows/9e5b28d1-.../definition.json" `
                            "$p/flows/sync-mail-to-list/validation/action_outline.txt"
#   WROTE ... (304 actions)

python "$p/tests/run_offline_tests.py"
#   合格 57 / 不合格 0（全 57 件）

python tools/pack_package.py "$p/flows/sync-mail-to-list/source/package" `
                             "$p/flows/sync-mail-to-list/release/SyncSharedMailboxToSharePointList_20260803213000.zip"
#   entries: 5 / corrupt: none

python "$p/flows/sync-mail-to-list/validation/extract_check.py"
#   (0 errors)
```

証跡: `validation/validate_result.txt` / `validation/extract_check_result.txt` /
`validation/action_outline.txt` / `tests/offline_test_result.txt`

---

## 3. 静的検証の内訳

### 3.1 汎用検査（保存可能性）

| 観点 | 結果 |
|---|---|
| パッケージGUIDの3点一致 | 一致 |
| `apisMap` / `connectionsMap` ↔ `resources` ↔ `dependsOn` | 全件一致（API3＋接続3＝6件） |
| `connectionReferences` キー ↔ `host.connectionName` | 全件一致・全て Invoker 形式 |
| `runAfter` の兄弟整合・状態値 | 違反0 |
| アクション名の全体重複 | 0件 |
| ネスト深さ | 最大7（上限8） |
| `InitializeVariable` のトップレベル配置 | 41件すべてトップレベル |
| 未初期化変数の参照 | 0件 |
| 初期化したが読み書きされない変数 | 0件 |
| **SetVariable 自己参照** | **0件** |
| 変数の重複初期化 | 0件 |
| `body()`/`outputs()` の参照先実在 | 全件実在 |
| **コネクタ出力の封筒参照**（`outputs('X')?['field']`） | 違反0 |
| **不正な `@` 位置** | 0件 |
| **関数許可リスト外の使用** | 0件（使用42関数すべて許可集合内） |
| `Foreach` の並列オフ | 1件すべて `repetitions=1` |
| トリガー入力（4項目の型・表示名・required） | 全件一致 |
| 実値混入（GUID・メールアドレス・サイトURL） | 0件 |

### 3.2 本フロー固有の安全検査

| # | 検査 | 結果 |
|---|---|---|
| A | `GetByTitle(` の出現 | **0件** |
| B | 書き込み系POST のURIに `varListId` | 全件（新規作成 `_api/web/lists` のみ例外） |
| C | 破壊的REST（`deleteObject` / `recycle` / `DELETE`） | **0件** |
| D | 列作成・表示名変更・Title変更・ビュー操作が `varCreatedInThisRun` ガード配下 | 18件すべて |
| E | `removeAllViewFields()` の件数 | 1件・ガード配下 |
| F | Outlook の operationId / メール変更操作 | `GetEmailsV3` のみ・変更操作**0件** |
| G | `mailboxAddress` が変数式・`fetchOnlyUnread=false`・`includeAttachments=false`・`top` が変数式 | 全件 |
| H | 全 SharePoint アクションの `dataset` | 34件すべて `@variables('varSiteUrl')` |
| I | `$filter` の `''` 2重化＋`uriComponent()` | 2件すべて |
| J | 同名判定が `equals`・`contains` 不使用・`toLower`/`trim` あり | 3件すべて |
| K | `ViewQuery` に `ReceivedDateTime` の `Ascending='FALSE'` | 有（第2キー `ID` も有） |
| L | 5列の SchemaXml（XMLパース・型・一意制約・`RichText=FALSE`） | 全件合格 |
| M | スコープの実行順 | 想定順に一致 |
| N | メール取得・同期が `varIsValid`/`varSchemaOk` ガード配下 | 全件 |
| — | Catch Scope の `runAfter` が1本だけ | 合格 |
| — | 作成直前の再確認の存在 | 合格 |
| — | 取得件数の上限（100）チェックの存在 | 合格 |

### 3.3 検証中に発見・修正した不具合

| # | 内容 | 発見 | 対応 |
|---|---|---|---|
| 1 | `Set_List_ServerRelativeUrl_Final` が `coalesce(body(...), variables('varListServerRelativeUrl'))` となっており、**SetVariable の自己参照**（保存時 `WorkflowRunActionInputsInvalidProperty` の原因）になっていた | 静的検証で自動検出 | フォールバックの合成を `Compose_List_ServerRelativeUrl` に切り出し、SetVariable は Compose の出力だけを読む形へ修正。既知エラー2と同型 |
| 2 | トリガー入力 `SharedMailboxAddress` の `description` が `例: shared-mailbox@{tenant}.example.com` となっており、**`@{tenant}` が式の補間として解釈**され、インポート時に `Unable to parse template language expression 'tenant': expected token 'LeftParenthesis' and actual 'EndOfData'.` で失敗した | **実環境のインポートで発覚**（当初の静的検証では検出できなかった） | 説明文から `@` を除去。あわせて検証スクリプトへ2つの検査を追加（下記） |

### 発見された検査の穴（#2）と、その塞ぎ方

当初の `scan_bad_at()` は「`@` の直後が `{` なら正当な補間」として**無条件に許可**していた。
`@{...}` の**中身**が式かどうかを見ていなかったため、表示テキスト中の
`name@{placeholder}.example.com` を通してしまった。

追加した検査（`source/validate_sync_flow.py`）:

| # | 検査 | 内容 |
|---|---|---|
| a | `@{...}` の中身が式か | 中身が `関数名(` で始まらなければエラー。`@{tenant}` `@{}` `@{foo.bar}` を捕捉 |
| b | トリガー入力の表示テキスト | `title` / `description` に `@` が1文字でもあればエラー（表示テキストに補間は不要なため） |

**回帰確認**: 修正前のパッケージへ新検査を当てて **2件検出**、修正後は **0件**であることを確認した。

**同型パターンの全数検索**（もぐら叩き防止）:

| 走査対象 | 結果 |
|---|---|
| リポジトリ内の全 `definition.json`（12件）の `@{...}` 総数17件 | **不正0件**（残りはすべて `concat(` 等の関数呼び出し） |
| `references/extracted/` の参照サンプル | **不正0件** |
| 全 `build_*.py` の表示テキスト中の `@{` | **残存0件** |

> **教訓**: `{tenant}` のような**波かっこ単体は安全**（`create_initialized_sharepoint_list` が
> 同じ文字列で実環境インポートに成功している）。危険なのは **`@` と `{` が隣接する場合だけ**。
> メールアドレスの例を表示テキストに書くと、プレースホルダの直前が必ず `@` になるため踏みやすい。

---

## 4. オフラインテストの内訳（57件合格）

`tools/wdl_eval.py` で **生成済み `definition.json` の式そのもの**を評価している。
設計書を読んで別実装したものを検証しているのではない。

| 群 | 件数 | 合格 |
|---|---|---|
| URL正規化・検証 | 18 | 18 |
| リスト名検証 | 13 | 13 |
| メールアドレス検証 | 7 | 7 |
| 取得件数検証 | 9 | 9 |
| 検証の優先順位 | 2 | 2 |
| ODataエスケープ | 8 | 8 |

各ケースで次の整合性も併せて検査している。

- エラーコードが空でないなら `varIsValid` が `false`
- エラーなら `varErrorMessages` が非空
- ODataエスケープ後の値に生の `' & 空白 # ? < > "` が残っていない
- 入力に `'` がある場合、エンコード結果に `%27%27` が現れる（`''` の2重化）

### この方式で確認できないこと

- Power Automate 実機での関数の挙動差
- SharePoint REST / Outlook / Content Conversion の実応答
- **メールの受信日時降順の整列**（`sort` / `reverse` / `formatDateTime` は `wdl_eval` 未実装）
- 保存可否・インポート可否

---

## 5. ZIP再展開検査の内訳（0 errors）

| 観点 | 結果 |
|---|---|
| ZIPの破損・展開可否 | 正常（5エントリ） |
| 5ファイル構造がZIPルート直下から始まる | 合格（余分な親フォルダなし） |
| `__MACOSX` / `.DS_Store` / ディレクトリエントリ | 0件 |
| 全JSONのパース | 5件すべて成功 |
| GUID3点一致 | 一致 |
| `dependsOn` が6件 | 合格 |
| `connectionReferences` ↔ `apisMap` / `connectionsMap` | 一致 |
| **`source/package` とのSHA-256バイト一致** | **全ファイル一致** |
| トリガー4入力・`MailCount` が integer | 合格 |
| 3コネクタ・3 operationId の実在 | 合格 |
| 5列の `AddViewField` / `createFieldAsXml` / `removeAllViewFields()` | 合格 |
| `ViewQuery` の日時降順 | 合格 |
| `EnforceUniqueValues="TRUE"` / `RichText="FALSE"` | 合格 |
| `GetByTitle(` / 破壊的REST / メール変更操作 | すべて0件 |
| サイトURL・メールアドレスの実値埋め込み | 0件 |

---

## 6. チェックリストとの照合

| チェックリスト | 状態 |
|---|---|
| [design_review_checklist.md](../../../handbook/checklists/design_review_checklist.md) | 全項目確認済み（§7参照） |
| [expression_type_checklist.md](../../../handbook/checklists/expression_type_checklist.md) | 全13項目を検証スクリプトで機械確認 |
| [import_save_validation_checklist.md](../../../handbook/checklists/import_save_validation_checklist.md) §A | **合格**（validate 全緑・アウトライン確認・匿名化漏れ0） |
| 同 §B | **合格**（ZIP再展開・JSONパース・接続参照突合・runAfter・重複名・実値混入） |
| 同 §C（環境準備） | **実施済み**（接続3本の割当・対象サイトの権限確認） |
| 同 §D（インポート後） | **実施済み**（インポート→接続再選択→保存→実行）。フローチェッカーの警告0確認は**要確認** |

---

## 7. 設計レビューチェックリストの確認結果

| 項目 | 結果 |
|---|---|
| 単一フローで完結するか判断した | 単一フロー。子フロー呼び出しは接続・権限・エラー伝播が増えるため不採用 |
| 標準コネクタのみで成立するか | SharePoint / Office 365 Outlook / Content Conversion の3本。すべて標準。汎用HTTP・Entra ID・アプリ登録は不使用 |
| 管理者権限を前提にしていないか | 一般ユーザー権限で完結。サイトのリスト作成権限は必要だが管理者権限ではない |
| 冪等性 | メッセージIDをキーに検索し、あれば更新。再実行でアイテムは増えない |
| 破壊的操作の順序 | **破壊的操作を1件も持たない**（削除系REST 0件）。既存リストは変更しない |
| 個別要素の失敗が全体を止めないか | 1メールの失敗は `itemErrors[]` に記録して次へ進む。全体エラーはスキーマ不整合等のみ |
| 小規模テストのパラメータがあるか | 取得件数で調整できる（3件から開始する手順を installation.md に記載） |
| DryRun 相当の切替 | **未実装**。本フローは「読み取り＋冪等な登録／更新」で破壊的処理が無いため、
少件数実行で代替できると判断した。制約として記録する |
| Do until の上限 | Do until を使用していない（ページングなし。上限100件で1回の取得に収まる） |
| 実行時間上限への対策 | 取得件数の上限を100件に設定（README §9） |
| ページング | `GetEmailsV3` の `top` が公式上限1000のため、100件では不要 |
| 更新不要な値は Compose | 定数・派生値はすべて Compose。変数は累積・状態保持のみ |
| 変数更新ループの並列オフ | `Foreach_Email` は `repetitions=1` |

---

## 8. 設計判断と指示からの逸脱

| 指示 | 判断 | 理由 |
|---|---|---|
| §2「原則としてソリューション形式」 | **レガシーパッケージのみ**を作成 | 指示§2 の但し書き「既存プロジェクトが別の正規形式を採用している場合は判断してよい」に該当。本リポジトリの全案件がレガシーで、実環境インポート・実行の実績もレガシーのみ。ソリューション形式は Dataverse が必要で、手書きZIPのインポート可否を当方で検証できない。**利用者に確認のうえ決定** |
| §4.4「コネクタの取得上限」 | 公式上限1000に対し**本フローの上限を100**にした | 1件につきSharePoint RESTが2〜3回走るため、1000件では Outlook の調整制限（300コール/60秒）と実行時間上限（目安30分）に確実に触れる。101以上は処理前にエラー終了（黙って切り捨てない）。**利用者に確認のうえ決定** |
| §9「Title列の扱い」 | **別途 `Subject` 列を作成**し、Title は必須解除して既定ビューから外す | 指示§9 が2案を提示しているうちの一方。内部名が指示の推奨例と完全に揃う。**利用者に確認のうえ決定** |
| §12「フォルダー：受信トレイ」 | `folderPath: "Inbox"` を明示指定 | 公式リファレンス由来のキー名。**要実環境確認**（§9参照） |
| §13「Content Conversion を使用できない環境の代替」 | 代替を**実装せず**、理由と制約を文書化 | 標準コネクタだけのHTMLタグ除去は、タグの入れ子・HTMLエンティティ・改行を正しく扱えず本文が壊れる。「HTMLをそのまま保存しない」は満たせても品質要件を満たさない（[troubleshooting.md §8](../docs/troubleshooting.md)） |
| §17「トリガーの同時実行制御」 | **未実装** | 手動トリガーではトリガーレベルの同時実行制御を設定できない。代わりに「作成直前の再確認」「一意制約」「作成失敗時の再検索」「並列オフ」で緩和 |
| §21「ソリューションファイル・マニフェスト」 | レガシーパッケージの `manifest.json` ／ `Microsoft.Flow/flows/manifest.json` ／ `apisMap.json` ／ `connectionsMap.json` で構成 | 形式をレガシーに決めたことに伴う |

---

## 9. 未確認事項（要実環境確認）

| # | 事項 | 影響 | 確認方法 |
|---|---|---|---|
| ~~1~~ | ~~インポート・保存・実行~~ → **✅ 2026-08-03 に成功** | — | 完了 |
| ~~2~~ | ~~`GetEmailsV3` のパラメータキー名~~ → **✅ 保存時のコネクタ検証を通過し実行できたため実証済み** | — | 完了 |
| 3 | `GetEmailsV3` の既定の並び順 | 「最新N件」にならない可能性 | リスト最上位の日時と Outlook 受信トレイを突合 |
| 4 | `createFieldAsXml` での `EnforceUniqueValues="TRUE"` の反映可否 | 重複登録の防止がフロー側検索のみに依存 | **新規作成経路（`status: Created`）でしか検証されない。`schemaWarnings` が空でも既存リスト経路なら未実行**。列設定画面でも確認できる |
| 5 | `ViewQuery` による並び順設定 | 既定ビューが降順にならない可能性 | **新規作成経路でしか実行されない**。リストを開いて並び順を確認 |
| ~~6~~ | ~~`__metadata.type` 付きアイテム作成~~ → **✅ 実証**（80件作成・20件更新） | — | 完了 |
| 7 | `HtmlToText` の出力形（文字列かオブジェクトか） | 本文列にJSONが入る可能性 | 変換は100件成功したが**列の中身は未確認**。本文列を目視 |
| ~~8~~ | ~~Content Conversion のDLP適合~~ → **✅ 実証**（100件すべて変換成功・`failedCount:0`） | — | 完了 |
| 9 | Outlook の `from` が文字列（アドレス）かオブジェクトか | 送信元列にJSONが入る可能性 | 失敗0件だが**列の中身は未確認**。送信元アドレス列を目視 |
| ~~10~~ | ~~3コネクタ構成での接続再マッピング~~ → **✅ インポート後に実行できたため実証済み** | — | 完了 |
| ~~11~~ | ~~100件実行時の所要時間・調整制限~~ → **✅ 実証**（100件完走・429なし） | — | 完了 |
| 12 | トリガースキーマ `integer` に小数・文字列を入れたときの挙動 | エラーメッセージの分かりやすさ | テスト6 |

**公式資料の参照可否について**: 2026-08-03 に learn.microsoft.com の
Office 365 Outlook コネクタリファレンスを参照したが、**同一URLへの再取得で
パラメータ表の内容が食い違う事象**が発生した（`references/shared-mailbox-to-teams-notify-20260803_analysis.md` §12-B に記録済み）。
複数回の取得で一致した「`GetEmailsV3` に `mailboxAddress` が存在する」「`top` の上限は1000」
「調整制限は300コール/60秒」のみを採用し、**個々のパラメータキー名は上表2として
未確認扱いにしている**。

---

## 10. 確認済みと未確認の切り分け（まとめ）

### 確認済み（当方で実行して緑を確認）
- JSON構造・GUID整合・接続参照の突合
- 保存可能性の静的観点（自己参照・重複名・runAfter・封筒参照・不正な`@`・未初期化変数）
- 安全要件A〜N（削除系0件・ガード配下・エスケープ・完全一致判定 等）
- 入力検証とURL正規化の論理（57ケース）
- ODataエスケープの結果文字列
- ZIP の構造と `source/package` とのバイト一致

### 未確認（実環境が必要）
- インポート・保存・実行の可否
- コネクタの実応答とパラメータ名
- SharePoint 側の実際の列・ビュー・アイテムの状態
- テスト1〜10 のすべて
