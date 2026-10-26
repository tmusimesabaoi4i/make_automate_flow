# teams-channel-member-sync — Teamsチャネルメンバーの SharePoint リスト同期

Teams チャネルのメンバー（氏名・メールアドレス）を毎日 SharePoint リストへ同期する Power Automate ソリューション。
初回だけ手動で「TeamsチャネルURL / SharePointサイトURL / リスト名」を入力し、テスト同期に成功した設定だけを永続保存して、以後は毎日 07:00（日本時間）に自動同期する。

## 1. 目的

- Teams チャネルの現在のメンバーを、指定した SharePoint リストへ一覧化する。
- 毎日実行しても重複が増えず、変更だけが反映される（冪等）。
- チャネルから外れた人は**論理的に無効化**する（行は消さない）。
- Teams 側の取得に失敗したときに SharePoint 側を空にしてしまう事故を、定義の構造として起こせないようにする。

## 2. 全体構成

```
projects/teams-channel-member-sync/
├─ README.md                     このファイル
├─ docs/                         設計判断・仕様・手順・制限
├─ tests/                        オフラインテスト（3本）と結果
├─ shared/                       ★両フローの唯一の定義元
│   ├─ sync_blocks.py            同期処理のアクション生成
│   ├─ flow_checks.py            本案件固有の静的検査（P01〜P15）
│   └─ extract_check_lib.py      ZIP再展開検査
└─ flows/
    ├─ setup-and-test-sync/      フローA（手動 Button）
    └─ daily-member-sync/        フローB（Recurrence 07:00 JST）
```

各フローは `spec/`（設計）・`source/`（唯一の編集元）・`validation/`（検証結果）・`release/`（配布ZIP）を持つ。

**同期処理は1箇所にしか書かれていない。** Power Automate の「子フローを実行する」は Dataverse ソリューションを必須とし（[公式](https://learn.microsoft.com/en-us/power-automate/create-child-flows)）、本リポジトリが採用しているレガシーパッケージ形式では使えない。そこで実行時ではなく**生成時**に共通化し、`shared/sync_blocks.py` が両フローへまったく同じアクション群を埋め込む。保守が発生する場所（Python ソース）での重複はゼロ。

## 3. 各フローの役割

| フロー | 論理名 | トリガー | 役割 |
|---|---|---|---|
| フローA | `TeamsChannelMemberSync_Setup` | 手動（ボタン） | 入力検証 → URL解析 → アクセス確認 → **テスト同期** → 成功時のみ設定を保存 |
| フローB | `TeamsChannelMemberSync_Daily` | Recurrence（毎日 07:00 JST） | 保存済みの有効な設定を読み、設定ごとに同期して結果を記録 |

フローA の実行順（要件どおり）:
1. TeamsチャネルURL・SharePointサイトURL・リスト名を受け取る
2. 形式を検証する（ホストが Teams / SharePoint であることを含む）
3. Teams URL から チームID・チャネルID・テナントID を取り出す
4. SharePoint サイトURLをサイトルートへ正規化する
5. Teams チャネルへアクセスできるか確認する（チャネル種別もここで判定）
6. SharePoint サイトと対象リストを確認する（無ければ作成・不足列だけ追加）
7. メンバーを実際に取得する
8. SharePoint リストへ同期する
9. **すべて成功した場合に限り**設定を保存する
10. 結果を `Compose_Result_Summary` に出力する

## 4. 永続設定の保存方式

**管理サイト上の SharePoint リスト「Teamsチャネルメンバー同期設定」** に、1設定＝1アイテムで保存する。

比較した4方式と選定理由は [docs/design_decisions.md](docs/design_decisions.md) に記載。要点だけ:

- **環境変数は使えない。** 公式に「ソリューションインポート以外で値を変えた場合、フローは保存されるかオフ→オンされるまで**以前の値を使い続ける**」「反映に**最大1時間**かかる」と明記されている（[1](https://learn.microsoft.com/en-us/power-apps/maker/data-platform/environmentvariables-power-automate) / [2](https://learn.microsoft.com/en-us/power-apps/maker/data-platform/environmentvariables)）。手動実行の直後に定期実行が新しい値を読める必要がある本要件では成立しない。
- **Dataverse テーブルは追加ライセンスが必要。** Dataverse コネクタは Power Automate で Premium 分類（[公式](https://learn.microsoft.com/en-us/connectors/commondataserviceforapps/)）。
- **循環依存の解消**: 「対象サイトの中に設定を置くと、定期フローが最初にそのサイトを知らない」という循環は、**管理サイトのURLだけをインポート後に1回設定する**ことで断ち切っている（各フローの `Compose_AdminSiteUrl` 1箇所）。ソリューションの環境変数が担う「デプロイ時に値を与える」役割を、レガシー形式で最小コストに再現したもの。ZIP にはテナント固有の値を一切含めない（検証スクリプトが空文字であることを機械確認する）。

保存する項目: TeamsチャネルURL / チームID / チャネルID / テナントID / SharePointサイトURL / リスト名 / チャネル種別 / メンバー取得方式 / 有効・無効 / 設定バージョン / 最終テスト成功日時 / 最終同期日時 / 最終同期結果 / 設定更新日時。

**複数チャネルに対応**している。設定リストの行を増やせば、日次フローは有効な設定すべてを順に処理する。1行ずつ「有効」列で個別に有効化・無効化できる。

**手動フローを再実行したときの挙動**: `設定キー`（`<チームID>_<チャネルID>`）で既存を探し、**0件→作成 / 1件→更新（設定バージョンを1つ進める）/ 2件以上→書き込まず記録**。同じチャネルなら上書き更新、別チャネルなら新しい行が増える。トリガー入力の「他のチャネル設定を無効化する」を「はい」にすると、テスト成功後にほかの設定を無効化して置き換える（削除はしない）。
**テストが失敗した場合は設定リストに一切書き込まない**ので、最後に正常動作していた設定はそのまま残る。

## 5. 採用した命名規則

| 対象 | 規則 | 例 |
|---|---|---|
| 案件フォルダ | ケバブケース | `teams-channel-member-sync` |
| フローフォルダ | ケバブケース | `setup-and-test-sync` / `daily-member-sync` |
| フロー論理名（ZIP名） | `TeamsChannelMemberSync_<役割>` | `TeamsChannelMemberSync_Setup` |
| Scope | `Scope_<連番>_<用途>` | `Scope_09_SyncItems` |
| その他アクション | `<種別>_<用途>` | `Compose_Member_Email_Raw` |
| 種別接頭辞 | `Scope_ Compose_ Initialize_ Set_ Append_ Increment_ Foreach_ Condition_ Do_Until_ Filter_ Get_ Create_ Update_ Teams_` | |
| 変数 | `var` + PascalCase | `varMembersFetchComplete` |
| SharePoint 列内部名 | ASCII PascalCase（表示名は日本語） | `TeamsUserId` ／「TeamsユーザーID」 |

アクション名は英数字とアンダースコアのみ。フロー全体で一意（Power Automate の要求）。
Scope に連番を振ってあるので、実行履歴の Scope 名だけで「どの段階で失敗したか」が分かる。

## 6. 必要な接続

| コネクタ | 種別 | 用途 |
|---|---|---|
| Microsoft Teams（`shared_teams`） | 標準 | チャネル情報の取得、メンバー一覧の取得、Graph 呼び出し |
| SharePoint（`shared_sharepointonline`） | 標準 | 設定リストとメンバーリストの読み書き（REST） |

接続情報はフロー定義に埋め込まない。`connectionReferences` には匿名の GUID だけが入っており、インポート時に選んだ実接続へ再マッピングされる（2026-07-24 に実環境で確認済みの方式）。

## 7. 必要な権限

- 接続したアカウントが **対象 Teams チャネルのメンバー**であること（共有チャネルの場合はホストチーム側）。
- 接続したアカウントが **管理サイトと同期先サイトの両方**に対して、リストの作成・列の追加・アイテムの作成／更新ができること（サイトの「メンバー（編集）」以上）。
- Microsoft Graph の `ChannelMember.Read.All` 相当が必要になるかは**要実環境確認**（[docs/known_limitations.md](docs/known_limitations.md) §2）。

## 8. 必要なライセンス

**Power Automate の標準ライセンス（Microsoft 365 に含まれるもの）で動く想定**。使用コネクタは Teams と SharePoint の2つで、どちらも標準（Standard）分類。Premium コネクタ・Dataverse・カスタムコネクタは使っていない。

## 9. インポート方法

詳細は [docs/installation.md](docs/installation.md)。概略:

1. Power Automate で **マイフロー → インポート → パッケージのインポート（レガシー）** を開く
2. `flows/setup-and-test-sync/release/TeamsChannelMemberSync_Setup_<日時>.zip` を選ぶ
3. 「関連リソース」で Teams と SharePoint の接続を選ぶ（無ければ作成する）
4. インポートを実行する
5. 同じ手順で `flows/daily-member-sync/release/TeamsChannelMemberSync_Daily_<日時>.zip` を取り込む

## 10. 初回設定方法

**フローA はインポート直後にそのまま実行できる。事前の設定作業は要らない。**

1. フローA を手動実行し、入力する。
   - TeamsチャネルURL: Teams のチャネルで「チャネルへのリンクを取得」して得られるURL
   - SharePointサイトURL: 同期先サイトのURL（一覧画面や設定画面のURLでもサイトルートへ自動正規化される）
   - SharePointリスト名: メンバーを書き込むリストの表示名（無ければ作成される）
   - 設定リストを置くサイトのURL（任意）: **空でよい。** 空なら同期先サイトに設定リストを作る
2. 実行履歴で `Compose_Result_Summary` を開き、`success` と `configSaved` が `true` であることを確認する。
3. 同じ結果の **`nextAction`** に、日次フローへ貼り付ける値がそのまま出ている。
   フローB を開き、`Compose_AdminSiteUrl` にその値（＝ `adminSiteUrl` の値）を貼り付けて保存する。
4. フローB を**オン**にする。

> 日次フローだけは、設定リストの場所を実行時に知る手段が無いため、この1箇所の貼り付けが必要になる
> （Recurrence トリガーには入力が無く、レガシーパッケージには環境変数が無いため）。
> フローA が貼り付ける値を提示するので、探す必要はない。

## 11. 毎日の実行時刻

**毎日 07:00（Tokyo Standard Time）**。業務開始前に前日までの異動を反映させるため。

```json
"recurrence": {
  "frequency": "Day", "interval": 1,
  "schedule": { "hours": [7], "minutes": [0] },
  "timeZone": "Tokyo Standard Time",
  "startTime": "2026-08-05T07:00:00"
}
```

`timeZone` を指定するときは `startTime` に `Z` を付けない（付けるとUTC扱いになり `timeZone` が無視される。[公式](https://learn.microsoft.com/en-us/azure/connectors/connectors-native-recurrence)）。UTCオフセットを直接書かないことで、意図しない日に実行される事故を防いでいる。
実行時刻は公式に**最大1分程度ずれる**ことがある。

時刻を変えるときは `flows/daily-member-sync/source/build_daily_flow.py` の `SCHEDULE_HOUR` / `SCHEDULE_MINUTE` を直して再生成する（デザイナー上で直接変えると、次回の再生成で戻る）。

## 12. SharePoint リストの必要列

フローが自動で作成・追加する。**既存のリスト・既存の列は一切変更しない**（不足している列だけを追加する）。
手で作る場合の定義は [docs/list_schema.md](docs/list_schema.md) を参照。

### メンバーリスト（利用者が指定するリスト）

| 内部名 | 表示名 | 型 | 用途 |
|---|---|---|---|
| `Title` | タイトル（組み込み列） | 1行テキスト | **同期キー**（内部識別子）。**氏名は入れない** |
| `FullName` | 氏名 | 1行テキスト | 整形済みの氏名 |
| `LastName` | 姓 | 1行テキスト | 最初のスペースより前 |
| `FirstName` | 名 | 1行テキスト | 最初のスペースより後ろ |
| `Email` | メールアドレス | 1行テキスト | メールアドレス |
| `SyncKey` | 同期キー | 1行テキスト | **一意キー**。`userId` か、無ければメンバーシップID |
| `TeamsUserId` | TeamsユーザーID | 1行テキスト | Entra のオブジェクトID |
| `MembershipId` | メンバーシップID | 1行テキスト | チャネル内のメンバーシップID |
| `TeamId` | チームID | 1行テキスト | |
| `ChannelId` | チャネルID | 1行テキスト | 同期対象の判別に使う |
| `MemberTenantId` | メンバーテナントID | 1行テキスト | 外部ユーザー判定に使う |
| `MemberRoles` | ロール | 1行テキスト | `owner` / `guest` など |
| `MembershipKind` | メンバー種別 | 1行テキスト | `direct` / `indirect` |
| `IsExternalUser` | 外部ユーザー | はい/いいえ | |
| `MemberStatus` | 同期状態 | 1行テキスト | `在籍` / `離脱` |
| `IsActive` | 有効 | はい/いいえ | |
| `LastSyncedAt` | 最終同期更新日時 | 日付と時刻 | 作成・更新した時刻 |
| `SyncSource` | 同期元 | 1行テキスト | 固定値 `TeamsChannelMemberSync` |

**すべての列は既定ビューに自動で追加される**ので、リストを開くと氏名・姓・名・メールアドレスがそのまま並ぶ。ビューへの追加は `AddViewField`（追加）だけで、`removeAllViewFields`（作り直し）は定義に一切含めない。利用者が並べ替えた既存ビューは壊さず、足りない列を足すだけ。

組み込みの `Title` 列は表示名も型も必須設定も変更しない（既存リストを壊さないため）。**氏名は `Title` に入れず、`FullName` / `LastName` / `FirstName` に入る。** `Title` は SharePoint で必須になっているため、空にできない代わりに同期キーを入れている。

### 氏名の整形

Teams の表示名には外字の代替表記や英字読みが混ざる。次の順で整形してから列へ入れる。

| 入力（Teams の表示名） | 氏名 | 姓 | 名 |
|---|---|---|---|
| `▲高▼元 優子(TAKAMOTO Yuko)` | `高元 優子` | `高元` | `優子` |
| `佐藤 花子（SATO Hanako）` | `佐藤 花子` | `佐藤` | `花子` |
| `山田　太郎`（全角スペース） | `山田 太郎` | `山田` | `太郎` |
| `山田太郎`（スペースなし） | `山田太郎` | `山田太郎` | （空） |

1. 外字マーカー `▲` `▼` を除去する
2. 括弧（半角 `(` / 全角 `（`）以降を落とす
3. 全角スペースを半角に寄せて前後を trim する → これを **氏名**
4. 最初のスペースの前を **姓**、後ろを **名** にする（スペースが無ければ全体を姓、名は空）

### 設定リスト（管理サイト上・名前は「Teamsチャネルメンバー同期設定」固定）

`Title`(設定名) / `ConfigKey`(設定キー) / `TeamsChannelUrl` / `TeamId` / `ChannelId` / `TenantId` / `SiteUrl` / `ListTitle` / `ChannelType` / `MemberSource` / `IsEnabled` / `ConfigVersion` / `LastTestSucceededAt` / `LastSyncAt` / `LastSyncResult` / `UpdatedAt`

## 13. 同期キー

`SyncKey` = **`userId`（Microsoft Entra のオブジェクトID）**。`userId` が空のメンバーだけメンバーシップID（`id`）を使う。

- メールアドレスには依存しない（改姓・メール変更で別人扱いにならない）。
- IDの内部構造は分解しない。Microsoft は公式に「メンバーシップIDは不透明な文字列として扱い、解析してはならない」としている（[公式](https://learn.microsoft.com/en-us/graph/api/channel-list-members?view=graph-rest-1.0)）。

同期の分岐は **0件→作成 / 1件→内容を比較して必要なときだけ更新 / 2件以上→書き込まず記録**。
比較対象は 氏名・メール・ロール・メンバー種別・同期状態・有効。**何も変わっていなければ書き込まない**。

## 14. メンバー離脱時の扱い

**論理無効化（物理削除はしない）。** 同期状態を `離脱`、有効を `いいえ` に更新するだけで、行は残す。

実行するのは次の条件を**すべて**満たしたときだけ:

- Teams からのメンバー取得が最後まで完了している
- 取得件数が **0件でない**
- 既存アイテムの取得が最後まで完了している
- どの段階でも失敗を記録していない

Teams コネクタが失敗して0件になっても、この条件が偽になるため無効化処理は丸ごとスキップされる。
対象は「このフローが作成した（`SyncSource` 一致）」かつ「同じチャネル（`ChannelId` 一致）」かつ「まだ在籍扱い」の行だけ。それ以外のアイテムには読み書きとも一切関与しない。
定義には **DELETE 系の REST が1件も含まれていない**（検証スクリプトが0件を機械確認する）。

## 15. 共有チャネルに関する制限

- Microsoft Graph の `/members` は共有チャネルでも**直接メンバーしか返さない**。共有先チーム経由の間接メンバーを含めるには `/allMembers` を使う必要がある（[公式](https://learn.microsoft.com/en-us/graph/api/channel-list-allmembers?view=graph-rest-1.0)）。
- 本フローは、チャネル種別が `shared` のときだけ `/allMembers` も取得して合流させる。間接メンバーは `@microsoft.graph.originalSourceMembershipUrl` の有無で判別し、`MembershipKind` 列に `direct` / `indirect` として記録する。
- Teams コネクタの `ListMembers` の公式説明は "List **direct** members of a group chat or a channel" であり、単独では直接メンバーのみ。
- 共有チャネルでは **ホストチーム（共有元のチーム）のID**を指定する必要がある（公式）。
- **実環境での動作は未確認**（[docs/known_limitations.md](docs/known_limitations.md)）。

## 16. エラー確認方法

1. Power Automate の実行履歴を開く。
2. 失敗した **Scope の名前**（`Scope_06_GetMembers` など）が、そのまま失敗した処理単位を表す。
3. `Scope_Finalize` の `Compose_Result_Summary` を開くと、実行ID・対象チームID・チャネルID・サイト・リスト・各件数・失敗した段階・エラーコード・HTTPステータスがまとまって出る。**氏名やメールアドレスはログに複製していない。**
4. 日次実行の結果は設定リストの `最終同期結果` 列にも記録される（件数のみ。個人情報は含まない）。

**想定内のエラー**（設定不備・アクセス不可など）は実行自体は成功扱いで終わり、`failedStage` と `errorCode` に理由が入る。**想定外の失敗**は実行が失敗として記録される。詳しくは [docs/troubleshooting.md](docs/troubleshooting.md)。

## 17. 設定変更方法

| やりたいこと | 方法 |
|---|---|
| 同期先や対象チャネルを変える | フローA を再実行して新しい値を入力する（テスト成功後に設定が更新される） |
| 一時的に同期を止める | 設定リストの該当行の `有効` を「いいえ」にする。またはフローB をオフにする |
| チャネルを1つだけに絞る | フローA 実行時に「他のチャネル設定を無効化する」を「はい」にする |
| 実行時刻を変える | `build_daily_flow.py` の `SCHEDULE_HOUR` / `SCHEDULE_MINUTE` を直して再生成 |
| 管理サイトを移す | 両フローの `Compose_AdminSiteUrl` を書き換え、設定リストを移設する |

## 18. 変更の手順（このリポジトリでの作法）

`definition.json` は生成物。**直接編集しない。**

```bash
# 1. source/build_*.py もしくは shared/sync_blocks.py を編集する
python projects/teams-channel-member-sync/flows/setup-and-test-sync/source/build_setup_flow.py
python projects/teams-channel-member-sync/flows/daily-member-sync/source/build_daily_flow.py

# 2. 静的検証（エラー0・警告0が完成条件）
python projects/teams-channel-member-sync/flows/setup-and-test-sync/source/validate_setup_flow.py
python projects/teams-channel-member-sync/flows/daily-member-sync/source/validate_daily_flow.py
python tools/wdl_lint.py --all .

# 3. オフラインテスト
python projects/teams-channel-member-sync/tests/run_url_parse_tests.py
python projects/teams-channel-member-sync/tests/run_sync_logic_tests.py
python projects/teams-channel-member-sync/tests/run_check_regression_tests.py

# 4. アウトライン → パッケージ化 → ZIP再展開検査
python tools/gen_outline.py <definition.json> <validation/action_outline.txt>
python tools/pack_package.py <source/package> <release/<論理名>_YYYYMMDDHHMMSS.zip>
python projects/teams-channel-member-sync/flows/<フロー>/validation/extract_check.py
```

最後に `handbook/checklists/import_save_validation_checklist.md` で照合する。

## 19. 関連文書

| 文書 | 内容 |
|---|---|
| [docs/design_decisions.md](docs/design_decisions.md) | 設計判断と根拠（公式資料の出典つき） |
| [docs/url_parsing_spec.md](docs/url_parsing_spec.md) | URL解析・正規化の仕様 |
| [docs/list_schema.md](docs/list_schema.md) | リストと列の定義 |
| [docs/installation.md](docs/installation.md) | インポートと初期設定の手順 |
| [docs/known_limitations.md](docs/known_limitations.md) | 既知の制限と要実環境確認事項 |
| [docs/troubleshooting.md](docs/troubleshooting.md) | エラーの調べ方と対処 |
| [tests/test_cases.md](tests/test_cases.md) | テスト一覧（オフライン済み／実環境で行うもの） |
