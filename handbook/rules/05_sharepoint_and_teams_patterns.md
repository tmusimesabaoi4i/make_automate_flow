# SharePoint / Teams 実装パターン

Teams からのメッセージ取得（Graph HTTP）と SharePoint への保存・台帳操作の実装パターンです。コネクタの標準/プレミアム区分は [04](./04_connectors_permissions_and_dlp.md)、破壊的処理の順序や冪等性は [08](./08_error_handling_and_idempotency.md) を参照。実値は書かず `{teamId}` `{channelId}` `{siteUrl}` `{listId}` `{destinationPath}` を使う。

## Teams: Graph HTTP リクエスト【事実 + 一部 要実環境確認】
- 【事実】「Send a Microsoft Graph HTTP request（operationId=HttpRequest, apiId=shared_teams）」で
  Graph の GET を標準接続だけで実行できる（プレミアム不要）。
- 【事実】URL 構成（プレースホルダー）:

  ```
  一覧:   https://graph.microsoft.com/v1.0/teams/{teamId}/channels/{channelId}/messages?$top=50
  単一:   https://graph.microsoft.com/v1.0/teams/{teamId}/channels/{channelId}/messages/{messageId}
  返信:   https://graph.microsoft.com/v1.0/teams/{teamId}/channels/{channelId}/messages/{messageId}/replies?$top=50
  ```

- 【事実】**チャネルIDのURLエンコードは必須**。チャネルIDは `:` と `@` を含む
  （例 `19:...@thread.tacv2`）ため、`:`→`%3A`、`%40`←`@` にエンコードする。式では `uriComponent()` を使う。
  親メッセージIDも `uriComponent()` でエンコードする。`{teamId}` は GUID なのでエンコード不要。
- 【事実】`@odata.nextLink` が Graph から返す完全URLは、そのまま次リクエストの URI に使う（再エンコード不要）。
- 【事実】**単一投稿の取得（`/messages/{messageId}`）と返信の取得は実環境で動作を確認済み**
  （2026-07-24・teams_post_url_flows 案件。エンコード済みURL構成）。
  「未エンコードでも動く」ことは保証しない（今回たまたま動いたを一般化しない）。
- 【要実環境確認】`@odata.nextLink` による**複数ページ**追跡（返信51件以上）は未確認。

### Teams投稿URLから識別子を取り出す【事実】
- 【事実】チャネル投稿の「リンクをコピー」で得られるURLの形は次のとおり。
  ホストは `teams.microsoft.com` のほか新Teamsの `teams.cloud.microsoft` もある。

  ```
  https://teams.microsoft.com/l/message/{channelId}/{messageId}?tenantId={tenantId}&groupId={groupId}&parentMessageId={parentMessageId}
  ```

- 【事実】対応関係: **`groupId` がチームID**、**パス上の `{channelId}` がチャネルID**。
  `groupId` をチャネルIDに流用しない。パス上の `{messageId}` は「リンクが指すメッセージ」であり、
  返信のリンクなら返信ID。**返信IDを常に親投稿IDとして扱わない**。
- 【推奨】Graphに渡す投稿IDは `parentMessageId` を優先し、無ければパス上の `{messageId}` を使う。
  これで返信のURLを入力しても親投稿へ解決できる。
- 【事実】親投稿のリンクには **`parentMessageId=0` が付く変種がある**。メッセージIDは13桁のエポックミリ秒であり
  `'0'` は実在しないため、`'0'` は「値なし」と同等に扱う（そのまま渡すと必ず404）。
- 【事実】チャネルIDはURLエンコードされていることが多い（`19%3A...%40thread.tacv2`）。
  `decodeUriComponent()` で復号してから保持し、Graph URL では `uriComponent()` で再エンコードする。
  非エンコードのURLでも `decodeUriComponent()` は無害（`%` が無ければ素通り）。
- 【事実】チャネルとチャットの判別: チャネルスレッドは `@thread.tacv2`、
  1対1・グループチャットは `@unq.gbl.spaces`。チャットは Graph の
  `/teams/{teamId}/channels/...` では取得できないため、入口で弾く。
- 【推奨】解析は固定文字数・固定位置に依存させず、区切り文字（`#` `?` `&` `/` `/l/message/`）で分割する。
  クエリは順不同・欠落・余分パラメータがあり得る。具体的な式は
  [../knowledge/expression_examples.md](../knowledge/expression_examples.md) の「Teams投稿URLの解析」を参照。
- 【要実環境確認】**共有チャネル**はURLの `groupId` が投稿の実体があるチームと一致しない場合があり、
  `/teams/{groupId}/channels/{channelId}/messages/{id}` が404になり得る。標準・プライベート・共有の
  各チャネルでの動作は個別に確認する。

### ページングは nextLink 追跡が必須【事実】
- 【事実】`$top=50` は1ページの最大件数にすぎず、それだけでは完了しない。50件超は取得漏れになる。
- 【推奨】「Do until（〜になるまで）」で `@odata.nextLink` を追跡し、nextLink が空になるまで繰り返す。
  ループは並列オフ（[01](./01_flow_architecture_rules.md)）。累積は Append to array variable（[03](./03_variables_arrays_and_objects.md)）。
- 【事実】`body('<Graph HTTP アクション>')` は **Graph 応答JSONそのもの**
  （`statusCode`/`headers`/`body` の封筒ではない）。応答の一覧は `body(...)?['value']`、次ページは `body(...)?['@odata.nextLink']`。

### チャネル添付ファイルの実際の保存場所【事実】
- 【事実】チャネル投稿の添付（`contentType`=`reference`）は**投稿のあるチームのSharePointサイト**の
  既定ライブラリ（`Shared Documents`/共有ドキュメント）配下に保存される。保存先として別途用意した
  サイトと同一とは限らない。
- 【事実】Graphが返す`contentUrl`は**生URL**（非エンコード。日本語ファイル名もそのまま）。
- 【推奨】ファイル取得（`GetFileContentByPath`）の`path`は**datasetサイトからのサイト相対パス**。
  `contentUrl`を`/Shared Documents/`の位置で分割し、前半を`dataset`・後半（`%20`→半角スペース置換）
  を`path`に使う（Composeで導出）。詳細・404事例は[エラーカタログ](../knowledge/error_catalog.md)参照。

## SharePoint: リスト/ライブラリ操作【事実 + 要実環境確認】
- リスト・列・ビューのREST自動作成は [../knowledge/sharepoint_rest_list_provisioning.md](../knowledge/sharepoint_rest_list_provisioning.md) 参照。
- 【事実】アクションの主要パラメータ: `dataset`=サイトのアドレス（`{siteUrl}`）、`table`=リスト/ライブラリ（`{listId}`）、
  項目は `item/<内部列名>` 形式。GetItems は `$filter` `$orderby` `$top`、CreateFile は `folderPath` `name` `body`。
- 【事実】**日本語表示名の列は内部名が `OData__xHHHH_` 形式**（Unicode コードポイントのエンコード）。
  `$filter` や `item/` で参照するときは表示名でなく**内部名**を使い、値のエスケープにも注意する。
- 【要実環境確認】`table` はフロー内でリスト名を仮置きしているため、**インポート後に実物のリスト/ライブラリを再選択**する。
  GetItems / PostItem / GetFileItem のリスト/ライブラリを選び直す。

### 動的なサイト/リストへの項目作成は REST を使う【事実・最重要】
- 【事実】「項目の作成」(Create item / operationId=`PostItem`) の本文パラメータ `item` は
  動的スキーマ（x-ms-dynamic-schema）で、列のフラット化キー（`item/Title`等）は
  `dataset`（サイト）/`table`（リスト）を**静的に選択した場合のみ**解決される。
- 【事実・アンチパターン】`dataset`/`table`を式にすると保存時に
  `OpenApiOperationParameterValidationFailed`（`item`欠落）で失敗する。詳細は
  [エラーカタログ](../knowledge/error_catalog.md)参照。
- 【推奨】サイト/リストを式で指定する必要がある場合は`PostItem`ではなく
  「SharePoint に HTTP 要求を送信」(Send an HTTP request to SharePoint) ＋ REST を使う。
  前段のComposeでボディオブジェクトを組み立て、`parameters/body`に
  `@string(outputs('Compose_X'))`を渡す。`Uri`=`_api/web/lists/getbytitle('{listName}')/items`
  （リスト名部分は式可）、`Headers`は`Accept`/`Content-Type`とも
  `application/json;odata=nometadata`にすれば`__metadata`は不要（出典2026-07-16参照: [tomriha.com](https://tomriha.com/http-request-to-create-sp-item-in-dynamic-list-site-with-power-automate/) / [Microsoft Learn](https://learn.microsoft.com/en-us/sharepoint/dev/business-apps/power-automate/guidance/working-with-send-sp-http-request)）。
- 【要実環境確認】ハイパーリンク列はRESTでは`{"Url":...}`形式を要求するため1行テキスト列を推奨。
  テナントによっては`__metadata`（`ListItemEntityTypeFullName`）指定を要求される場合がある。

### コネクタ出力は封筒構造。フィールドは body() で参照する【事実・最重要】
- 【事実】コネクタ（OpenApiConnection）アクションの `outputs('X')` は封筒
  `{statusCode, headers, body}` を返す。フィールドの直下参照 `outputs('X')?['ItemId']` は**常に null**。
- 【事実】正しい参照は `body('X')?['ItemId']`（または `outputs('X')?['body/ItemId']`）。
  Compose の `outputs('Compose_X')` は封筒を持たないためそのままでよい。
- 【事実】本案件では監査で5箇所の潜在バグ（`outputs('Create...')?['ItemId']` 等）として検出・修正した。
  DryRun 経路では発火せず、本番経路でのみ全添付が保存失敗になるところだった。
  機械走査「outputs(コネクタ名)?[非body キー] → エラー」で再発防止できる。

### ファイル保存先フォルダの事前確保【事実・最重要】
- 【事実】SharePoint「ファイルの作成」(Create file / CreateFile) は**中間フォルダを自動作成しない**。
  保存先フォルダ階層は事前に存在している必要がある。
- 【推奨】フロー内で確保する場合はREST `POST _api/web/folders`（`SP.Folder`・`odata=verbose`・
  `ServerRelativeUrl`=**フルサーバー相対** `{sitePath}/{library}/{segments}`）を1階層ずつ、
  `runAfter=[Succeeded,Failed]`で継続実行し、最後に`GET GetFolderByServerRelativeUrl`で実在検証する
  （既存時のPOST失敗を握り潰さないのは最終GETがあるため）。
- 【事実・アンチパターン】サイト相対の先頭スラッシュはテナントルート基準に誤解決される。
  作成例は[../knowledge/sharepoint_rest_list_provisioning.md](../knowledge/sharepoint_rest_list_provisioning.md)、
  発生事例は[エラーカタログ](../knowledge/error_catalog.md)参照。

### 保存後URLは既知の値から決定的に構築する【事実・最重要】
- 【事実】成果物リンクには**保存したファイル自体のURL**を使う。Teams の `contentUrl`（添付の元URL）を
  成果物リンクに流用しない（別物）。
- 【推奨・主方式】`replace(concat({siteUrl}, '/', {library}, '/', {folderPath}, '/', {savedName}), ' ', '%20')`
  のように**サイト＋ライブラリ＋パス＋ファイル名という既知の値から決定的に構築**する。`CreateFile`の
  成功自体がそのパス・名前でファイルが存在することの直接証拠になるため、追加の取得アクションが不要。
- 【事実・アンチパターン】`GetFileItem`等の`table`はライブラリの**表示名/GUID**を要求し、`{library}`
  （URLセグメント。例:`Shared Documents`）と表示名（日本語サイトでは「ドキュメント」等）が食い違うと
  名前解決に失敗し、実行時に対象アクション全件がFailedになる。詳細は[エラーカタログ](../knowledge/error_catalog.md)参照。
- 【経緯】旧方式の `body('<GetFileItem>')?['{Link}']`（波括弧キー）は名前解決・応答依存のため廃止した。

### 破壊的処理は取得成功後にのみ【事実・アンチパターン】
- 【事実・アンチパターン】実働サンプルには「既存項目を全削除してから Graph 取得」する順序があり、
  取得が失敗/0件でも削除済みでロールバックできない危険があった。
- 【推奨】**新規データ取得が成功した後にのみ**、上書き・削除などの破壊的処理を行う。順序を逆にしない。
- 【推奨】同名ファイルの扱い（上書き/連番付与/スキップ）は**事前に方針を決めて**おく。実装後に迷わない。

## タイムゾーンの基準をそろえる【事実・アンチパターン】
- 【事実・アンチパターン】実働サンプルはタイトルを JST 変換、別列を UTC のまま保存し、
  UTC 深夜前後で日付がずれる不整合があった。
- 【推奨】同一項目内で日時の基準（UTC か JST か）をそろえる。表示用に JST 変換するなら、
  比較・キー生成も基準を明確にする。

関連: [00 コアルール](./00_power_automate_core_rules.md) / [04 コネクタ・権限](./04_connectors_permissions_and_dlp.md) / [08 エラー処理](./08_error_handling_and_idempotency.md) / [エラーカタログ](../knowledge/error_catalog.md)
