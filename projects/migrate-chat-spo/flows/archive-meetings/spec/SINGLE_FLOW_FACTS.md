# 単一フロー事実シート（PA_Migrate_Teams_Meeting_Archive_To_SPO）

これは今回の単一フロー成果物の正典。名称・式はここと生成済み definition.json から取り、勝手に変えない。
- 生成済み定義: `../source/package/Microsoft.Flow/flows/fcca0e31-6d8b-40a8-8d63-2441c979a2c7/definition.json`（フロー本体）
- アクション構造の全体アウトライン: `../validation/action_outline.txt`（実行順・ネスト・operationId付き）
- 最終ZIP: `../release/` 配下の日時付きZIP

## パッケージ（レガシー形式）
```
manifest.json (ルート)
Microsoft.Flow/flows/manifest.json
Microsoft.Flow/flows/fcca0e31-6d8b-40a8-8d63-2441c979a2c7/definition.json
Microsoft.Flow/flows/fcca0e31-6d8b-40a8-8d63-2441c979a2c7/apisMap.json
Microsoft.Flow/flows/fcca0e31-6d8b-40a8-8d63-2441c979a2c7/connectionsMap.json
```
- フロー表示名: 「Teams課内会議アーカイブ」 / 英語名(パッケージdisplayName): PA_Migrate_Teams_Meeting_Archive_To_SPO
- フローID(definition.json name): 2fe554b1-6ba6-4ce0-962c-07bde4bdb6ee（匿名の新規GUID）
- 種別: インスタントクラウドフロー / トリガー: manual（type=Request, kind=Button）
- フロー数: 1（子フローなし）

## トリガー入力（手動）
| 内部名 | 表示名 | 型 | 既定値 |
|---|---|---|---|
| LookbackDays | 取得対象日数 | number | 7 |
| DryRun | テスト実行 | boolean | true(Yes) |
| ForceReprocess | 処理済みファイルを再処理する | boolean | false(No) |
- 参照: `triggerBody()?['LookbackDays']` 等（手作業定義のため内部名＝この名前。UI組立時は自動採番になる点を注記）。
- 開始日時: `addDays(variables('varEndDateUtc'), sub(0, variables('varLookbackDays')))`、終了=utcNow()。

## 使用コネクタ（3種・すべて標準）と operationId
| コネクタ | apiId | operationId（使用） |
|---|---|---|
| Microsoft Teams | shared_teams | HttpRequest（Graph送信。messages/replies） |
| SharePoint | shared_sharepointonline | GetItems / CreateFile / GetFileItem / GetFileContentByPath / PostItem |
| Content Conversion | shared_conversionservice | HtmlToText（パラメータキー=Content） |
- アクションは `type:"OpenApiConnection"`、`inputs.host={apiId,connectionName,operationId}`、`authentication`=Raw(X-MS-APIM-Tokens)。
- Teams「Send a Microsoft Graph HTTP request」で `GET /teams/{teamId}/channels/{channelId}/messages?$top=50` と `.../messages/{id}/replies?$top=50` を @odata.nextLink ページング（Do until, `empty(varNextLink)`終了）。

## 内部変数（すべてトップレベルで初期化。Initialize変数はScope内不可のためルート配置）
varRunId, varLookbackDays(int), varEndDateUtc, varStartDateUtc, varTeamId, varChannelId, varSiteAddress, varLibrary, varDestinationPath, varLedgerList, varMessagesArray(array), varNextLink, varRepliesArray(array), varReplyNextLink, varAttachmentCandidates(array), varMeetingAttachments(array), varMeetings(array), varSortedMeetings(array), varDocumentHtml, varDocHtmlParts(array), varMeetingIndex(int), varSavedCount(int), varSkippedCount(int), varArchiveUrl, varRunStatus, varErrorMessage

## 定数（初期化値。手順書で書き換え箇所として明示）
- varTeamId=a7ac0c68-87ba-4613-8960-13660f0f5f56
- varChannelId=19:53e5d619e45b4fda8d0dc7f2858a9d64@thread.tacv2
- varSiteAddress=https://metijapan.sharepoint.com/sites/mROOM_240600018
- varLibrary=Shared Documents
- varDestinationPath=123_伝送システム/00_共用フォルダ/60_庶務担当/99_過去の課内会議
- varLedgerList=MeetingArchiveLedger

## Scope構成（実行順。詳細は action_outline.txt）
ルート初期化（Initialize_*）→ Scope_10_Get_Channel_Messages → Scope_20_Process_Meetings（Filter_Messages_By_Period → Process_Each_Parent_Message: 会議情報/返信ページング/添付抽出/Scope_30_Save_Attachments/正規化Append）→ Scope_40_Sort_Meetings（`sort(varMeetings,'sortKey')`）→ Scope_50_Build_Word_Content（ヘッダ→会議ごとescape/改ページ/添付リンク→フッタ→join）→ Scope_60_Create_Archive_File（.doc作成→プロパティ取得→URL）→ Scope_70_Write_Run_Log → Scope_90_Catch（runAfter Scope_70 Failed/Skipped/TimedOut）→ Scope_99_Finally。
- 全Foreach/Untilは並列オフ（`runtimeConfiguration.concurrency.repetitions=1`）。
- 会議データモデル: {meetingDate, postedDateTimeJst, messageId, author, organizer, bodyText, teamsMessageUrl, attachments[], sortKey}。attachments要素={originalName, savedName, savedFileUrl, status(Saved/Skipped/Failed)}。

## 主要な式（definition.jsonと一致）
- 投稿者: `if(empty(trim(coalesce(items('Process_Each_Parent_Message')?['from']?['user']?['displayName'],''))),'不明',trim(coalesce(...)))`
- 主催者: 定数 '不明'（§10.3：投稿者を無条件に主催者にしない。会議情報から取得可能なら差し替える旨を注記）
- 会議日付: `formatDateTime(convertFromUtc(...createdDateTime,'Tokyo Standard Time'),'yyyy-MM-dd')`
- SortKey: `concat(formatDateTime(convertFromUtc(...),'yyyyMMddHHmmss'),'_',...['id'])`
- ソート: `sort(variables('varMeetings'),'sortKey')`（昇順・実在確認済）
- 本文変換: Content Conversion HtmlToText（Content=body.content）
- HTMLエスケープ: &→< →>→"→' の順（Compose5分割 Escape_*）。改行→<br>。
- 改ページ: `varMeetingIndex>0` のとき `<div style="page-break-before: always;"></div>`
- ファイル名: `yyyyMMdd_元名`、禁止文字 " * : < > ? / \ | を Replace_Invalid_* で _ 置換、末尾空白/ピリオド除去、拡張子保持、長さ>100短縮、null時'file'
- 冪等キー: `MessageId(_ReplyId)_AttachmentId`。台帳GetItems($filter IdempotencyKey/Status)で既存Saved確認、ForceReprocess=falseなら再利用(Skipped)
- 保存後URL: `outputs('Get_Saved_File_Properties')?['{Link}']`（要SharePointコネクタ確認）
- .doc名: `課内会議総括_yyyyMMdd_HHmmss.doc`

## SharePointリスト（手順書で作成を案内。フロー内では table にリスト名を仮置き＝インポート後に実リスト選択が必要）
- MeetingArchiveLedger（処理台帳）: Title, IdempotencyKey, RunId, MessageId, ReplyId, AttachmentId, OriginalFileName, SavedFileName, SavedFileUrl, Status, ErrorMessage, ProcessedDateTimeUtc
- MeetingArchiveRunLog（実行ログ）: Title, RunId, FlowName, Level, ErrorMessage, MeetingCount, SavedCount, SkippedCount, ArchiveUrl, Status, OccurredDateTimeUtc

## 匿名化（実施済み）
- 雛形のメール iihoshi-yohei@jpo.go.jp、creator.id 641b02f0…、tenantId、接続GUID c101e3db…/054920e5… は新パッケージに含めない。
- connectionReferences.connectionName は匿名GUID。metadata.creator={}（空）。details.creator="N/A"。
- 認証情報・トークンは埋め込まない（authentication は X-MS-APIM-Tokens 参照式のみ＝雛形と同一の標準形。秘密情報ではない）。

## インポート後の再設定ポイント（要実環境確認。手順書/インポート手順書/検証レポートに明記）
1. 3コネクタ（Teams / SharePoint / Content Conversion）の接続選択。
2. SharePoint系アクションの「サイトのアドレス」「リスト/ライブラリ」を実物に再選択（table にリスト名を仮置きのため、GetItems/PostItem/GetFileItem のリスト/ライブラリを選び直す）。
3. varTeamId/varChannelId/varSiteAddress/varDestinationPath/varLedgerList の値確認。
4. `{Link}` でのファイルURL取得可否（取得不能時は {FullPath}+サイトから構築、スラッシュ非エンコード）。
5. 添付 contentUrl→本体取得（GetFileContentByPath のパス解析）。取得不能はStatus=Failedで継続。
6. .doc のWord形式警告可能性（→.html代替）。
7. 手動トリガー入力の内部名（UI組立時は自動採番）。
- **実環境インポートは未検証**（構造/JSON/ZIP再展開のみ検証済み）。「インポート成功済み」とは書かない。

## 検証結果（package_validation_report.txt / official_reference_findings.md に反映）
- 全JSON(5ファイル)パースOK、runAfter参照はすべて同階層に存在、InitializeVariableは全てトップレベル、参照変数26=初期化26で欠落なし、body/outputs参照先すべて実在、operationIdは実在7種のみ、ユーザー固有情報の混入なし、トリガーは manual 1つのみ、フロー1つ、ZIP再展開OK・雛形と同一構造・__MACOSX/.DS_Store無し。

## 修正反映（v2・定義更新済み。TXT/手順書はこのv2に合わせる）
定義レビューで見つかった3点を修正済み（build/definition.json はv2）:
1. **DryRun時は総括.docを作成しない**: Scope_60 に Condition_DryRun_Archive を追加。
   DryRun=true → Set_ArchiveUrl_DryRun（varArchiveUrl='(DryRun: 総括Wordファイルは作成していません…)'、ファイル未作成で本番フォルダを汚さない）。
   DryRun=false → Create_Archive_Document→Get_Saved_Archive_Properties→Set_ArchiveUrl。
2. **添付1件失敗で全体を止めない＋Status=Failed記録**: Process_Each_Attachment の実保存ブランチを再構成。
   Scope_Save_File（危険操作: Get_Source_File_Content/Create_Attachment_File/Get_Saved_File_Properties）の
   Failed/TimedOut を後続ハンドラで吸収して継続:
   - 成功時: Create_Ledger_Item(Status=Saved)→Append_Saved_Meeting_Attachment(status=Saved)→Increment_SavedCount
   - 失敗時: Append_Failed_Meeting_Attachment(status=Failed,url='')→Create_Ledger_Item_Failed(Status=Failed,ErrorMessage)→Increment_FailedCount
   新変数 **varFailedCount(int,0)** を追加（合計27変数）。RunLog/Finallyに FailedCount 追加。
3. **Word添付リンク判定を savedFileUrl 非空に変更**: Condition_Attachment_Saved の条件を
   `length(coalesce(item()?['savedFileUrl'],''))>0` に変更。URLがあれば（Saved も 再利用Skipped も）リンク表示。
   URL無しは status=Failed→「（保存失敗）」、それ以外（DryRun等）→「（テスト実行のため未保存）」。
- 添付結果オブジェクト status: Saved / Skipped(再利用・既存URLあり) / Skipped(DryRun・URL無) / Failed(URL無)。
- MeetingArchiveRunLog に **FailedCount(数値)** 列を追加（Title/RunId/FlowName/Level/ErrorMessage/MeetingCount/SavedCount/SkippedCount/FailedCount/ArchiveUrl/Status/OccurredDateTimeUtc）。
- 総アクション数 **129**（v1の123から+6。重複名 Set_ReplyNextLink→Set_ReplyNextLink_First 分離で+1、機械カウント上128→129に確定）。変数27。最新のアクション順は action_outline.txt（再生成済み）。

## 修正反映（v4・SetVariable自己参照の全面除去。保存エラー対応）
実環境インポート後の保存で `WorkflowRunActionInputsInvalidProperty`（Set_MessagesArray の自己参照）が発生。
Power Automate は SetVariable で更新対象変数自身を入力式から参照する構成を許可しないため、全3件を除去した。

**除去した自己参照SetVariable（3件）→ 置換後:**
1. `Set_MessagesArray`（union(varMessagesArray自身, 新ページ)）→ **削除**。代替: Do_Until_Messages_Paging 内に
   `Process_Retrieved_Messages`（Apply to each, 入力=`coalesce(body('Get_Channel_Messages')?['value'], json('[]'))`, 並列オフ）
   ＋ `Append_Message_To_MessagesArray`（AppendToArrayVariable, varMessagesArray, 値=`item()`）。
   `Set_NextLink` の runAfter は Process_Retrieved_Messages に変更。
2. `Set_RepliesArray`（union自己参照）→ **削除**。代替: Do_Until_Replies_Paging 内に
   `Process_Retrieved_Replies`（Apply to each, 入力=`coalesce(body('Get_Message_Replies')?['value'], json('[]'))`, 並列オフ）
   ＋ `Append_Reply_To_RepliesArray`（AppendToArrayVariable, varRepliesArray, 値=`item()`）。
   `Set_ReplyNextLink` の runAfter は Process_Retrieved_Replies に変更。
   ※`Set_RepliesArray_Reset`（varRepliesArray=json('[]') の代入）は自己参照ではないため存続。
3. `Append_Reply_Attachment_Candidates`（名前はAppendだが実体はSetVariable+union自己参照）→ **削除**。代替:
   Process_Each_Reply 内に `Process_Each_Reply_Attachment`（Apply to each, 入力=`body('Select_Reply_Attachments')`, 並列オフ）
   ＋ `Append_Reply_Attachment_Candidate`（AppendToArrayVariable, varAttachmentCandidates, 値=`item()`）。

**HTML連結の方式変更（§4.2準拠）:**
- varDocHtmlParts（配列）＋ join() 方式を廃止 → varDocumentHtml へ **AppendToStringVariable** で直接連結。
- `Set_DocumentHtml_Header`→`Append_DocumentHtml_Header` に改名（AppendToStringVariable化）。
- `Append_Page_Break` / `Append_Meeting_Header_Html` / `Append_Attachment_Html` / `Append_Attachment_Failed_Html` /
  `Append_No_Attachments_Html` / `Append_DocumentHtml_Footer` はすべて AppendToStringVariable（varDocumentHtml）。
- `Set_DocumentHtml`（join）と `Initialize_DocHtmlParts` は**削除**。変数 27→**26**（varDocHtmlParts廃止）。

**LookbackDays安全化（§8）:**
- ルート先頭に `Compose_EffectiveLookbackDays`（Compose）を追加:
  `@if(greater(int(coalesce(triggerBody()?['LookbackDays'], 0)), 0), int(coalesce(triggerBody()?['LookbackDays'], 7)), 7)`
  （null/未入力→7、0以下→7、正の整数のみ採用。730超の上限は設けず手順書で注意喚起）
- `Initialize_LookbackDays` の値は `@outputs('Compose_EffectiveLookbackDays')` に変更。初期化チェーンの先頭は Compose の後。

**ネストForeach入力の明確化:**
- `Apply_To_Each_Saved_Attachment` の入力を `coalesce(items('Apply_To_Each_Sorted_Meeting')?['attachments'], json('[]'))` に変更
  （外側ループ項目の明示参照。item() の曖昧さ排除）。

## 修正反映（v5・Opus監査指摘＋実働サンプル準拠の堅牢化）
実働サンプル `create_meeting_list_sample_20260716105612.zip`（実環境で作成・動作実績あり。参照展開先
`create_meeting_list_sample_ref/`、整形済み定義は `../../../../../references/extracted/sample2_definition_pretty.json`）を参考に反映:
1. **Graph URLのuriComponent化**: チャネルID（`19:...@thread.tacv2` は ':' '@' を含む）と親メッセージIDを
   `uriComponent()` でエンコード。`Set_NextLink_First`＝channelId、`Set_ReplyNextLink_First`＝channelId＋messageId
   （計3箇所）。実働サンプルは %3A/%40 エンコード済みURL＋uriComponent(メッセージID) で動作している。
   teamId はGUIDのためエンコード不要。@odata.nextLink はGraphが返す完全URLをそのまま使用。
2. **曜日式の堅牢化**（Opus監査指摘）: `json('["日",...]')[dayOfWeek(...)]`（計算インデックス角括弧）→
   `substring('日月火水木金土', dayOfWeek(item()?['meetingDate']), 1)` に変更（Compose_Meeting_Header_Html内）。
3. **runAfterの明示化**（Opus監査指摘）: コンテナ起点4アクション（Get_Channel_Messages/Get_Message_Replies/
   Select_Reply_Attachments/Get_Source_File_Content）に `"runAfter": {}` を明示（PA標準エクスポート形式）。

**実働サンプルから移植しなかったもの（設計バグ・劣位のため）:**
- `SetVar_ChildAttachments_Append` の `union(createArray(item()), ...)` を毎回SetVariable → 累積でなく上書き＋
  返信オブジェクト自体を添付配列へ混入する二重バグ。当方は Foreach＋AppendToArrayVariable で正しく累積。
- ページング無し（$top=50の1ページのみ）→ 当方は Do until＋nextLink ページングを維持。
- 封筒形（statusCode/headers/body）のParseJsonスキーマ → 当方は式参照のためParseJson不要
  （サンプルの動作実績から body('Teams HttpRequest') はGraph応答JSONそのものと確認）。
- 値式末尾の `\n` 混入、ハードコードURL/リストGUID、空トリガーschema。
- 認証形式: サンプルは source=Embedded＋@parameters('$authentication')、当方は雛形due来の
  source=Invoker＋X-MS-APIM-Tokens 参照式を維持（v3が実環境インポートに成功した実績を優先）。

## 修正反映（v10・添付保存の全件失敗への対処。2026-07-18）
**v9実環境実行の結果**: フローはエンドツーエンド完走（封じ込め・台帳Failed記録・エラーログ201が全て機能）。
しかし**全添付が Status=Failed**（例: ６Ｇと７Ｇ.pptx）。新実行証跡（run-evidence/Get_Channel_Messages.txt
＝親50件）の分析で、失敗添付のcontentUrlは正しい形（pjteam/Shared Documents配下・生URL）と確認
→ v9のサイト/パス導出は正しい値を生成する → **失敗は保存側**が濃厚：
(a) CreateFileは中間フォルダを自動作成しない（mROOMの保存先4階層が未作成なら全件失敗）
(b) **GetFileItem の table="Shared Documents" はライブラリの表示名/GUIDでなくURLセグメント**
    （日本語サイトの表示名は「ドキュメント」）→ 名前解決不能＝全件失敗の最有力候補。
    ※この場合**ファイル自体は保存先に出来ている**可能性→再実行時の同名409に注意（残骸確認を手順書に明記）
また新証跡から **Graphは%エンコード済みcontentUrlも返す**（.aspx実例）→ エンコード文書が
現行フィルタを通らず黙って除外される潜在バグも発見。

**v10修正（4本柱＋2堅牢化）**:
1. **Scope_05_Ensure_Destination_Folder 新設**（ルート・初期化後）: DryRun=いいえ のときのみ、
   REST POST _api/web/folders（SP.Folder・verbose）で保存先を1階層ずつ作成（L1〜L4、各runAfter
   [Succeeded,Failed]で既存エラー許容継続）→ GET GetFolderByServerRelativeUrl で実在検証。
   検証失敗＝パス/権限の問題を**実行早期に明確な形で失敗**させる（全添付が黙々とFailedを防ぐ）。
   ServerRelativeUrlは**フルサーバー相対**（`concat(uriPath(varSiteAddress),'/',varLibrary,'/',
   join(take(split(varDestinationPath,'/'),N),'/'))`）。保存先パスは最大4階層対応。
2. **エンコードURL正規化**: Filter_File_Attachments に `/Shared%20Documents/` 含有をor追加。
   Scope_Save_File 先頭に `Compose_Source_Url`（%20版含有時のみ decodeUriComponent）を追加し、
   Site/Path導出は正規化URLから（誤デコード非発火は判定の限定で担保）。
3. **GetFileItem（{Link}）全廃**: 保存後URLを既知の値から決定的に構築
   `replace(concat(varSiteAddress,'/',varLibrary,'/',varDestinationPath,'/',SavedName),' ','%20')`
   （CreateFile成功＝そのパス・名前で作成された、の直接証明。長年の要実環境確認事項{Link}自体を消した）。
   Compose_Saved_File_Url は Scope_Save_File の**前**（失敗時も参照可能）。総括docの Set_ArchiveUrl も同式。
4. **自己診断エラーメッセージ**: 失敗時の台帳ErrorMessageに元contentUrl（生のitems()参照＝
   Compose失敗時もハンドラが壊れない）と保存先を埋め込む。再発時は台帳の1行で原因特定可能。
5. ファイル名サニタイズに **#・%** を追加（Replace_Invalid_Hash/Percent。決定的URLの保証を完全化）。
6. 検証スクリプトに「GetFileItem存在→エラー」「{Link}残存→エラー」を恒久追加。

**v10集計**: 総アクション **148**（v9の139 +Scope_05系7 +Compose_Source_Url +Compose_Saved_File_Url
+サニタイズ2 −GetFileItem2）。変数28不変。ネスト深さ8維持。0エラー0警告。互換突合=完全互換。
release: `PA_Migrate_Teams_Meeting_Archive_To_SPO_20260718012104.zip`
**実環境確認ポイント**: (1)Verify_Destination_Folder成功 (2)台帳にSaved行とクリック可能なSavedFileUrl
(3)まだFailedなら ErrorMessage の「元URL=/保存先=」で一意に原因特定 (4)初回実行前に保存先の残骸確認（409対策）

## 修正反映（v9・実行時404の根本修正＋添付有無の明示分岐。2026-07-17）
**実環境での初実行結果（重要な進展）**: v8はインポート・保存・実行・RESTログ書き込み（201。
pjteamのMeetingArchiveRunLogにId=1）まで到達。実行時に Get_Source_File_Content が
**404 File not found** で失敗（ユーザー提供の実行出力3ファイルで確認）。

**404の根本原因（実データで確定）**:
- 実際の添付 contentUrl: `https://metijapan.sharepoint.com/teams/pjteam_220400119/Shared Documents/03_課内会議/…`
  （Teamsチャネル添付は**チームのサイト**の Shared Documents 配下。生URL＝非エンコードで返る）
- 旧実装: dataset=varSiteAddress（mROOM=ファイル保存先）＋サイト接頭辞付きpath → **別サイト参照で404**。

**v9修正（3点）**:
1. **サイト・パスを contentUrl から導出**（設定不要・汎用）: Scope_Save_File 先頭に
   `Compose_Source_Site`＝`substring(cu, 0, indexOf(cu, '/Shared Documents/'))`、
   `Compose_Source_Path`＝`replace(substring(cu, indexOf(cu, '/Shared Documents/')), '%20', ' ')` を追加。
   Get_Source_File_Content は dataset=@outputs('Compose_Source_Site')、path=@outputs('Compose_Source_Path')。
   実contentUrlでのシミュレーション: dataset=チームサイトURL／path=/Shared Documents/03_課内会議/ファイル名 ✓
2. **Filter_File_Attachments 強化**: 条件に `contains(contentUrl, '/Shared Documents/')` を追加。
   チームサイトのライブラリに実在するファイル添付のみ収集対象（外部リンク・タブ参照等は最初から除外
   ＝不要なエラーの根絶。ユーザー提案の趣旨）。
3. **添付有無の明示分岐（ユーザー提案）**: `Scope_30_Save_Attachments`（Scope）を
   **`Condition_Has_File_Attachments`（If: greater(length(body('Filter_File_Attachments')), 0)）に置換**。
   添付がある場合のみ Process_Each_Attachment を実行。※Scopeのまま外側にIfを足すと
   ネスト深さ上限8を超えるため「Scope自体をIfに置き換え」で深さを維持（重要な設計判断）。
   後続 Compose_SortKey の runAfter は Condition_Has_File_Attachments へ。

**v9集計**: 総アクション **139**（v8の137＋Compose_Source_Site/Path。Scope→If置換は増減なし）。
変数28不変。0エラー0警告。実データ（返信9件中8件添付なし・1件に6添付）とも整合。
**残る確認事項**: v8実行が「全体失敗」（Catch発火）になった経路——Scope_Save_File失敗は
ハンドラで吸収される設計のため、Create_Ledger_Item_Failed 等の失敗が疑われるが実行履歴が必要。
v9では404の発生源自体が消えるため、再実行で解消される見込み。再発時は失敗アクション名の確認を依頼。

## 修正反映（v8・リスト操作サイトの分離。ユーザー決定 2026-07-17）
台帳・実行ログのリストを **pjteam_220400119** に作成することがユーザー決定された
（リスト自動作成フロー CreateMeetingArchiveLists の構築に伴う。AskUserQuestionで確認済み）。
varSiteAddress（mROOM_240600018）はファイル保存（添付・総括doc）にも使われ、保存先フォルダは
mROOM側に実在するため、**リスト操作のみを分離**:
1. 新変数 `varListSiteAddress`（初期値 `https://metijapan.sharepoint.com/teams/pjteam_220400119`）を追加。
   変数 27→**28**、総アクション 136→**137**（Initialize_ListSiteAddress追加）。
2. `Get_Ledger_Existing` の dataset → `@variables('varListSiteAddress')`。
3. REST4アクション（Create_Ledger_Item / Create_Ledger_Item_Failed / Create_Run_Log / Create_Error_Log）の
   静的 dataset（SITE_URL_STATIC）→ pjteam URL。
4. ファイル保存系（Get_Source_File_Content / Create_Attachment_File / Get_Saved_File_Properties /
   Create_Archive_Document / Get_Saved_Archive_Properties）は varSiteAddress（mROOM）のまま。
検証: 0エラー0警告。初期化28=参照28（「未参照の初期化変数」検査を検証スクリプトへ恒久追加——
初回ビルドで Get_Ledger_Existing の付け替え漏れをこの検査観点で検出・修正した）。

## 関連: リスト自動作成フロー（CreateMeetingArchiveLists・別パッケージ）
- 成果物: ../../provision-archive-lists/release/CreateMeetingArchiveLists_*.zip（レガシー5ファイル・1フロー）
- 参照フロー CreateKnowledgeList_20260716161116.zip（実働）に忠実: Embedded接続参照＋$authentication、
  SharePoint HttpRequest（REST）のみ、完全直列、変数不使用（全てCompose）
- 2リスト（MeetingArchiveLedger 11列 / MeetingArchiveRunLog 11列）を作成・列構成・既定ビュー再構築
- 列型: Text(255)基本／SavedFileUrl・ArchiveUrl・ErrorMessage=**Note(RichText=FALSE, NumLines=6)**
  （URL・エラー文の255字超対策。ハイパーリンク型不可の制約はNoteでも満たす）／件数4列=Number／日時2列=Text
- 冪等化（参照フローからの改善）: 列ごとに Filter（InternalName一致）→If（length(body)==0のときのみ
  createFieldAsXml）。リスト作成は failed でも GetByTitle に[Succeeded,Skipped,Failed,TimedOut]で継続
- ビュー: removeAllViewFields→LinkTitle→カスタム列（表示名FilterでInternalName解決・フォールバック付き）
  →Author/Editor/Created/Modified。Attachmentsは追加しない（添付利用実績なし）
- 実施しない（根拠あり）: EnableAttachments／Title Required解除（Titleは常時書き込み）／Lookup列（RunId文字列相関のみ）
- GUID: 資産GUID 7c3e50b2-…（manifest resourcesキー=フォルダ名=assetPathsの3点一致）、
  フローGUID d94a1b6e-…、API/接続リソースGUIDは参照フロー値を維持（apisMap/connectionsMapと整合）
- 総アクション156（トリガー除く。If内22含む）。静的検証0エラー（SchemaXml 22本XMLパース・型純度・
  DisplayName==Name・If式length形式・Ledger/RunLog取り違え0・Knowledge残存0・ネスト@0・封筒参照0）

## 修正反映（v7・最終。PostItem保存エラーの根本修正）
実環境でv6の保存時に3件目のエラーが発生:
「OpenApiOperationParameterValidationFailed: Input parameter 'item' validation failed in workflow
 operation 'Create_Run_Log': The API operation 'PostItem' is missing required property 'item'.」
**原因（Sonnet Web調査＋Opus監査で確定・確度高）**: PostItem は必須の動的ボディ `item`
（x-ms-dynamic-schema）を持つ。dataset/table が式（@variables）だと列スキーマを解決できず、
フラット化キー item/Title 等を `item` に束ねられない→「item 欠落」で保存失敗。
実働サンプルの PostItem は dataset/table とも静的リテラルでのみ保存実績。
保存時検証は1件ずつしか報告しないため、**同型のPostItem×4がすべて該当**
（Create_Ledger_Item / Create_Ledger_Item_Failed / Create_Run_Log / Create_Error_Log）。

**修正（PostItem×4 → SharePoint「HTTP要求を送信」(operationId=HttpRequest)＋REST）**:
- 各PostItemの直前に Compose でボディオブジェクトを構築（item/接頭辞なしの内部列名。
  数値・日時は式のまま→string()でJSON化時に正しい型で出力）:
  Compose_Ledger_Body / Compose_LedgerFailed_Body / Compose_RunLog_Body / Compose_ErrorLog_Body
- REST形（雛形tmpの実エクスポートでキー形式確認済み）:
  dataset=**静的リテラル**（サイトURL。雛形で保存実績のある唯一の形）、
  parameters/method="POST"、
  parameters/uri=`@concat('_api/web/lists/getbytitle(''', variables('varLedgerList|varRunLogList'), ''')/items')`
  （URI は動的スキーマ非対象の単純文字列のため式でも保存安全＝リスト名の変数化を維持）、
  parameters/headers={"Accept":"application/json;odata=nometadata","Content-Type":"application/json;odata=nometadata"}
  （nometadata両指定で __metadata 不要の単純JSONボディ。learn.microsoft.com確認）、
  parameters/body=`@string(outputs('Compose_X_Body'))`（エスケープ安全）
- アクション名は同名維持（Create_Ledger_Item等）→後続runAfterの名前参照は不変。
- **応答参照の変更ゼロ**（4アクションの出力を参照する箇所は元々存在しない）。
- **他の9アクションは無改修**: GetItems/GetFileItem×2/CreateFile×2/GetFileContentByPath/
  Teams HttpRequest×2/HtmlToText は必須の動的ボディを持たず、式のdataset/tableでも
  「必須パラメータの存在チェック」で保存検証を通る（Opus監査で全13アクションを一斉判定）。
- 検証スクリプトに「PostItem存在→エラー」「SharePoint HttpRequestの必須キー検査」を恒久追加。

**v7集計（機械検証済み・0エラー0警告）**: 総アクション **136**（v6の132＋Compose×4）。変数27不変。
operationId は CreateFile/GetFileContentByPath/GetFileItem/GetItems/HtmlToText/HttpRequest の6種
（PostItem廃止）。SetVariable 13（自己参照0）／AppendToArray 8／AppendToString 7／Increment 5。

**残存注意（実行時。保存はブロックしない）**:
- テナント設定によりRESTのPOSTで __metadata 型指定を要求される可能性（その場合
  `_api/web/lists/getbytitle('リスト名')?$select=ListItemEntityTypeFullName` で型名取得し
  ボディへ "__metadata":{"type":"SP.Data.xxxListItem"} を追加）。
- SavedFileUrl/ArchiveUrl 列が「ハイパーリンク」型の場合はRESTでは {"Url":...} オブジェクトが必要
  →**単一行テキスト列で作成すること**（手順書に明記）。
- 4つのREST化アクションの dataset は静的リテラルのため、サイト変更時は4アクションの編集が必要。

## 修正反映（v6・最終。Opus設計監査で検出した重大バグ修正＋任意推奨2件）
Opus級の設計監査（実働サンプル突合・8観点）が(A)〜(F)の暫定判断を全支持した上で、**必須修正1件**を検出:
1. **【重大】コネクタ出力参照の body/ パス欠落（5箇所）**: OpenApiConnection の outputs('X') は
   封筒 {statusCode, headers, body} を返すため、outputs('X')?['ItemId'] や ?['{Link}'] は**常にnull**。
   非DryRun本番経路で全添付が Failed 化し、総括docのURL取得も失敗する潜在バグだった
   （DryRun=true 既定では発火しないため未発見だった）。修正:
   - Get_Saved_File_Properties.id = `@body('Create_Attachment_File')?['ItemId']`
   - Create_Ledger_Item の SavedFileUrl = `@body('Get_Saved_File_Properties')?['{Link}']`
   - Append_Saved_Meeting_Attachment の savedFileUrl = 同上
   - Get_Saved_Archive_Properties.id = `@body('Create_Archive_Document')?['ItemId']`
   - Set_ArchiveUrl = `@body('Get_Saved_Archive_Properties')?['{Link}']`
   根拠: 同一定義内で body('Get_Ledger_Existing')?['value'] は正しく使用（内部不整合＝取りこぼし）。
   実働サンプルの封筒形ParseJsonスキーマも outputs()=封筒 の証拠。
   検証スクリプトに「outputs(コネクタ)?[非body]→エラー」検査を恒久追加。
2. **RunLogリスト名の変数化**: varRunLogList（初期値 MeetingArchiveRunLog）を追加し、
   Create_Run_Log / Create_Error_Log の table を @variables('varRunLogList') に変更（再選択点の一元化）。
3. **添付hrefのエスケープ**: att_link_true の href 内URLを replace(url,'&','&amp;') でエスケープ。

**v6集計（機械検証済み・0エラー0警告）**: 総アクション **132**（v5の131 +Initialize_RunLogList）、
変数 **27**（varRunLogList追加）。SetVariable 13（自己参照0）／AppendToArray 8／AppendToString 7／
Increment 5／Foreach 8。コネクタ出力のbody/欠落 0件。

**Opus設計監査の主な支持事項（v6でも有効）:**
- body('Teams HttpRequest') はGraph応答そのもの（ParseJson不要）。
- 認証形式は Invoker＋X-MS-APIM-Tokens 維持（v3実環境インポート成功実績。parameters節の
  $authentication/$connections 宣言は未参照でも無害なボイラープレート）。
- uriComponent(channelId/messageId)・teamId生・nextLinkそのまま、はサンプルとバイト一致相当で正。
- Set_AttachmentCandidates_Parent は Do_Until_Replies_Paging 後・Process_Each_Reply 前に正しく配置
  （SetによるOverwriteが親ごとのリセットとして機能）。
- 残注意（要実環境確認のまま）: {Link} が直接ファイルURLか、contentUrl→GetFileContentByPath パス解析、
  SharePoint列は**ASCII英名で作成**し内部名一致が前提（非ASCIIだと OData__x..._ 化で不一致）、
  台帳/RunLogリストはインポート後に実物再選択。

**v4集計（機械検証済み・0エラー0警告）:**
- 総アクション数 **131**（v3の129 +Compose_EffectiveLookbackDays +Foreach×3 +Append×3 −SetVariable自己参照3 −Set_DocumentHtml −Initialize_DocHtmlParts = +2）
- 変数 **26**。SetVariable 13（自己参照0）／AppendToArrayVariable 8／AppendToStringVariable 7／Increment 5／Foreach 8
- 重複初期化0・未初期化参照0・runAfter不正0・接続参照3対3一致
- 注: union()による重複排除は廃止（Graphのページングは重複を返さない前提。冪等キー台帳で添付の重複保存は防止）
