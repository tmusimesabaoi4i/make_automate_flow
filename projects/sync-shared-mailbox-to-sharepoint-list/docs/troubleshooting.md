# トラブルシューティング

## 0. まず見るところ

1. 実行履歴の最後 `Scope_Finalize` → `Compose_Flow_Output` の出力
2. `resultObject.error.code`（何が）/ `.stage`（どこで）/ `.message`（対処）
3. `resultObject.error.details[]`（`httpStatusCode=` と `stage=` が入っている）
4. 件単位の失敗は `resultObject.itemErrors[]`

---

## 1. 入力に関するエラー（SharePoint・Outlook へは一切アクセスしていない）

この段階のエラーでは**リストは作られず、メールも取得されていない**。安全に終了している。

| コード | 対処 |
|---|---|
| `ERR_URL_EMPTY` | サイトURLが空。ブラウザのアドレスバーからコピーする |
| `ERR_URL_NOT_HTTPS` | `http://` になっている。`https://` にする |
| `ERR_URL_NOT_SHAREPOINT` | ホスト名が `.sharepoint.com` で終わっていない。SharePoint Online のURLか確認する |
| `ERR_URL_MALFORMED` | URLの形式が不正。`@` を含む形式（`https://user@host/...`）は受け付けない |
| `ERR_LISTNAME_EMPTY` | リスト名が空、または空白のみ |
| `ERR_LISTNAME_TOO_LONG` | 255文字以内にする |
| `ERR_LISTNAME_INVALID_CHARS` | `" # % * : < > ? / \ \| { } ~ &` と制御文字は使えない |
| `ERR_LISTNAME_INVALID_PERIOD` | 先頭・末尾のピリオドを外す |
| `ERR_LISTNAME_RESERVED` | `forms` `_catalogs` 等の予約名。別の名前にする |
| `ERR_MAILBOX_EMPTY` / `ERR_MAILBOX_INVALID` | `name@domain.tld` の形式で入力する |
| `ERR_COUNT_INVALID` | 1以上の整数を入力する（0・負数・小数・文字は不可） |
| `ERR_COUNT_TOO_LARGE` | 100以下にする。上限の理由は README §9 |

### 「サイトのURLは正しいのに `ERR_URL_MALFORMED` になる」

`https://user@{tenant}.sharepoint.com/...` のように `@` を含む形になっていないか確認する。
ブラウザによっては認証情報付きURLがコピーされることがある。

### 「リスト一覧のURLを貼ったのに 404 になる」

個別リストのビューURL（`.../Lists/{listName}/AllItems.aspx`）を貼っていないか確認する。
このURLは `/_layouts/` を含まないためサイトURLとして切り出せず、
実行時に `ERR_SITE_OR_RESOURCE_NOT_FOUND` になる。
サイトのトップページか「サイトのコンテンツ」（`/_layouts/15/viewlsts.aspx`）のURLを使う。

---

## 2. リストに関するエラー

| コード | 意味 | 対処 |
|---|---|---|
| `ERR_LIST_AMBIGUOUS` | 同名リストが複数見つかった | SharePoint側でリスト名を整理する。フローはリストを変更していない |
| `ERR_LIST_NOT_GENERIC` | 同名リストが非表示リストまたはシステムリスト（ドキュメントライブラリ等）だった | 別のリスト名にする |
| `ERR_LIST_CREATE_FAILED` | 作成に失敗し、同名リストも存在しなかった | `details` の `httpStatusCode` を見る。403 なら権限、400 ならリスト名 |
| `ERR_SCHEMA_INCOMPATIBLE` | 既存リストに必要な列が無い／型が違う | 下記 |

### `ERR_SCHEMA_INCOMPATIBLE` の対処

`resultObject.missingFields` と `incompatibleFields` を見る。

```json
"missingFields": ["BodyPlainText"],
"incompatibleFields": [{"internalName": "ReceivedDateTime", "expected": "DateTime", "actual": "Text"}]
```

- **不足している列**: SharePoint で手動追加する。**内部名**が一致している必要がある。
  列を新規作成するとき、表示名にASCII名（例 `BodyPlainText`）を入れて作成すると内部名がそれになる。
  作成後に表示名だけ日本語へ変更してよい（内部名は変わらない）
- **型が違う列**: 型は後から変更できないことが多い。別のリスト名を使うのが安全
- **フローはリストを一切変更していない**。既存データは無事

### 「新規作成したはずなのに `status` が `Existing` になる」

同時実行で別の実行が先にリストを作成した場合、そのリストを既存として扱う（削除も上書きもしない）。
`resultObject.schemaWarnings` に「同時実行により別の実行がリストを作成済みでした」と入る。正常な動作。

---

## 3. 実行時のエラー

| コード | HTTPステータス | 対処 |
|---|---|---|
| `ERR_PERMISSION_DENIED` | 401 / 403 | 接続を作り直す。SharePointサイトの編集権限、共有メールボックスへのアクセス権を確認する |
| `ERR_SITE_OR_RESOURCE_NOT_FOUND` | 404 | サイトURL・共有メールボックスの実在を確認する |
| `ERR_BAD_REQUEST` | 400 | リスト名・アドレス・件数を確認する |
| `ERR_THROTTLED` | 429 | 待ってから件数を減らして再実行する（Outlook は 300コール/60秒/接続） |
| `ERR_UNEXPECTED_FAILURE` | その他 | 実行履歴で赤いアクションの入出力を確認する |

### 403 が SharePoint 側か Outlook 側か分からない

`error.stage` を見る。

- `CheckList` / `CreateList` / `InitListSchema` / `ConfigureView` / `VerifySchema` / `SyncItems` → SharePoint
- `GetEmails` → Outlook（共有メールボックスへのアクセス権）

---

## 4. 件単位の失敗（`itemErrors[]`）

フロー全体は完走する。1件だけ失敗しても他のメールは処理される。

| コード | 意味 | 対処 |
|---|---|---|
| `ERR_ITEM_MESSAGE_ID_UNUSABLE` | メッセージIDが空、または255文字超 | `MessageId` は1行テキスト列（255文字上限）。該当メールは同期できない（既知の制約） |
| `ERR_BODY_CONVERSION_FAILED` | 本文のプレーンテキスト変換に失敗 | **HTMLはそのまま登録していない**。Content Conversion の接続とDLPを確認する |
| `ERR_ITEM_SEARCH_FAILED` | 既存アイテムの検索に失敗 | **一致0件と誤認せず書き込みを見送っている**。再実行すれば同期される |
| `ERR_ITEM_CREATE_FAILED` | 作成に失敗し再検索でも見つからなかった | `httpStatusCode` を見る。403 なら権限、400 なら列の値 |
| `ERR_ITEM_UPDATE_FAILED` | 既存アイテムの更新に失敗 | 同上 |

---

## 5. 重複異常（`duplicates[]`）

同じメッセージIDのアイテムが2件以上あった場合、**作成も更新もせず**記録だけ行う。

```json
"duplicates": [{"messageId": "<...>", "count": 2, "itemIds": [{"Id": 12}, {"Id": 34}]}]
```

対処: リストを開き、`itemIds` のアイテムを確認して手動で整理する。
`MessageId` 列に一意制約がかかっていれば通常は発生しない。
`schemaWarnings` に「MessageId 列に一意制約が適用されませんでした」が出ている場合は、
列の設定で「一意の値を適用」を有効にする（SharePoint のリスト設定 → 列 → MessageId）。

---

## 6. 本文が途中で切れている（`truncatedItems[]`）

複数行テキスト列の上限（63,999文字）を超えたため切り詰めた。

```json
"truncatedItems": [{"messageId": "<...>", "originalLength": 80000, "storedLength": "63999"}]
```

黙って切り捨ててはいないが、元の全文は保存されていない。
全文が必要なら、そのメールは Outlook 側で確認する。

---

## 7. インポート・保存時のエラー

### `Unable to parse template language expression 'xxx': expected token 'LeftParenthesis' and actual 'EndOfData'`（インポート時）

**本フローで実際に発生した。修正済み**（`..._20260803224500.zip` 以降で解消）。

文字列中に `@{...}` があり、その中身が関数呼び出しでない場合に発生する。
Power Automate は `@{` を**式の補間**として解釈するため、`@{tenant}` は
「`tenant` という関数を呼ぼうとしたが `(` が無い」と判定される。

原因だった記述:

```text
"description": "例: shared-mailbox@{tenant}.example.com。メールは読み取るだけで変更しません"
                              ~~~~~~~~~ ここが式として解釈された
```

- **`{tenant}` のような波かっこ単体は安全**。危険なのは **`@` と `{` が隣接する場合だけ**
- メールアドレスの例を表示テキストに書くと、プレースホルダの直前が必ず `@` になるため踏みやすい
- 対処: 表示テキスト（トリガー入力の `title` / `description`、アクションの固定文言）に
  `@` を書かない。例示は docs 側に置く

検証スクリプトが次の2点を機械検査するようになっている（再発防止）。

| 検査 | 内容 |
|---|---|
| `@{...}` の中身 | `関数名(` で始まらなければエラー |
| トリガー入力の表示テキスト | `title` / `description` に `@` があればエラー |

**`..._20260803213000.zip` は使用しないこと**（この不具合を含む。履歴として残しているだけ）。

### `'@' at position ... is not expected`（インポート時）

式のネストに `@` が付いている。本パッケージは検証スクリプトで
「不正な `@` 位置 0件」を機械確認しているため、本来発生しない。
発生した場合は ZIP が破損していないか `validation/extract_check.py` で確認する。

### `Self reference is not supported`（保存時）

SetVariable が自身の変数を参照している。本パッケージは検証スクリプトで
「自己参照 0件」を機械確認しているため、本来発生しない。

### `OpenApiOperationParameterValidationFailed`（保存時）

コネクタの必須パラメータが欠けている。**本フローで最も起こりうる保存時エラー**。

【要実環境確認】`GetEmailsV3` のパラメータキー名は公式リファレンスに基づいて設定しているが、
本セッションでは同一ページの再取得でパラメータ表が食い違う事象があり、確定できていない。
このエラーが `Get_Emails` で出た場合の切り分け:

1. デザイナーで `Get_Emails` アクションを開き、表示される入力欄の名前を確認する
2. 欠けている必須パラメータがあれば画面上で設定して保存する
3. 恒久対応として `source/build_sync_flow.py` の `emails_inner["Get_Emails"]` の
   パラメータキーを実際の名前に直し、再生成・再検証・再パッケージする
   （`definition.json` は生成物。直接編集しない）

同様に `Convert_Body_To_Text`（`HtmlToText` の `Content`）でも起こりうる。

### アクション名の重複

検証スクリプトで「全体一意」を機械確認済み。本来発生しない。

---

## 8. Content Conversion が使えない環境

DLPポリシーで Content Conversion が遮断されている場合、本フローは動作しない
（`ERR_BODY_CONVERSION_FAILED` が全件に出る）。

### 検討した代替と、採用しなかった理由

| 代替 | 判断 |
|---|---|
| 標準コネクタだけで `replace()` を連ねてHTMLタグを除去 | **採用しない**。WDL に正規表現が無く、タグの入れ子・属性値中の `>`・HTMLエンティティ（`&nbsp;` `&amp;` 等）・`<br>` の改行化を正しく扱えない。「HTMLをそのまま保存しない」という要件は満たせても、本文が壊れる |
| `Body Preview` を本文として保存 | **禁止**（指示§25）。冒頭の抜粋にすぎず本文全体ではない |
| HTTP with Microsoft Entra ID + Graph | **採用しない**。Azureアプリ登録と管理者同意が必要で、本リポジトリの「一般ユーザー権限で完結させる」方針に反する |

したがって Content Conversion が使えない環境では、
**管理者にDLPポリシーの例外追加を依頼する**のが唯一の対応になる。

---

## 9. 期待した件数が取れない

`requestedCount` と `fetchedCount` を比べる。

- `fetchedCount < requestedCount` で、受信トレイのメールがそもそも少ない → 正常
- 受信トレイに十分あるのに少ない → 【要実環境確認】`GetEmailsV3` の `top` が
  効いているか、`folderPath` が受信トレイを指しているかをデザイナーで確認する

### 最新のメールが取れていない

【要実環境確認】本フローは `sort` + `reverse` で受信日時の降順に並べ替えてから上位N件を採る。
ただし `GetEmailsV3` が**古い順にN件返す**仕様だった場合、
並べ替えても「古いN件の中での降順」にしかならない。

確認方法: リストを開き、最上位のアイテムの日時が Outlook の受信トレイの最新メールと
一致するか見る。一致しない場合は取得件数を増やすか、Outlook 側で並び順を指定できるか確認する。

---

## 10. 開発側での再検証

```powershell
cd D:\make_automate_flow
$p = "projects/sync-shared-mailbox-to-sharepoint-list"
python "$p/flows/sync-mail-to-list/source/build_sync_flow.py"
python "$p/flows/sync-mail-to-list/source/validate_sync_flow.py"    # errors 0 / warnings 0
python "$p/tests/run_offline_tests.py"                              # 57件合格
python "$p/flows/sync-mail-to-list/validation/extract_check.py"     # errors 0
```

`definition.json` は生成物。**直接編集せず** `source/build_sync_flow.py` を編集して再生成する。
