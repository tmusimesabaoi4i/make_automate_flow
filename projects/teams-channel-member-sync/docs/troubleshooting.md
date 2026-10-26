# トラブルシューティング

---

## 1. まずここを見る

| 見る場所 | 分かること |
|---|---|
| 実行履歴で**赤くなった Scope の名前** | どの処理単位で失敗したか（`Scope_06_GetMembers` など） |
| `Scope_Finalize` → `Compose_Result_Summary` | 実行ID・対象・件数・`failedStage`・`errorCode`・`errorMessage`・`httpStatusCode` |
| 設定リストの **最終同期結果** 列 | 日次実行の内訳（件数のみ。個人情報は含まない） |

**想定内のエラー**（設定不備・アクセス不可）は実行自体は成功で終わり、`failedStage` と `errorCode` に理由が入る。
**想定外の失敗**（REST の予期しない失敗など）は実行が失敗として記録され、`Scope_ErrorHandler` が動く。

Scope 名と処理単位の対応:

| Scope | 処理単位 |
|---|---|
| `Scope_00_Bootstrap` | 管理サイトURLの確定 |
| `Scope_01_ValidateInput` / `Scope_01_LocateConfigList` | 入力検証（A）／設定リストの特定（B） |
| `Scope_02_ParseTeamsUrl` / `Scope_02_ReadConfig` | Teams URL解析（A）／設定の読込み（B） |
| `Scope_03_ParseSharePointUrl` | SharePoint URL解析 |
| `Scope_03B_EnsureConfigList` | 設定リストの確保（Aのみ） |
| `Scope_04_CheckTeamsAccess` | Teams チャネルへのアクセス確認 |
| `Scope_05_EnsureMemberList` | 対象リストの確認・作成・不足列の追加 |
| `Scope_06_GetMembers` | Teams メンバー取得 |
| `Scope_07_NormalizeMembers` | メンバー情報の正規化 |
| `Scope_08_GetExistingItems` | SharePoint 既存アイテムの取得 |
| `Scope_09_SyncItems` | 新規作成・更新 |
| `Scope_10_DeactivateLeft` | 離脱者の無効化 |
| `Scope_11_SaveConfig` / `Scope_11_RecordResult` | 設定の保存（A）／結果の記録（B） |

---

## 2. エラーコード別の対処

### `ERR_ADMIN_SITE_NOT_SET`（**日次フローのみ**）
日次フローの `Compose_AdminSiteUrl` が空。初期設定フローの実行結果 `adminSiteUrl` の値を貼り付けて保存する（[installation.md](installation.md) §3）。初期設定フローの実行結果 `nextAction` に、貼り付けるべき値がそのまま出ている。

> 初期設定フローはこのエラーを出さない。管理サイトが指定されていなければ、入力された同期先サイトへ設定リストを作って続行する（2026-08-04 に「設定しないと1回も動かない」状態で2回続けて止まったため変更した）。

### `ERR_ADMIN_SITE_NOT_SHAREPOINT`
「設定リストを置くサイトのURL」または `Compose_AdminSiteUrl` に、SharePoint Online 以外のURLが入っている。`https://<テナント名>.sharepoint.com/sites/<サイト名>` の形にするか、**空にして同期先サイトへ作らせる**。

### 設定リストが見つからない／日次フローが `NOT_CONFIGURED` になる
初期設定フローの実行結果 `adminSiteUrl` と、日次フローの `Compose_AdminSiteUrl` が**同じ値か**を確認する。違うサイトを見ていると設定が見つからない。`adminSiteSource` が `target-site` なら、設定リストは同期先サイトにできている。

### `ERR_CHANNEL_URL_EMPTY` / `ERR_SITE_URL_EMPTY` / `ERR_LIST_NAME_EMPTY`
入力が空。3項目とも必須。

### `ERR_NOT_TEAMS_URL`
TeamsチャネルURLのホストが `teams.microsoft.com` でも `teams.cloud.microsoft` でもない。チャネルの「…」→「チャネルへのリンクを取得」で得られるURLを貼り付ける。

### `ERR_NOT_SHAREPOINT_URL`
SharePointサイトURLのホストが `*.sharepoint.com` でない。オンプレミスの SharePoint Server は対象外。

### `ERR_GROUPID_NOT_FOUND` / `ERR_GROUPID_INVALID`
URLのクエリに `groupId` が無い、またはGUIDの形式でない。チャネルのリンクではなく、チーム名からコピーしたURLになっている可能性がある。

### `ERR_CHANNELID_NOT_FOUND`
URLのパスに `/l/team/` が含まれていない。古い形式のリンクや、手で組み立てたURLでは起きうる。

### `ERR_CHANNELID_INVALID`
URLから取り出した値が `19:` で始まり `thread.` を含む形になっていない。チャット（1対1・グループ）のURLを貼っていないか確認する。

### `ERR_TEAMS_CHANNEL_ACCESS`
Teams チャネルの情報を取得できなかった。
- 接続したアカウントがそのチャネルのメンバーか確認する
- **共有チャネルの場合はホストチーム（共有元のチーム）のURLを使う**（公式の制約）
- `httpStatusCode` が `403` なら権限、`404` ならID不一致の可能性が高い

### `ERR_LIST_NOT_FOUND`（フローB）
設定リストが管理サイトに無い。フローA をまだ実行していないか、`Compose_AdminSiteUrl` が別のサイトを指している。フローAの値と一致しているか確認する。

### `ERR_LIST_CREATE_FAILED`
対象リストを作成できなかった。接続アカウントにサイトのリスト作成権限があるか確認する。

### `ERR_CONFIG_TEAMID_MISSING` など（フローB）
設定リストの行に必須項目が欠けている、または `SharePointサイトURL` のホストが `*.sharepoint.com` でない。手でリストを編集して壊した可能性がある。フローA を実行し直すのが確実。

### `ERR_CONFIG_DUPLICATE`
同じ `設定キー` の行が2件以上ある。どれを正とすべきか判断できないため、**書き込まずに記録だけ**している。設定リストで重複行を1つに整理する。

### `ERR_DUPLICATE_ITEMS`
同じ `同期キー` のアイテムがメンバーリストに2件以上ある。同様に書き込みを見送っている。リストで重複行を整理する。

### `ERR_FIELD_CREATE_FAILED`
列の作成に失敗した。同期は続くが、その列への書き込みは失敗する。`varItemErrors` にどの列かが記録されている。既に同名で**型の違う**列がある場合に起きうる。

---

## 3. 保存・インポート時に落ちる場合

### `OpenApiOperationParameterValidationFailed`（`ListMembers`）

**最も可能性が高い原因**: `body/recipient/groupId` / `body/recipient/channelId` というキー名が実機と違う（[known_limitations.md](known_limitations.md) A-1）。

対処は2つ。

**(a) 正しいキー名に直す（推奨）**

1. Power Automate で空のフローを作り、Teams コネクタの **「List chat or channel members」**（`ListMembers`）アクションを1つだけ追加する
2. スレッドの種類に **Channel** を選び、チームとチャネルを選ぶ
3. アクションの「…」→ **コードのプレビュー**（Peek code）で実際のパラメータ名を確認する
4. `shared/sync_blocks.py` の2定数を確認した値に直す

   ```python
   LISTMEMBERS_KEY_TEAM = "body/recipient/groupId"      # ← 実機の値に直す
   LISTMEMBERS_KEY_CHANNEL = "body/recipient/channelId" # ← 実機の値に直す
   ```

5. 両フローを再生成 → 検証 → 再パッケージ → 再インポートする

**(b) `ListMembers` を使わず Graph だけにする**

```python
# shared/sync_blocks.py
MEMBER_SOURCE_MODE = "graph_only"
```

に変えて再生成する。`ListMembers` アクションが定義から外れ、Teams コネクタの `HttpRequest` 経由の Graph（`GET /teams/{teamId}/channels/{channelId}/members`）だけでメンバーを取得する。機能は落ちない（むしろページングは Graph 経路のほうが確実）。

どちらの場合も、再生成後に必ず次を通すこと。

```bash
python projects/teams-channel-member-sync/flows/setup-and-test-sync/source/build_setup_flow.py
python projects/teams-channel-member-sync/flows/daily-member-sync/source/build_daily_flow.py
python projects/teams-channel-member-sync/flows/setup-and-test-sync/source/validate_setup_flow.py
python projects/teams-channel-member-sync/flows/daily-member-sync/source/validate_daily_flow.py
python tools/wdl_lint.py --all .
```

### 接続の認証で落ちる（実行時に401、または接続が解決されない）

認証方式は `shared/sync_blocks.py` の `AUTH_MODE` で切り替えられる。

```python
AUTH_MODE = "embedded"   # 既定。"invoker" に変えると X-MS-APIM-Tokens 方式になる
```

`connectionReferences[].source` も連動して切り替わる。ただし Invoker 方式は起動者のいない定期実行フローでは成立しない可能性が高いので、フローB では既定のまま使うことを推奨する（[design_decisions.md](design_decisions.md) §3）。

### `substring parameter is out of range: 'start index' ...`（解決済み・2026-08-04）

```
Unable to process template language expressions in action 'Compose_Admin_Cut' inputs at line '0'
and column '0': 'The template language function 'substring' parameter is out of range:
'start index' must be non-negative integer and should be less than the length of the string.'
```

**原因**: `substring()` の開始位置は「0以上」だけでなく**文字列長より小さい**必要があり、
空文字には `substring('', 0, 0)` すら適用できません。`Compose_AdminSiteUrl` が空のまま実行すると
サイトURL正規化の途中で落ちていました。

**対処済み**: すべての `substring` を番兵付き（`substring(concat(S, '#'), …)`）に変更し、
入力が空でも成立する形にしました。静的検査 P16 が「番兵の無い `substring`」を機械検出し、
`tests/run_check_regression_tests.py` の R23 がその検査の発火を確認しています。

2026-08-04 より前に取得したZIPを使っている場合は、`release/` の新しい日時のZIPを取り込み直してください。
なお `Compose_AdminSiteUrl` の設定は依然として必要です（未設定なら `ERR_ADMIN_SITE_NOT_SET` で安全に終了します）。

### `Unable to parse template language expression`

トリガー入力の説明文などに `@{` が入るとこのエラーになる（handbook の既知エラー #3）。本パッケージでは共通リンターの L02 / L03 が機械的に防いでいるので、手でデザイナー上のテキストを編集した場合に疑う。

---

## 4. 実行はするが結果がおかしい場合

### メンバーが1人も取れない（`memberCount` が 0）

1. `memberSource` を見る。空なら `Scope_06_GetMembers` そのものが失敗している
2. `httpStatusCode` が `403` なら、Teams コネクタが Graph のメンバーAPIを叩く権限を持っていない可能性（[known_limitations.md](known_limitations.md) A-2）
3. `MEMBER_SOURCE_MODE` を切り替えて、もう一方の経路で取れるか試す

**このとき既存のメンバーが全員「離脱」にされることはない。** 取得件数が0のときは無効化処理のガードが偽になり、スコープごとスキップされる。

### 取得件数が実際より少ない

`ListMembers` はページングを持たないため、大規模チャネルで打ち切られている可能性がある（[known_limitations.md](known_limitations.md) A-4）。`MEMBER_SOURCE_MODE = "graph_only"` に切り替えると、`@odata.nextLink` を追跡する経路になる。

### 共有チャネルで人数が期待と違う

- `/members` は**直接メンバーのみ**を返す（公式）。間接メンバーは `/allMembers` でしか取れない
- 本フローは `channelType` が `shared` のときだけ `/allMembers` も引く。`Compose_Result_Summary` の `allMembersFetched` が `true` になっているか確認する
- `メンバー種別` 列で `direct` / `indirect` を区別できる

### メールアドレスが空のメンバーがいる

- Teams / Graph が `email` を返さないメンバー（ゲスト・外部ユーザーなど）では、`GET /users/{userId}` で補完を試みる
- それでも取得できない場合は**空のまま残す**。推測でメールアドレスを生成することはしない
- 補完に失敗した件数は `Compose_Result_Summary` の `emailLookupFailures` に出る

### 毎日同じ人が「更新」され続ける

`unchangedCount` が伸びず `updatedCount` が毎回同じ数になる場合、比較対象の列（氏名・メール・ロール・メンバー種別・同期状態・有効）のどれかが書き込みと読み出しで一致していない。列の型が想定と違う（例: `有効` が「はい/いいえ」でなく1行テキストになっている）可能性がある。

### 対象外のアイテムが変更されてしまった

設計上ありえない。書き込み対象は `同期元 = TeamsChannelMemberSync` かつ `チャネルID` 一致の行だけに二重に絞っており、静的検査 P09 と `tests/run_sync_logic_tests.py` の Q01〜Q03 が確認している。もし起きたら、リストを手で編集して `同期元` 列に同じ値を入れてしまっていないか確認する。

---

## 5. 定期実行が動かない

| 症状 | 確認 |
|---|---|
| 実行履歴に何も出ない | フローがオンになっているか。インポート直後はオフ |
| 「初回設定が未完了」で終わる | 設定リストに `有効` = はい の行があるか。`Compose_AdminSiteUrl` がフローAと同じ値か |
| 実行時刻が数十秒ずれる | 公式に最大1分程度のずれがある。仕様 |
| 実行時刻を変えたい | `build_daily_flow.py` の `SCHEDULE_HOUR` / `SCHEDULE_MINUTE` を直して再生成する。デザイナー上で直接変えると次回の再生成で戻る |
| 1つの設定が失敗すると他も止まる | 起きない設計。各設定の最後の `Scope_11_RecordResult` が4状態すべてを受けるため、1件の失敗は他の設定に波及しない（静的検査 D05） |

---

## 6. 再生成・再検証のコマンド一覧

```bash
cd D:/make_automate_flow

# 生成
python projects/teams-channel-member-sync/flows/setup-and-test-sync/source/build_setup_flow.py
python projects/teams-channel-member-sync/flows/daily-member-sync/source/build_daily_flow.py

# 検証（エラー0・警告0が完成条件）
python projects/teams-channel-member-sync/flows/setup-and-test-sync/source/validate_setup_flow.py
python projects/teams-channel-member-sync/flows/daily-member-sync/source/validate_daily_flow.py
python tools/wdl_lint.py --all .

# オフラインテスト
python projects/teams-channel-member-sync/tests/run_url_parse_tests.py
python projects/teams-channel-member-sync/tests/run_sync_logic_tests.py
python projects/teams-channel-member-sync/tests/run_check_regression_tests.py

# パッケージ化と再展開検査
python tools/pack_package.py projects/teams-channel-member-sync/flows/setup-and-test-sync/source/package projects/teams-channel-member-sync/flows/setup-and-test-sync/release/TeamsChannelMemberSync_Setup_YYYYMMDDHHMMSS.zip
python projects/teams-channel-member-sync/flows/setup-and-test-sync/validation/extract_check.py
```

---
関連: [../README.md](../README.md) / [known_limitations.md](known_limitations.md) / [../../../handbook/knowledge/error_catalog.md](../../../handbook/knowledge/error_catalog.md)
