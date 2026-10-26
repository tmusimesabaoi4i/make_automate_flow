# コネクタ・権限・DLP

使用するコネクタが標準かプレミアムか、operationId（アクションの内部ID）が実在するか、接続と権限・DLP（データ損失防止）をどう扱うかのルールです。接続参照のパッケージ内の扱いは [07](./07_export_import_package_rules.md) を参照。

## 標準かプレミアムかの確認【推奨】
- 【推奨】アクションを選ぶ前に、そのコネクタが標準かプレミアムかを確認する。プレミアムはライセンス依存で、
  環境によっては使えない・追加費用がかかる。
- 【推奨】確認方法: 各コネクタの公式リファレンス（learn.microsoft.com/connectors/…）の表記と、
  デザイナー上の「プレミアム」バッジの有無で判断する（参照日 2026-07-16）。

## 今回使用した標準コネクタ（すべてプレミアム不要）【事実】
| コネクタ | apiId | 使用アクション（operationId） | 公式リファレンス |
|---|---|---|---|
| Microsoft Teams | shared_teams | HttpRequest（Send a Microsoft Graph HTTP request） | connectors/teams/ |
| SharePoint | shared_sharepointonline | GetItems / CreateFile / GetFileItem / GetFileContentByPath / PostItem | connectors/sharepointonline/ |
| Content Conversion | shared_conversionservice | HtmlToText（パラメータキー=Content） | connectors/conversionservice/ |

- 【事実】上記3コネクタはすべて標準。汎用 HTTP コネクタ・HTTP with Microsoft Entra ID（旧 HTTP with Azure AD）・
  Azure AD アプリ登録・管理者同意は使っていない。Teams の Graph 呼び出し（HttpRequest）は標準接続だけで完結する。
- 【事実】各コネクタの詳細な使い方は [05 SharePoint/Teamsパターン](./05_sharepoint_and_teams_patterns.md) と
  [06 Word/HTML生成](./06_word_html_document_generation.md)（HtmlToText）。

## operationId の実在確認【推奨】
- 【推奨】アクションを定義に書くときは operationId が**実在する**ことを公式リファレンスで確認する。
  記憶や推測で存在しない operationId を書かない。検証時に「operationId 実在チェック」を機械走査に含める。
- 【事実】今回の定義で使用した operationId は上表の7種のみ（すべて実在確認済み）。
- 【参考・未使用】公式で実在確認したが今回未使用のもの: Teams `GetMessagesFromChannel` /
  `ListRepliesToMessage`（`$top` 最大50）、Office 365 Users `UserProfile_V2`。
  返信が50件を超える場合はページングが必要という判断の根拠になった。

## DLP・接続権限は環境依存【要実環境確認】
- 【要実環境確認】DLP ポリシーはテナント/環境ごとに異なる。標準コネクタでも、組織のDLPで
  ブロック・分離される場合がある。実環境の管理者設定に依存するため、事前に断定しない。
- 【要実環境確認】接続の作成可否・スコープ（読み取り/書き込み権限）は、フローを動かすユーザーの
  アカウント権限に依存する。SharePoint サイトへの書き込み、Teams チャネルの閲覧権限などは実環境で確認する。
- 【推奨】**管理者権限を暗黙の前提にしない**。一般ユーザー権限で動くことを基本設計とし、
  管理者操作（DLP例外追加、アプリ登録など）が必要になった時点で明示的に依頼する。

## 接続の再設定はインポート後に必要【事実】
- 【事実】インポート直後は接続が未確定。3コネクタ（Teams / SharePoint / Content Conversion）の
  接続選択と、SharePoint 系アクションのサイト・リスト/ライブラリの再選択が必要
  （手順の詳細は [07](./07_export_import_package_rules.md) と [05](./05_sharepoint_and_teams_patterns.md)）。

関連: [00 コアルール](./00_power_automate_core_rules.md) / [05 SharePoint/Teams](./05_sharepoint_and_teams_patterns.md) / [06 Word/HTML生成](./06_word_html_document_generation.md) / [07 エクスポート/インポート](./07_export_import_package_rules.md)
