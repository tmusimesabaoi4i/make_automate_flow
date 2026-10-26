# Power Automate 実装Tips集

migrate_chat_spo案件で実際に効果があった実装パターンと避けるべきパターンをまとめる。
式の詳細は[expression_examples.md](expression_examples.md)、エラー事例は[error_catalog.md](error_catalog.md)参照。関連ルール: [../rules/02_expression_and_type_safety.md](../rules/02_expression_and_type_safety.md) / [../rules/01_flow_architecture_rules.md](../rules/01_flow_architecture_rules.md)

## 変数よりComposeを優先する場面
### 適用場面
値を一度作り後続で参照するだけで、ループをまたいで更新しない場合。
### 推奨方法
「作成する」(Compose)で値を作り`outputs('Compose名')`で参照する。
### 避ける方法
更新しない値のためにInitialize variableを使うこと（不要な変数は保守を煩雑にする）。
### 例
```
Compose_EffectiveLookbackDays: @if(greater(int(coalesce(triggerBody()?['LookbackDays'], 0)), 0), int(coalesce(triggerBody()?['LookbackDays'], 7)), 7)
```
### 注意点
ループ内で蓄積・更新する値は変数（Append/Increment系）が必要。次項参照。

## Appendアクションを使用する場面
### 適用場面
ループ内で配列や文字列に要素を蓄積していく場合。
### 推奨方法
配列蓄積は「配列変数に追加」、文字列連結蓄積は「文字列変数に追加」を使う。
### 避ける方法
Set variableで`union(variables('自身'), 新要素)`のように自己参照して蓄積すること（保存時エラー。[error_catalog.md](error_catalog.md)）。
### 例
```
AppendToArrayVariable: 対象=varMessagesArray, 値=@item()
```
### 注意点
Apply to eachの中に置き、ページ単位の配列をまるごと追加せず1要素ずつ追加する。

## SelectとApply to eachの使い分け
### 適用場面
配列の各要素を変換するだけならSelect、コネクタ呼び出し等を伴うならApply to each。
### 推奨方法
単純な射影のみは「選択」(Select)。呼び出し・変数更新・条件分岐を伴う処理はApply to each。
### 避ける方法
Apply to eachの中で単純な並べ替えだけを行い余分なループコストをかけること。
### 例
```
Select: 差出人=item()?['from']?['user']?['displayName']
```
### 注意点
Selectの出力はそのままApply to each/Filter arrayの入力にできる。

## Filter arrayのnull安全な入力
### 適用場面
配列が空・未定義の可能性がある入力元をFilter array等に渡す場合。
### 推奨方法
`coalesce(配列候補, json('[]'))`で配列を保証してから渡す。
### 避ける方法
null/undefinedの可能性がある値をそのままFromに指定すること。
### 例
```
From: @coalesce(body('Get_Channel_Messages')?['value'], json('[]'))
```
### 注意点
Filter/Selectの出力は常に配列（0件でも`[]`）なので重ねてcoalesceは不要。

## 配列の初期値
### 適用場面
Initialize variable（種類=array）の初期化。
### 推奨方法
`json('[]')`を初期値にする。
### 避ける方法
初期値を空文字列や未入力のままにすること（型不一致の原因）。
### 例
```
Initialize_MessagesArray: 種類=array, 値=@json('[]')
```
### 注意点
`array()`と`json('[]')`は同値だが表記をプロジェクト内で統一する。

## 文字列の初期値
### 適用場面
Initialize variable（種類=string）の初期化。
### 推奨方法
空文字列`''`を初期値にする。
### 避ける方法
初期値をnullや数値にすること。
### 例
```
Initialize_ReplyNextLink: 種類=string, 値=""
```
### 注意点
後続でtrim/concatする際も基本形`trim(coalesce(x,''))`は保持する。

## オブジェクトの初期値
### 適用場面
Initialize variable（種類=object）の初期化。
### 推奨方法
`json('{}')`を初期値にする。
### 避ける方法
オブジェクト型変数をnullや文字列で初期化すること。
### 例
```
値: @json('{}')
```
### 注意点
null安全化は`coalesce(item()?['obj'], json('{}'))`の形で統一する。

## 日付関数へ空文字列を渡さない方法
### 適用場面
formatDateTime/convertFromUtc等に、存在しない可能性のある日時文字列を渡す場合。
### 推奨方法
対象フィールドが空でないことを先に確認してから日付関数を適用する。
### 避ける方法
空文字列を日付関数にそのまま渡すこと（無効な日時としてエラーになる）。
### 例
```
条件: @not(empty(coalesce(item()?['createdDateTime'], '')))
```
### 注意点
日付が無い場合の代替表示（例:「不明」）はCondition分岐で明示する。

## Booleanのfalseを未設定扱いしない方法
### 適用場面
トリガー入力等のBoolean値をcoalesceで既定値補完する場合。
### 推奨方法
`equals(coalesce(x, 既定値), true)`でcoalesce後にequalsで厳密比較する。
### 避ける方法
`if(triggerBody()?['DryRun'], ...)`のように素通しで条件に使い、falseを未設定と誤解釈すること。
### 例
```
@equals(coalesce(triggerBody()?['DryRun'], true), true)
```
### 注意点
falseは「明示的なfalse」であり未設定（null）とは区別する。

## 数値の0を未設定扱いしない方法
### 適用場面
トリガー入力の数値（例:LookbackDays）を既定値補完する場合。
### 推奨方法
`if(greater(int(coalesce(x, 0)), 0), int(coalesce(x, 既定値)), 既定値)`で0以下のみ既定値に差し替える。
### 避ける方法
`coalesce(x, 既定値)`のみで済ませ、数値の0がそのまま採用される点を考慮しないこと。
### 例
```
@if(greater(int(coalesce(triggerBody()?['LookbackDays'], 0)), 0), int(coalesce(triggerBody()?['LookbackDays'], 7)), 7)
```
### 注意点
「0を有効値とするか未入力とみなすか」は要件を確認した上で使い分ける。

## 複雑な式をComposeへ分割する方法
### 適用場面
1つの式が長大でネストが深く、可読性・デバッグ性が低下する場合。
### 推奨方法
中間結果をComposeに分割し、後続で`outputs('Compose名')`を参照する。
### 避ける方法
1アクションの入力欄に何段もネストした巨大な式を書くこと。
### 例
```
HTMLエスケープをEscape_Amp→Escape_Lt→Escape_Gt→Escape_Quote→Escape_Aposの5Composeに分割
```
### 注意点
アクション数は増えるが、テスト実行時に各段の出力を個別確認できる。

## アクション名を最初に変更する理由
### 適用場面
アクションを追加した直後。
### 推奨方法
既定の自動採番名を、役割が分かる名前に即座に変更する。
### 避ける方法
自動採番のまま放置し、式の中で自動採番名への参照を大量に作ること（後の改名で参照が壊れる）。
### 例
```
Initialize_LookbackDays, Set_NextLink_First 等、役割+対象が分かる名前
```
### 注意点
名前は全体で一意にする（[error_catalog.md](error_catalog.md)参照）。初期化用とループ内更新用は`_First`等で区別する。

## 並列実行を無効にすべき場面
### 適用場面
Apply to each/Do untilの中で変数（SetVariable/Append/Increment）を更新する場合。
### 推奨方法
ループの並列実行をオフにする（`runtimeConfiguration.concurrency.repetitions=1`）。
### 避ける方法
変数を更新するループを既定の並列実行のまま残すこと（実行順序不定・更新競合の恐れ）。
### 例
```
Apply to each設定: 同時実行の制御=オン, 次数の制限=1
```
### 注意点
Do untilはそもそも逐次実行が仕様のため並列度の設定自体が無い。

## Graphのページング
### 適用場面
Microsoft Graphの一覧取得系エンドポイントで、1回の応答件数上限（例:$top=50）を超えるデータがありうる場合。
### 推奨方法
`@odata.nextLink`が空になるまでDo untilで繰り返し取得し、各ページをApply to each＋Append to array variableで蓄積する。
### 避ける方法
1ページのみ取得して処理を終えること（50件超のデータが取得漏れになる）。
### 例
```
GET https://graph.microsoft.com/v1.0/teams/{teamId}/channels/{channelId}/messages?$top=50
終了条件: @empty(variables('varNextLink'))
```
### 注意点
`{channelId}`のように`:`や`@`を含む識別子は`uriComponent()`でエンコードする。`{teamId}`はGUID形式のためエンコード不要。`@odata.nextLink`はそのまま使用する。

## Graph contentUrlのエンコード両対応
### 適用場面
Teams添付の`contentUrl`を`contains`等の文字列一致でフィルタ・分割する場合。
### 推奨方法
`/Shared Documents/`と`/Shared%20Documents/`の両方をorで含める（同一チャネル内でも生URLと
%エンコード済みURLが混在しうる）。
### 避ける方法
片方の形だけを前提にフィルタし、もう一方を黙って除外すること。
### 例
```
Filter条件: @or(contains(contentUrl, '/Shared Documents/'), contains(contentUrl, '/Shared%20Documents/'))
```
### 注意点
デコードは「エンコード済みと判定できる場合のみ」に限定する（生URLに含まれるリテラル`%`を壊さないため）。

## SharePoint保存後リンク
### 適用場面
SharePointにファイルを作成した後、そのファイルの表示URLを他の処理で使いたい場合。
### 推奨方法
ファイル作成後にプロパティ取得（Get file properties）を行い、その出力からURLを取得する。
### 避ける方法
ファイル作成アクションの出力に直接URLが含まれると仮定すること。
### 例
```
擬似コード: 保存成功後 → プロパティ取得 → URLプロパティを参照
```
### 注意点
参照キーは要実環境確認（[connector_action_notes.md](connector_action_notes.md)参照）。取得不能時はサイトURL+パスから構築する代替も検討する。

## SharePoint項目作成のサイト/リストを動的にしたいときはRESTを使う
### 適用場面
サイトのアドレス・リスト名をトリガー入力や変数など**式**で指定する必要がある場合。
### 推奨方法
「項目の作成」(Create item / PostItem)ではなく「SharePoint に HTTP 要求を送信」
(Send an HTTP request to SharePoint)を使う。前段のComposeでボディオブジェクトを組み立て、
`@string(outputs('Compose_X'))`をbodyに渡す。
### 避ける方法
`dataset`（サイト）/`table`（リスト）を式のままCreate item（PostItem）に渡すこと
（列スキーマが解決できず保存時に`item`欠落で失敗する。[error_catalog.md](error_catalog.md)参照）。
### 例
```
Method: POST
Uri: _api/web/lists/getbytitle('{listName}')/items
Headers: Accept=application/json;odata=nometadata, Content-Type=application/json;odata=nometadata
Body: @string(outputs('Compose_Run_Log_Body'))
```
### 注意点
ハイパーリンク列はRESTでは`{"Url":...}`形式を要求するため1行テキスト列を推奨。
テナントによっては`__metadata`（`ListItemEntityTypeFullName`）指定が必要な場合がある（要実環境確認）。

## インポート後の即時保存テスト
### 適用場面
ZIPパッケージをPower Automateへインポートした直後。
### 推奨方法
(1)開く (2)接続・パラメータ再設定 (3)そのまま一度保存 (4)フローチェッカー実行、の順で即座に検証する。
### 避ける方法
インポート成功を完成とみなし、保存・実行のテストをせず放置すること。
### 例
```
擬似コード: インポート成功 → 接続再設定 → 保存 → フローチェッカーで警告0件を確認
```
### 注意点
「インポート成功」「保存成功」「実行成功」は別々に検証が必要な段階である。

## 小期間から段階的にテストする方法
### 適用場面
大量データ（長期間）を扱うフローを初めて実行する場合。
### 推奨方法
取得期間パラメータを7→30→365→730のように段階的に拡大しながらテストする。
### 避ける方法
初回から最大期間でいきなり本番実行すること（実行時間上限や想定外挙動を検出しにくい）。
### 例
```
擬似コード: 7日でテスト → 問題なければ30日 → 365日 → 730日
```
### 注意点
フロー実行時間には上限（既定約30分）がある。上限到達時は期間分割で複数回実行する。
