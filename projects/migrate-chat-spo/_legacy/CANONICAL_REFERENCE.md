# 正典設計リファレンス（Teams課内会議アーカイブ / 標準Power Automateのみ）

これは全成果物（flow/*.txt と doc/*.md）の唯一の正典。名称・型・式は**この文書からコピーし、勝手に変えない**。

## 0. 前提と制約（毎ファイルの冒頭方針に反映）
- Azure/外部サーバー/独自コード/PAD/汎用HTTP/HTTP with Entra ID/カスタムコネクタ/アプリ登録/プレミアム文書生成/Open XML独自処理は**使用しない**。
- 使用コネクタは標準のみ: Microsoft Teams / SharePoint / Content Conversion / Office 365 Users / OneDrive for Business / Power Apps（子フロー戻り値用「Respond to a PowerApp or flow」）。
- 主目的: **過去2年分の一発取得**（明日の大規模システム移行に備える）。定期実行はオプション。
- Word生成: HTML文字列→SharePoint「ファイルの作成」で `.doc` 保存（Word互換HTML）。`.html` 代替も記載。Word Onlineテンプレートは**プレミアムのため不採用**。
- Teams取得: 標準Teamsコネクタ「Send a Microsoft Graph HTTP request」（標準・非プレミアム・アプリ登録不要）を主方式。簡易代替は「Get messages」＋「List replies of a channel message」。

## 1. グローバル定数（仕様書1.1由来）
| 名称 | 値 |
|---|---|
| TenantId | b6d94148-69a6-487a-8a69-88236d09260a |
| TeamId(groupId) | a7ac0c68-87ba-4613-8960-13660f0f5f56 |
| ChannelId | 19:53e5d619e45b4fda8d0dc7f2858a9d64@thread.tacv2 |
| ChannelName | 03_課内会議 |
| SiteUrl | https://metijapan.sharepoint.com/sites/mROOM_240600018 |
| Library | Shared Documents |
| DestinationPath(ライブラリ内フォルダ) | 123_伝送システム/00_共用フォルダ/60_庶務担当/99_過去の課内会議 |

## 2. 環境変数（Power Platformソリューション内。表示名で参照）
| 表示名 | 型 | 既定値 |
|---|---|---|
| envTeamId | テキスト | a7ac0c68-87ba-4613-8960-13660f0f5f56 |
| envChannelId | テキスト | 19:53e5d619e45b4fda8d0dc7f2858a9d64@thread.tacv2 |
| envTenantId | テキスト | b6d94148-69a6-487a-8a69-88236d09260a |
| envSiteUrl | テキスト | https://metijapan.sharepoint.com/sites/mROOM_240600018 |
| envLibrary | テキスト | Shared Documents |
| envDestinationPath | テキスト | 123_伝送システム/00_共用フォルダ/60_庶務担当/99_過去の課内会議 |
| envLookbackDays | 数値 | 730 |
| envLedgerListName | テキスト | MeetingArchiveLedger |
| envStagingListName | テキスト | MeetingArchiveStaging |
| envRunLogListName | テキスト | MeetingArchiveRunLog |
| envIncludeKeywords | テキスト | 課内会議 |
| envExcludeKeywords | テキスト | （空） |
- 注: 環境変数のスキーマ名にはソリューション発行者プレフィックス（例 `xxx_envTeamId`）が自動付与される。フロー内では表示名で選択。値は既定値でなく「現在の値」を設定してもよい（要ライセンス確認: 環境変数は通常標準）。

## 3. SharePointリスト（3つ）
### 3.1 MeetingArchiveLedger（処理台帳。冪等性）
| 列 | 型 |
|---|---|
| Title | 単一行（既定） |
| IdempotencyKey | 単一行 |
| RunId | 単一行 |
| MessageId | 単一行 |
| ReplyId | 単一行 |
| AttachmentId | 単一行 |
| OriginalFileName | 単一行 |
| SavedFileName | 単一行 |
| SavedFileUrl | 複数行（プレーン） |
| Status | 単一行（Saved/Failed/Skipped） |
| ErrorMessage | 複数行 |
| ProcessedDateTimeUtc | 単一行 |

### 3.2 MeetingArchiveStaging（会議一時保存。並び替え用）
| 列 | 型 |
|---|---|
| Title | 単一行（既定） |
| RunId | 単一行 |
| SortKey | 単一行（yyyyMMddHHmmss_メッセージID） |
| MeetingDate | 単一行（yyyy-MM-dd） |
| PostedDateTimeJst | 単一行 |
| MessageId | 単一行 |
| Author | 単一行 |
| Organizer | 単一行 |
| BodyText | 複数行（Html to text後のプレーン） |
| AttachmentsJson | 複数行（保存済み添付のJSON配列文字列） |
| TeamsMessageUrl | 複数行（Teams投稿webUrl。参照用。添付リンクには使わない） |

### 3.3 MeetingArchiveRunLog（実行ログ/エラーログ）
| 列 | 型 |
|---|---|
| Title | 単一行（既定） |
| RunId | 単一行 |
| FlowName | 単一行 |
| ActionName | 単一行 |
| MessageId | 単一行 |
| ReplyId | 単一行 |
| AttachmentId | 単一行 |
| Level | 単一行（Info/Warning/Error） |
| ErrorMessage | 複数行 |
| OccurredDateTimeUtc | 単一行 |
| MeetingCount | 数値 |
| SavedCount | 数値 |
| SkippedCount | 数値 |
| ArchiveUrl | 複数行 |

## 4. フロー一覧（統合型・5フロー）
| # | 表示名 | 種別 | トリガー | 呼出元→呼出先 |
|---|---|---|---|---|
| 1 | PA_Manual_Meeting_Archive_Start | インスタント（手動） | フローを手動でトリガーする | →3 |
| 2 | PA_Scheduled_Meeting_Archive_Start | スケジュール（オプション） | 繰り返し | →3 |
| 3 | PA_Meeting_Archive_Orchestrator | 子（呼出可能） | フローを手動でトリガーする（子フロー入力） | 1,2→3、3→4,5 |
| 4 | PA_Save_Meeting_Attachment | 子（呼出可能） | フローを手動でトリガーする | 3→4 |
| 5 | PA_Write_Run_Log | 子（呼出可能） | フローを手動でトリガーする | 3(,4)→5 |

- 子フロー呼出は「Run a Child Flow」アクション。子フローは同一ソリューション内で、トリガーは「フローを手動でトリガーする」、末尾に「Respond to a PowerApp or flow」で戻り値を返す。**要ライセンス確認**（子フロー機能）。
- TXTファイルとフローの対応: 04/06/07は独立フローではなく**オーケストレータ(3)内のScope/セクション**の詳細シート。00で明記。

## 5. フロー入出力（引数名・型を全ファイルで一致）
### 5.1 PA_Manual_Meeting_Archive_Start（手動トリガー入力）
| 引数 | 型 | 必須 | 既定 | 用途 |
|---|---|---|---|---|
| StartDateUtc | テキスト | 任意 | 空 | 取得開始UTC。空ならEndから逆算 |
| EndDateUtc | テキスト | 任意 | 空 | 取得終了UTC。空ならutcNow() |
| LookbackDays | 数値 | 任意 | 7 | 逆算日数（7=テスト, 730=本番2年） |
| DryRun | はい/いいえ | 任意 | はい | trueはWord/添付保存をスキップ |
| ForceReprocess | はい/いいえ | 任意 | いいえ | trueは台帳無視で再保存 |
- オーケストレータへ渡す: RunId, StartDateUtc, EndDateUtc, DryRun, ForceReprocess

### 5.2 PA_Scheduled_Meeting_Archive_Start
- 繰り返しトリガー（例: 週次）。最終成功日時は MeetingArchiveRunLog から取得（Level=Info最新）。StartDateUtc = addDays(lastSuccess, -2)。EndDateUtc = utcNow()。DryRun=いいえ, ForceReprocess=いいえ。→3呼出。

### 5.3 PA_Meeting_Archive_Orchestrator（子フロー入力）
| 引数 | 型 |
|---|---|
| RunId | テキスト |
| StartDateUtc | テキスト |
| EndDateUtc | テキスト |
| DryRun | はい/いいえ |
| ForceReprocess | はい/いいえ |
- 戻り値（Respond to a PowerApp or flow）: Status(テキスト), MeetingCount(数値), SavedCount(数値), SkippedCount(数値), ArchiveUrl(テキスト), ErrorMessage(テキスト)

### 5.4 PA_Save_Meeting_Attachment（子フロー入力）
| 引数 | 型 |
|---|---|
| RunId | テキスト |
| MessageId | テキスト |
| ReplyId | テキスト |
| AttachmentId | テキスト |
| OriginalFileName | テキスト |
| ContentUrl | テキスト |
| MeetingDate | テキスト（yyyy-MM-dd） |
| DryRun | はい/いいえ |
| ForceReprocess | はい/いいえ |
- 戻り値: Status(テキスト: Saved/Skipped/Failed), SavedName(テキスト), SavedFileUrl(テキスト), ErrorMessage(テキスト), IdempotencyKey(テキスト)

### 5.5 PA_Write_Run_Log（子フロー入力）
| 引数 | 型 |
|---|---|
| RunId | テキスト |
| FlowName | テキスト |
| ActionName | テキスト |
| MessageId | テキスト |
| ReplyId | テキスト |
| AttachmentId | テキスト |
| Level | テキスト |
| ErrorMessage | テキスト |
| MeetingCount | 数値 |
| SavedCount | 数値 |
| SkippedCount | 数値 |
| ArchiveUrl | テキスト |
- 戻り値: LogItemId(テキスト)

## 6. 統一アクション表示名（英数字+アンダースコア）
- 共通: Initialize_RunId
- 手動(1): Initialize_RunId, Init_DryRun, Init_ForceReprocess, Init_LookbackDays, Compose_EndDateUtc, Compose_StartDateUtc, Run_Child_Flow_Orchestrator, Notify_Manual_Result
- 定期(2): Initialize_RunId, Get_Last_Success_Log, Compose_StartDateUtc, Compose_EndDateUtc, Run_Child_Flow_Orchestrator
- オーケストレータ(3):
  - 初期化: Initialize_MessagesArray, Initialize_NextLink, Initialize_RepliesArray, Initialize_ReplyNextLink, Initialize_AttachmentCandidates, Initialize_MeetingAttachments, Initialize_DocumentHtml, Initialize_MeetingIndex, Initialize_SavedCount, Initialize_SkippedCount
  - 収集(04): Scope_Collect, Do_Until_Messages_Paging, Get_Channel_Messages, Set_MessagesArray, Set_NextLink
  - 抽出/整形: Filter_Messages_By_Period, Apply_To_Each_Meeting, Compose_Author, Compose_Organizer, Compose_MeetingDate, Compose_PostedDateTimeJst, Convert_Body_Html_To_Text, Set_ReplyNextLink, Set_RepliesArray, Do_Until_Replies_Paging, Get_Message_Replies, Apply_To_Each_Reply, Append_Reply_Attachments, Compose_Parent_Attachments, Filter_File_Attachments, Apply_To_Each_Attachment, Run_Child_Flow_Save_Attachment, Append_Meeting_Attachment, Compose_SortKey, Create_Staging_Item
  - 並び替え: Get_Sorted_Meetings
  - HTML生成(06): Set_DocumentHtml_Header, Apply_To_Each_Sorted_Meeting, Escape_Ampersand, Escape_LessThan, Escape_GreaterThan, Escape_DoubleQuote, Escape_SingleQuote, Compose_Body_With_Breaks, Compose_Page_Break, Apply_To_Each_Saved_Attachment, Append_Attachment_Html, Append_Meeting_Html, Increment_MeetingIndex, Append_DocumentHtml_Footer
  - Word作成(07): Compose_ArchiveFileName, Condition_DryRun, Create_Word_Archive_File, Get_Saved_File_Properties, Set_ArchiveUrl
  - 通知/ログ: Post_Result_Message, Run_Child_Flow_Write_Run_Log_Info, Run_Child_Flow_Write_Run_Log_Error, Respond_To_Caller
  - Scope: Scope_Try, Scope_Catch, Scope_Finally
- 添付保存(5→4): Compose_IdempotencyKey, Get_Ledger_Existing, Condition_Already_Saved, Compose_Extension, Compose_BaseName, Replace_Invalid_1..（複数）, Compose_SavedName, Get_Source_File_Content, Create_Attachment_File, Get_Saved_File_Properties, Set_SavedFileUrl, Create_Ledger_Item, Respond_To_Caller, Scope_Try, Scope_Catch
- ログ(5): Create_Run_Log, Respond_To_Caller

## 7. 正典の式（コピーして使う）
### 7.1 RunId
`guid()`
### 7.2 投稿者（安全参照・空白/null→不明）
Compose_Author =
```
if(empty(trim(coalesce(items('Apply_To_Each_Meeting')?['from']?['user']?['displayName'], ''))),'不明',trim(coalesce(items('Apply_To_Each_Meeting')?['from']?['user']?['displayName'], '')))
```
### 7.3 主催者（＝投稿者。ユーザー決定）
Compose_Organizer = `outputs('Compose_Author')`
### 7.4 会議日付（JST・優先度3=投稿日を主方式）
Compose_MeetingDate = `formatDateTime(convertFromUtc(items('Apply_To_Each_Meeting')?['createdDateTime'],'Tokyo Standard Time'),'yyyy-MM-dd')`
- 本文からの開催日抽出（優先度1/2）はPAに正規表現がなく確実でないため**任意・要実環境確認**。主方式は投稿日JST。
### 7.5 投稿日時JST
Compose_PostedDateTimeJst = `concat(formatDateTime(convertFromUtc(items('Apply_To_Each_Meeting')?['createdDateTime'],'Tokyo Standard Time'),'yyyy-MM-ddTHH:mm:ss'),'+09:00')`
### 7.6 SortKey
Compose_SortKey = `concat(formatDateTime(convertFromUtc(items('Apply_To_Each_Meeting')?['createdDateTime'],'Tokyo Standard Time'),'yyyyMMddHHmmss'),'_',items('Apply_To_Each_Meeting')?['id'])`
### 7.7 Word表示用日付 yyyy年M月d日（曜日）
`concat(formatDateTime(item()?['MeetingDate'],'yyyy年M月d日'),'（',json('["日","月","火","水","木","金","土"]')[dayOfWeek(item()?['MeetingDate'])],'）')`
- 注: dayOfWeekは日=0。json配列を動的intで添字。
### 7.8 本文HTML→テキスト入力
Convert_Body_Html_To_Text 入力 = `coalesce(items('Apply_To_Each_Meeting')?['body']?['content'], '')`
### 7.9 HTMLエスケープ（順序厳守。&が最初）
- Escape_Ampersand = `replace(<入力>, '&', '&amp;')`
- Escape_LessThan = `replace(outputs('Escape_Ampersand'), '<', '&lt;')`
- Escape_GreaterThan = `replace(outputs('Escape_LessThan'), '>', '&gt;')`
- Escape_DoubleQuote = `replace(outputs('Escape_GreaterThan'), '"', '&quot;')`
- Escape_SingleQuote = `replace(outputs('Escape_DoubleQuote'), '''', '&#39;')`
- 改行→<br>: Compose_Body_With_Breaks = `replace(replace(outputs('Escape_SingleQuote'), decodeUriComponent('%0D%0A'), '<br>'), decodeUriComponent('%0A'), '<br>')`
### 7.10 改ページ（2件目以降のみ）
Compose_Page_Break = `<div style="page-break-before:always"></div>`
### 7.11 Wordファイル名
Compose_ArchiveFileName = `concat('課内会議総括_', formatDateTime(convertFromUtc(utcNow(),'Tokyo Standard Time'),'yyyyMMdd_HHmmss'), '.doc')`
### 7.12 冪等キー
Compose_IdempotencyKey = `if(empty(trim(coalesce(triggerBody()?['ReplyId'],''))), concat(triggerBody()?['MessageId'],'_',triggerBody()?['AttachmentId']), concat(triggerBody()?['MessageId'],'_',triggerBody()?['ReplyId'],'_',triggerBody()?['AttachmentId']))`
### 7.13 添付保存名（会議日付_元名。禁止文字→_、末尾空白/ピリオド除去）
- Compose_Extension = `if(contains(triggerBody()?['OriginalFileName'],'.'), concat('.',last(split(triggerBody()?['OriginalFileName'],'.'))), '')`
- Compose_BaseName = `if(contains(triggerBody()?['OriginalFileName'],'.'), substring(triggerBody()?['OriginalFileName'],0,sub(length(triggerBody()?['OriginalFileName']),length(outputs('Compose_Extension')))), coalesce(triggerBody()?['OriginalFileName'],'file'))`
- 禁止文字置換はComposeを分割: Replace_Invalid_Quote/Star/Colon/Lt/Gt/Q/Slash/Backslash/Pipe（順に " * : < > ? / \ | を '_'）。末尾空白/ピリオド除去は `if(or(endsWith(x,' '),endsWith(x,'.')), ...trim...)`、簡便には `trim()`で空白、ピリオドは `if(endsWith(x,'.'), substring(x,0,sub(length(x),1)), x)`。
- Compose_SavedName = `concat(formatDateTime(triggerBody()?['MeetingDate'],'yyyyMMdd'),'_', <正規化Base>, outputs('Compose_Extension'))`
- 長さ超過時: Baseを短縮（拡張子保持）。OriginalFileNameがnull時は 'file' を使用。
### 7.14 保存後URL（主方式: Get file properties → Link to item）
- Get_Saved_File_Properties の動的コンテンツ「Link to item」= `outputs('Get_Saved_File_Properties')?['body/{Link}']`
- 代替（構築）: `concat(<envSiteUrl>, replace(outputs('Get_Saved_File_Properties')?['body/{FullPath}'],' ','%20'))` ※スラッシュはエンコードしない。URL全体にencodeUriComponent/uriComponentを掛けない。
- 注: SharePoint「ファイルの作成」出力に webUrl は存在しない。作成後に Get file properties を実行する。
### 7.15 Graph URI（初回ページ）
- messages: `concat('https://graph.microsoft.com/v1.0/teams/', <envTeamId>, '/channels/', <envChannelId>, '/messages?$top=50')`
- replies: `concat('https://graph.microsoft.com/v1.0/teams/', <envTeamId>, '/channels/', <envChannelId>, '/messages/', items('Apply_To_Each_Meeting')?['id'], '/replies?$top=50')`
- ページング: NextLink = `coalesce(body('Get_Channel_Messages')?['@odata.nextLink'],'')`。Do untilは `empty(変数)` で終了。※nextLinkの絶対URL受理は**要実環境確認**。channelIdの`:`は原則そのまま（要実環境確認）。
### 7.16 期間フィルタ（Filter array 詳細/advanced）
```
@and(greaterOrEquals(item()?['createdDateTime'], triggerBody()?['StartDateUtc']), lessOrEquals(item()?['createdDateTime'], triggerBody()?['EndDateUtc']))
```
- 併せて messageType='message'、deletedDateTime が null を条件に。ISO8601同形式の文字列比較でOK。

## 8. HTMLテンプレート（Set_DocumentHtml_Header / Footer）
Header（初回会議前。空白ページを作らないため改ページは入れない）:
```
<html><head><meta charset="utf-8"><style>
@page { size: A4; margin: 20mm; }
body { font-family: "Yu Gothic","Meiryo",sans-serif; font-size: 10.5pt; }
.page-break { page-break-before: always; }
.meeting-title { font-size: 16pt; font-weight: bold; }
.label { font-weight: bold; }
.attachment-list { margin-top: 8px; }
</style></head><body>
```
Footer: `</body></html>`
1会議ブロックのHTML（Append_Meeting_Html）例:
```
<div class="meeting-title">{日付yyyy年M月d日（曜日）}</div>
<div><span class="label">投稿者：</span>{Author}</div>
<div><span class="label">主催者：</span>{Organizer}</div>
<div><span class="label">投稿日時：</span>{PostedDateTimeJst}</div>
<div><span class="label">内容：</span></div>
<div>{エスケープ済み本文+<br>}</div>
<div class="attachment-list"><span class="label">添付ファイル：</span></div>
{添付リンク群 or 添付ファイルなし}
```
添付1件（Append_Attachment_Html）:
- 成功: `<div><a href="{SavedFileUrl}">{エスケープ済みSavedName}</a></div>`
- 失敗: `<div>{エスケープ済みOriginalName}（保存失敗）</div>`
- 添付なし: `<div>添付ファイルなし</div>`

## 9. 厳格ルール（全ファイル反映）
- trimは文字列のみ。基本 `trim(coalesce(x,''))`。型不明値に機械的trim/string禁止。
- 既定値: 文字列`''`, 配列`json('[]')`, オブジェクト`json('{}')`, 整数`0`, Boolean`false`。false/0を未設定扱いしない。
- 安全参照 `?['a']?['b']`。
- HTMLエスケープ順序: &最初→< > " '。元HTML非サニタイズで直接埋め込まない。
- 共通変数へAppendするループ（HTML連結/会議配列/添付配列/連番）は**並列オフ**（Apply to each設定 同時実行度=オフ、Do untilは既定で逐次）。
- Scope_Try/Scope_Catch（失敗・タイムアウト）/Scope_Finally（成功・失敗・スキップ・タイムアウト）。添付1件失敗で全停止しない（子フローが戻り値でエラー返却）。
- ログにトークン/本文/認証情報を記録しない。
- 要確認ラベル: 要実環境確認/要Teamsコネクタ確認/要SharePointコネクタ確認/要ライセンス確認/要DLP確認/要レスポンス確認/要Word表示確認。

## 10. 各TXTの必須書式（§12）
先頭ブロック: 表示名/推奨名（英語）/ファイル名/フロー種別/作成場所/役割/呼出元/呼出先、使用するコネクタ/使用する接続/必要な権限/プレミアムコネクタの有無/管理者承認の必要性、入力引数（引数名・PA表示名・型・必須任意・既定値・用途・呼出元・呼出元から渡す式）、出力（出力名・型・内容・呼出元での参照方法）、環境変数、内部変数（変数名・型・初期値・用途・更新するアクション・並列実行時の注意）、アクション一覧（各: アクション表示名/コネクタ/PA上のアクション名/配置場所/入力内容/使用する式/出力/次のアクション/実行条件/再試行/タイムアウト/エラー時の処理）、条件/Apply to each/Do until/Select/Filter array/Compose/ページング/並列実行/エラー処理/ログ/想定されるエラー/エラー発生時の修正方法/テスト手順/完成条件、式・型検査結果。
アクション説明は§13の逐次操作粒度（「新しいステップ」→検索→追加→名前変更→各欄入力→式）で書く。

## 11. 各TXT末尾の監査表（§23。全17問にYes/該当説明で回答）
```
式・型監査
trim対象はすべて文字列か:
coalesceの候補値は同一型か:
nullと空文字列を区別しているか:
空白だけの文字列を考慮しているか:
配列の既定値がjson('[]')になっているか:
オブジェクトの既定値がjson('{}')になっているか:
falseを未設定扱いしていないか:
0を未設定扱いしていないか:
Apply to eachへnullを渡していないか:
JSONプロパティを安全に参照しているか:
HTMLへ入れる値をエスケープしているか:
未定義の変数がないか:
未定義のアクション参照がないか:
式内のアクション名が実在するか:
添付リンクが保存後SharePointファイルを指しているか:
会議が日付順に並ぶか:
各会議が新しいページから開始するか:
```

## 12. 想定エラー書式（§20）
```
想定エラー: / 原因: / 確認するアクション: / 確認する入力: / 修正方法: / 修正後の式:
```
必須で扱う想定エラー: trimへ非文字列 / coalesce型不一致 / Apply to eachへnull / Parse JSON不一致 / 投稿者なし / attachmentsなし / ファイル名null / contentUrl null / SharePointファイル無 / 同名ファイル存在 / 保存先フォルダ無 / ファイルリンク取得不可 / HTML過大 / 並列で配列変数競合 / 2年処理タイムアウト / .doc警告。

## 13. 内部変数の型（オーケストレータ、全て先頭で初期化）
- varRunId(文字列), varMessagesArray(配列 json('[]')), varNextLink(文字列 初回URI), varRepliesArray(配列 json('[]')), varReplyNextLink(文字列 ''), varAttachmentCandidates(配列 json('[]')), varMeetingAttachments(配列 json('[]')), varDocumentHtml(文字列 ''), varMeetingIndex(整数 0), varSavedCount(整数 0), varSkippedCount(整数 0)
- 注: PA変数はトップレベルでのみ初期化可。Apply_To_Each_Meeting（並列オフ・逐次）内で varRepliesArray/varReplyNextLink/varAttachmentCandidates/varMeetingAttachment を各反復先頭でSet（リセット）して再利用。
