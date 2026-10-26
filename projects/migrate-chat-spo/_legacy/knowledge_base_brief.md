# 共通ナレッジベース作成ブリーフ（Fable監修・migrate_chat_spo案件の全履歴）

これは migrate_chat_spo 案件（Teams課内会議アーカイブ単一フロー）の経験を共通知識化するための原材料。
執筆エージェントはこれと下記参照ファイルを根拠とし、ここに無い事実を創作しない。

## 参照ファイル（読み取り専用）
- 事実シート（v1→v5全履歴の正典）: scratchpad/SINGLE_FLOW_FACTS.md
- 検証レポート: migrate_chat_spo/dist/package_validation_report.txt
- 公式資料調査（URL+参照日あり）: migrate_chat_spo/doc/official_reference_findings.md
- 雛形サンプル解析: migrate_chat_spo/doc/sample_export_analysis.md
- 実装手順書: migrate_chat_spo/doc/power_automate_cloud_flow_implementation_guide.md
- インポート手順書: migrate_chat_spo/doc/power_automate_import_guide.md
- 実働サンプル整形定義: scratchpad/sample2_definition_pretty.json
- 実行順アウトライン: scratchpad/action_outline.txt

## 案件で実際に発生したエラー（時系列）

### エラー1: インポート時の式パースエラー（ネストした@）
- メッセージ: 「電源フローのロジック アプリ フロー テンプレートが無効です。The template language expression
  'if(contains(@coalesce(...' is not valid: the string character '@' at position '12' is not expected.」
- 原因: 式文字列を Python で連結生成した際、外側 @if(...) の内側にネストした関数にも @ を付けた
  （@coalesce）。@ は式文字列の先頭または @{...} 補間でのみ有効。
- 修正: 内側の @coalesce(...) → coalesce(...)。定義全体を機械走査し不正な @ が0件であることを確認。
- 教訓: 式を文字列連結で生成する場合、「埋め込み用（@なし）」と「単独式用（@あり）」を明確に分離する。

### エラー2: 保存時の SetVariable 自己参照エラー（最重要）
- メッセージ: 「フローの保存がコード 'WorkflowRunActionInputsInvalidProperty' およびメッセージ
  'The inputs of workflow run action 'Set_MessagesArray' of type 'SetVariable' are not valid.
  Self reference is not supported when updating the value of variable 'varMessagesArray'.' で失敗しました。」
- 重要事実: インポートは成功した。保存で失敗した。「インポート成功＝完成」ではない。
- 原因: SetVariable の値式が更新対象変数自身を参照（union(variables('varMessagesArray'), 新ページ)）。
  配列累積・文字列concat累積・add(自身,1) はすべて同じ理由で保存不可。
- 検出された自己参照は3件: Set_MessagesArray / Set_RepliesArray / Append_Reply_Attachment_Candidates
  （3つ目は名前がAppendでも実体はSetVariable+union。名前でなく type を見る）。
- 修正: (a)配列累積→Apply to each＋「配列変数に追加」(AppendToArrayVariable, 値=item())、
  (b)文字列累積→「文字列変数に追加」(AppendToStringVariable)、(c)カウンター→「変数を増分する」(IncrementVariable)。
  ページ配列を1要素としてAppendせず、Apply to eachで1件ずつ追加する。
- 教訓: 保存検証は「全SetVariableの値式に variables('更新対象') が含まれないこと」の機械走査で事前に検出可能。

### エラー3（事前検出・輸入前に修正）: アクション名の全体重複
- Set_ReplyNextLink が2箇所（ループ外初期化とループ内更新）に存在。Power Automate はフロー全体で
  アクション名の一意性を要求するため、インポートが壊れる。
- 修正: 外側を Set_ReplyNextLink_First に改名（Set_NextLink_First / Set_NextLink と同型のパターン）。
- 教訓: 「初期化用」と「ループ内更新用」は _First などで名前を分ける。重複名検査を検証スクリプトに含める。

## 実働サンプル（create_meeting_list_sample）から得た知見

### 参考にした点（実環境で動作実績のある実装）
- Teams「Send a Microsoft Graph HTTP request」（shared_teams / operationId=HttpRequest）は標準コネクタで
  Graph GET を実行できる（プレミアム不要）。パラメータ: Uri / Method / ContentType。
- 親投稿取得URL: https://graph.microsoft.com/v1.0/teams/{teamId}/channels/{channelId}/messages?$top=50
- 返信取得URL: .../messages/{messageId}/replies?$top=50
- チャネルID（19:xxxx@thread.tacv2）はURLエンコード必須（:→%3A、@→%40）。実働サンプルはエンコード済みURLで動作。
  メッセージIDは uriComponent() で処理していた。→ 当方は uriComponent(variables/items) で統一。
- teamId はGUIDのためエンコード不要。
- body('Teams HttpRequest') は Graph 応答JSONそのもの（statusCode/headers/body の封筒ではない）。
  根拠: サンプルの Apply to each 入力が body('ParseJson')?['value'] で動作（ParseJsonのcontent=body(Graph)）。
- HtmlToText（shared_conversionservice）のパラメータキーは Content。
- SharePoint PostItem は dataset=サイトURL、table=リストGUID、item/列内部名 形式。
- connectionReferences のキーは shared_teams-2 のようにサフィックスが付くことがある。
  アクションの host.connectionName はこのキーと一致させる必要がある。

### 流用しなかった点（実際のエクスポートでも設計バグはある）
- SetVar_ChildAttachments_Append: union(createArray(item()), coalesce(outputs('Compose_ReplyAttachments'), json('[]')))
  を毎回 SetVariable → (a)累積でなく毎回上書き（最後の返信の添付しか残らない）、
  (b)createArray(item()) が返信オブジェクト自体を添付配列へ混入（後段のFilterで偶然除去されているだけ）。
  ※作者が自己参照禁止を回避しようとして上書き方式になった形跡＝自己参照禁止の傍証でもある。
- ページング無し（$top=50 の1ページのみ）。50件超は取得漏れ。@odata.nextLink 追跡が必須。
- Parse JSON スキーマが封筒形（statusCode/headers/body）で実際の参照パス（?['value']）と不一致。
  トップレベル required が無いため偶然通っているだけ。実応答からスキーマを作り required は最小限にする。
- SharePoint値式の末尾に \n が混入（"@{...}\n"）。
- トリガーschemaが空。ハードコードされたURL・リストGUID。

## v2 論理レビューで修正した設計バグ（保存はできるが動作が誤り）
1. DryRun=はい でも総括ファイルを常時作成していた → Condition_DryRun_Archive で分岐。
2. 添付1件の保存失敗が会議処理全体を止めていた＋台帳に Failed が記録されない
   → 危険操作を Scope_Save_File に隔離し、runAfter Failed/TimedOut の後続ハンドラで吸収・継続。
   Status=Failed 記録＋varFailedCount 集計。
3. 再利用（Skipped・既存URLあり）添付が「保存失敗」と誤表示 → 判定を「savedFileUrl 非空」に変更。

## その他の確定知見
- InitializeVariable はトップレベル必須（Scope内不可）。
- 変数を更新する Apply to each / Do until は並列オフ（runtimeConfiguration.concurrency.repetitions=1）必須。
- ネスト深さ上限8（今回最深7=Scope>Foreach>Scope>Foreach>If>If>Scope、その中のリーフが8段目でちょうど上限）。
- sort(コレクション, 'プロパティ名') は昇順のみ。降順は reverse() 併用。オブジェクト配列のプロパティソート可。
- 曜日等の配列インデックス参照 json('[...]')[式] は式エディタで不安定になり得る
  → substring('日月火水木金土', dayOfWeek(...), 1) のような関数形が堅い。
- 計算インデックスの角括弧アクセスは避け、関数（substring等）で代替。
- runAfter はコンテナ起点でも "runAfter": {} を明示（PA標準エクスポート形式）。
- trim(coalesce(<文字列またはnull>, '')) が基本形。coalesce(trim(x), '') は trim が先に評価され null で失敗し得るため禁止。
- coalesce の候補は同一型（文字列は ''、配列は json('[]')、オブジェクトは json('{}')）。
- Apply to each の入力は配列保証（coalesce(x, json('[]')) か Filter/Select/Query の出力）。
- Boolean判定は equals(coalesce(triggerBody()?['X'], 既定値), true) で false/0 を未設定扱いしない。
- 数値トリガー入力の安全化: if(greater(int(coalesce(入力, 0)), 0), int(coalesce(入力, 7)), 7)（既定7、0以下→7）。
- HTMLエスケープは & を最初に（&→&amp; → < → > → " → '）。改行→<br>。
- 改ページ <div style="page-break-before: always;"></div> は2件目以降のみ（varMeetingIndex>0 判定）。
- 標準コネクタのみで真正 .docx の動的生成は不可（Word Online (Business) のテンプレート機能はプレミアム）。
  HTMLベース .doc（Word互換HTML）を採用。HTMLの拡張子 .docx リネームは破損ファイルになるため禁止。
- ファイル名サニタイズ: 禁止文字 " * : < > ? / \ | → _、末尾空白/ピリオド除去、拡張子保持、長さ制限、null時既定名。
- 冪等キー: MessageId(_ReplyId)_AttachmentId。SharePoint台帳リストの GetItems($filter) で既存確認。
- 保存後URL: GetFileItem/{Link}（コミュニティ確認のみ・要実環境確認）。Teams contentUrl を成果物リンクに流用しない。
- レガシーパッケージZIP: ルートmanifest.json + Microsoft.Flow/flows/{guid}/(definition|apisMap|connectionsMap).json。
  XMLは含まない。ソリューション形式（Dataverse）と混同しない。ZIP直下階層を雛形と一致させる。
- 匿名化: creator.id / tenantId / 接続GUID / メールは新規GUID・空オブジェクトへ。認証情報は埋め込まない
  （authentication は参照式のみで秘密情報ではない）。
- インポート≠完成。インポート後に (1)開く (2)即保存 (3)フローチェッカー (4)小期間(1〜7日)テスト。
- 段階テスト: LookbackDays 7→30→365→730。フロー実行時間上限（約30分）超過時は期間分割で複数回実行。
- フロー実行時間・Until上限（count/timeout）を大量データ時に考慮。
- 検証は機械走査で: JSON構文 / runAfter兄弟整合 / 変数初期化=参照 / 重複アクション名 / SetVariable自己参照 /
  重複初期化 / 接続参照突合 / 不正@ / operationId実在 / 匿名化リーク。すべて0件になるまで修正。

## 案件固有事項（共通知識へ実値を転記しない。プレースホルダー {teamId} {channelId} {siteUrl} {listId} {destinationPath} を使用）
- Team ID / Channel ID / SharePointサイトURL / リストGUID / 保存先フォルダーパス / 台帳・ログの列構成 /
  会議判定条件（messageType='message' 等の組合せ）/ 取得期間730日 / 接続名。

## 実働サンプルの機械解析での追加発見（Sonnet解析・2026-07-16）
- 実働サンプルの危険パターン（アンチパターンとして知識化）:
  (a) **取得前に全削除**: 既存SharePoint項目を全削除してからGraph取得を実行。取得が失敗/0件でも
      削除済みでロールバック不能。「新規データ取得の成功後にのみ破壊的処理を行う」順序が正しい。
  (b) SetVariable上書きによる添付蓄積 → 複数返信の添付がサイレント消失（最後の1件のみ残る）。
  (c) タイトルは lastModifiedDateTime のJST変換、投稿日時列は createdDateTime のUTCそのまま
      → 同一項目内でタイムゾーン基準が不整合（UTC深夜前後で日付ずれ）。
  (d) mentions?[0]?['mentionText'] の先頭決め打ち（複数メンション時の妥当性なし）。
  (e) coalesce(..., json('[]')) と coalesce(..., array()) の表記ゆれ混在（機能同値だが一貫性なし）。
  (f) SharePoint値式の末尾 \n が実際に列値へ混入する（"@{...}\n" は改行が保存される）。
- Parse JSON「デッドスキーマ」の仕組み: content の実データがフラット（{value:[...]}）なのに
  スキーマが封筒形（{statusCode,headers,body}）。トップレベル required 無し＋properties は
  「キーが存在する場合のみ」検証されるため、body.value.items 配下の膨大な required は一度も
  評価されず素通り。スキーマと参照パス（?['value'] vs ?['body']?['value']）は必ず一致させること。
- connectionReferences の2方式（どちらも実在の正当形式）:
  (a) Embedded ＋ authentication="@parameters('$authentication')"（実働サンプル）
      フィールド: connectionName/source/id/tier/apiName/isProcessSimpleApiReferenceConversionAlreadyDone
  (b) Invoker ＋ authentication=X-MS-APIM-Tokens 復号式（雛形サンプル・当方採用）
      → 当方v3が実環境インポートに成功した実績あり。どちらを使うかはプロジェクトで一貫させ、
      アクションの host.connectionName は connectionReferences のキーと完全一致させる。
  キーは shared_teams-2 のような自動採番サフィックスが付くことがある。
- apisMap.json / connectionsMap.json は connectionReferences キー→リソースGUID の対応表。
  manifest.json の dependsOn がAPI3件＋接続3件の全GUIDを含む（3コネクタの場合）。
- 実働サンプルの operationMetadataId はデザイナー付与の任意メタデータ（無くてもインポート可）。
- HtmlToText へ渡す本文をサンプルは <p class="editor-paragraph">@{...}</p> でラップ（必須ではない）。
- SharePoint日本語表示名列の内部名は OData__xHHHH_ 形式（例: item/OData__x30d5__x30a1__x30a4__x30eb_）。

## 公式資料（詳細は doc/official_reference_findings.md。参照日 2026-07-16）
- Logic Apps ワークフロー定義言語 / 関数リファレンス（learn.microsoft.com）
- Power Automate クラウドフロー パッケージのエクスポート/インポート
- Teams コネクタ / SharePoint コネクタ / Content Conversion コネクタのリファレンス
- 変数の作成と管理（Increment/Append to array/Append to string の正式名）
