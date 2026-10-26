# エラーカタログ (Error Catalog)

## 索引（エラーコード/現象→節）

| コード/現象 | 発生局面 | 節 |
|---|---|---|
| WorkflowRunActionInputsInvalidProperty（SetVariable自己参照） | 保存時 | WorkflowRunActionInputsInvalidProperty（SetVariable自己参照。保存時）★最重要 |
| `'@' at position ... is not expected`（ネストした@） | インポート時 | インポート時の式パースエラー「'@' at position ... is not expected」（ネストした@） |
| `Unable to parse template language expression ...: expected token 'LeftParenthesis'`（表示テキスト中の `@{`） | インポート時 | 表示テキスト中の `@{...}` が式として解釈される（インポート時） |
| リスト列挙で 403 Access denied（`$expand` の投影欠落） | 実行時 | コレクション列挙の `$expand` に `$select` の投影が無く 403（実行時） |
| アクション名の全体重複 | インポート前（事前検出） | アクション名の全体重複（事前検出。インポート破損の原因になる） |
| コネクタ出力の body/ パス欠落 | 実行時（潜在バグ・監査で事前検出） | コネクタ出力の body/ パス欠落（潜在バグ。監査で事前検出） |
| OpenApiOperationParameterValidationFailed（PostItem item欠落） | 保存時 | OpenApiOperationParameterValidationFailed（PostItem item欠落。保存時） |
| GetFileContentByPath 404 File not found（クロスサイト参照） | 実行時 | GetFileContentByPath の 404 File not found（クロスサイト参照。実行時） |
| 台帳が全件Failed（CreateFile中間フォルダ非作成／GetFileItemライブラリ名前解決） | 実行時 | 添付保存の全件Failed（実行時。CreateFileの中間フォルダ非作成／GetFileItemのライブラリ名前解決） |
| `substring` parameter is out of range: 'start index' ...（空文字への substring） | 実行時 | `substring` が空文字で範囲外エラーになる（実行時） |

Power Automate開発で実際に発生したエラーの原因・修正方針・再発防止策を記録する。
ここに無いエラーは未確認として扱い、新規発生時は末尾「追記方法」の書式で追記する。

関連ルール: [../rules/03_variables_arrays_and_objects.md](../rules/03_variables_arrays_and_objects.md) / [../checklists/expression_type_checklist.md](../checklists/expression_type_checklist.md)

## WorkflowRunActionInputsInvalidProperty（SetVariable自己参照。保存時）★最重要

### 発生メッセージ
```
フローの保存がコード 'WorkflowRunActionInputsInvalidProperty' およびメッセージ
'The inputs of workflow run action 'Set_MessagesArray' of type 'SetVariable' are not valid.
Self reference is not supported when updating the value of variable 'varMessagesArray'.' で失敗しました。
```

### 発生条件
パッケージ（ZIP）のインポート自体は成功した後、Power Automate画面でフローを保存しようとした時に発生する。「インポート成功＝完成」ではなく、保存操作で初めて検出されるエラーがある点に注意。

### 原因
「変数を設定する」(Set variable / SetVariable) アクションの値式が、更新対象の変数自身を`variables('...')`で参照している（自己参照）。Power Automateはこの自己参照を許可しない。
- 配列蓄積: `union(variables('varX'), 新要素)` をvarX自身にSetVariable
- 文字列連結蓄積: `concat(variables('varX'), 追加文字列)` をvarX自身にSetVariable
- カウンター加算: `add(variables('varX'), 1)` をvarX自身にSetVariable

今回のフローでは自己参照が3件検出された。うち1件はアクション名が`Append_...`だったが、実体（type）はSetVariable+unionであり、**名前ではなくtypeで判定する必要がある**。

### 誤った実装例
```
アクション種類: SetVariable
名前: Set_MessagesArray
値: @union(variables('varMessagesArray'), body('Get_Channel_Messages')?['value'])
```
（varMessagesArrayを更新するのに、値式の中でvariables('varMessagesArray')自身を参照している）

### 修正方針
用途別に自己参照不要な専用アクションへ置き換える。
- (a) 配列蓄積 → Apply to each（配列の各要素をループ）＋「配列変数に追加」(Append to array variable)、値=`item()`。ページ単位の配列をまるごとAppendせず、1要素ずつ追加する。
- (b) 文字列連結蓄積 → 「文字列変数に追加」(Append to string variable)。
- (c) カウンター加算 → 「変数の値を増やす」(Increment variable)。

### 修正例
```
[Apply to each]
名前: Process_Retrieved_Messages
入力: @coalesce(body('Get_Channel_Messages')?['value'], json('[]'))
並列実行: オフ (concurrency.repetitions = 1)
  [中の子アクション]
  アクション種類: AppendToArrayVariable
  名前: Append_Message_To_MessagesArray
  対象変数: varMessagesArray
  値: @item()
```

### ZIP定義上の確認箇所
definition.json内の全アクションを走査し、`"type": "SetVariable"`のアクションについて`inputs.value`の式文字列に、`inputs.name`と同名の`variables('同名')`が含まれていないかを機械チェックする。

### Power Automate画面上の確認箇所
保存時のエラーダイアログのメッセージからアクション名（例:`Set_MessagesArray`）と変数名（例:`varMessagesArray`）を特定し、該当アクションを開いて「値」欄の式を確認する。

### 再発防止チェック
- [ ] 全SetVariableアクションの値式に、更新対象と同名の`variables('...')`参照が無いことを確認した
- [ ] アクション名だけで判断せず実際のtype（SetVariable/AppendToArrayVariable/AppendToStringVariable/IncrementVariable）を確認した
- [ ] 配列・文字列の蓄積は専用のAppend系アクションに置き換えた
- [ ] カウンターはIncrementVariable/DecrementVariableを使用した

### 初出案件
migrate_chat_spo（2026-07-16）

---

## インポート時の式パースエラー「'@' at position ... is not expected」（ネストした@）

### 発生メッセージ
```
電源フローのロジック アプリ フロー テンプレートが無効です。The template language expression
'if(contains(@coalesce(...' is not valid: the string character '@' at position '12' is not expected.
```

### 発生条件
パッケージ（ZIP）をPower Automate画面からインポートする時点（保存より前）で発生。

### 原因
式文字列をプログラム（Pythonなど）で文字列連結生成した際、外側の`@if(...)`の中にネストした関数（`coalesce(...)`等）の前にも誤って`@`を付けてしまった。`@`は式文字列の先頭、または文字列中の`@{...}`補間としてのみ有効であり、関数呼び出しの入れ子部分に単独で付けてはいけない。

### 誤った実装例
```
式（誤り）: @if(contains(@coalesce(triggerBody()?['X'], ''), 'abc'), 'yes', 'no')
```
（外側のifは正しく@始まりだが、内側のcoalesceの前にも@が付いており不正）

### 修正方針
式全体で`@`が使えるのは(1)式文字列の先頭、(2)文字列リテラル内の`@{式}`補間、の2箇所のみと徹底する。ネストした関数呼び出しには`@`を付けない。式を文字列連結で生成する場合は「埋め込み用（@なし）」と「単独式用（@あり）」のテンプレートを明確に分離する。

### 修正例
```
式（正しい）: @if(contains(coalesce(triggerBody()?['X'], ''), 'abc'), 'yes', 'no')
```

### ZIP定義上の確認箇所
definition.json全体をテキストとして走査し、`@`の出現位置が「式文字列の先頭」または「文字列中の`@{`」以外に無いことを機械チェックする。

### Power Automate画面上の確認箇所
インポート時のエラーダイアログに表示される式文字列とエラー位置（position）を確認し、該当アクションの式エディタで入れ子の`@`を除去する。

### 再発防止チェック
- [ ] 式を文字列連結で生成するスクリプトで「埋め込み用」と「単独式用」のテンプレートを分離した
- [ ] 定義全体に対して不正な位置の`@`が0件であることを機械走査で確認した
- [ ] インポート前に生成JSONをパースし、主要な式をサンプリング確認した

### 初出案件
migrate_chat_spo（2026-07-16）

---

## 表示テキスト中の `@{...}` が式として解釈される（インポート時）

### 発生メッセージ
```
電源フローのロジック アプリ フロー テンプレートが無効です。
Unable to parse template language expression 'tenant':
expected token 'LeftParenthesis' and actual 'EndOfData'.
```

### 発生条件
パッケージ（ZIP）をPower Automate画面からインポートする時点で発生する。
**式ではない表示テキスト**（トリガー入力スキーマの `description` / `title`、アクションの固定文言など）に
`@{...}` が含まれている場合。定義中に式が1つも間違っていなくても発生する。

### 原因
Power Automate は**文字列中の `@{...}` を式の補間として評価**する。
補間の中身は式（関数呼び出し）でなければならず、`@{tenant}` のような裸の識別子は
「`tenant` という関数を呼ぼうとしたが `(` が無い」と判定されてパースに失敗する。

踏みやすいのは**メールアドレスの例をプレースホルダー付きで書いた場合**。
プレースホルダーの直前が必ず `@` になるため、`@{` が意図せず出来上がる。

- 【事実】**波かっこ単体（`{tenant}`）は安全**。`https://{tenant}.sharepoint.com/...` を
  トリガー入力の説明文に書いたパッケージは実環境インポートに成功している
  （2026-07-24 / create_initialized_sharepoint_list）。
- 【事実】危険なのは **`@` と `{` が隣接する場合だけ**。

### 誤った実装例
```
"SharedMailboxAddress": {
  "title": "共有メールボックスのアドレス",
  "type": "string",
  "description": "例: shared-mailbox@{tenant}.example.com。メールは読み取るだけで変更しません"
}                              ~~~~~~~~~ ここが式として解釈される
```

### 修正方針
**表示テキストに `@` を書かない。** 具体例（メールアドレス等）はスキーマの説明文ではなく
docs 側に置き、説明文には形式の説明だけを書く。

`@` をどうしても表示したい場合は `@@` でエスケープできるが、説明文が読みにくくなるため
「書かない」方を推奨する。

### 修正例
```
"description": "監視対象の共有メールボックスの完全なメールアドレス。"
               "メールは読み取るだけで、既読化・移動・削除は行いません"
```

### ZIP定義上の確認箇所
definition.json 内の全文字列を走査し、`@{...}` の**中身**が関数呼び出しかを機械チェックする。
`@` の直後が `{` であることをもって「正当な補間」と無条件に許可する検査では**捕捉できない**
（本エラーはその穴から漏れた）。

```python
INTERP_RE = re.compile(r"@\{([^}]*)\}")
for path, s in 全文字列:
    for m in INTERP_RE.finditer(s):
        if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*\s*\(", m.group(1).strip()):
            fail("'@{...}' の中身が式（関数呼び出し）でない: %s: %r" % (path, s[:120]))
```

あわせて、トリガー入力スキーマの `title` / `description` に `@` が1文字でもあればエラーにする
（表示テキストに補間が必要な場面は無いため、こちらの方が強く単純）。

### Power Automate画面上の確認箇所
インポート時のエラーダイアログに表示される識別子（例 `'tenant'`）を、定義全文から検索する。
アクションの式ではなく**説明文・表示名**に見つかることがある点に注意する。

### 再発防止チェック
- [ ] `@{...}` の中身が関数呼び出しであることを機械走査で確認した（0件）
- [ ] トリガー入力スキーマの `title` / `description` に `@` が無いことを確認した
- [ ] 表示テキストにメールアドレスの例を書いていない（例示は docs 側に置いた）
- [ ] 同型パターンをリポジトリ内の全 definition.json に対して走査し0件を確認した
- [ ] 「式は全部正しい」ことと「インポートが通る」ことは別、と理解した

### 初出案件
sync-shared-mailbox-to-sharepoint-list（2026-08-03・実環境インポートで発生）

---

## アクション名の全体重複（事前検出。インポート破損の原因になる）

### 発生メッセージ
（実行時のエラーメッセージは未確認。事前の機械走査で検出し実インポート前に修正済み。Power Automateはフロー全体でアクション名の一意性を要求するため、重複が残った場合はインポート破損やインポートエラーの原因になり得る。）

### 発生条件
同一フロー内で同じアクション表示名を2箇所以上に配置した場合。今回は「ループ外の初期化用」アクションと「ループ内の更新用」アクションに同一名（例:`Set_ReplyNextLink`）を付けてしまっていた。

### 原因
同じ役割の説明（「次ページURLを設定する」）から初期化アクションと更新アクションに同じ名前を付けてしまった。Power Automateはフロー全体（Scope/ループをまたいで）でアクション名が一意であることを要求する。

### 誤った実装例
```
[ループ外] アクション名: Set_ReplyNextLink （初回のURLを設定）
[ループ内] アクション名: Set_ReplyNextLink （毎回URLを更新）
```
（同一フロー内に同名アクションが2箇所存在）

### 修正方針
「初期化用」と「ループ内更新用」で名前を分ける。サフィックス`_First`を初期化用に付ける命名規則を統一する。

### 修正例
```
[ループ外] アクション名: Set_ReplyNextLink_First （初回のURLを設定）
[ループ内] アクション名: Set_ReplyNextLink （毎回URLを更新）
```
（同型パターン: Set_NextLink_First / Set_NextLink も同様の命名）

### ZIP定義上の確認箇所
definition.json全体からアクション名（キー）を再帰的に全て収集し、重複が0件であることを機械チェックする。Scope/Foreach/If/Doの子・else子・catchも含めて再帰的に走査する。

### Power Automate画面上の確認箇所
インポートが失敗する、またはフローが壊れた状態で開かれる場合、デザイナー上で同名アクションが複数箇所に表示されていないか確認する。

### 再発防止チェック
- [ ] 全アクション名の重複チェックを機械走査で実施し0件を確認した
- [ ] 「初期化用」と「ループ内更新用」で命名規則（`_First`等）を分けた
- [ ] インポート前の検証スクリプトに重複名検査を含めた

### 初出案件
migrate_chat_spo（2026-07-16）

---

## コネクタ出力の body/ パス欠落（潜在バグ。監査で事前検出）

### 発生メッセージ
```
（保存・インポートではエラーにならない。実行時に値が null になり、後続アクションの失敗や
 「保存失敗」扱いなどの誤動作として現れる。今回は実発生前に設計監査で検出・修正した）
```

### 発生条件
コネクタ（type=OpenApiConnection）アクションの出力フィールドを `outputs('X')?['フィールド名']` で参照した場合。DryRun等でその経路を通らないテストでは発火せず、本番経路で初めて誤動作する。

### 原因
コネクタアクションの `outputs('X')` は封筒構造 `{statusCode, headers, body}` を返す。フィールドは `body` の中にあるため、`outputs('X')?['ItemId']` のような直下参照は**常に null**。
Compose の `outputs('Compose_X')` は封筒を持たないため混同しやすい。

### 誤った実装例
```
@outputs('Create_Attachment_File')?['ItemId']
@outputs('Get_Saved_File_Properties')?['{Link}']
```

### 修正方針
コネクタ出力のフィールドは `body('X')?['フィールド名']`（または `outputs('X')?['body/フィールド名']`）で参照する。

### 修正例
```
@body('Create_Attachment_File')?['ItemId']
@body('Get_Saved_File_Properties')?['{Link}']
```

### ZIP定義上の確認箇所
definition.json内の `outputs('アクション名')?['キー']` をすべて抽出し、参照先アクションが OpenApiConnection の場合にキーが `body` 系（`body` / `body/...`）でなければ誤り、と機械チェックする。同一定義内に `body('X')?['value']` の正しい参照が混在している場合は書き分けの取りこぼしを疑う。

### Power Automate画面上の確認箇所
実行履歴で該当アクションの「出力」を開き、フィールドが `body` の下にネストしていることを確認する。式の評価結果が null になっていないかを後続アクションの「入力」で確認する。

### 再発防止チェック
- [ ] コネクタ出力のフィールド参照がすべて `body('X')?[...]` 形式であることを機械走査した
- [ ] DryRun/テスト経路だけでなく、本番経路（実際に保存・取得する分岐）を最低1件は実走して値を確認した
- [ ] Compose の outputs とコネクタの outputs を混同していない

### 初出案件
migrate_chat_spo（2026-07-16。実働サンプルとの突合監査で実発生前に検出）

---

## OpenApiOperationParameterValidationFailed（PostItem item欠落。保存時）

### 発生メッセージ
```
フローの保存がコード 'OpenApiOperationParameterValidationFailed' およびメッセージ
'Input parameter 'item' validation failed in workflow operation 'Create_Run_Log':
The API operation 'PostItem' is missing required property 'item'.' で失敗しました。
```

### 発生条件
パッケージ（ZIP）のインポート自体は成功した後、Power Automate画面でフローを保存しようとした時に発生する。
保存時のエラーダイアログは**1件ずつ**しか報告しないため、今回は同型の`PostItem`アクションが
`Create_Ledger_Item` / `Create_Ledger_Item_Failed` / `Create_Run_Log` / `Create_Error_Log` の
計4箇所に存在し、1件直して保存し直すたびに次の1件が新たに報告される「もぐら叩き」状態になった。

### 原因
SharePoint「項目の作成」(Create item / operationId=`PostItem`) の本文パラメータ`item`は
`x-ms-dynamic-schema`による動的スキーマで、列単位のフラット化キー（`item/Title`等）は
デザイナーで`dataset`（サイトのアドレス）/`table`（リスト名）を**静的に選択した場合のみ**
解決・生成される。`dataset`/`table`が式（`@variables(...)`等）だと列スキーマを解決できず、
フラット化キーを`item`に束ねられないため、保存時検証で「`item`が欠落している」と判定される。
実働サンプルの`PostItem`はサイト・リストとも静的リテラルの場合にのみ保存実績があった。

### 誤った実装例
```
アクション種類: OpenApiConnection (operationId=PostItem)
名前: Create_Run_Log
dataset: @variables('varSiteUrl')
table: @variables('varRunLogList')
item/Title: @variables('varRunTitle')
item/Result: @variables('varRunResult')
```
（サイト・リストとも式のため列スキーマが解決できず、保存時に`item`欠落エラー）

### 修正方針
`PostItem`を「SharePoint に HTTP 要求を送信」(Send an HTTP request to SharePoint /
operationId=`HttpRequest`) ＋ REST に置き換える。同型のPostItemが複数ある場合は
1件だけ直して満足せず、definition.json全体から`"operationId": "PostItem"`を機械検索し
**残り全件**を洗い出してから修正・保存する。
- 前段にCompose（例:`Compose_Run_Log_Body`）でボディオブジェクトを組み立てる。
- HTTP要求の`parameters/body`には`@string(outputs('Compose_Run_Log_Body'))`を渡す（数値・日時列の型を保持するため文字列化してから送信）。
- `Method`=POST、`Uri`=`_api/web/lists/getbytitle('{listName}')/items`（リスト名部分は式可）。
- `Headers`は`Accept`/`Content-Type`とも`application/json;odata=nometadata`にすれば`__metadata`は不要。
- `dataset`（サイトのアドレス）は静的リテラルで指定する（式にすると同種の問題が再発し得るため）。

### 修正例
```
[Compose]
名前: Compose_Run_Log_Body
入力: {"Title": "@{variables('varRunTitle')}", "Result": "@{variables('varRunResult')}"}

[SharePointにHTTP要求を送信]
名前: Create_Run_Log
Site Address (dataset): {siteUrl}  ※静的リテラル
Method: POST
Uri: _api/web/lists/getbytitle('{listName}')/items
Headers: {"Accept": "application/json;odata=nometadata", "Content-Type": "application/json;odata=nometadata"}
Body: @string(outputs('Compose_Run_Log_Body'))
```

### ZIP定義上の確認箇所
definition.json内で`"operationId": "PostItem"`の存在を機械検査する。`PostItem`が1件でも
残っていれば、`dataset`/`table`が式（`variables(...)`等の式文字列）と併用されていないかを
併せて確認する。式との併用がある場合は保存不可と判定してよい。

### Power Automate画面上の確認箇所
保存時のエラーダイアログのメッセージからアクション名（例:`Create_Run_Log`）を特定し、
該当アクションを開いて「サイトのアドレス」「リスト名」がドロップダウンの静的選択か、
動的コンテンツ（式）になっているかを確認する。

### 再発防止チェック
- [ ] definition.json全体を機械検索し、`"operationId": "PostItem"`が0件、または`dataset`/`table`が
      すべて静的リテラルであることを確認した
- [ ] 保存エラーが1件解消しても即座に完了とせず、同型パターンの残数を機械検索で確認してから再保存した
- [ ] サイト/リストを式にする必要があるアクションはHttpRequest+RESTへ置換した
- [ ] REST置換後のHeadersに`Accept`/`Content-Type`とも`application/json;odata=nometadata`を設定した
- [ ] ハイパーリンク列を使う場合は1行テキスト列への変更を検討した（RESTは`{"Url":...}`形式を要求するため）

### 補足（実行時の残注意）
- 【要実環境確認】テナント設定によりPOSTで`__metadata`（`ListItemEntityTypeFullName`）の型指定を要求される場合がある。
  その場合はリストの`ListItemEntityTypeFullName`を取得しボディに追加する回避策を検討する。
- 【事実】必須の動的ボディを持たない操作は`dataset`が**式でも保存検証を通る**。
  特に「SharePoint に HTTP 要求を送信」(`HttpRequest`) は、`dataset`に`@variables('varSiteUrl')`のような式を
  指定した状態で**保存・実行できることを実環境で確認済み**
  （2026-07-24 / create_initialized_sharepoint_list。16アクション全てが式指定）。
  従来は演繹による判断だったが実証された。→ [sharepoint_rest_list_provisioning.md](sharepoint_rest_list_provisioning.md) §11
- 【推奨】したがって「サイトを実行時に決める」フローは`PostItem`ではなく`HttpRequest`＋RESTで組む。

### 参照（2026-07-16時点で実在確認）
- https://tomriha.com/http-request-to-create-sp-item-in-dynamic-list-site-with-power-automate/
  （リストを静的選択しない場合は汎用`Item`フィールドのみになる旨の解説）
- https://community.powerplatform.com/ （フォーラム。動的なサイト/リストはCreate itemではなくHTTP requestを推奨する複数スレッドあり）
- https://learn.microsoft.com/en-us/sharepoint/dev/business-apps/power-automate/guidance/working-with-send-sp-http-request
  （`odata=nometadata`ヘッダー、`body('...')['value']`でのアクセス方法を公式解説）
- https://vrdmn.com/2017/04/ （`odata=nometadata`で`__metadata`省略が可能という2017年の実証記事）
- https://techcommunity.microsoft.com/ （PnPブログ等。HttpRequestアクションの構成例）

### 初出案件
migrate_chat_spo（2026-07-16）

---

## GetFileContentByPath の 404 File not found（クロスサイト参照。実行時）

### 発生メッセージ
```
{"status": 404, "message": "File not found\r\nclientRequestId: {guid}"}
```

### 発生条件
パッケージのインポート・保存はいずれも成功した後、**フロー実行時**にSharePoint
「パスによるファイル コンテンツの取得」(Get file content using path /
operationId=`GetFileContentByPath`) アクションで発生する。Teamsチャネルメッセージの
添付（`contentType`=`reference`）の`contentUrl`から`uriPath`でパスを取り出し、
**保存先サイト（添付があるチームサイトとは別サイト）**を`dataset`に指定して取得しようと
していた。

### 原因
実データで以下が確定した。
- (a) Teamsチャネルの添付ファイルは**投稿のあるチームのSharePointサイト**の既定ライブラリ
  （`Shared Documents`/共有ドキュメント）配下に保存される。保存先として別途用意したサイトと
  同一とは限らない。
- (b) Graphが返す`contentUrl`は**生URL（非エンコード）**。日本語ファイル名もそのまま含まれる。
- (c) `GetFileContentByPath`の`path`は**datasetサイトからのサイト相対パス**（サイト接頭辞を
  含まない）。

`dataset`に保存先サイトを指定したまま`contentUrl`の`uriPath`（チームサイト側の絶対パス）を
そのまま`path`に渡したため、`dataset`と`path`が指すサイトが食い違い404になった。

### 誤った実装例
```
[GetFileContentByPath]
dataset: {destinationSiteUrl}  ※保存先サイト。添付があるチームサイトとは別サイト
path: @uriPath(items('Apply_to_each_Attachment')?['contentUrl'])
```
（`contentUrl`のサイトと`dataset`に指定したサイトが異なるため404）

### 修正方針
`contentUrl`を`/Shared Documents/`（共有ドキュメント。既定ライブラリ）の位置で分割し、
前半を`dataset`、後半を`path`に使う。Composeで導出するため設定不要・汎用。
- `Compose_Source_Site` = `@substring(cu, 0, indexOf(cu, '/Shared Documents/'))`
- `Compose_Source_Path` = `@replace(substring(cu, indexOf(cu, '/Shared Documents/')), '%20', ' ')`

予防として、Filter arrayで`contains(contentUrl, '/Shared Documents/')`を条件に加え、
ライブラリ実在ファイルのみを取得対象にする（外部リンク・タブ参照由来の404を事前排除）。
添付有無の明示分岐（If: `length(Filter結果)` > 0）も有効。

### 修正例
```
[Compose] Compose_Source_Site
入力: @substring(items('Apply_to_each_Attachment')?['contentUrl'], 0,
      indexOf(items('Apply_to_each_Attachment')?['contentUrl'], '/Shared Documents/'))

[Compose] Compose_Source_Path
入力: @replace(substring(items('Apply_to_each_Attachment')?['contentUrl'],
      indexOf(items('Apply_to_each_Attachment')?['contentUrl'], '/Shared Documents/')), '%20', ' ')

[GetFileContentByPath]
dataset: @outputs('Compose_Source_Site')
path: @outputs('Compose_Source_Path')
```

### ZIP定義上の確認箇所
`GetFileContentByPath`の`dataset`が`contentUrl`のサイトと一致するかは、definition.json
だけを見る静的検証では判定不能（`contentUrl`は実行時にしか得られない実データのため）。
**実行時検証が必須**と判定してよい。静的走査では`GetFileContentByPath`アクション自体の
存在と、直前にサイト/パスをComposeで分割導出しているかの有無のみ確認できる。

### Power Automate画面上の確認箇所
実行履歴で404になったアクションの「入力」（`dataset`/`path`）と、直前のTeams取得アクション
の`contentUrl`実値を突き合わせ、サイト部分が一致しているかを確認する。

### 再発防止チェック
- [ ] Teams添付のファイル取得は`contentUrl`を`/Shared Documents/`で分割して`dataset`/`path`を導出しているか確認した
- [ ] Filter arrayで`contains(contentUrl, '/Shared Documents/')`により実在ライブラリのファイルのみを対象にした
- [ ] 添付の有無をIfで明示的に分岐した（`length(Filter結果)` > 0）
- [ ] 小規模データで本番経路（DryRun=いいえ）を1件実走し、実データで確認した
- [ ] インポート・保存の成功だけでなく、実行時のクロスサイト参照エラーの有無を確認した

### 初出案件
migrate_chat_spo（2026-07-17・実環境実行で発生）

---

## 添付保存の全件Failed（実行時。CreateFileの中間フォルダ非作成／GetFileItemのライブラリ名前解決）

### 発生メッセージ
```
（エラーダイアログとしては現れない。フローは完走し、台帳リスト（例: MeetingArchiveLedger相当）に
以下のような行が対象添付すべてで Status=Failed として記録される――「データとして現れる」型のエラー）

| Title（元ファイル名）      | Status | ErrorMessage                                              |
|---------------------------|--------|-------------------------------------------------------------|
| {originalFileName}         | Failed | 元URL={sourceContentUrl} / 保存先={folderPath}/{savedName} |
```

### 発生条件
本番経路（DryRun=いいえ）の実行で、複数メッセージ・複数添付にわたり**全件**が Status=Failed になる。
フロー自体は正常終了し、封じ込め（Scope失敗のハンドラ吸収・台帳へのFailed記録）は正しく機能している。
実行証跡で個々の`contentUrl`は正しい形（既定ライブラリ配下・生URL）と確認できるにもかかわらず、
保存側のアクションが全滅する点が特徴。

### 原因
独立した2つの原因が重なりうる。
1. SharePoint「ファイルの作成」(Create file / CreateFile) は**中間フォルダを自動作成しない**。
   保存先フォルダ階層（`{siteUrl}/{library}/{folderPath}`の各階層）が事前に存在しないと作成に失敗する。
2. `GetFileItem`等の`table`パラメータは**ライブラリの表示名またはGUID**を要求する。`"Shared Documents"`
   はURLの構成セグメントにすぎず、日本語サイトの既定ライブラリ表示名（例:「ドキュメント」）とは別物
   のため名前解決に失敗する。この失敗は保存時の静的検証では検出されず、**実行時**に初めて（多くの
   場合は対象アクション全件の）Failedとして現れる。

### 誤った実装例
```
[CreateFile]
folderPath: {library}/{folderPath1}/{folderPath2}/{folderPath3}  ※中間階層が未作成
（中間フォルダが存在しないため作成失敗）

[GetFileItem]
table: "Shared Documents"  ※URLセグメントをそのままtableに指定
（日本語既定ライブラリの表示名と一致せず名前解決失敗）
```

### 修正方針
名前解決に依存しない設計にする。
- (a) 保存先フォルダをフロー内で事前確保する。REST `POST _api/web/folders`（`SP.Folder`・
  `odata=verbose`・`ServerRelativeUrl`=**フルサーバー相対**）を1階層ずつ、`runAfter=[Succeeded,Failed]`
  で継続実行し、最後に`GET GetFolderByServerRelativeUrl`で実在検証する。
- (b) 保存後のファイルURLは`GetFileItem`等の応答を待たず、既知の値（サイト＋ライブラリ＋パス＋
  ファイル名）から**決定的に構築**する。`CreateFile`の成功自体がそのパス・名前でファイルが存在する
  ことの直接証拠になるため、名前解決を要するアクションを使わずに済む。

### 修正例
```
[Ensure_Folder_L1]（L2〜L4も同型）
Method: POST
Uri: _api/web/folders
Headers: {"Accept":"application/json;odata=verbose","Content-Type":"application/json;odata=verbose"}
Body: {"__metadata":{"type":"SP.Folder"},"ServerRelativeUrl":"{sitePath}/{library}/{segment1}"}
runAfter: 前段のフォルダ作成アクションに対して [Succeeded, Failed]

[Verify_Destination_Folder]
Method: GET
Uri: _api/web/GetFolderByServerRelativeUrl('{sitePath}/{library}/{folderPath}')

[Compose_Saved_File_Url]
入力: @replace(concat('{siteUrl}','/','{library}','/','{folderPath}','/',variables('varSavedName')), ' ', '%20')
```

### ZIP定義上の確認箇所
definition.json内で`CreateFile`アクションの直前にフォルダ存在確認/確保のRESTアクション列があるか、
`GetFileItem`の`table`に`"Shared Documents"`等のURLセグメントがリテラル指定されていないかを機械
チェックする。保存後URLを`GetFileItem`の応答（`{Link}`等）から取得している箇所が残っていないかも
併せて確認する。

### Power Automate画面上の確認箇所
台帳リストを開き`Status`列を`Failed`でフィルタし、`ErrorMessage`列を確認する。フォルダ確保アクション
の実行履歴で最終`GET GetFolderByServerRelativeUrl`が成功しているか、`CreateFile`がどのエラーコード
（404/409等）で失敗しているかを確認する。

### 再発防止チェック
- [ ] 本番経路（DryRun=いいえ）を最低1件、実データで実走してから完成とみなした
- [ ] `table`/`dataset`など名前解決に依存するアクションを棚卸しし、決定的URL構築で代替できないか検討した
- [ ] 保存先フォルダ階層をフロー内RESTで事前確保する、または手順書で手動作成を明記した
- [ ] 再実行時に同名ファイルが既に保存先に存在していないか（409衝突・残骸）を確認した

### 初出案件
migrate_chat_spo（2026-07-17実行/2026-07-18対処）

---

## コレクション列挙の `$expand` に `$select` の投影が無く 403（実行時）

### 発生メッセージ
```
（フローは完走し、結果JSONにエラーとして現れる型）
"error": {"code": "ERR_PERMISSION_DENIED", "stage": "CheckList",
          "details": ["stage=CheckList", "httpStatusCode=403", ...]}
```
`_api/web?$select=Id,Title,Url`（サイト疎通）は **200 で成功**しているのに、
直後の `_api/web/lists?` のクエリだけが 403 になるのが特徴。

### 発生条件
インポート・保存は成功し、**実行時**に発生する。
`_api/web/lists` のような**コレクション**に対して `$expand=RootFolder` を指定し、
`$select` に `RootFolder/<プロパティ>` の**投影を書かなかった**場合。

### 原因
投影を省くと SharePoint はナビゲーション先（`RootFolder`）の**全プロパティを実体化**しようとする。
`_api/web/lists` は非表示リストやカタログ等のシステムリストも返すため、
実行ユーザーがアクセスできないリストに当たった時点で Access denied（403）になる。
サイト自体への読み取り権限はあるので `_api/web` は通る、という食い違いが起きる。

- 【事実】**単一リソース**（`lists(guid'{listId}')` / `GetByTitle('{name}')`）への `$expand` は
  投影が無くても動く。実環境で成功した3実装がいずれも `?$select=Id,Title&$expand=RootFolder`。
  **危険なのはコレクション列挙のときだけ。**

### 誤った実装例
```text wdl-lint:ignore
_api/web/lists?$select=Id,Title,Hidden,BaseTemplate&$expand=RootFolder&$top=5000
```

### 修正方針
`$expand` したナビゲーションプロパティは、`$select` にも**投影を必ず書く**。
実証済みの形（[sharepoint_rest_list_provisioning.md §12](sharepoint_rest_list_provisioning.md)）を
逐語コピーし、クエリを短くしない。

### 修正例
```
_api/web/lists?$select=Id,Title,Hidden,BaseTemplate,RootFolder/ServerRelativeUrl&$expand=RootFolder&$top=5000
```

### ZIP定義上の確認箇所
`tools/wdl_lint.py` の **L04** が機械検査する。
「パスがコレクション（`/lists` `/fields` `/views` `/items` 等）で終わる URI に `$expand=X` があるのに、
`$select` へ `X/` が現れない」を検出する。Markdown 側は同ツールの **M02** が検査する。

### Power Automate画面上の確認箇所
実行履歴で 403 になったアクションの「入力」の `parameters/uri` を開き、
`$expand` と `$select` を突き合わせる。
403 の切り分けとして、直前の `_api/web` が 200 かどうかを必ず見る
（200 なら「サイトへの権限」ではなく「クエリの形」を疑う）。

### 再発防止チェック
- [ ] `tools/wdl_lint.py` を実行し L04 / M02 が0件であることを確認した
- [ ] REST URI を**実証済みの `definition.json` から逐語コピー**した（handbook の要約から書き起こしていない）
- [ ] ドキュメントに載せた REST 断片も同じ規則で検査した（文書の誤りは次の実装にコピーされる）
- [ ] 403 を見たら、直前の `_api/web` の成否でクエリ起因か権限起因かを切り分けた

### 初出案件
sync-shared-mailbox-to-sharepoint-list（2026-08-03・実環境実行で発生）
【事実】`$select` に `RootFolder/ServerRelativeUrl` を足した修正版で**実環境の再実行に成功**した
（2026-08-03）。403 の原因がクエリの形であり、権限ではなかったことが実証された。

---

## `substring` が空文字で範囲外エラーになる（実行時）

### 発生メッセージ
```
Unable to process template language expressions in action 'Compose_Admin_Cut' inputs at line '0'
and column '0': 'The template language function 'substring' parameter is out of range:
'start index' must be non-negative integer and should be less than the length of the string.
Please see https://aka.ms/logicexpressions#substring for usage details.'.
```

### 発生条件
インポートも保存も成功し、**実行時**に初めて失敗する。入力が空文字になる経路
（未入力・未設定・上流の取得失敗）を通ったときだけ落ちるため、正常系のテストでは表面化しない。

### 原因
`substring()` の開始位置は「0以上」だけでなく **文字列長より小さい** ことを要求される。
したがって長さ0の文字列には `substring('', 0, 0)` すら適用できない。
「開始位置0・長さ0なら何もしないから安全」という直感が成り立たない。

- 【事実】`start` は `0 <= start < length(s)` を満たす必要がある（上記メッセージの文言）。
- 【事実】`length(s) == 0` のとき、`start` に何を渡しても条件を満たせない。
- 【誤解しやすい点】`if()` は両分岐を先行評価するため、「空なら通らない分岐」に置いても守れない。
  さらに、そもそも `substring(S, 0, 0)` 自体が単体で失敗する。

### 誤った実装例
```
# S が空文字だと落ちる（cutIdx は length(S) = 0 になる）
@substring(outputs('Compose_Url_NoQuery'), 0, outputs('Compose_Url_CutIndex'))
```

### 修正方針
**番兵（sentinel）を1文字足してから切り出す。** 「空にならないはず」という前提を置かず、
定義の形として空文字でも成立させる。

`0 <= start <= length(S)` かつ `start + length <= length(S)` であれば、
`concat(S, '#')` の長さは必ず 1 以上になり、`start < 長さ` が常に成立する。
番兵は `length` 引数で切り落とされるため結果には現れない。

### 修正例
```
@substring(concat(outputs('Compose_Url_NoQuery'), '#'), 0, outputs('Compose_Url_CutIndex'))
```

末尾1文字を削る用途には、そもそも `substring` を使わず `split` → `take` → `join` にする
（空文字でも `split('', '/')` → `['']` / `take(…, 0)` → `[]` / `join([], '/')` → `''` で安全）。
→ [../rules/02_expression_and_type_safety.md](../rules/02_expression_and_type_safety.md)

### ZIP定義上の確認箇所
`definition.json` を `substring(` で検索し、第1引数が **空文字になりうるか**を1件ずつ確認する。
番兵を付ける規約にしておくと「`substring(concat(` 以外は禁止」という機械検査で閉じられる
（実装例: `projects/teams-channel-member-sync/shared/flow_checks.py` の P16）。

### Power Automate画面上の確認箇所
実行履歴で失敗したアクション（Compose であることが多い）の「入力」を開く。
上流の Compose の出力が空文字になっていないかを遡る。

### 再発防止チェック
- [ ] `substring` の第1引数が空文字になりうる経路を洗い出した
- [ ] 空文字でも成立する形（番兵付き、または `split`/`take`/`join`）に書き換えた
- [ ] **入力が空のテストケース**を用意し、生成済み `definition.json` の式を `tools/wdl_eval.py` で評価した
- [ ] `tools/wdl_eval.py` の `substring` は実機と同じ厳密さ（`start < length`）であることを確認した
- [ ] 同型パターンをリポジトリ全体で検索し、全数対策した

### 初出案件
teams-channel-member-sync（2026-08-04・実環境実行で発生。`Compose_Admin_Cut`）
同型の潜在バグが sync-shared-mailbox-to-sharepoint-list の両フロー（`URL_BEFORE_LAYOUTS`）にも
存在し、同時に修正した。
【教訓】この誤りを見逃した直接の原因は、`tools/wdl_eval.py` の `substring` が
`start == length(s)` を許容していて **実機より緩かった**こと。空文字のテストケースは
存在していたのに合格してしまっていた。**評価器が実機より緩いと、テストは「通ったこと」を
証明するだけで「動くこと」を証明しない。** 評価器を実機に合わせて厳密化した結果、
別案件の同型バグ3件が即座に検出された。

---

## 追記方法
新しいエラーが発生した場合は、本ファイルに以下の書式で追記する。
```
## エラー名またはコード

### 発生メッセージ
### 発生条件
### 原因
### 誤った実装例
### 修正方針
### 修正例
### ZIP定義上の確認箇所
### Power Automate画面上の確認箇所
### 再発防止チェック
### 初出案件
```
- メッセージは可能な限り全文を引用する（実際のGUID・URL・メールアドレス等の機密性のある実値が含まれる場合はプレースホルダーに置換する）。
- 「初出案件」には案件名と発生日を記載する。
- 調査過程は[../templates/error_investigation_template.md](../templates/error_investigation_template.md)を使って記録し、確定後に本ファイルへ集約する。
