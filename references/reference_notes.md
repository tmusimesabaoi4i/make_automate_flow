# 参照フロー解析メモ（CreateKnowledgeList）

CreateMeetingArchiveLists設計の土台となった参照フロー CreateKnowledgeList の構造・パターン・固有依存を整理した作業メモ。詳細な全アクション表は `02_reference_flow_action_map.md` を参照。
作成日: 2026-07-17

## 1. 参照フローの素性

- ソース: `create_meeting_list_sample_ref` 系列とは別の実働ZIP `CreateKnowledgeList_20260716161116.zip`（実働・保存実績あり）。展開先はローカルの `extracted/reference_original/`。
- フローGUID: `f4d84ea8-3f8e-4e74-b607-14a6eb3356bf`（definition.json の `name`/`id`、manifest resourcesキー、`Microsoft.Flow/flows/manifest.json` の `assetPaths` の3点で一致）。
- 表示名: `CreateKnowledgeList`。トリガー: `manual`（`Request`/`Button`、`inputs.schema={type:object,properties:{},required:[]}`、入力パラメータなし）。
- 接続: SharePoint（`shared_sharepointonline`）のみ、1本。`connectionReferences.shared_sharepointonline.source="Embedded"`、`connectionName="054920e5a92b48b6b53f62b01b3cb354"`。
- 認証は `"authentication": "@parameters('$authentication')"`（`$authentication`/`$connections` パラメータ経由のEmbedded形式）。全アクションが `OpenApiConnection`（`operationId=HttpRequest`のSharePoint REST）／`Compose`／`Query` のいずれかで、`Foreach`・`SetVariable`・`Scope` は一切使わない**完全直列・変数不使用**の構成。
- 総アクション数: **33**（トリガー除く）。トリガー含め **34**。ネスト（If/Foreach内）は無い＝全アクションがトップレベルの直列チェーン1本。

## 2. 実行順（トポロジカル）の要点

`runAfter` を辿った実際の実行順は、オブジェクトのJSONキー出現順とは一致しない。特に:
- `createList` の `runAfter` は `varListTitle` ではなく `varTagListTitle`（Tag側の定数Compose）を指す。`varTagListTitle` 自体が `varListTitle` の後続なので結果的にリスト名確定後にリスト作成が走るが、**本来無関係なはずのTag定数を経由させている**歪な依存になっている。新フローではこの歪みを踏襲せず、`Create_XList` は対応する `Compose_XListTitle` に直接 `runAfter` させている。
- `getCreatedList` は `createList` の `["Succeeded","Skipped","Failed","TimedOut"]`（4ステータス）で続行する。既存リストがある場合 `createList` は失敗するが、それでも `getCreatedList` は実行され実在リストのIDを取得できる——この「作成失敗を許容し取得で継続する」半冪等パターンは新フローの `Get_XList` にそのまま踏襲。
- 列追加チェーン（`addRowKnowledgeTitle`→`addRowPrimaryTag`→`addRowSummary`→`addRowKnowledgeBody`）は無条件の直列 `createFieldAsXml` で、**存在チェックが無い**。2回目の実行では列が重複作成されず既存列に対して失敗するだけ、という単純な「一度きり」設計。新フローはここに列ごとの `Filter`(InternalName一致)→`If`(`length==0`)を追加して冪等化した（参照フローからの唯一の構造的改善点）。
- ビュー再構築チェーン（`removeAllViewFields`→`addViewFieldKnowledgeTitle`→…→`addViewFieldModified`）は表示名で `Query` フィルタして `InternalName` を取得し、`AddViewField` する2段方式。この「表示名→InternalName解決」の考え方は新フローの `Filter_*View_*`→`ComposeInternalName_*`→`Add_*ViewField_*` に踏襲（フォールバック `coalesce(...,'列名')` を追加した点が改善）。

## 3. Knowledgeサンプル固有の要素（新フローで不採用）

| 要素 | 内容 | 不採用の根拠 |
|---|---|---|
| `varTagListTitle`/`getTagList`/`varTagListId` | Lookup先マスタリスト`KnowledgeTag`のID解決 | 新フローの2リストはLookup列を持たない（RunId文字列相関のみ）ため、Lookup先を解決する仕組み自体が不要 |
| `addRowPrimaryTag`（`KnowledgePrimaryTag`列） | `Type="Lookup"` で`List="{tagListId}"` を参照する列 | 台帳・実行ログにLookup列は存在しない |
| `EnableAttachments` | `EnableAttachments:true` へのMERGE更新 | 台帳・実行ログとも添付ファイルを使う処理が単一フロー側に存在しない（添付は文書ライブラリへの直接保存で完結） |
| `deactivateSPOTitle` | `Title`列の`Required`をfalseへ変更 | 単一フローは`Compose_Ledger_Body`/`Compose_RunLog_Body`で常に`Title`へ値（`IdempotencyKey`/`RunId_summary`等）を書き込むため、Required解除は不要かつ有害（誤って空Titleを許容してしまう） |
| `addViewFieldAttachments` | 既定ビューへ`Attachments`列を追加 | 添付利用実績がないため表示不要 |
| `KnowledgeTitle`/`KnowledgeSummary`/`KnowledgeBody` の列定義 | サンプル固有の日本語業務列 | 台帳・実行ログの列は`../flows/archive-meetings/source/package/.../definition.json`の`Compose_Ledger_Body`等で実際に使われている列名（`IdempotencyKey`, `RunId`, `SavedFileUrl`等）に総入れ替え |

## 4. 踏襲したパターン（構造として維持）

1. リスト名を`Compose`で定数化してから全REST呼び出しの`GetByTitle('...')`に埋め込む方式。
2. `Create_*List`失敗を許容し`Get_*List`（4ステータス）で継続する半冪等パターン。
3. `createFieldAsXml`によるSchemaXml列追加（`SP.XmlSchemaFieldCreationInformation`、`Options:0`）。
4. `removeAllViewFields()`→列ごと`AddViewField(InternalName)`(`SetAsDefaultView:true`)による既定ビュー再構築。
5. 表示名→InternalName解決に`Query`(Filter)+`Compose`(first().InternalName)を使う2段方式。
6. Embedded接続参照＋`$authentication`パラメータ参照という認証形式。
7. dataset(サイトURL)は全アクションで単一の静的リテラルに統一（動的式にしない）。

## 5. 新フローへの主な追加・変更（詳細は`03_implementation_design.md`）

- 列ごとの冪等ガード（Filter+If）を追加。
- ビュー先頭に`LinkTitle`（リンク付きタイトル）を追加（参照フローは先頭がカスタム列だった）。
- 列型をKnowledge固有の`Text(255,Indexed)`/`Note(RichText=TRUE)`から、台帳・実行ログの実利用に合わせ`Text(255)`/`Note(RichText=FALSE,NumLines=6)`/`Number`の3種へ再設計。
- `Required="TRUE"`（参照）→`Required="FALSE"`（新）。`Indexed="TRUE"`（参照の一部列）→属性省略（新、既定FALSE）。
