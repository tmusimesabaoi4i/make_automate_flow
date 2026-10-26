# 01. リスト列仕様の根拠（List Schema Evidence）

MeetingArchiveLedger（12列）／MeetingArchiveRunLog（12列）の全列について、表示名・内部名・型・制約とその根拠ファイル／根拠アクションを一覧化する。
作成日: 2026-07-17

## 凡例

- **確度**: 「確定」= 生成済み定義（`../source/package`）・単一フロー本体（`../../archive-meetings/source/package/`）・ドキュメント2冊のいずれかに実引用できる記載がある。「設計判断」= 複数根拠から今回新たに導出した判断（本文で理由を明記）。
- 全列とも **Lookup先はなし**（後述§3）。
- 参照元ファイルの略記:
  - `BUILD_DEF` = `../../archive-meetings/source/package/Microsoft.Flow/flows/fcca0e31-6d8b-40a8-8d63-2441c979a2c7/definition.json`（単一フロー本体。列名の実利用箇所）
  - `BUILD_PKG_PY` = `../source/build_list_package.py`（リスト作成フローの生成スクリプト。列型・SchemaXmlの決定箇所）
  - `WORK_DEF` = `../source/package/Microsoft.Flow/flows/7c3e50b2-91a4-4f2e-8f5a-6f1de2a9c4b7/definition.json`（生成済み実定義。SchemaXml原文の最終確認）
  - `GUIDE12` = `../../archive-meetings/spec/power_automate_cloud_flow_implementation_guide.md` 12.4節
  - `IMPORT01` = `../../archive-meetings/spec/power_automate_import_guide.md` 0-1節

## 1. MeetingArchiveLedger（処理台帳・12列）

| 表示名 | 内部名 | 列型 | 必須 | インデックス | 一意制約 | Lookup先 | 参照元ファイル | 参照元アクション | 採用根拠 | 確度 |
|---|---|---|---|---|---|---|---|---|---|---|
| Title | Title | Text（既定システム列・単一行） | TRUE（SharePoint既定のまま維持） | なし | なし | なし | `BUILD_DEF`／`BUILD_PKG_PY` | `Compose_Ledger_Body`（単一フロー、`"Title": "@outputs('Compose_IdempotencyKey')"`）／`Add_LedgerViewField_LinkTitle`（本フロー） | 単一フローが保存の都度Titleへ冪等キーを書き込むため常時書込み対象。参照フローの`deactivateSPOTitle`（Required解除）は不採用とし列作成もしない（既定列をそのまま使用、ビュー先頭にLinkTitleとして配置のみ） | 確定 |
| IdempotencyKey | IdempotencyKey | Text（1行, MaxLength=255） | FALSE | なし | なし | なし | `BUILD_PKG_PY`／`WORK_DEF`／`GUIDE12` | `Compose_Ledger_Body.IdempotencyKey`／`If_Create_Ledger_IdempotencyKey`→`Create_Ledger_IdempotencyKey` | 冪等キー本体（`MessageId(_ReplyId)_AttachmentId`形式）。台帳検索(`Get_Ledger_Existing`)の`$filter`対象 | 確定 |
| RunId | RunId | Text（1行, MaxLength=255） | FALSE | なし | なし | なし | 同上 | `Compose_Ledger_Body.RunId`＝`@variables('varRunId')` | 実行識別子。RunLog側と**文字列一致**で相関させる唯一のキー | 確定 |
| MessageId | MessageId | Text（1行, MaxLength=255） | FALSE | なし | なし | なし | 同上 | `Compose_Ledger_Body.MessageId`＝`@items('Process_Each_Parent_Message')?['id']` | 親投稿のGraphメッセージID | 確定 |
| ReplyId | ReplyId | Text（1行, MaxLength=255） | FALSE | なし | なし | なし | 同上 | `Compose_Ledger_Body.ReplyId`＝`@coalesce(items('Process_Each_Attachment')?['sourceReplyId'], '')` | 返信投稿の添付のみ設定（親投稿添付は空文字） | 確定 |
| AttachmentId | AttachmentId | Text（1行, MaxLength=255） | FALSE | なし | なし | なし | 同上 | `Compose_Ledger_Body.AttachmentId`＝`@items('Process_Each_Attachment')?['attachment']?['id']` | 添付固有ID。冪等キーの構成要素 | 確定 |
| OriginalFileName | OriginalFileName | Text（1行, MaxLength=255） | FALSE | なし | なし | なし | 同上 | `Compose_Ledger_Body.OriginalFileName` | 元ファイル名（禁止文字置換前） | 確定 |
| SavedFileName | SavedFileName | Text（1行, MaxLength=255） | FALSE | なし | なし | なし | 同上 | `Compose_Ledger_Body.SavedFileName`＝`@outputs('Compose_SavedName')` | 保存後ファイル名（`yyyyMMdd_元名`） | 確定 |
| SavedFileUrl | SavedFileUrl | **Note（RichText=FALSE, NumLines=6）** | FALSE | なし | なし | なし | `BUILD_PKG_PY`（`schema_xml()`）／`WORK_DEF`／`GUIDE12`（12.4節コラム・27.1節v7） | `Compose_Ledger_Body.SavedFileUrl`＝`@body('Get_Saved_File_Properties')?['{Link}']` | **型の特記（後述§2）**: ドキュメント記載の「単一行テキスト」から変更。ハイパーリンク型は不可という制約（RESTボディが`{"Url":...}`オブジェクトを要求し単純文字列書込みと不整合）は維持しつつ、URLが255字を超える実運用パス（`https://metijapan.sharepoint.com/...`配下の深いフォルダ＋長いファイル名）に対応するためNote(プレーンテキスト)を採用 | 設計判断 |
| Status | Status | Text（1行, MaxLength=255） | FALSE | なし | なし | なし | `BUILD_PKG_PY`／`GUIDE12` | `Compose_Ledger_Body.Status`＝固定文字列`"Saved"`／`Compose_LedgerFailed_Body.Status`＝固定文字列`"Failed"` | 選択肢型ではなくText採用（GUIDE12.4節コラム: 「候補外の値が来ても書込み自体が失敗しないようにする配慮」） | 確定 |
| ErrorMessage | ErrorMessage | **Note（RichText=FALSE, NumLines=6）** | FALSE | なし | なし | なし | `BUILD_PKG_PY`／`WORK_DEF`／`GUIDE12` | `Compose_LedgerFailed_Body.ErrorMessage`＝`@concat('添付の保存に失敗しました: ', outputs('Compose_SavedName'))` | 日本語の定型文＋ファイル名の連結で255字に接近しうるため、複数行プレーンテキストのNoteを採用（Text(255)超過対策） | 設計判断 |
| ProcessedDateTimeUtc | ProcessedDateTimeUtc | **Text（1行, MaxLength=255, ISO8601文字列）** | FALSE | なし | なし | なし | `BUILD_PKG_PY`／`GUIDE12`（「単一行（または日付/時刻）」） | `Compose_Ledger_Body.ProcessedDateTimeUtc`＝`@utcNow()` | 日時2列はSharePoint「日付と時刻」型ではなくText採用（`utcNow()`のISO8601文字列をそのままRESTボディへ書き込む方式と整合させ、タイムゾーン変換・型変換の失敗リスクを排除） | 設計判断 |

## 2. MeetingArchiveRunLog（実行ログ・12列）

| 表示名 | 内部名 | 列型 | 必須 | インデックス | 一意制約 | Lookup先 | 参照元ファイル | 参照元アクション | 採用根拠 | 確度 |
|---|---|---|---|---|---|---|---|---|---|---|
| Title | Title | Text（既定システム列・単一行） | TRUE（SharePoint既定のまま維持） | なし | なし | なし | `BUILD_DEF`／`BUILD_PKG_PY` | `Compose_RunLog_Body.Title`＝`@concat(variables('varRunId'), '_summary')`／`Compose_ErrorLog_Body.Title`＝`@concat(variables('varRunId'), '_error')` | Ledgerと同様、常時書込み対象のため列作成・Required解除ともに不要。ビュー先頭にLinkTitleとして配置 | 確定 |
| RunId | RunId | Text（1行, MaxLength=255） | FALSE | なし | なし | なし | `BUILD_PKG_PY`／`WORK_DEF`／`GUIDE12` | `Compose_RunLog_Body.RunId`／`Compose_ErrorLog_Body.RunId` | Ledger側と文字列一致で相関する唯一のキー（Lookup列は使わない） | 確定 |
| FlowName | FlowName | Text（1行, MaxLength=255） | FALSE | なし | なし | なし | 同上 | `Compose_RunLog_Body.FlowName`＝固定文字列`"PA_Migrate_Teams_Meeting_Archive_To_SPO"` | フロー識別用の固定文字列 | 確定 |
| Level | Level | Text（1行, MaxLength=255） | FALSE | なし | なし | なし | 同上 | `Compose_RunLog_Body.Level`＝`"Info"`／`Compose_ErrorLog_Body.Level`＝`"Error"` | ログレベル。選択肢型ではなくText（Status列と同じ配慮） | 確定 |
| Status | Status | Text（1行, MaxLength=255） | FALSE | なし | なし | なし | 同上 | `Compose_RunLog_Body.Status`＝`@variables('varRunStatus')`／`Compose_ErrorLog_Body.Status`＝固定`"Failed"` | 実行結果（Success/Failed） | 確定 |
| MeetingCount | MeetingCount | **Number** | FALSE | なし | なし | なし | `BUILD_PKG_PY`／`WORK_DEF`／`GUIDE12`（「単一行（数値可）」） | `Compose_RunLog_Body.MeetingCount`＝`@length(variables('varSortedMeetings'))` | 件数4列はSharePoint「数値」型で作成（ドキュメントの「単一行（数値可）」目安をNumber型に確定。整数のみのため小数桁指定なし） | 設計判断 |
| SavedCount | SavedCount | **Number** | FALSE | なし | なし | なし | 同上 | `Compose_RunLog_Body.SavedCount`＝`@variables('varSavedCount')` | 同上 | 設計判断 |
| SkippedCount | SkippedCount | **Number** | FALSE | なし | なし | なし | 同上 | `Compose_RunLog_Body.SkippedCount`＝`@variables('varSkippedCount')` | 同上 | 設計判断 |
| FailedCount | FailedCount | **Number** | FALSE | なし | なし | なし | 同上 | `Compose_RunLog_Body.FailedCount`＝`@variables('varFailedCount')` | 同上（v2で追加された列） | 設計判断 |
| ArchiveUrl | ArchiveUrl | **Note（RichText=FALSE, NumLines=6）** | FALSE | なし | なし | なし | `BUILD_PKG_PY`／`WORK_DEF`／`GUIDE12`（12.4節コラム・27.1節v7） | `Compose_RunLog_Body.ArchiveUrl`＝`@variables('varArchiveUrl')`（実体は`Set_ArchiveUrl`＝`@body('Get_Saved_Archive_Properties')?['{Link}']`、DryRun時は案内文字列） | SavedFileUrlと同じ根拠。URL・DryRun案内文が255字を超えうるためNote採用。ハイパーリンク型不可の制約は維持 | 設計判断 |
| ErrorMessage | ErrorMessage | **Note（RichText=FALSE, NumLines=6）** | FALSE | なし | なし | なし | `BUILD_PKG_PY`／`WORK_DEF`／`GUIDE12` | `Compose_ErrorLog_Body.ErrorMessage`＝`@variables('varErrorMessage')` | エラーメッセージは可変長・日本語文のため255字超過対策でNote採用 | 設計判断 |
| OccurredDateTimeUtc | OccurredDateTimeUtc | **Text（1行, MaxLength=255, ISO8601文字列）** | FALSE | なし | なし | なし | `BUILD_PKG_PY`／`GUIDE12` | `Compose_RunLog_Body.OccurredDateTimeUtc`＝`@utcNow()`／`Compose_ErrorLog_Body.OccurredDateTimeUtc`＝`@utcNow()` | ProcessedDateTimeUtcと同じ根拠。日時2列（Ledgerの`ProcessedDateTimeUtc`とこの列）はText(ISO8601)で統一 | 設計判断 |

合計: MeetingArchiveLedger **12列**（Title含む。カスタム作成11列）／MeetingArchiveRunLog **12列**（Title含む。カスタム作成11列）。

## 3. 型・制約に関する特記事項（3事実の記録）

### 3.1 SavedFileUrl／ArchiveUrl／ErrorMessage を Note(RichText=FALSE, NumLines=6) にした理由

`../../archive-meetings/spec/power_automate_import_guide.md` 0-1節・`../../archive-meetings/spec/power_automate_cloud_flow_implementation_guide.md` 12.4節はいずれも次のように明記している（原文引用）:

```
SavedFileUrl | **1行テキスト（必須。「ハイパーリンクまたは画像」型は不可。理由は下記コラム参照）**
```
```
`SavedFileUrl`・`ArchiveUrl`は必ず1行テキストで作成してください（重要）: 現行版では、台帳・実行ログへの書込み
（`Create_Ledger_Item`等4アクション）がSharePoint「HTTP要求を送信します」(REST)方式に変わっています。
RESTで送信する本文は単純な文字列（URL文字列そのもの）であり、列を「ハイパーリンクまたは画像」型で作成していると、
RESTが期待する`{"Url": "...", "Description": "..."}`という入れ子オブジェクトと形式が一致せず、書込みに失敗する
おそれがあります。この2列は必ず「1行テキスト」で作成してください。
```

一方でSharePointの単一行テキスト（Text）列には**MaxLength=255の上限**があり、`{Link}`が返すSharePoint共有ドキュメントライブラリの絶対URL（サイトURL＋長いフォルダパス＋日本語ファイル名のURLエンコード後文字列）は255字を容易に超えうる。また`ErrorMessage`も日本語の定型文＋ファイル名の連結で同様に超過しうる。
そこで本リスト作成フローでは、`build_list_package.py`の`schema_xml()`関数で3列を次のSchemaXmlで作成する（`WORK_DEF`実物より抜粋）:

```xml
<Field Type="Note" DisplayName="SavedFileUrl" Name="SavedFileUrl" Required="FALSE" Group="AutoGenerated Columns" RichText="FALSE" NumLines="6" />
```

`Type="Note"`（複数行テキスト）かつ`RichText="FALSE"`（書式なしプレーンテキスト）とすることで、
- ドキュメントが要求する「ハイパーリンクまたは画像型ではない」という制約は維持される（Noteはハイパーリンク型ではないため、REST書込み時に`{"Url":...}`オブジェクトを要求しない単純文字列列である点は1行テキストと同じ）。
- 一方でNote型はMaxLength上限を持たないため、255字超のURL・エラー文でも書込みが失敗しない。

つまり「ドキュメントの『1行テキスト』という推奨からNoteへ変更」しているが、**ドキュメントが本当に守りたかった制約（ハイパーリンク型の禁止）は満たしたまま、文字数上限という別の失敗要因を追加で回避した**、という位置づけの設計判断である。

### 3.2 件数4列（MeetingCount／SavedCount／SkippedCount／FailedCount）はNumber型

ドキュメントの目安は「単一行（数値可）」（Text列に数値を書くことも許容する表現）だが、本フローでは実際にSharePointの数値型（`<Field Type="Number" ... />`、`WORK_DEF`で確認）で作成する。台帳・実行ログとも該当4列は常に整数（`length(...)`・`variables('varXxxCount')`の整数変数）のみが書き込まれ、選択肢の曖昧さや空文字許容の必要がないため、Text型で妥協する理由がない。

### 3.3 日時2列（ProcessedDateTimeUtc／OccurredDateTimeUtc）はText(ISO8601)

いずれも`utcNow()`（ISO8601形式の文字列）をそのまま書き込む。SharePoint「日付と時刻」型で作成すると、REST書込み時にタイムゾーン変換・パース挙動の実環境差異という未検証リスクが生じるため、単純な文字列列（Text, MaxLength=255）として作成し、値の解釈をSharePoint側の型変換に依存させない。

## 4. 全列共通の3事実

1. **Lookup先はなし**。両リストとも全12列（Titleおよびカスタム11列×2）にLookup型の列は存在しない。台帳とRunLogの相関は`RunId`列（Text）の文字列一致のみで行われる。参照フロー`CreateKnowledgeList`が持っていた`KnowledgePrimaryTag`（Lookup型、`List="{tagListId}"`）に相当する仕組みは、`WORK_DEF`・`BUILD_PKG_PY`のいずれにも存在しない（全文検索で`Lookup`という文字列自体が0件）。
2. **添付ファイル（Attachments）利用なし**。両リストとも`EnableAttachments`アクション、既定ビューへの`Attachments`列追加のいずれも行わない（`WORK_DEF`に該当アクション0件）。単一フロー側の添付ファイル保存はSharePointライブラリへの直接ファイル保存で完結し、台帳リスト自体に添付ファイルを付与する運用はない。
3. **Title列は常時書き込み対象**。参照フローの`deactivateSPOTitle`（Titleの`Required`をfalseへ変更する処理）は不採用。単一フロー本体`BUILD_DEF`の`Compose_Ledger_Body`／`Compose_LedgerFailed_Body`／`Compose_RunLog_Body`／`Compose_ErrorLog_Body`はいずれも`Title`キーへ値を設定しており（空文字を書く箇所はない）、Title列の必須制約を緩める理由がない。
