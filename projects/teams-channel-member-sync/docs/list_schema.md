# SharePoint リストと列の定義

列の定義の正本は [`shared/sync_blocks.py`](../shared/sync_blocks.py) の `MEMBER_FIELDS` / `CONFIG_FIELDS`。
この文書はそれを人が読める形にしたもの。両者が食い違ったらソースが正しい。

---

## 1. 作成・変更の方針

| やること | やらないこと |
|---|---|
| 同名のリストが無ければ作る | 既存リストを削除・再作成する |
| 作成の直前に**もう一度**存在を確認する（競合で他の実行が先に作っていたらそれを使う） | リスト名だけを根拠に破壊的な操作をする |
| 不足している列**だけ**を追加する | 既存列の型・表示名・必須設定を変更する |
| 新しく作った列にだけ日本語の表示名を付ける | 既存列の表示名を変更する |
| — | 列を削除する（`deleteObject` を定義に一切含めない） |
| — | ビューを再構築する（`removeAllViewFields` / `AddViewField` を定義に一切含めない） |
| — | アイテムを削除する（DELETE 系 REST を定義に一切含めない） |

これらは静的検査 P03 / P04 / P05 が機械的に確認しており、検査が実際に発火することを
[`tests/run_check_regression_tests.py`](../tests/run_check_regression_tests.py) の R03〜R07 が証明している。

### 列の作り方（内部名を安定させる）

`createFieldAsXml` の `Options: 0` では内部名が表示名から自動生成される。日本語の表示名で作ると内部名が
`OData__x6c0f__x540d_` のような Unicode エスケープ形になり、後続の参照が壊れる（handbook §4）。

そこで **`DisplayName` = `Name` = ASCII で作成 → その列にだけ表示名を日本語へ変更** という2段階にしている。
表示名の変更は「今この実行で作成した列」に対してだけ行うため、既存列の表示名は変わらない。

表示名の変更に失敗しても同期は止まらない（列は使えるため）。`WARN_FIELD_RENAME_FAILED` として記録するだけ。

---

## 2. メンバーリスト（利用者が指定するリスト）

| 内部名 | 表示名 | 型 | Field XML の型 | 用途 |
|---|---|---|---|---|
| `Title` | タイトル（組み込み） | 1行テキスト | — | **同期キー**。組み込み列なので作成も変更もしない。**氏名は入れない** |
| `FullName` | 氏名 | 1行テキスト | `Text` (255) | 整形済みの氏名 |
| `LastName` | 姓 | 1行テキスト | `Text` (255) | 最初のスペースより前 |
| `FirstName` | 名 | 1行テキスト | `Text` (255) | 最初のスペースより後ろ（無ければ空） |
| `Email` | メールアドレス | 1行テキスト | `Text` (255) | メールアドレス。取得できなければ空 |
| `SyncKey` | 同期キー | 1行テキスト | `Text` (255) | **一意キー**。`userId`、無ければメンバーシップID |
| `TeamsUserId` | TeamsユーザーID | 1行テキスト | `Text` (255) | Microsoft Entra のオブジェクトID |
| `MembershipId` | メンバーシップID | 1行テキスト | `Text` (255) | チャネル内のメンバーシップID |
| `TeamId` | チームID | 1行テキスト | `Text` (255) | |
| `ChannelId` | チャネルID | 1行テキスト | `Text` (255) | 同期対象の判別に使う |
| `MemberTenantId` | メンバーテナントID | 1行テキスト | `Text` (255) | 外部ユーザー判定に使う |
| `MemberRoles` | ロール | 1行テキスト | `Text` (255) | `owner` / `guest` など。複数はカンマ区切り |
| `MembershipKind` | メンバー種別 | 1行テキスト | `Text` (255) | `direct` / `indirect` |
| `IsExternalUser` | 外部ユーザー | はい/いいえ | `Boolean` | |
| `MemberStatus` | 同期状態 | 1行テキスト | `Text` (255) | `在籍` / `離脱` |
| `IsActive` | 有効 | はい/いいえ | `Boolean` | |
| `LastSyncedAt` | 最終同期更新日時 | 日付と時刻 | `DateTime` | 作成・更新が実際に起きた時刻 |
| `SyncSource` | 同期元 | 1行テキスト | `Text` (255) | 固定値 `TeamsChannelMemberSync` |

要件が求める最小項目（氏名・メールアドレス）は `FullName` と `Email`。姓・名は `LastName` / `FirstName`。
それ以外は重複防止・同期管理・監査のために持っている。

### なぜ `Title` に氏名を入れないか

SharePoint の組み込み `Title` 列は、既定で必須かつ「リンク（アイテムの編集メニュー付き）」として表示される特別な列。
ここに氏名を入れると、氏名が「タイトル」という無関係な見出しで表示され、専用列との二重管理にもなる。
一方 `Title` を空にするには組み込み列の必須設定を変更する必要があり、それは**既存リストを壊さない**という
方針に反する。そこで `Title` には人が読む値ではなく**同期キー**（内部識別子）を入れ、
人が読む値はすべて専用列に持たせている。

### 氏名の整形（`FullName` / `LastName` / `FirstName` の作り方）

Teams の表示名には外字の代替表記（`▲`〜`▼`）や英字読みの併記が混ざる。

| 入力 | `FullName` | `LastName` | `FirstName` |
|---|---|---|---|
| `▲高▼元 優子(TAKAMOTO Yuko)` | `高元 優子` | `高元` | `優子` |
| `佐藤 花子（SATO Hanako）` | `佐藤 花子` | `佐藤` | `花子` |
| `山田　太郎`（全角スペース） | `山田 太郎` | `山田` | `太郎` |
| `斎藤 ▲徳▼子` | `斎藤 徳子` | `斎藤` | `徳子` |
| `山田太郎`（スペースなし） | `山田太郎` | `山田太郎` | （空） |
| `山田 太郎 二世` | `山田 太郎 二世` | `山田` | `太郎 二世` |
| （空） | （空） | （空） | （空） |

処理順:

1. `replace(replace(raw, '▲', ''), '▼', '')` — 外字マーカーを除去
2. `first(split(first(split(x, '(')), '（'))` — 括弧（半角・全角）以降を落とす
3. `trim(replace(x, '　', ' '))` — 全角スペースを半角に寄せて trim → **氏名**
4. `first(split(氏名, ' '))` → **姓**
5. 最初のスペースの次の位置から末尾まで → **名**
   開始位置は「スペースがあれば 姓の長さ+1、無ければ全長」を先に Compose で確定させ、
   番兵付きの `substring` に渡す（空文字でも失敗しない。[known_limitations.md](known_limitations.md) C-1）

全ケースは [`tests/run_sync_logic_tests.py`](../tests/run_sync_logic_tests.py) の D01〜D10 で、
生成済み `definition.json` の式をそのまま評価して確認している。

### 既定ビューへの表示

列を作っただけでは SharePoint の既定ビューに出ない（`Title` しか見えない）。
そこで列の整備後に、**不足している列だけを既定ビューへ追加**する。

```
GET  _api/web/lists(guid'{listId}')/views?$select=Id,Title,DefaultView&$top=100
GET  _api/web/lists(guid'{listId}')/views(guid'{viewId}')/ViewFields
POST _api/web/lists(guid'{listId}')/views(guid'{viewId}')/viewfields/AddViewField('{internalName}')
```

- 既定ビューは表示名（「すべてのアイテム」等）ではなく **`DefaultView` プロパティ**で特定する。
- `ViewFields` の応答は `{"Items": [...]}` 形（内部名の配列）。ここに無い列だけを追加する。
- **`removeAllViewFields`（ビューの作り直し）は定義に一切含めない。** 追加しかしないので、
  利用者が並べ替えた既存ビューを壊さない。静的検査 P18 が0件を機械確認する。
- ビューの取得に失敗した場合は追加対象が0件になり、ループごとスキップされる（保険）。

### 手で作る場合

自動作成に任せるのが確実だが、手で作る場合は上表の**内部名**が一致するように作る。
SharePoint の画面から日本語名で列を作ると内部名がエスケープされてしまうため、次のようにする。

1. まず**表示名を ASCII**（例 `Email`）にして列を作る → 内部名が `Email` になる
2. 作成後に列の設定から表示名を日本語（例 `メールアドレス`）に変える → 内部名は変わらない

`Title` 列は既定のままでよい（氏名がここに入る）。

### 大量アイテムを扱う場合

`SyncKey` と `ChannelId` にインデックスを付けると、SharePoint 側の検索が速くなる。
フローは `$filter` を使わず全件ページングするためインデックスが無くても動作するが、
アイテム総数が増えると毎回の取得件数が増える（[known_limitations.md](known_limitations.md) B-1）。
インデックスはリスト設定から手動で付ける（`createFieldAsXml` の `Indexed` 属性は本リポジトリで未実証のため実装していない）。

---

## 3. 設定リスト（名前は「Teamsチャネルメンバー同期設定」固定）

**手動フローと日次フローは、必ず同じ設定リストを参照する。** そのために次を機械的に固定している（静的検査 P17）。

| 一致させるもの | 固定方法 |
|---|---|
| リスト名 | 共有定数 `sync_blocks.CONFIG_LIST_TITLE` から両フローを生成する。検査が literal の一致を確認する |
| サイト | 設定リストへの REST の `dataset` は両フローとも `@variables('varConfigSiteUrl')` に固定。ほかの変数を使うと検査が落ちる |
| リストの特定 | 名前で引くのは存在確認の1回だけ。読み書きは `lists(guid'{varConfigListId}')` |

`varConfigSiteUrl` に入る値だけが2フローで独立に決まる。手動フローは実行時に決められる（入力または同期先サイト）が、日次フローは Recurrence トリガーで入力を持てないため、`Compose_AdminSiteUrl` へ1回設定する必要がある。
手動フローは使ったサイトを実行結果の `adminSiteUrl` と `nextAction` に出すので、その値をそのまま貼り付ければ一致する。

> **複数チャネルを扱う場合の注意**: 同期先サイトがチャネルごとに違うと、既定（管理サイト未指定）ではサイトごとに別々の設定リストができる。日次フローは `Compose_AdminSiteUrl` が指す1か所しか見ないため、2つ目以降のチャネルでは手動フローの「設定リストを置くサイトのURL」に**1つ目と同じサイト**を指定する。


| 内部名 | 表示名 | 型 | 用途 |
|---|---|---|---|
| `Title` | タイトル（組み込み） | 1行テキスト | 設定名。チャネルの表示名が入る |
| `ConfigKey` | 設定キー | 1行テキスト | `<チームID>_<チャネルID>`。設定の一意キー |
| `TeamsChannelUrl` | TeamsチャネルURL | 複数行テキスト | 入力された元のURL |
| `TeamId` | チームID | 1行テキスト | |
| `ChannelId` | チャネルID | 1行テキスト | |
| `TenantId` | テナントID | 1行テキスト | 空のことがある（URLに無い場合） |
| `SiteUrl` | SharePointサイトURL | 複数行テキスト | 正規化済みのサイトルート |
| `ListTitle` | SharePointリスト名 | 1行テキスト | |
| `ChannelType` | チャネル種別 | 1行テキスト | `standard` / `private` / `shared` |
| `MemberSource` | メンバー取得方式 | 1行テキスト | `connector` / `graph` |
| `IsEnabled` | 有効 | はい/いいえ | **日次実行の対象にするか。1設定ずつ個別に制御できる** |
| `ConfigVersion` | 設定バージョン | 数値 | 更新のたびに1つ進む |
| `LastTestSucceededAt` | 最終テスト成功日時 | 日付と時刻 | フローA が成功した時刻 |
| `LastSyncAt` | 最終同期日時 | 日付と時刻 | 日次実行が走った時刻 |
| `LastSyncResult` | 最終同期結果 | 複数行テキスト | 件数のJSON。**氏名・メールは含まない** |
| `UpdatedAt` | 設定更新日時 | 日付と時刻 | 設定を書き換えた時刻 |

`複数行テキスト`（`Note` 型）は OData の `$filter` に使えないため、絞り込みに使う `ConfigKey` は1行テキストにしている。

---

## 4. 使用している REST

すべて SharePoint コネクタの「SharePoint に HTTP 要求を送信します」（`operationId: HttpRequest`）で呼ぶ。
`dataset`（サイトのアドレス）には式（`@variables('varSiteUrl')` / `@variables('varConfigSiteUrl')`）を渡す。
これは実環境で実証済み（handbook/knowledge/sharepoint_rest_list_provisioning.md §11、2026-07-24）。

`PostItem`（項目の作成）を使わない理由は、必須の動的ボディ `item` を持つため `dataset` / `table` を式にすると
保存時に `OpenApiOperationParameterValidationFailed` になるから（handbook/knowledge/error_catalog.md #6）。

| 目的 | メソッド | URI | ヘッダー |
|---|---|---|---|
| リスト一覧（存在確認） | GET | `_api/web/lists?$select=Id,Title,Hidden,BaseTemplate,RootFolder/ServerRelativeUrl&$expand=RootFolder&$top=5000` | `odata=nometadata` |
| リスト作成 | POST | `_api/web/lists` | `odata=verbose` |
| リスト情報（型名の取得） | GET | `_api/web/lists(guid'{listId}')?$select=Id,Title,ListItemEntityTypeFullName,RootFolder/ServerRelativeUrl&$expand=RootFolder` | `odata=nometadata` |
| 列一覧 | GET | `_api/web/lists(guid'{listId}')/fields?$select=Id,Title,InternalName,TypeAsString&$top=5000` | `odata=nometadata` |
| 列作成 | POST | `_api/web/lists(guid'{listId}')/fields/createFieldAsXml` | `odata=verbose` |
| 列の表示名変更 | POST | `_api/web/lists(guid'{listId}')/fields/getbyinternalnameortitle('{internalName}')` | `odata=nometadata` ＋ `IF-MATCH: *` ＋ `X-HTTP-Method: MERGE` |
| アイテム取得 | GET | `_api/web/lists(guid'{listId}')/items?$select=<列を列挙>&$top=1000` | `odata=nometadata` |
| アイテム作成 | POST | `_api/web/lists(guid'{listId}')/items` | `odata=verbose` |
| アイテム更新 | POST | `_api/web/lists(guid'{listId}')/items({itemId})` | `odata=verbose` ＋ `IF-MATCH: *` ＋ `X-HTTP-Method: MERGE` |

**書き込み系のURIは必ずリストIDで対象を指定している。** `GetByTitle('{listName}')` は1件も使っていない（名前の取り違えで既存リストを壊さないため。静的検査 P04）。

`$expand=RootFolder` には `$select` に `RootFolder/ServerRelativeUrl` の投影を必ず書いている。
コレクション列挙で投影を落とすと、アクセス権の無いシステムリストを実体化しようとして 403 になる
（handbook/knowledge/sharepoint_rest_list_provisioning.md §15 の実発生事例。共通リンター L04 が機械検出する）。

### ボディの作り方

ボディは必ず Compose でオブジェクトを組み立て、`@string(outputs('Compose_...'))` を渡す。
文字列連結で JSON を組むと、値に `"` や改行や `\` が含まれたときに壊れる（handbook §14）。静的検査 P07 が形式を確認する。

`__metadata.type` には、実行時に取得した `ListItemEntityTypeFullName`（例 `SP.Data.TeamsMembersListItem`）を入れる。
テナントによって `__metadata` の型指定を要求される差異を、推測ではなく取得で回避している（handbook §16）。

### ページングの受け方

SharePoint REST の継続リンクは、受理ヘッダーやテナントによって次の3つの形で返りうる。

- `odata.nextLink`（OData v3 形）
- `@odata.nextLink`（OData v4 形）
- `d.__next`（verbose 形）

3形すべてを `coalesce` で受け、返ってきた絶対URLは `_api/` 以降を切り出してサイト相対に直してから次の要求に使う。
Graph 側の `@odata.nextLink` は完全URLをそのまま使う（handbook/rules/05）。

---
関連: [../README.md](../README.md) / [design_decisions.md](design_decisions.md) / [../../../handbook/knowledge/sharepoint_rest_list_provisioning.md](../../../handbook/knowledge/sharepoint_rest_list_provisioning.md)
