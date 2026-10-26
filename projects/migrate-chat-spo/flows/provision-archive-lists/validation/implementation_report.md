# 05. 実装報告書（CreateMeetingArchiveLists）

参照フロー解析からパッケージ生成・静的検証までの成果を18項目でまとめる。
作成日: 2026-07-17

## 1. 参照フローの構造

参照フロー`CreateKnowledgeList`（実働ZIP `CreateKnowledgeList_20260716161116.zip`、フローGUID`f4d84ea8-3f8e-4e74-b607-14a6eb3356bf`）は、トリガー`manual`（Request/Button、入力パラメータなし）＋アクション33本（合計34、トリガー含む）の**完全直列・変数不使用**構成。接続はSharePoint（`shared_sharepointonline`）1本のみ、`source="Embedded"`＋`@parameters('$authentication')`という認証形式。単一のKnowledgeListを作成し、4つのカスタム列（うち1つはLookup型でTagマスタリストを参照）と、添付ファイル有効化・既定ビュー再構築を行う。詳細な全アクション対応は`02_reference_flow_action_map.md`、パターン分析は`01_reference_analysis/reference_notes.md`を参照。

## 2. 踏襲した処理

- リスト名を`Compose`で定数化し、全REST呼び出しの`GetByTitle('...')`に埋め込む方式。
- `Create_*List`失敗を許容し`Get_*List`（`Succeeded`/`Skipped`/`Failed`/`TimedOut`の4ステータス）で継続する半冪等パターン。
- `createFieldAsXml`によるSchemaXml列追加（`SP.XmlSchemaFieldCreationInformation`、`Options:0`）。
- `removeAllViewFields()`→列ごと`AddViewField(InternalName)`（`SetAsDefaultView:true`）による既定ビュー再構築。
- 表示名(Title)でQuery(Filter)→`first(...)?['InternalName']`でCompose、という2段のInternalName解決方式。
- Embedded接続参照＋`$authentication`パラメータという認証形式、および単一SharePoint接続のみという構成。
- `dataset`（サイトURL）を全アクションで単一の静的リテラルに統一する方式（検証項目「dataset全アクションで一致」で機械確認）。

## 3. 削除したKnowledgeList固有処理

| 処理 | 削除理由 |
|---|---|
| Lookup機構一式（`varTagListTitle`/`getTagList`/`varTagListId`/`addRowPrimaryTag`/`filterKnowledgePrimaryTag`/`getInternalNameKnowledgePrimaryTag`/`addViewFieldPrimaryTag`） | 台帳・実行ログはLookup列を持たない設計（§6参照） |
| `EnableAttachments` | 添付ファイル利用実績なし |
| `deactivateSPOTitle`（Title列のRequired解除） | Title列は常時書き込み対象のため解除不要（§8参照） |
| `addViewFieldAttachments` | 添付ファイル利用実績なし |
| `KnowledgeTitle`/`KnowledgePrimaryTag`/`KnowledgeSummary`/`KnowledgeBody`等のサンプル固有列名 | 台帳・実行ログの実列名（`IdempotencyKey`/`SavedFileUrl`等）に総入れ替え |

Knowledge固有トークンの残存は静的検証（`validate_list_definition.py`）で**0件**を確認済み（`04_validation_report.md`検査項目14）。

## 4. Ledger列定義

MeetingArchiveLedger（**12列**、Title含む）:

| 列 | 型 | 備考 |
|---|---|---|
| Title | Text（既定システム列） | 冪等キーを格納。常時書込み |
| IdempotencyKey | Text(255) | 冪等キー本体 |
| RunId | Text(255) | 実行識別子（RunLogとの相関キー） |
| MessageId | Text(255) | 親投稿ID |
| ReplyId | Text(255) | 返信ID（親投稿添付は空） |
| AttachmentId | Text(255) | 添付ID |
| OriginalFileName | Text(255) | 元ファイル名 |
| SavedFileName | Text(255) | 保存後ファイル名 |
| SavedFileUrl | **Note(RichText=FALSE, NumLines=6)** | 255字超URL対策 |
| Status | Text(255) | Saved/Failed |
| ErrorMessage | **Note(RichText=FALSE, NumLines=6)** | 255字超エラー文対策 |
| ProcessedDateTimeUtc | Text(255, ISO8601) | 処理日時 |

根拠・原文引用は`01_list_schema_evidence.md`§1参照。

## 5. RunLog列定義

MeetingArchiveRunLog（**12列**、Title含む）:

| 列 | 型 | 備考 |
|---|---|---|
| Title | Text（既定システム列） | `RunId_summary`/`RunId_error`。常時書込み |
| RunId | Text(255) | 実行識別子（Ledgerとの相関キー） |
| FlowName | Text(255) | 固定文字列 |
| Level | Text(255) | Info/Error |
| Status | Text(255) | Success/Failed |
| MeetingCount | **Number** | 件数 |
| SavedCount | **Number** | 件数 |
| SkippedCount | **Number** | 件数 |
| FailedCount | **Number** | 件数 |
| ArchiveUrl | **Note(RichText=FALSE, NumLines=6)** | 255字超URL対策 |
| ErrorMessage | **Note(RichText=FALSE, NumLines=6)** | 255字超エラー文対策 |
| OccurredDateTimeUtc | Text(255, ISO8601) | 記録日時 |

根拠・原文引用は`01_list_schema_evidence.md`§2参照。

## 6. 両リストの関係（Lookupなし・RunId相関）

MeetingArchiveLedgerとMeetingArchiveRunLogの間に**Lookup列は一切存在しない**（参照フローの`KnowledgePrimaryTag`のようなLookup型列は不採用）。両リストは**`RunId`列（Text）の文字列一致**のみで相関付けられる設計であり、単一フロー本体（`build/.../definition.json`）の`Compose_Ledger_Body.RunId`＝`Compose_RunLog_Body.RunId`＝`@variables('varRunId')`という同一値の書き込みによって、実行単位での紐付けが行われる。SharePoint側のリレーション機能（Lookup）に依存しないため、片方のリストのアイテム削除がもう一方に影響しない疎結合な設計になっている。

## 7. 添付ファイル設定（無効のまま・理由）

両リストとも`EnableAttachments`アクションを実行しないため、添付ファイル機能は既定の無効状態のまま維持される。理由は、単一フロー本体・本リスト作成フローのいずれにも、台帳・実行ログのリストアイテムへ添付ファイルを付与する処理が存在しないため（添付ファイル本体はSharePointドキュメントライブラリへ直接保存され、リスト側は文字列URLを記録するのみ）。既定ビューへの`Attachments`列追加（`addViewFieldAttachments`）も同じ理由で不採用。

## 8. Title列の扱い（維持・理由）

参照フローの`deactivateSPOTitle`（Title列の`Required`をfalseへ変更する処理）は不採用とし、Title列はSharePoint既定のRequired=TRUEのまま維持する。理由は、単一フロー本体の`Compose_Ledger_Body`／`Compose_LedgerFailed_Body`／`Compose_RunLog_Body`／`Compose_ErrorLog_Body`（`build/.../definition.json`実引用）がいずれも`Title`キーへ毎回値（`IdempotencyKey`、または`RunId_summary`/`RunId_error`）を設定しており、Titleを空にする経路が存在しないため。Required制約を緩める必要がなく、緩めることで得られる利点もない。

## 9. 既定ビューの列順

両リストとも既定ビューは次の順で再構築される: **LinkTitle**（先頭。タイトルをリンク付きで表示。参照フローには無かった追加要素）→ カスタム列11本（定義順、`01_list_schema_evidence.md`の列挙順）→ **Author → Editor → Created → Modified**（システム列、末尾）。`Attachments`列は追加しない（§7）。

## 10. 既存リスト・既存列がある場合の動作（2周目挙動含む）

- **リストが既存の場合**: `Create_{prefix}List`はSharePoint側で重複名エラーとなり失敗するが、`Get_{prefix}List`は`Succeeded`/`Skipped`/`Failed`/`TimedOut`のいずれでも実行される設定のため、既存リストのIdを問題なく取得し後続処理へ継続する。
- **列が既存の場合**: 列ごとの`Filter_{prefix}_<列>`（InternalName一致検索）の結果が1件以上になり、対応する`If_Create_{prefix}_<列>`の条件（`length(...)==0`）が偽となるため、`Create_{prefix}_<列>`（列作成）は実行されない。重複列は作成されない。
- **2周目実行の予測**: `Create_{prefix}List`のみFailed表示となるが、それ以外（列存在チェック11×2、ビュー再構築）はすべて1周目と同じ最終状態に収束する完全冪等動作と予測される（設計上の予測であり、実行による確認は行っていない。§17参照）。詳細は`03_implementation_design.md`§3.3。

## 11. フローの冪等性

- **列作成・既定ビュー構成**: 完全冪等（§10参照。Filter+If、およびビュー全削除→再構築という「常に同じ最終状態に収束させる」方式のため、実行回数によらず列・ビューの内容は変化しない）。
- **リスト作成自体**: 半冪等（`Create_{prefix}List`は2回目以降Failed表示になるが実害なし。参照フローから踏襲した設計であり、`03_implementation_design.md`§3.4で「正常な表示」と明記）。
- フロー全体としては、複数回実行しても最終的なSharePoint側の状態（リスト・列・ビュー）が変化しない意味での冪等性を確保している。

## 12. connectionReferenceの扱い

`connectionReferences.shared_sharepointonline`は`source="Embedded"`を維持し、`connectionName`も参照フローの実値`054920e5a92b48b6b53f62b01b3cb354`をそのまま採用した（新規に捏造していない）。理由は、`apisMap.json`（`shared_sharepointonline`→`e4f31fdf-c13c-4607-8af5-06baa431158d`）・`connectionsMap.json`（`shared_sharepointonline`→`f1e38ae6-6c4b-4670-9e29-c58312fbd2fb`）・ルート`manifest.json`の`resources`という**3ファイル間のGUIDマッピング方式を維持する**ため。これらのGUIDは参照フロー環境における実際のAPIリソース・接続インスタンスの識別子であり、同一テナント・同一SharePoint接続を前提とする別パッケージであるため、対応関係を壊さずに踏襲することが最も安全という判断による（`03_implementation_design.md`§5.4）。

## 13. フローIDおよびmanifestの変更内容

**新規採番3種**（参照フローの値を流用せず新規生成。いずれもインポート時に環境側で再採番される想定の識別子）:

| 用途 | 値 |
|---|---|
| 資産GUID（`manifest.resources`キー＝`assetPaths`＝フォルダ名の3点一致） | `7c3e50b2-91a4-4f2e-8f5a-6f1de2a9c4b7` |
| フローGUID（`definition.json`の`name`/`id`） | `d94a1b6e-3c58-47f0-b2e1-9a7c05e8f3d2` |
| `packageTelemetryId` | `5e8b2c4f-7a91-4d36-a8e0-1f6b9d3c7a25` |

**維持2種**（参照フローの実値をそのまま流用。§12参照）:

| 用途 | 値 |
|---|---|
| SharePoint APIリソースGUID | `e4f31fdf-c13c-4607-8af5-06baa431158d` |
| 接続インスタンスリソースGUID | `f1e38ae6-6c4b-4670-9e29-c58312fbd2fb`（＋`connectionName`＝`054920e5a92b48b6b53f62b01b3cb354`） |

**displayName変更**: `CreateKnowledgeList` → `CreateMeetingArchiveLists`（ルートmanifest`resources.<資産GUID>.details.displayName`および`details.displayName`トップレベルの両方）。

**匿名化**: 参照フローのルートmanifestには接続リソースの`details.displayName`が個人メールアドレス（`iihoshi-yohei@jpo.go.jp`）になっていたが、新パッケージでは汎用名`"SharePoint 接続"`に置換。`metadata.creator`は`{}`（空オブジェクト）、`details.creator`は`"N/A"`とし、参照フローに含まれていた`creator.id`/`tenantId`等の個人・テナント識別情報は一切含めていない。

## 14. 検証結果

`validate_list_definition.py`による静的検証で**0エラー・0警告**（全39検査観点）。総アクション156（トリガー除く、If内22含む）、SchemaXml22本すべてXMLパース成功・型純度確認済み、Ledger/RunLog取り違え0件、Knowledge固有トークン残存0件、コネクタ出力の`body/`欠落0件。ZIP再展開検証でも5エントリのハッシュが`source/package`・`03_repacked_extract_check`・完成ZIPの3者間で完全一致し、参照ZIPと同一の階層構造であることを確認した。詳細は`04_validation_report.md`。

## 15. 完成ZIPのパス

```
../release/CreateMeetingArchiveLists_20260717021044.zip（本フローのreleaseフォルダー）
```

サイズ7,302バイト、レガシー形式5ファイル（`manifest.json`／`Microsoft.Flow/flows/manifest.json`／`Microsoft.Flow/flows/7c3e50b2-91a4-4f2e-8f5a-6f1de2a9c4b7/{apisMap.json,connectionsMap.json,definition.json}`）。

## 16. インポート後に必要な手動設定

- **接続選択のみ**: インポート時にSharePointコネクタの接続（インポート作業者自身のアカウント）を選択し直す必要がある（ZIPには認証情報を含めていない）。
- **サイトは静的だが変更時の編集箇所**: 本フローの全`OpenApiConnection`アクション（134アクション、トップレベルのみでも67×2）は`dataset`パラメータに`https://metijapan.sharepoint.com/teams/pjteam_220400119`という**単一の静的リテラル**を使用している（単一フロー本体のPostItem制約対応とは異なり、本フローはすべて`HttpRequest`のみで動的スキーマ解決の制約はないが、参照フローに合わせて静的リテラルに統一した設計判断・`03_implementation_design.md`§5.4）。したがって保存先サイトを`pjteam_220400119`以外に変更する場合は、`build_list_package.py`の`SITE`定数を書き換えて再生成するか、インポート後にフロー編集画面で該当アクションの「サイトのアドレス」を個別に選び直す必要がある（後者は対象アクション数が多いため現実的には前者のスクリプト再生成を推奨）。

## 17. 未解決事項

1. **実環境インポート・保存・実行は未検証**（静的検証のみ。§14・`04_validation_report.md`§5参照）。
2. **`LinkTitle`の実際の表示挙動**（既定ビュー先頭でタイトルがリンク付きで表示されるか）は実機未確認。
3. **2回目実行時の`Create_{prefix}List`失敗表示**は設計上正常な挙動と位置づけているが（§10・§11）、実際にPower Automateの実行履歴上どう見えるか（全体ステータスが「成功」と表示されるか、それとも一部失敗としてアラート通知の対象になるか）は未確認。
4. テナント設定によりSharePoint RESTのレスポンス形式（`odata=verbose`/`nometadata`）や`createFieldAsXml`の応答仕様に差異がある可能性は、単一フロー本体側のPostItem関連の教訓（`SINGLE_FLOW_FACTS.md`v7「残存注意」）と同種の懸念として残る。列作成・ビュー追加が本フローの想定どおりに動くかは実環境確認が必要。
5. サイト変更時、134個のOpenApiConnectionアクションが同一の静的`dataset`を持つため、変更コストが単一フロー本体（変数化されたサイト）より高い（§16）。

## 18. Git操作を行っていないこと

本タスクの成果物はいずれもファイルシステム上への新規作成（`Write`/生成スクリプトの実行結果）のみであり、`git init`／`git add`／`git commit`／`git push`等のGit操作は一切行っていない。作業対象ディレクトリ（`migrate_chat_spo`）自体がGitリポジトリではないことも確認済みである。
