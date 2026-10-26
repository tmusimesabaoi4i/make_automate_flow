# 式と型の安全性（@規則・trim/coalesce・型規律）

式（ワークフロー定義言語 / Workflow Definition Language）の書き方と型の扱いのルールです。今回のインポートエラーの直接原因である `@` の付け方、null/空文字/空配列の区別、日付・インデックス操作の安全策を扱います。変数更新の詳細は [03](./03_variables_arrays_and_objects.md) を参照。

## `@` の規則（今回のインポートエラーの原因）
- 【事実】`@` は式文字列の**先頭**、または `@{…}` 補間の**中**でのみ有効。
- 【事実】ネストした内側の関数に `@` を付けるとインポート時に式パースエラーになる。
  今回 `if(contains(@coalesce(...` のように内側 `coalesce` に `@` を付けてしまい、
  「the string character '@' at position '12' is not expected」で失敗した。
- 【推奨】正しい形。外側だけ `@` を付け、内側の関数には付けない。

  ```
  @if(contains(coalesce(triggerBody()?['X'], ''), 'foo'), 'A', 'B')
  ```

- 【推奨】式を文字列連結（スクリプト等）で生成する場合は、「補間用（`@`なし）」と
  「単独式用（`@`あり、先頭1個だけ）」を明確に分離し、生成後に不正な `@` が0件であることを機械走査する。

## `@{…}` の中身は式でなければならない【事実】
- 【事実】`@{…}` は**式の補間**として評価される。中身が関数呼び出しでないとインポート時に
  `Unable to parse template language expression 'xxx': expected token 'LeftParenthesis' and actual 'EndOfData'`
  で失敗する。**式ではない表示テキストでも評価される**（トリガー入力スキーマの
  `description`/`title`、アクションの固定文言も対象）。
- 【事実】**波かっこ単体（`{tenant}`）は安全**。危険なのは **`@` と `{` が隣接する場合だけ**。
  `https://{tenant}.sharepoint.com/...` を説明文に書いたパッケージはインポートに成功している
  （2026-07-24 / create_initialized_sharepoint_list）。
- 【事実・アンチパターン】メールアドレスの例をプレースホルダー付きで書くと、
  プレースホルダーの直前が必ず `@` になり `@{` が意図せず出来上がる。

  ```
  # 危険（インポートが失敗する）
  "description": "例: shared-mailbox@{tenant}.example.com"
  # 安全（例示は docs 側へ置き、説明文には形式だけを書く）
  "description": "監視対象の共有メールボックスの完全なメールアドレス"
  ```

- 【推奨】検査は「`@` の直後が `{` なら正当」で止めない。**`@{…}` の中身が `関数名(` で
  始まること**まで確認する。トリガー入力の `title`/`description` は `@` を1文字も許さない、
  という強い規則にすると単純で漏れが無い。
  → 実発生と再発防止策: [エラーカタログ](../knowledge/error_catalog.md)

## trim / coalesce の型規律
- 【事実/推奨】基本形は次のとおり。coalesce を**外側**、trim を内側に置く。

  ```
  trim(coalesce(<文字列またはnull>, ''))
  ```

- 【事実】`coalesce(trim(x), '')` は禁止。trim が先に評価され、x が null だと trim が失敗し得る。
- 【事実】`coalesce` の候補は**同一型**でそろえる。文字列は `''`、配列は `json('[]')`、オブジェクトは `json('{}')`。
  型の違う既定値（例: 文字列に `json('[]')`）を混ぜない。

## null・空文字・空配列は別物
- 【推奨】`null` ≠ `''`（空文字）≠ `[]`（空配列）として扱う。存在チェックには目的に合った既定値を与える。
- 【事実/推奨】Boolean の `false` / 数値の `0` を「未設定」と誤判定しない。
  - Boolean 判定は既定値付きで厳密に比較する。

    ```
    equals(coalesce(triggerBody()?['Flag'], false), true)
    ```

  - 数値入力の安全化（既定7、0以下は7に丸める例）。

    ```
    if(greater(int(coalesce(triggerBody()?['LookbackDays'], 0)), 0), int(coalesce(triggerBody()?['LookbackDays'], 7)), 7)
    ```

## 日付関数へ空文字を渡さない
- 【推奨】`formatDateTime` / `convertFromUtc` / `addDays` 等の日付関数へ空文字や null を渡すと実行時エラーになる。
  日付が必ず入る値（トリガー時刻・API応答の日時フィールド）を使い、無い場合は分岐で回避する。
- 【事実】今回は `formatDateTime(convertFromUtc(<...createdDateTime>, 'Tokyo Standard Time'), 'yyyy-MM-dd')`
  のように、必ず値が入る Graph 応答の日時を使っている。

## `if()` は両分岐の引数を先行評価する【事実・最重要】
- 【事実】Logic Apps / Power Automate の `if(条件, 真の値, 偽の値)` は、**条件の真偽に関わらず
  両方の引数を先に評価する**（短絡評価ではない）。したがって「条件で守っているから安全」は成り立たない。
- 【事実・アンチパターン】末尾1文字を削る次の式は、`P` が空文字のとき `sub(length(P),1)` が `-1` になり、
  `endsWith` が false でも `substring` が実行時エラーになり得る。

  ```
  # 危険
  if(endsWith(P, '/'), substring(P, 0, sub(length(P), 1)), P)
  ```

- 【推奨】長さ計算を伴う `substring` を分岐の中に置かない。分割・再結合で代替する。
  空文字でも `split('', '/')` → `['']` / `take(…, 0)` → `[]` / `join([], '/')` → `''` となり安全。

  ```
  # 安全
  if(endsWith(P, '/'), join(take(split(P, '/'), sub(length(split(P, '/')), 1)), '/'), P)
  ```

- 【推奨】同様に、分岐内の `int()` / 日付関数 / 角括弧インデックスも「通らない側」で失敗しない形にする。
  安全にできない場合は `if()` ではなく Condition（分岐アクション）で実行自体を分ける。

## `substring` は空文字に適用できない【事実・実発生】
- 【事実】`substring()` の開始位置は「0以上」だけでなく **文字列長より小さい**必要がある。
  したがって **長さ0の文字列には `substring('', 0, 0)` すら適用できない**。
  「開始位置0・長さ0なら何もしないから安全」という直感は成り立たない。
  実機のエラー文言（2026-08-04 実発生。teams-channel-member-sync）:

  ```
  The template language function 'substring' parameter is out of range:
  'start index' must be non-negative integer and should be less than the length of the string.
  ```

- 【推奨】切り出し位置が計算値になる `substring` は、**末尾に1文字の番兵を足してから**使う。
  `0 <= start <= length(S)` かつ `start + length <= length(S)` であれば、
  `concat(S, '#')` の長さが必ず1以上になり `start < 長さ` が常に成立する。
  番兵は `length` 引数で切り落とされるため結果には現れない。

  ```
  # 危険（S が空文字だと落ちる）
  substring(S, 0, <計算した位置>)

  # 安全（番兵付き）
  substring(concat(S, '#'), 0, <計算した位置>)
  ```

- 【推奨】「空にならないはず」という前提を置かない。上流の取得失敗・未入力・未設定で
  空文字は容易に発生し、正常系のテストでは表面化しない。
- 【事実】この誤りは `tools/wdl_eval.py` の `substring` を実機と同じ厳密さ（`start < length`）に
  そろえることで、空文字のテストケースが機械的に検出できる。
  緩い評価器のもとでは、空文字のテストがあっても合格してしまう。
  → [../knowledge/error_catalog.md](../knowledge/error_catalog.md)

## 計算インデックスの角括弧アクセスを避ける
- 【事実/推奨】`json('[...]')[<計算式>]` のような**計算インデックスの角括弧参照**は式エディタで不安定になり得る。
  関数形で代替する。曜日を出す例（`dayOfWeek` は 0=日曜）。

  ```
  substring('日月火水木金土', dayOfWeek(item()?['meetingDate']), 1)
  ```

- 【注意】上記は「今回この形で堅く動いた」ものを一般化した推奨であり、
  角括弧が常に壊れるという意味ではない。堅い関数形を優先する、という指針。

## 複雑な式は Compose（作成）で分割
- 【推奨】長い・入れ子が深い式は、途中結果を「作成（Compose）」に切り出して段階化する。
  デバッグ時に中間値を確認でき、`@` の付け間違いも減る。今回も有効日数の算出を Compose に分けた。

## Parse JSON（JSONの解析）の注意
- 【推奨】スキーマを作る前に**実レスポンスの形を先に確認する**（実行履歴のサンプルペイロードから
  「スキーマの生成」を使う）。HTTPやコネクタのラッパー（封筒）構造の有無を確認し、
  参照パスが `body/value` か `value` かを**推測で決めない**。
- 【事実・アンチパターン】実働サンプルには、実データがフラット（`{value:[...]}`）なのにスキーマが
  封筒形（`{statusCode, headers, body}`）という不一致があった。トップレベルに `required` が無く、
  `properties` は「キーが存在する場合のみ」検証されるため、入れ子の `required` が一度も評価されない
  「デッドスキーマ」となり偶然通過していた。スキーマと参照パスは必ず一致させる。
- 【推奨】null や欠落し得るプロパティを `required` へ過剰指定しない。スキーマは必要最小限にする。
  式参照だけで足りる場合は Parse JSON 自体を省略してよい（`body('X')?['value']` の直接参照で動作する）。

## 実在確認済みの関数のみ使う
- 【事実】本リポジトリの実働 definition.json に**使用実績のある**関数（＝安心して使える集合）:

  ```
  文字列  concat substring replace split trim length indexOf endsWith join string guid
  配列    first last take union createArray array sort reverse json
  論理    if not and or equals empty contains greater greaterOrEquals lessOrEquals coalesce
  数値    int sub
  日付    utcNow addDays formatDateTime convertFromUtc dayOfWeek
  URI     uriComponent decodeUriComponent uriPath decodeBase64
  参照    variables outputs body item items parameters triggerBody triggerOutputs
  ```

  `sort` は昇順のみ（降順は `reverse` 併用）。`union` は重複を排除する仕様
  （配列連結の副作用に注意）→ [03](./03_variables_arrays_and_objects.md)。
- 【推奨】実在しない関数・記憶頼りの関数名を書かない。迷ったら公式の関数リファレンスで確認する
  （learn.microsoft.com のワークフロー定義言語 関数リファレンス。参照日 2026-07-16）。
- 【推奨】**検証スクリプトに「関数許可リスト検査」を入れる**と機械的な歯止めになる。
  定義中の全 `関数名(` を抽出し、上記の実績集合に含まれることを確認する
  （teams_post_url_flows 案件の `validate_flow*.py` に実装例）。
- 【事実】`uriQuery()` / `uriComponentToString()` は公式には存在するが本リポジトリに使用実績が無い。
  クエリ解析は `split()`、URLデコードは実績のある `decodeUriComponent()` で代替できる。
  `uriPath()` はパス中の `%3A` を復号するか否かが未確認のため、復号タイミングが問題になる用途では使わない。

関連: [00 コアルール](./00_power_automate_core_rules.md) / [03 変数・配列](./03_variables_arrays_and_objects.md) / [06 Word/HTML生成](./06_word_html_document_generation.md) / [エラーカタログ](../knowledge/error_catalog.md)
