# Teams課内会議アーカイブ自動化

Power Automateクラウドフロー実装手順書（初心者向け・単一フロー・画面操作ガイド）

## 本書について

本書は、Teamsチャネル「03_課内会議」の過去投稿（親投稿＋返信＋添付ファイル）を自動的にSharePointへアーカイブする仕組みを、**単一のPower Automateクラウドフロー**として構築・利用するための手順書です。以前に作成した「5フロー構成（親フロー＋子フロー4本）」版の手順書を、本書が全面的に置き換えます。旧構成の記載は本書には残していません。

- 成果物は、そのままインポートできるZIPファイル1本です: `../release/PA_Migrate_Teams_Meeting_Archive_To_SPO_20260718012104.zip`（v10）
- フロー数は**1つ**（子フローなし）。フロー内部は複数の「スコープ(Scope)」で処理単位を区切って整理しています。
- 名称・変数名・列名・式は、実装済みフロー定義 `../source/package/Microsoft.Flow/flows/fcca0e31-6d8b-40a8-8d63-2441c979a2c7/definition.json` の内容と完全に一致させています。本書の記載とdefinition.jsonが食い違う場合はdefinition.jsonを正としてください。
- コネクタ・式・パッケージ形式について公式資料で確認できた仕様・不確実な点は `../../../../../references/official_reference_findings.md` にまとめてあります。本書でも該当箇所で参照します。
- Power Automateクラウドフロー全般に通用する汎用ルール（式の書き方・変数の扱い・自己参照禁止・コネクタ出力の参照方法・エクスポート/インポート形式など）は、本案件固有の内容ではなく [../../rules/00_power_automate_core_rules.md](../../../../../handbook/rules/00_power_automate_core_rules.md) 等の共通ナレッジ（`make_automate_flow`直下の`rules/`）にまとめてあります。本書は本フロー固有の名称・式・手順に絞って記載しており、一般論の重複説明はしていません。
- 定期実行トリガー（繰り返し等）は**追加しません**。今回の成果物は手動トリガー1つのみのインスタントクラウドフローです。将来、定期実行が必要になった場合は、本フローを複製し、複製後のフローのトリガーだけを手動から繰り返しトリガーへ変更することを想定してください（本体のロジックは変更不要）。

> 表記ルール: 「**要実環境確認**」「**要SharePointコネクタ確認**」「**要Word表示確認**」「**要ライセンス確認**」「**要DLP確認**」は、実際のテナント・ライセンス・コネクタバージョンで確認が必要な未確定事項を示します。一覧は27章にまとめています。

---

## 目次

- [1. このフローでできること](#1-このフローでできること)
- [2. 全体構成](#2-全体構成)
- [3. 使用するコネクタ](#3-使用するコネクタ)
- [4. 使用しないサービス](#4-使用しないサービス)
- [5. 事前に確認する権限](#5-事前に確認する権限)
- [6. サンプルZIPの構造](#6-サンプルzipの構造)
- [7. フローのインポート](#7-フローのインポート)
- [8. 接続の設定](#8-接続の設定)
- [9. 手動トリガーの入力](#9-手動トリガーの入力)
- [10. 初期設定変数](#10-初期設定変数)
- [11. Teams親投稿の取得](#11-teams親投稿の取得)
- [12. Teams返信の取得](#12-teams返信の取得)
- [13. 会議情報の作成](#13-会議情報の作成)
- [14. 添付ファイルの取得](#14-添付ファイルの取得)
- [15. SharePointへの保存](#15-sharepointへの保存)
- [16. 保存後URLの取得](#16-保存後urlの取得)
- [17. 会議の日付順ソート](#17-会議の日付順ソート)
- [18. Word用HTMLの作成](#18-word用htmlの作成)
- [19. 1会議1ページの改ページ](#19-1会議1ページの改ページ)
- [20. Wordファイルの保存](#20-wordファイルの保存)
- [21. エラー処理](#21-エラー処理)
- [22. 過去7日間のテスト](#22-過去7日間のテスト)
- [23. 取得期間の変更](#23-取得期間の変更)
- [24. 過去1年間の実行](#24-過去1年間の実行)
- [25. 過去2年間の実行](#25-過去2年間の実行)
- [26. トラブルシューティング](#26-トラブルシューティング)
- [27. 制約と未確定事項](#27-制約と未確定事項)

---

## 1. このフローでできること

本手順を最後まで実施すると、以下が実現します。

- Power Automateの「フローを実行」画面から手動でボタンを押すだけで、指定した日数（既定7日、本番は365日または730日）だけさかのぼってTeamsチャネル投稿（親投稿＋返信）を全件取得できる。
- 各会議（親投稿1件を1会議として扱う）ごとに、投稿者・会議日付（投稿日のJST日付）・投稿日時・本文・添付ファイルを1つのまとまり（会議データ）として認識する。
- 添付ファイル（PDF/Excel/Word等）を `yyyyMMdd_元ファイル名` の形式でSharePointの指定フォルダーへ保存し、保存後のファイルへのリンクを控える。
- 会議を開催日（同日は投稿日時）順に並べ替え、1会議＝1ページとなるWord互換ファイル（`.doc`）を1つ生成し、SharePointへ保存する。
- 同じ添付ファイルを何度再実行しても無制限に複製しない（処理台帳による冪等性）。
- 実行結果（件数・保存件数・スキップ件数・生成ファイルURL）をSharePointの実行ログリストに記録する。
- テスト実行（DryRun）モードで、添付ファイル本体を保存せずに件数・内容だけを確認できる。
- 処理済みファイルの再処理（ForceReprocess）を指定すれば、台帳を無視して添付ファイルを再保存できる。

これらはすべて**1つのクラウドフロー**（表示名「Teams課内会議アーカイブ」、パッケージ内表示名 `PA_Migrate_Teams_Meeting_Archive_To_SPO`）の中で完結します。子フローの呼び出しはありません。

---

## 2. 全体構成

### 2.1 フロー内部の処理単位（スコープ構成）

フロー内部は、実行順に次の「スコープ(Scope)」で区切って整理されています。すべて**同じ1つのフローの中**にあり、上から下へ順に実行されます（`runAfter`でつながっています）。

```
[手動トリガー: LookbackDays / DryRun / ForceReprocess]
  ↓
[Compose_EffectiveLookbackDays（LookbackDaysの安全化。10章参照）]
  ↓
[ルートの変数初期化（28個・Initialize_*）]
  ↓
Scope_05_Ensure_Destination_Folder（v10新設） … 保存先フォルダーの事前作成・実在検証（DryRun=いいえの場合のみ）
  ↓
Scope_10_Get_Channel_Messages    … Teams親投稿を全ページ取得
  ↓
Scope_20_Process_Meetings        … 期間フィルタ→会議ごとに返信取得・添付抽出・保存・正規化
  ↓
Scope_40_Sort_Meetings           … 会議を開催日順に並べ替え
  ↓
Scope_50_Build_Word_Content      … Word用HTML文字列を組み立て
  ↓
Scope_60_Create_Archive_File     … .docファイルを作成しSharePointへ保存
  ↓
Scope_70_Write_Run_Log           … 実行ログ（成功）を記録
  ↓（Scope_70が失敗/スキップ/タイムアウトした場合のみ）
Scope_90_Catch                   … 実行ログ（失敗）を記録
  ↓（Scope_90の成功/失敗/スキップ/タイムアウトいずれでも）
Scope_99_Finally                 … 実行結果サマリをCompose（フロー実行履歴の最終確認用）
```

- 旧版（5フロー構成）にあった「Scope_Try」でフロー全体を包む形は取っていません。代わりに、`Scope_70_Write_Run_Log`が失敗・スキップ・タイムアウトした場合にのみ`Scope_90_Catch`が動く、という`runAfter`条件でエラー処理を実現しています（21章で詳述）。
- `Scope_20_Process_Meetings`の内部（会議ごとのループ）で例外が発生した場合、そこから先の`Scope_40`〜`Scope_70`は実行されず、直接`Scope_90_Catch`（実行ログへの失敗記録）に進みます。**v2では、添付ファイル本体のコピー（`Scope_Save_File`）の失敗に限り、その添付だけを`Status=Failed`として記録して会議処理・フロー全体を継続する仕組みを追加しました**（15章・21章で詳述）。ただし、それ以外の箇所（Teams取得・処理台帳検索等）での例外は、引き続き実行全体を失敗として扱います（21章・27章で詳しく説明します）。
- すべてのForeach（Apply to each）・Do untilループは「同時実行を有効にする」を**オフ**（`runtimeConfiguration.concurrency.repetitions: 1`）にしてあります。共通の配列変数（varRepliesArray等）をループの中で使い回すため、同時実行するとデータが混在してしまうためです。

### 2.2 使用するSharePointリスト

| リスト名 | 役割 | 案内章 |
|---|---|---|
| MeetingArchiveLedger | 添付ファイル1件ごとの処理台帳（冪等性の根拠） | 12章末 |
| MeetingArchiveRunLog | 実行ログ・エラーログ | 12章末・21章 |

旧版にあった「会議一時保存リスト（MeetingArchiveStaging）」は、単一フローでは使用しません。会議の並べ替えはSharePointリストを介さず、フロー内の配列変数に対して`sort()`関数を直接適用する方式に変更しています（17章）。

### 2.3 主要な技術方式の要約

| 課題 | 採用方式 |
|---|---|
| Teamsメッセージ・返信の全件取得 | Teams「Send a Microsoft Graph HTTP request」＋`@odata.nextLink`によるDo untilページング |
| 会議の並び替え | フロー内配列変数`varMeetings`に対し`sort(variables('varMeetings'), 'sortKey')`を直接適用（SharePointリスト経由なし） |
| Word文書生成 | HTML文字列を組み立て、SharePoint「ファイルの作成(Create file)」で`.doc`として保存（Word互換HTML）。Word Online (Business)のテンプレート/PDF変換はプレミアムのため不採用 |
| 保存後ファイルURLの取得 | SharePoint「ファイルのプロパティの取得(Get file properties／GetFileItem)」の出力`{Link}`を使用（**要SharePointコネクタ確認**、16章） |
| 冪等性（重複保存防止） | 台帳`MeetingArchiveLedger`に`IdempotencyKey`＝MessageId(_ReplyId)_AttachmentIdで保存前検索 |

---

## 3. 使用するコネクタ

本フローで実際に使用するコネクタ・アクションは、以下の3種類（すべて標準・非プレミアム）と、コネクタ接続を必要としない組み込みアクションのみです。`../../../../../references/official_reference_findings.md`で公式資料上の仕様を確認済みです。

| コネクタ | apiId | 使用するoperationId（アクション名） | 用途 |
|---|---|---|---|
| Microsoft Teams | shared_teams | HttpRequest（Send a Microsoft Graph HTTP request） | 親投稿・返信の全件取得（Graph呼び出し） |
| SharePoint | shared_sharepointonline | GetItems（複数の項目の取得） | 処理台帳の重複確認 |
| SharePoint | shared_sharepointonline | CreateFile（ファイルの作成） | 添付ファイル・Word互換ファイルの保存 |
| SharePoint | shared_sharepointonline | HttpRequest（SharePoint に HTTP 要求を送信します・REST） | 保存先フォルダーの事前作成・検証（**v10で追加**。10.2節参照）／処理台帳・実行ログへの書込み（**v7でPostItemから変更**。15.6節参照） |
| SharePoint | shared_sharepointonline | GetFileContentByPath（ファイルコンテンツの取得・パス使用） | 添付ファイル本体の取得 |
| Content Conversion | shared_conversionservice | HtmlToText（Html to text） | Teams投稿本文のプレーンテキスト化（パラメータキーは`Content`） |

実在するoperationIdは上記の**5種類**です（v7で`PostItem`を廃止して7→6種類、**v10で`GetFileItem`（ファイルのプロパティの取得）を廃止して6→5種類**になりました。保存後のファイルURLは、v10以降はプロパティ取得を呼び出さず、既知の値から直接組み立てる方式に変わっています。詳細は15.6節・16章・27章参照）。SharePointコネクタの`HttpRequest`（HTTP要求を送信します）とTeamsコネクタの`HttpRequest`（Send a Microsoft Graph HTTP request）は同名のoperationIdですが、接続先コネクタ自体（`apiId`）が異なるため区別されます。

このほか、以下の組み込みアクション（コネクタ接続不要）を使用します: 変数を初期化する(InitializeVariable)／変数を設定する(SetVariable)／変数の値を増やす(IncrementVariable)／配列変数に追加(AppendToArrayVariable)／作成(Compose)／選択(Select)／配列のフィルター処理(Query)／条件(If)／Apply to each(Foreach)／Do until(Until)／スコープ(Scope)。

Teamsチャネルからのメッセージ取得には「Send a Microsoft Graph HTTP request」を使用しますが、これは**標準・非プレミアムのアクション**であり、アプリ登録や管理者同意は不要です。汎用HTTPアクションやHTTP with Microsoft Entra IDとは別物であり、許可範囲内です。

---

## 4. 使用しないサービス

以下は一切使用しません。

- Azure Functions / Azure Automation / Logic Apps / App Service などのAzureリソース
- 外部サーバー・自前でホストするアプリケーション
- Power Automate for desktop（PAD）
- Python / PowerShell / C# などの独自コード
- カスタムコネクタ
- 汎用HTTPアクション、HTTP with Microsoft Entra ID（いずれもアプリ登録・管理者同意が前提になるため）
- アプリケーション権限を前提としたGraph呼び出し・アプリ登録
- Open XML（.docx/.xlsx）を独自に組み立てる処理
- Word Online (Business) の「テンプレートに値を入力」「WordをPDFに変換」（いずれもプレミアムコネクタ）
- その他プレミアム／外部の文書生成コネクタ（Encodian等）
- 子フロー（Run a Child Flow）。本成果物は単一フローのみで完結します
- 定期実行トリガー（繰り返し／Recurrence）。手動トリガーのみを使用します（1章・2章参照）

---

## 5. 事前に確認する権限

フローをインポート・実行する前に、以下を確認してください。

| 用途 | 必要な権限・接続 |
|---|---|
| チャネルメッセージ取得 | 対象チーム（`varTeamId`）のメンバーであること。Teamsコネクタの接続を作成するアカウントがそのチームの投稿・返信を閲覧できる必要があります |
| 保存先書込み | 保存先SharePointサイト（`varSiteAddress`）のライブラリ・フォルダーへの編集（Contribute以上）権限。**v10以降はフロー冒頭の`Scope_05_Ensure_Destination_Folder`（10.2節）が保存先フォルダーを自動作成するため、フォルダー未作成の状態からでも実行できますが、フォルダー作成にはやはり編集権限が必要です** |
| 添付ファイル本体の取得 | `GetFileContentByPath`は`dataset`に保存先サイト（`varSiteAddress`）を指定し、Teams添付の`contentUrl`から解析したパスをその中で解決します（14章・15章）。添付ファイルの実体が保存先サイトとは別のサイト（例: チームの既定のファイルライブラリ）にある場合、このパス解決が失敗する可能性があります。**要実環境確認** |
| 文書生成（Content Conversion） | 認証不要（サインイン不要）。接続の作成手順自体が表示されない場合があります |

このフローは標準コネクタの委任（Delegated）権限のみで動作する設計であり、Azure ADへのアプリ登録・管理者の同意（Admin Consent）は不要です。ただし、以下は組織側で個別に確認してください。

- **要DLP確認**: Microsoft Teams・SharePoint・Content Conversionの各コネクタが、組織のDLP（データ損失防止）ポリシーで同一グループに属しているか。異なるグループに分類されている場合、フローの保存時にエラーになることがあります。
- **要ライセンス確認**: 実行アカウントのPower Automateライセンス（クラウドフローの実行に必要なプラン）。
- 条件付きアクセスポリシーにより、Teams/SharePointコネクタの接続作成がブロックされていないか。

---

## 6. サンプルZIPの構造

成果物ZIP `../release/PA_Migrate_Teams_Meeting_Archive_To_SPO_20260718012104.zip` は、Power Automateの「パッケージ（レガシー）」形式です。内部構造は次のとおりで、Microsoftが配布しているサンプルパッケージと同一の構造で作成しています（`../../../../../references/official_reference_findings.md` §7参照）。

```
PA_Migrate_Teams_Meeting_Archive_To_SPO.zip
├─ manifest.json                                      … ルートmanifest（schema/details/resources）
└─ Microsoft.Flow/
   └─ flows/
      ├─ manifest.json                                … flowAssets.assetPaths
      └─ fcca0e31-6d8b-40a8-8d63-2441c979a2c7/
         ├─ definition.json                            … フロー本体（トリガー・アクション・接続参照）
         ├─ apisMap.json                                … 使用コネクタのマッピング
         └─ connectionsMap.json                         … 接続参照のマッピング
```

主な内容:

| 項目 | 値 |
|---|---|
| フロー表示名（日本語） | Teams課内会議アーカイブ |
| パッケージ内displayName（英語名） | PA_Migrate_Teams_Meeting_Archive_To_SPO |
| フローID（definition.json内のname） | 2fe554b1-6ba6-4ce0-962c-07bde4bdb6ee（匿名の新規GUID） |
| 種別 | インスタントクラウドフロー |
| トリガー | manual（type=Request, kind=Button）の1つのみ |
| フロー数 | 1（子フローなし） |
| バージョン | v10（27章にv2〜v10の修正履歴を記載。DryRun時の.doc未作成／添付失敗の封じ込め／添付リンク判定の3点(v2)、SetVariable自己参照の全面除去(v4)、uriComponentエンコード等の堅牢化(v5)、コネクタ出力body/参照欠落5箇所の修正(v6)、PostItem保存エラーのSharePoint REST置換(v7)、台帳・実行ログのリスト操作サイト分離(v8)、実行時404エラーの根本修正＋添付有無の明示分岐(v9)、**保存先フォルダー事前作成・GetFileItem全廃による決定的URL構築(v10)**を反映済み） |

匿名化について: 元になった雛形パッケージに含まれていた実際のメールアドレス・creator.id・tenantId・接続GUIDは、本パッケージには一切含まれていません。`connectionReferences`の`connectionName`は匿名GUID、`metadata.creator`は空オブジェクト、`details.creator`は`"N/A"`としています。認証情報・トークンも埋め込んでいません（`authentication`はX-MS-APIM-Tokens参照式のみで、これは雛形と同一の標準的な形であり秘密情報ではありません）。

> **重要**: 検証済みなのは、5つのJSONファイルすべてがパースできること、`runAfter`参照がすべて同階層に存在すること、`InitializeVariable`がすべてトップレベルにあること、参照している変数28個と初期化している変数28個が過不足なく一致していること（v4で`varDocHtmlParts`廃止により27→26、v6で`varRunLogList`追加により26→27、v8で`varListSiteAddress`追加により27→28。v9・v10では変数の増減なし。詳細は27章）、参照先のアクション出力がすべて実在すること、operationIdが実在する**5種類**のみであること（v7で`PostItem`を廃止して7→6種類、**v10で`GetFileItem`を廃止して6→5種類**）、ユーザー固有情報が混入していないこと、ZIPを再展開した結果が雛形と同一構造であることです。総アクション数はv10で**148**（v9の139に、保存先フォルダー事前作成・検証の`Scope_05`系7アクション、`Compose_Source_Url`、`Compose_Saved_File_Url`、サニタイズ2件（`Replace_Invalid_Hash`／`Replace_Invalid_Percent`）を追加し、`Get_Saved_File_Properties`／`Get_Saved_Archive_Properties`（`GetFileItem`）2件を削除した分。10章・27章参照）。SetVariableの自己参照は0件（v4で全面除去。27章参照）、コネクタ出力の`body/`参照欠落も0件（v6で修正。27章参照）、`PostItem`の残存も0件（v7で新設した機械検査。27章参照）、旧`Scope_30_Save_Attachments`の残存も0件（v9で新設した機械検査）、**`GetFileItem`／`{Link}`の残存も0件（v10で新設した機械検査。変更履歴内の言及を除く。27章参照）**です。**実環境での経緯**: v3のZIPはユーザー環境でのインポート自体には成功しましたが、その後の保存で`WorkflowRunActionInputsInvalidProperty`（SetVariable自己参照）エラーが発生し、v4で原因を除去しました。その後、v6のZIPはインポート自体には問題がなかったものの、保存時に3件目の実環境エラー（`OpenApiOperationParameterValidationFailed`。`PostItem`の`item`欠落）が発生し、v7でPostItemをSharePoint「HTTP要求を送信します」(REST)に置き換えて原因を除去しました（15.6節）。v8では、台帳・実行ログの2リストをファイル保存先（`varSiteAddress`＝mROOM）とは別サイト（`varListSiteAddress`＝pjteam）に作成するユーザー決定に伴い、`Get_Ledger_Existing`のサイト参照とREST4アクションの静的サイト値を変更しています（10.1節・15.2節・8.3節参照）。**v8のZIPは実際に実環境でインポート・保存・実行に成功し、`MeetingArchiveRunLog`への書き込みまで到達しましたが、実行時に`Get_Source_File_Content`が404エラー（4件目の実環境エラー）で失敗しました。** v9はこの404の原因を`contentUrl`由来のサイト・パス動的導出で修正し、**v9のZIPは実際に実環境でエンドツーエンドで完走しました**が、**全添付がStatus=Failedになる**という5件目の実環境事象が発生しました（27.1節v10項参照）。v10はこの事象への対応（保存先フォルダー事前作成・`GetFileItem`全廃による決定的URL構築等）ですが、**修正後の実環境での再実行はまだ行っていません**。「全添付Failedが解消される」「正しく実行できる」こと自体を保証するものではなく、静的検証（JSON構文・参照整合・自己参照監査・`PostItem`／`GetFileItem`残存監査等）の結果であることにご留意ください。

---

## 7. フローのインポート

インポートの詳細な画面操作（スクリーンショット相当の逐次手順）は、別紙 `power_automate_import_guide.md`（同じspecフォルダー） を参照してください。本章では、本書の8章以降を読み進めるために必要な要点だけをまとめます。

### 手順の要点

1. ブラウザで `https://make.powerautomate.com` を開き、対象の環境（**要実環境確認**: どの環境にインポートするかは組織のポリシーに従う）を選択する。
2. 左側ナビゲーションの「マイフロー」を開く。
3. 画面上部の「インポート」→「パッケージ（レガシー）」を選択する。
4. 「アップロード」で `../release/PA_Migrate_Teams_Meeting_Archive_To_SPO_20260718012104.zip` を指定する。
5. インポート画面に表示される関連リソース一覧（今回は接続3つ: Microsoft Teams／SharePoint／Content Conversion）について、それぞれ「新規作成として(Create as new)」を選ぶか、既存の接続があれば選択する。
6. 「インポート」ボタンをクリックし、完了を待つ。
7. インポート後、「マイフロー」一覧に表示名「Teams課内会議アーカイブ」のフローが1つだけ追加されていることを確認する。

インポート直後は、接続が正しく解決されていない状態（未選択・エラー表示）になっている場合があります。次の8章で、3つの接続の選択とSharePointアクションのサイト・リストの確認を行います。

---

## 8. 接続の設定

### 8.1 3つのコネクタ接続の選択・作成

インポートしたフローを開き（「編集」）、次の3種類のアクションを順に開いて、接続が正しく設定されているか確認します。接続が未設定・エラー表示の場合は、その場で「サインイン」または「新規作成」を行います。

| 接続対象コネクタ | 該当アクション（代表例） | 必要な権限（5章参照） |
|---|---|---|
| Microsoft Teams | `Get_Channel_Messages`、`Get_Message_Replies` | 対象チーム（`varTeamId`）のメッセージ閲覧 |
| SharePoint | `Create_Destination_Folder_L1`〜`L4`、`Verify_Destination_Folder`（**v10で追加**。10.2節参照）、`Get_Ledger_Existing`、`Create_Attachment_File`、`Create_Ledger_Item`、`Get_Source_File_Content`、`Create_Archive_Document`、`Create_Run_Log`、`Create_Error_Log` | 保存先サイト（`varSiteAddress`）への編集権限 |
| Content Conversion | `Convert_Body_Html_To_Text` | 不要（認証なし。接続作成の案内が出ない場合あり） |

補足:
- 1つのコネクタにつき接続は1つ作成すれば、同じコネクタを使う他のすべてのアクションに自動的に反映されます（アクションごとに個別作成する必要はありません）。
- Content Conversionは認証不要のコネクタのため、「続行」をクリックするだけで接続作成が完了する場合があります。

### 8.2 SharePointアクションのサイト・リスト（テーブル）の確認

このフローのSharePoint系アクションは、「サイトのアドレス」欄・「リストまたはライブラリ」欄の多くが、固定選択ではなく**変数を参照する式**（`variables('varSiteAddress')`、`variables('varListSiteAddress')`、`variables('varLibrary')`、`variables('varLedgerList')`など）になっています。サイト・ライブラリ・台帳リスト名を1か所（10章の初期設定変数）だけ変更すればフロー全体に反映される設計です。**v8で`varSiteAddress`（ファイル保存系。mROOM）と`varListSiteAddress`（リスト操作系。pjteam）の2系統に分かれた**ため、どちらの変数を確認すべきかはアクションによって異なります（10.1節参照）。

インポート直後は、この「式が入っている」状態をPower Automateの画面がうまく認識できず、フィールドが赤枠・エラー表示になることがあります。次の手順で確認してください。

1. 対象のSharePointアクションを開く。
2. 「サイトのアドレス」欄・「リストまたはライブラリ」欄の右側にある「fx」（式）アイコン、または雷アイコンをクリックし、中身が `variables('varSiteAddress')` 等の式のままになっているか確認する。
3. もしフィールドが空欄・赤枠のままの場合は、一度ドロップダウンから実際のサイト・リストを選択したあと、再度「fx」アイコンから元の式（`variables('varSiteAddress')`等）に戻す。
4. これを、8.1表の対象アクションすべてで行う（**要SharePointコネクタ確認**: この挙動はコネクタのバージョン・環境により異なる場合があります）。

| アクション名 | 「サイトのアドレス」欄の値 | 「テーブル」欄の値 | 備考 |
|---|---|---|---|
| Get_Ledger_Existing | `variables('varListSiteAddress')`（**v8で変更**。旧:`varSiteAddress`。10.1節参照） | `variables('varLedgerList')` | 台帳リスト名（変数） |

**v10でのGetFileItem廃止**: 旧`Get_Saved_File_Properties`／`Get_Saved_Archive_Properties`（いずれも「ファイルのプロパティの取得」・operationId=GetFileItem）は**v10で削除**しました。保存後ファイルのURLは、これらを呼び出さずCreateFileの成功事実から直接組み立てる方式に変わっています（16章参照）。そのため、上表にこの2アクションは登場しません。

`Get_Ledger_Existing`の「サイトのアドレス」が他のSharePointアクション（`varSiteAddress`参照）と異なる変数を参照している点に注意してください。台帳（`MeetingArchiveLedger`）がファイル保存先とは別サイト（pjteam）に作成されているためです（10.1節）。

`Create_Attachment_File`・`Create_Archive_Document`（CreateFile）と`Get_Source_File_Content`（GetFileContentByPath）は「テーブル」欄を持たず、代わりに「サイトのアドレス」（`variables('varSiteAddress')`）と「フォルダーのパス」（`concat('/', variables('varLibrary'), '/', variables('varDestinationPath'))`）で保存先・取得元を指定しています。

### 8.3 台帳・実行ログ書込み4アクション（REST。v7でPostItemから変更・v8でサイト変更）

`Create_Ledger_Item`／`Create_Ledger_Item_Failed`／`Create_Run_Log`／`Create_Error_Log`の4アクションは、**v7でSharePoint「項目の作成」(PostItem)からSharePoint「HTTP要求を送信します」(REST)に置き換わっています**（なぜ置き換えたかは15.6節を参照）。この4アクションは「テーブル」欄を持たず、代わりに次の入力を持ちます。

| アクション名 | サイトのアドレス | URI（リスト部分の式） |
|---|---|---|
| Create_Ledger_Item | `https://metijapan.sharepoint.com/teams/pjteam_220400119`（**静的な選択値**。**v8で変更**。旧: mROOM_240600018） | `concat('_api/web/lists/getbytitle(''', variables('varLedgerList'), ''')/items')` |
| Create_Ledger_Item_Failed | 同上（静的な選択値） | 同上（`varLedgerList`参照） |
| Create_Run_Log | 同上（静的な選択値） | `concat('_api/web/lists/getbytitle(''', variables('varRunLogList'), ''')/items')` |
| Create_Error_Log | 同上（静的な選択値） | 同上（`varRunLogList`参照） |

> **重要（サイト変更時の再設定ポイント）**: この4アクションの「サイトのアドレス」は、他のSharePointアクションと違い変数を参照する式ではなく、**ドロップダウンで選択した静的な値**になっています（雛形の実エクスポートで保存実績のある形。15.6節で理由を説明します）。**v8で、この静的な値をファイル保存先サイト（mROOM）とは別の、台帳・実行ログリストの作成先サイト（`https://metijapan.sharepoint.com/teams/pjteam_220400119`）へ変更しました**（10.1節参照）。そのため、**保存先サイトを変更する場合は、10章の`varListSiteAddress`（台帳・実行ログのサイト）変更に加えて、この4アクションを個別に開いて「サイトのアドレス」を選び直す必要があります**（添付・総括docの保存先である`varSiteAddress`とは別物である点に注意してください）。リスト名（台帳／実行ログ）は引き続き`varLedgerList`／`varRunLogList`変数で一元管理されているため、リスト名だけを変える場合は10章の変数変更のみで反映されます。

---

## 9. 手動トリガーの入力

トリガー「フローを手動でトリガーする」には、次の3つの入力があります（`definition.json`の`triggers.manual.inputs.schema`どおり）。

| 表示名 | 内部名（スキーマキー） | 型 | 既定値 | 説明 |
|---|---|---|---|---|
| 取得対象日数 | `LookbackDays` | 数値 | 7 | 実行日時から何日前までのTeams投稿を取得するか（7/30/365/730） |
| テスト実行 | `DryRun` | はい/いいえ | はい（true） | はい＝本番保存せずテスト |
| 処理済みファイルを再処理する | `ForceReprocess` | はい/いいえ | いいえ（false） | はい＝台帳を無視して再保存 |

補足:
- 本パッケージは`definition.json`を直接記述して作成しているため、内部名（スキーマキー）は表示名どおり`LookbackDays`／`DryRun`／`ForceReprocess`に固定されています。フロー内の式（`triggerBody()?['LookbackDays']`等）はすべてこの内部名を直接参照しています。
- もし今後、画面の「+ 入力の追加」から手動でトリガー入力を追加・変更する場合、Power Automateの標準UIでは内部名が自動採番される場合があります（例: `text_1`など）。既存の3入力を編集し直す必要は通常ありませんが、追加する場合はご注意ください。
- **重要**: `DryRun`（テスト実行）は、添付ファイル本体の保存（`Condition_Has_File_Attachments`内・15章。**v9で名称変更**。旧`Scope_30`）と、会議一覧のWord互換ファイル（Scope_60・20章）の**両方**をスキップします（`Condition_DryRun_Archive`。20章参照）。`DryRun=はい`のあいだは、SharePointの保存先フォルダーに何も新規作成されません。
- `EndDateUtc`（取得終了日時）に相当するトリガー入力はありません。終了日時は常に実行時点の`utcNow()`です。取得開始日時は「実行時点 − LookbackDays日」で自動計算されます（10章）。
- `LookbackDays`は、フロー先頭の`Compose_EffectiveLookbackDays`（10章）で安全化されています。未入力・null・0以下の値が渡された場合は既定の`7`に丸められ、正の整数が入力された場合のみその値がそのまま採用されます（730日超の上限チェックはフロー側では行っていないため、極端な大きい値を入力しないよう運用で注意してください）。

---

## 10. 初期設定変数

トリガーの直後、フローのいちばん最初に「作成(Compose)」1個と、28個の「変数を初期化する(Initialize variable)」アクションが**すべてトップレベル（どのScopeの中にも入れない状態）**で並んでいます。Power Automateの「変数を初期化する」は同じ変数名につき1回しか実行できず、Scopeの中では条件分岐やループの都合で2回実行されるおそれがあるため、Scopeの外（ルート階層）にまとめて置く設計です。

### 10.0 LookbackDaysの安全化（Compose_EffectiveLookbackDays）

トリガー直後・最初のInitializeより前に、「作成(Compose)」を1つ追加し、名前を`Compose_EffectiveLookbackDays`に変更します。式:

```
if(greater(int(coalesce(triggerBody()?['LookbackDays'], 0)), 0), int(coalesce(triggerBody()?['LookbackDays'], 7)), 7)
```

`LookbackDays`が未入力・null・0以下の場合は既定値`7`に丸め、正の整数が入力された場合のみその値をそのまま採用します。この安全化がないと、`triggerBody()?['LookbackDays']`が`0`や負数のときに取得期間が不正になる可能性がありました。次の`Initialize_LookbackDays`は、この`Compose_EffectiveLookbackDays`の出力を参照します。

以下は実際の`runAfter`のつながり順（＝画面上での表示順）です。`Compose_EffectiveLookbackDays`の直後から、「新しいステップ」→検索「変数を初期化する」→追加→名前を変更→型と値を入力、を28回繰り返します。

| # | アクション名 | 変数名 | 型 | 初期値の式・値 |
|---|---|---|---|---|
| 1 | Initialize_RunId | varRunId | 文字列 | `guid()` |
| 2 | Initialize_LookbackDays | varLookbackDays | 整数 | `outputs('Compose_EffectiveLookbackDays')` |
| 3 | Initialize_EndDateUtc | varEndDateUtc | 文字列 | `utcNow()` |
| 4 | Initialize_StartDateUtc | varStartDateUtc | 文字列 | `addDays(variables('varEndDateUtc'), sub(0, variables('varLookbackDays')))` |
| 5 | Initialize_TeamId | varTeamId | 文字列 | `a7ac0c68-87ba-4613-8960-13660f0f5f56` |
| 6 | Initialize_ChannelId | varChannelId | 文字列 | `19:53e5d619e45b4fda8d0dc7f2858a9d64@thread.tacv2` |
| 7 | Initialize_SiteAddress | varSiteAddress | 文字列 | `https://metijapan.sharepoint.com/sites/mROOM_240600018`（ファイル保存系専用。10.1節参照） |
| 8 | Initialize_ListSiteAddress | varListSiteAddress | 文字列 | `https://metijapan.sharepoint.com/teams/pjteam_220400119`（**v8で新規追加**。台帳・実行ログのリスト操作専用。10.1節参照） |
| 9 | Initialize_Library | varLibrary | 文字列 | `Shared Documents` |
| 10 | Initialize_DestinationPath | varDestinationPath | 文字列 | `123_伝送システム/00_共用フォルダ/60_庶務担当/99_過去の課内会議` |
| 11 | Initialize_LedgerList | varLedgerList | 文字列 | `MeetingArchiveLedger` |
| 12 | Initialize_RunLogList | varRunLogList | 文字列 | `MeetingArchiveRunLog`（**v6で新規追加**。実行ログリスト名の一元化。21章参照） |
| 13 | Initialize_MessagesArray | varMessagesArray | 配列 | `json('[]')` |
| 14 | Initialize_NextLink | varNextLink | 文字列 | `''`（空文字。Scope_10内で最初のURLを設定） |
| 15 | Initialize_RepliesArray | varRepliesArray | 配列 | `json('[]')` |
| 16 | Initialize_ReplyNextLink | varReplyNextLink | 文字列 | `''` |
| 17 | Initialize_AttachmentCandidates | varAttachmentCandidates | 配列 | `json('[]')` |
| 18 | Initialize_MeetingAttachments | varMeetingAttachments | 配列 | `json('[]')` |
| 19 | Initialize_Meetings | varMeetings | 配列 | `json('[]')` |
| 20 | Initialize_SortedMeetings | varSortedMeetings | 配列 | `json('[]')` |
| 21 | Initialize_DocumentHtml | varDocumentHtml | 文字列 | `''`（**v4以降**: この文字列変数へ「文字列変数に追加」で直接連結する方式に変更。18章参照） |
| 22 | Initialize_MeetingIndex | varMeetingIndex | 整数 | `0` |
| 23 | Initialize_SavedCount | varSavedCount | 整数 | `0` |
| 24 | Initialize_SkippedCount | varSkippedCount | 整数 | `0` |
| 25 | Initialize_FailedCount | varFailedCount | 整数 | `0`（v2で新規追加。添付保存に失敗した件数の集計用。21章参照） |
| 26 | Initialize_ArchiveUrl | varArchiveUrl | 文字列 | `''` |
| 27 | Initialize_RunStatus | varRunStatus | 文字列 | `Failed`（安全側の既定値） |
| 28 | Initialize_ErrorMessage | varErrorMessage | 文字列 | `''` |

28番目の`Initialize_ErrorMessage`の直後に、11章の`Scope_10_Get_Channel_Messages`が続きます。

> **v4での変更**: 旧`Initialize_DocHtmlParts`（varDocHtmlParts・配列）は**廃止**されました。Word用HTMLの組み立て方式を「配列に断片を貯めて最後にjoinする」方式から「文字列変数(varDocumentHtml)へ直接AppendToStringVariableで連結する」方式に変更したため、配列変数そのものが不要になったためです（18章で詳述）。
> **v6での変更**: 上表12番目の`Initialize_RunLogList`（varRunLogList）が新規追加されました。実行ログリスト名`MeetingArchiveRunLog`が固定文字列のハードコードから変数参照に変わり、変更箇所が1か所（本アクション）に一元化されています（21章参照）。
> **v8での変更**: 上表8番目の`Initialize_ListSiteAddress`（varListSiteAddress）が新規追加されました。台帳・実行ログの2リストを、ファイル保存先（`varSiteAddress`＝mROOM）とは別サイト（pjteam）に作成するユーザー決定に伴うものです（10.1節参照）。`Initialize_Library`以降の番号が1つずつ後ろにずれています。
> この結果、変数の総数はv3時点27個 → v4で`varDocHtmlParts`廃止により26個 → v6で`varRunLogList`追加により27個 → **v8で`varListSiteAddress`追加により28個**に変わりました（27章参照）。

### 10.1 サイトが2系統ある理由（ファイル保存＝mROOM／リスト操作＝pjteam。v8で追加）

v8以降、このフローが参照するSharePointサイトは**2つ**に分かれています。

| 変数 | 参照先サイト | 対象アクション |
|---|---|---|
| `varSiteAddress` | `https://metijapan.sharepoint.com/sites/mROOM_240600018` | 保存先フォルダーの事前作成・検証（`Create_Destination_Folder_L1`〜`L4`／`Verify_Destination_Folder`。**v10で追加**）、添付ファイル・総括Word互換ファイルの保存（`Get_Source_File_Content`／`Create_Attachment_File`／`Create_Archive_Document`）、保存後URLの組み立て（`Compose_Saved_File_Url`／`Set_ArchiveUrl`。**v10で追加**） |
| `varListSiteAddress` | `https://metijapan.sharepoint.com/teams/pjteam_220400119` | 台帳（`MeetingArchiveLedger`）・実行ログ（`MeetingArchiveRunLog`）の2リストに対する操作（`Get_Ledger_Existing`の「サイトのアドレス」。ならびに`Create_Ledger_Item`／`Create_Ledger_Item_Failed`／`Create_Run_Log`／`Create_Error_Log`の静的な「サイトのアドレス」の値としても同じサイトを指す） |

**分かれている理由**: 添付ファイル・総括docの保存先フォルダーは実際にmROOMサイト側に存在するため、ファイル保存系のアクションは`varSiteAddress`（mROOM）のまま維持しています。一方、台帳・実行ログの2リストは、別パッケージのリスト自動作成フロー`CreateMeetingArchiveLists`（`../../provision-archive-lists/release/`）の作成先に合わせてpjteamサイトに作成する運用がユーザー決定されたため、リスト操作だけを新変数`varListSiteAddress`へ分離しました。

**再設定時の注意**: この2つのサイトは**独立して変更する必要があります**。片方だけ変更すると、ファイル保存またはリスト操作（台帳検索・ログ書込み）のいずれかが誤ったサイトを参照する状態になります。特に`Create_Ledger_Item`等のREST4アクション（8.3節）は静的な選択値のため、`varListSiteAddress`の値を変えるだけでは反映されず、4アクションを個別に開いて選び直す必要があります。

12章末（12.4節）でこの2つのリストの作成手順を説明します。作成先は`varListSiteAddress`（pjteam）側のサイトです。

### 書き換え箇所（対象環境に合わせて変更する変数）

次の8個は、対象のチーム・チャネル・保存先・ログリストを変更する際に書き換える「定数」です。それぞれのInitializeアクションを開き、「値」欄を実物に置き換えてください。

| 変数名 | 既定値 | 変更する場面 |
|---|---|---|
| varTeamId | a7ac0c68-87ba-4613-8960-13660f0f5f56 | 対象チーム（groupId）を変える場合 |
| varChannelId | 19:53e5d619e45b4fda8d0dc7f2858a9d64@thread.tacv2 | 対象チャネルを変える場合 |
| varSiteAddress | https://metijapan.sharepoint.com/sites/mROOM_240600018 | ファイル保存先SharePointサイトを変える場合 |
| varListSiteAddress | https://metijapan.sharepoint.com/teams/pjteam_220400119 | 台帳・実行ログリストの作成先サイトを変える場合（**v8で新規追加**。10.1節参照。あわせて8.3節のREST4アクションのサイトも個別に変更） |
| varLibrary | Shared Documents | 保存先ライブラリを変える場合 |
| varDestinationPath | 123_伝送システム/00_共用フォルダ/60_庶務担当/99_過去の課内会議 | 保存先フォルダーを変える場合 |
| varLedgerList | MeetingArchiveLedger | 処理台帳リスト名を変える場合 |
| varRunLogList | MeetingArchiveRunLog | 実行ログリスト名を変える場合（**v6で変数化**。旧版はCreate_Run_Log/Create_Error_Logの直接編集が必要でした） |

> **v6で変更**: 実行ログリスト名（`MeetingArchiveRunLog`）は、v5以前は`Create_Run_Log`・`Create_Error_Log`の2アクションに直接ハードコードされ変数化されていませんでしたが、v6で`varRunLogList`に一元化されました。この2アクションの「テーブル」欄は`variables('varRunLogList')`を参照する式になっています（21章参照）。
> **v8で変更**: 上表に`varListSiteAddress`が加わりました。`varSiteAddress`はファイル保存系専用に絞られ、台帳・実行ログのリスト操作は`varListSiteAddress`が担います（10.1節参照）。

### なぜループ内で「初期化」を繰り返さないか

`varRepliesArray`・`varReplyNextLink`・`varAttachmentCandidates`・`varMeetingAttachments`など、会議ごと・添付ごとに使い回す変数は、ここで**1回だけ**初期化し、実際にループへ入るたびは「変数を設定する(Set variable)」で値をリセットする設計です（12章・14章で説明）。これは、`Apply_To_Each_Meeting`等のループの「同時実行を有効にする」がオフであることを前提にしています。

### 10.2 保存先フォルダーの事前作成・検証（Scope_05_Ensure_Destination_Folder。v10新設）

**なぜこのScopeを追加したか**: v9パッケージを実環境で実行したところ、フロー自体はエンドツーエンドで完走した（台帳への`Status=Failed`記録・エラーログ書込みも正常に機能した）ものの、**添付ファイルが1件も保存されず、全件`Status=Failed`になる**という事象が発生しました。原因調査の結果、以下の2点が有力な原因候補として浮かび上がりました。

1. SharePointの「ファイルの作成(CreateFile)」は、指定したフォルダーパスの**中間フォルダーを自動作成しません**。保存先（`varDestinationPath`）が4階層のフォルダー構成で、そのいずれかが未作成だと、添付・総括ファイルの保存が軒並み失敗します。
2. （v9まで存在した）`Get_Saved_File_Properties`（ファイルのプロパティの取得。operationId=GetFileItem）の「テーブル」欄に渡していた`Shared Documents`は、ライブラリの**URLセグメント**であり、ライブラリの表示名やGUIDではありません。日本語のSharePointサイトでは、既定のドキュメントライブラリの表示名が「ドキュメント」であることが多く、`GetFileItem`が表示名ベースでの名前解決を行う場合、`Shared Documents`という値では解決できず全件失敗し得ます（v10で`GetFileItem`自体を廃止した理由。16章参照）。

`Initialize_ErrorMessage`（10章・28番目の変数初期化）の直後に「スコープ」を追加し、名前を`Scope_05_Ensure_Destination_Folder`に変更します。この中で、DryRun=いいえの本番実行時のみ、保存先フォルダーを1階層ずつ作成し、最後に実在を検証します。

#### 手順

1. `Scope_05_Ensure_Destination_Folder`の枠内に「条件(Condition)」を追加し、名前を`Condition_Provision_Destination`に変更する。詳細モードで次の式を入力する（DryRunでない場合のみtrue）。

```
not(equals(coalesce(triggerBody()?['DryRun'], true), true))
```

2. 「はい」の枝に、SharePointコネクタの「HTTP要求を送信します」を4つ、この順で追加する（既存のフォルダーへPOSTすると「既に存在する」旨のエラーになるが、後述のとおりこれは意図的に無視する）。

| # | アクション名 | 主な入力 |
|---|---|---|
| 1 | Create_Destination_Folder_L1 | サイト=`variables('varSiteAddress')`、方法=POST、URI=`_api/web/folders`、ヘッダー（Accept・Content-Typeとも`application/json;odata=verbose`）、本文=`{"__metadata": {"type": "SP.Folder"}, "ServerRelativeUrl": "@{concat(uriPath(variables('varSiteAddress')), '/', variables('varLibrary'), '/', join(take(split(variables('varDestinationPath'), '/'), 1), '/'))}"}` |
| 2 | Create_Destination_Folder_L2 | L1と同型。`ServerRelativeUrl`の`take(split(...), 1)`部分を`take(split(...), 2)`に変更（先頭2階層） |
| 3 | Create_Destination_Folder_L3 | 同様に`take(split(...), 3)`（先頭3階層） |
| 4 | Create_Destination_Folder_L4 | 同様に`take(split(...), 4)`（全4階層） |

3. 4アクションそれぞれについて、「...」→「実行条件の構成」を開き、直前のアクションの「成功した場合」に加えて**「失敗した場合」にもチェックを入れる**（`runAfter`が`["Succeeded", "Failed"]`になる）。L1は`Scope_05`内で最初（`runAfter={}`）のままでよい。

4. 最後に、SharePointの「HTTP要求を送信します」をもう1つ追加し、名前を`Verify_Destination_Folder`に変更する。`runAfter`は`Create_Destination_Folder_L4`の「成功した場合」「失敗した場合」の両方にする。

```
サイト = variables('varSiteAddress')
方法   = GET
URI    = concat('_api/web/GetFolderByServerRelativeUrl(''', uriPath(variables('varSiteAddress')), '/', variables('varLibrary'), '/', variables('varDestinationPath'), ''')')
ヘッダー = Accept: application/json;odata=nometadata
```

#### なぜ「失敗した場合」も後続へ進めるのか（既存エラー許容の設計）

SharePointの`_api/web/folders`へのPOSTは、指定した`ServerRelativeUrl`のフォルダーが**既に存在する場合にエラー**（409相当）を返します。今回は「保存先フォルダーが存在することを保証する」ことが目的であり、「既に存在する」ことはエラーとして扱う必要がありません。そこで、L1〜L4の各アクションの後続runAfterに`["Succeeded", "Failed"]`（成功・失敗のどちらでも次へ進む）を指定し、「既存フォルダーへのエラー」を意図的に無視して次の階層の作成へ進む設計にしています。デザイナー上でこの4アクションが赤い×（失敗）になっていても、それ自体は異常ではありません。

一方、最後の`Verify_Destination_Folder`（GET）は、通常のrunAfter（成功した場合のみ次へ進む）のままにします。ここが失敗した場合は、保存先パスまたは権限に本当に問題がある（フォルダーが作成できていない、権限が無い等）ことを意味し、`Scope_05`自体が失敗扱いとなって`Scope_10`以降が実行されず、`Scope_90_Catch`（21章）が捕捉します。これにより、保存先の問題を実行のごく早い段階で明確な失敗として検出でき、v9で発生した「全添付が黙々と`Status=Failed`になる」という分かりにくい事象を未然に防ぎます。

#### 保存先パスは最大4階層まで対応

`ServerRelativeUrl`の組み立ては`varDestinationPath`を`/`で分割し、先頭1〜4要素を`join`する方式です。**`varDestinationPath`が5階層以上のパスの場合、5階層目以降はこのScope_05では自動作成されません。** 保存先フォルダーの階層を変更する場合は4階層以内に収めるか、`Create_Destination_Folder_L5`等を追加してください。

#### DryRunとの関係

`DryRun=はい`のときは`Condition_Provision_Destination`がfalseとなり、`Scope_05`は何も実行せず成功扱いで終了します。本番の保存先フォルダーに対して、テスト実行のたびにフォルダー作成のリクエストが飛ぶことはありません。

---

## 11. Teams親投稿の取得

`Initialize_ErrorMessage`（10章・28番目の変数初期化）の直後に、「新しいステップ」→検索「スコープ」→追加→名前を`Scope_10_Get_Channel_Messages`に変更、で作成します。この中で、Teamsチャネルの親投稿を`@odata.nextLink`によって全ページ取得します。

### 手順

1. `Scope_10_Get_Channel_Messages`の枠内に「変数を設定する」を追加し、名前を`Set_NextLink_First`に変更する。`varNextLink`に次の式を設定する（1ページ目のURL組み立て）。

```
concat('https://graph.microsoft.com/v1.0/teams/', variables('varTeamId'), '/channels/', uriComponent(variables('varChannelId')), '/messages?$top=50')
```

**v5で変更**: チャネルID（`19:...@thread.tacv2`は`:`と`@`を含む）を`uriComponent()`でURLエンコードするようにしました。teamId（GUID）はエンコード不要のためそのままです（詳細は次節）。

2. `Set_NextLink_First`の直後に「Do until」を追加し、名前を`Do_Until_Messages_Paging`に変更する。終了条件（式）:

```
empty(variables('varNextLink'))
```

「編集」→「変更」で、繰り返しの上限を「カウント: 5000」「タイムアウト: PT1H」に設定する（既定の60回では2年分のページングに不足する可能性があるため）。

3. `Do_Until_Messages_Paging`の枠内に、この順で3アクションを追加する（**v4で構成変更**。旧`Set_MessagesArray`は廃止し、Apply to each＋「配列変数に追加」に置き換えています。理由は次項参照）。

| # | アクション名 | コネクタ/種類 | 入力/式 |
|---|---|---|---|
| 1 | Get_Channel_Messages | Teams「Send a Microsoft Graph HTTP request」 | メソッド=GET、URI=`variables('varNextLink')`、Content-Type=`application/json`。「...」→「設定」で`runAfter`を明示的に`{}`にしておく（v5でコンテナ起点アクションに明示） |
| 2 | Process_Retrieved_Messages | Apply to each | 対象=`coalesce(body('Get_Channel_Messages')?['value'], json('[]'))`。「同時実行を有効にする」は**オフ**。ループ内に「配列変数に追加」を1つ追加し、名前を`Append_Message_To_MessagesArray`に変更する。varMessagesArray へ `item()` を追加する |
| 3 | Set_NextLink | 変数を設定する | varNextLink = `coalesce(body('Get_Channel_Messages')?['@odata.nextLink'], '')`（`runAfter`は`Process_Retrieved_Messages`の成功） |

「新しいステップ」→検索「Send a Microsoft Graph HTTP request」→追加→名前変更→メソッド・URI入力、という要領で1を作成し、続けて「Apply to each」（ループ内に「配列変数に追加」）、最後に「変数を設定する」を追加します。

### なぜ「配列変数に追加」に置き換えたか（v4・重要）

旧版（v3以前）は`Set_MessagesArray`という「変数を設定する」アクションで、`varMessagesArray = union(variables('varMessagesArray'), 新しいページの配列)`という式を使い、1ページ取得するたびに**自分自身**（`varMessagesArray`）を式の中で参照して上書きしていました。この構成のZIPは**インポート自体には成功しましたが、フローを保存しようとした時点で**次のエラーが発生することが実環境で確認されました。

```
WorkflowRunActionInputsInvalidProperty: The inputs of workflow run action 'Set_MessagesArray' of
type 'SetVariable' are not valid. Self reference is not supported when updating the value of
variable 'varMessagesArray'.
```

Power Automateの「変数を設定する(SetVariable)」は、更新対象の変数自身を値の式の中から参照する構成（自己参照）を保存時に拒否します。配列の累積・文字列の連結累積・カウンターの`add(自分, 1)`もすべて同じ理由で保存できません。v4でこの自己参照を全面的に除去し、配列に1件ずつ追加する処理は必ず「Apply to each＋配列変数に追加(AppendToArrayVariable)」（またはカウンターは「変数の値を増やす(IncrementVariable)」）に置き換えています。12章の返信取得・14章の添付候補集約でも同じパターンで置き換えています。

### ページングに関する注意（要確認事項）

- **要実環境確認**: `@odata.nextLink`は絶対URLで返ります。この値をそのまま`Get_Channel_Messages`の「URI」欄に渡して2ページ目以降が正しく応答するか、22章の7日間テストで必ず確認してください。
- `varChannelId`内の`:`（コロン）・`@`の扱いは、**v5で`uriComponent()`によるエンコードに変更し解決済み**です（実働サンプルが`%3A`/`%40`エンコード済みURLで動作している実績を根拠に採用）。teamId（GUID）は元々エンコード不要です。
- `Get_Channel_Messages`の再試行ポリシーは既定（Default）のままにしておくと、429/5xxへ自動対応します。

---

## 12. Teams返信の取得

`Scope_10_Get_Channel_Messages`の直後に「スコープ」を追加し、名前を`Scope_20_Process_Meetings`に変更します。この中で、期間の絞り込み・会議ごとの返信取得・添付抽出・保存・正規化までをまとめて行います（13〜15章・17章前半もこのScopeの中の作業です）。

### 12.1 期間でのフィルタリング

`Scope_20_Process_Meetings`の枠内に「配列のフィルター処理(Filter array)」を追加し、名前を`Filter_Messages_By_Period`に変更します。「From」欄=`variables('varMessagesArray')`。詳細モードに切り替え、次の式を入力します。

```
and(equals(item()?['messageType'], 'message'), and(greaterOrEquals(item()?['createdDateTime'], variables('varStartDateUtc')), lessOrEquals(item()?['createdDateTime'], variables('varEndDateUtc'))))
```

`messageType`が`message`（通常投稿）で、かつ`createdDateTime`が取得期間（`varStartDateUtc`〜`varEndDateUtc`）に収まる投稿だけを残します。

### 12.2 会議（親投稿）ごとのループ

`Filter_Messages_By_Period`の直後に「Apply to each」を追加し、名前を`Process_Each_Parent_Message`に変更します。「以前の手順から出力を選択」欄=`body('Filter_Messages_By_Period')`。「...」→「設定」→「同時実行を有効にする」は**オフ**のままにします（共通変数の使い回しのため）。

以降13〜15章・17章前半のアクションは、すべてこの`Process_Each_Parent_Message`ループの内側に追加していきます。

### 12.3 返信のページング取得

ループ内の実際の並び順では、この返信取得の3アクションは13章で説明する`Compose_Author`〜`Convert_Body_Html_To_Text`の**直後**に置かれます（画面上は「本文の変換」の次に来ます）。読みやすさのため本書では先に説明します。

| # | アクション名 | 種類 | 式 |
|---|---|---|---|
| 1 | Set_ReplyNextLink_First | 変数を設定する | varReplyNextLink = `concat('https://graph.microsoft.com/v1.0/teams/', variables('varTeamId'), '/channels/', uriComponent(variables('varChannelId')), '/messages/', uriComponent(items('Process_Each_Parent_Message')?['id']), '/replies?$top=50')`（**v5でchannelId・messageIdの2箇所を`uriComponent()`化**） |
| 2 | Set_RepliesArray_Reset | 変数を設定する | varRepliesArray = `json('[]')`（自己参照ではないため存続。次項参照） |
| 3 | Do_Until_Replies_Paging | Do until | 終了条件=`empty(variables('varReplyNextLink'))`。制限: カウント5000／タイムアウトPT1H |

`Do_Until_Replies_Paging`の枠内には、この順で3アクションを追加します（**v4で構成変更**。旧`Set_RepliesArray`は廃止し、11章と同じくApply to each＋「配列変数に追加」に置き換えています）。

| # | アクション名 | 種類 | 式 |
|---|---|---|---|
| 1 | Get_Message_Replies | Teams「Send a Microsoft Graph HTTP request」 | メソッド=GET、URI=`variables('varReplyNextLink')`、Content-Type=`application/json`。`runAfter`は`{}`を明示 |
| 2 | Process_Retrieved_Replies | Apply to each | 対象=`coalesce(body('Get_Message_Replies')?['value'], json('[]'))`。「同時実行を有効にする」は**オフ**。ループ内に「配列変数に追加」を1つ追加し、名前を`Append_Reply_To_RepliesArray`に変更する。varRepliesArray へ `item()` を追加する |
| 3 | Set_ReplyNextLink | 変数を設定する | varReplyNextLink = `coalesce(body('Get_Message_Replies')?['@odata.nextLink'], '')`（`runAfter`は`Process_Retrieved_Replies`の成功） |

### なぜ「リセット」が必要か

Power Automateの「変数を初期化する」は1つの変数名につき1回しか実行できません。会議ごとに使い回す`varRepliesArray`／`varReplyNextLink`は、10章でトップレベルに1回だけInitializeし、ループの各反復の先頭では「変数を設定する(Set variable)」でリセットする設計です。`Process_Each_Parent_Message`の「同時実行を有効にする」が**オフ**であることが前提です（オンにすると複数会議が同時にリセット・更新し合い内容が混在します）。`Set_RepliesArray_Reset`は「その回の値で丸ごと上書きする」リセットであり、更新対象自身を式の中で参照する自己参照（11章参照）とは異なるため、v4以降も問題なく存続しています。

- 返信50件超のチャネルを想定し、`Do_Until_Replies_Paging`の上限（カウント5000）を確保しています（受入条件「返信50件超をテストする」に対応）。

### 12.4 事前準備: SharePointリストの作成（処理台帳・実行ログ）

会議処理（15章）と実行ログ記録（21章）で使う2つのSharePointリストを、ここで先に作成しておきます。作成先は**`varListSiteAddress`が指すサイト**（pjteam。10.1節参照）です。ファイル保存先の`varSiteAddress`（mROOM）とは別のサイトである点に注意してください。

> **自動作成という選択肢**: これら2リストは、別パッケージのリスト自動作成フロー**`CreateMeetingArchiveLists`**（`../../provision-archive-lists/release/`配下のZIP）をインポート・実行することで自動的に作成できます。列構成・既定ビューまで自動で組み立てられるため、以下の手動手順を省略できます。手動で作成する場合は、以下の列表・作成手順に従ってください（列構成は自動作成フローと同一です）。

#### MeetingArchiveLedger（処理台帳）

同じ添付（`MessageId`＋`AttachmentId`、返信の場合は＋`ReplyId`）が既に保存済みかをこのリストで判定し、再実行時の無制限複製を防ぎます。

| 列 | 型 | 用途 |
|---|---|---|
| Title | 単一行（既定列。そのまま使用） | IdempotencyKeyを格納 |
| IdempotencyKey | 単一行 | 冪等キー（検索用） |
| RunId | 単一行 | 実行識別子 |
| MessageId | 単一行 | 親投稿のメッセージID |
| ReplyId | 単一行 | 返信ID（親投稿添付は空） |
| AttachmentId | 単一行 | 添付のID |
| OriginalFileName | 単一行 | 元ファイル名 |
| SavedFileName | 単一行 | 保存後ファイル名（yyyyMMdd_元名） |
| SavedFileUrl | **複数行テキスト（書式なし、RichText=FALSE）推奨（「ハイパーリンクまたは画像」型は不可。理由は本節末尾のコラム参照）** | 保存後SharePointファイルのURL（失敗時は空） |
| Status | 単一行（値: Saved/Failed） | 処理結果（**v2**: 添付の保存に失敗した場合は`Failed`が書き込まれます。既存流用でスキップした場合はこのリストへの新規書込み自体を行わないため、`Skipped`という値がこの列に入ることはありません） |
| ErrorMessage | **複数行テキスト（書式なし、RichText=FALSE）推奨** | `Status=Failed`の行にのみ`添付の保存に失敗しました: <保存予定ファイル名>`が入ります（成功時は空文字） |
| ProcessedDateTimeUtc | 単一行 | 処理日時（UTC） |

#### MeetingArchiveRunLog（実行ログ）

フロー1回の実行結果（成功・失敗）を1行ずつ記録します。

| 列 | 型 | 用途 |
|---|---|---|
| Title | 単一行（既定列） | `RunId_summary`または`RunId_error` |
| RunId | 単一行 | 実行識別子 |
| FlowName | 単一行 | `PA_Migrate_Teams_Meeting_Archive_To_SPO`（固定） |
| Level | 単一行（値: Info/Error） | ログレベル |
| ErrorMessage | **複数行テキスト（書式なし、RichText=FALSE）推奨** | エラー時のみ設定 |
| MeetingCount | 単一行（数値可） | 会議件数（成功時のみ） |
| SavedCount | 単一行（数値可） | 保存件数（成功時のみ） |
| SkippedCount | 単一行（数値可） | スキップ件数（成功時のみ） |
| FailedCount | 単一行（数値可） | **（v2で新規追加）** 保存に失敗した添付件数（成功時のみ。21章参照） |
| ArchiveUrl | **複数行テキスト（書式なし、RichText=FALSE）推奨（「ハイパーリンクまたは画像」型は不可。理由は本節末尾のコラム参照）** | 生成したWord互換ファイルのURL（成功時のみ。DryRun時は「作成していません」という案内文字列が入ります。20章参照） |
| Status | 単一行（値: Success/Failed） | 実行結果 |
| OccurredDateTimeUtc | 単一行 | 記録日時（UTC） |

#### 作成手順（両リスト共通）

1. `varListSiteAddress`のサイト（`https://metijapan.sharepoint.com/teams/pjteam_220400119`。**v8でmROOMからpjteamへ変更**。10.1節参照）を開き、「サイトコンテンツ」を開く。
2. 画面上部の「+ 新規」→「リスト」→「空白のリスト」を選択する。
3. 「名前」欄に **`MeetingArchiveLedger`**（またはRunLogの場合`MeetingArchiveRunLog`）を大文字小文字・アンダースコアの有無まで正確に入力し「作成」をクリックする。
4. 作成直後は既定列「Title」のみが存在する。これは削除せずそのまま使う。
5. リスト画面右端の「+ 列の追加」をクリックし、列の種類を選ぶ（「1行テキスト」＝単一行、「複数行テキスト」＝複数行）。複数行テキストを選んだ場合は詳細設定で「テキストの種類」を「書式なし（プレーンテキスト）」にする。
6. 「名前」欄に上表の列名を入力し「保存」をクリックする。
7. 上表の残りの列すべてについて、手順5〜6を繰り返す。

> Status・Level等の列は「選択肢」型ではなく**単一行テキスト**で作成します。Power Automateから任意の文字列をそのまま書き込めるようにするためで、候補外の値が来ても書込み自体が失敗しないようにする配慮です。

> **重要（実働サンプルで実証済みの注意点）**: 上表の列名（`IdempotencyKey`、`SavedFileUrl`等）は、SharePoint画面の「名前」欄に**ASCII英数字のまま**入力してください。日本語などの非ASCII文字を列名に使うと、SharePointが自動生成する内部名が`OData__x30d5__x30a1__x30a4__x30eb_`のようなUnicodeエスケープ形式になり、本フローの式（`item()?['SavedFileUrl']`のように列名を直接キーとして参照する形）と一致しなくなります。列の「表示名」を後から日本語に変更するのは問題ありませんが、**作成時の名前（＝内部名の元）は必ずASCII英数字にする**ことが必要です。

> **重要（v7で追加。RESTでの書込み方式に伴う注意）**: `SavedFileUrl`・`ArchiveUrl`列は、列の種類を選ぶ際に**「ハイパーリンクまたは画像」型を選ばないでください**。v7で`Create_Ledger_Item`等4アクション（15.6節）がSharePoint「HTTP要求を送信します」(REST)に置き換わっており、送信する本文は単純な文字列（URL文字列そのもの）です。ハイパーリンク型の列にRESTで書き込むには`{"Url": "...", "Description": "..."}`という入れ子オブジェクトが必要ですが、本フローの本文はこの形になっていないため、ハイパーリンク型の列だと書込みに失敗するおそれがあります。
>
> **列型の推奨（本書で更新）**: `SavedFileUrl`・`ArchiveUrl`・`ErrorMessage`の3列は、**複数行テキスト（書式なし＝RichText FALSE）で作成することを推奨します**。理由は、SharePointの単一行テキスト列は既定で255文字の上限があり、長いURL（クエリ文字列付きの共有リンク等）やエラー文言がこれを超えると値が切り捨てられる可能性があるためです。単一行テキストでも動作はしますが、切り捨てリスクがある点を理解した上で選択してください。列の種類で「複数行テキスト」を選び、詳細設定の「テキストの種類」を「書式なし（プレーンテキスト）」にすれば、RESTへの単純文字列書込みと問題なく整合します。`ErrorMessage`等の他の自由記述列も、選択肢型やハイパーリンク型ではなく通常のテキスト型（単一行／複数行）で作成すれば問題ありません。

---

## 13. 会議情報の作成

`Process_Each_Parent_Message`ループの先頭（実際の並び順もここが先頭です）に、この順で5つのアクションを追加します。

| # | アクション名 | 種類 | 式 |
|---|---|---|---|
| 1 | Compose_Author | 作成(Compose) | `if(empty(trim(coalesce(items('Process_Each_Parent_Message')?['from']?['user']?['displayName'], ''))), '不明', trim(coalesce(items('Process_Each_Parent_Message')?['from']?['user']?['displayName'], '')))` |
| 2 | Compose_Organizer | 作成(Compose) | `不明`（固定文字列） |
| 3 | Compose_MeetingDate | 作成(Compose) | `formatDateTime(convertFromUtc(items('Process_Each_Parent_Message')?['createdDateTime'], 'Tokyo Standard Time'), 'yyyy-MM-dd')` |
| 4 | Compose_PostedDateTimeJst | 作成(Compose) | `concat(formatDateTime(convertFromUtc(items('Process_Each_Parent_Message')?['createdDateTime'], 'Tokyo Standard Time'), 'yyyy-MM-ddTHH:mm:ss'), '+09:00')` |
| 5 | Convert_Body_Html_To_Text | Content Conversion「Html to text」 | パラメータ`Content`=`coalesce(items('Process_Each_Parent_Message')?['body']?['content'], '')` |

「新しいステップ」→検索「作成」（Compose）→追加→名前変更→式入力、を4回、続けて「Html to text」を検索して追加、という要領で作成します。

### 投稿者（Compose_Author）

`from.user.displayName`を取得し、空・null（退職者や外部ユーザー等でnullになる場合を含む）なら「不明」にフォールバックします。`trim`と`empty`で判定しているため、空白のみの表示名も「不明」扱いになります。

### 主催者（Compose_Organizer）— 重要な設計判断

主催者は**常に固定文字列「不明」**です。投稿者をそのまま主催者として扱うことはしていません。Teamsの通常のチャネル投稿には「主催者」に相当する情報が含まれておらず、Graphの会議オブジェクト（online meeting）と関連付けない限り正確な主催者は判定できないため、誤った情報を表示するより「不明」と明示する方針にしています。会議情報（online meetingのorganizer等）から補完する拡張を行う場合は、このComposeの式を差し替えてください。

### 会議日付（Compose_MeetingDate）

会議日付は「投稿日時（`createdDateTime`）をTokyo Standard Timeに変換した`yyyy-MM-dd`」を**唯一の判定方法**として採用しています。本文中の「〇月〇日開催」といった記載から日付を抽出する方式は、Power Automateの標準式に正規表現関数がなく確実に実装できないため採用していません（**要実環境確認**: 将来的に拡張する場合の検討事項）。

### 本文プレーンテキスト化（Convert_Body_Html_To_Text）

Teams投稿本文はHTML形式（`body.content`）で返ってきます。Content Conversionコネクタの「Html to text」でプレーンテキスト化することで、`<script>`等のタグそのものが除去された状態になります。このプレーンテキストは、後段（18章）でさらにHTMLエスケープしてからWord用HTMLへ埋め込むため、二重に安全な処理になっています。

> **重要な注意**: パラメータのキー名は`Content`です（`html`ではありません）。`../../../../../references/official_reference_findings.md`で公式資料により確認済みです。キー名を誤ると入力が渡らずエラーになるため、動的なコンテンツパネルでキー名を必ず確認してください。

---

## 14. 添付ファイルの取得

`Do_Until_Replies_Paging`（12章）の直後に続けて、親投稿・返信それぞれの添付ファイル候補を集約し、会議資料として扱うものだけに絞り込みます。

### 14.1 親投稿の添付を候補へ追加

| # | アクション名 | 種類 | 式 |
|---|---|---|---|
| 1 | Select_Parent_Attachments | 選択(Select) | From=`coalesce(items('Process_Each_Parent_Message')?['attachments'], json('[]'))`。マップ: `attachment`=`item()`、`sourceReplyId`=`''` |
| 2 | Set_AttachmentCandidates_Parent | 変数を設定する | varAttachmentCandidates = `body('Select_Parent_Attachments')` |

親投稿自身の添付には返信IDが無いため、`sourceReplyId`は空文字にしておきます。

### 14.2 各返信の添付を候補へ追加

「Apply to each」を追加し、名前を`Process_Each_Reply`に変更します。「以前の手順から出力を選択」欄=`variables('varRepliesArray')`。「同時実行を有効にする」は**オフ**のままにします。ループ内に以下2アクションを追加します（**v4で構成変更**。旧`Append_Reply_Attachment_Candidates`という名前のアクションは、名前に反して実体は`union`自己参照の「変数を設定する」でした。11章・12章と同じ理由で保存エラーの原因になるため、Apply to each＋「配列変数に追加」に置き換えています）。

| # | アクション名 | 種類 | 式 |
|---|---|---|---|
| 1 | Select_Reply_Attachments | 選択(Select) | From=`coalesce(items('Process_Each_Reply')?['attachments'], json('[]'))`。マップ: `attachment`=`item()`、`sourceReplyId`=`items('Process_Each_Reply')?['id']` |
| 2 | Process_Each_Reply_Attachment | Apply to each | 対象=`body('Select_Reply_Attachments')`。「同時実行を有効にする」はオフ。ループ内に「配列変数に追加」を1つ追加し、名前を`Append_Reply_Attachment_Candidate`に変更する。varAttachmentCandidates へ `item()` を追加する |

各返信の添付には、その返信自身のID（`sourceReplyId`）を紐付けます。後段の冪等キー生成（15章）で使用します。

> **名前でなく`type`で判定する教訓**: 旧`Append_Reply_Attachment_Candidates`は「Append」という名前が付いていましたが、実際のアクション種別（`type`）は`SetVariable`であり、値の式が更新対象の`varAttachmentCandidates`自身を参照する自己参照でした。アクション名の見た目に惑わされず、`type`が`SetVariable`かどうかで自己参照の危険性を判断する必要があります。

### 14.3 ファイル添付だけへの絞り込み

`Process_Each_Reply`ループの直後（外側）に「配列のフィルター処理(Filter array)」を追加し、名前を`Filter_File_Attachments`に変更します。「From」欄=`variables('varAttachmentCandidates')`。詳細モードで次の式を入力します（**v9で3つ目の条件`contains(...)`を追加、v10でエンコード済みURL対応のorを追加**）。

```
and(
  and(
    equals(item()?['attachment']?['contentType'], 'reference'),
    not(empty(coalesce(item()?['attachment']?['contentUrl'], '')))
  ),
  or(
    contains(coalesce(item()?['attachment']?['contentUrl'], ''), '/Shared Documents/'),
    contains(coalesce(item()?['attachment']?['contentUrl'], ''), '/Shared%20Documents/')
  )
)
```

`contentType`が`reference`（ファイルへの参照）で、かつ`contentUrl`が空でないものだけを残します。これにより、Teamsのカード（会議招待カード等）や画像プレビュー、会議オブジェクトへの参照は除外され、実際にファイルへのリンクを持つ添付だけが対象になります。

> **v9で追加した条件（`contains(...,'/Shared Documents/')`）**: 実環境での初実行で、後段の`Get_Source_File_Content`（15.5節）が404エラーになる事象が発生しました。原因調査の結果、Teamsチャネル添付の`contentUrl`は必ず「サイトURL＋`/Shared Documents/`＋パス」という形式であることが確認できたため、この形式に合致しない添付（外部リンク・タブ参照など、実体がSharePointドキュメントライブラリのファイルではない添付）を、この時点で候補から除外するようにしました。これにより、後段の`Compose_Source_Site`（15.5節）が`/Shared Documents/`の位置を必ず見つけられることが保証されます。詳しい原因・修正内容は15.5節・27.1節（v9）を参照してください。
>
> **v10で追加した`/Shared%20Documents/`（%エンコード済み）のor条件**: v9の実環境実行を分析したところ、Graphが添付`contentUrl`を**%エンコード済み**（`Shared Documents`の空白が`%20`のまま）で返す場合があることが新たに判明しました（.aspxファイルの実例で確認）。v9までの条件は非エンコードの`/Shared Documents/`のみを見ていたため、エンコード済みのURLを持つ添付が本条件をすり抜け、候補の時点で黙って除外されてしまう潜在バグがありました。orで両方の表記を許容することで、この種の添付も正しく候補に残るようになります（15.5節の`Compose_Source_Url`で実際の正規化を行います）。

続けて「変数を設定する」を追加し、名前を`Set_MeetingAttachments_Reset`に変更します。varMeetingAttachments = `json('[]')`（この会議の保存済み添付一覧を空にリセット）。

---

## 15. SharePointへの保存

`Set_MeetingAttachments_Reset`の直後に「条件(Condition)」を追加し、名前を`Condition_Has_File_Attachments`に変更します（**v9でスコープからIfへ変更**。旧`Scope_30_Save_Attachments`）。詳細モードで次の式を入力します。

```
greater(length(body('Filter_File_Attachments')), 0)
```

「はい」の枝（trueの中）に「Apply to each」を追加し、以降の処理をすべてこの中に配置します。「いいえ」の枝（elseブランチ）には何も追加しません（ファイル添付が1件も無い会議では、この条件が単にfalseのまま何もせず後続の`Compose_SortKey`へ進みます）。この中で、添付ファイル1件ごとに「既に保存済みか判定→未保存ならファイル名整形→DryRunでなければ実際にコピー」という一連の処理を行います。

> **v9でスコープから条件（If）に変更した理由（ユーザー提案）**: 旧版では、添付が0件の会議でも`Scope_30_Save_Attachments`（無条件のスコープ）に毎回入り、内側の`Process_Each_Attachment`（Apply to each）が0回だけ反復して終わっていました（実害はありません）。v9では、ファイル添付が実際に1件以上ある場合だけ`Process_Each_Attachment`へ入るよう、明示的な条件分岐に変更しました。
>
> **なぜ「スコープの外側にIfを追加」ではなく「スコープ自体をIfに置き換え」たか**: `Scope_30_Save_Attachments`をそのまま残し、その外側に新しくIfを追加してラップする案も検討しましたが、その場合`Process_Each_Attachment`以下の既存のネスト構造がさらに1段深くなり、Power Automateのネスト深さの上限（8段）を超えてしまいます。そのため「既存のスコープの型そのものをIfへ置き換える」という構成にし、ネストの深さを増やさずに済ませています。`Process_Each_Attachment`以下の子アクション構成・実行順序は変更していません。

### 15.1 添付ごとのループと冪等キー

`Condition_Has_File_Attachments`の「はい」の枝に「Apply to each」を追加し、名前を`Process_Each_Attachment`に変更します。「以前の手順から出力を選択」欄=`body('Filter_File_Attachments')`。「同時実行を有効にする」は**オフ**のままにします。

ループ内の先頭に「作成(Compose)」を追加し、名前を`Compose_IdempotencyKey`に変更します。式:

```
if(
  empty(trim(coalesce(items('Process_Each_Attachment')?['sourceReplyId'], ''))),
  concat(items('Process_Each_Parent_Message')?['id'], '_', items('Process_Each_Attachment')?['attachment']?['id']),
  concat(items('Process_Each_Parent_Message')?['id'], '_', items('Process_Each_Attachment')?['sourceReplyId'], '_', items('Process_Each_Attachment')?['attachment']?['id'])
)
```

親投稿の添付なら`MessageId_AttachmentId`、返信の添付なら`MessageId_ReplyId_AttachmentId`という冪等キーになります。

### 15.2 既存確認（処理台帳の検索）

続けて、SharePoint「複数の項目の取得(Get items)」を追加し、名前を`Get_Ledger_Existing`に変更します。

| 設定項目 | 値 |
|---|---|
| サイトのアドレス | `variables('varListSiteAddress')`（**v8で変更**。旧: `varSiteAddress`。台帳リストがpjteamサイトに作成されるため。10.1節参照） |
| リスト名 | `variables('varLedgerList')` |
| フィルタークエリ($filter) | `concat('IdempotencyKey eq ''', outputs('Compose_IdempotencyKey'), ''' and Status eq ''Saved''')` |
| 上位件数($top) | `1` |

続けて「条件(Condition)」を追加し、名前を`Condition_Already_Saved`に変更します。詳細モードの式:

```
and(
  greater(length(coalesce(body('Get_Ledger_Existing')?['value'], json('[]'))), 0),
  not(equals(coalesce(triggerBody()?['ForceReprocess'], false), true))
)
```

「既に台帳に`Saved`状態で存在し、かつForceReprocessが指定されていない」場合にtrueになります。

**はいの場合（既存を再利用）:**

| # | アクション名 | 種類 | 内容 |
|---|---|---|---|
| 1 | Append_Existing_Meeting_Attachment | 配列変数に追加 | varMeetingAttachments へ `{originalName: coalesce(items('Process_Each_Attachment')?['attachment']?['name'], 'file'), savedName: first(body('Get_Ledger_Existing')?['value'])?['SavedFileName'], savedFileUrl: first(body('Get_Ledger_Existing')?['value'])?['SavedFileUrl'], status: 'Skipped'}` |
| 2 | Increment_SkippedCount_Existing | 変数の値を増やす | varSkippedCount += 1 |

**いいえの場合（未保存、または強制再処理）:** 15.3節へ続きます。

### 15.3 ファイル名の整形（禁止文字の置換）

`Condition_Already_Saved`の「いいえ」の枝に、この順でアクションを追加します。

| # | アクション名 | 式 |
|---|---|---|
| 1 | Compose_Extension | `if(contains(coalesce(items('Process_Each_Attachment')?['attachment']?['name'], 'file'), '.'), concat('.', last(split(coalesce(items('Process_Each_Attachment')?['attachment']?['name'], 'file'), '.'))), '')` |
| 2 | Compose_BaseName | `if(contains(coalesce(items('Process_Each_Attachment')?['attachment']?['name'], 'file'), '.'), substring(coalesce(items('Process_Each_Attachment')?['attachment']?['name'], 'file'), 0, sub(length(coalesce(items('Process_Each_Attachment')?['attachment']?['name'], 'file')), length(outputs('Compose_Extension')))), coalesce(items('Process_Each_Attachment')?['attachment']?['name'], 'file'))` |

続けて、禁止文字（`" * : < > ? / \ | # %`）を1文字ずつ`_`へ置換する「作成(Compose)」を**11個**、この順で追加します（**v10で`Replace_Invalid_Hash`／`Replace_Invalid_Percent`の2段を追加**。前段の出力を次段が受け取る形で連結します）。

```
Replace_Invalid_Quote     : replace(outputs('Compose_BaseName'), '"', '_')
Replace_Invalid_Star      : replace(outputs('Replace_Invalid_Quote'), '*', '_')
Replace_Invalid_Colon     : replace(outputs('Replace_Invalid_Star'), ':', '_')
Replace_Invalid_Lt        : replace(outputs('Replace_Invalid_Colon'), '<', '_')
Replace_Invalid_Gt        : replace(outputs('Replace_Invalid_Lt'), '>', '_')
Replace_Invalid_Question  : replace(outputs('Replace_Invalid_Gt'), '?', '_')
Replace_Invalid_Slash     : replace(outputs('Replace_Invalid_Question'), '/', '_')
Replace_Invalid_Backslash : replace(outputs('Replace_Invalid_Slash'), '\', '_')
Replace_Invalid_Pipe      : replace(outputs('Replace_Invalid_Backslash'), '|', '_')
Replace_Invalid_Hash      : replace(outputs('Replace_Invalid_Pipe'), '#', '_')          ← v10新設
Replace_Invalid_Percent   : replace(outputs('Replace_Invalid_Hash'), '%', '_')          ← v10新設
```

> **v10で`#`・`%`を追加した理由**: 添付ファイルの保存後URLは、v10からGetFileItemを呼び出さず、ファイル名を含めてURLを直接組み立てる方式（`Compose_Saved_File_Url`。15.5節・16章参照）に変わりました。`#`はURLのフラグメント識別子、`%`はURLエンコードの特殊文字であり、ファイル名にこれらの文字がそのまま残っていると、組み立てたURLが意図しない形に解釈されるおそれがあります。決定的URL構築の安全性を高めるため、この2文字も置換対象に追加しました。

続けて2アクションを追加します。

| # | アクション名 | 式 |
|---|---|---|
| 1 | Compose_TrimTrailing | `if(endsWith(trim(outputs('Replace_Invalid_Percent')), '.'), trim(substring(trim(outputs('Replace_Invalid_Percent')), 0, sub(length(trim(outputs('Replace_Invalid_Percent'))), 1))), trim(outputs('Replace_Invalid_Percent')))`（末尾の空白・ピリオドを除去。**v10で入力元が`Replace_Invalid_Pipe`→`Replace_Invalid_Percent`に変更**） |
| 2 | Compose_SavedName | `concat(formatDateTime(items('Process_Each_Parent_Message')?['createdDateTime'], 'yyyyMMdd'), '_', if(greater(length(outputs('Compose_TrimTrailing')), 100), substring(outputs('Compose_TrimTrailing'), 0, 100), outputs('Compose_TrimTrailing')), outputs('Compose_Extension'))` |

`Compose_SavedName`が最終的な保存ファイル名（`yyyyMMdd_元名.拡張子`）です。元ファイル名部分（拡張子除く）が100文字を超える場合は100文字に短縮し、拡張子は保持します。日付は投稿日時（`createdDateTime`）をそのまま`formatDateTime`しています（UTCのまま日付部分を取り出す形。JST変換した`Compose_MeetingDate`とは別の式です）。

### 15.4 DryRunの分岐

続けて「条件(Condition)」を追加し、名前を`Condition_DryRun`に変更します。式: `equals(coalesce(triggerBody()?['DryRun'], true), true)`

**はいの場合（テスト実行。実際には保存しない）:**

| # | アクション名 | 内容 |
|---|---|---|
| 1 | Append_DryRun_Meeting_Attachment | varMeetingAttachments へ `{originalName: 元ファイル名, savedName: '', savedFileUrl: '', status: 'Skipped'}` |
| 2 | Increment_SkippedCount_DryRun | varSkippedCount += 1 |

**いいえの場合（実際に保存）:** 15.5節へ続きます。

### 15.5 実際のファイルコピー（Scope_Save_File）とその成功・失敗の振り分け（v2・v6・v7・v10）

**v2で構成が変わりました。** 危険操作（実際にファイルを取りに行き、コピーする部分）だけを`Scope_Save_File`に閉じ込め、その成功・失敗によって後続の処理を「保存成功」と「保存失敗」の2系統に分岐させ、**添付1件が失敗しても会議処理・フロー全体を止めずに継続する**ようにしています。

**v6で式を修正しました。** 旧`Get_Saved_File_Properties`のid・`Create_Ledger_Item`のSavedFileUrl・`Append_Saved_Meeting_Attachment`のsavedFileUrlは、v5まで`outputs(...)`で参照していましたが、これは常に`null`になる誤りでした（16章で理由を説明します）。v6で`body(...)`に修正しました。

**v7でCreate_Ledger_Item・Create_Ledger_Item_Failedの実装方式が変わりました。** 実環境の保存時に`OpenApiOperationParameterValidationFailed`（`PostItem`の`item`欠落）エラーが発生したため、この2アクションをSharePoint「項目の作成」(PostItem)からSharePoint「HTTP要求を送信します」(REST)に置き換えています。

**v10で保存後URLの取得方式が変わりました。** v9パッケージの実環境実行で全添付が`Status=Failed`になる事象が発生し（10.2節・16章参照）、旧`Get_Saved_File_Properties`（ファイルのプロパティの取得。operationId=GetFileItem）を**廃止**しました。保存後URLは、`Scope_Save_File`の**前**に置く`Compose_Saved_File_Url`で、既知の値（サイト・ライブラリ・保存先パス・ファイル名）から直接組み立てます。あわせて、Graphが返す添付`contentUrl`が%エンコード済みの場合に対応する`Compose_Source_Url`を`Scope_Save_File`の先頭に追加しています。

#### 手順0: Compose_Saved_File_Url（Scope_Save_Fileの直前。v10新設）

`Condition_DryRun`の「いいえ」の枝の**先頭**（`Scope_Save_File`より前）に「作成(Compose)」を追加し、名前を`Compose_Saved_File_Url`に変更します。

```
replace(concat(variables('varSiteAddress'), '/', variables('varLibrary'), '/', variables('varDestinationPath'), '/', outputs('Compose_SavedName')), ' ', '%20')
```

サイトURL・ライブラリ・保存先パス・`Compose_SavedName`（15.3節）で組み立てたファイル名を連結し、空白だけを`%20`に置換した値です。`Create_Attachment_File`（下記手順1の4番目）に渡す`folderPath`／`name`とまったく同じ材料から組み立てているため、`Create_Attachment_File`が成功した時点で「このURLにファイルが存在する」ことが保証されます。

#### 手順1: Scope_Save_File（危険操作のみ・5アクション。**v9でCompose_Source_Site/Compose_Source_Pathを追加、v10でGet_Saved_File_Propertiesを削除しCompose_Source_Urlを追加**）

`Compose_Saved_File_Url`の直後に「スコープ」を追加し、名前を`Scope_Save_File`に変更します。中に、この順で5アクションだけを追加します。

| # | アクション名 | コネクタ/種類 | 主な入力 |
|---|---|---|---|
| 1 | Compose_Source_Url | 作成(Compose)（**v10新設**） | `if(contains(coalesce(items('Process_Each_Attachment')?['attachment']?['contentUrl'], ''), '/Shared%20Documents/'), decodeUriComponent(items('Process_Each_Attachment')?['attachment']?['contentUrl']), items('Process_Each_Attachment')?['attachment']?['contentUrl'])` |
| 2 | Compose_Source_Site | 作成(Compose)（v9新設。**v10で入力元を変更**） | `substring(outputs('Compose_Source_Url'), 0, indexOf(outputs('Compose_Source_Url'), '/Shared Documents/'))` |
| 3 | Compose_Source_Path | 作成(Compose)（v9新設。**v10で入力元を変更**） | `replace(substring(outputs('Compose_Source_Url'), indexOf(outputs('Compose_Source_Url'), '/Shared Documents/')), '%20', ' ')` |
| 4 | Get_Source_File_Content | SharePoint「ファイルコンテンツの取得（パス使用）」 | サイト=`outputs('Compose_Source_Site')`、パス=`outputs('Compose_Source_Path')`、`inferContentType`=true（式自体はv9から不変） |
| 5 | Create_Attachment_File | SharePoint「ファイルの作成」 | サイト=`variables('varSiteAddress')`、フォルダーパス=`concat('/', variables('varLibrary'), '/', variables('varDestinationPath'))`、名前=`outputs('Compose_SavedName')`、コンテンツ=`body('Get_Source_File_Content')` |

**v10でGetFileItemを削除**: 旧`Get_Saved_File_Properties`（サイト=`varSiteAddress`、リスト=`variables('varLibrary')`、id=`body('Create_Attachment_File')?['ItemId']`）は、この5アクション目から**削除**しました。`Create_Attachment_File`が本Scopeの最後のアクションになります。理由・代替方式は16章を参照してください。

> **設定手順（デザイナー操作）**: `Scope_Save_File`の中に「作成(Compose)」を3つ、この順で追加します。1つ目の名前を`Compose_Source_Url`に変更し、上表の式を入力します。2つ目の名前を`Compose_Source_Site`、3つ目を`Compose_Source_Path`に変更し、それぞれ上表の式を入力します（`Compose_Source_Site`・`Compose_Source_Path`とも、入力の中で`items(...)`ではなく`outputs('Compose_Source_Url')`を参照する点に注意してください）。続く`Get_Source_File_Content`の「サイトのアドレス」欄・「パス」欄は、それぞれ`outputs('Compose_Source_Site')`／`outputs('Compose_Source_Path')`のまま変更不要です。

> **`Compose_Source_Url`を追加した理由（v10）**: v9の実環境実行を分析したところ、Graphが添付`contentUrl`を%エンコード済み（`/Shared%20Documents/`）で返す場合があることが判明しました。旧`Compose_Source_Site`／`Compose_Source_Path`は非エンコードの`/Shared Documents/`のみを前提に`indexOf()`で分割していたため、エンコード済みのURLだと`indexOf()`が`-1`になり分割に失敗し、当該添付が黙って処理から外れる潜在バグがありました。`Compose_Source_Url`は`/Shared%20Documents/`を含む場合のみ`decodeUriComponent()`でデコードし、含まない場合（非エンコードの生`contentUrl`）はそのまま通す条件分岐のため、既存の非エンコードURLの経路には影響しません。

> **404エラーの原因とv9での修正（重要・履歴）**: 実環境の初実行で、`Get_Source_File_Content`が「404 File not found」で失敗する事象が発生しました。原因は、Teamsチャネル添付の実体が、保存先の`varSiteAddress`（このフローが総括ファイルや添付コピーを保存するサイト）ではなく、**投稿元のチームのサイト**の`Shared Documents`配下にあることでした。v9で、`contentUrl`自体を`/Shared Documents/`の位置で前後に分割し、前半（サイトURL）を`Compose_Source_Site`、後半（サイト配下のパス）を`Compose_Source_Path`として、`Get_Source_File_Content`にそのまま渡すよう変更し、この404の発生源を無くしました。

#### 手順2: 成功時の後続処理（Scope_Save_Fileの直後・兄弟アクション）

`Scope_Save_File`の**外側**（同じ階層）に、この順で4アクションを追加します（**v7でCompose_Ledger_Bodyが追加され3→4アクションになりました**）。「...」→「実行条件の構成」で、`Create_Ledger_Item`（の直前に置く`Compose_Ledger_Body`）については`Scope_Save_File`行の「成功した場合」のみにチェックを入れます（`runAfter`が`Scope_Save_File`の`["Succeeded"]`になります）。

| # | アクション名 | 種類 | 内容 |
|---|---|---|---|
| 1 | Compose_Ledger_Body | 作成(Compose) | 台帳へ書き込むJSONオブジェクトを組み立てる（内容は下記）。`runAfter`=`Scope_Save_File`の`["Succeeded"]` |
| 2 | Create_Ledger_Item | SharePoint「HTTP要求を送信します」(REST。**v7でPostItemから変更**。15.6節参照) | サイト=`https://metijapan.sharepoint.com/teams/pjteam_220400119`（**静的な選択値**。**v8でmROOMから変更**。10.1節参照）、方法=POST、URI=`concat('_api/web/lists/getbytitle(''', variables('varLedgerList'), ''')/items')`、ヘッダー2行、本文=`string(outputs('Compose_Ledger_Body'))`（設定手順は下記） |
| 3 | Append_Saved_Meeting_Attachment | 配列変数に追加 | varMeetingAttachments へ `{originalName, savedName: outputs('Compose_SavedName'), savedFileUrl: outputs('Compose_Saved_File_Url'), status: 'Saved'}`（**v10で変更**。旧: `body('Get_Saved_File_Properties')?['{Link}']`） |
| 4 | Increment_SavedCount | 変数の値を増やす | varSavedCount += 1 |

`Compose_Ledger_Body`の中身（作成(Compose)の入力欄にJSONオブジェクトとして入力します。次の`Create_Ledger_Item`の本文としてそのままJSON文字列化されます）:

```json
{
  "Title": "@outputs('Compose_IdempotencyKey')",
  "IdempotencyKey": "@outputs('Compose_IdempotencyKey')",
  "RunId": "@variables('varRunId')",
  "MessageId": "@items('Process_Each_Parent_Message')?['id']",
  "ReplyId": "@coalesce(items('Process_Each_Attachment')?['sourceReplyId'], '')",
  "AttachmentId": "@items('Process_Each_Attachment')?['attachment']?['id']",
  "OriginalFileName": "@coalesce(items('Process_Each_Attachment')?['attachment']?['name'], 'file')",
  "SavedFileName": "@outputs('Compose_SavedName')",
  "SavedFileUrl": "@outputs('Compose_Saved_File_Url')",
  "Status": "Saved",
  "ErrorMessage": "",
  "ProcessedDateTimeUtc": "@utcNow()"
}
```

`SavedFileUrl`は**v10で`@outputs('Compose_Saved_File_Url')`に変更**しました（旧: `@body('Get_Saved_File_Properties')?['{Link}']`）。

**`Create_Ledger_Item`（SharePoint「HTTP要求を送信します」）の設定手順**（デザイナー操作の粒度）:

1. `Compose_Ledger_Body`の直後に「新しいステップ」→SharePointコネクタを検索→「HTTP要求を送信します」を追加し、名前を`Create_Ledger_Item`に変更する。
2. 「サイトのアドレス」欄で、ドロップダウンから対象サイト（`https://metijapan.sharepoint.com/teams/pjteam_220400119`。**v8でmROOMから変更**。台帳・実行ログリストの作成先サイト。10.1節参照）を選択する（**式ではなく通常の選択値**。理由は15.6節）。
3. 「方法」欄で`POST`を選択する。
4. 「URI」欄に式を入力する: `concat('_api/web/lists/getbytitle(''', variables('varLedgerList'), ''')/items')`
5. 「ヘッダー」欄に2行追加する。
   - `Accept` : `application/json;odata=nometadata`
   - `Content-Type` : `application/json;odata=nometadata`
6. 「本文」欄に式を入力する: `string(outputs('Compose_Ledger_Body'))`

以降、`Create_Run_Log`・`Create_Error_Log`（21章）も同じ6手順のパターンです。「サイトのアドレス」は毎回同じ静的値を選択し、「URI」の中の変数名（`varLedgerList`／`varRunLogList`）と「本文」の中の`Compose_X_Body`名だけが変わります。

#### 手順3: 失敗時の後続処理（Scope_Save_Fileの直後・兄弟アクション、v2で新規追加・v7でREST化・v10で自己診断化）

同じ階層に、この順で4アクションを追加します（**v7でCompose_LedgerFailed_Bodyが追加され3→4アクションになりました**）。「実行条件の構成」で、`Append_Failed_Meeting_Attachment`について`Scope_Save_File`行の「失敗した場合」「タイムアウトした場合」の2つにチェックを入れます（`runAfter`が`Scope_Save_File`の`["Failed", "TimedOut"]`になります）。

| # | アクション名 | 種類 | 内容 |
|---|---|---|---|
| 1 | Append_Failed_Meeting_Attachment | 配列変数に追加 | varMeetingAttachments へ `{originalName: coalesce(items('Process_Each_Attachment')?['attachment']?['name'], 'file'), savedName: '', savedFileUrl: '', status: 'Failed'}` |
| 2 | Compose_LedgerFailed_Body | 作成(Compose) | 台帳（失敗記録用）のJSONオブジェクトを組み立てる（内容は下記。**v10でErrorMessageを自己診断化**） |
| 3 | Create_Ledger_Item_Failed | SharePoint「HTTP要求を送信します」(REST。**v7でPostItemから変更**) | サイト=静的な選択値（`Create_Ledger_Item`と同一サイト）、方法=POST、URI=`concat('_api/web/lists/getbytitle(''', variables('varLedgerList'), ''')/items')`、ヘッダー2行、本文=`string(outputs('Compose_LedgerFailed_Body'))`（手順は`Create_Ledger_Item`と同じ。上記参照） |
| 4 | Increment_FailedCount | 変数の値を増やす | varFailedCount += 1 |

`Compose_LedgerFailed_Body`の中身（`Compose_Ledger_Body`との違いは太字部分）:

```json
{
  "Title": "@outputs('Compose_IdempotencyKey')",
  "IdempotencyKey": "@outputs('Compose_IdempotencyKey')",
  "RunId": "@variables('varRunId')",
  "MessageId": "@items('Process_Each_Parent_Message')?['id']",
  "ReplyId": "@coalesce(items('Process_Each_Attachment')?['sourceReplyId'], '')",
  "AttachmentId": "@items('Process_Each_Attachment')?['attachment']?['id']",
  "OriginalFileName": "@coalesce(items('Process_Each_Attachment')?['attachment']?['name'], 'file')",
  "SavedFileName": "",
  "SavedFileUrl": "",
  "Status": "Failed",
  "ErrorMessage": "@concat('添付の保存に失敗しました: ', outputs('Compose_SavedName'), ' 元URL=', coalesce(items('Process_Each_Attachment')?['attachment']?['contentUrl'], '(なし)'), ' 保存先=/', variables('varLibrary'), '/', variables('varDestinationPath'))",
  "ProcessedDateTimeUtc": "@utcNow()"
}
```

> **v10でErrorMessageを自己診断化した理由**: v9まではErrorMessageに保存予定だったファイル名（`Compose_SavedName`の出力）しか記録していませんでした。v10では、元の`contentUrl`（`items(...)`の生参照。`Compose_Source_Url`等の途中経過が失敗していてもこのハンドラ自体は壊れないよう、あえて生の値を直接埋め込んでいます）と保存先パスを追記し、**台帳（MeetingArchiveLedger）の1行を見るだけで「どのファイルを」「どこへ保存しようとして」失敗したかを特定できる**ようにしました。再発時の原因調査を大幅に簡略化します（26章参照）。

### 添付1件の失敗を吸収して継続する仕組み（v2で修正済み）

Power Automate（Logic Apps）では、あるアクションの`runAfter`に「失敗した場合(Failed)」「タイムアウトした場合(TimedOut)」を指定し、そのアクションが正常に完了すると、直前の失敗はそこで「処理済み」として扱われ、それより外側（`Process_Each_Attachment`の反復、`Condition_Has_File_Attachments`、`Process_Each_Parent_Message`のループ、`Scope_20_Process_Meetings`…）へは失敗が伝播しません。この仕組みにより、**添付ファイル1件のコピーに失敗しても、その添付を`Status=Failed`として処理台帳・会議データに記録したうえで、他の添付・他の会議の処理、そして`Scope_40`以降（並べ替え・Word生成・保存・実行ログ）は通常どおり継続します。**

> **要実環境確認（残る論点）**: この失敗封じ込めは`Scope_Save_File`（`Compose_Source_Url`／`Compose_Source_Site`／`Compose_Source_Path`／`Get_Source_File_Content`／`Create_Attachment_File`の5アクション。**v10で`Get_Saved_File_Properties`を削除し`Compose_Source_Url`を追加**。子の総数は5のまま）の失敗・タイムアウトに限定されています。`Get_Ledger_Existing`（15.2節）やTeams取得（11章・12章）など、`Scope_Save_File`の外側で発生するエラーには同様の受け皿がなく、そこで失敗した場合は引き続き実行全体が`Scope_90_Catch`（21章）で失敗として扱われます。なお**v10でフロー冒頭に`Scope_05_Ensure_Destination_Folder`（10.2節）を追加**し、保存先フォルダー自体の事前作成・検証を行うようになったため、「フォルダー未作成」が原因の失敗はこの`Scope_Save_File`に到達する前の、より早い段階で明確に検出されるようになりました。

### 添付ファイル本体取得の重要な注意（v9で404の実例が判明・対処済み）

`Get_Source_File_Content`は、Teamsの添付の`contentUrl`から本体コンテンツを取得します。**v8までの実装は、パス部分だけ（`uriPath()`関数で抽出し、`%20`をスペースに戻したもの）を取り出し、それを保存先サイト（`varSiteAddress`）の中で検索する方式でした。この節は元々「もし添付ファイルの実体が保存先サイトとは異なるサイトにある場合、このパス解決が失敗する可能性がある。要実環境確認」という未確認の懸念として記載していましたが、v8を実環境で実行した際に実際にこの懸念が的中し、`Get_Source_File_Content`が404 File not foundで失敗しました。**

原因は、Teamsチャネル添付の実体が保存先サイト（`varSiteAddress`）ではなく、投稿元のチームのサイトにあったことです。v9では、`Compose_Source_Site`／`Compose_Source_Path`（上記手順1参照）で`contentUrl`自体からサイト・パスを動的に導出するよう変更し、この404の発生源を無くしました。取得できない添付があった場合は引き続き`Scope_Save_File`が失敗しますが、その添付だけが`Status=Failed`として記録され、会議処理・フロー全体は継続します。**ただし、v9修正後の実環境での再実行はまだ行っておらず、404が解消されたことの実環境確認はできていません**（実際のcontentUrlを用いた式のシミュレーション検証のみ実施済みです。27章参照）。

### 15.6 なぜPostItemではなくSharePoint「HTTP要求を送信します」(REST)を使うか（v7）

v6までの定義では、`Create_Ledger_Item`・`Create_Ledger_Item_Failed`・`Create_Run_Log`・`Create_Error_Log`の4アクションはいずれもSharePoint「項目の作成」(`operationId=PostItem`)を使用していました。実環境でこのZIP（v6）をインポートし、フローを保存しようとしたところ、次のエラーが発生しました（**実際に発生したエラーメッセージの全文**）。

```
OpenApiOperationParameterValidationFailed: Input parameter 'item' validation failed in workflow
operation 'Create_Run_Log': The API operation 'PostItem' is missing required property 'item'.
```

**原因（Web調査＋定義全体の監査で確定）**: SharePoint「項目の作成」(`PostItem`)は、必須の動的ボディパラメータ`item`（`x-ms-dynamic-schema`で定義される、選択したリストの列構成に応じて動的に生成されるフィールド群）を持っています。デザイナー上で「サイトのアドレス」「リスト名」を**両方とも固定値としてドロップダウンから選択**した場合は、その場でリストの列スキーマを取得でき、`item`パラメータの中身（`Title`・`IdempotencyKey`等の各列）を正しく組み立てられます。しかし本フローでは、リスト名を`variables('varLedgerList')`・`variables('varRunLogList')`という**式**にしており（10章・8.3節。リストの再選択を1か所に集約するため）、この場合は保存時の検証がリストの列スキーマを解決できず、`item`パラメータそのものを構築できずに保存が失敗します。保存時のエラー報告は1アクションずつしか行われないため、エラーメッセージには`Create_Run_Log`だけが表示されていましたが、同じ理由により**同型の`PostItem`アクション4件すべて**（`Create_Ledger_Item`／`Create_Ledger_Item_Failed`／`Create_Run_Log`／`Create_Error_Log`）が同様に保存できない状態でした。実働サンプルの`PostItem`は、サイト・リストとも静的リテラルの構成でのみ保存実績が確認できています。

> **もしリストをデザイナーで静的に選択できるなら、`PostItem`のままで問題ありません。** 今回`PostItem`をやめてSharePoint REST（「HTTP要求を送信します」）に置き換えたのは、あくまで「リスト名を変数化し、変更箇所を10章の初期設定変数1か所に集約する」という設計を維持するためです。リスト名を固定値に戻す（変数化をやめる）運用でよければ、`PostItem`に戻すことも可能です。

**修正内容（`PostItem`×4 → SharePoint「HTTP要求を送信します」+ REST）**:
- 各アクションの直前に「作成(Compose)」でボディのJSONオブジェクトを組み立てる（`Compose_Ledger_Body`／`Compose_LedgerFailed_Body`／`Compose_RunLog_Body`／`Compose_ErrorLog_Body`の4件を新規追加。15.5節・21章参照）
- 「サイトのアドレス」（`dataset`）は**静的な選択値**のまま（雛形の実エクスポートで保存実績が確認できた形。式にすると同様の検証エラーが再発するおそれがあるため。**要実環境確認**）
- 「URI」には`concat('_api/web/lists/getbytitle(''', variables('varLedgerList'または'varRunLogList'), ''')/items')`という式を使う。URIパラメータは動的スキーマの対象外の単純な文字列であるため、式のままでも保存時検証を通過する
- 「ヘッダー」はAccept・Content-Typeとも`application/json;odata=nometadata`
- 「本文」は`string(outputs('Compose_X_Body'))`
- アクション名は変更していない（`Create_Ledger_Item`等のまま）ため、後続の`runAfter`参照は無変更
- これら4アクションの出力を後続で参照している箇所はもともと存在しないため、**応答参照の変更はゼロ**です

**`__metadata`が不要な理由と、必要になった場合のフォールバック**: リクエストヘッダーの`Accept`・`Content-Type`を両方とも`application/json;odata=nometadata`にすることで、SharePoint RESTは本文に`__metadata`（アイテムの型情報）を含めない単純なJSONオブジェクトを受け付けます（`../../../../../references/official_reference_findings.md`で公式資料を確認済み）。ただし、テナントの設定によっては、これでも`__metadata`型指定を要求される場合があります。その場合は、`_api/web/lists/getbytitle('リスト名')?$select=ListItemEntityTypeFullName`というGETリクエストで型名（例: `SP.Data.MeetingArchiveLedgerListItem`）を取得し、`Compose_X_Body`のJSONオブジェクトの先頭に`"__metadata": {"type": "取得した型名"}`を追加するアクションを、`Compose_X_Body`と`Create_X`の間に挿入してください。

**他の9アクションは無改修です**（v7当時の構成。`GetFileItem`×2は**v10で削除済み**）: `GetItems`（`Get_Ledger_Existing`）／`GetFileItem`×2（旧`Get_Saved_File_Properties`・`Get_Saved_Archive_Properties`。**v10で廃止**。16章参照）／`CreateFile`×2（`Create_Attachment_File`・`Create_Archive_Document`）／`GetFileContentByPath`（`Get_Source_File_Content`）／Teams`HttpRequest`×2（`Get_Channel_Messages`・`Get_Message_Replies`）／`HtmlToText`（`Convert_Body_Html_To_Text`）は必須の動的ボディを持たないため、式のままの`dataset`/`table`でも保存時検証を通過します（v7時点で全13アクションを一斉に判定した結果）。

検証スクリプトに「`PostItem`が残存していないか」「SharePoint `HttpRequest`アクションの必須キー（dataset/method/uri、POST時はbody）が揃っているか」の機械検査を恒久的に追加しました（27章参照）。

> **v8での追記**: `Create_Ledger_Item`／`Create_Ledger_Item_Failed`／`Create_Run_Log`／`Create_Error_Log`の静的な「サイトのアドレス」は、v8で台帳・実行ログリストの作成先サイト（pjteam）に変更しています（8.3節・10.1節参照）。上記「他の9アクション」に含まれる`Get_Ledger_Existing`も、v8で「サイトのアドレス」が`varSiteAddress`から`varListSiteAddress`へ変更されています（15.2節）。この検証スクリプトには「初期化済みだが未参照の変数」を検出する検査も恒久追加しており、v8の初回ビルドでは、この検査によって`Get_Ledger_Existing`のサイト参照を`varListSiteAddress`へ付け替え忘れていたことを検出・修正した経緯があります。

---

## 16. 保存後URLの取得（v10で決定的構築方式へ全面変更）

添付ファイル（15章）とWord互換ファイル（20章）のいずれも、SharePoint「ファイルの作成(Create file)」の実行結果自体にはWebURLが含まれません。**v10では、保存後URLを追加のプロパティ取得なしに、既知の値（サイト・ライブラリ・保存先パス・ファイル名）から直接組み立てます。**

| 用途 | URL組み立てアクション | 式 |
|---|---|---|
| 添付ファイル | Compose_Saved_File_Url（`Scope_Save_File`の直前。15.5節参照） | `replace(concat(variables('varSiteAddress'), '/', variables('varLibrary'), '/', variables('varDestinationPath'), '/', outputs('Compose_SavedName')), ' ', '%20')` |
| Word互換ファイル | Set_ArchiveUrl（`Create_Archive_Document`の直後。20章参照） | `replace(concat(variables('varSiteAddress'), '/', variables('varLibrary'), '/', variables('varDestinationPath'), '/', outputs('Compose_ArchiveFileName')), ' ', '%20')` |

いずれも「サイトURL＋ライブラリ＋保存先パス＋ファイル名」を`/`で連結し、空白だけを`%20`に置換した文字列です。`Create_Attachment_File`／`Create_Archive_Document`の`folderPath`／`name`の組み立てと同じ材料を使っているため、CreateFileが成功した時点で「このURLにファイルが存在する」ことが直接保証されます。

### なぜ`{Link}`（GetFileItem）をやめたか（v10）

v9まではこの節で、SharePoint「ファイルのプロパティの取得(Get file properties／operationId: GetFileItem)」を呼び出し、その出力の`{Link}`キーから保存後URLを取得する方式を採っていました（`Get_Saved_File_Properties`／`Get_Saved_Archive_Properties`の2アクション）。

> **v9パッケージを実環境で実行したところ、全添付が`Status=Failed`になる事象が発生しました。** 新しい実行証跡を分析したところ、失敗した添付の`contentUrl`自体は正しい形式であり、`Get_Source_File_Content`（添付本体の取得）は成功していたと推定されます。原因調査で最有力候補と判断したのが、`Get_Saved_File_Properties`の「テーブル」欄に渡していた`variables('varLibrary')`（値は`Shared Documents`）です。
>
> **`Shared Documents`はドキュメントライブラリのURLセグメントであり、ライブラリの表示名やGUIDではありません。** 日本語のSharePointサイトでは、既定のドキュメントライブラリの**表示名**が「ドキュメント」であることが多く、`GetFileItem`（GetFileItem操作は内部的にリストの表示名またはGUIDでの解決を要求する場合があります）に`Shared Documents`という値を渡すと名前解決に失敗し、このアクションが全件失敗していた可能性が最も高いと判断しました。
>
> ※この場合、直前の`Create_Attachment_File`（ファイルの作成）自体は成功しているため、**ファイルは保存先に実際に作成できている**可能性があります。再実行する際は、保存先フォルダーに前回実行の残骸ファイルが残っていないか確認してください（同名ファイルへの`CreateFile`は409相当のエラーになります。10.2節・27章参照）。

v10ではこの`GetFileItem`呼び出し自体を**廃止**し、上表のとおり決定的にURLを組み立てる方式に変更しました。`CreateFile`が指定どおりの`folderPath`・`name`で成功したという事実そのものが、そのURLにファイルが存在することの直接証明になるため、追加のプロパティ取得やライブラリ名の解決が不要になり、v9で疑われた名前解決の問題が構造的に発生し得なくなりました。

### `outputs()`ではなく`body()`で参照していた経緯（v6・履歴）

v10で`GetFileItem`自体を廃止したため、以下は現行の実装には該当しない**過去の経緯の記録**です。v5までの定義では、`Get_Saved_File_Properties`のid（`Create_Attachment_File`の`ItemId`を参照）や保存後URL（`{Link}`）を`outputs(...)`で直接参照しており、`type: OpenApiConnection`のアクションの実行結果が`{statusCode, headers, body}`という封筒（エンベロープ）構造で保持されることを踏まえていなかったため、この5箇所が常に`null`になる潜在バグでした。`DryRun=はい`（既定値）ではこの経路自体が実行されないため見つかりにくく、`DryRun=いいえ`の本番実行で初めて全添付が保存失敗扱いになる状態でした。v6で該当5箇所を`body(...)`参照に修正し、v7でPostItem置換に伴いCompose段へ値が集約されましたが、`body('...')?['{Link}']`という参照式自体はv9まで維持されていました。v10でこの参照式・参照先アクションごと削除しています。

### `{Link}`というキー名について（履歴・v10で対応不要化）

`{Link}`という波括弧付きのキー表記は、SharePointコネクタが返す「委任不可（not delegable）のシステムフィールド」の1つで、コミュニティ（フォーラム等）の情報でのみ確認できるものであり、Microsoft公式資料に直接の明記はありませんでした（`../../../../../references/official_reference_findings.md`参照）。v9まではこの表記が実環境で正しく機能するかどうかが**要SharePointコネクタ確認**の未確定事項として残っていましたが、v10で`{Link}`自体を参照しない決定的URL構築方式に変更したため、この確認事項は**対応不要**になりました（{FullPath}併用のフォールバック案も、同じ理由で不要になっています）。

---

## 17. 会議の日付順ソート

### 17.1 会議データの正規化（Process_Each_Parent_Messageループの末尾）

`Condition_Has_File_Attachments`の直後（`Process_Each_Parent_Message`ループの末尾）に、この順で2アクションを追加します（**v9で変更**。旧`Scope_30_Save_Attachments`の直後）。

| # | アクション名 | 種類 | 式 |
|---|---|---|---|
| 1 | Compose_SortKey | 作成(Compose) | `concat(formatDateTime(convertFromUtc(items('Process_Each_Parent_Message')?['createdDateTime'], 'Tokyo Standard Time'), 'yyyyMMddHHmmss'), '_', items('Process_Each_Parent_Message')?['id'])` |
| 2 | Append_Normalized_Meeting | 配列変数に追加 | varMeetings へ会議データ1件（下表） |

`Append_Normalized_Meeting`が追加する会議データの構造:

| フィールド | 値 |
|---|---|
| meetingDate | `outputs('Compose_MeetingDate')` |
| postedDateTimeJst | `outputs('Compose_PostedDateTimeJst')` |
| messageId | `items('Process_Each_Parent_Message')?['id']` |
| author | `outputs('Compose_Author')` |
| organizer | `outputs('Compose_Organizer')` |
| bodyText | `body('Convert_Body_Html_To_Text')` |
| teamsMessageUrl | `coalesce(items('Process_Each_Parent_Message')?['webUrl'], '')` |
| attachments | `variables('varMeetingAttachments')` |
| sortKey | `outputs('Compose_SortKey')` |

`SortKey`は「JST変換した投稿日時（`yyyyMMddHHmmss`、14桁のゼロ埋め）＋アンダースコア＋メッセージID」という形式です。前半14桁が文字列比較でも日時の早い順に並び、同一秒内の複数投稿はメッセージIDでタイブレークされます。

### 17.2 Scope_40での並べ替え

`Scope_20_Process_Meetings`の直後に「スコープ」を追加し、名前を`Scope_40_Sort_Meetings`に変更します。中に「変数を設定する」を1つ追加し、名前を`Sort_Meetings`に変更します。

```
varSortedMeetings = sort(variables('varMeetings'), 'sortKey')
```

`sort()`関数は昇順ソートのみに対応しており、降順オプションはありません（`../../../../../references/official_reference_findings.md`で確認済み）。今回は「開催日昇順、同日は投稿日時昇順」という要件そのものが昇順ソートで満たせるため、これで十分です。

---

## 18. Word用HTMLの作成

`Scope_40_Sort_Meetings`の直後に「スコープ」を追加し、名前を`Scope_50_Build_Word_Content`に変更します。この中で、並べ替え済みの会議一覧から、Word互換ファイルの中身になるHTML文字列を組み立てます。

> **v4で組み立て方式が変わりました。** 旧版（v3以前）は、配列変数`varDocHtmlParts`にHTML断片を1つずつ追加し、最後に`join(variables('varDocHtmlParts'), '')`で1本の文字列に結合する方式でした。v4で**「文字列変数に追加(Append to string variable)」で`varDocumentHtml`へ直接連結する方式**に統一し、`varDocHtmlParts`という配列変数そのものを廃止しています（10章参照）。本章の手順はすべてこの新方式（AppendToStringVariable）で説明します。

### 18.1 HTML文書のヘッダー

`Scope_50_Build_Word_Content`の枠内に「文字列変数に追加(Append to string variable)」を追加し、名前を`Append_DocumentHtml_Header`に変更します（**v4で`Set_DocumentHtml_Header`から改名・AppendToStringVariable化**）。`varDocumentHtml`へ、次の文字列をそのまま追加します。

```html
<html><head><meta charset="utf-8"><style>@page { size: A4; margin: 20mm; } body { font-family: "Yu Gothic","Meiryo",sans-serif; font-size: 10.5pt; } .page-break { page-break-before: always; } .meeting-title { font-size: 16pt; font-weight: bold; } .label { font-weight: bold; } .attachment-list { margin-top: 8px; }</style></head><body>
```

`varDocumentHtml`は10章で初期化した文字列変数で、以降の各アクションがこの同じ変数へHTML断片を直接追加していきます（配列への一時貯留・join結合は行いません）。

### 18.2 会議ごとのループ

続けて「Apply to each」を追加し、名前を`Apply_To_Each_Sorted_Meeting`に変更します。「以前の手順から出力を選択」欄=`variables('varSortedMeetings')`。「同時実行を有効にする」は**オフ**のままにします。

ループの先頭にはまず改ページ判定（`Condition_Insert_Page_Break`）が入りますが、これは19章で扱います。本章では、その直後（改ページ判定の次）から続く本文組み立てのアクションを説明します。

### 18.3 本文のエスケープと会議見出しHTML

この順で7アクションを追加します。

| # | アクション名 | 種類 | 式 |
|---|---|---|---|
| 1 | Escape_Ampersand | 作成(Compose) | `replace(coalesce(item()?['bodyText'], ''), '&', '&amp;')` |
| 2 | Escape_LessThan | 作成(Compose) | `replace(coalesce(outputs('Escape_Ampersand'), ''), '<', '&lt;')` |
| 3 | Escape_GreaterThan | 作成(Compose) | `replace(coalesce(outputs('Escape_LessThan'), ''), '>', '&gt;')` |
| 4 | Escape_DoubleQuote | 作成(Compose) | `replace(coalesce(outputs('Escape_GreaterThan'), ''), '"', '&quot;')` |
| 5 | Escape_SingleQuote | 作成(Compose) | `replace(coalesce(outputs('Escape_DoubleQuote'), ''), '''', '&#39;')` |
| 6 | Compose_Body_With_Breaks | 作成(Compose) | `replace(replace(outputs('Escape_SingleQuote'), decodeUriComponent('%0D%0A'), '<br>'), decodeUriComponent('%0A'), '<br>')` |
| 7 | Compose_Meeting_Header_Html | 作成(Compose) | 下記参照 |

エスケープの順序は`&`→`<`→`>`→`"`→`'`の順で固定です（先に`&`を変換しないと、後段で追加した`&amp;`等が二重にエスケープされてしまうため）。`Compose_Body_With_Breaks`では、改行コード（CRLF＝`%0D%0A`、LF＝`%0A`）を`<br>`タグへ変換しています。

`Compose_Meeting_Header_Html`の式:

```
concat(
  '<div class="meeting-title">', formatDateTime(item()?['meetingDate'], 'yyyy年M月d日'), '（',
  substring('日月火水木金土', dayOfWeek(item()?['meetingDate']), 1), '）</div>',
  '<div><span class="label">投稿者：</span>', item()?['author'], '</div>',
  '<div><span class="label">主催者：</span>', item()?['organizer'], '</div>',
  '<div><span class="label">投稿日時：</span>', item()?['postedDateTimeJst'], '</div>',
  '<div><span class="label">内容：</span></div>',
  '<div>', outputs('Compose_Body_With_Breaks'), '</div>',
  '<div class="attachment-list"><span class="label">添付ファイル：</span></div>'
)
```

曜日は`dayOfWeek()`関数（0=日曜〜6=土曜）を使って求めています。**v5で式を変更しました。** 旧式`json('["日","月","火","水","木","金","土"]')[dayOfWeek(...)]`は、配列を計算インデックス（`[式]`）で直接アクセスする書き方で、式エディタ上で不安定になり得る境界事例と判断されたため、`substring('日月火水木金土', dayOfWeek(item()?['meetingDate']), 1)`という関数呼び出し形式に置き換えています（結果は同一です）。

続けて「文字列変数に追加」を追加し、名前を`Append_Meeting_Header_Html`に変更します（**v4でAppendToStringVariable化**）。varDocumentHtml へ `outputs('Compose_Meeting_Header_Html')` を追加します。

### 18.4 添付ファイル一覧の表示

`Append_Meeting_Header_Html`の直後に「条件(Condition)」を追加し、名前を`Condition_Has_Attachments`に変更します。式: `greater(length(coalesce(item()?['attachments'], json('[]'))), 0)`

**はいの場合（添付あり）:** 「Apply to each」を追加し、名前を`Apply_To_Each_Saved_Attachment`に変更します。対象=`coalesce(items('Apply_To_Each_Sorted_Meeting')?['attachments'], json('[]'))`（**v4で`item()`から外側ループの明示参照に変更**。ネストしたApply to each内での曖昧さを避けるため）。「同時実行を有効にする」はオフ。ループ内に「条件」を追加し、名前を`Condition_Attachment_Saved`に変更します。式（**v2で変更**）:

```
greater(length(coalesce(item()?['savedFileUrl'], '')), 0)
```

| 分岐 | アクション名 | 追加するHTML |
|---|---|---|
| はい（有効なURLあり） | Append_Attachment_Html | `concat('<div><a href="', replace(coalesce(item()?['savedFileUrl'], ''), '&', '&amp;'), '">', （savedNameを&/</>/"/'の順でエスケープ）, '</a></div>')` |
| いいえ（URLなし） | Append_Attachment_Failed_Html | `concat('<div>', （originalNameを同様にエスケープ）, if(equals(coalesce(item()?['status'], ''), 'Failed'), '（保存失敗）', '（テスト実行のため未保存）'), '</div>')` |

いずれも「文字列変数に追加」（varDocumentHtmlへ直接追加。**v4でAppendToStringVariable化**）です。**v6で`Append_Attachment_Html`のhref内URLをエスケープするよう変更しました**（`replace(url, '&', '&amp;')`）。SharePointの共有URLにはクエリパラメータの区切りに`&`が含まれることがあり、エスケープせずHTML属性値へそのまま埋め込むと厳密なHTMLパーサーで属性が正しく解釈されないおそれがあったための対応です。

**いいえの場合（添付なし）:** 「文字列変数に追加」を追加し、名前を`Append_No_Attachments_Html`に変更します。varDocumentHtml へ `<div>添付ファイルなし</div>` を追加します。

### 判定方式の変更点（v2で修正済み）

v1では`status`が文字列`'Saved'`と完全一致する場合のみリンク表示していたため、既存流用（`Skipped`だが有効なURLを持つ）の添付が「（保存失敗）」と誤表示される問題がありました。v2では**`savedFileUrl`が空文字でないかどうか**で判定するように修正しています。

- `savedFileUrl`に値がある場合（新規保存`Saved`、既存流用`Skipped`のいずれも）→ リンク表示（`Append_Attachment_Html`）。
- `savedFileUrl`が空の場合 → `status`が`Failed`（15章のとおり、実際にコピーに失敗した添付）なら「（保存失敗）」、それ以外（DryRunによる`Skipped`。9章・15章参照）なら「（テスト実行のため未保存）」と表示（`Append_Attachment_Failed_Html`）。

これにより、既存流用の添付は正しくリンク表示され、DryRunによる未保存と実際の保存失敗が文言上も区別されるようになりました。

### 18.5 フッター

`Apply_To_Each_Sorted_Meeting`ループの直後（外側）に「文字列変数に追加」を追加し、名前を`Append_DocumentHtml_Footer`に変更します（**v4でAppendToStringVariable化**）。varDocumentHtml へ `</body></html>` を追加します。

**v4で廃止**: 旧`Set_DocumentHtml`（`join(variables('varDocHtmlParts'), '')`で最終結合する「変数を設定する」アクション）は不要になったため削除しました。18.1〜18.5の各アクションが`varDocumentHtml`へ直接追記していくため、この時点で`varDocumentHtml`はすでに完成した1本のHTML文字列になっています。この`varDocumentHtml`が20章でWord互換ファイルの中身として保存されます。

---

## 19. 1会議1ページの改ページ

`Apply_To_Each_Sorted_Meeting`ループ（18章）の**先頭**、つまり本文組み立て（Escape_Ampersand等）よりも前に、改ページを挿入するかどうかの判定を追加します。

1. ループ内の先頭に「条件(Condition)」を追加し、名前を`Condition_Insert_Page_Break`に変更する。式: `greater(variables('varMeetingIndex'), 0)`
2. 「はい」の枝に「文字列変数に追加」を追加し、名前を`Append_Page_Break`に変更する（**v4でAppendToStringVariable化**）。varDocumentHtml へ次の文字列を追加する。

```html
<div style="page-break-before: always;"></div>
```

3. ループの**末尾**（18.4節の添付ファイル一覧処理の後）に「変数の値を増やす」を追加し、名前を`Increment_MeetingIndex`に変更する。varMeetingIndex += 1

### 仕組みの説明

`varMeetingIndex`は10章で`0`に初期化した整数変数です。1件目の会議（`varMeetingIndex`がまだ`0`）では改ページを入れず、2件目以降（`varMeetingIndex`が`1`以上）では会議本文の前に改ページのdivタグを挿入します。各会議の処理が終わるたびに`Increment_MeetingIndex`で1ずつ増やすことで、「1件目は改ページなし、2件目以降は改ページあり」＝「1会議1ページ」を実現しています。

> 補足: 18.1節のヘッダーCSSには`.page-break { page-break-before: always; }`というクラス定義がありますが、実際の改ページには`class="page-break"`ではなく、上記のようにインラインスタイル（`style="page-break-before: always;"`）を直接使っています。CSSクラス自体は未使用のまま残っていますが、動作には影響しません。

---

## 20. Wordファイルの保存

`Scope_50_Build_Word_Content`の直後に「スコープ」を追加し、名前を`Scope_60_Create_Archive_File`に変更します。この中で、18章・19章で組み立てたHTML文字列を`.doc`ファイルとしてSharePointへ保存します。

### 手順

**v2でDryRunの分岐が追加されました。** `DryRun=はい`のときは総括`.doc`ファイルを作成せず、本番の保存先フォルダーを汚さないようにしています。

| # | アクション名 | コネクタ/種類 | 主な入力 |
|---|---|---|---|
| 1 | Compose_ArchiveFileName | 作成(Compose) | `concat('課内会議総括_', formatDateTime(convertFromUtc(utcNow(), 'Tokyo Standard Time'), 'yyyyMMdd_HHmmss'), '.doc')` |
| 2 | Condition_DryRun_Archive | 条件(Condition) | 式=`equals(coalesce(triggerBody()?['DryRun'], true), true)`（下記参照） |

`Compose_ArchiveFileName`の直後に「条件」を追加し、名前を`Condition_DryRun_Archive`に変更します。

**はいの場合（DryRun。総括ファイルを作成しない）:**

| # | アクション名 | 種類 | 内容 |
|---|---|---|---|
| 1 | Set_ArchiveUrl_DryRun | 変数を設定する | varArchiveUrl = `(DryRun: 総括Wordファイルは作成していません。DryRun=いいえで実行してください)` |

**いいえの場合（本番実行。実際に作成・保存する）:**

| # | アクション名 | コネクタ/種類 | 主な入力 |
|---|---|---|---|
| 1 | Create_Archive_Document | SharePoint「ファイルの作成」 | サイト=`variables('varSiteAddress')`、フォルダーパス=`concat('/', variables('varLibrary'), '/', variables('varDestinationPath'))`、名前=`outputs('Compose_ArchiveFileName')`、コンテンツ=`variables('varDocumentHtml')` |
| 2 | Set_ArchiveUrl | 変数を設定する | varArchiveUrl = `replace(concat(variables('varSiteAddress'), '/', variables('varLibrary'), '/', variables('varDestinationPath'), '/', outputs('Compose_ArchiveFileName')), ' ', '%20')`（**v10で決定的URL構築に変更**。旧: `body('Get_Saved_Archive_Properties')?['{Link}']`） |

**v10で`Get_Saved_Archive_Properties`（ファイルのプロパティの取得）を削除**しました。`Set_ArchiveUrl`は`Create_Archive_Document`の直後に置かれ、サイト・ライブラリ・保存先パス・`Compose_ArchiveFileName`の出力から直接URLを組み立てます（`Create_Attachment_File`側の`Compose_Saved_File_Url`と同じパターンです。16章参照）。

ファイル名は`課内会議総括_yyyyMMdd_HHmmss.doc`（実行時点のJST日時）です。**`DryRun=はい`の場合、`Create_Archive_Document`（実際のファイル作成）自体が実行されず、保存先フォルダーに`.doc`ファイルは作成されません**（9章・22章参照）。生成されるはずだった内容（`varDocumentHtml`）自体は`Scope_50_Build_Word_Content`で組み立て済みですが、ファイルとしての保存は本番実行（`DryRun=いいえ`）のときだけ行われます。

### 「Word互換ファイル」であることの正直な説明（要Word表示確認）

このアクションが保存するファイルの中身は、実際にはHTML文字列（`varDocumentHtml`）であり、拡張子だけを`.doc`にしています。Microsoft Wordは古くからこの形式（HTMLを`.doc`拡張子で保存したファイル）を開けますが、環境によっては開く際に「ファイルの内容が拡張子と一致しません。ファイルが壊れているか、安全でない可能性があります。」といった警告ダイアログが表示されることがあります（**要Word表示確認**）。この警告が出た場合は「はい」を選んで開けば内容は正しく表示されます。

標準のPower Automateコネクタだけでは、真正のOpen XML形式（`.docx`）を組み立てることはできません。今回は「HTMLベースの`.doc`」を採用し、より軽量な代替として拡張子を`.html`に変更する方法も考えられますが、**HTMLの中身をそのまま`.docx`という拡張子にリネームすることはしていません**（Wordが正しく開けない壊れたファイルになるため）。`.doc`のままでの警告が業務上許容できない場合は、`Compose_ArchiveFileName`の拡張子部分を`.html`に変更し、ブラウザで開く運用に切り替えることを検討してください。

---

## 21. エラー処理

### 21.1 Scope_70_Write_Run_Log（成功時のログ）

`Scope_60_Create_Archive_File`の直後に「スコープ」を追加し、名前を`Scope_70_Write_Run_Log`に変更します。中に、この順で3アクションを追加します（**v7でCompose_RunLog_Bodyが追加され2→3アクションになりました**）。

| # | アクション名 | 種類 | 内容 |
|---|---|---|---|
| 1 | Set_RunStatus_Success | 変数を設定する | varRunStatus = `Success` |
| 2 | Compose_RunLog_Body | 作成(Compose) | 実行ログのJSONオブジェクトを組み立てる（内容は下記） |
| 3 | Create_Run_Log | SharePoint「HTTP要求を送信します」(REST。**v7でPostItemから変更**。15.6節参照) | サイト=静的な選択値、方法=POST、URI=`concat('_api/web/lists/getbytitle(''', variables('varRunLogList'), ''')/items')`（リスト名は引き続き**v6で変数化**した`varRunLogList`を参照。8.3節・10章参照）、ヘッダー2行、本文=`string(outputs('Compose_RunLog_Body'))` |

`Compose_RunLog_Body`の中身（JSONオブジェクト。次の`Create_Run_Log`の本文としてそのままJSON文字列化されます）:

```json
{
  "Title": "@concat(variables('varRunId'), '_summary')",
  "RunId": "@variables('varRunId')",
  "FlowName": "PA_Migrate_Teams_Meeting_Archive_To_SPO",
  "Level": "Info",
  "MeetingCount": "@length(variables('varSortedMeetings'))",
  "SavedCount": "@variables('varSavedCount')",
  "SkippedCount": "@variables('varSkippedCount')",
  "FailedCount": "@variables('varFailedCount')",
  "ArchiveUrl": "@variables('varArchiveUrl')",
  "Status": "@variables('varRunStatus')",
  "OccurredDateTimeUtc": "@utcNow()"
}
```

`FailedCount`は**v2で新規追加**した項目です（15章の失敗封じ込めで集計した件数）。`Create_Run_Log`の設定手順は15.5節の`Create_Ledger_Item`と同じパターンです（URI中のリスト名変数と、本文が参照する`Compose`アクション名だけが異なります）。

### 21.2 Scope_90_Catch（失敗時のログ）

`Scope_70_Write_Run_Log`の直後に「スコープ」を追加し、名前を`Scope_90_Catch`に変更します。「...」→「実行条件の構成」で、`Scope_70_Write_Run_Log`行の「成功した場合」のチェックを外し、「失敗した場合」「スキップされた場合」「タイムアウトした場合」の3つにチェックを入れます（`runAfter`が`["Failed", "Skipped", "TimedOut"]`になります）。

中に、この順で4アクションを追加します（**v7でCompose_ErrorLog_Bodyが追加され3→4アクションになりました**）。

| # | アクション名 | 種類 | 内容 |
|---|---|---|---|
| 1 | Set_RunStatus_Failed | 変数を設定する | varRunStatus = `Failed` |
| 2 | Set_ErrorMessage | 変数を設定する | varErrorMessage = `concat('実行中にエラーが発生しました。RunId=', variables('varRunId'))` |
| 3 | Compose_ErrorLog_Body | 作成(Compose) | エラーログのJSONオブジェクトを組み立てる（内容は下記） |
| 4 | Create_Error_Log | SharePoint「HTTP要求を送信します」(REST。**v7でPostItemから変更**) | サイト=静的な選択値、方法=POST、URI=`concat('_api/web/lists/getbytitle(''', variables('varRunLogList'), ''')/items')`（**v6で変数化**）、ヘッダー2行、本文=`string(outputs('Compose_ErrorLog_Body'))` |

`Compose_ErrorLog_Body`の中身:

```json
{
  "Title": "@concat(variables('varRunId'), '_error')",
  "RunId": "@variables('varRunId')",
  "FlowName": "PA_Migrate_Teams_Meeting_Archive_To_SPO",
  "Level": "Error",
  "ErrorMessage": "@variables('varErrorMessage')",
  "Status": "Failed",
  "OccurredDateTimeUtc": "@utcNow()"
}
```

`Create_Error_Log`の設定手順は`Create_Run_Log`・`Create_Ledger_Item`と同じパターンです（15.5節・15.6節参照）。

### 21.3 Scope_99_Finally（実行結果サマリ）

`Scope_90_Catch`の直後に「スコープ」を追加し、名前を`Scope_99_Finally`に変更します。「実行条件の構成」で、`Scope_90_Catch`行の「成功した場合」「失敗した場合」「スキップされた場合」「タイムアウトした場合」の**4つ全て**にチェックを入れます。

中に「作成(Compose)」を1つ追加し、名前を`Compose_Finally_Summary`に変更します。

```
{
  "RunId": "@{variables('varRunId')}",
  "Status": "@{variables('varRunStatus')}",
  "MeetingCount": @{length(variables('varSortedMeetings'))},
  "SavedCount": @{variables('varSavedCount')},
  "SkippedCount": @{variables('varSkippedCount')},
  "FailedCount": @{variables('varFailedCount')},
  "ArchiveUrl": "@{variables('varArchiveUrl')}"
}
```

`FailedCount`は**v2で新規追加**した項目です。このアクションはメールやTeamsへの通知は行いません。フローの実行履歴（「実行の詳細」画面）を開いたときに、最後の一目で結果を確認できるようにするためのComposeです。実行結果はSharePointの`MeetingArchiveRunLog`リストでも確認できます（21.1・21.2節）。

### 21.4 「1件の失敗で止めない」方針について（v2で修正済み）

もとの仕様（`Teams課内会議アーカイブ自動化_仕様書.docx`（同じspecフォルダー））では「1ファイルの失敗で会議全体を中止せず、添付statusをFailedとして会議処理を継続する」ことが求められています。v1のフロー定義ではこの方針が実現されていませんでしたが、**v2で15.5節の構成変更により実現しました。**

- 添付ファイルの実コピー（`Compose_Source_Url`／`Compose_Source_Site`／`Compose_Source_Path`／`Get_Source_File_Content`／`Create_Attachment_File`。**v10で`Get_Saved_File_Properties`を削除**）は`Scope_Save_File`に閉じ込められています。これが失敗・タイムアウトした場合、`Append_Failed_Meeting_Attachment`→`Create_Ledger_Item_Failed`→`Increment_FailedCount`が`runAfter`＝`["Failed", "TimedOut"]`で実行され、その添付を`Status=Failed`として処理台帳・会議データに記録したうえで**処理を継続**します（15.5節）。
- 添付ファイルの状態（`Status`列）は`Saved`（新規保存成功）／`Failed`（保存失敗）の2値を取ります。既存流用でスキップした場合はこのリストへの新規書込み自体を行わないため、`Skipped`という値がこのリストに書き込まれることはありません（12.4節）。会議データ内の一時的な`varMeetingAttachments`（フロー内配列）では、既存流用・DryRunによる未保存はいずれも`status: 'Skipped'`として保持されます（18章参照）。
- 保存に失敗した件数は`varFailedCount`に集計され、実行ログの`FailedCount`列（21.1節）・`Compose_Finally_Summary`（本節）に反映されます。
- **この失敗封じ込めは`Scope_Save_File`の範囲に限定されます。** `Get_Ledger_Existing`（15.2節）やTeamsメッセージ・返信の取得（11章・12章）など、`Scope_Save_File`の外側で発生したエラーは、引き続き実行全体を失敗として扱い、`Scope_90_Catch`（21.2節）で記録されます。会議・添付単位の継続処理が実装されているのは「添付ファイル本体のコピー」の失敗に限られる、という範囲は27章「制約と未確定事項」にも明記しています。

---

## 22. 過去7日間のテスト

フローの骨格（1〜21章）が完成したら、まず小規模なテストを行います。

### 実行手順

1. フローを開き、画面右上の「テスト」または「実行」をクリックする。
2. 入力画面で次の値を設定する。

| 入力 | 値 |
|---|---|
| 取得対象日数（LookbackDays） | 7 |
| テスト実行（DryRun） | はい |
| 処理済みファイルを再処理する（ForceReprocess） | いいえ |

3. 「実行」をクリックし、完了を待つ。
4. 「実行の詳細」画面で、各アクションが緑色（成功）になっているか確認する。

### 確認項目（DryRun=はい）

- `Filter_Messages_By_Period`の出力件数が、直近7日間の投稿数と一致するか。
- `Process_Each_Parent_Message`ループの反復回数が会議件数と一致するか。
- `Compose_Author`・`Compose_MeetingDate`が期待どおりの値になっているか（投稿者不明の場合は「不明」表示になっているか）。
- 添付ファイルがある会議で、`Filter_File_Attachments`の出力に想定した添付が含まれているか。
- **v9の確認項目**: 添付ファイルが1件も無い会議では、`Condition_Has_File_Attachments`が**いいえ（false）側**を通り、`Process_Each_Attachment`が実行されずに`Compose_SortKey`へ進むのが正常な挙動です（実行の詳細画面では、当該会議の周回で`Process_Each_Attachment`自体がスキップ表示になります）。逆に添付が1件でもある会議では「はい（true）」側を通り、`Process_Each_Attachment`が実行されることを確認してください。
- **v2の重要な変更**: `DryRun=はい`の場合、`Condition_DryRun_Archive`（20章）により`Create_Archive_Document`自体が実行されず、`.doc`ファイルは保存先フォルダーに**作成されません**。`varArchiveUrl`には「(DryRun: 総括Wordファイルは作成していません。DryRun=いいえで実行してください)」という案内文字列が入ります。添付ファイル本体も保存されません（`varMeetingAttachments`の各要素は`status: 'Skipped'`、`savedFileUrl`は空）。このテストでは、`.doc`の中身ではなく**件数・値の確認のみ**を行います。
- `Scope_70_Write_Run_Log`実行後、SharePointの`MeetingArchiveRunLog`リストに`Level=Info`、`Status=Success`の行が1件追加され、`ArchiveUrl`列に上記の案内文字列が入っているか確認する。

### 実ファイルの確認（DryRun=いいえで再実行）

件数確認に問題がなければ、同じ7日間の範囲で`DryRun=いいえ`にして再実行し、実際に保存された内容を確認します。

1. 「実行」画面で「取得対象日数」は`7`のまま、「テスト実行」を「いいえ」に変更して実行する。
2. 保存先フォルダーに添付ファイルと`課内会議総括_yyyyMMdd_HHmmss.doc`が作成されているか確認する。
3. `.doc`を開き、日付・投稿者・本文・改ページが1会議1ページになっているかを目視確認する。添付ファイル一覧は、保存済みの添付は実際にリンクとして開けるか、添付なしの会議は「添付ファイルなし」と表示されているかを確認する（18章参照）。
4. `MeetingArchiveLedger`リストに、保存した添付の件数分`Status=Saved`の行が追加されているか確認する。
5. `varSavedCount`・`varSkippedCount`・`varFailedCount`（`MeetingArchiveRunLog`の`SavedCount`／`SkippedCount`／`FailedCount`列）が想定と一致するか確認する。`FailedCount`が1件でもある場合は、`MeetingArchiveLedger`の該当行（`Status=Failed`）の`ErrorMessage`列を確認し、原因を調査する（26章参照）。

このテストがすべて緑色で完了し、生成された`.doc`の内容に問題がなければ、23〜25章へ進みます。

---

## 23. 取得期間の変更

取得対象日数（`LookbackDays`）を変更するだけで、取得する期間を調整できます。`EndDateUtc`に相当する入力はなく、常に実行時点（`utcNow()`）が終了日時になります（9章・10章参照）。

### 変更方法

1. フローの「実行」画面を開く。
2. 「取得対象日数」欄に、取得したい日数を入力する（例: 30、90、365、730）。
3. 「テスト実行」「処理済みファイルを再処理する」は目的に応じて設定する。

### 値の目安

| LookbackDays | 用途 |
|---|---|
| 7 | 初回の動作確認（22章） |
| 30〜90 | 中規模テスト（会議件数・添付件数を段階的に増やして確認） |
| 365 | 過去1年間の実行（24章） |
| 730 | 過去2年間の実行（25章） |

トリガーの既定値（10章のInitialize_LookbackDaysの`7`）自体を変更したい場合は、`triggers.manual.inputs.schema.properties.LookbackDays.default`（画面上は「実行」画面の入力欄の初期表示値）を編集しますが、通常は実行のたびに画面上で値を指定すれば十分です。

---

## 24. 過去1年間の実行

過去2年間の一括実行（25章）の前段階として、まず1年分（`LookbackDays=365`）で実行し、件数・所要時間・エラーの有無を確認することを推奨します。

### 実行手順

1. 「実行」画面で「取得対象日数」に`365`を入力する。
2. 「テスト実行」は、初回は「はい」（DryRun）で会議件数・添付候補件数を確認してから、「いいえ」に切り替えて本番実行することを推奨する。
3. 「処理済みファイルを再処理する」は「いいえ」のまま実行する。
4. 実行後、`Scope_10_Get_Channel_Messages`の`Do_Until_Messages_Paging`、`Scope_20`内の`Do_Until_Replies_Paging`が、上限（カウント5000・タイムアウトPT1H）内で完了しているか確認する。
5. `MeetingArchiveLedger`リストに、保存した添付の件数分の行が追加されているか確認する。
6. `MeetingArchiveRunLog`リストに`Status=Success`の行が追加され、`MeetingCount`・`SavedCount`・`SkippedCount`・`FailedCount`が想定と一致するか確認する。`FailedCount`が0でない場合は、`MeetingArchiveLedger`の`Status=Failed`の行を確認し、原因を調査する（15章・26章参照）。

1年分で問題なく完了すれば、25章の2年間実行に進みます。

---

## 25. 過去2年間の実行

### 実行手順

1. 「実行」画面で「取得対象日数」に`730`を入力する。
2. 「テスト実行」は「いいえ」（本番保存）にする。
3. 「処理済みファイルを再処理する」は「いいえ」のままにする（既に24章で保存済みの添付を再度コピーしないため）。
4. 実行し、完了を待つ。

### タイムアウトした場合の対処

すべてのループの「同時実行を有効にする」はオフ（逐次実行）にしているため、投稿数・返信数・添付件数が多いほど実行時間が線形に伸びます。2年分の実行がタイムアウトする場合は、次の対応を検討してください。

- `Do_Until_Messages_Paging`・`Do_Until_Replies_Paging`の「設定」→「ループの制限を変更する」で、カウント・タイムアウトの上限をさらに引き上げる（**要実環境確認**: フロー1回の実行時間には環境側の上限もあります）。
- それでも収まらない場合は、**フローを1つのまま**、`LookbackDays`を分割して複数回に分けて実行する（例: 1回目`LookbackDays=400`、しばらく日を空けて2回目`LookbackDays=730`など）。

分割実行に関する重要な注意: 本フローには「前回の実行以降の差分だけを取得する」機能はありません（定期実行フロー自体を追加していないため）。`EndDateUtc`は常に実行時点の`utcNow()`であり、`LookbackDays`は常に「そこから何日前まで」という相対指定です。そのため、分割して複数回実行すると、**実行回数分のWord互換ファイル（`.doc`）がそれぞれ生成されます**（1つのファイルに自動的に統合されるわけではありません）。添付ファイル自体は`MeetingArchiveLedger`による冪等性で重複保存されませんが、Word互換ファイルについては、最終的にどの実行回の`.doc`を正式な成果物とするかを人手で判断し、不要な回の`.doc`は手動で整理する運用を想定してください。

---

## 26. トラブルシューティング

| 症状 | 想定される原因 | 対処 |
|---|---|---|
| フローの保存時に「接続がありません」エラー | 3コネクタ（Teams/SharePoint/Content Conversion）のいずれかの接続が未作成・失効している | 8.1節の手順で該当アクションを開き、接続を選択・作成し直す |
| SharePointアクションの「サイトのアドレス」「リスト」欄が赤枠・エラー表示になる | インポート直後、式（`variables('varSiteAddress')`等）がUIに正しく認識されていない | 8.2節の手順で、一度ドロップダウンから選び直してから式に戻す |
| （履歴・v10で対象外化）`body(...)?['{Link}']`が空、または存在しないというエラー | v9までは`{Link}`（GetFileItem）に依存していたため発生し得た症状です。**v10で`GetFileItem`自体を廃止し決定的URL構築へ変更**したため、`{Link}`を参照する式自体がフロー内に存在しなくなりました（16章参照） | v10パッケージでは対応不要。旧バージョンのフローをまだ使っている場合は16章の履歴セクションを参照 |
| `Get_Source_File_Content`（GetFileContentByPath）が404等のエラーになる | 添付ファイルの実体が保存先サイト（`varSiteAddress`）以外のサイトにある（15章の注意参照） | **v2**: この失敗は`Scope_Save_File`単位で吸収され、当該添付だけが`Status=Failed`として記録され処理は継続します（15.5節）。`MeetingArchiveLedger`の`Status=Failed`行の`ErrorMessage`（**v10で元URL・保存先パスを含む自己診断形式に変更**）で該当添付を特定し、恒常的に失敗する場合は`contentUrl`の実際の値を確認し`path`の解決先サイトを補正する式への変更を検討する |
| 添付が**全件**`Status=Failed`になる（v9実環境実行で発生した事象） | 候補1: 保存先フォルダーの中間階層が未作成（CreateFileは中間フォルダーを自動作成しない）。候補2: v9まで存在した`Get_Saved_File_Properties`（GetFileItem）のライブラリ名前解決の失敗（16章参照） | **v10で対処**: `Scope_05_Ensure_Destination_Folder`（10.2節）が保存先フォルダーを事前作成・検証、`GetFileItem`自体を廃止して決定的URL構築に変更（16章）。v10パッケージへの更新後、`MeetingArchiveLedger`の`ErrorMessage`（自己診断形式）で原因を再確認する |
| `Verify_Destination_Folder`（Scope_05）が失敗し、フローがそこで停止する | 保存先パス（`varSiteAddress`／`varLibrary`／`varDestinationPath`の組み合わせ）が実在しない、または権限が不足している（10.2節参照） | 該当サイト・ライブラリ・フォルダーパスが正しいか、実行アカウントに編集権限があるかを確認する。`varDestinationPath`が4階層を超えていないかも確認する（10.2節参照） |
| `Create_Attachment_File`／`Create_Archive_Document`が同名ファイルへの書込みでエラー（409相当）になる | 前回実行の残骸ファイルが保存先に既に存在する。特にv9で全添付Failedが発生した後の再実行では、実際にはファイルが保存できていた可能性がある（27章v10項参照） | 再実行前に保存先フォルダーの中身を確認し、前回実行の残骸と思われるファイルを退避・削除する（10.2節・27章参照） |
| 生成された`.doc`をWordで開くと警告ダイアログが出る | 中身がHTMLで拡張子のみ`.doc`のため（20章参照） | 「はい」を選んで開く。業務上許容できない場合は拡張子を`.html`に変更する運用に切り替える |
| `DryRun=はい`で実行しても保存先フォルダーに`.doc`が見当たらない | **v2の仕様どおりの動作**です。`Condition_DryRun_Archive`（20章）により、DryRun時は`.doc`を作成しません | 実ファイルを確認したい場合は`DryRun=いいえ`で再実行する（22章参照） |
| `Do_Until_Messages_Paging`や`Do_Until_Replies_Paging`がタイムアウトする | 投稿・返信件数が多く、既定の上限（カウント/タイムアウト）に収まらない | 11章・12章の手順で上限を引き上げる。730日実行の場合は25章も参照 |
| 2ページ目以降の取得で応答がおかしい・エラーになる | `@odata.nextLink`の絶対URLの扱い（**要実環境確認**。`varChannelId`内の`:`・`@`の扱いはv5の`uriComponent()`化で解決済み） | 22章のテスト実行時に`Get_Channel_Messages`の入力・出力を1件ずつ確認する |
| 429（Too Many Requests）エラーが頻発する | Graph APIのレート制限 | `Get_Channel_Messages`・`Get_Message_Replies`の再試行ポリシーは既定のままにしておくと自動対応される。頻発する場合は実行の間隔を空ける |
| SharePointリストへ書き込む列の値がずれる／`item()?['列名']`が空になる | リスト作成時に列名を日本語等の非ASCII文字にしたため、内部名が`OData__x30d5__x30a1__x30a4__x30eb_`のような自動エンコード形式になり、本フローの式（列名を直接キーに使う`item`）と一致していない | 12.4節のとおりSharePointリストの列は**ASCII英数字の列名で作成**する。既に非ASCII列名で作成済みの場合は、列を作り直すか、実際の内部名を確認して式を修正する |
| Word本文で、添付が「（テスト実行のため未保存）」または「（保存失敗）」と表示される | 前者はDryRunによる未保存（`status: 'Skipped'`）、後者は実際の保存失敗（`status: 'Failed'`）。**v2で両者を区別表示するよう修正済み**（18章参照。既存流用や新規保存で`savedFileUrl`が有効な場合は正しくリンク表示されます） | 「（テスト実行のため未保存）」はDryRun=いいえで再実行すれば解消。「（保存失敗）」は`MeetingArchiveLedger`の`Status=Failed`行の`ErrorMessage`で原因を確認する |
| 添付1件が失敗しても実行全体は`Failed`にならない | **v2の仕様どおりの動作**です。添付本体のコピー失敗は`Scope_Save_File`単位で吸収され、`Status=Failed`記録後に処理を継続します（15.5節・21.4節） | `varFailedCount`／`MeetingArchiveRunLog`の`FailedCount`列で件数を確認し、`MeetingArchiveLedger`の`Status=Failed`行で個別の原因を調査する |
| 実行全体が失敗（Failed）になり、`MeetingArchiveRunLog`にエラーが記録される | `Scope_Save_File`（添付コピー）以外の箇所（Teams取得・`Get_Ledger_Existing`・HTML生成等）で例外が発生した（21.4節のとおり、失敗封じ込めは添付コピーの範囲に限定） | 「実行の詳細」画面でどのアクション・どの反復回で失敗したかを特定し、原因（権限・パス解決・429等）に応じて対処する |
| SharePointリストへの書込みでエラーになる | 12.4節の列名・型がリストの実際の列と一致していない（`FailedCount`列の追加漏れ等） | リストの列名（大文字小文字・スペルを含む）を12.4節の表と突き合わせて確認する |
| フローの保存時に`OpenApiOperationParameterValidationFailed`（`PostItem`は必須プロパティ`item`が欠落）というエラーが出る | SharePoint「項目の作成」(`PostItem`)を使い、かつ「サイトのアドレス」または「リスト」欄を式にしている（v6以前の構成、または`PostItem`に手動で戻した場合） | **v7ではこの4アクションをSharePoint「HTTP要求を送信します」(REST)に置き換え済みです**（15.6節）。デザイナーで`PostItem`に戻す場合は、サイト・リストの両方を静的な選択値にしてください |
| `Create_Ledger_Item`等（REST）の保存・実行で`__metadata`関連のエラーになる | テナント設定によりPOST時に型情報（`__metadata`）の指定を要求される場合がある（**要実環境確認**） | `_api/web/lists/getbytitle('リスト名')?$select=ListItemEntityTypeFullName`で型名を取得し、`Compose_X_Body`の先頭に`"__metadata": {"type": "取得した型名"}`を追加する（15.6節） |
| `Create_Ledger_Item`等（REST）の書込みで`SavedFileUrl`・`ArchiveUrl`列の値が正しく入らない | 該当列を「ハイパーリンクまたは画像」型で作成しており、RESTが送る単純な文字列と型が一致していない | 12.4節のとおり両列を**単一行テキスト**で作成し直す |

---

## 27. 制約と未確定事項

本フローの実装・検証で判明している制約・未確定事項を一覧にまとめます。実際のテナントでの検証時に、この一覧を1件ずつ確認してください。本書の版はv10で、v2〜v10の修正履歴は27.1節に、修正後も残る制約は27.3節にまとめています。

### 27.1 修正履歴（v2〜v10）

現在のフロー定義（v10）に至るまでに、v1〜v9で判明した問題を段階的に修正しています。旧版の「既知のバグ」一覧からは外し、ここに修正内容として記録します。

#### v2: 定義レビューで検出した3件の設計バグを修正

| # | 修正前（v1）の問題 | 修正後（v2）の挙動 | 該当章 |
|---|---|---|---|
| 1 | DryRun（テスト実行）でも、会議一覧のWord互換ファイル（`.doc`）が必ず作成・保存されてしまい、本番の保存先フォルダーが汚れる | `Scope_60_Create_Archive_File`に`Condition_DryRun_Archive`を追加。`DryRun=はい`のときは`.doc`を作成せず、`varArchiveUrl`に案内文字列を設定するのみにした | 20章・22章 |
| 2 | 添付ファイル1件のコピーに失敗すると、その例外が実行全体に伝播し、フロー全体が失敗（Failed）扱いになっていた。添付の`Status`列も`Saved`／`Skipped`のみで`Failed`を記録する手段がなかった | 実コピー処理を`Scope_Save_File`に閉じ込め、その失敗・タイムアウトを`runAfter`で受け止める後続ハンドラ（`Append_Failed_Meeting_Attachment`→`Create_Ledger_Item_Failed`(Status=Failed)→`Increment_FailedCount`）を追加。添付1件が失敗しても会議処理・フロー全体を継続し、新変数`varFailedCount`とRunLogの`FailedCount`列で件数を集計するようにした | 15章・21章 |
| 3 | `Condition_Attachment_Saved`が`status=='Saved'`のみを「保存済み」として扱っていたため、既存流用（`Skipped`だが有効なURLを持つ添付）がWord本文で「（保存失敗）」と誤表示されていた | 判定条件を`length(coalesce(item()?['savedFileUrl'], '')) > 0`（URLの有無）に変更。有効なURLがあれば新規保存・既存流用のいずれもリンク表示し、URLが無い場合のみ`status`に応じて「（保存失敗）」（`Failed`）または「（テスト実行のため未保存）」（それ以外）と表示する | 18章 |

これに伴い、変数は26個から27個（`varFailedCount`を追加）、`MeetingArchiveRunLog`の列は10列から11列（`FailedCount`を追加）、フロー全体のアクション総数はv1の123からv2の129に増えました。

#### v3: インポート時の式パースエラーを修正

v2のZIPを実環境でインポートしようとしたところ、次のエラーが発生しました。

```
The template language expression 'if(contains(@coalesce(...' is not valid:
the string character '@' at position '12' is not expected.
```

原因は、`Compose_Extension`・`Compose_BaseName`（15.3節）の式で、外側の`@if(...)`の内側にネストした`coalesce(...)`の前にも誤って`@`を付けていたことです（`@`は式文字列の先頭、または`@{...}`補間の中でのみ有効で、入れ子になった関数の前には付けません）。該当2アクションの式から余分な`@`を除去し、定義全体を機械走査して不正な`@`が0件であることを確認しました。**v3のZIPは実環境でのインポート自体には成功しています**（その後の保存で発生したエラーはv4を参照）。

#### v4: 保存時のSetVariable自己参照エラーを全面修正（最重要）

v3のZIPをインポート後、フローを保存しようとしたところ、次のエラーが発生しました。

```
WorkflowRunActionInputsInvalidProperty: The inputs of workflow run action 'Set_MessagesArray' of
type 'SetVariable' are not valid. Self reference is not supported when updating the value of
variable 'varMessagesArray'.
```

Power Automateの「変数を設定する(SetVariable)」は、更新対象の変数自身を値の式の中から参照する構成（自己参照）を保存時に拒否します。定義全体を機械走査した結果、自己参照は3件見つかりました。

| # | 旧アクション名 | 実体 | 置換後 | 該当章 |
|---|---|---|---|---|
| 1 | Set_MessagesArray | `union(varMessagesArray自身, 新ページ)` | Process_Retrieved_Messages（Apply to each）＋Append_Message_To_MessagesArray（配列変数に追加） | 11章 |
| 2 | Set_RepliesArray | `union(varRepliesArray自身, 新ページ)` | Process_Retrieved_Replies（Apply to each）＋Append_Reply_To_RepliesArray（配列変数に追加） | 12章 |
| 3 | Append_Reply_Attachment_Candidates | 名前はAppendだが実体は`SetVariable`+`union`自己参照 | Process_Each_Reply_Attachment（Apply to each）＋Append_Reply_Attachment_Candidate（配列変数に追加） | 14章 |

あわせて次の変更も行いました。

- **Word用HTMLの連結方式を変更**: `varDocHtmlParts`（配列）＋`join()`方式を廃止し、`varDocumentHtml`へ「文字列変数に追加(AppendToStringVariable)」で直接連結する方式に統一（18章）。`varDocHtmlParts`変数は廃止（変数27→26）。
- **LookbackDaysの安全化**: ルート先頭に`Compose_EffectiveLookbackDays`を追加し、未入力・null・0以下の場合は既定値7に丸める（10章）。
- **ネストしたApply to eachの入力を明示化**: `Apply_To_Each_Saved_Attachment`の入力を`items('Apply_To_Each_Sorted_Meeting')?['attachments']`の明示参照に変更（`item()`の曖昧さ排除。18章）。

これに伴い、フロー全体のアクション総数はv3の129からv4の131に、変数は27個から26個（`varDocHtmlParts`廃止）に変わりました。**v3のZIPはインポートには成功しましたが保存はできない状態でした。v4はこの保存エラーの原因を除去した版です。**

#### v5: Opus級モデルによる監査指摘＋実働サンプル準拠の堅牢化

実働サンプル`create_meeting_list_sample_20260716105612.zip`（実環境で作成・動作実績のあるエクスポート。詳細は`../../../../../references/sample_export_analysis.md`）との突合、およびOpus級モデルによる論理監査を踏まえ、次の3点を修正しました。

| # | 修正内容 | 該当章 |
|---|---|---|
| 1 | チャネルID（`19:...@thread.tacv2`）と親メッセージIDを`uriComponent()`でURLエンコード（`Set_NextLink_First`＝channelId、`Set_ReplyNextLink_First`＝channelId＋messageIdの計3箇所）。teamIdはGUIDのためエンコード不要 | 11章・12章 |
| 2 | 曜日式を`json('[...]')[dayOfWeek(...)]`（配列の計算インデックスアクセス）から`substring('日月火水木金土', dayOfWeek(...), 1)`に変更（式エディタでの不安定さ回避） | 18章 |
| 3 | コンテナ起点4アクション（Get_Channel_Messages／Get_Message_Replies／Select_Reply_Attachments／Get_Source_File_Content）に`"runAfter": {}`を明示（PA標準エクスポート形式に整合） | 11章・12章・14章・15章 |

アクション総数・変数数はv4と同じ（131・26）です。実働サンプルの設計（SetVariable上書きによる添付蓄積、ページング無し、封筒形ParseJsonスキーマ等）は劣位と判断し移植していません（詳細は`../../../../../references/sample_export_analysis.md`）。

#### v6: コネクタ出力の`body/`参照欠落を修正（重大バグ修正）

Opus級モデルによる実働サンプル突合監査（8観点）で、次の重大バグを検出しました。

**【重大】** `type: OpenApiConnection`のアクションの`outputs('X')`は`{statusCode, headers, body}`という封筒を返すため、`outputs('X')?['ItemId']`や`outputs('X')?['{Link}']`のように封筒の外側から直接フィールドを取り出そうとすると**常に`null`**になります。`DryRun=はい`（既定値）ではこの経路が実行されないため気づかれず、`DryRun=いいえ`の本番実行で初めて全添付の保存が失敗扱いになる潜在バグでした。次の5箇所を`outputs(...)`から`body(...)`参照に修正しています（16章で詳しく説明）。

- `Get_Saved_File_Properties`のid（`body('Create_Attachment_File')?['ItemId']`）
- `Create_Ledger_Item`のSavedFileUrl（`body('Get_Saved_File_Properties')?['{Link}']`）
- `Append_Saved_Meeting_Attachment`のsavedFileUrl（同上）
- `Get_Saved_Archive_Properties`のid（`body('Create_Archive_Document')?['ItemId']`）
- `Set_ArchiveUrl`（`body('Get_Saved_Archive_Properties')?['{Link}']`）

あわせて、任意推奨として次の2点も反映しました。

- **RunLogリスト名の変数化**: `varRunLogList`（既定値`MeetingArchiveRunLog`）を追加し、`Create_Run_Log`・`Create_Error_Log`のテーブル欄を`variables('varRunLogList')`に変更（10章・21章）。変数`varDocHtmlParts`廃止分と相殺し、変数総数は26個から**27個**に戻りました。
- **添付hrefのエスケープ**: Word本文の添付リンクのhref内URLを`replace(url, '&', '&amp;')`でエスケープ（18章）。

**v6集計（機械検証済み・0エラー0警告）**: 総アクション数**132**（v5の131にInitialize_RunLogListが加わった分）、変数**27個**。SetVariableアクション13件中、自己参照は**0件**。コネクタ出力の`body/`参照欠落も**0件**。詳細は27.5節。

#### v7: PostItemの保存エラーをSharePoint RESTへの置換で修正

v6のZIPを実環境でインポートし、フローを保存しようとしたところ、**3件目の実環境エラー**（1件目はv2→v3のインポート時パースエラー、2件目はv3→v4の保存時自己参照エラー）が発生しました。

```
OpenApiOperationParameterValidationFailed: Input parameter 'item' validation failed in workflow
operation 'Create_Run_Log': The API operation 'PostItem' is missing required property 'item'.
```

**原因**: SharePoint「項目の作成」(`PostItem`)は必須の動的ボディ`item`（`x-ms-dynamic-schema`）を持ちます。この`item`は、デザイナーで「サイトのアドレス」「リスト」を両方とも静的に選択した場合にのみ、リストの列スキーマから動的に生成できます。本フローでは`Create_Ledger_Item`等の「リスト」欄が`variables('varLedgerList')`のような式になっているため（リスト名の再選択を10章の変数1か所に集約するため）、保存時の検証が列スキーマを解決できず`item`を構築できずに保存が失敗しました。保存時エラーは1アクションずつしか報告されないため、メッセージには`Create_Run_Log`だけが表示されましたが、同型の`PostItem`アクション4件（`Create_Ledger_Item`／`Create_Ledger_Item_Failed`／`Create_Run_Log`／`Create_Error_Log`）すべてが同じ理由で保存できない状態でした。詳細（実働サンプルとの比較・デザイナーで静的選択できる場合は`PostItem`のままでよいこと等）は15.6節を参照してください。

**修正**: `PostItem`×4を、SharePoint「HTTP要求を送信します」(`operationId=HttpRequest`)によるSharePoint REST呼び出しに置き換えました（15.5節・21章）。各アクションの直前に「作成(Compose)」でボディのJSONオブジェクトを組み立てるアクション（`Compose_Ledger_Body`／`Compose_LedgerFailed_Body`／`Compose_RunLog_Body`／`Compose_ErrorLog_Body`）を新規追加し、「サイトのアドレス」は静的な選択値のまま、「URI」は`concat('_api/web/lists/getbytitle(''', variables('varLedgerListまたはvarRunLogList'), ''')/items')`という式、「ヘッダー」はAccept・Content-Typeとも`application/json;odata=nometadata`、「本文」は`string(outputs('Compose_X_Body'))`としています。アクション名は変更していないため後続の`runAfter`参照は無変更で、これら4アクションの出力を参照する箇所ももともと存在しないため応答参照の変更もゼロです。他の9アクション（`GetItems`／`GetFileItem`×2／`CreateFile`×2／`GetFileContentByPath`／Teams`HttpRequest`×2／`HtmlToText`）は必須の動的ボディを持たないため無改修です（全13アクションの一斉監査で判定）。

検証スクリプトに「`PostItem`が残存していないか」「SharePoint `HttpRequest`アクションの必須キーが揃っているか」の機械検査を恒久追加しました。

**残る注意点（実行時。保存はブロックしない）**:
- テナント設定によりRESTのPOSTで`__metadata`型指定が要求される可能性があります（15.6節のフォールバック手順を参照）。
- `SavedFileUrl`・`ArchiveUrl`列が「ハイパーリンク」型の場合、RESTでは`{"Url":...}`オブジェクトが必要になり書込みに失敗する可能性があります。**両列はハイパーリンク型を避けてください**（12.4節では複数行テキスト＝書式なしを推奨に更新しています）。
- REST化した4アクションの「サイトのアドレス」は静的な選択値です。保存先サイトを変更する場合は、10章の`varListSiteAddress`変更に加えてこの4アクションを個別に編集する必要があります（**v8で対象変数が`varSiteAddress`から`varListSiteAddress`に変わりました**。8.3節参照）。

**v7集計（機械検証済み・0エラー0警告）**: 総アクション数**136**（v6の132にCompose×4が加わった分）、変数**27個**（不変）。使用operationIdは`CreateFile`／`GetFileContentByPath`／`GetFileItem`／`GetItems`／`HtmlToText`／`HttpRequest`の**6種類**（`PostItem`は廃止）。SetVariableアクション13件中、自己参照は**0件**。コネクタ出力の`body/`参照欠落も**0件**。`PostItem`の残存も**0件**（新設した機械検査）。詳細は27.5節。

#### v8: 台帳・実行ログのリスト操作サイトを分離（最終版）

台帳（`MeetingArchiveLedger`）・実行ログ（`MeetingArchiveRunLog`）の2リストを、ファイル保存先サイト（`varSiteAddress`＝mROOM_240600018）とは別のサイト**pjteam_220400119**に作成することがユーザー決定されました（別パッケージのリスト自動作成フロー`CreateMeetingArchiveLists`の構築に伴う決定。`../../provision-archive-lists/release/`配下。12.4節参照）。`varSiteAddress`は添付ファイル・総括docの保存先フォルダーが実在するサイトであるため、ファイル保存系アクションはそのまま維持し、**リスト操作のみを新変数へ分離**しました。

**修正内容**:
- 新変数`varListSiteAddress`（文字列、初期値`https://metijapan.sharepoint.com/teams/pjteam_220400119`）を追加。`Initialize_ListSiteAddress`を`Initialize_SiteAddress`の直後（10章の8番目）に挿入しました（10章・10.1節）。
- `Get_Ledger_Existing`の「サイトのアドレス」を`variables('varSiteAddress')`から`variables('varListSiteAddress')`に変更（15.2節）。
- `Create_Ledger_Item`／`Create_Ledger_Item_Failed`／`Create_Run_Log`／`Create_Error_Log`（v7でPostItemから置き換え済みの4アクション）の静的な「サイトのアドレス」を、mROOM_240600018からpjteam_220400119へ変更（8.3節・15.5節）。
- ファイル保存系5アクション（`Get_Source_File_Content`／`Create_Attachment_File`／`Get_Saved_File_Properties`／`Create_Archive_Document`／`Get_Saved_Archive_Properties`）は`varSiteAddress`（mROOM）のまま変更なし。

これに伴い、変数の総数は27個から**28個**（`varListSiteAddress`を追加）、フロー全体のアクション総数はv7の136から**137**（`Initialize_ListSiteAddress`を追加）に増えました。

**v8集計（機械検証済み・0エラー0警告）**: 総アクション数**137**（v7の136に`Initialize_ListSiteAddress`が加わった分）、変数**28個**（`varListSiteAddress`を追加）。「初期化済みだが未参照の変数」検査を検証スクリプトへ恒久追加しており、v8の初回ビルドではこの検査観点で`Get_Ledger_Existing`のサイト参照の付け替え漏れを検出・修正した経緯があります。詳細は27.5節。

**現行版（v9）に至るまでの実環境での経緯（正直な記載）**: v2のZIPは実環境でのインポート自体に失敗しました（テンプレート言語式の`@`不正エラー。v3で修正）。v3のZIPは実環境でのインポートには成功しましたが、保存時に自己参照エラーが発生しました（v4で修正）。v6のZIPはインポート自体には問題がなかったものの、保存時にPostItemエラー（3件目の実環境エラー）が発生し、v7でその原因を除去しました。**v8のZIPは実環境でインポート・保存・実行に成功し、`MeetingArchiveRunLog`への書き込み（201応答）まで到達しましたが、実行時に`Get_Source_File_Content`が404エラーで失敗しました**（4件目の実環境エラー。詳細は次のv9項目参照）。**v9（本バージョン）は、この404の原因を修正した式レベルの変更ですが、修正後の実環境での再実行はまだ行っていません。** 上記の「機械検証済み」はすべて静的検査（JSON構文・参照整合性・自己参照監査・`PostItem`残存監査・未参照変数監査等）の結果であり、v9について「404が解消される」「正しく実行できる」ことそのものを保証するものではない点にご留意ください。

#### v9: 実行時の404エラーをcontentUrl由来のサイト/パス導出で修正＋添付有無の明示分岐

v8のZIPを実環境でインポート・保存した後、実行したところ、フローは`MeetingArchiveRunLog`への書き込み（201応答、Id=1）まで到達しましたが、**4件目の実環境エラー**（1件目はv2→v3のインポート時パースエラー、2件目はv3→v4の保存時自己参照エラー、3件目はv6→v7のPostItem保存エラー）として、`Get_Source_File_Content`が次のエラーで失敗しました（ユーザー提供の実行出力3ファイルで確認）。

```
404 File not found
```

**原因（実データで確定）**: 実際の添付`contentUrl`は`https://metijapan.sharepoint.com/teams/pjteam_220400119/Shared Documents/03_課内会議/…`のような形式で、Teamsチャネル添付の実体は**投稿元のチームのサイト**の`Shared Documents`配下にありました。v8までの実装は、サイトを`varSiteAddress`（ファイル保存先のmROOMサイト）に固定し、パスにも`contentUrl`のサイト部分込みの値（`uriPath(contentUrl)`）を渡していたため、「保存先サイトに対して、投稿元サイトのパスを問い合わせる」という食い違いが生じ、404になっていました。

**修正内容（3点）**:
1. **404の根本修正**: `Scope_Save_File`の先頭に`Compose_Source_Site`／`Compose_Source_Path`を追加し、`contentUrl`を`/Shared Documents/`の位置で前後に分割して、前半をサイトURL、後半をサイト配下のパスとして`Get_Source_File_Content`へ渡すよう変更しました（15.5節）。設定値に依存せず、添付が実際に存在するサイトを都度動的に特定できます。
2. **`Filter_File_Attachments`の強化**: whereに`contains(contentUrl, '/Shared Documents/')`を追加し、この形式に合致しない添付（外部リンク等）を候補の時点で除外するようにしました（14.3節）。
3. **添付有無の明示分岐（ユーザー提案）**: `Scope_30_Save_Attachments`（スコープ）を`Condition_Has_File_Attachments`（条件）へ置き換え、ファイル添付が1件以上ある場合のみ後続処理を実行するようにしました（15章）。既存のスコープをそのまま残して外側にIfを追加する案では、ネスト深さの上限（8段）を超えてしまうため、スコープの型自体をIfへ置き換える構成を採用しています。

**v9集計（機械検証済み・0エラー0警告）**: 総アクション数**139**（v8の137に`Compose_Source_Site`／`Compose_Source_Path`が加わった分。スコープ→If置換自体は増減なし）、変数**28個**（不変）。実データ（返信9件中8件添付なし・1件に6添付という構成）とも式レベルで整合することを確認しました。

**v9パッケージの実環境実行結果（重要な進展）**: v9はユーザー環境で実際にインポート・保存・実行され、**フローはエンドツーエンドで完走しました**（封じ込め・台帳Failed記録・エラーログ書き込みが全て機能）。しかし**全添付が`Status=Failed`になる**（例: ６Ｇと７Ｇ.pptx）という新たな事象が発生しました。詳細な原因分析と対処は次のv10項目を参照してください。

#### v10: 添付保存の全件失敗への対処（保存先フォルダー事前作成＋GetFileItem全廃）

v9パッケージを実環境で実行した結果、フロー自体はエンドツーエンドで完走しましたが、**全添付がStatus=Failedになる**事象が発生しました。新しい実行証跡（親投稿50件分のGraph応答）を分析したところ、失敗した添付の`contentUrl`は正しい形式（pjteamサイトの`Shared Documents`配下・非エンコードの生URL）であることを確認しました。つまりv9のサイト・パス導出（`Compose_Source_Site`／`Compose_Source_Path`）自体は正しく機能しており、**失敗の原因は保存側にある**と推定しました。原因の候補は次の2つです。

1. SharePointの「ファイルの作成(CreateFile)」は中間フォルダーを自動作成しません。保存先（`varDestinationPath`）は4階層のフォルダー構成であり、そのいずれかが未作成であれば全件が失敗し得ます。
2. （v9まで存在した）`Get_Saved_File_Properties`（GetFileItem）の「テーブル」欄に渡していた`Shared Documents`は、ライブラリの**URLセグメント**であり、表示名やGUIDではありません。日本語のSharePointサイトでは既定ライブラリの表示名が「ドキュメント」であることが多く、名前解決に失敗して全件失敗した可能性が**最有力候補**です。この場合、直前の`Create_Attachment_File`自体は成功しており、**ファイルは保存先に実際に作成できている**可能性が高いため、再実行時の同名409エラーに注意が必要です。

あわせて、新しい実行証跡から、**Graphが添付`contentUrl`を%エンコード済み（`/Shared%20Documents/`）で返す場合がある**ことも判明しました。既存の`Filter_File_Attachments`／`Compose_Source_Site`／`Compose_Source_Path`は非エンコード表記のみを前提としていたため、エンコード済みの添付が候補の時点で黙って除外される潜在バグも新たに発見しました。

**修正内容（4本柱＋2件の堅牢化）**:

1. **`Scope_05_Ensure_Destination_Folder`を新設**（ルート・`Initialize_ErrorMessage`の直後・`Scope_10`の前。10.2節参照）: `DryRun=いいえ`の場合のみ、保存先フォルダーを1階層ずつ作成（既存フォルダーへのエラーは意図的に無視して継続）し、最後にGETで実在を検証します。検証失敗は実行の最も早い段階での明確な失敗として扱われます（候補1への対処）。
2. **エンコード済みURLの正規化**: `Filter_File_Attachments`のwhereに`/Shared%20Documents/`含有のor条件を追加（14.3節）。`Scope_Save_File`の先頭に`Compose_Source_Url`を追加し、%エンコード判定時のみ`decodeUriComponent()`で正規化してから`Compose_Source_Site`／`Compose_Source_Path`へ渡すようにしました（新たに発見した潜在バグへの対処）。
3. **`GetFileItem`（`{Link}`）を全廃**: `Get_Saved_File_Properties`／`Get_Saved_Archive_Properties`を削除し、保存後URLを既知の値（サイト・ライブラリ・保存先パス・ファイル名）から決定的に組み立てる方式に変更しました（`Compose_Saved_File_Url`／`Set_ArchiveUrl`。16章参照。候補2への対処）。
4. **自己診断エラーメッセージ**: `Compose_LedgerFailed_Body`のErrorMessageに元の`contentUrl`と保存先パスを埋め込み、台帳の1行だけで原因特定できるようにしました（15.5節参照）。
5. ファイル名サニタイズに`Replace_Invalid_Hash`（`#`）／`Replace_Invalid_Percent`（`%`）を追加しました（15.3節）。
6. 検証スクリプトに「`GetFileItem`存在→エラー」「`{Link}`残存→エラー」を恒久検査として追加しました。

**v10集計**: 総アクション数**148**（v9の139に`Scope_05`系7アクション、`Compose_Source_Url`、`Compose_Saved_File_Url`、サニタイズ2件を追加し、`GetFileItem`2件を削除した分）。変数**28個**（不変）。使用operationIdは**5種類**（`GetFileItem`廃止で6→5種類）。機械検証0エラー0警告。

**実環境確認ポイント**: (1)`Verify_Destination_Folder`が成功すること (2)台帳にSaved行とクリック可能な`SavedFileUrl`が記録されること (3)まだ`Status=Failed`が発生する場合は`ErrorMessage`の「元URL=／保存先=」から原因を一意に特定できること (4)**初回実行前に保存先フォルダーの残骸ファイルを確認**すること（候補2が正しければ、v9実行時に実際にはファイルが保存できていた可能性があるため。26章参照）。

**★重要**: v10はここまでの推定原因に基づく**静的な**対処であり、**修正後の実環境での再実行はまだ行っていません**。「全添付Failedが解消され実環境で動作確認済み」であることを意味するものではありません（詳細は6章・27.5節参照）。

### 27.2 実環境での確認が必要な項目（要実環境確認 等）

| # | 項目 | 状況 | 該当章 |
|---|---|---|---|
| 1 | インポート先の環境（開発/テスト/本番）の選定 | 未確認 | 7章 |
| 2 | `@odata.nextLink`の絶対URLをそのまま「URI」欄が受理するか、2ページ目以降が正しく応答するか | 未確認（実働サンプルにページングが無いため参照実績なし） | 11章・12章 |
| 3 | `varChannelId`内の`:`・`@`の扱い | **v5で解決**: `uriComponent()`エンコードを適用（実働サンプルが同形式で動作した実績を根拠に採用） | 11章 |
| 4 | （履歴・v10で対応不要化）`body(...)?['{Link}']`というキー表記が実際のSharePointコネクタで正しく機能するか | **v10で対応不要**: `GetFileItem`自体を廃止し決定的URL構築へ変更したため、`{Link}`を参照する式がフロー内に存在しない | 16章 |
| 5 | SharePointアクションの「サイトのアドレス」「リスト」欄が式のままインポート後も機能するか（`Get_Ledger_Existing`のサイトは`varListSiteAddress`。v7でREST化した4アクションの「サイトのアドレス」は静的な選択値のため対象外。8.2節・8.3節参照） | 未確認 | 8章 |
| 6 | 添付の`contentUrl`から解析したサイト・パスが正しく解決できるか | **v8の実環境実行で実際に404エラーとして発生を確認**。v9で`contentUrl`自体から動的にサイト・パスを導出する方式へ修正し、**v9のZIPは実際に実環境でエンドツーエンドで完走した**（式レベルでは解決済み）。ただし全添付Failedという新事象が発生（27.1章v10項参照） | 5章・15章・27.1章(v9・v10) |
| 7 | 生成した`.doc`をWordで開いた際の警告表示の有無（**要Word表示確認**） | 未確認 | 20章 |
| 8 | 実行アカウントのPower Automateライセンス（**要ライセンス確認**） | 未確認 | 5章 |
| 9 | 3コネクタが組織のDLPポリシーで同一グループに属しているか（**要DLP確認**） | 未確認 | 5章 |
| 10 | フロー1回あたりの実行時間・ループ回数の環境側の上限 | 未確認 | 25章 |
| 11 | SharePointリストの列は**ASCII英名で作成し内部名を一致させる**必要がある（非ASCII列名だと内部名が`OData__x....__`形式になり、本フローの`item`/列名直書きの式と一致しなくなる。実働サンプルで実証済みの事象） | 対応要（作成時にASCII名で作成） | 12.4章・import_guide |
| 12 | REST化した4アクション（`Create_Ledger_Item`／`Create_Ledger_Item_Failed`／`Create_Run_Log`／`Create_Error_Log`）で、テナント設定により`__metadata`型指定が要求されるか（**要実環境確認**） | 未確認 | 15.6章 |
| 13 | `SavedFileUrl`・`ArchiveUrl`列がハイパーリンク型で誤って作成されていないか | 対応要（12.4節どおり複数行テキスト＝書式なしで作成） | 12.4章・15.6章 |
| 14 | `varSiteAddress`（mROOM）と`varListSiteAddress`（pjteam）の2サイトが、それぞれ正しい実サイトを指しているか（**v8で追加**。片方だけ変更するとファイル保存・リスト操作のいずれかが失敗する） | 未確認 | 10.1章・8.2章・8.3章 |
| 15 | 添付が全件`Status=Failed`になる事象（**v9実環境実行で発生**）が、v10の対処（`Scope_05`によるフォルダー事前作成・`GetFileItem`全廃）で解消するか | **未確認**（静的検証のみ。実環境再実行はまだ実施していない） | 10.2章・15.5章・16章・27.1章(v10) |
| 16 | 初回実行前の保存先フォルダー残骸ファイル確認（v9実行で実際にファイルが保存できていた場合、再実行が409エラーになる可能性） | 対応要（実行前に手動確認） | 10.2章・26章・27.1章(v10) |
| 17 | `varDestinationPath`が5階層以上の場合、`Scope_05`のフォルダー事前作成は4階層までしか対応しない（**v10新設の制約**） | 対応要（4階層以内に収めるか、L5以降のアクションを追加） | 10.2章・§3 varDestinationPath |

### 27.3 設計上の残る制約（v10でも実装済みの挙動として認識しておくべき点）

- **主催者は常に固定文字列「不明」**です。投稿者をそのまま主催者として扱うことはしていません（13章）。会議情報からの補完は未実装です。
- **会議日付の決定方法は「投稿日時のJST変換」のみ**です。本文からの日付抽出（例:「〇月〇日開催」）は、正規表現関数が標準式に存在しないため実装していません（13章）。
- **会議・添付単位での失敗封じ込めは、添付ファイル本体のコピー（`Scope_Save_File`）の範囲に限定されます。** それ以外の箇所（Teams取得・`Get_Ledger_Existing`・HTML生成等）で例外が発生した場合は、引き続き実行全体が失敗（Failed）として扱われ、`MeetingArchiveRunLog`に記録されます（21.4節）。
- **定期実行（差分実行）機能は実装されていません。** 本フローは実行のたびに「実行時点からLookbackDays日前まで」を毎回取得する設計であり、前回実行との差分検知は行いません。分割実行時は複数のWord互換ファイルが生成されます（25章）。
- **単一フロー・子フローなしの設計です。** 旧版にあった「会議一時保存リスト（Staging）」「子フロー呼び出し」はいずれも使用していません。会議の並べ替えはフロー内配列変数への`sort()`適用のみで行います（2章・17章）。
- **台帳・実行ログ書込み4アクションの「サイトのアドレス」は静的値です（v7）。** `Create_Ledger_Item`／`Create_Ledger_Item_Failed`／`Create_Run_Log`／`Create_Error_Log`は、`PostItem`から SharePoint「HTTP要求を送信します」(REST)に置き換わったことに伴い、「サイトのアドレス」欄が変数を参照する式ではなく静的な選択値になっています。保存先サイトを変更する場合は、10章の`varListSiteAddress`変更（**v8で対象変数がvarSiteAddressから変わりました**）に加えてこの4アクションを個別に編集する必要があります（8.3節・15.6節参照）。
- **サイトが2系統に分かれています（v8）。** ファイル保存（添付・総括doc）は`varSiteAddress`（mROOM）、台帳・実行ログのリスト操作は`varListSiteAddress`（pjteam）を使用します。1つのサイトに統合されていると誤解して片方だけ変更すると、ファイル保存またはリスト操作のいずれかが失敗します（10.1節参照）。
- **保存先フォルダーの事前作成は最大4階層までです（v10）。** `Scope_05_Ensure_Destination_Folder`は`varDestinationPath`の先頭1〜4階層を`join`／`take`／`split`で組み立てて作成します。5階層以上のパスを設定する場合は、この仕組みを拡張しない限り最深階層は手動で作成しておく必要があります（10.2節参照）。
- **保存後URLは決定的に構築される値であり、SharePoint側の実際のファイル状態を都度確認しているわけではありません（v10）。** `Compose_Saved_File_Url`／`Set_ArchiveUrl`は、`CreateFile`が成功したという実行結果のみを根拠にURLを組み立てます。CreateFile成功後にファイルが外部から削除・移動された場合でも、記録されるURLの値自体は変わりません（v9までの`GetFileItem`方式も、取得したプロパティが即座に古くなり得る点は同様でした）。

### 27.4 採用しなかった構成（意図的な不採用）

- **Word Online (Business) のテンプレート機能・PDF変換機能はプレミアムコネクタのため不採用**です（4章）。
- **真正のOpen XML形式（`.docx`）は標準コネクタのみでは生成できないため不採用**とし、HTML文字列を`.doc`拡張子で保存する方式を採用しています。**HTMLの中身を`.docx`という拡張子にリネームすることはしていません**（正しく開けない壊れたファイルになるため）。業務上`.doc`の警告表示が許容できない場合は`.html`拡張子への変更を検討してください（20章）。
- Azure Functions・Open XML処理・外部/プレミアムの文書生成コネクタ、汎用HTTP／HTTP with Microsoft Entra ID、アプリ登録を前提とした構成はいずれも不採用です（4章）。
- 実働サンプル（`create_meeting_list_sample_20260716105612.zip`）に見られた設計（SetVariable上書きによる添付蓄積、ページング無し、封筒形ParseJsonスキーマ、値式末尾の`\n`混入等）は、動作実績はあるものの設計上劣位と判断し移植していません。詳細は`../../../../../references/sample_export_analysis.md`を参照してください。

### 27.5 検証の範囲

本パッケージについて検証済みなのは、`../source/package/`配下のJSON5ファイルすべてがパースできること、`runAfter`参照がすべて同階層に存在すること、`InitializeVariable`が全てトップレベルに配置されていること、参照している変数28個と初期化している変数28個が過不足なく一致していること（v3時点27個→v4で`varDocHtmlParts`廃止により26個→v6で`varRunLogList`追加により27個→**v8で`varListSiteAddress`追加により28個**。v9・v10では変数の増減なし）、`body(...)`・`outputs(...)`の参照先アクションがすべて実在すること、使用している`operationId`が実在する**5種類**のみであること（v7で`PostItem`を廃止して7→6種類、**v10で`GetFileItem`を廃止して6→5種類**）、ユーザー固有情報（実メールアドレス・テナントID・接続GUID等）が混入していないこと、トリガーが`manual`の1つのみであること、フローが1つのみであること、ZIPを再展開した結果が構造検証済みの雛形と同一であることです。`Get_Ledger_Existing`のサイト参照が`varListSiteAddress`に、REST4アクションの静的サイト値がpjteamになっていることも確認済みです（v8で新設した「初期化済みだが未参照の変数」検査を含む）。**v10で新設した恒久検査**として、`GetFileItem`が現行仕様として残存していないこと、`{Link}`が現行仕様の式として残存していないこと（いずれも変更履歴内の言及を除く）も確認済みです。

総アクション数はv10で**148**（v1の123→v2で129→v4で131→v6で132→v7で136→v8で137→v9で139→**v10で148**。`Scope_05`系7＋`Compose_Source_Url`＋`Compose_Saved_File_Url`＋サニタイズ2−`GetFileItem`2）。SetVariableアクション13件のうち自己参照は**0件**（v4で全面除去）。コネクタ出力の`body/`参照欠落も**0件**（v6で修正）。`PostItem`の残存も**0件**（v7で新設した機械検査）。旧`Scope_30_Save_Attachments`の残存も**0件**（v9で新設した機械検査）。`GetFileItem`／`{Link}`の残存も**0件**（v10で新設した機械検査。変更履歴内の言及を除く）。AppendToArrayVariable8件・AppendToStringVariable7件・IncrementVariable5件・Apply to each（Foreach）8件（すべて並列オフ）。Scope 9件（`Scope_05`を含む）・If 8件（`Condition_Provision_Destination`を含む）。

**実環境での経緯（正直な記載）**: v2のZIPは実環境でのインポート自体に失敗しました（テンプレート言語式の`@`不正エラー。v3で修正）。v3のZIPはユーザー環境での**インポート自体には成功**しましたが、その後の**保存**で`WorkflowRunActionInputsInvalidProperty`（SetVariable自己参照）エラーが発生しました。v4でこの原因を全面的に除去し、v5でさらに堅牢化を行いました。v6のZIPはインポート自体には問題がなかったものの、**保存**時に3件目の実環境エラー（`OpenApiOperationParameterValidationFailed`。`PostItem`の`item`欠落）が発生し、v7でPostItemをSharePoint「HTTP要求を送信します」(REST)に置き換えて原因を除去しました。v8では台帳・実行ログのリスト操作サイトをpjteamへ分離し、**このv8のZIPは実際に実環境でインポート・保存・実行に成功し、`MeetingArchiveRunLog`への書き込みまで到達しましたが、実行時に`Get_Source_File_Content`が404エラー（4件目の実環境エラー）で失敗しました。** v9はこの404の原因（`contentUrl`のサイト・パス解析の誤り）を修正し、**v9のZIPは実際に実環境でエンドツーエンドで完走しました**が、**全添付が`Status=Failed`になる**（5件目の実環境事象）という新たな問題が発生しました。v10はこの事象への対処（保存先フォルダー事前作成・`GetFileItem`全廃による決定的URL構築等）ですが、**修正後の実環境での再実行はまだ行っていません。** 上記の「検証済み」はすべてJSON構文・参照整合性・自己参照監査・コネクタ出力参照監査・`PostItem`／`GetFileItem`残存監査・未参照変数監査等の**静的検査**の結果であり、v10について「全添付Failedが解消される」「正しく実行できる」ことそのものを保証するものではない点にご留意ください。

