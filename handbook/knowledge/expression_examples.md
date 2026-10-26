# 式サンプル集 (Expression Examples)

migrate_chat_spo案件で実際に使用した式を、汎用化・プレースホルダー化して掲載する。貼り付け可能な式は```で囲んだコードブロック、手順の説明は「擬似コード」と明記する。実在しない関数は使用していない。
関連ルール: [../rules/02_expression_and_type_safety.md](../rules/02_expression_and_type_safety.md) / チェックは[../checklists/expression_type_checklist.md](../checklists/expression_type_checklist.md)を使用。

## 1. 文字列のnull安全化
- 目的: null/未定義の可能性がある文字列を安全にtrimする。
- 入力型: string または null
- 出力型: string
- 式:
```
trim(coalesce(triggerBody()?['Field'], ''))
```
- 使用条件: 対象が文字列であることが前提。`coalesce(trim(x), '')`のようにtrimを先に評価する順序は、xがnullの場合にエラーとなり得るため禁止。
- 注意事項: 配列・オブジェクトには適用しない。

## 2. 配列のnull安全化
- 目的: null/未定義の可能性がある配列をApply to each等へ渡す前に配列として保証する。
- 入力型: array または null
- 出力型: array
- 式:
```
coalesce(body('取得アクション名')?['value'], json('[]'))
```
- 使用条件: Filter array/Selectの出力は元々配列を返すため、その出力に重ねて適用する必要はない。
- 注意事項: 空配列フォールバックに空文字列`''`を使う誤用をしないこと（型不一致）。

## 3. オブジェクトのnull安全化
- 目的: null/未定義の可能性があるオブジェクトのプロパティに安全にアクセスする。
- 入力型: object または null
- 出力型: object
- 式:
```
coalesce(item()?['targetObject'], json('{}'))
```
- 使用条件: プロパティアクセス自体も`?['prop']`の安全参照演算子を併用する。
- 注意事項: オブジェクトのフォールバックに`''`や`json('[]')`を使わない（型を揃える）。

## 4. 投稿者名のフォールバック
- 目的: 投稿者表示名が空の場合に既定文字列へ差し替える。
- 入力型: string または null
- 出力型: string
- 式:
```
if(
  empty(trim(coalesce(items('Process_Each_Parent_Message')?['from']?['user']?['displayName'], ''))),
  '不明',
  trim(coalesce(items('Process_Each_Parent_Message')?['from']?['user']?['displayName'], ''))
)
```
- 使用条件: Apply to eachのループ内でのみ`items('ループ名')`が有効。
- 注意事項: 主催者情報として無条件に流用しない（投稿者と主催者は別概念。主催者は既定値「不明」とし、会議情報から取得できる場合のみ差し替える）。

## 5. 日付の存在確認
- 目的: 日付関数（formatDateTime等）に渡す前に、対象フィールドが存在するか確認する。
- 入力型: string（日時） または null/空文字列
- 出力型: boolean
- 式:
```
not(empty(coalesce(item()?['createdDateTime'], '')))
```
- 使用条件: この式がtrueの場合のみ後続でformatDateTime/convertFromUtcを適用する（Condition分岐と併用）。
- 注意事項: 空文字列を直接日付関数に渡すとエラーになるため、必ず存在確認を先に行う。

## 6. JST変換
- 目的: UTC日時をJST（日本標準時）表示用に変換する。
- 入力型: string（UTC日時）
- 出力型: string（JST日時）
- 式:
```
convertFromUtc(item()?['createdDateTime'], 'Tokyo Standard Time')
```
- 使用条件: 入力が有効なUTC日時文字列であること（事前に「5. 日付の存在確認」を通過していること）。
- 注意事項: 1項目内で複数の日時列を扱う場合、タイムゾーン基準（UTCのまま/JST変換後）を混在させない。同一項目内で基準を統一する。

## 7. 取得期間計算
- 目的: 終了日時から遡って取得対象の開始日時を求める。
- 入力型: string（終了日時UTC）, integer（日数）
- 出力型: string（開始日時UTC）
- 式:
```
addDays(variables('varEndDateUtc'), sub(0, variables('varLookbackDays')))
```
- 使用条件: varEndDateUtc・varLookbackDaysが初期化済みであること。
- 注意事項: 大きな日数（例:730日）を指定する場合、フロー実行時間の上限に注意（[power_automate_tips.md](power_automate_tips.md)参照）。

## 8. HTMLエスケープ
- 目的: プレーンテキストをHTML本文へ安全に埋め込む。
- 入力型: string
- 出力型: string
- 式（Composeを5段に分割する擬似コード）:
```
擬似コード:
Escape_Amp   = replace(元文字列, '&', '&amp;')
Escape_Lt    = replace(outputs('Escape_Amp'), '<', '&lt;')
Escape_Gt    = replace(outputs('Escape_Lt'), '>', '&gt;')
Escape_Quote = replace(outputs('Escape_Gt'), '"', '&quot;')
Escape_Apos  = replace(outputs('Escape_Quote'), "'", '&#39;')
```
- 使用条件: `&`を必ず最初に置換する（後から置換すると、他の置換で生成された`&`まで二重エスケープされる）。改行は`<br>`へ別途置換する。
- 注意事項: この5段はComposeアクションへの分割例（[power_automate_tips.md](power_automate_tips.md)「複雑な式をComposeへ分割する方法」参照）。

## 9. ファイル名サニタイズ
- 目的: ファイル名に使用できない文字を除去し安全なファイル名にする。
- 入力型: string または null
- 出力型: string
- 式（擬似コード。禁止文字を1つずつreplaceで置換）:
```
擬似コード:
名前 = coalesce(元ファイル名, '')
禁止文字 " * : < > ? / \ | をそれぞれ replace(名前, 該当文字, '_') で置換
末尾の空白・ピリオドを除去
長さが上限（例:100文字）を超える場合は拡張子を保持したまま短縮
名前が空の場合は既定名（例:'file'）を使用
```
- 使用条件: 拡張子は保持したまま本体部分のみを短縮する。
- 注意事項: 実際のreplace関数呼び出しは禁止文字の数だけ連鎖させる（実式は本ファイルでは擬似コード化）。

## 10. 添付なし判定
- 目的: 会議（またはメッセージ）に添付ファイルが1件も無いことを判定する。
- 入力型: array または null
- 出力型: boolean
- 式:
```
equals(length(coalesce(item()?['attachments'], json('[]'))), 0)
```
- 使用条件: attachmentsが配列であることを前提とする（事前に配列のnull安全化を適用）。
- 注意事項: 添付が無い場合の表示文言（例:「添付ファイルなし」）はCondition分岐で明示する。

## 11. 保存成功判定
- 目的: 添付ファイルの保存が成功したか（保存後URLが得られているか）を判定する。
- 入力型: string または null
- 出力型: boolean
- 式:
```
greater(length(coalesce(item()?['savedFileUrl'], '')), 0)
```
- 使用条件: status（Saved/Skipped/Failed）ではなく、savedFileUrlの有無で判定する（再利用時のSkippedも正しくリンク表示するため）。
- 注意事項: URLが無い場合はさらにstatusを見て「（保存失敗）」/「（テスト実行のため未保存）」を出し分ける。

## 12. LookbackDaysの既定値
- 目的: トリガー入力の日数指定がnull・未入力・0以下の場合に既定日数へフォールバックする。
- 入力型: integer または null
- 出力型: integer
- 式:
```
if(
  greater(int(coalesce(triggerBody()?['LookbackDays'], 0)), 0),
  int(coalesce(triggerBody()?['LookbackDays'], 7)),
  7
)
```
- 使用条件: 正の整数のみ採用。0以下・未入力は既定値7を採用。
- 注意事項: 上限（例:730日）のバリデーションはこの式自体には含めていない。運用手順書側で注意喚起する。

## 13. Boolean判定
- 目的: トリガー入力のBoolean値をfalseも正しく扱いつつ既定値で補完する。
- 入力型: boolean または null
- 出力型: boolean
- 式:
```
equals(coalesce(triggerBody()?['DryRun'], true), true)
```
- 使用条件: coalesceでnullのみを既定値に置き換え、false自体はfalseのまま評価する。
- 注意事項: `if(triggerBody()?['DryRun'], ...)`のような素通し判定はfalseを未設定と誤解釈しうるため使わない。

## 14. SortKey作成
- 目的: 会議一覧を時系列順にソートするためのキー文字列を作る。
- 入力型: string（日時）, string（ID）
- 出力型: string
- 式:
```
concat(
  formatDateTime(convertFromUtc(item()?['createdDateTime'], 'Tokyo Standard Time'), 'yyyyMMddHHmmss'),
  '_',
  item()?['id']
)
```
- 使用条件: `sort(コレクション, 'sortKey')`は昇順のみ。降順が必要な場合は`reverse()`を併用する。
- 注意事項: 日時部分を先頭に置くことで文字列比較がそのまま時系列比較になる。

## 15-A. Teams投稿URLの解析: クエリ値の取り出し（名前アンカー方式）
- 目的: URLのクエリから指定した名前の値を、**順番に依存せず**取り出す。
- 入力型: string（`?`より後ろのクエリ文字列）
- 出力型: string（見つからなければ空文字）
- 前処理: 前後に`&`を付けた正規化クエリを作る（トークン境界を確定させるため）。

```
concat('&', <クエリ文字列>, '&')
```

- 式（`{paramName}`を取り出したい名前に置換。`Q`は上記正規化クエリのCompose出力）:
```
if(
  contains(Q, '&{paramName}='),
  trim(decodeUriComponent(first(split(last(split(Q, '&{paramName}=')), '&')))),
  ''
)
```
- 使用条件: **先頭に`&`を付けたトークン（`'&名前='`）で分割するのが要点**。単に`'名前='`で探すと、
  別のパラメータ名の末尾に部分一致する（例: `messageId=`が`parentMessageId=`に一致してしまう）。
- 注意事項: パラメータが存在しない場合、`split`は元の文字列をそのまま1要素で返すが、正規化クエリが`&`で
  始まるため`first(split(..., '&'))`が空文字になる。`contains`の判定と合わせて安全に空文字を返す。

## 15-B. Teams投稿URLの解析: パスからの識別子取り出し
- 目的: `https://.../l/message/{channelId}/{messageId}?...` からチャネルIDとメッセージIDを取り出す。
- 入力型: string（URL）
- 出力型: string
- 式（Composeを段階的に分割する。各行が1アクション）:
```
Url_Without_Fragment = first(split(<入力URL>, '#'))
Url_Path_Raw         = first(split(outputs('Url_Without_Fragment'), '?'))
Url_Path_Part        = if(endsWith(P, '/'), join(take(split(P, '/'), sub(length(split(P, '/')), 1)), '/'), P)
                       ※ P = outputs('Url_Path_Raw')
Message_Path_Tail    = if(contains(outputs('Url_Path_Part'), '/l/message/'),
                          last(split(outputs('Url_Path_Part'), '/l/message/')), '')
ChannelId            = trim(decodeUriComponent(first(split(outputs('Message_Path_Tail'), '/'))))
MessageId            = if(contains(outputs('Message_Path_Tail'), '/'),
                          trim(decodeUriComponent(last(split(outputs('Message_Path_Tail'), '/')))), '')
```
- 使用条件: 固定文字数・固定位置に依存しない。`decodeUriComponent()`は`%3A`→`:`、`%40`→`@`を復号し、
  非エンコードのURLでは無害に素通りする。Graphに渡すときは`uriComponent()`で再エンコードする。
- 注意事項:
  - `MessageId`は「`/`が含まれる場合のみ」取り出す。`/l/message/{channelId}`だけのURLで
    `last()`を無条件に使うとチャネルIDをメッセージIDと誤認する。
  - 末尾スラッシュ除去に`substring`を使わない（`if()`は両分岐を先行評価するため空文字で失敗しうる）。
    → [../rules/02_expression_and_type_safety.md](../rules/02_expression_and_type_safety.md)

## 15-C. Teams投稿URLの解析: 対象メッセージIDの決定
- 目的: 返信のURLを入力されても親投稿を対象にする。
- 入力型: string, string
- 出力型: string
- 式:
```
if(
  or(empty(variables('varParentMessageId')), equals(variables('varParentMessageId'), '0')),
  variables('varUrlMessageId'),
  variables('varParentMessageId')
)
```
- 使用条件: `parentMessageId`を優先し、無ければパス上の`messageId`を使う。
- 注意事項: **親投稿のリンクには`parentMessageId=0`が付く変種がある**。メッセージIDは13桁の
  エポックミリ秒であり`'0'`は実在しないため、`'0'`は「値なし」と同等に扱う（渡すと必ず404）。

## 15-D. 失敗しても読めるHTTPステータスの退避
- 目的: コネクタ呼び出しが失敗した場合でも、後段のエラーハンドラからHTTPステータスを参照できるようにする。
- 入力型: コネクタアクションの出力（封筒）
- 出力型: string
- 式（SetVariableの値。`runAfter`を`[Succeeded, Failed]`にして必ず実行させる）:
```
string(coalesce(outputs('<コネクタアクション名>')?['statusCode'], 0))
```
- 使用条件: 失敗ハンドラは**変数だけ**を参照する（Scope内アクションの`outputs()`を参照すると、
  そのアクションが未実行のときハンドラ自体が壊れる）。この式で変数へ退避しておけば安全に読める。
  → [../rules/08_error_handling_and_idempotency.md](../rules/08_error_handling_and_idempotency.md)
- 注意事項: コネクタ出力の封筒キー（`statusCode`/`headers`/`body`）は`outputs()`で参照してよい。
  それ以外のフィールドは`body('X')?['field']`で参照する。
- 要実環境確認: 失敗したアクションで`statusCode`が実際に取得できるかは未確認。取得できない場合は
  `coalesce`により`'0'`となるため、既定のエラーコードへ落ちる設計にしておく。

## 16. OData `$filter` の値エスケープ（SharePoint REST）【実証済み】

- 目的: 実行時に決まる値（メッセージID・件名等）を `$filter` の文字列リテラルへ安全に埋め込む。
- 入力型: string / 出力型: string（URIの一部）
- 式（`{列名}` と `{値の式}` を置換して使う）:

```
@concat('_api/web/lists(guid''', variables('varListId'),
        ''')/items?$select=Id&$top=2&$filter={列名} eq ''',
        uriComponent(replace({値の式}, '''', '''''')), '''')
```

- **2段のエスケープが必要**。片方だけでは壊れる。
  1. `replace(x, '''', '''''')` … シングルクォートを2重化し、OData のリテラル境界を守る
  2. `uriComponent(...)` … `& < > # ? 空白 " 日本語 絵文字` をURLエンコードする
     （サーバ側で `%27%27` が `''` に復号され、エスケープ済みクォートとして解釈される）
- **`uriComponent()` は値の部分だけに適用する**。クォート区切り文字 `'` まで包むと壊れる。
- 使用条件: 対象列は `$filter` 可能な型であること。**`Note`（複数行テキスト）は `$filter` 不可**。
  重複判定キーは `Text`（1行テキスト）にする。
- 注意事項: 文字列連結だけでクエリを組み立てない。`$top=2` にしておくと
  「2件以上あるか」を1回の要求で判定できる（重複異常の検出）。
- 【事実】**実環境で実証済み**（2026-08-03 / sync-shared-mailbox-to-sharepoint-list）。
  100件の同期で20件が既存と正しくヒットして更新された。
  エスケープが壊れていれば全件が新規扱いになり重複登録されるため、
  **20件が更新された事実そのものが検索の正しさの証拠**になる。
- 【要実環境確認】値に `%` を含む場合の二重エンコード。オフラインテストでは通っているが実データ未確認。

## 15. 冪等キー作成
- 目的: 同一の添付ファイルを重複保存しないための一意キーを作る。
- 入力型: string, string, string
- 出力型: string
- 式:
```
concat(item()?['messageId'], '_', coalesce(item()?['replyId'], ''), '_', item()?['attachmentId'])
```
- 使用条件: 台帳（SharePointリスト）を`$filter`でこのキーを検索し、既存Saved項目があれば再処理をスキップする（ForceReprocess=falseの場合）。
- 注意事項: メッセージ本体の添付にはreplyIdが無いため空文字列を許容する。

## 17. 接頭辞を「先頭の1回だけ」取り除く（センチネル前置）
- 目的: 文字列 `s` の先頭にある接頭辞 `p` を、**先頭の1回だけ**取り除く。
- 入力型: string, string
- 出力型: string
- 式:
```
replace(concat('◇S◇', s), concat('◇S◇', p), '')
```
- 使用条件: `p` が `s` の接頭辞であること。センチネル `◇S◇` は入力に絶対に現れない文字列にする。
- 注意事項:
  - **素の `replace(s, p, '')` は使わない**。WDL の `replace` は**全置換**なので、
    接頭辞と同じ並びが後ろにもう一度出ると、そこまで消える
    （`s='田中田'`, `p='田'` → `'中'`。期待は `'中田'`）。
  - `substring(s, length(p))` は範囲外で実行時エラーになるうえ、
    第2引数が可変になるため「定数オフセットでのみ substring する」規約に反する。
  - `split` + `skip` でも書けるが、`skip` は本リポジトリの実働定義に出現実績が無い
    （検証スクリプトの関数許可リストで弾かれる）。上式は `replace`/`concat` だけで済む。
- 【事実】オフライン評価器（`tools/wdl_eval.py`）で確認済み。
- 【要実環境確認】実機での挙動（2026-08-04 時点で未インポート）。

## 18. `if()` の使わない側の分岐にも安全な値を渡す
- 目的: 分岐で実際には採用されない式が**実行時エラーを起こさない**ようにする。
- 式（悪い例 → 良い例）:
```
悪い: if(empty(sep), s, split(s, sep))          ... sep が空でも split が評価され落ちる
良い: if(equals(sep, '◇S◇'), s, split(s, sep))  ... 見つからない場合もセンチネルを入れておく
```
- 使用条件: 「見つからなかった」を表すのに**空文字を使わない**。
  区切り文字・接頭辞・キーなど、空文字だと関数が落ちる引数に使う値が対象。
- 注意事項: WDL の `if()` は**両方の分岐を先に評価する**（`handbook/rules/02` 参照）。
  「条件で守っているから安全」は成立しない。
  センチネルは入力に現れない文字列（例 `◇S◇`）にし、
  「見つからなかった」の判定はセンチネルとの一致で行う。
- 【事実】オフライン評価器で確認済み（sync-mail-to-list-with-examiner-detection）。
