# 04. 検証レポート（CreateMeetingArchiveLists）

`../source/validate_list_definition.py`による静的検証の全項目・結果と、ZIP再展開検証の結果をまとめる。実環境インポート・実行は行っていない（未検証）。
作成日: 2026-07-17

## 0. 検証の位置づけ（検証済み／未検証の区別）

| 区分 | 内容 |
|---|---|
| **検証済み** | JSON構文・GUID整合・アクション参照整合・SchemaXml妥当性・REST形式・トリガー/接続参照（すべて静的解析）。ZIP再展開後のファイル同一性（ハッシュ一致）。 |
| **未検証** | Power Automate実環境へのインポート、フローチェッカー、実行（保存動作を含む）。列作成・ビュー再構築が実際のSharePointサイト`pjteam_220400119`に対して成功するかどうかは、この静的検証の対象外である。 |

「インポート成功済み」「実行確認済み」とは一切書かない。以降の結果はすべて**静的検証**の範囲であることに注意。

## 1. 静的検証スクリプトの実行結果（生出力）

実行コマンド: `python validate_list_definition.py`（対象: `../source/package/`）

```
=== CreateMeetingArchiveLists 静的検証 ===
総アクション数(トリガー除く): 156
operationId: ['HttpRequest']
SchemaXml検査数: 22 / 変数系アクション: 0 / PostItem: 0 / Foreach: 0
Ledger/RunLog取り違え: 0件
GUID3点一致: assetGuid=7c3e50b2-91a4-4f2e-8f5a-6f1de2a9c4b7

=== ERRORS ===
(0 errors)
=== WARNINGS ===
(0 warnings)
```

終了コード0（`errors`が空のため`sys.exit(1 if errors else 0)`により正常終了）。

## 2. 検査項目一覧（スクリプト内セクション対応）

| # | セクション（スクリプト内） | 検査内容 | 期待値 | 結果 |
|---|---|---|---|---|
| 1 | JSON検証(5ファイル)＋GUID3点一致 | `manifest.json`（ルート）／`Microsoft.Flow/flows/manifest.json`／`definition.json`／`apisMap.json`／`connectionsMap.json`の5ファイルがすべてJSONとしてパース可能 | パース成功 | OK（例外なし） |
| 2 | 同上 | `assetPaths`が1件のみ | 1件 | OK |
| 3 | 同上 | ルートmanifestの`resources`中`type=="Microsoft.Flow/flows"`のキーが`assetPaths`の値と一致 | 一致 | OK（`7c3e50b2-91a4-4f2e-8f5a-6f1de2a9c4b7`） |
| 4 | 同上 | `assetPaths`のGUID名フォルダが実在 | 実在 | OK |
| 5 | 同上 | `apisMap`/`connectionsMap`の各GUIDがルートmanifestの`resources`に存在 | 全件存在 | OK |
| 6 | 同上 | フローの`dependsOn`に`apisMap`/`connectionsMap`の全GUIDが含まれる | 含まれる | OK |
| 7 | アクション参照検証 | 全`runAfter`の参照先が同一階層（同じ`actions`辞書内）に実在 | 参照先0件欠落 | OK |
| 8 | 同上 | `runAfter`のステータス値が`Succeeded`/`Failed`/`Skipped`/`TimedOut`のみ | 不正値0件 | OK |
| 9 | 同上 | アクション名の重複なし | 重複0件 | OK（156件すべて一意） |
| 10 | 同上 | 変数系アクション（`SetVariable`/`InitializeVariable`/`AppendToArrayVariable`/`AppendToStringVariable`）が存在しないこと | 0件（本フローはCompose統一設計のため） | OK（0件） |
| 11 | 同上 | `PostItem`（`operationId`）が存在しないこと | 0件（保存検証で失敗するため） | OK（0件） |
| 12 | 同上 | `outputs('X')`/`body('X')`で参照される`X`が実在アクション名であること | 未定義参照0件 | OK |
| 13 | 同上 | 式文字列内でのネスト`@`（`@{...}`以外の位置での`@`）がないこと | 0件 | OK |
| 14 | REST検証 | Knowledge固有トークン（`tmplist`/`KnowledgeTag`/`KnowledgeTitle`/`KnowledgePrimaryTag`/`KnowledgeSummary`/`KnowledgeBody`/`varTagList`/`addRowPrimaryTag`/`CreateKnowledgeList`/`getTagList`）の残存 | 0件 | OK（0件） |
| 15 | 同上 | 各`OpenApiConnection`に`dataset`/`method`/`uri`が揃っている | 欠落0件 | OK |
| 16 | 同上 | `parameters/headers`がオブジェクト型であること | 全件オブジェクト | OK |
| 17 | 同上 | `method=POST`のアクションに`body`が存在（`removeAllViewFields`系を除く） | 欠落0件 | OK |
| 18 | 同上 | `method=GET`のアクションに`body`が存在しない | 違反0件 | OK |
| 19 | 同上 | `X-HTTP-Method=MERGE`のヘッダーに`IF-MATCH:*`が伴う | 違反0件 | OK |
| 20 | 同上 | `__metadata`を含むボディの`Content-Type`が`verbose`であること | 違反0件 | OK |
| 21 | 同上 | Ledger系アクションがRunLog側の`Compose`を参照（またはその逆）していないこと（取り違え検査） | 0件 | OK（0件） |
| 22 | SchemaXml/RESTボディ妥当性 | 全`parameters/body`（JSON文字列）が`json.loads`可能 | 22件（列作成分）全件パース成功 | OK |
| 23 | 同上 | `SchemaXml`が妥当なXML（`ET.fromstring`成功） | 22件全件成功 | OK |
| 24 | 同上 | `SchemaXml`のルート要素が`Field`タグ | 22件全件一致 | OK |
| 25 | 同上 | `Name`属性がASCII英数字のみ（`[A-Za-z][A-Za-z0-9]*`） | 22件全件一致 | OK |
| 26 | 同上 | アクション名に列名（`Name`属性値）が含まれる（取り違え防止） | 22件全件一致 | OK |
| 27 | 同上 | 期待列一覧（Ledger11列・RunLog11列）に対応する`Create_{prefix}_<列>`アクションが漏れなく存在 | 欠落0件 | OK |
| 28 | 同上 | `SchemaXml`検査数が22（Ledger11＋RunLog11） | 22 | OK |
| 29 | 同上 | 生成された列型が期待定義（`EXPECT`辞書）と一致 | 不一致0件 | OK |
| 30 | 追加検査（コネクタ出力） | `outputs('OpenApiConnectionアクション名')?['プロパティ']`が`body`以外を参照していないこと（封筒問題の再発防止） | 違反0件 | OK |
| 31 | 追加検査（SchemaXml純度） | `SchemaXml`の`DisplayName`と`Name`が一致 | 不一致0件 | OK |
| 32 | 同上 | `Number`型に`MaxLength`/`RichText`/`RichTextMode`/`NumLines`等の異型属性がない | 違反0件 | OK |
| 33 | 同上 | `Text`型に`RichText`/`RichTextMode`/`NumLines`等の異型属性がない | 違反0件 | OK |
| 34 | 同上 | `Note`型に`MaxLength`属性がない | 違反0件 | OK |
| 35 | 追加検査（If式形状） | 全`If`の`expression`が`and`+`equals`+`length(...)`の実績形式であること | 22件全件一致 | OK |
| 36 | 追加検査（dataset一致） | 全アクションの`dataset`が単一の値（サイトURL）に統一されていること | 1種のみ（`https://metijapan.sharepoint.com/teams/pjteam_220400119`） | OK |
| 37 | トリガー・接続参照 | トリガーが`manual`（`kind=Button`）のみ | 一致 | OK |
| 38 | 同上 | `connectionReferences`が`shared_sharepointonline`のみ | 一致 | OK |
| 39 | 同上 | 式中で使用される接続名（`connectionName`）が`connectionReferences`に定義されている | 未定義0件 | OK |

**総合結果: 0エラー・0警告**（全39観点）。

## 3. 主要指標（機械集計）

| 指標 | 値 |
|---|---|
| 総アクション数（トリガー除く。If内22含む） | 156 |
| トップレベルアクション数 | 134 |
| operationId種別 | `HttpRequest`のみ（1種） |
| SchemaXml検査数 | 22（Ledger11＋RunLog11） |
| 変数系アクション（SetVariable等） | 0 |
| PostItem | 0 |
| Foreach | 0 |
| Ledger/RunLog取り違え | 0件 |
| GUID3点一致 | assetGuid=`7c3e50b2-91a4-4f2e-8f5a-6f1de2a9c4b7`（manifest resourcesキー＝assetPaths＝フォルダ名） |

## 4. ZIP再展開検証

対象ZIP: `../release/CreateMeetingArchiveLists_20260717021044.zip`（7,302バイト）

| 検証項目 | 結果 |
|---|---|
| エントリ数 | **5件**（`manifest.json`／`Microsoft.Flow/flows/manifest.json`／`Microsoft.Flow/flows/7c3e50b2-.../apisMap.json`／`connectionsMap.json`／`definition.json`） |
| ハッシュ一致（ZIP内容 vs `../source/package/`） | **一致**（SHA-256、5ファイル全件） |
| ハッシュ一致（ZIP内容 vs `03_repacked_extract_check/`再展開結果） | **一致**（SHA-256、5ファイル全件） |
| 参照ZIP（`CreateKnowledgeList_20260716161116.zip`）と同一階層構造か | **同一**（`manifest.json`ルート直下＋`Microsoft.Flow/flows/manifest.json`＋`Microsoft.Flow/flows/<GUID>/{apisMap.json,connectionsMap.json,definition.json}`の5パス構成が一致。GUID値のみ異なる） |
| 混入ファイルの有無（`__MACOSX/`・`.DS_Store`等） | **なし**（5エントリ以外に何も含まれない） |
| Knowledge固有トークンの残存 | **0件**（§2 検査項目14と同一結果） |

## 5. 未検証事項（明記）

以下は本レポートの対象外であり、**実環境での確認が必要**:

1. Power Automate「パッケージのインポート(レガシー)」からの実際のインポート可否。
2. インポート後のSharePoint接続選択・保存（フローチェッカー含む）。
3. `pjteam_220400119`サイトに対する実際のリスト作成・列作成・既定ビュー再構築の実行結果。
4. 2回目実行時の冪等動作（§3.3設計予測どおりに列重複が起きないか）は**設計上の予測**であり、実行による確認は行っていない。
5. `LinkTitle`の`AddViewField`が実際に「タイトル（リンク付き）」として表示されるかどうかの実機確認。

これらは`05_implementation_report.md`「17. 未解決事項」にも記載する。


---

## 追補: アーカイブフローv8との互換性突合（2026-07-17・機械検証）

作る側（本フロー definition.json）と使う側（アーカイブフローv8 definition.json）を
スクリプト（../../../check_compat.py）で突合した結果、**完全互換・不一致0件**。

| # | 観点 | 結果 |
|---|---|---|
| 1 | リスト名（MeetingArchiveLedger / MeetingArchiveRunLog） | 一致 |
| 2 | サイト（作成先=pjteam_220400119 ／ 使う側 varListSiteAddress・REST4のdataset） | 全一致（ファイル保存系のみmROOM=意図どおり） |
| 3 | 書き込み先リスト変数の対応（台帳2→varLedgerList／ログ2→varRunLogList） | 取り違えなし |
| 4 | 書き込み列⊆作成列（Ledger 12/12・RunLog 12/12。Title含む） | 未作成列への書き込みなし |
| 5 | $filter列（IdempotencyKey/Status）・既存流用の読み取り列（SavedFileName/SavedFileUrl） | 全て作成される |
| 6 | $filter対象列の型（Note型は$filter不可） | 両方Text型でOK |
| 7 | 数値書き込み4列（MeetingCount/SavedCount/SkippedCount/FailedCount） | 全てNumber型でOK |
| 8 | 空文字が書き込まれ得る6列のRequired=FALSE | 全てFALSEでOK |
| 9 | Title供給（既定必須列への書き込み） | 両リストとも供給あり |

※本突合は定義ファイル間の静的検証であり、実環境での動作は未検証。
