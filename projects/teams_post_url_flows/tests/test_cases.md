# テストケース

指示書§12が要求する正常系11件・異常系10件を網羅した一覧です。各ケースに**確認方法**と**現在の確認状況**を明記しています。

## 確認状況の凡例

| 記号 | 意味 |
|---|---|
| ✅ 静的検証済み | `tests/run_url_parse_tests.py` により、生成済み `definition.json` の式を実際に評価して確認済み（2026-07-24） |
| 🔍 構造確認済み | 定義上その処理が存在することを検証スクリプトで確認済み。ただし実データでの動作は未確認 |
| ⚠ 要実環境確認 | **実環境でしか確認できない。正常動作は断定していない** |

**重要**: 本パッケージは実環境でのインポート・保存・実行を行っていません。⚠ の項目は、インポート後にご自身の環境で確認してください。

---

## 1. 正常系（指示書§12）

### 1-1. URL解析（オフラインで検証済み）

`tests/run_url_parse_tests.py` は Flow1 / Flow2 それぞれの `definition.json` から `Scope_ParseUrl` を読み出し、`tools/wdl_eval.py`（案件横断のWDL式ミニ評価器）で式を評価します。結果は `tests/url_parse_test_result.txt`。

| # | 指示書の要求 | ケースID | 入力URLの特徴 | 期待結果 | 状況 |
|---|---|---|---|---|---|
| 1 | 親投稿のURL | N01 | `parentMessageId` が `messageId` と同値 | `targetMessageId` = messageId、エラーなし | ✅ |
| 2 | 返信のURL（`parentMessageId` あり） | N02 | パスは返信ID、クエリは親ID | `targetMessageId` = **親ID**（親投稿へ解決） | ✅ |
| 3 | URLエンコードされたチャネルID | N03 | `19%3A…%40thread.tacv2` | `channelId` = `19:…@thread.tacv2` に復号 | ✅ |
| 4 | クエリパラメーターの順番が異なる | N04 | `groupId` が先頭、`tenantId` が末尾 | 全識別子が正しく取得される | ✅ |
| — | `parentMessageId` が無い | N05 | クエリに `parentMessageId` 無し | `targetMessageId` = パス上の messageId | ✅ |
| — | `parentMessageId=0` の変種 | N06 | 親投稿リンクの変種 | `'0'` を値なし扱い → パス上の messageId | ✅ |
| — | 末尾に追加パラメーター | N07 | `teamName` / `channelName` / `createdTime` 等 | 無視して必要な3つを取得 | ✅ |
| — | 非エンコードのチャネルID | N08 | `19:…@thread.tacv2` が生 | 復号は無害で素通り | ✅ |
| — | URL前後に空白 | N09 | `"   https://… "` | `trim()` で除去 | ✅ |
| — | フラグメント付き | N10 | `…&groupId=…#anchor` | `#` 以降を切り捨て | ✅ |
| — | パス末尾にスラッシュ | N11 | `…/{messageId}/` | messageId を正しく取得 | ✅ |
| — | 新Teamsドメイン | N12 | `teams.cloud.microsoft` | 正常に解析 | ✅ |

**実行結果（2026-07-24）: Flow1 20件 / Flow2 20件、合計40件すべて合格。**

### 1-2. 実データが必要なもの（実環境確認）

| # | 指示書の要求 | 確認方法 | 期待結果 | 状況 |
|---|---|---|---|---|
| 5 | 返信が0件の投稿 | Flow2 に返信0件の投稿URLを入力 | `replyCount: 0` / `replies: []`。`Do_Until_Replies_Paging` は1回で終了 | ⚠ |
| 6 | 返信が1件の投稿 | Flow2 に返信1件の投稿URLを入力 | `replyCount: 1`。本文・投稿者が一致 | ⚠ |
| 7 | 返信が複数件の投稿 | Flow2 に返信数件の投稿URLを入力 | `replyCount` が実際の件数と一致 | ⚠ |
| 8 | 返信がページネーション上限を超える投稿 | Flow2 に**返信51件以上**の投稿URLを入力 | `Do_Until_Replies_Paging` が**2回以上反復**し、`replyCount` が全件になる（50で頭打ちにならない） | ⚠ **最重要** |
| 9 | 添付ファイルを含む投稿 | Flow1 に添付付き投稿URLを入力 | `message.attachments[]` に要素が入る。無い場合は `[]` | ⚠ |
| 10 | メンションを含む投稿 | Flow1 にメンション付き投稿URLを入力 | `message.mentions[]` に要素が入る。本文中に `<at>` タグが残る | ⚠ |
| 11 | HTML形式の本文を含む投稿 | Flow1 に書式付き投稿URLを入力 | `message.body.contentType: "html"`、`content` にHTMLがそのまま入る | ⚠ |

> ケース8が最も重要です。「全返信」要件を満たしているかは、**1ページ（50件）を超えるスレッド**でしか確認できません。確認手順は `docs/installation.md` §10 を参照してください。
>
> 定義上は、`Do_Until_Replies_Paging`（`@empty(variables('varReplyNextLink'))` まで反復・`limit.count=5000` / `timeout=PT1H`）と `Set_ReplyNextLink`（`@coalesce(body('Get_All_Replies')?['@odata.nextLink'], '')`）が存在することを検証スクリプトで確認済みです（🔍）。先頭N件で打ち切る処理は定義中に存在しません。

---

## 2. 異常系（指示書§12）

### 2-1. URL解析で判定できるもの（オフラインで検証済み）

| # | 指示書の要求 | ケースID | 入力 | 期待するエラーコード | 状況 |
|---|---|---|---|---|---|
| 1 | 空文字 | E01 | `""` | `ERR_URL_EMPTY` | ✅ |
| — | 空白のみ | E02 | `"    "` | `ERR_URL_EMPTY`（trim後に空） | ✅ |
| 2 | Teams以外のURL | E03 | `https://example.com/some/page?groupId=…` | `ERR_NOT_TEAMS_URL` | ✅ |
| 3 | TeamsのチャットURL | E04 | `https://teams.microsoft.com/l/chat/…` | `ERR_NOT_CHANNEL_MESSAGE_URL` | ✅ |
| 3 | チャットスレッドのメッセージURL | E05 | チャネルIDが `…@unq.gbl.spaces` | `ERR_CHAT_URL_NOT_SUPPORTED` | ✅ |
| 4 | `groupId` がないURL | E06 | クエリに `groupId` 無し | `ERR_GROUPID_NOT_FOUND` | ✅ |
| 5 | チャネルIDがないURL | E07 | `/l/message//{messageId}?…` | `ERR_CHANNELID_NOT_FOUND` | ✅ |
| 6 | メッセージIDがないURL | E08 | `/l/message/{channelId}?…` | `ERR_MESSAGEID_NOT_FOUND` | ✅ |

**すべて期待どおりのエラーコードを返すことを、定義の式を評価して確認済み。**

いずれのケースも、Graph呼び出しをスキップして `Create_Error_Result_Object` によりエラー形式のJSONを組み立て、`varResultObject` / `varResultJson` に格納します（フローは失敗せず完走します）。

### 2-2. Graph応答が必要なもの（実環境確認）

| # | 指示書の要求 | 確認方法 | 期待するエラーコード | 状況 |
|---|---|---|---|---|
| 7 | 存在しない投稿 | URLの messageId を実在しない13桁の値に書き換えて実行 | `ERR_MESSAGE_NOT_FOUND`（HTTP 404） | ⚠ |
| 8 | 削除済み投稿 | 削除した投稿のURLで実行 | `ERR_MESSAGE_DELETED`（`deletedDateTime` あり）または `ERR_MESSAGE_NOT_FOUND`（完全削除時の404） | ⚠ |
| 9 | 権限がないチーム | メンバーでないチームの投稿URLで実行 | `ERR_PERMISSION_DENIED`（HTTP 403） | ⚠ |
| 10 | 権限がないプライベートチャネル | メンバーでないプライベートチャネルの投稿URLで実行 | `ERR_PERMISSION_DENIED`（403）または `ERR_MESSAGE_NOT_FOUND`（404） | ⚠ |
| — | 返信の取得に失敗 | Flow2 で返信取得時にGraphが失敗 | `stage=GetTeamsData` のエラー | ⚠ |
| — | ページネーション途中で失敗 | Flow2 で複数ページ取得中に失敗（スロットリング等） | `ERR_UNEXPECTED_FAILURE` + `partialReplyCount` に取得済み件数 | ⚠ |

> **8・9・10 の分岐先が確定できない理由**: 削除済み投稿にGraphが `deletedDateTime` 付きで応答するか404を返すかは削除方法（ソフト削除／完全削除）に依存します。また権限不足時にGraphが403を返すか404を返すかもテナント設定に依存します。**本フローは両方の経路に対応する実装**（`deletedDateTime` チェック ＋ HTTPステータス判定）にしていますが、実際にどちらを通るかは断定できません。
>
> **共通の追加リスク（⚠）**: 失敗したコネクタアクションの `outputs(…)?['statusCode']` が実際に取得できるかは未確認です。取得できない場合は `httpStatusCode=0` となり `ERR_UNEXPECTED_FAILURE` に落ちます（結果JSONの `error.details` で判別可能）。

---

## 3. パッケージ検証（実施済み）

| 観点 | 確認方法 | 結果 |
|---|---|---|
| ZIPが正常に展開できる | `validation/extract_check.py` | ✅ 両フローとも展開成功・破損なし |
| 必要なファイルが含まれている | 同上 | ✅ レガシー5ファイル構造 |
| JSONが構文エラーになっていない | 同上（全5ファイルをパース） | ✅ |
| 接続参照が壊れていない | `validate_flow*.py` / `extract_check.py` | ✅ `shared_teams` で `connectionReferences` / `apisMap` / `connectionsMap` / `dependsOn` が一致 |
| フロー名が正しい | `extract_check.py` | ✅ |
| トリガーが存在する | `validate_flow*.py` | ✅ manual / Button |
| URL入力が存在する | 同上 | ✅ `TeamsPostUrl`（string・required・表示名「Teams投稿URL」） |
| Teamsアクションが存在する | 同上 | ✅ `shared_teams` / `HttpRequest`（Flow1: 1件、Flow2: 2件） |
| 変数の初期化より前に変数を参照していない | 同上 | ✅ 未初期化変数の参照0件・`InitializeVariable` は全件トップレベル |
| SetVariableで自己参照していない | 同上 | ✅ 自己参照0件（Flow1: 21件中0、Flow2: 24件中0） |
| Apply to each内の配列変数更新で並列処理が有効になっていない | 同上 | ✅ 全 Foreach が `concurrency.repetitions = 1` |
| アクション間の参照名が一致している | 同上 | ✅ `body()` / `outputs()` の参照先が全件実在 |
| `runAfter` の参照先が存在する | 同上 | ✅ 全 `runAfter` が同一コンテナの兄弟 |
| 存在しないアクション名を参照していない | 同上 | ✅ |
| 不正な式や未対応関数を使用していない | 同上 | ✅ 不正な `@` 位置0件・関数許可リスト外0件 |
| マニフェストと実体が一致している | `extract_check.py` | ✅ GUID3点一致・展開結果が `source/package` とバイト一致 |

詳細は [validation_report.md](validation_report.md) を参照してください。

---

## 4. 再実行方法

```powershell
cd projects/teams_post_url_flows
python tests/run_url_parse_tests.py            # URL解析テスト（40件）
python tests/run_url_parse_tests.py flow1      # Flow1のみ
```

テストケースを追加する場合は `tests/run_url_parse_tests.py` の `CASES` に `(ID, 説明, 入力URL, 期待値dict)` を追記してください。期待値は変数名（`varTargetMessageId` 等）をキーにします。エラーコードの期待値は `"varErrorCode": "ERR_…"`、正常なら `"varErrorCode": "-"` と書きます。

---

関連: [validation_report.md](validation_report.md) / [../docs/url_parsing_spec.md](../docs/url_parsing_spec.md) / [../docs/troubleshooting.md](../docs/troubleshooting.md)
