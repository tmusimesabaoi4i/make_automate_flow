# 03. 実装設計書（CreateMeetingArchiveLists）

フロー構造・アクション内訳・冪等設計・参照フローとの差分・主要な設計判断を記録する。
作成日: 2026-07-17

## 1. フロー構造

### 1.1 全体構成: Ledger→RunLog 完全直列

`MeetingArchiveLedger` の全アクションチェーンが完了した後に `MeetingArchiveRunLog` のチェーンが続く、**単一の直列パス**（分岐なし・並列なし・Foreachなし）。境界は次の1点のみで確認できる（`WORK_DEF`=`../source/package/.../definition.json`実引用）:

```json
"Compose_RunLogListTitle": {
  "type": "Compose",
  "inputs": "MeetingArchiveRunLog",
  "runAfter": { "Add_LedgerViewField_Modified": ["Succeeded"] }
}
```

`Add_LedgerViewField_Modified`（Ledgerチェーンの最終アクション）の成功後に`Compose_RunLogListTitle`（RunLogチェーンの起点）が走る。

### 1.2 各リストの9段構成

両リストとも同一の9段パターンを持つ（`prefix`=`Ledger`または`RunLog`）:

| 段 | 内容 | 代表アクション名 |
|---|---|---|
| 1 | リスト名定数 | `Compose_{prefix}ListTitle` |
| 2 | リスト作成 | `Create_{prefix}List` |
| 3 | リスト取得（4ステータス継続） | `Get_{prefix}List` |
| 4 | リストID保持 | `Compose_{prefix}ListId` |
| 5 | 既存列一覧取得 | `Get_{prefix}ExistingFields` |
| 6 | 列ごとの冪等作成（Filter→If×11） | `Filter_{prefix}_<列>` → `If_Create_{prefix}_<列>` |
| 7 | 既定ビュー全削除 | `Remove_{prefix}DefaultViewFields` |
| 8 | ビュー用列一覧再取得 | `Get_{prefix}FinalFields` |
| 9 | 既定ビュー再構築（LinkTitle→カスタム11列→システム4列） | `Add_{prefix}ViewField_LinkTitle` → (`Filter_{prefix}View_<列>`→`ComposeInternalName_{prefix}_<列>`→`Add_{prefix}ViewField_<列>`)×11 → `Add_{prefix}ViewField_Author/Editor/Created/Modified` |

### 1.3 命名規約

| 接頭辞 | 意味 | 型 |
|---|---|---|
| `Compose_{prefix}ListTitle` / `Compose_{prefix}ListId` | リスト名・IDの定数保持 | Compose |
| `Create_{prefix}List` | リスト本体の作成 | OpenApiConnection(POST) |
| `Get_{prefix}List` / `Get_{prefix}ExistingFields` / `Get_{prefix}FinalFields` | リスト・列メタデータの取得 | OpenApiConnection(GET) |
| `Filter_{prefix}_<列>` | 列存在チェック（InternalName一致） | Query |
| `If_Create_{prefix}_<列>` / `Create_{prefix}_<列>`（If内） | 列の冪等作成 | If / OpenApiConnection(POST) |
| `Remove_{prefix}DefaultViewFields` | 既定ビュー全列削除 | OpenApiConnection(POST) |
| `Filter_{prefix}View_<列>` | ビュー用InternalName解決の検索 | Query |
| `ComposeInternalName_{prefix}_<列>` | 解決したInternalName（フォールバック付き） | Compose |
| `Add_{prefix}ViewField_<列 or システム列名>` | 既定ビューへの列追加 | OpenApiConnection(POST/MERGE) |

`{prefix}`は`Ledger`/`RunLog`の2種、`<列>`は各リストの11カスタム列名（`01_list_schema_evidence.md`参照）。

## 2. 156アクションの内訳（機械集計・`validate_list_definition.py`実行結果と一致）

| 種別 | 該当アクション群 | Ledger | RunLog | 合計 |
|---|---|---|---|---|
| OpenApiConnection | `Create_{prefix}List`(1)＋`Get_{prefix}List`(1)＋`Get_{prefix}ExistingFields`(1)＋`Get_{prefix}FinalFields`(1)＋`Remove_{prefix}DefaultViewFields`(1)＋`Add_{prefix}ViewField_LinkTitle`(1)＋`Add_{prefix}ViewField_<11列>`(11)＋`Add_{prefix}ViewField_<Author/Editor/Created/Modified>`(4)＋`Create_{prefix}_<11列>`(If内・11) | 32 | 32 | 64 |
| Query | `Filter_{prefix}_<11列>`（存在チェック）＋`Filter_{prefix}View_<11列>`（ビュー用解決） | 22 | 22 | 44 |
| Compose | `Compose_{prefix}ListTitle`(1)＋`Compose_{prefix}ListId`(1)＋`ComposeInternalName_{prefix}_<11列>`(11) | 13 | 13 | 26 |
| If | `If_Create_{prefix}_<11列>` | 11 | 11 | 22 |
| **合計** |  | **78** | **78** | **156** |

トップレベル134（If自体を1アクションとしてカウント）＋If内側の`Create_{prefix}_<列>`22＝156。トリガー（`manual`）は上記に含まない。

## 3. 冪等設計

### 3.1 列レベル: Filter + If(`length==0`)

各カスタム列は次の2アクションで冪等化する（`WORK_DEF`実引用、`If_Create_Ledger_IdempotencyKey`）:

```json
"Filter_Ledger_IdempotencyKey": {
  "type": "Query",
  "inputs": {
    "from": "@coalesce(body('Get_LedgerExistingFields')?['value'], json('[]'))",
    "where": "@equals(coalesce(item()?['InternalName'], ''), 'IdempotencyKey')"
  },
  "runAfter": { "Get_LedgerExistingFields": ["Succeeded"] }
},
"If_Create_Ledger_IdempotencyKey": {
  "type": "If",
  "expression": { "and": [ { "equals": ["@length(body('Filter_Ledger_IdempotencyKey'))", 0] } ] },
  "actions": { "Create_Ledger_IdempotencyKey": { "...": "createFieldAsXml" } },
  "runAfter": { "Filter_Ledger_IdempotencyKey": ["Succeeded"] }
}
```

初回実行: `Get_LedgerExistingFields`は空配列（新規リストのため既定Title列のみ）→`Filter`結果は0件→`length==0`が真→列作成。
2回目以降の実行: `Get_LedgerExistingFields`に該当`InternalName`の列が存在→`Filter`結果は1件→`length==0`が偽→`Create_Ledger_<列>`は実行されない（Ifの`else`は定義していないため、条件不成立時は単に何もしない）。

### 3.2 リストレベル: 4ステータス継続

`Get_{prefix}List`は`Create_{prefix}List`の`["Succeeded","Skipped","Failed","TimedOut"]`いずれでも実行される（参照フロー`getCreatedList`のパターンを踏襲、`WORK_DEF`実引用）:

```json
"Get_LedgerList": {
  "runAfter": { "Create_LedgerList": ["Succeeded", "Skipped", "Failed", "TimedOut"] }
}
```

リストが既に存在する場合、`Create_LedgerList`（`_api/web/lists`へのPOST）はSharePoint側で重複名エラーとなり**Failed**になるが、後続の`Get_LedgerList`（`GetByTitle`のGET）は既存リストを問題なく取得できるため、以降の列存在チェック・ビュー再構築は正常に継続する。

### 3.3 2周目の完全冪等動作（予測）

同一環境で2回目にこのフローを実行した場合に予測される挙動:

1. `Compose_LedgerListTitle`/`Compose_RunLogListTitle`: 定数のため常に成功。
2. `Create_LedgerList`/`Create_RunLogList`: **Failed**になる（リストが既に存在するため）。**これは異常ではなく設計どおりの表示**（§3.4参照）。
3. `Get_LedgerList`/`Get_RunLogList`: 4ステータス継続により実行され、既存リストのIdを取得して成功。
4. `Get_{prefix}ExistingFields`: 既存の11カスタム列（1回目で作成済み）を含む配列を返す。
5. 11本の`Filter_{prefix}_<列>`はすべて1件ヒット（`length==0`が偽）となり、対応する`If_Create_{prefix}_<列>`はすべて列作成をスキップ。**列の重複作成は発生しない**。
6. `Remove_{prefix}DefaultViewFields`: 既定ビューを全削除（1回目と同じ操作、冪等）。
7. `Get_{prefix}FinalFields`: 既存列一覧を再取得（列が既に存在するため1回目と同じ内容）。
8. `Filter_{prefix}View_<列>`→`ComposeInternalName_{prefix}_<列>`→`Add_{prefix}ViewField_<列>`: 同じInternalNameを再解決し、同じ既定ビューを再構築。結果として1回目と**同一の状態**に収束する。

結論: **列作成・ビュー構成の観点では完全に冪等**。差異が生じるのは`Create_{prefix}List`の実行結果表示（Failed）のみであり、リスト自体・列・ビューの最終状態は1回目の実行結果と一致する。

### 3.4 「`createList`失敗表示は正常」という運用上の注記

2回目以降の実行で`Create_LedgerList`/`Create_RunLogList`が赤（Failed）で表示されるのは、参照フロー`CreateKnowledgeList`から踏襲した**意図的な半冪等パターン**の帰結であり、フローの不具合ではない。実行履歴で全体が「成功」と表示されない場合でも、後続の4ステータス継続・列ごとのFilter+Ifにより実害（列やビューの破壊・重複）は生じない。この点は`05_implementation_report.md`の未解決事項にも記録する。

## 4. 参照フローとの差分表

| 区分 | 内容 | 根拠 |
|---|---|---|
| 追加 | 列ごとの冪等ガード（`Filter_{prefix}_<列>`→`If_Create_{prefix}_<列>`、22アクション/リスト） | 参照フローの`addRow*`は無条件直列実行で再実行時に重複作成エラーが起きる設計だった（`02_reference_flow_action_map.md` #9-#12） |
| 追加 | 既定ビュー先頭への`LinkTitle`列（`Add_{prefix}ViewField_LinkTitle`） | 参照フローは先頭がカスタム列（`KnowledgeTitle`）で、リンク付きタイトル表示という一覧性への配慮がなかった |
| 追加 | `Note`型（`RichText=FALSE, NumLines=6`）採用列（`SavedFileUrl`/`ErrorMessage`/`ArchiveUrl`の3列） | `01_list_schema_evidence.md`§2・§3.1参照。255字超URL・エラー文対策 |
| 追加 | `Number`型採用列（`MeetingCount`/`SavedCount`/`SkippedCount`/`FailedCount`の4列、RunLogのみ） | 件数列は常に整数のためText型で妥協する理由がない |
| 追加 | InternalName解決のフォールバック`coalesce(first(body(...))?['InternalName'], '<列名>')` | 参照フローの`getInternalNameKnowledge*`はフォールバックなし（`first()`が`null`の場合`AddViewField('')`となり失敗しうる）。表示名と一致する列が万一未作成でも、列名リテラルでのAddViewField試行にフォールバックする改善 |
| 削除 | Lookup機構一式（`varTagListTitle`/`getTagList`/`varTagListId`/`addRowPrimaryTag`/`filterKnowledgePrimaryTag`/`getInternalNameKnowledgePrimaryTag`/`addViewFieldPrimaryTag`、計7アクション） | 台帳・実行ログはLookup列を持たない（`01_list_schema_evidence.md`§4-1） |
| 削除 | `EnableAttachments` | 添付利用実績なし（`02_reference_flow_action_map.md`不採用根拠） |
| 削除 | `deactivateSPOTitle`（Title Required解除） | Title常時書き込みのため（同上） |
| 削除 | `addViewFieldAttachments` | 添付利用実績なし |
| 変更 | 列ビューの解決方式は「表示名(Title)でFilter→InternalName取得→AddViewField」のまま維持 | 表示名=内部名=ASCIIを列作成時に保証する設計（`DisplayName==Name`の静的検査あり）だが、手動で先に列が作られていた場合など内部名がずれるケースにも対応できるよう、直接リテラルではなく表示名解決のロジック自体は参照フローから維持した（§5.2参照） |
| 変更 | SchemaXmlの`Required`: `TRUE`（参照の`KnowledgeTitle`等） → `FALSE`（新フロー全列） | 台帳・実行ログの列はいずれも空値許容の運用（例: `ReplyId`は親投稿添付で常に空文字）のため必須制約は不要 |
| 変更 | SchemaXmlの`Indexed`: 参照は一部列`TRUE` → 新フローは全列で属性省略（既定FALSE） | 台帳・実行ログの検索は`RunId`等の文字列一致のみで、SharePoint側インデックスに性能上の要件がないため付与しない |
| 変更 | `createList`のrunAfter: 参照は`varTagListTitle`経由の歪んだ依存 → 新フローは対応する`Compose_{prefix}ListTitle`への直接依存 | `../../../../../references/reference_notes.md`§2で指摘した実行順の歪みを是正 |

## 5. 設計判断の記録

### 5.1 per-column方式 vs Foreach（採用: per-column方式）

11個のカスタム列それぞれに専用の`Filter_*`/`If_Create_*`/`Create_*`アクションを個別定義する方式（per-column）を採用し、列定義の配列を`Foreach`で回す方式は採らなかった。

- 参照フロー`CreateKnowledgeList`自体が`Foreach`を一切使わない完全直列構成であり、これに忠実な構造とした。
- 列ごとに`SchemaXml`（`Type`/`DisplayName`/`Name`/型固有属性）が異なるため、`Foreach`化しても結局アイテムごとの分岐ロジック（型ごとのXML組み立て）が必要になり、複雑さの削減効果が薄い。
- per-column方式は各アクションが静的に列挙されるため、`validate_list_definition.py`のような**静的検証**（SchemaXmlの直接XMLパース、期待列一覧との突合）がアクション単位でそのまま行える。`Foreach`化すると実行時にしか列内容が確定せず、静的検証の一部（列名とアクション名の対応チェックなど）が成立しなくなる。
- `Foreach`は`runtimeConfiguration.concurrency`の設定要否など考慮点が増えるが、この一度きりのリスト作成ユーティリティフローではその複雑さに見合う利点がない。

### 5.2 ビュー段: Filter+Compose維持 vs 直接AddViewField（採用: Filter+Compose維持。112アクション案は代替として記録）

カスタム列の`SchemaXml`は`DisplayName`と`Name`を必ず同一値（ASCII）で作成する（`check_schema_purity`で機械検証済み）。このため理論上は、列作成時と同じ列名リテラルを使って`AddViewField('<列名>')`を直接呼び出せば、`Filter_{prefix}View_<列>`→`ComposeInternalName_{prefix}_<列>`の2アクション（列あたり）を省略できる。この場合の総アクション数は156−44（11列×2アクション×2リスト）＝**112**となる。

この112アクション案は**代替として記録するに留め、採用しなかった**。理由:

- 表示名ベースでInternalNameを解決する方式は参照フロー由来のパターンであり、「列が手動で事前作成されていた」「過去の部分実行で異なる内部名の列が残っている」といった、列作成アクション自身を経由しない経路で列が存在するケースにも対応できる（Filterは`Get_{prefix}FinalFields`の実データに基づくため、実際に存在する列のInternalNameを常に正しく引ける）。
- フォールバック（§4「変更」参照）と組み合わせることで、表示名一致が万一取れなかった場合でも列名リテラルへ自動的にフォールバックするため、**堅牢性を優先**し、44アクション分のコスト増を許容した。
- 156アクションという規模はレガシーパッケージのJSON1ファイルとして十分に静的検証・レビュー可能な範囲（`04_validation_report.md`で0エラー確認済み）であり、112への圧縮によるメリットよりも堅牢性を優先する判断とした。

### 5.3 If式は`length`形式を採用（実環境インポート実績のある形式）

`If_Create_{prefix}_<列>`の条件式は`{"and":[{"equals":["@length(body('Filter_...'))", 0]}]}`という「`and`+`equals`+`length`」の組み合わせで統一した（`validate_list_definition.py`の`check_if_shape`で全22件を機械検証）。これは単一フロー本体（`PA_Migrate_Teams_Meeting_Archive_To_SPO`）の開発過程で実環境インポートに成功した実績のある式の型（v3以降で確立した書き方）に合わせたものであり、他の等価な表現（`less`/`not(greater(...))`等）は実環境での動作実績がないため採用しなかった。

### 5.4 パッケージGUID・API/接続GUID・認証形式の維持方針

- **資産GUID3点一致**: `7c3e50b2-91a4-4f2e-8f5a-6f1de2a9c4b7`を、ルート`manifest.json`の`resources`キー・`Microsoft.Flow/flows/manifest.json`の`flowAssets.assetPaths`・実際のフォルダ名`Microsoft.Flow/flows/7c3e50b2-.../`の3箇所すべてで一致させた（レガシーパッケージ形式の必須要件。`04_validation_report.md`で機械検証済み）。
- **API/接続リソースGUIDは参照フローの値を維持**: `e4f31fdf-c13c-4607-8af5-06baa431158d`（SharePoint APIリソース）・`f1e38ae6-6c4b-4670-9e29-c58312fbd2fb`（接続インスタンスリソース）・`connectionReferences.shared_sharepointonline.connectionName="054920e5a92b48b6b53f62b01b3cb354"`は、いずれも参照フロー`CreateKnowledgeList`の実ファイル（`../../../../../references/extracted/reference_original/.../apisMap.json`・`connectionsMap.json`）から採取した値をそのまま採用し、新規に捏造していない。同一テナント・同一SharePoint接続を前提とする別パッケージであるため、この対応関係（`apisMap`/`connectionsMap`とmanifestのGUIDの整合）を維持することが最も安全という判断による。
- **Embedded認証の維持**: 接続は`source="Embedded"`＋`"authentication": "@parameters('$authentication')"`（`$authentication`/`$connections`パラメータ経由）とし、単一フロー本体が採用する`source="Invoker"`＋`X-MS-APIM-Tokens`参照式とは異なる形式を意図的に維持した。これは参照フロー`CreateKnowledgeList`（実働・保存実績あり）がこの形式で構築されているためであり、各パッケージはそれぞれの実績ある前例に忠実であることを優先した（単一フロー側はv3の実環境インポート成功実績がある`Invoker`形式を維持している。`SINGLE_FLOW_FACTS.md`v5参照）。

## 6. サイト決定の経緯

`SINGLE_FLOW_FACTS.md`「修正反映（v8・リスト操作サイトの分離。ユーザー決定 2026-07-17）」に基づく:

- 単一フロー（`PA_Migrate_Teams_Meeting_Archive_To_SPO`）の`varSiteAddress`（`https://metijapan.sharepoint.com/sites/mROOM_240600018`）はファイル保存（添付・総括doc）専用として維持されている（保存先フォルダが実在するため）。
- 台帳・実行ログの**リスト操作のみ**を`pjteam_220400119`サイト（`https://metijapan.sharepoint.com/teams/pjteam_220400119`）に分離することが`AskUserQuestion`でユーザーに確認・決定された。
- この決定を受けて本リスト作成フロー`CreateMeetingArchiveLists`は、`build_list_package.py`の`SITE`定数（`https://metijapan.sharepoint.com/teams/pjteam_220400119`）を全REST呼び出しの`dataset`に採用し、`MeetingArchiveLedger`/`MeetingArchiveRunLog`の両リストを`pjteam_220400119`サイト上に作成する。
- 単一フロー本体側も同じv8修正で、台帳・実行ログへの書込み4アクション（`Create_Ledger_Item`/`Create_Ledger_Item_Failed`/`Create_Run_Log`/`Create_Error_Log`）の`dataset`を`pjteam_220400119`側に付け替え済みであり、本リスト作成フローが作るリストの設置場所と単一フロー本体が書き込む先が一致するよう整合させている。
