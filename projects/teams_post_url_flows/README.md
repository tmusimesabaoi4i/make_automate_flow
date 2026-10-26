# teams_post_url_flows — Teams投稿URLから投稿・全返信を取得する2フロー

Microsoft Teams のチャネル投稿で「リンクをコピー」して得たURLを入力すると、その投稿（Flow1）または投稿への全返信（Flow2）を取得し、Object型変数とJSON文字列型変数に格納する、**独立した2本のクラウドフロー**です。

| | Flow1 | Flow2 |
|---|---|---|
| フロー名 | `Flow1_GetTeamsChannelPostFromUrl` | `Flow2_GetAllTeamsChannelPostRepliesFromUrl` |
| 取得するもの | 対象の親投稿1件 | 対象の親投稿＋その**全返信** |
| アクション数 | 67 | 81 |
| 使用コネクタ | Microsoft Teams 1本（**プレミアム不要**） | 同左 |
| 出力 | `varResultObject` / `varResultJson` | `varResultObject` / `varResultJson` / `varReplies` |

どちらも単独でインポート・実行できます。

> **状態: 静的検証を通過し、実環境でのインポートと実行に成功しました（2026-07-24・利用者報告）。**
> ただし報告は「安全にインポートでき、安全に実行できた」という範囲です。**返信51件超でのページング**、添付・メンションを含む投稿、異常系（存在しない／削除済み／権限なし／共有チャネル）の実挙動は未確認のまま残っています。詳細は [tests/validation_report.md](tests/validation_report.md) §5・§7 を参照してください。

---

## クイックスタート

1. [docs/installation.md](docs/installation.md) の手順でZIPをインポートする（「パッケージのインポート **(レガシー)**」を使用）
2. Teams接続を選択する（必要な接続は1つだけ）
3. フローを開いて**すぐ保存**する（保存でしか出ないエラーの早期発見）
4. Teamsで対象投稿の「…」→「リンクをコピー」でURLを取得
5. フローを実行し、「Teams投稿URL」にURLを貼り付ける
6. 実行履歴の `Scope_Finalize` → `Compose_Flow_Output` で結果を確認する

インポート用ZIP:

- `flows/flow1-get-channel-post/release/Flow1_GetTeamsChannelPostFromUrl_20260724190952.zip`
- `flows/flow2-get-post-replies/release/Flow2_GetAllTeamsChannelPostRepliesFromUrl_20260724190952.zip`

---

## 成果物の場所

```text
projects/teams_post_url_flows/
├── README.md                      ← このファイル
├── docs/                          両フロー共通のドキュメント
│   ├── installation.md            インポート手順・接続参照の設定手順
│   ├── usage.md                   実行方法・入力・出力の読み方
│   ├── url_parsing_spec.md        URL解析仕様（式の全文と設計根拠）
│   ├── connector_requirements.md  コネクタ・権限・Graph使用理由・取得上限
│   ├── json_schema.md             出力JSON仕様（成功時・エラー時・エラーコード一覧）
│   └── troubleshooting.md         症状別の対処
├── tests/
│   ├── test_cases.md              正常系11・異常系10 の全ケースと確認状況
│   ├── validation_report.md       検証レポート（実施済み検証と未確認事項）
│   ├── run_url_parse_tests.py     URL解析の回帰テスト（definition.json の式を直接評価）
│   └── url_parse_test_result.txt  テスト実行結果（40件合格）
└── flows/
    ├── flow1-get-channel-post/
    │   ├── spec/Flow1_GetTeamsChannelPostFromUrl.md   フロー定義の説明
    │   ├── source/                ← 唯一の編集元
    │   │   ├── build_flow1.py     definition.json / manifest 群の生成
    │   │   ├── validate_flow1.py  静的検証（検証の正典）
    │   │   └── package/           生成物（レガシー5ファイル構造）
    │   ├── validation/            検証証跡
    │   │   ├── action_outline.txt      実行順のアクション一覧
    │   │   ├── validate_result.txt     静的検証の出力
    │   │   ├── extract_check.py        ZIP再展開検査
    │   │   ├── extract_check_result.txt 検査結果
    │   │   └── extracted/              展開したZIPの中身（検証用コピー）
    │   └── release/               インポート用ZIP（日時付き）
    └── flow2-get-post-replies/    （同構成）
```

`source/package/` と `release/*.zip` は**生成物**です。`definition.json` を直接編集せず、`source/build_flow*.py` を編集して再生成してください（`CLAUDE.md` 不変則1）。

---

## 設計の要点

### URL解析

- **固定文字数・固定位置に依存しません。** すべて区切り文字（`#` `?` `&` `/` `/l/message/`）による分割です。
- **クエリの順番に依存しません。** 前後に `&` を付けた正規化クエリを `'&<名前>='` で分割する**名前アンカー方式**。`parentMessageId` が `messageId` に部分一致する問題も起きません。
- **URLエンコードされたチャネルIDを復号します**（`%3A` → `:` / `%40` → `@`）。非エンコードのURLでも無害に素通りします。
- **実在確認済みの関数だけを使います。** 本リポジトリの実働 `definition.json` に出現実績のある関数のみで構成し、`validate_flow*.py` の許可リスト検査で機械的に担保しています。指示された `uriQuery()` / `uriPath()` / `uriComponentToString()` は使わず、`split()` と `decodeUriComponent()` に置き換えました（理由は [docs/url_parsing_spec.md](docs/url_parsing_spec.md) §2）。

### 取得方式

**Microsoft Teams 標準コネクタの「Send a Microsoft Graph HTTP request」(`shared_teams` / `HttpRequest`)** のみを使います。プレミアムコネクタ・Azure ADアプリ登録・管理者同意はいずれも不要です。ネイティブの投稿取得アクションを使わなかった理由は [docs/connector_requirements.md](docs/connector_requirements.md) §2 に記載しています。

### 全返信の取得（Flow2）

`@odata.nextLink` を `Do until` で追跡し、空になるまで全ページを取得します。`$top=50` は1ページあたりの件数であり、**先頭N件で打ち切る処理は定義中にありません**。蓄積は Apply to each ＋「配列変数に追加」で1件ずつ行い、`SetVariable` の自己参照（`Self reference is not supported` の原因）を使いません。並列処理は全ループでオフです。

### エラー処理

Scope を直列に連鎖させ、`Scope_ErrorHandler` の `runAfter` を**最終Scope1本だけ**に張ります。複数Scopeを列挙するとAND判定になり「前段成功・中段失敗」でハンドラが発火しないためです。ハンドラは**変数だけ**を参照するため、未実行アクションの参照で自壊しません。

エラー時も `varResultObject` / `varResultJson` に結果が入り、フローは完走します。12種類のエラーコードで原因を区別します（[docs/json_schema.md](docs/json_schema.md) §5）。

---

## 検証状況

| 区分 | 結果 |
|---|---|
| 静的検証（`validate_flow*.py`） | **エラー0 / 警告0**（両フロー） |
| URL解析のオフライン検証 | **40件中40件合格** |
| ZIP再展開検査（`extract_check.py`） | **エラー0**（両フロー） |
| 実環境のインポート | **成功**（2026-07-24） |
| 実環境の実行 | **成功**（2026-07-24） |
| 実データでの網羅確認（返信51件超・添付・異常系） | **未確認** |

URL解析の検証は、設計書の再実装ではなく**生成済み `definition.json` の式そのもの**を評価しています。
評価器は案件横断の共通ツール [`tools/wdl_eval.py`](../../tools/wdl_eval.py) を使います（案件ごとに複製しません）。

再検証:

```powershell
cd projects/teams_post_url_flows
python flows/flow1-get-channel-post/source/build_flow1.py
python flows/flow1-get-channel-post/source/validate_flow1.py
python flows/flow2-get-post-replies/source/build_flow2.py
python flows/flow2-get-post-replies/source/validate_flow2.py
python tests/run_url_parse_tests.py
python flows/flow1-get-channel-post/validation/extract_check.py
python flows/flow2-get-post-replies/validation/extract_check.py
```

---

## 制約

| 項目 | 内容 |
|---|---|
| 対応するURL | Teamsチャネル投稿（`teams.microsoft.com` / `teams.cloud.microsoft` の `/l/message/…`）。返信のURLも可（親投稿へ解決） |
| 対応しないURL | 1対1チャット・グループチャット・会議チャット・Viva Engage・Teams以外のM365 URL（明示的にエラーを返す） |
| 必要なコネクタ | Microsoft Teams 1本（標準・プレミアム不要） |
| 必要な権限 | 対象チームのメンバーであること（**要実環境確認**） |
| 返信取得の上限 | `$top=50`／ページ、`Do until` 5,000反復・1時間、フロー実行時間 目安30分（実務上はこれが先に効く） |
| チャネル種別 | 標準・プライベート・共有はいずれも**要実環境確認**。特に共有チャネルは `groupId` 不一致で404の可能性 |
| インポート後の追加設定 | **不要**（環境固有の値を保持する変数がありません） |

---

## 関連

- 案件横断の共通知識: [`handbook/`](../../handbook/)（[rules](../../handbook/rules/) / [knowledge](../../handbook/knowledge/) / [checklists](../../handbook/checklists/)）
- 雛形にした既存フロー: [`projects/migrate-chat-spo/flows/archive-meetings/`](../migrate-chat-spo/flows/archive-meetings/)
- リポジトリ全体の作業規範: [`CLAUDE.md`](../../CLAUDE.md)
