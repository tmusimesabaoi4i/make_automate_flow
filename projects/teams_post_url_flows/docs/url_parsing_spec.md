# URL解析仕様

Flow1 / Flow2 が Teams投稿URLから識別子を取り出す仕組みの仕様です。両フローは**同一の解析チェーン**を持ちます（アクション名・式ともに同じ）。

本書に載せている式は、生成済みの `definition.json` からそのまま抜き出したものです。式を変更するときは `flows/*/source/build_flow*.py` を編集して再生成し、`tests/run_url_parse_tests.py` を再実行してください。

---

## 1. 前提とする入力

Teamsのチャネル投稿で「…」→「リンクをコピー」を実行すると得られるURL。代表形は次のとおりです。

```text
https://teams.microsoft.com/l/message/{channelId}/{messageId}?tenantId={tenantId}&groupId={groupId}&parentMessageId={parentMessageId}
```

実際には次のような表記揺れがあり、いずれも解析できるように設計しています。

| 揺れ | 例 | 対応 |
|---|---|---|
| チャネルIDがURLエンコード | `19%3Aabc%40thread.tacv2` | `decodeUriComponent()` で復号 |
| チャネルIDが生 | `19:abc@thread.tacv2` | 復号は無害（%が無ければ素通り） |
| クエリの順番が違う | `?groupId=…&tenantId=…` | 名前アンカーで抽出（位置非依存） |
| `parentMessageId` が無い | `?tenantId=…&groupId=…` | 空文字として扱い、パス上の messageId を採用 |
| `parentMessageId=0` | 親投稿リンクの変種 | 「値なし」と同等に扱う（後述 §4） |
| 末尾に追加パラメーター | `&teamName=…&channelName=…&createdTime=…` | 無視して必要な3つだけ取り出す |
| 前後に空白 | `"  https://… "` | `trim()` で除去 |
| フラグメント付き | `…?groupId=…#anchor` | `#` 以降を切り捨て |
| パス末尾にスラッシュ | `…/{messageId}/` | 除去してから分割 |
| 新Teamsドメイン | `teams.cloud.microsoft` | ホスト判定に含める |

**固定文字数・固定位置には一切依存していません。** すべて区切り文字（`#` `?` `&` `/` `/l/message/`）による分割で解析します。

---

## 2. 採用した関数と、指示された関数を採用しなかった理由

`handbook/rules/02_expression_and_type_safety.md` の「実在確認済みの関数のみ使う」に従い、**本リポジトリの実働 `definition.json` に出現実績のある関数だけ**を使いました。`flows/*/source/validate_flow*.py` に許可リスト検査を実装しており、リスト外の関数が定義に現れるとエラーになります。

実際に使用している関数:

```text
trim  coalesce  concat  split  first  last  if  not  or  empty  contains  equals
endsWith  join  take  length  sub  decodeUriComponent  uriComponent  json  string
variables  outputs  body  item  items  triggerBody  utcNow  union  createArray  decodeBase64
```

### 指示書§4で例示された関数のうち、置き換えたもの

| 例示された関数 | 採用したもの | 理由 |
|---|---|---|
| `uriQuery()` | `split()` によるクエリ抽出 | 本リポジトリ内に使用実績が無い。また後述の「名前アンカー方式」なら追加関数なしで順不同・欠落に対応できるため、実在確認の取れた関数だけで完結させた |
| `uriPath()` | `split()` によるパス抽出 | `uriPath()` がパス中の `%3A` を復号するかどうかを本リポジトリ内の実績から確定できず、チャネルIDの復号タイミングが不定になる。分割方式なら復号は `decodeUriComponent()` の1箇所に限定できる |
| `uriComponentToString()` | `decodeUriComponent()` | 同機能。`decodeUriComponent()` は本リポジトリの実働定義に使用実績あり（3件） |

`trim` `split` `first` `last` `replace` `contains` `if` `empty` は指示書の例示どおり採用しています。

---

## 3. 解析チェーン（Scope_ParseUrl）

`Compose`（作成）で段階的に導出し、最後に変数へ確定します。段階を分けているのは、実行履歴で中間値を1つずつ確認できるようにするためです（`handbook/rules/02`「複雑な式は Compose で分割」）。

### 3.1 URLの分解

```text
Compose_Url_Without_Fragment
@first(split(variables('varInputUrl'), '#'))

Compose_Url_Path_Raw
@first(split(outputs('Compose_Url_Without_Fragment'), '?'))

Compose_Url_Path_Part            ← 末尾スラッシュを除去
@if(endsWith(outputs('Compose_Url_Path_Raw'), '/'),
    join(take(split(outputs('Compose_Url_Path_Raw'), '/'),
              sub(length(split(outputs('Compose_Url_Path_Raw'), '/')), 1)), '/'),
    outputs('Compose_Url_Path_Raw'))

Compose_Url_Query_Part
@if(contains(outputs('Compose_Url_Without_Fragment'), '?'),
    last(split(outputs('Compose_Url_Without_Fragment'), '?')), '')

Compose_Query_Normalized         ← 前後に & を付ける（§3.3の要）
@concat('&', outputs('Compose_Url_Query_Part'), '&')

Compose_Message_Path_Tail        ← "{channelId}/{messageId}"
@if(contains(outputs('Compose_Url_Path_Part'), '/l/message/'),
    last(split(outputs('Compose_Url_Path_Part'), '/l/message/')), '')
```

> **末尾スラッシュ除去に `substring` を使わなかった理由**
> Logic Apps / Power Automate の `if()` は**両方の分岐の引数を先に評価**します。`substring(P, 0, sub(length(P), 1))` は `P` が空文字のとき長さ `-1` となり、条件が false でも実行時エラーになり得ます。`split → take → join` 方式なら `P=''` でも `split('','/')=['']` → `take(…, 0)=[]` → `join([], '/')=''` となり安全です。同じ理由で、解析チェーン全体から長さ計算を伴う `substring` を排除しています。

### 3.2 パスからの抽出

```text
Parse_ChannelId_From_Path
@trim(decodeUriComponent(first(split(outputs('Compose_Message_Path_Tail'), '/'))))

Parse_MessageId_From_Path
@if(contains(outputs('Compose_Message_Path_Tail'), '/'),
    trim(decodeUriComponent(last(split(outputs('Compose_Message_Path_Tail'), '/')))), '')
```

`Compose_Message_Path_Tail` が空でも `split('', '/')` は `['']` を返すため、`first()` は空文字になり例外になりません。空文字は §5 の検証で `ERR_CHANNELID_NOT_FOUND` として弾かれます。

`messageId` は「`/` が含まれる場合のみ」取り出します。`/l/message/{channelId}` だけで messageId が無いURLでは、`last()` がチャネルIDを拾ってしまうのを防ぐためです。

### 3.3 クエリからの抽出（名前アンカー方式）

クエリ文字列の**順番に依存しません**。取り出したいパラメーター名 `P` に対して、正規化クエリ（前後に `&` を付けたもの）を `'&P='` で分割します。

```text
@if(contains(outputs('Compose_Query_Normalized'), '&groupId='),
    trim(decodeUriComponent(first(split(last(split(outputs('Compose_Query_Normalized'), '&groupId=')), '&')))),
    '')
```

動作例（`&tenantId=T&groupId=G&parentMessageId=P&`）:

1. `split(q, '&groupId=')` → `['&tenantId=T', 'G&parentMessageId=P&']`
2. `last(...)` → `'G&parentMessageId=P&'`
3. `split(..., '&')` → `['G', 'parentMessageId=P', '']`
4. `first(...)` → `'G'`

**先頭に `&` を足しているのが要点です。** 単に `'parentMessageId='` で探すと `messageId=` が `parentMessageId=` に部分一致してしまいますが、`'&parentMessageId='` のように区切り文字でアンカーすればトークン境界が確定します。パラメーターが存在しない場合は `contains()` が false になり空文字を返します。

この式で `tenantId` / `groupId` / `parentMessageId` の3つを取り出します（アクション名: `Parse_TenantId_From_Query` / `Parse_TeamId_From_Query` / `Parse_ParentMessageId_From_Query`）。

---

## 4. targetMessageId の決定

```text
Determine_TargetMessageId
@if(or(empty(variables('varParentMessageId')),
       equals(variables('varParentMessageId'), '0')),
    variables('varUrlMessageId'),
    variables('varParentMessageId'))
```

指示書§3の優先順位（`parentMessageId` があり空でなければそれを使う／無ければパス上の `messageId`）に、**`'0'` を「値なし」と同等に扱う条件を追加**しています。

- 理由: 親投稿の「リンクをコピー」で `parentMessageId=0` が付く変種が存在します。Teamsのメッセージ ID は13桁のエポックミリ秒であり `'0'` は実在しないため、そのまま Graph に渡すと必ず 404 になります。
- 返信のURLを入力した場合は `parentMessageId` が親投稿を指すため、**親投稿とその全返信**を取得できます（指示書§3の意図どおり）。
- 親投稿のURLで `parentMessageId` が messageId と同値の場合は、どちらを採用しても結果は同じです。

**URLの `groupId` はチームID、パス上の `{channelId}` はチャネルIDとして扱います。**（`groupId` をチャネルIDに流用したり、返信IDを常に親投稿IDとして扱ったりはしていません。）
**チーム名・チャネル名はURLから取得できるものとして扱っていません。** URLの `teamName` / `channelName` クエリは表示用の付随情報にすぎないため、識別子としては一切使用していません。

---

## 5. 検証とエラーコード

`Validate_ParsedIdentifiers`（Compose）が、最初に該当した1つのエラーコードを返します。空文字なら正常です。判定順は次のとおりです。

| 順 | 条件 | エラーコード |
|---|---|---|
| 1 | 入力URLが空 | `ERR_URL_EMPTY` |
| 2 | `teams.microsoft.com` / `teams.cloud.microsoft` のどちらも含まない | `ERR_NOT_TEAMS_URL` |
| 3 | パスに `/l/message/` が無い | `ERR_NOT_CHANNEL_MESSAGE_URL` |
| 4 | チャネルIDに `unq.gbl.spaces` を含む（＝チャットスレッド） | `ERR_CHAT_URL_NOT_SUPPORTED` |
| 5 | `groupId` が取得できない | `ERR_GROUPID_NOT_FOUND` |
| 6 | チャネルIDが取得できない | `ERR_CHANNELID_NOT_FOUND` |
| 7 | `targetMessageId` が取得できない | `ERR_MESSAGEID_NOT_FOUND` |

続く `Set_ErrorCode_From_Validation` / `Set_IsValid` / `Set_ErrorMessage_From_Validation` が変数に確定し、`Condition_Has_Parse_Error` が `varErrorMessages` へ1件追加します。

`varIsValid` が false のときは Graph 呼び出しをスキップし、`Scope_CreateResult` がエラー形式のJSONを組み立てます（詳細は `json_schema.md`）。

### 既知の制限

- **`contains()` は大文字小文字を区別します。** 判定対象（ホスト名・`/l/message/`）はいずれも Teams が生成する小文字の文字列なので実運用では問題になりませんが、URLを手入力で大文字化した場合（例 `https://TEAMS.microsoft.com/…`）は `ERR_NOT_TEAMS_URL` になります。「リンクをコピー」の値をそのまま貼り付けてください。
- チャネル種別（標準／プライベート／共有）はURLからは判別できません。URL上の見た目は同じで、実際にアクセスできるかは実行時のGraph応答で決まります（`connector_requirements.md` の §制限を参照）。

---

## 6. 検証方法（オフライン）

`tests/run_url_parse_tests.py` は、**生成済み `definition.json` の式文字列そのもの**を `tools/wdl_eval.py`（案件横断のWDL式ミニ評価器）で評価し、入力URLごとの解析結果を期待値と突き合わせます。Power Automate実機を使わずに解析ロジックを検証できます。

```powershell
python tests/run_url_parse_tests.py          # Flow1 / Flow2 の両方
python tests/run_url_parse_tests.py flow1    # 片方だけ
```

2026-07-24 実行結果: **Flow1 20件 / Flow2 20件、合計40件すべて合格**（`tests/url_parse_test_result.txt`）。ケース一覧は `tests/test_cases.md` を参照してください。

**この検証で確認できないこと**: Power Automate実機での関数の細かな挙動差、コネクタ応答、保存時検証、実行時エラー。これらは「要実環境確認」として `tests/validation_report.md` に列挙しています。

---

関連: [json_schema.md](json_schema.md) / [connector_requirements.md](connector_requirements.md) / [troubleshooting.md](troubleshooting.md)
