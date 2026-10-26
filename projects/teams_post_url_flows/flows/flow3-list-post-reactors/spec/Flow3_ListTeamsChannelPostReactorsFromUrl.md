# Flow3_ListTeamsChannelPostReactorsFromUrl — フロー定義の説明

Teams投稿URLを解析し、そのチャネル投稿に**リアクションした人を一覧化**して、Object型変数とJSON文字列型変数に格納する手動トリガーのクラウドフローです。
表示名とメールアドレスは、チャネルメンバー一覧とユーザーIDで突き合わせて補います。
**OneDriveフォルダURLを入力すると、`displayName` / `email` の2列CSVをそのフォルダへ保存します**（任意）。

| 項目 | 値 |
|---|---|
| フロー名（論理名） | `Flow3_ListTeamsChannelPostReactorsFromUrl` |
| 表示名 | Flow3 Teams投稿URLからリアクションした人を一覧化 |
| トリガー | 手動でフローをトリガーします（`manual` / `Request` / `kind: Button`） |
| 使用コネクタ | Microsoft Teams（`shared_teams`）＋ SharePoint（`shared_sharepointonline`。CSV出力用）・いずれも標準（プレミアム不要） |
| アクション総数 | 150 |
| 生成元 | `../source/build_flow3.py`（雛形: `flow1-get-channel-post/source/build_flow1.py`） |
| 検証 | `../source/validate_flow3.py`（エラー0 / 警告0） |
| パッケージ | `../release/Flow3_ListTeamsChannelPostReactorsFromUrl_20261026130049.zip`（CSV出力付き。それより前のZIPは使わない） |
| 実環境 | CSV出力**前**の版（`_20261026124224.zip`）は**インポート・実行 成功・出力OK**（2026-10-26・利用者報告）。**CSV出力付きの現行版は未実施** |

**`definition.json` は生成物です。** 修正は必ず `../source/build_flow3.py` を編集し、再生成 → 検証 → 再パッケージしてください（`CLAUDE.md` 不変則1）。

---

## 1. 目的

チャネル投稿（例: 「確認したらリアクションしてください」という連絡）に**誰がリアクションしたか**を、表示名・メールアドレス付きで取り出す。結果はJSONで返し、指定があれば Excel で開ける CSV として OneDrive に保存する。

## 2. トリガーと入力

| 入力名 | 表示名 | 型 | 必須 |
|---|---|---|---|
| `TeamsPostUrl` | Teams投稿URL | string | **はい** |
| `OutputFolderUrl` | OneDriveフォルダURL（任意） | string | いいえ（空欄ならCSVを作らない） |
| `OutputFileName` | ファイル名（任意） | string | いいえ（空欄なら `reactors_yyyyMMdd_HHmmss.csv`。日時は日本時間） |

Teams投稿URLは、投稿の「…」→「リンクをコピー」で得たものをそのまま貼り付けます。URL解析は Flow1 と同一の式です（仕様は [docs/url_parsing_spec.md](../../../docs/url_parsing_spec.md)）。

- **対象は親投稿です。** 返信のURLを貼った場合も `parentMessageId` から親投稿へ解決し、親投稿のリアクションを集計します（Flow1 と同じ挙動）。返信へのリアクションは対象外です。

### OneDriveフォルダURLの書式

**OneDrive をブラウザで開き、保存先フォルダを表示した状態のアドレスバーのURL**を貼り付けるのが確実です。

| 形式 | 例 | 扱い |
|---|---|---|
| アドレスバー（`id=` 付き） | `https://{tenant}-my.sharepoint.com/my?id=%2Fpersonal%2F{user}%2FDocuments%2F{フォルダ}` | 対応（`…/_layouts/15/onedrive.aspx?id=…` も同じ） |
| パスそのまま | `https://{tenant}-my.sharepoint.com/personal/{user}/Documents/{フォルダ}` | 対応（末尾 `/`・`%20` 等のエンコードも可） |
| SharePoint／Teams のライブラリ | `https://{tenant}.sharepoint.com/sites/{サイト}/Shared%20Documents/Forms/AllItems.aspx?id=…` | 対応（`/sites/`・`/teams/` 配下） |
| 共有リンク | `https://{tenant}-my.sharepoint.com/:f:/g/personal/…` | **非対応**（実パスを持たない）→ `ERR_OUTPUT_FOLDER_SHARING_LINK` |

URLのサーバー相対パスの先頭2階層（`/personal/{user}`・`/sites/{name}`・`/teams/{name}`）をサイト、残り（例 `/Documents/{フォルダ}`）を保存先フォルダとして扱います。**フォルダは事前に存在している必要があります**（CreateFile は中間フォルダを作らない。error_catalog #7）。

## 3. 出力

### JSON（`varResultObject` / `varResultJson`）

実行履歴の `Scope_Finalize` → `Compose_Flow_Output` で確認できます。

```json
{
  "success": true,
  "flowName": "Flow3_ListTeamsChannelPostReactorsFromUrl",
  "sourceUrl": "<入力URL>",
  "retrievedAt": "2026-10-26T03:00:00.0000000Z",
  "identifiers": { "tenantId": "…", "teamId": "…", "channelId": "19:…@thread.tacv2",
                   "urlMessageId": "…", "parentMessageId": "…", "targetMessageId": "…" },
  "message": { "id": "…", "createdDateTime": "…", "subject": "…",
               "from": { "displayName": "…", "userId": "…" }, "webUrl": "…" },
  "memberLookup": { "loaded": true, "httpStatusCode": "200", "memberCount": 42 },
  "reactorCount": 2,
  "reactionCount": 3,
  "table": [
    { "displayName": "山田 太郎", "email": "{user@example.com}" },
    { "displayName": "佐藤 花子", "email": "{user2@example.com}" }
  ],
  "csv": "\"displayName\",\"email\"\r\n\"山田 太郎\",\"{user@example.com}\"\r\n…",
  "export": { "status": "created", "errorCode": "", "httpStatusCode": "200",
              "site": "https://{tenant}-my.sharepoint.com/personal/{user}",
              "folderPath": "/Documents/{フォルダ}", "fileName": "週次_確認者.csv",
              "fileUrl": "https://{tenant}-my.sharepoint.com/personal/{user}/Documents/{フォルダ}/週次_確認者.csv" },
  "reactors": [
    {
      "userId": "{userObjectId}",
      "displayName": "山田 太郎",
      "email": "{user@example.com}",
      "userIdentityType": "aadUser",
      "memberLookup": "found",
      "reactionCount": 2,
      "reactions": [
        { "reactionType": "like",  "reactionDisplayName": "Like",  "createdDateTime": "…" },
        { "reactionType": "heart", "reactionDisplayName": "Heart", "createdDateTime": "…" }
      ]
    }
  ],
  "reactions": [ { "userId": "…", "displayName": "…", "email": "…", "userIdentityType": "…",
                   "memberLookup": "…", "reactionType": "…", "reactionDisplayName": "…",
                   "createdDateTime": "…" } ],
  "warnings": []
}
```

| キー | 内容 |
|---|---|
| `table` | **`displayName` と `email` だけの表**（1人1行・初めてリアクションした順）。CSV と同じ内容 |
| `csv` | CSV本文（BOMなしの文字列。フォルダ未指定でも返すので、コピーして使える） |
| `export.status` | `notRequested`＝フォルダURL未入力 / `created`＝作成済み / `failed`＝作成失敗（`httpStatusCode` 参照） / `invalidInput`＝URL・ファイル名が不正（`errorCode` 参照） |
| `export.fileUrl` | 作成したファイルのURL（`created` のときだけ） |
| `reactors` | 1人1件の詳細（ユーザーID・リアクション種別の一覧付き） |
| `reactions` | リアクション1件ごとの一覧（重複排除なし。集計の元データ） |
| `memberLookup`（各人） | `found`＝メンバー一覧で一致 / `notFound`＝一覧に居ない（退出者・ゲスト等。表示名・メールは空） / `unavailable`＝一覧自体を取得できなかった |
| `memberLookup`（全体） | メンバー一覧を取得できたか・HTTPステータス・件数。リアクション0件のときは取得しないため `loaded: false`・`httpStatusCode: "0"` |
| `warnings` | `WARN_MEMBER_LOOKUP_FAILED` / `WARN_CSV_EXPORT_FAILED` / `WARN_CSV_EXPORT_SKIPPED`。**警告があっても `success` は true** |

### CSVファイル

```text
"displayName","email"
"山田 太郎","{user@example.com}"
"佐藤 花子","{user2@example.com}"
```

- UTF-8（**BOM付き**。Excel でダブルクリックして開いても日本語が文字化けしない）・改行 CRLF。
- すべての値を `"` で囲み、値の中の `"` は `""` に二重化する（カンマ・引用符を含む名前でも列がずれない）。
- リアクションした人が0人のときは見出し行だけのファイルになる。

### CSVの入力エラー（`export.errorCode`）

| コード | 条件 |
|---|---|
| `ERR_OUTPUT_FOLDER_URL_INVALID` | `https://` で始まらない |
| `ERR_OUTPUT_FOLDER_NOT_ONEDRIVE` | ホストに `sharepoint.` を含まない |
| `ERR_OUTPUT_FOLDER_SHARING_LINK` | 共有リンク（`/:f:/…` 等） |
| `ERR_OUTPUT_FOLDER_PATH_NOT_FOUND` | フォルダのパスを取り出せない（`…/my` だけ、サイト直下、`.aspx` で終わる等） |
| `ERR_OUTPUT_FILE_NAME_INVALID` | ファイル名に `" * : < > ? / \ |` を含む |

### 失敗時（投稿を取得できない等）

Flow1 と同じ形式（`success: false` と `error.code` / `error.message` / `error.stage` / `error.details`）です。エラーコードは [docs/json_schema.md](../../../docs/json_schema.md) §5 と共通です。

## 4. 処理の流れ（Scope）

```text
Initialize_*（34変数・トップレベル）
→ Scope_ParseUrl            URL解析（Flow1と同一）
→ Scope_GetTeamsData        GET /teams/{teamId}/channels/{channelId}/messages/{messageId}
                            → reactions を varRawReactions へ退避
→ Scope_GetChannelMembers   リアクションが1件以上のときだけ
                            GET /teams/{teamId}/channels/{channelId}/members を nextLink 追跡
→ Scope_BuildReactors       ① リアクション1件ごとにメンバーを Filter して正規化（初出の userId を記録）
                            ② userId ごとに Filter / Select して1人1件にまとめ、CSV行を追加
→ Scope_ExportCsv           フォルダURLが入力されたときだけ: URL解析 → 入力検査 → SharePoint CreateFile
→ Scope_CreateResult        結果JSONの作成（table / csv / export を含む）
→ Scope_ErrorHandler        Scope_CreateResult が Failed/Skipped/TimedOut のときだけ（変数のみ参照）
→ Scope_Finalize            常に実行。Compose_Flow_Output に結果を出す
```

## 5. 設計上の判断

| 判断 | 理由 |
|---|---|
| 表示名・メールは**チャネルメンバー一覧**で補う | Graph の `reactions[].user.user` は `id` と `userIdentityType` だけで、`displayName` が null のことが多く、メールは含まれない。`/members` は `aadUserConversationMember` の `userId` / `displayName` / `email` を返す。`/users/{id}` は Teams コネクタの Graph HTTP 要求で許可されるパスの範囲外になる可能性があるため使わない |
| メンバー一覧の取得失敗で**フローを失敗させない** | 一覧取得には投稿の読み取りとは別の権限が要る可能性がある（§8）。失敗時もユーザーIDの一覧は有用なので、`memberLookup: "unavailable"` と警告を付けて返す |
| Do until 内で取得失敗時に失敗フラグを立て、終了条件 `or(empty(nextLink), varMembersLookupFailed)` で止める | 反復が失敗した後も Do until が続くかは実機の挙動に依存する。どちらでも1回で止まるようにする（テストで両方を評価）。nextLink を空文字に「設定」する方式は保存エラーになったため使わない（§10） |
| リアクション0件なら一覧を取得しない | 不要な Graph 呼び出しと権限エラーを避ける |
| `body('Get_Parent_Message')` を後続 Scope から参照しない | 解析エラーで取得が Skipped のとき、条件式から参照すると壊れる。リアクションは取得直後に変数へ退避する（`validate_flow3.py` §8 で機械検査） |
| 重複排除は「初出の userId を配列変数に追加」で行う | `SetVariable` の自己参照を使わない（`handbook/rules/03`）。配列の `contains()` で判定し、`AppendToArrayVariable` で追加する。CSV行も `AppendToStringVariable` で追加する |
| ループ内で外側の要素は `items('<ループ名>')` で参照する | Filter array の `where` 内の `item()` はフィルタ対象側を指すため、取り違えを防ぐ |
| 出力形式は **CSV（BOM付きUTF-8）** | 本物の .xlsx は、標準コネクタだけでは雛形ファイルと Excel コネクタ（ドライブID等の指定）が必要になり、構成が重く前例も無い。CSV は Excel でそのまま開け、利用者とも合意済み |
| 書き込みは **SharePoint コネクタの CreateFile** | OneDrive for Business の実体は SharePoint の個人用サイトなので、フォルダURLからサイトとパスを導けば1アクションで書ける。CreateFile に式で `dataset` を渡す方式は archive-meetings で実環境の実績がある。OneDrive コネクタは接続ユーザー自身の OneDrive にしか書けず、URL指定と相性が悪い |
| CSV出力の失敗で**フローを失敗させない** | URLの貼り間違い・権限不足でも、一覧（JSON の `table` / `csv`）は得られるようにする。`export.status` と `warnings` で知らせる |
| URLの切り出しに `substring` を使わない | 開始位置が長さ以上だと失敗し、`if()` は両分岐を先行評価するため短い入力で壊れる（error_catalog #10）。`split` / `take` / `reverse` / `join` で切り出す（`validate_flow3.py` で機械検査） |
| 変数の初期化・設定の値に空文字・`false` を渡さない | 保存時に「'値' は必須です」になる（§10）。`build_flow3.py` の `nonblank()` で `@string('')` / `@false` に置換する |

## 6. ループとページング

| ループ | 対象 | 並列 | 上限 |
|---|---|---|---|
| `Do_Until_Members_Paging` | メンバー一覧（`@odata.nextLink` が空になるか、取得に失敗するまで） | — | 5,000反復・1時間 |
| `Process_Retrieved_Members` | 1ページ分のメンバー | オフ | — |
| `Apply_To_Each_Reaction` | 親投稿のリアクション | オフ | — |
| `Apply_To_Each_Reactor` | 重複排除した userId | オフ | — |

リアクション1件ごとにメンバー配列を Filter するため、計算量は「リアクション数 × メンバー数」です。通常のチャネル（数百人・リアクション数十件）なら問題ありません。

## 7. 冪等性

Teams 側は読み取り専用（GET のみ）です。書き込みは、フォルダURLを入力したときの CSV 作成1件だけです。
**同じフォルダ・同じファイル名で再実行したときの挙動（上書きか失敗か）は要実環境確認**です。失敗した場合は `export.status: "failed"` と警告で返ります。ファイル名を省略すると日時付きの名前になるため衝突しません。

## 8. 要実環境確認

| 項目 | 内容 |
|---|---|
| CSV出力付きの現行版 | インポート・保存・実行は**未実施**。インポート時に **SharePoint の接続**も選ぶ必要がある（Teams と合わせて2接続） |
| CSVの保存 | OneDrive のフォルダURLから導いたサイト・パスに CreateFile で書けるか。BOM が付いて Excel で文字化けしないか |
| 同名ファイル | 既存ファイルがある場合に上書きされるか、失敗するか |
| `/members` の権限 | 現行版の前の版（`_20261026124224.zip`）で出力OKの報告あり（2026-10-26）。表示名・メールが実際に埋まったかの詳細は未記録 |
| リアクションの応答形 | `reactions[].user.user.id` が Entra ID のオブジェクトIDで、`/members` の `userId` と一致する前提。カスタム絵文字のリアクションでの `reactionType` の値 |
| `/members` の `email` | ゲスト・外部ユーザーで空になる可能性 |
| `/members` のページング | 大規模チームで `@odata.nextLink` が返るか（返らなければ1回で終わる） |
| チャネル種別 | 標準・プライベートは動作する想定。共有チャネルは Flow1 と同じく `groupId` 不一致で 404 の可能性 |
| 失敗時の実行履歴の見え方 | メンバー取得・CSV作成に失敗したとき、該当 Scope が「失敗」と表示されたうえで後続が続行し、実行全体は成功になる想定 |

## 9. 検証

| 区分 | 結果 |
|---|---|
| 静的検証（`validate_flow3.py`。Flow1 の全検査＋Flow3 固有の配線・CSV出力の検査） | **エラー0 / 警告0** |
| 共通リンター（`python tools/wdl_lint.py --all .`） | **指摘0件** |
| URL解析の回帰テスト（`tests/run_url_parse_tests.py flow3`） | **20件中20件合格** |
| 通し回帰テスト（`tests/run_reactor_flow_tests.py`。ダミー応答で definition.json の式を評価） | **24件中24件合格**（12ケース × Do until の2つの挙動仮定） |
| ZIP再展開検査（`validation/extract_check.py`） | **エラー0** |
| 実環境 | CSV出力前の版はインポート・実行・出力OK（利用者報告）。現行版は**未実施** |

通し回帰テストのケース:
- 一覧化: 同一人物の複数リアクションの集約と2ページのメンバー一覧 / メンバー一覧が 403 / リアクション0件 / メンバー一覧に居ない人 / URL解析エラー / 投稿取得 404
- CSV出力: アドレスバー形式（`my?id=`・日本語と空白を含むフォルダ・`"` を含む名前）/ パス形式（末尾 `/`・ファイル名省略）/ SharePoint のビューURL / 入力エラー6種（共有リンク・`/my` だけ・`https://` 無し・SharePoint以外・不正なファイル名・サイト直下）/ 作成 403 / フォルダ未入力

## 10. 修正履歴

| 日付 | 局面 | 内容 |
|---|---|---|
| 2026-10-26 | 保存時 | `'Stop Member Paging On Failure' のパラメーターが無効です。エラー: '値' は必須です。` — 「変数の設定」の値に空文字 `""` を渡していた。アクションを削除し、`Set_Members_Lookup_Failed_In_Loop`（`true` を設定）と Do until の終了条件で止める方式に変更（`_20261026123718.zip`）。`validate_flow3.py` に「SetVariable の値が空」の検査を追加 |
| 2026-10-26 | 保存時（予防） | 同型の予防: 変数の初期化・設定の値に残っていた空文字10件・`false` 3件を `@string('')` / `@false` の式に置換（`build_flow3.py` の `nonblank()` で一括）。`validate_flow3.py` の検査を「初期化・設定の値が空文字 / null / false」に拡張（`_20261026124224.zip`）。**この版でインポート・実行・出力OK（利用者報告）** |
| 2026-10-26 | 機能追加 | `displayName` / `email` の表（`table`・`csv`）を結果JSONに追加。任意入力「OneDriveフォルダURL」「ファイル名」を追加し、指定時は SharePoint CreateFile で BOM付きCSVを保存（`Scope_ExportCsv`・`export`）。109 → 150アクション（削除0・追加41）（`_20261026130049.zip`）。**実環境は未実施** |
