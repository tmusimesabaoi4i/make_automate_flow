# URL正規化と入力検証の仕様

トリガー入力4項目の検証と、SharePointサイトURLの抽出方法。
**この検証を通過するまで SharePoint / Outlook へ一切アクセスしない**（指示§5）。

検証結果は `varIsValid` / `varErrorCode` / `varErrorMessage` に入り、
NG の場合は以降のスコープがすべてガードで素通りして `Scope_Finalize` に到達する。
Catch Scope（`Scope_Handle_Error`）には落とさない（**想定内エラー**として正常系で処理する）。

---

## 1. サイトURLの正規化

`Scope_Validate_Input` 内の Compose チェーン。**固定文字数では切らない。**

| # | アクション | 式 |
|---|---|---|
| 1 | `Compose_Url_No_Fragment` | `first(split(variables('varInputSharePointUrl'), '#'))` |
| 2 | `Compose_Url_No_Query` | `first(split(<1>, '?'))` |
| 3 | `Compose_Url_Before_Layouts` | `substring(<2>, 0, length(first(split(toLower(<2>), '/_layouts/'))))` |
| 4 | `Compose_Site_Url` | 末尾スラッシュ除去（下記） |
| 5 | `Compose_Site_Host` | `first(split(last(split(<4>, '//')), '/'))` |
| 6 | `Compose_Site_Origin` | `if(greaterOrEquals(length(split(<4>,'/')), 3), join(take(split(<4>,'/'), 3), '/'), '')` |

トリガー入力は `trim(coalesce(triggerBody()?['SharePointUrl'], ''))` で受けているため、
前後の空白は最初に除去されている。

### 3 の要点（`/_layouts/` 以降の除去）

```text
substring(U, 0, length(first(split(toLower(U), '/_layouts/'))))
```

- `toLower(U)` に対して分割するので **`/_Layouts/` `/_LAYOUTS/` の表記ゆれに依存しない**
- `/_layouts/` が**無い**場合、`first(split(...))` は `U` 全体になり `length` は `U` の長さ。
  結果は `substring(U, 0, length(U))` ＝ `U` そのもの
- したがって**分岐が要らず、`if()` の両分岐先行評価による事故が起きない**
  （[handbook/rules/02](../../../handbook/rules/02_expression_and_type_safety.md)）
- 空文字入力でも `substring('', 0, 0)` ＝ `''` で安全

### 4 の要点（末尾スラッシュ除去）

```text
if(endsWith(P, '/'),
   join(take(split(P, '/'), sub(length(split(P, '/')), 1)), '/'),
   P)
```

`substring(P, 0, sub(length(P), 1))` を**使わない**。`if()` は両分岐を先行評価するため、
`P` が空文字のとき `sub(length(P),1)` が `-1` になり、条件が false でも実行時エラーになりうる。
`split` → `take` → `join` なら空文字でも `''` を返して安全
（[expression_examples.md 15-B](../../../handbook/knowledge/expression_examples.md)）。

### 変換例

| 入力 | 正規化後（`varSiteUrl`） |
|---|---|
| `https://{tenant}.sharepoint.com/sites/{site}` | 同左 |
| `https://{tenant}.sharepoint.com/sites/{site}/` | `.../sites/{site}` |
| `https://{tenant}.sharepoint.com/sites/{site}/_layouts/15/viewlsts.aspx` | `.../sites/{site}` |
| `.../_layouts/15/viewlsts.aspx?view=14` | `.../sites/{site}` |
| `.../_layouts/15/viewlsts.aspx#top` | `.../sites/{site}` |
| `.../_Layouts/15/viewlsts.aspx`（大文字L） | `.../sites/{site}` |
| `.../sites/{site}/subsite01/_layouts/15/viewlsts.aspx` | `.../sites/{site}/subsite01` |
| `https://{tenant}.sharepoint.com`（ルートサイト） | 同左 |

`varSiteOrigin` は `https://{tenant}.sharepoint.com` の部分だけを取り出したもので、
結果の `listUrl` を組み立てるのに使う。

---

## 2. 対応できないURL（既知の限界）

**個別リストのビューURL**（`.../sites/{site}/Lists/{listName}/AllItems.aspx`）は
`/_layouts/` を含まないため、サイトURLとして切り出せず URL 全体がそのまま `varSiteUrl` になる。

- 解析段階では検出できない（形式としては正しいSharePoint URLのため）
- 実行時に `GET _api/web` が 404 を返し、`ERR_SITE_OR_RESOURCE_NOT_FOUND` で**明確に失敗**する
- **誤ったサイトへ書き込む危険は無い**（`_api/web` が通らない限り以降のRESTに到達しない）

URLに含まれるリスト名は**採用しない**。作成対象のリスト名は `ListName` 入力のみを使う（指示§4.1）。

---

## 3. URLの検証

| # | 判定 | エラーコード |
|---|---|---|
| 1 | 入力が空 | `ERR_URL_EMPTY` |
| 2 | `https://` で始まらない | `ERR_URL_NOT_HTTPS` |
| 3 | ホスト名が `.sharepoint.com` で終わらない | `ERR_URL_NOT_SHAREPOINT` |
| 4 | ホスト名に `@` を含む（userinfo 付きURL） | `ERR_URL_MALFORMED` |
| 5 | オリジンを抽出できない（`//` を含むセグメントが3未満） | `ERR_URL_MALFORMED` |
| 6 | 正規化後のサイトURLが空 | `ERR_URL_MALFORMED` |

判定はこの順で、最初に該当したものを採用する。

### 別テナントのURLについて

「別テナントのURLを無条件で処理しない」（指示§4.1）への対応は2段構えにしている。

1. **形式検証**: `https://` かつ `*.sharepoint.com` かつ userinfo 無し。
   `https://sharepoint.com.evil.example/...` のような偽装ホストは 3 で弾く
2. **疎通確認**: 書き込みの前に `GET _api/web?$select=Id,Title,Url` を必ず通す。
   SharePoint接続のスコープ外サイトはここで失敗し、以降のRESTに到達しない

【要実環境確認】自テナント判定そのものはフロー内では行えない（自テナント名を定義に固定しない方針のため）。
接続のスコープに依存する。

---

## 4. リスト名の検証

| # | 判定 | エラーコード |
|---|---|---|
| 1 | trim 後に空 | `ERR_LISTNAME_EMPTY` |
| 2 | 255文字超 | `ERR_LISTNAME_TOO_LONG` |
| 3 | 禁止文字・制御文字を含む | `ERR_LISTNAME_INVALID_CHARS` |
| 4 | 先頭または末尾がピリオド | `ERR_LISTNAME_INVALID_PERIOD` |
| 5 | 予約名 | `ERR_LISTNAME_RESERVED` |

### 禁止文字の検出方法

WDL には正規表現が無いため、**除去前後の長さ比較**で検出する。

```text
Compose_ListName_Sanitized =
  replace(replace(...replace(variables('varListName'), '"', '')..., '&', ''),
          decodeUriComponent('%09'), '')  …… タブ/CR/LF も同様に除去

判定: length(varListName) != length(outputs('Compose_ListName_Sanitized')) → 混入あり
```

対象文字: `" # % * : < > ? / \ | { } ~ &`
制御文字: タブ（`%09`）・CR（`%0D`）・LF（`%0A`）を `decodeUriComponent()` で表現

**限界**: 上記3種以外の制御文字（`%00`〜`%08` 等）は式で表現できないため検出できない。
実行時に SharePoint 側が 400 を返し `ERR_BAD_REQUEST` になる。

### 予約名

`con` / `prn` / `aux` / `nul` / `forms` / `_catalogs` / `_private` / `_vti_bin` / `_vti_pvt` /
`_vti_cnf` / `app packages` / `appdata`（`toLower` して比較）

---

## 5. 共有メールボックスの検証

| # | 判定 | エラーコード |
|---|---|---|
| 1 | trim 後に空 | `ERR_MAILBOX_EMPTY` |
| 2 | `@` で分割して2要素にならない（`@` が0個または2個以上） | `ERR_MAILBOX_INVALID` |
| 3 | ローカル部が空 | `ERR_MAILBOX_INVALID` |
| 4 | ドメイン部に `.` を含まない | `ERR_MAILBOX_INVALID` |
| 5 | ドメイン部の先頭または末尾が `.` | `ERR_MAILBOX_INVALID` |

RFC 準拠の厳密な検証ではなく、**明らかな誤入力を弾く**ための最小限の形式検査。
実在性とアクセス可否は実行時に Outlook 側が判定し、401/403 なら `ERR_PERMISSION_DENIED`、
404 なら `ERR_SITE_OR_RESOURCE_NOT_FOUND` になる。

---

## 6. 取得件数の検証

`int()` を直接使わない。`int('abc')` は実行時エラーになり、`if()` は両分岐を先行評価するため
「条件で守る」ことができないため。**まず文字列で受けて数字だけかを検査する。**

| # | アクション | 内容 |
|---|---|---|
| 1 | `Initialize_RawCount` | `trim(string(coalesce(triggerBody()?['MailCount'], 0)))` |
| 2 | `Compose_Count_Digits_Removed` | `0`〜`9` を順に `replace` で除去 |
| 3 | `Compose_Count_Safe` | 「空でない」かつ「数字だけ」かつ「9桁以内」なら生値、そうでなければ `'0'` |
| 4 | `Compose_Count_Numeric` | `int(outputs('Compose_Count_Safe'))` ← **必ず数字だけの文字列なので安全** |

| # | 判定 | エラーコード |
|---|---|---|
| 1 | 生値が空 | `ERR_COUNT_INVALID` |
| 2 | 数字以外を含む（負号 `-`・小数点 `.`・英字） | `ERR_COUNT_INVALID` |
| 3 | 10桁以上 | `ERR_COUNT_TOO_LARGE` |
| 4 | 0以下 | `ERR_COUNT_INVALID` |
| 5 | 101以上 | `ERR_COUNT_TOO_LARGE` |

トリガーのスキーマは `"type": "integer"` のため、デザイナー上では数値以外の入力は
そもそも受け付けられない。上記は**多層防御**として実装している。

---

## 7. 検証の優先順位

`Compose_Input_Validation_Code` が、最初に空でないものを採用する。

```text
URL → リスト名 → メールボックス → 取得件数
```

複数の入力が同時に不正な場合、この順で最初のものだけが `error.code` になる。
すべてのエラーは `error.details` にも積まれる。

---

## 8. 検証方法（オフライン）

`tests/run_offline_tests.py` が、**生成済み `definition.json` の式そのもの**を
`tools/wdl_eval.py` で評価して検証する。設計書の再実装は検証しない。

```powershell
python projects/sync-shared-mailbox-to-sharepoint-list/tests/run_offline_tests.py
```

URL 18件 / リスト名 13件 / メールボックス 7件 / 件数 9件 / 優先順位 2件 / ODataエスケープ 8件
＝ **計57件**。結果は `tests/offline_test_result.txt`。

**確認できないこと**: Power Automate 実機での挙動、コネクタの実応答、
メールの降順整列（`sort`/`reverse` は `wdl_eval` 未実装）。いずれも要実環境確認。
