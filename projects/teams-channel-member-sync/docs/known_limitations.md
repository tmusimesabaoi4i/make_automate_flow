# 既知の制限と要実環境確認事項

**この文書の約束**: 実環境で確認できていないことを「対応済み」「テスト済み」とは書かない。
オフラインで確認できたことと、実機でしか確認できないことを分けて書く。

作成者は Power Automate 環境にアクセスできないため、**実環境での動作確認は一件も行っていない**。
下記の「要実環境確認」は、利用者が実機で確かめる必要がある項目である。

---

## A. 要実環境確認（未検証）

### A-1. `ListMembers` の `body` 配下のキー名 ★最優先

| 項目 | 状況 |
|---|---|
| `threadType` の値 `"channel"` | **確定**（コネクタ swagger 現物の enum。docs/design_decisions.md §4.1） |
| 返り値のプロパティ名 | **確定**（公式ドキュメントの Definitions と swagger が一致） |
| `body/recipient/groupId` / `body/recipient/channelId` | **要実環境確認** |

`ListMembers` を `threadType=channel` で使った実エクスポート定義は公開例が存在しない。兄弟アクション `GetMessageDetails`（同じ threadType 駆動の dynamic-body パターン）の実エクスポート定義と、Microsoft 公式リポジトリのテストフィクスチャからの推論である。

**確かめ方**: フローA をインポートして開き、`Teams_List_Channel_Members` アクションがデザイナー上でエラーにならないこと、保存できることを確認する。

**外れていた場合の症状**: 保存時に `OpenApiOperationParameterValidationFailed`（`The API operation 'ListMembers' is missing required property 'body'` 等）。

**直し方**: `shared/sync_blocks.py` の次の2定数を実機のコードビューで確認した値に直して再生成する。1箇所の修正で両フローに反映される。

```python
LISTMEMBERS_KEY_TEAM = "body/recipient/groupId"
LISTMEMBERS_KEY_CHANNEL = "body/recipient/channelId"
```

もしくは `MEMBER_SOURCE_MODE = "graph_only"` にすれば `ListMembers` を定義から外し、Graph 経路だけで同期できる。詳細は [troubleshooting.md](troubleshooting.md)。

### A-2. Teams コネクタ経由で Graph のメンバーAPIが通るか

Teams コネクタの `HttpRequest`（Send a Microsoft Graph HTTP request）の公式説明にある許可セグメントは次のとおり。

> These segments are supported: 1st segment: /teams, /me, /users 2nd segment: channels, chats, installedApps, messages, pinnedMessages, onlineMeetings

`GET /teams/{teamId}/channels/{channelId}/members` は 1st=`/teams`・2nd=`channels` なので**形式上は適合**する。ただし:

- 3rd セグメント以降（`members` / `allMembers`）に対する制限は公式に記述が無い。
- **このコネクタが保持している Graph のスコープを公式に記載したページが存在しない。** `ChannelMember.Read.All` は委任版でも管理者同意が必須（[アクセス許可リファレンス](https://learn.microsoft.com/en-us/graph/permissions-reference)）なので、コネクタが事前同意を持っていなければ 403 になりうる。
- 本リポジトリで Teams コネクタ経由の Graph 呼び出しに成功した実績は `/messages` 系のみ（2026-07-24）。

**確かめ方**: フローA を実行し、`Compose_Result_Summary` の `memberSource` を見る。`connector` なら `ListMembers` で取れており、`graph` ならフォールバックが働いている。両方失敗した場合は `Scope_06_GetMembers` が失敗する。

### A-3. `GET /users/{userId}` によるメール補完

メールが空のメンバーについて `GET https://graph.microsoft.com/v1.0/users/{userId}?$select=mail,userPrincipalName` を引く。1st セグメント `/users` は許可されているが、2nd セグメントがユーザーIDになるため許可対象に該当するかは公式に不明。

失敗しても同期は止まらない設計（`runAfter` に `Failed` を含め、`emailLookupFailures` を数えるだけ）。取得できなければメールは空のまま残る。**推測でメールアドレスを生成することはしない。**

### A-4. `ListMembers` の件数上限

`ListMembers` には `x-ms-pageable` が無く、Power Automate のページネーション設定が使えない。`$top` パラメータも持たない。**大規模チャネルで何件まで返るかは公式に記述が無い。**

対策として Graph 経路（`@odata.nextLink` を Do until で追跡）を併設してある。取得件数が実際のメンバー数より少ないと疑われる場合は `MEMBER_SOURCE_MODE = "graph_only"` に切り替える。

### A-5. `/allMembers` のページング

`/allMembers` は `$top` をサポートせず、既定ページサイズの公式記載も無い（`/members` は既定100・最大999と明記されているのに対して）。本フローは返ってきた `@odata.nextLink` を追跡するが、そもそも nextLink が返るかどうかを確認できていない。

### A-6. 共有チャネル・プライベートチャネルでの動作

| チャネル種別 | 実装状況 | 検証状況 |
|---|---|---|
| 標準チャネル | 実装済み | **未検証** |
| プライベートチャネル | 実装済み（種別による分岐なし） | **未検証** |
| 共有チャネル（直接メンバー） | 実装済み | **未検証** |
| 共有チャネル（間接メンバー） | `/allMembers` で補完する実装 | **未検証** |

共有チャネルでは**ホストチーム（共有元のチーム）のID**を指定する必要がある（公式）。「チャネルへのリンクを取得」で得られる `groupId` がホストチームを指すかどうかは、共有先から取得した場合に異なる可能性がある。

### A-7. `createFieldAsXml` による列作成

型ごとの Field XML は handbook の実証済みパターン（Text / Note / Number）に加え、本案件で **Boolean 型と DateTime 型を新たに使っている**。

```xml
<Field Type="Boolean" DisplayName="IsActive" Name="IsActive" StaticName="IsActive" Required="FALSE" />
<Field Type="DateTime" DisplayName="LastSyncedAt" Name="LastSyncedAt" StaticName="LastSyncedAt" Required="FALSE" Format="DateTime" />
```

この2型での列作成は**未検証**。失敗した場合は該当列の作成だけが失敗し、`varItemErrors` に `ERR_FIELD_CREATE_FAILED` が記録される（同期全体は止まらないが、その列への書き込みは失敗する）。

### A-8. 認証方式（Embedded）

`@parameters('$authentication')` ＋ `source: "Embedded"` を採用した。Microsoft の実エクスポート3本がこの形であることが根拠だが、**本リポジトリが生成したパッケージをこの形でインポートした実績は無い**（既存フローはすべて Invoker 形式）。

外れていた場合は `shared/sync_blocks.py` の `AUTH_MODE = "invoker"` に変えて再生成する。ただし Invoker 形式は定期実行フローで成立しない可能性が高い（design_decisions.md §3）。

### A-9. SharePoint 継続リンクのプロパティ名

`odata=nometadata` で返る継続リンクが `odata.nextLink` か `@odata.nextLink` か `d.__next` かはテナント・受理ヘッダーで変わりうる。3形すべてを `coalesce` で受けているが、**どれが実際に返るかは未確認**。3形とも来なければ1ページ目（最大1,000件）で打ち切られる。

---

## B. 設計上の制限（仕様として受け入れているもの）

### B-1. 5,000件のビューしきい値

既存アイテムは `$filter` を使わず全件ページングで取得するため、しきい値エラーは起きない。ただし:

- **同期先リストのアイテム総数が多いほど、毎回の実行で取得する件数が増える**。同期先リストは本用途に専用化することを推奨する。
- 複数チャネルを1つのリストへ同期する場合、全チャネル分のアイテムを毎回取得する。

`SyncKey` と `ChannelId` にインデックスを付ける実装は含めていない（`createFieldAsXml` の `Indexed` 属性が本リポジトリで未実証のため）。必要なら SharePoint のリスト設定から手動で付ける。

### B-2. `ListTeamMembers` は使っていない

要件どおり `ListMembers`（チャネルのメンバー）と `ListTeamMembers`（チーム全体のメンバー）を混同していない。本フローが返すのは**チャネルのメンバー**であり、チーム全体のメンバー一覧ではない。標準チャネルではチームのメンバー全員がチャネルにアクセスできるため、期待と食い違う可能性がある。

【要実環境確認】標準チャネルに対して `ListMembers` が「チームのメンバー全員」を返すのか「チャネルに明示的に追加された人だけ」を返すのかは、公式の記述からは判断できない。実機で件数を確認すること。

### B-3. テナントIDが取得できない場合、外部ユーザー判定を行わない

TeamsチャネルURLに `tenantId` が含まれていない場合、`varTenantId` は空になる。このとき全メンバーの `IsExternalUser` は `false` のままになる（「同一テナントである」と判定しているのではなく、「判定していない」）。誤って全員を外部扱いすることを避けるための仕様。

### B-4. 変更がなければ `最終同期更新日時` も更新されない

要件§10「変更がない場合は不要な更新を行わない」を優先した結果、`LastSyncedAt` は**作成・更新が実際に起きたとき**にだけ更新される。「毎日この人を確認した」という記録ではない。実行ごとの確認記録は設定リストの `最終同期日時` / `最終同期結果` を見る。

### B-5. 想定内エラーでは実行が「成功」で終わる

設定不備・アクセス不可などの想定内のエラーは、`failedStage` と `errorCode` に理由を記録したうえで実行自体は成功として終わる。実行履歴の色だけを見ると気付けない。監視するなら `Compose_Result_Summary` の `status` / `failedStage`、または設定リストの `最終同期結果` を見る。

Power Automate の `Terminate` アクション（実行を失敗として終わらせる）は本リポジトリで実績が無いため採用していない。

### B-6. 設定リストの名前は固定

設定リストの表示名は「Teamsチャネルメンバー同期設定」で固定（`shared/sync_blocks.py` の `CONFIG_LIST_TITLE`）。管理サイトにこの名前の別用途リストがあると衝突する。変更する場合は定数を直して両フローを再生成する。

### B-7. 同期処理の修正は両フローの再生成が必要

子フローを使えないため、同期処理を直したら**両方のフローを再生成して両方を配り直す**必要がある。片方だけ更新すると挙動が食い違う。

### B-8. 組み込みの `Title` 列の表示名は変更しない

既存リストを壊さないため、組み込み列（`Title`）には一切手を触れない。したがってメンバーリストの列見出しは「タイトル」のままで、中身は**同期キー**（内部識別子）になる。氏名は `FullName` / `LastName` / `FirstName` 列に入る。`Title` を非表示にしたい場合は SharePoint のビュー設定から手動で外す（フローは列を追加するだけで、外しはしない）。

### B-10. 姓名の分割は「最初のスペース」を境にする

Teams の表示名に姓名の区切りが無い（`山田太郎`）場合、姓＝全体・名＝空になる。区切りが複数ある（`山田 太郎 二世`）場合は、最初のスペースより後ろがすべて名になる。表示名の書式はテナントの設定に依存するため、**分割は書式の約束に依存する**。分割結果が期待と違う場合は `FullName` を正とし、`LastName` / `FirstName` は参考値として扱う。

### B-11. 既定ビューへの列追加は「追加のみ」

既存ビューを壊さないため `AddViewField`（追加）しか行わない。したがって:

- すでに利用者が並べ替えた既定ビューがある場合、追加した列は**末尾**に並ぶ。順序を変えたい場合は SharePoint のビュー設定から手動で行う。
- 既定ビューから列を手動で外した場合、次回実行で**また追加される**（フローは「不足している列を足す」ため）。恒久的に隠したい場合は、既定ビューではなく別のビューを作ってそちらを使う。
- 既定ビューが特定できなかった場合（`DefaultView` が真のビューが無い等）は、列の追加をまるごとスキップし `WARN_VIEW_FIELD_ADD_FAILED` を記録する。同期そのものは止まらない。

### B-9. リスト作成直後の実行について

リストを新規作成した回の実行では、列の作成が同じ実行の中で行われる。SharePoint 側の反映が間に合わずアイテム作成が失敗する可能性は否定できない（**未検証**）。その場合はフローA をもう一度実行すれば、2回目は既存リスト・既存列として扱われる。

---

## C. オフラインで確認できたこと

実機を使わずに検証した内容。詳細は [../tests/test_cases.md](../tests/test_cases.md)。

| 検証 | 件数 | 結果 |
|---|---|---|
| URL解析・正規化（生成済み definition.json の式をそのまま評価） | 29 | 全件合格 |
| 同期ロジック（差分判定・離脱ガード・正規化・氏名整形・ページング） | 62 | 全件合格 |
| 静的検査の回帰（わざと壊して検査の発火を確認） | 29 | 全件合格 |
| 共通リンター `tools/wdl_lint.py`（L01〜L13 / M01・M02） | — | 指摘0件 |
| 本案件固有の静的検査（P01〜P15） | — | エラー0・警告0 |
| ZIP再展開＋SHA-256 バイト一致 | — | 両フローとも一致 |

**これらは「定義が壊れていないこと」と「式の論理が正しいこと」を示すだけで、Power Automate 実機での保存可否・インポート可否・実行結果を保証しない。**

### C-1. 実環境で発覚し修正した事象（2026-08-04）

`substring` の開始位置は「文字列長より小さい」必要があり、**空文字には `substring('', 0, 0)` すら
適用できない**。管理サイトURLが空のまま実行したときに `Compose_Admin_Cut` で実行時エラーになった。

このとき空文字入力のテストケース（A01・S11）は**存在していたのに合格していた**。
`tools/wdl_eval.py` の `substring` が `start == length(s)` を許容しており、**実機より緩かった**ため。

対処:
1. 評価器を実機の文言どおり `start < length(s)` に厳密化した（リポジトリ共通ツール）
2. すべての `substring` を番兵付き（`substring(concat(S, '#'), …)`）に変更した
3. 静的検査 P16（番兵の無い `substring` を検出）と回帰テスト R23 を追加した
4. 同型パターンをリポジトリ全体で検索し、`sync-shared-mailbox-to-sharepoint-list` の
   両フローにあった同じ形も修正した

**教訓**: オフライン評価器が実機より緩いと、テストは「動くこと」を証明しない。
詳細は `handbook/knowledge/lessons_learned.md` §36。

---
関連: [../README.md](../README.md) / [design_decisions.md](design_decisions.md) / [troubleshooting.md](troubleshooting.md)
