# コネクタ・アクション仕様メモ

確認したコネクタ・アクションの入力パラメータと確認根拠をまとめる。実環境での最終確認が必要な項目には「要実環境確認」と明記する。
**確認根拠は節ごとに異なる**（実環境での実行実績／実エクスポート定義／公式資料）。各節の「確認日」と根拠を必ず読むこと。
Teams・SharePoint・Content Conversion の各節は 2026-07-16 時点（一部 2026-07-24 に実環境で格上げ）、
Office 365 Outlook の `GetEmailsV3` は 2026-08-03 に**実環境で保存・実行を確認**。
同節の他の操作と Teams `PostMessageToConversation` は**参照サンプル定義に実在したキーのみ**（実行実績なし）。
関連ルール: [../rules/05_sharepoint_and_teams_patterns.md](../rules/05_sharepoint_and_teams_patterns.md)

## Microsoft Teams（shared_teams）

### Send a Microsoft Graph HTTP request（operationId: HttpRequest）
- 標準（非プレミアム）コネクタ・アクション。Azure ADアプリ登録・管理者同意は不要。
- 主要パラメータ: `Uri`（呼び出すGraph APIのURL）/ `Method`（GET等）/ `ContentType`。
- 用途例:
  - 一覧: `GET https://graph.microsoft.com/v1.0/teams/{teamId}/channels/{channelId}/messages?$top=50`
  - **単一投稿**: `GET https://graph.microsoft.com/v1.0/teams/{teamId}/channels/{channelId}/messages/{messageId}`
  - 返信: `GET .../messages/{messageId}/replies?$top=50`
- 応答: `body('アクション名')`はGraph応答JSONそのもの（`statusCode`/`headers`/`body`の封筒形ではない）。
  HTTPステータスは封筒側の`outputs('アクション名')?['statusCode']`で参照できる。
- 【事実】**単一メッセージ取得（`/messages/{messageId}`）が本コネクタで動作する**ことを実環境で確認した。
  任意のメッセージIDを指定して1件だけ取得する用途に使える。
  確認日: 2026-07-24 / 根拠: teams_post_url_flows 案件のFlow1を実環境でインポート・実行し、投稿本文の取得に成功。
- 【事実】`/replies` の取得も同案件のFlow2で実環境動作を確認した（返信50件以下＝単一ページ）。
  確認日: 2026-07-24。
- 【事実】`{channelId}`のような`:`や`@`を含む識別子は`uriComponent()`でのエンコードが必要。
  上記の実環境実行はエンコードした構成で成功している。
- 【要実環境確認】`@odata.nextLink`による**複数ページ**の追跡（返信51件以上）は未確認。
  単一ページで`@odata.nextLink`が返らずループが正常終了することのみ確認済み。

### 参照実装
- teams_post_url_flows 案件の2フローが、本アクションのみで完結する最小構成の実例。
  URL解析→Graph単一取得→JSON正規化（Flow1）、＋`Do until`による返信ページング（Flow2）。
  → [sample_flow_reference_index.md](sample_flow_reference_index.md)

### Get messages in a channel / List replies of a channel message（参考・未使用）
- operationId: `GetMessagesFromChannel` / `ListRepliesToMessage`。標準コネクタ。
- `ListRepliesToMessage`の`$top`既定20・最大50。
- 今回のフローでは簡易代替として整理したのみで未使用（HttpRequest方式を採用）。
- 確認日: 2026-07-16 / 根拠: 公式資料（Teamsコネクタリファレンス）。

### Post message in a chat or channel（operationId: PostMessageToConversation）
日本語表示名「チャットまたはチャネルでメッセージを投稿する」。確認日: 2026-08-03。
根拠: `references/raw/sample_function_20260803105312.zip` の実エクスポート定義
（→ [sample_flow_reference_index.md](sample_flow_reference_index.md)）。**サンプル定義に実在するキーの記録であり、
パラメータ仕様の網羅ではない。**
- 【事実】入力キーは `poster` / `location` ＋ 動的ボディのフラット化キー `body/recipient` / `body/messageBody`。
- 【事実】`poster` の実値例は `"Flow bot"`。`location` の実値例は **`"Chat with Flow bot"`**。
- 【要実環境確認】公式リファレンス（参照日 2026-08-03）で読めた `location` の許可値は `Channel` / `Chat` で、
  上記の実値と表記が一致しない。**チャネル投稿を組む場合は値をデザイナーで確認する**（実値を推測で書かない）。
- 【事実】`body/messageBody` の実値例は `<p class="editor-paragraph">…</p>`。
  【推定】デザイナーのリッチテキストエディタが生成する既定マークアップ。
  【要実環境確認】このラッパーが必須か（プレーン文字列で足りるか）は未確認。

## Office 365 Outlook（shared_office365）

確認日: 2026-08-03。**操作ごとに根拠の強さが違うので注意する。**

| 操作 | 根拠 |
|---|---|
| `GetEmailsV3` | **実環境で保存・実行に成功**（sync-shared-mailbox-to-sharepoint-list） |
| `SharedMailboxOnNewEmailV2` / `MarkAsRead_V3` | 参照サンプルの実エクスポート定義に実在したキーのみ（**実行実績なし**） |

公式コネクタリファレンスは 2026-08-03 時点で**パラメータ表を正確に読み取れなかった**
（同一URLの再取得で内容が食い違った）ため、実行実績の無い操作については
キー名を確定させる必要が生じた時点で**デザイナー上で入力欄を確認する**。

### When a new email arrives in a shared mailbox (V2)（operationId: SharedMailboxOnNewEmailV2）
日本語表示名「新しいメールが共有メールボックスに届いたとき (V2)」。**トリガー**。
- 【事実】`type` は `OpenApiConnection`。ポーリング間隔はトリガー直下の `recurrence`/`evaluatedRecurrence`
  で指定する（形式は [../rules/01_flow_architecture_rules.md](../rules/01_flow_architecture_rules.md)）。
- 【事実】サンプルに実在した入力キー: `mailboxAddress`（監視する共有メールボックス）/ `folderId`（値 `"Inbox"`）/
  `importance`（文字列 `"Any"`）/ `hasAttachments`（真偽値）/ `includeAttachments`（真偽値）。
  **フォルダ指定のキーは `folderPath` ではなく `folderId`**（実エクスポートで確認）。
- 【事実】`splitOn: "@triggerOutputs()?['body/value']"` を併用した実例がある（デバッチ）。
- 【要実環境確認】共有メールボックス監視に必要な権限（フルアクセス等）とDLPポリシー適合。
- 【要実環境確認】1分間隔ポーリングのライセンス上の実行回数上限・スロットリング。

### Get emails (V3)（operationId: GetEmailsV3）
日本語表示名「メールを取得する (V3)」。
- 【事実】次のパラメータ構成で**実環境の保存・実行に成功**した（2026-08-03 /
  sync-shared-mailbox-to-sharepoint-list）。保存時のコネクタ検証を通過しているため、
  **キー名が実在することの実証**になる。
  `mailboxAddress`（式で共有メールボックスを指定）/ `folderPath`（`"Inbox"`）/
  `top`（式）/ `fetchOnlyUnread`（`false`）/ `includeAttachments`（`false`）。
- 【事実】共有メールボックスの読み取りは本アクション＋`mailboxAddress` で行う
  （専用の「共有メールボックスからメール取得」アクションは存在しない）。
- 【事実】`top` の公式上限は 1000（既定10）。Office 365 Outlook の調整制限は 300コール/60秒/接続。
  参照日 2026-08-03。
- 【事実】`top=100` で**100件を1回で取得できた**（2026-08-03 実測。`fetchedCount:100`）。
  後段の SharePoint REST 約250回と合わせても調整制限・実行時間上限に触れなかった。
- 【事実・別事例】参照サンプル（`sample_function_20260803105312.zip`）では `inputs.parameters` キーが
  **ごと省略**されていた（`host` と `authentication` のみ）。必須パラメータを持たない操作は
  この形でもエクスポートされる。**ただしその状態では対象メールボックスを指定できない**ため、
  共有メールボックスを読むなら上記のとおり `mailboxAddress` を明示すること。
- 【要実環境確認】`parameters` を省略した場合の既定の対象メールボックス・フォルダ・取得件数は未確認。
- 【要実環境確認】`GetEmailsV3` の**既定の並び順**。本フローは `sort`+`reverse` で受信日時降順に
  並べ替えてから上位N件を採るが、コネクタが古い順にN件返す場合は最新N件にならない。

### Mark as read or unread (V3)（operationId: MarkAsRead_V3）
日本語表示名「開封済みまたは未読としてマークする (V3)」。
- 【事実】サンプルに実在した入力キーは `messageId` の**1件のみ**（値は `@items('<Foreach名>')?['id']`）。
- 【要実環境確認】既読/未読を切り替えるパラメータを指定しない状態で保存・実行できるか。
  未指定の必須パラメータは保存時 `OpenApiOperationParameterValidationFailed` の原因になり得る
  （同型: [error_catalog.md](error_catalog.md) の PostItem `item` 欠落）。
- 【注意】既読化は**状態を変更する副作用**。対象メールボックスを取り違えると実害が出る。

## パラメータ表記の共通則【事実】

- 【事実】**動的スキーマを持つボディパラメータは、スラッシュでフラット化したキー**で定義に現れる。
  コネクタをまたいで同じ規則: `item/Title`（SharePoint `PostItem`）/ `parameters/uri`（SharePoint `HttpRequest`）/
  `body/messageBody`（Teams `PostMessageToConversation`）。
- 【事実】**必須パラメータを持たない操作は `inputs.parameters` キーごと省略される**ことがある。
  `parameters` が無い＝壊れている、とは限らない（検証スクリプトで無条件に必須としない）。
- 【事実】アクションの**内部名は表示名の空白を `_` に置換したもの**。表示名を英語にすれば内部名も英語になる
  （本リポジトリの命名規則は英数字＋アンダースコア。[../rules/01_flow_architecture_rules.md](../rules/01_flow_architecture_rules.md)）。

## SharePoint（shared_sharepointonline）

### GetItems（Get items）
- 主要パラメータ: `dataset`（サイトURL、例:`{siteUrl}`）/ `table`（リスト/ライブラリ、例:`{listId}`）/ `$filter` / `$orderby` / `$top`。
- 用途: 処理台帳（冪等性確認用リスト）の既存項目検索。
- 確認日: 2026-07-16 / 根拠: 公式資料＋雛形サンプル。

### PostItem（Create item）
- 主要パラメータ: `dataset` / `table` / `item`（列内部名ベースのオブジェクト）。
- 要実環境確認: 日本語表示名の列は内部名が`OData__xHHHH_`形式（例:`item/OData__x30d5__x30a1__x30a4__x30eb_`）になる場合がある。列内部名はインポート後に実際のリストへ再選択して確認する。
- 確認日: 2026-07-16 / 根拠: 実働サンプルの機械解析＋公式資料。

### CreateFile（Create file）
- 主要パラメータ: `dataset` / `folderPath`（例:`{destinationPath}`）/ `name` / `body`。
- 用途: 添付ファイル・総括文書ファイルの保存。
- 確認日: 2026-07-16 / 根拠: 公式資料＋雛形サンプル。

### GetFileItem（Get file properties）
- 主要パラメータ: `dataset` / `table` / `id`。
- 要実環境確認: 保存後URL参照式`outputs(...)?['{Link}']`はコミュニティ情報のみで、公式資料に直接の記載なし。代替として`{FullPath}`+サイトURLの組み立ても検討する。
- 確認日: 2026-07-16 / 根拠: 公式資料（Link/FullPath/Pathの存在は確認済み）＋コミュニティ情報（Link参照式は未確認）。

### GetFileContentByPath（Get file content using path）
- 主要パラメータ: `dataset` / `path`。
- 要実環境確認: 添付contentUrlの実際のパス解析可否（カード形式・共有リンク種別により形式が異なりうる）。
- 確認日: 2026-07-16 / 根拠: 公式資料。

## Content Conversion（shared_conversionservice）

### HtmlToText（Html to text）
- 主要パラメータ: `Content`（キー名は`"html"`ではなく`Content`である点に注意。公式資料で確認済み）。
- 用途: HTML形式の投稿本文をプレーンテキスト化。
- 【事実】**実環境で100件連続の変換に成功**（2026-08-03 / sync-shared-mailbox-to-sharepoint-list。
  `failedCount:0`）。少なくとも当該テナントではDLPで遮断されていない。
- 【要実環境確認】出力の形（文字列そのものか、オブジェクトに包まれるか）。
  `@string(coalesce(body('<変換アクション>'), ''))` で受けているため変換自体は成功しているが、
  保存された列の中身は未確認。
- 要実環境確認: 他テナントでの接続要否・DLPポリシーとの適合。
- 確認日: 2026-07-16 / 根拠: 公式資料（[references/official_reference_findings.md](../../references/official_reference_findings.md)）。

---
本メモは[expression_examples.md](expression_examples.md)・[sample_flow_reference_index.md](sample_flow_reference_index.md)と合わせて参照する。実装前に必ず[../checklists/design_review_checklist.md](../checklists/design_review_checklist.md)と照合すること。
