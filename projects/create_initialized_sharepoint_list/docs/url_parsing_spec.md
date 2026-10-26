# URL解析仕様

入力された SharePoint URL から、REST API の接続先として使うサイトURLを取り出す仕組みの仕様です（指示書§4・§5）。

本書の式は生成済み `definition.json` からそのまま抜き出したものです。変更は `flows/create-initialized-list/source/build_list_flow.py` を編集して再生成し、`tests/run_url_parse_tests.py` を再実行してください。

---

## 1. 対応するURL形式

| 形式 | 例 | 抽出結果 |
|---|---|---|
| サイトのルートURL | `https://{tenant}.sharepoint.com/sites/{site}` | 同じ |
| リスト一覧ページ | `.../sites/{site}/_layouts/15/viewlsts.aspx` | `.../sites/{site}` |
| クエリパラメーター付き | `.../viewlsts.aspx?view=14` | `.../sites/{site}` |
| サブサイト | `.../sites/{site}/{subsite}/_layouts/15/viewlsts.aspx` | `.../sites/{site}/{subsite}` |
| テナントルートサイト | `https://{tenant}.sharepoint.com` | 同じ |

加えて次の揺れに対応します。

| 揺れ | 対応 |
|---|---|
| 前後の空白 | `trim()` で除去 |
| 末尾のスラッシュ | 除去 |
| フラグメント（`#...`） | 切り捨て |
| `/_Layouts/` `/_LAYOUTS/` の表記ゆれ | 小文字形へ正規化してから分割 |
| サイトルートにクエリだけが付く | クエリを除去 |

**固定文字数・特定サイト名の固定値には依存していません。** すべて区切り文字（`#` `?` `/` `/_layouts/` `//`）による分割です。

---

## 2. 解析チェーン（Scope_Parse_And_Validate_Input）

```text
Compose_Url_Without_Fragment
@first(split(variables('varInputSharePointUrl'), '#'))

Compose_Url_Normalized_Layouts          ← 大文字小文字の表記ゆれを吸収
@replace(replace(outputs('Compose_Url_Without_Fragment'), '/_Layouts/', '/_layouts/'),
         '/_LAYOUTS/', '/_layouts/')

Compose_Url_Before_Layouts              ← /_layouts/ があればその直前まで／無ければクエリ除去
@if(contains(outputs('Compose_Url_Normalized_Layouts'), '/_layouts/'),
    first(split(outputs('Compose_Url_Normalized_Layouts'), '/_layouts/')),
    first(split(outputs('Compose_Url_Normalized_Layouts'), '?')))

Parse_SiteUrl                           ← 末尾スラッシュを除去
@if(endsWith(outputs('Compose_Url_Before_Layouts'), '/'),
    join(take(split(outputs('Compose_Url_Before_Layouts'), '/'),
              sub(length(split(outputs('Compose_Url_Before_Layouts'), '/')), 1)), '/'),
    outputs('Compose_Url_Before_Layouts'))

Compose_Site_Host                       ← スキームの大文字小文字に依存しないホスト抽出
@first(split(last(split(outputs('Parse_SiteUrl'), '//')), '/'))
```

最後に `Set_SiteUrl` が `varSiteUrl` へ確定します。この値が全 HTTP 要求の `dataset`（サイトのアドレス）になります。

> **末尾スラッシュ除去に `substring` を使わない理由**
> Logic Apps / Power Automate の `if()` は**両方の分岐の引数を先に評価**します。`substring(P, 0, sub(length(P), 1))` は `P` が空文字のとき長さ `-1` となり、条件が false でも実行時エラーになり得ます。`split → take → join` なら `P=''` でも `split('','/')=['']` → `take(…,0)=[]` → `join([],'/')=''` となり安全です。
>
> **ホスト抽出に `replace('https://','')` を使わない理由**
> `replace` は大文字小文字を区別するため `HTTPS://` に一致しません。`//` で分割する方式なら scheme の表記に依存しません。

---

## 3. 使用した関数

`handbook/rules/02_expression_and_type_safety.md` の「実在確認済みの関数のみ使う」に従い、本リポジトリの実働 `definition.json` に出現実績のある関数を使っています。`validate_list_flow.py` の**関数許可リスト検査**で機械的に担保しています。

```text
trim coalesce concat split first last join take if not and or empty contains equals
greater greaterOrEquals lessOrEquals startsWith endsWith replace length sub int
string json toLower decodeUriComponent createArray union
variables outputs body item items triggerBody triggerOutputs decodeBase64
```

### `toLower` について

**本リポジトリで初めて使用する関数です。** 採用理由:

- 指示書§9.2 が同名リスト判定に `toLower(trim(item()?['Title']))` を**明示的に指定**している
- Microsoft の公式ワークフロー定義言語 関数リファレンスに実在する基本関数である

許可リストにはその旨を注記して追加しています。他の関数はすべて本リポジトリ内に使用実績があります。

---

## 4. URL の検証（§6.1）

`Validate_SiteUrl`（Compose）が、最初に該当した1つのエラーコードを返します。空文字なら正常です。

| 順 | 条件 | エラーコード |
|---|---|---|
| 1 | 入力URLが空（trim後） | `ERR_URL_EMPTY` |
| 2 | 抽出結果が `https://` で始まらない | `ERR_NOT_HTTPS` |
| 3 | ホスト名が `.sharepoint.com` で終わらない | `ERR_NOT_SHAREPOINT_HOST` |
| 4 | サイトURLを抽出できない（空） | `ERR_SITE_URL_NOT_EXTRACTED` |

ホスト名で判定するため、`https://sharepoint.com.evil.example/...` のような紛らわしいURLも `ERR_NOT_SHAREPOINT_HOST` で弾きます（テスト E05）。

「SharePoint REST API へ接続できない」「接続ユーザーが対象サイトを参照できない」は、この静的検証では判定できません。`Scope_Verify_SharePoint_Site` の `_api/web` 呼び出しの結果（401/403/404）で判定します（[safety_mechanisms.md](safety_mechanisms.md) §7）。

---

## 5. リスト名の検証（§6.2）

`Validate_ListName`（Compose）が判定します。**入力されたリスト名を勝手に別の名前へ変更することはありません。** 使えない名前はエラーとして返します。

| 順 | 条件 | エラーコード |
|---|---|---|
| 1 | trim 後に空 | `ERR_LIST_NAME_EMPTY` |
| 2 | 255文字を超える | `ERR_LIST_NAME_TOO_LONG` |
| 3 | 禁止文字または制御文字を含む | `ERR_LIST_NAME_INVALID_CHARS` |
| 4 | 先頭または末尾がピリオド | `ERR_LIST_NAME_INVALID_PERIOD` |
| 5 | 予約名に該当 | `ERR_LIST_NAME_RESERVED` |

使用するのは **trim 後の値**です（`varListName` は初期化時点で `@trim(...)` 済み）。

### 禁止文字の検出方法

禁止文字を1つずつ `replace` で除去した文字列を作り、**元の長さと比較**します。長さが変われば禁止文字が含まれていた、という判定です。

```text
Compose_ListName_Sanitized
@replace(replace(… replace(variables('varListName'), '"', ''), '#', '') …,
         decodeUriComponent('%0A'), '')

判定: not(equals(length(varListName), length(outputs('Compose_ListName_Sanitized'))))
```

除去対象:

```text
記号   "  #  %  *  :  <  >  ?  /  \  |  {  }  ~
制御   %09（タブ） %0D（CR） %0A（LF）
```

**空白と日本語はそのまま通します**（指示書§33 の「日本語のリスト名」「空白を含むリスト名」を正常系として扱うため）。

> **既知の限界**: 検出できる制御文字はタブ・CR・LF の3種類だけです。他の制御文字（`%00`〜`%08` 等）はワークフロー定義言語の式では列挙的にしか扱えないため検出していません。これらを含む名前は SharePoint 側で拒否され、`ERR_CREATE_CONFLICT`（HTTP 400）として返ります。

### 予約名

```text
con  prn  aux  nul  forms  _catalogs  _private  _vti_bin  _vti_pvt  _vti_cnf
app packages  appdata
```

`contains(createArray(…), toLower(variables('varListName')))` で判定するため、大文字小文字を問わず検出します（テスト N12: `NUL`）。

> この一覧は Windows のデバイス予約名と SharePoint のシステムフォルダ名から構成した**保守的な集合**です。SharePoint が実際に拒否する名前の完全な一覧は公開されていないため、ここに無い名前が SharePoint 側で拒否される可能性があります。その場合は作成が 400 で失敗し、`ERR_CREATE_CONFLICT` として返ります（既存リストには影響しません）。

### 判定順序

URL のエラーが優先されます。

```text
Compose_Input_Validation_Code
@if(not(empty(outputs('Validate_SiteUrl'))), outputs('Validate_SiteUrl'),
    outputs('Validate_ListName'))
```

---

## 6. 対応できないURL（明記）

| 形式 | 挙動 |
|---|---|
| 個別リストのビューURL（`.../Lists/<名前>/AllItems.aspx`） | `/_layouts/` を含まないためサイトURLとして切り出せず、URL全体が `varSiteUrl` になる。**解析段階では検出できず、実行時に `_api/web` が 404 を返して `ERR_SITE_OR_RESOURCE_NOT_FOUND` で失敗する**（誤ったサイトへ書き込む危険はない） |
| `http://`（非TLS） | `ERR_NOT_HTTPS` |
| SharePoint 以外のホスト | `ERR_NOT_SHAREPOINT_HOST` |
| OneDrive の個人サイト（`-my.sharepoint.com`） | ホスト判定は通るが、リスト作成の可否は未確認（**要実環境確認**） |

対応する形式は §1 の5種類です。それ以外を渡した場合でも、**既存リストに変更が及ぶ経路はありません**。

---

## 7. 検証方法（オフライン）

`tests/run_url_parse_tests.py` は、生成済み `definition.json` から `Scope_Parse_And_Validate_Input` を読み出し、`tools/wdl_eval.py`（案件横断のWDL式ミニ評価器）で**定義に実際に書かれている式そのもの**を評価します。

```powershell
python tests/run_url_parse_tests.py
```

2026-07-24 実行結果: **35件中35件合格**（`tests/url_parse_test_result.txt`）。内訳は URL正常系11・URL異常系5・リスト名正常系5・リスト名異常系13・判定順序1。

各ケースでは期待値の照合に加えて、**`varErrorCode` と `varIsValid` の整合**（エラーコードが空でなければ `varIsValid` は false）も検査しています。

**この検証で確認できないこと**: Power Automate 実機での関数の挙動差、SharePoint REST の応答、保存時検証、実行時エラー。

---

関連: [list_operations_spec.md](list_operations_spec.md) / [safety_mechanisms.md](safety_mechanisms.md) / [troubleshooting.md](troubleshooting.md)
