# Microsoft公式資料調査結果ドキュメント

対象フロー: PA_Migrate_Teams_Meeting_Archive_To_SPO（Teams課内会議アーカイブ）
作成日: 2026-07-16

本ドキュメントは、今回のフロー実装で使用したコネクタアクション（operationId）・式関数・パッケージ形式について、Microsoft公式資料で確認できた仕様と、それに基づく今回の採用方法をまとめたものである。各項目は「確認した機能／公式資料／確認できた仕様／今回の採用方法／注意事項」の5点セットで記載する。不確実な点は「不確実」と明記し、断定しない。

---

## 1. Teams「Send a Microsoft Graph HTTP request」

```
確認した機能: Microsoft Teamsコネクタの「Send a Microsoft Graph HTTP request」アクション
公式資料: https://learn.microsoft.com/connectors/teams/
確認できた仕様:
  - operationId = HttpRequest
  - apiId = shared_teams（Microsoft Teams標準コネクタ内のアクション）
  - 標準（プレミアムではない）コネクタ・アクションであり、Azure ADアプリ登録や管理者同意は不要
  - 雛形ZIP（既存の配布済みフローパッケージ）内でも実際に使用されていることを確認済み
今回の採用方法:
  - 親投稿一覧取得: GET /teams/{teamId}/channels/{channelId}/messages?$top=50
  - 返信一覧取得: GET /teams/{teamId}/channels/{channelId}/messages/{messageId}/replies?$top=50
  - いずれも応答の @odata.nextLink を使ったDo untilページング（varNextLink / varReplyNextLink が空になるまで継続）で全件取得
注意事項:
  - authenticationはRaw（X-MS-APIM-Tokens参照式）で、雛形と同一の標準形。秘密情報の埋め込みはない
  - Graph APIのレスポンス構造（from.user.displayName等）はGraph側のドキュメントに準拠する前提であり、Teamsコネクタ自体の公式ページには個々のGraphエンドポイントの詳細仕様までは記載されていない
```

---

## 2. Teams「Get messages in a channel」/「List replies of a channel message」

```
確認した機能: Microsoft Teamsコネクタの「Get messages in a channel」「List replies of a channel message」アクション
公式資料: https://learn.microsoft.com/connectors/teams/
確認できた仕様:
  - Get messages in a channel: operationId = GetMessagesFromChannel、パラメータ (groupId, channelId)
  - List replies of a channel message: operationId = ListRepliesToMessage、パラメータ (groupId, channelId, messageId, $top)、$top既定値20・最大50
  - いずれも標準コネクタ・アクション
今回の採用方法:
  - 今回のフローの主方式は上記1.のHttpRequest（Graph直接呼び出し＋nextLinkページング）であり、GetMessagesFromChannel / ListRepliesToMessageは簡易的な代替手段として整理したのみで、本フローの実装では未使用
注意事項:
  - ListRepliesToMessageの$topは最大50が公式仕様上の上限であるため、50件を超える返信がある会話には別途ページング処理（HttpRequest方式）が必要という判断につながっている
```

---

## 3. SharePointコネクタ（CreateFile / GetFileItem / GetItems / GetFileContentByPath / HttpRequest(REST)）

```
確認した機能: SharePointコネクタ（shared_sharepointonline）の各アクション
公式資料: https://learn.microsoft.com/connectors/sharepointonline/
確認できた仕様:
  - Create file: operationId = CreateFile、パラメータ (dataset, folderPath, name, body)
  - Get file properties: operationId = GetFileItem、パラメータ (dataset, table, id)
  - Get items: operationId = GetItems、パラメータ (dataset, table, $filter, $orderby, $top)
  - Create item: operationId = PostItem、パラメータ (dataset, table, item)
    ※本フローでは**v7でPostItemの採用をやめている**（下記「今回の採用方法」・末尾「追加確認（2026-07-16・保存エラー調査）」参照）。operationId自体・パラメータ構成は公式資料どおりであり、この行は研究時点の確認事実として残す。
  - Send an HTTP request to SharePoint: operationId = HttpRequest、パラメータ (dataset, method, uri, headers, body等)。SharePoint RESTでの項目作成に使用（詳細は末尾「追加確認（2026-07-16・保存エラー調査）」参照）
  - Get file content using path: operationId = GetFileContentByPath、パラメータ (dataset, path)
  - いずれも標準（プレミアムではない）コネクタ・アクション
  - ファイルのWeb URLについては、委任不可（not delegable）のシステムフィールドとして Link / FullPath / Path が公式に存在することを確認
今回の採用方法（v7時点）:
  - Scope_10でGetItems（台帳MeetingArchiveLedgerの重複確認用$filter・$orderby）
  - Scope_30でCreateFile（添付ファイル保存）とGetFileItem（保存後のプロパティ取得、URL取得に使用）
  - Scope_60でCreateFile（.doc本体作成）とGetFileItem
  - 台帳・実行ログへの書き込みは、v6まではPostItemを使用していたが、v7でSharePoint「HTTP要求を送信します」(operationId=HttpRequest)によるREST呼び出しに変更した（サイト/リストが式のためPostItemの保存時検証でitem欠落エラーになったため。理由は末尾の追加確認節を参照）
  - 添付ファイル本体取得にGetFileContentByPath（contentUrlから解析したパスを使用）
注意事項:
  - 保存後ファイルURL取得式 outputs(...)?['{Link}'] という波括弧キー表記は、コミュニティ（フォーラム等）情報でのみ確認されたものであり、公式資料上の直接的な記載は確認できていない＝不確実。実環境での動作確認が必要
  - {Link}が取得できない場合の代替として、{FullPath}＋サイトアドレスを結合してURLを構築する方式を検討事項として残している（スラッシュはエンコードしない前提）
  - table（リスト/ライブラリ選択）はフロー内で名前を仮置きしているため、インポート後に実際のリスト・ライブラリへの再選択が必要（GetItems/GetFileItem対象。台帳・実行ログ書込み4アクションはv7でREST化されテーブル欄自体を持たない）
```

---

## 4. Content Conversion「Html to text」

```
確認した機能: Content Conversionコネクタ（shared_conversionservice）の「Html to text」アクション
公式資料: https://learn.microsoft.com/connectors/conversionservice/
確認できた仕様:
  - operationId = HtmlToText
  - 入力パラメータのキー名は Content（"html"ではない点に注意。公式資料で確認済み）
  - 標準（プレミアムではない）コネクタ・アクション
今回の採用方法:
  - 各会議の返信本文（body.content、HTML形式）をプレーンテキスト化する処理で使用し、パラメータには Content キーでbody.contentの値を渡す
注意事項:
  - パラメータキーを誤って "html" 等とすると入力欠落・エラーの原因になるため、実装・レビュー時にキー名 Content を必ず確認すること
```

---

## 5. Office 365 Users「Get user profile (V2)」

```
確認した機能: Office 365 Usersコネクタの「Get user profile (V2)」アクション
公式資料: https://learn.microsoft.com/connectors/office365users/
確認できた仕様:
  - operationId = UserProfile_V2、パラメータ (id, $select)
  - 標準（プレミアムではない）コネクタ・アクション
今回の採用方法:
  - 今回のフローでは主催者情報を定数 '不明' を既定値として扱う設計としたため、UserProfile_V2は未使用
  - 将来的に投稿者のAAD情報等から主催者を補完する拡張を行う場合の参考として記載
注意事項:
  - 現状は投稿者表示名をそのまま主催者に流用しない設計（§10.3方針）であり、主催者は会議情報から取得できる場合にのみ差し替える運用を想定している。UserProfile_V2を使う場合はAzure AD上のユーザー解決可否・権限に依存する点に留意
```

---

## 6. 式（Workflow Definition Language）関数: sort / reverse / union 等

```
確認した機能: Power Automate（Logic Apps式言語）のコレクション操作関数群
公式資料: https://learn.microsoft.com/azure/logic-apps/workflow-definition-language-functions-reference
確認できた仕様:
  - sort(collection [, 'プロパティ名']) は実在する関数であり、昇順ソートのみをサポートする。オブジェクトの配列に対してプリミティブ型のプロパティを指定してソート可能
  - 降順にしたい場合は sort() の結果に reverse() を組み合わせる必要がある（sort自体に降順オプションはない）
  - reverse() は実在する関数（配列やコレクションの並びを反転）
  - union() は実在する関数だが、重複を排除する仕様である（完全一致する要素は統合される）。ページング結果の配列連結に使う場合、要素が完全一致するケースがあるとその副作用で件数が減る可能性がある点に注意が必要
  - このほか coalesce / trim / empty / addDays / formatDateTime / convertFromUtc / replace / xpath 等も公式資料に実在する関数として確認済み
今回の採用方法:
  - 会議一覧のソートに sort(variables('varMeetings'), 'sortKey') を採用（昇順、sortKeyはyyyyMMddHHmmss_messageId形式のため時系列昇順に一致）
  - trim/coalesce/emptyは投稿者名・本文等のnull/空文字ガードに使用
  - addDays/formatDateTime/convertFromUtcは取得期間（LookbackDays）計算や日本時間変換、ファイル名の日付付与に使用
  - replaceはファイル名の禁止文字（" * : < > ? / \ |）の置換に使用
注意事項:
  - union()はページング連結処理では今回未使用（配列連結にはconcat/unionではなく、Do until内でのAppend to array variable方式を採用しているため、重複排除の副作用は今回の実装には影響しない）が、他の実装で配列連結にunion()を使う場合は重複排除仕様を必ず考慮すること
  - sort()は降順非対応という仕様上の制約を理解した上で、今回は昇順のみで用が足りる設計としている
```

---

## 7. レガシーパッケージ（.zip）形式

```
確認した機能: Power Automateの「パッケージ（レガシー）」形式によるフローのエクスポート／インポート
公式資料: https://learn.microsoft.com/power-automate/export-import-flow-non-solution
確認できた仕様:
  - インポート手順（公式）: make.powerautomate.com → マイフロー → インポート → パッケージ（レガシー）を選択 → 対象ZIPを指定 → 各接続について「新規作成として(Create as New)」等を選び、関連リソースで接続を選択 → インポート実行
  - パッケージ内部のJSON構造（ルートのmanifest.json、Microsoft.Flow/flows/manifest.json、flows/{guid}/definition.json・apisMap.json・connectionsMap.json等）そのものについては、公式ドキュメントページでは内部フォーマットの詳細仕様は公開されていない
  - 上記の内部構造は、Microsoft（OfficeDev）が実際に配布しているサンプルパッケージの中身を確認することで構造を把握したものである
今回の採用方法:
  - 今回生成したZIPは、ルートmanifest.json（schema/details/resources）＋Microsoft.Flow/flows/manifest.json（flowAssets.assetPaths）＋flows/{guid}/definition.json・apisMap.json・connectionsMap.jsonという、確認済みの雛形と同一の構造で作成
  - フロー名（definition.json内のname）は匿名の新規GUID（2fe554b1-6ba6-4ce0-962c-07bde4bdb6ee）を採番して使用
  - connectionReferences.connectionNameは匿名GUID、metadata.creatorは空オブジェクト、details.creatorは"N/A"とし、雛形に含まれていた実際のメールアドレス・creator.id・tenantId・接続GUIDは一切含めていない
注意事項:
  - connectionName／creator.id／tenantIdが、インポート時にユーザーが選択した実際の接続情報へ再マッピングされるという挙動については、Microsoft自身が実サンプルパッケージを非匿名（実際のGUID等を含む）の状態で配布している事実が状況証拠として存在するのみで、公式ドキュメントにこの再マッピング挙動が明言されているわけではない＝不確実
  - インポート時にフローのGUIDがどのように新規採番・処理されるかの詳細動作についても、公式資料に明記された仕様は確認できていない＝不確実
  - 実環境でのインポート自体は今回未実施・未検証であり、確認できているのはJSONのパース可否・参照整合性・ZIP再展開結果が雛形と同一構造であることのみ
```

---

## 注意事項（全体）

- 本フローで使用した3コネクタ（Teams / SharePoint / Content Conversion）のアクションはすべて標準コネクタであり、汎用HTTPコネクタ・HTTP with Microsoft Entra ID（旧HTTP with Azure AD）・Azure ADアプリ登録・管理者同意はいずれも使用していない。TeamsコネクタのGraph呼び出し（HttpRequest）は標準接続のみで完結する。
- 実環境でのパッケージインポートは本調査では未検証である。確認できたのはパッケージ内JSON構造・参照整合性・ZIP再展開結果が公式手順および雛形と一致することのみであり、「インポートが成功する」ことそのものを保証するものではない。
- 以下の項目は実環境での確認が別途必要な「不確実」事項として明記している。
  - SharePoint保存後ファイルURL取得式における {Link} 波括弧キー表記の実際の動作
  - パッケージインポート時のconnectionName／creator.id／tenantIdの再マッピング挙動
  - インポート時のフローGUID新規採番の詳細動作
  - 添付ファイルのcontentUrl解析によるSharePoint本体取得（GetFileContentByPath）のパス解析の実際の成否

---

## 追加確認（2026-07-16・実働サンプル突合）

実働サンプル`create_meeting_list_sample_20260716105612.zip`（実環境で作成・動作実績のあるエクスポート。`sample_export_analysis.md`（同フォルダー）「追加サンプル」章参照）との突合、および本プロジェクトの実環境作業で得られた事実。区分（公式確認／実サンプル確認／実環境実体験）を各項目に明記する。公式資料で確認していないものは公式確認と書かない。

1. **`type: OpenApiConnection`の出力は封筒`{statusCode, headers, body}`**であり、フィールド参照は`body('X')?['f']`または`outputs('X')?['body/f']`が正しい形。`outputs('X')?['f']`（bodyを経由しない直接参照）は常に`null`になる。
   根拠: 実働サンプルのParseJsonスキーマが同じ封筒形を明示的に定義していたこと、および当方定義内で同種の参照が一部`outputs(...)?['ItemId']`等の直接参照になっていた内部不整合の実例（v6で修正）。
   区分: **実サンプル確認**
2. **SetVariable（変数を設定する）は、更新対象の変数自身を値の式の中で参照する構成（自己参照）を保存時に拒否する。** 配列のunion累積・文字列のconcat累積・カウンターの`add(自身,1)`はいずれも同じ理由で保存できない。
   根拠: 本プロジェクトの実環境で実際に発生した保存エラー。エラーコード`WorkflowRunActionInputsInvalidProperty`、メッセージ「Self reference is not supported when updating the value of variable '...'」。v4で該当3箇所を全て除去した。
   区分: **実環境実体験**
3. **TeamsチャネルID（`19:...@thread.tacv2`形式。`:` `@`を含む）は、Graph呼び出しのURLに埋め込む前にURLエンコードが必要**。`uriComponent()`関数によるエンコードで対応できる。
   根拠: 実働サンプルが`%3A`/`%40`エンコード済みのURLをハードコードして動作しており、メッセージIDについても`uriComponent()`で動的エンコードしていた実例。
   区分: **実サンプル確認**
4. **パッケージの`connectionReferences`には、認証情報の持たせ方が異なる2方式が実在する**: (a) `source="Embedded"` + `authentication="@parameters('$authentication')"`、(b) `source="Invoker"` + `authentication`=X-MS-APIM-Tokens復号式。どちらも正当なレガシーパッケージ形式であり、プロジェクト内で一貫させればよい。
   根拠: 2つの実エクスポート（雛形サンプルは(b)、実働サンプル`create_meeting_list_sample`は(a)）を直接比較して確認。
   区分: **実サンプル確認**

---

## 追加確認（2026-07-16・保存エラー調査）

実環境でv6のZIPを保存しようとした際に発生した`OpenApiOperationParameterValidationFailed`（`PostItem`の`item`欠落）エラーの原因調査、およびその修正（`PostItem`からSharePoint「HTTP要求を送信します」+ REST方式への置換）にあたって確認した内容。区分（実環境実体験／コミュニティ確認／実サンプル確認／公式確認／演繹）を各項目に明記する。公式資料で確認していないものは公式確認と書かない。

1. **SharePoint「項目の作成」(`PostItem`)は必須の動的ボディ`item`（`x-ms-dynamic-schema`）を持ち、「サイトのアドレス」「リスト」が式（`variables(...)`）の場合、保存時の検証がリストの列スキーマを解決できず`item`パラメータの欠落エラーになる。**
   根拠: 本プロジェクトの実環境で実際に発生した保存エラー（アクション`Create_Run_Log`、エラーコード`OpenApiOperationParameterValidationFailed`、メッセージ「The API operation 'PostItem' is missing required property 'item'.」）。加えて、tomriha.com（Power Automate解説ブログ）に「リストを事前に静的選択できない場合は汎用的な`Item`という単一フィールドしか使えなくなる」という趣旨の記述、Power Platform Community（フォーラム）にも「サイト/リストを動的にする構成では`Create item`ではなく`Send an HTTP request to SharePoint`を使う」という趣旨の投稿が確認できた（いずれも2026-07-16参照）。
   区分: **実環境実体験＋コミュニティ確認**
2. **「SharePoint に HTTP 要求を送信します」アクションのエクスポート形式（definition.json上のキー）は、`dataset`（サイトURL）／`parameters/method`／`parameters/uri`／`parameters/headers`（オブジェクト）／`parameters/body`という構造になる。**
   根拠: 雛形（実エクスポート）に含まれるGET呼び出しの実サンプルで`dataset`・`parameters/method`・`parameters/uri`のキー形式を確認済み。`parameters/headers`がオブジェクト形式であることはTech Community記事の実例で確認した。`parameters/body`キー自体は、雛形サンプルにPOST（本文付き）の実例が無かったため、他パラメータの命名規則（`parameters/`接頭辞＋パラメータ名）からの**推定**であることを明記する。
   区分: **実サンプル確認（雛形のGET）＋Tech Community実例（headers）＋命名規則からの推定（body）**
3. **REST での項目作成は、リクエストヘッダーの`Accept`・`Content-Type`を両方とも`application/json;odata=nometadata`にすることで、本文に`__metadata`（アイテムの型情報）を含めない単純なJSONオブジェクトを送信できる。**
   根拠: learn.microsoft.com「Work with items using the Send an HTTP request to SharePoint action」に、nometadata形式でのCRUD操作についての記載を確認した。vrdmn.com（コミュニティブログ）の実装例でも、Accept/Content-Typeを`nometadata`にしたうえで`__metadata`なしの単純なJSONボディでPOSTしている実例を確認した（いずれも2026-07-16参照）。テナント設定によっては`__metadata`指定を別途要求される可能性があり、その場合のフォールバック（`ListItemEntityTypeFullName`取得）は実装手順書15.6節に記載している。
   区分: **公式確認（learn.microsoft.com）＋コミュニティ実装例（vrdmn.com）**
4. **`GetItems`（複数の項目の取得）・`GetFileItem`（ファイルのプロパティの取得）・`CreateFile`（ファイルの作成）・`GetFileContentByPath`（ファイルコンテンツの取得・パス使用）は、`PostItem`のような必須の動的ボディを持たないため、`dataset`/`table`が式のままでも保存時検証を通過すると考えられる。**
   根拠: 各operationIdのswagger定義上、`x-ms-dynamic-schema`が`item`パラメータにのみ付与されており、他アクションの入力パラメータは固定スキーマの単純な型であることからの**演繹**。本プロジェクトでこれらのアクションを式のままで実環境保存できることを直接検証した実績はない。
   区分: **swagger構造からの演繹（直接の実環境実績なし）**
