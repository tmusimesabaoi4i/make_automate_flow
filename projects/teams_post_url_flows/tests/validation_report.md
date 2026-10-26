# 検証レポート

- 対象: `Flow1_GetTeamsChannelPostFromUrl` / `Flow2_GetAllTeamsChannelPostRepliesFromUrl`
- 検証日: **2026-07-24**
- 検証ZIP:
  - `flows/flow1-get-channel-post/release/Flow1_GetTeamsChannelPostFromUrl_20260724190952.zip`
  - `flows/flow2-get-post-replies/release/Flow2_GetAllTeamsChannelPostRepliesFromUrl_20260724190952.zip`

## 総括

| 区分 | 結果 |
|---|---|
| 静的検証（definition構造・式・参照整合） | **エラー0 / 警告0**（両フロー） |
| URL解析のオフライン検証 | **40件中40件合格** |
| ZIP再展開検査 | **エラー0**（両フロー） |
| **実環境でのインポート** | **成功**（2026-07-24・利用者報告） |
| **実環境での実行** | **成功**（2026-07-24・利用者報告） |
| 実環境での保存操作 | 明示の報告なし（実行成功により定義はエンジンに受理されている） |

**パッケージは実環境でインポートでき、実行できることが確認されました（2026-07-24・利用者報告）。**

ただし報告内容は「安全にインポートでき、安全に実行できた」という範囲であり、**個別のテストケース（返信51件超のページング、共有チャネル、権限不足時の挙動など）まで確認されたことを意味しません。** 依然として確認が必要な事項は §5 に残しています。過去案件では「インポート・保存・実行に成功したが、実データでは全件が失敗していた」事例があるため（`handbook/knowledge/error_catalog.md`）、実行成功と結果の正しさは分けて扱います。

---

## 1. 実行した検証コマンドと結果

```powershell
cd projects/teams_post_url_flows

python flows/flow1-get-channel-post/source/build_flow1.py
python flows/flow1-get-channel-post/source/validate_flow1.py
python flows/flow2-get-post-replies/source/build_flow2.py
python flows/flow2-get-post-replies/source/validate_flow2.py
python tests/run_url_parse_tests.py
python ../../tools/gen_outline.py <definition.json> <validation/action_outline.txt>
python ../../tools/pack_package.py <source/package> <release/*.zip>
python flows/flow1-get-channel-post/validation/extract_check.py
python flows/flow2-get-post-replies/validation/extract_check.py
```

出力の全文は次のファイルに保存しています。

| 証跡 | パス |
|---|---|
| Flow1 静的検証 | `flows/flow1-get-channel-post/validation/validate_result.txt` |
| Flow2 静的検証 | `flows/flow2-get-post-replies/validation/validate_result.txt` |
| Flow1 アクションアウトライン | `flows/flow1-get-channel-post/validation/action_outline.txt` |
| Flow2 アクションアウトライン | `flows/flow2-get-post-replies/validation/action_outline.txt` |
| Flow1 ZIP再展開検査 | `flows/flow1-get-channel-post/validation/extract_check_result.txt` |
| Flow2 ZIP再展開検査 | `flows/flow2-get-post-replies/validation/extract_check_result.txt` |
| URL解析テスト | `tests/url_parse_test_result.txt` |
| 展開したZIPの中身 | `flows/*/validation/extracted/`（検証用コピー。正典は `source/package/`） |

---

## 2. 静的検証（`validate_flow*.py`）

### 集計

| 項目 | Flow1 | Flow2 |
|---|---|---|
| パッケージフォルダGUID | `5d2b8f31-7a46-49c0-b8e2-1f93c65a0d87` | `2c96a4e7-8b53-4d10-9f27-e6a41b085c39` |
| アクション総数 | 67 | 81 |
| 初期化変数 | 15 | 18 |
| SetVariable | 21（**自己参照 0**） | 24（**自己参照 0**） |
| AppendToArrayVariable | 2 | 4 |
| Foreach / Until | 0 / 0 | 2 / 1 |
| operationId | `HttpRequest` のみ | `HttpRequest` のみ |
| connectionReferences | `shared_teams` のみ | `shared_teams` のみ |
| **エラー / 警告** | **0 / 0** | **0 / 0** |

### 実施した検査項目

雛形（`projects/migrate-chat-spo/flows/archive-meetings/source/validate_definition.py`）から継承した検査:

- JSON構文の妥当性
- `runAfter` の参照先が同一コンテナの兄弟として実在すること
- アクション名がフロー全体で一意であること（重複0件）
- 変数の初期化⇔参照の双方向突合（未初期化参照0件・未使用変数0件）
- `InitializeVariable` が全件トップレベルにあること（Scope内配置0件）
- `body()` / `outputs()` の参照先アクションが実在すること
- SetVariable の自己参照（保存時 `WorkflowRunActionInputsInvalidProperty` の原因）が0件であること
- 変数の重複初期化が0件であること
- Append / Increment の対象変数が初期化済みであること
- `connectionReferences` とアクションの `host.connectionName` の突合

本件向けに追加した検査:

- **不正な `@` 位置の検査** — 式先頭・`@{}` 補間・文字列リテラル内 以外の `@` が0件（`error_catalog` の「`'@' at position …`」対策）
- **関数許可リスト検査** — 定義中の全関数が、本リポジトリの実働 `definition.json` に出現実績のある関数の集合に含まれること。**実在が不確かな関数を推測で使わないための機械的な歯止め**
- **Teams HttpRequest の必須パラメータ検査** — `Uri` / `Method` の存在、`connectionName` が `shared_teams`、`operationId` が `HttpRequest`、`Method` が `GET`（読み取り専用の担保）、`authentication` の存在
- **並列オフ検査** — 全 Foreach が `runtimeConfiguration.concurrency.repetitions = 1`
- **Do until の上限検査** — `limit.count` / `limit.timeout` が設定済み
- **トリガー検査** — `manual` / `Button` 単独、`TeamsPostUrl` が `string` 型・表示名「Teams投稿URL」・`required` に含まれる
- **実値混入検査** — 定義の `triggers` / `actions` に GUID実値・チャネルID実値・メールアドレス・SharePointサイトURL が0件
- **パッケージ整合検査** — GUID3点一致、`apisMap` / `connectionsMap` の値が `resources` と `dependsOn` に実在、`connectionReferences` とキーが一致

### 使用関数（両フロー）

```text
body coalesce concat contains createArray decodeBase64 decodeUriComponent empty
endsWith equals first if item items join json last length not or outputs split
string sub take triggerBody triggerOutputs trim union uriComponent utcNow variables
```

すべて `projects/migrate-chat-spo` の実働 `definition.json` に出現実績があります（`decodeBase64` は接続の `authentication` 標準参照式で18件、`endsWith` / `createArray` は1件ずつ）。指示書§4で例示された `uriQuery()` / `uriPath()` / `uriComponentToString()` は使用していません（理由は `docs/url_parsing_spec.md` §2）。

---

## 3. URL解析のオフライン検証

`tests/run_url_parse_tests.py` は、生成済み `definition.json` から `Scope_ParseUrl` のアクション列を読み出し、`tests/wdl_eval.py`（WDL式のミニ評価器）で**定義に実際に書かれている式そのもの**を評価します。設計書の再実装ではなく、成果物そのものを対象にしている点が重要です。

```text
[flow1] 合格 20 / 不合格 0（全 20 件）
[flow2] 合格 20 / 不合格 0（全 20 件）
合計: 合格 40 / 不合格 0
```

ケースの内訳は `test_cases.md` を参照してください（正常系12・異常系8を、2フロー分）。

**この検証で確認できないこと**: Power Automate実機での関数の挙動差、コネクタの応答、保存時検証、実行時エラー。

---

## 4. ZIP再展開検査（`extract_check.py`）

両フローとも **エラー0** です。

| 検査項目 | Flow1 | Flow2 |
|---|---|---|
| ZIPが破損なく開ける | ✅ | ✅ |
| エントリ数 | 5 | 5 |
| レガシー5ファイル構造がZIPルート直下から始まる（余分な親フォルダ無し） | ✅ | ✅ |
| `__MACOSX` / `.DS_Store` / ディレクトリエントリの混入 | 無し | 無し |
| 全JSONのパース | ✅ 5/5 | ✅ 5/5 |
| JSON以外のファイル混入 | 無し | 無し |
| パッケージGUID3点一致 | ✅ | ✅ |
| `apisMap` / `connectionsMap` が `resources`・`dependsOn` に実在 | ✅ | ✅ |
| `connectionReferences` とキー一致 | ✅ `shared_teams` | ✅ `shared_teams` |
| 展開結果が `source/package` とバイト一致（SHA-256） | ✅ | ✅ |
| フロー表示名 | Flow1 Teams投稿URLから投稿を取得 | Flow2 Teams投稿URLから全返信を取得 |
| トリガー・`TeamsPostUrl`・Teams HttpRequest の実在 | ✅ | ✅ |

### ZIPの内容（Flow1）

```text
manifest.json
Microsoft.Flow/flows/manifest.json
Microsoft.Flow/flows/5d2b8f31-7a46-49c0-b8e2-1f93c65a0d87/definition.json
Microsoft.Flow/flows/5d2b8f31-7a46-49c0-b8e2-1f93c65a0d87/apisMap.json
Microsoft.Flow/flows/5d2b8f31-7a46-49c0-b8e2-1f93c65a0d87/connectionsMap.json
```

Flow2 も同構造（GUIDは `2c96a4e7-8b53-4d10-9f27-e6a41b085c39`）。

---

## 5. 実環境確認が必要な事項（未検証）

**以下はいずれも未確認です。正常動作を断定していません。**

### 5-1. パッケージのインポート・保存 — **確認済み（2026-07-24）**

| # | 事項 | 状況 |
|---|---|---|
| 1 | ZIPが「パッケージのインポート (レガシー)」で取り込めるか | **✅ 成功**（利用者報告） |
| 2 | インポート後にフローを保存できるか（保存時にのみ出るエラーが無いか） | 保存操作の明示報告は無いが、**実行に成功しているため定義はエンジンに受理済み**。自己参照・パラメータ検証エラーは発生していないと判断できる |
| 3 | フローチェッカーでエラー・警告が0件か | 明示の報告なし |
| 4 | 匿名化した接続GUIDが、選択した実接続に再マッピングされるか | **✅ 実質確認**（実行に成功したため、接続は実接続へ正しく解決された） |

> この結果により、`handbook/rules/07` の「匿名化した接続情報がインポート時に実接続へ再マッピングされる挙動」は状況証拠から**実績**に格上げできます（`knowledge-update` Skill で還元予定）。

### 5-2. Graph呼び出し

| # | 事項 | 補足 |
|---|---|---|
| 5 | `GET /teams/{teamId}/channels/{channelId}/messages/{messageId}`（単一投稿の取得）が標準Teamsコネクタの `HttpRequest` で成功するか | 同一エンドポイント族（`/messages` `/messages/{id}/replies`）は実働サンプルでの動作実績が `handbook` に記録されているが、**単一メッセージ取得の直接の実行証跡は無い** |
| 6 | チャネルメッセージ読み取りに必要な権限が、Teamsコネクタの既存同意の範囲で満たされるか | テナントのAPIアクセス許可・条件付きアクセスに依存 |
| 7 | 失敗したコネクタアクションで `outputs(…)?['statusCode']` が取得できるか | 取得できない場合は `httpStatusCode=0` となり `ERR_UNEXPECTED_FAILURE` に落ちる（設計上フォールバック済み） |
| 8 | 削除済み投稿が `deletedDateTime` 付きで返るか 404 になるか | 両方に対応する実装だが、どちらを通るかは未確認 |
| 9 | 権限不足時に 403 が返るか 404 が返るか | 同上 |

### 5-3. 返信取得（Flow2）

| # | 事項 | 補足 |
|---|---|---|
| 10 | **返信が50件を超えるスレッドで、全件取得できるか** | `test_cases.md` ケース8。**最重要**。ページングが機能しているかはここでしか確認できない |
| 11 | `@odata.nextLink` の完全URLをそのまま `Uri` に渡して受理されるか | `handbook/rules/05` に【事実】として記載があるが、本フローでの実行は未確認 |
| 12 | 返信の並び順 | Graphが返す順序をそのまま保持。時系列保証は無い |
| 13 | 返信件数が多い場合にフロー実行時間（目安30分）に収まるか | `Do until` の上限は5,000反復 / 1時間だが、フロー側の制限が先に効く |

### 5-4. チャネル種別

| # | 事項 | 補足 |
|---|---|---|
| 14 | 標準チャネルで動作するか | 想定はしているが未確認 |
| 15 | プライベートチャネルで、メンバーであれば動作するか | 未確認 |
| 16 | **共有チャネルで動作するか** | URLの `groupId` が投稿の実体があるチームと一致しない場合があり、**404になる可能性がある**。対処は `docs/troubleshooting.md` §4-2 |

### 5-5. その他

| # | 事項 | 補足 |
|---|---|---|
| 17 | テナントのDLPポリシーでTeamsコネクタが許可されているか | 本フローは1コネクタのみのため、コネクタ間のDLP違反は原理的に発生しない |
| 18 | 添付・メンション・HTML本文を含む投稿での実データ形状 | `test_cases.md` 正常系9〜11 |

---

## 6. 設計上の判断と、指示書からの逸脱

いずれも理由を明記したうえで意図的に採用したものです。

| # | 指示書の記載 | 実装 | 理由 |
|---|---|---|---|
| 1 | §8 `Scope_Initialize` を作る | 変数初期化を**トップレベルの `Initialize_*` 連鎖**にした | `InitializeVariable` は Scope 内に置けない（`handbook/rules/01` 【事実】）。Scope名の例示は「例：」であり、Try/Catch/Finally 構造自体は `Scope_ParseUrl` / `Scope_GetTeamsData` / `Scope_CreateResult` / `Scope_ErrorHandler` / `Scope_Finalize` で実現している |
| 2 | §4 `uriPath()` `uriQuery()` `uriComponentToString()` の例示 | `split()` と `decodeUriComponent()` に置換 | 前2つは本リポジトリ内に使用実績が無く、`uriPath()` はパスの復号挙動が確定できない。§4は「実際に利用できる式を確認したうえで採用してください」としており、確認できた関数のみを採用した（`docs/url_parsing_spec.md` §2） |
| 3 | §3 `parentMessageId` が空でなければそれを使う | `'0'` も「値なし」と同等に扱う | 親投稿のリンクに `parentMessageId=0` が付く変種があり、そのまま渡すと必ず404になる。メッセージIDは13桁のエポックミリ秒であり `'0'` は実在しない（`docs/url_parsing_spec.md` §4） |
| 4 | §6.4 / §7.6 の `from.email` | 常に空文字 | Graph の `chatMessage.from.user` はメールアドレスを返さない。§6.4の「無理に値を捏造せず、空文字…」に従った |
| 5 | §7.6 の `replies[]` 構造 | `etag` / `messageType` を追加 | 「正規化の過程で情報を失わない構造にする」（§6.4）に沿った追加。既存フィールドは削っていない |
| 6 | §11 のディレクトリ構成 | `projects/teams_post_url_flows/flows/<フロー>/{spec,source,validation,release}` ＋ `docs/` `tests/` | §11は「既存ルールと整合する場所に配置」を第一に指示している。`build/` `dist/` `dist_extract_check/` `flow/` は 2026-07-17 の再編（`_legacy/2026-07-reorg-survey.md` §3）で廃止された旧名称のため使用していない。**ユーザー確認済み** |

### 共有ツールの修正（報告事項）

`tools/gen_outline.py` の60行目が、前案件のトリガー入力名（`LookbackDays/DryRun/ForceReprocess`）を**ハードコード**しており、他フローのアウトラインに誤った入力名が出力されていました。定義から実際のトリガー入力を読む形に修正しています（1箇所・出力のみに影響）。`CLAUDE.md` は `tools/` を「原則変更しない」としているため、判断が異なる場合は当該コミット前の状態に戻してください。

---

## 7. 確認済みの範囲と、まだ確認されていない範囲

### 確認済み（2026-07-24・利用者報告）

- **実環境へのインポートに成功した。**
- **実環境での実行に成功した。**
- これにより、レガシーパッケージの構造・接続参照の再マッピング・式の妥当性・保存時検証の通過が実証されました。

### まだ確認されていないこと

報告は「安全にインポートでき、安全に実行できた」という範囲です。次は依然として未確認です。

- **返信が50件を超えるスレッドで全件取得できるか**（§5-3 #10。最重要）
- 添付・メンション・HTML本文を含む投稿での実データ形状（`test_cases.md` 正常系9〜11）
- 異常系の実挙動（存在しない投稿・削除済み投稿・権限不足・共有チャネル）
- 返信の並び順

> **「実行できた」と「結果が正しい」は別です。** 過去案件では、フローがエラーなく完走したにもかかわらず対象データが全件失敗していた事例があります（`handbook/knowledge/error_catalog.md`「添付保存の全件Failed」）。`Compose_Flow_Output` の `success` と、Flow2 の `replyCount` が実際の返信数と一致するかを確認してください。

実環境で問題が見つかった場合は、`flows/*/source/build_flow*.py` を修正して再生成し、本レポートを更新してください。得られた知見は `knowledge-update` Skill で `handbook/` に還元してください。

---

関連: [test_cases.md](test_cases.md) / [../docs/installation.md](../docs/installation.md) / [../docs/troubleshooting.md](../docs/troubleshooting.md)
