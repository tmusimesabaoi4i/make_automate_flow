# 2026-07リポジトリ再編 調査記録

## 1. 再編日と目的

再編日: **2026-07-17**。

目的は次の3点。
1. 開発ソース（build_*.py/validate_*.py等の生成・検証スクリプトや事実シート）がエージェントのセッション一時領域（scratchpad）にしか存在しない状態を解消し、リポジトリ本体に永続化する。
2. `dist`/`build`/`03_repacked`等の意味が名前だけでは判別できないディレクトリ名を、工程（source/spec/validation/release）が分かる名前に揃える。
3. 案件固有資料（`projects/migrate-chat-spo/`）と共通知識（`handbook/`）を分離し、原本・生成物・検証記録・旧版控えの混在を整理する。

## 2. 再編前の主な問題点

- **開発ソースがセッション一時領域のみに存在**: build_package.py/validate_definition.py/build_list_package.py/validate_list_definition.py/check_compat.py/tools/gen_outline.py等、パッケージを生成・検証する実体のスクリプトがリポジトリ内になく、エージェントの一時scratchpadにしか無かった。セッション終了で消失する経路依存の状態だった。
- **`dist`/`build`等の意味不明瞭な名称**: `migrate_chat_spo/build`・`migrate_chat_spo/dist`・`migrate_chat_spo/dist_make_list`・`dist_extract_check`・`dist_make_list_extract_check`のように類似名が並び、どれが「生成元（source）」「検証用展開（extract check）」「配布物（release）」なのか名前から判別できなかった。`00_`〜`05_`の連番接頭辞も、フォルダをまたいで意味が一貫していなかった。
- **原本・生成物・検証記録の混在**: 参照用の実働サンプルZIP（原本）、そこから生成した作業パッケージ、検証用の再展開コピー、検証レポートが同じ階層に並び、どれが変更してよい生成物でどれが変更してはいけない原本かが構造から読み取れなかった。
- **`dist_extract_check`=旧definition版の取り残し**: 単一フロー本体（archive-meetings）の`dist_extract_check`は、現行の`source/package`より古い版のdefinition（`fcca0e31-...`GUID）を展開検証した記録であり、最新版ではない旧版が最新版と同じ階層に残っていた。
- **`03_repacked_extract_check`=完全コピー**: リスト作成フロー（provision-archive-lists）側の`03_repacked_extract_check`は、`02_working_package`を再パック→再展開して得たハッシュ一致確認用のコピーであり、内容は`02_working_package`と完全に同一。検証目的の一時コピーが恒久資料と同じ階層に置かれ、どちらが正典か分かりにくかった。

## 3. 旧→新 対応表

以下はscratchpad上の`move_map.json`（全92件）をディレクトリ単位でまとめた対応表。単発ファイル（README.mdや`dist/`直下の2ファイル等）は個別に記載する。**`move_map.json`自体はセッション一時領域のファイルであり本再編後は保持されないため、この表が唯一の恒久的な記録である**。以降、`_legacy`内文書やコード中に旧パス（`migrate_chat_spo/...`・ルート直下の`rules/`等）の記述が残っている場合は、この表で新パスに読み替えること。

| # | 旧パス（配下件数） | 新パス | 備考 |
|---|---|---|---|
| 1 | `README.md`（1） | `README.md` | 変更なし・ルート据え置き |
| 2 | `rules/*.md`（9） | `handbook/rules/*.md` | 同名 |
| 3 | `knowledge/*.md`（7） | `handbook/knowledge/*.md` | 同名 |
| 4 | `checklists/*.md`（4） | `handbook/checklists/*.md` | 同名 |
| 5 | `templates/*`（5） | `handbook/templates/*` | 同名 |
| 6 | `migrate_chat_spo/{Get Message Replies.txt, Get_Source_File_Content.txt, Create_Error_Log.txt}`（3） | `projects/migrate-chat-spo/flows/archive-meetings/validation/run-evidence/` | 同名 |
| 7 | `migrate_chat_spo/{tmp_20260716051507.zip, create_meeting_list_sample_20260716105612.zip, CreateKnowledgeList_20260716161116.zip}`（3） | `projects/migrate-chat-spo/references/raw/` | 同名。原本（§6参照） |
| 8 | `migrate_chat_spo/sample_extracted_ref/**`（5） | `projects/migrate-chat-spo/references/extracted/sample_extracted_ref/**` | 同名 |
| 9 | `migrate_chat_spo/create_meeting_list_sample_ref/**`（5） | `projects/migrate-chat-spo/references/extracted/create_meeting_list_sample_ref/**` | 同名 |
| 10 | `migrate_chat_spo/dist_make_list_extract_check/00_reference_original/**`（5） | `projects/migrate-chat-spo/references/extracted/reference_original/**` | `00_`接頭辞を除去 |
| 11 | `migrate_chat_spo/build/**`（5） | `projects/migrate-chat-spo/flows/archive-meetings/source/package/**` | 同名。「生成元パッケージ」であることを`source/package`で明示 |
| 12 | `migrate_chat_spo/dist/PA_Migrate_Teams_Meeting_Archive_To_SPO.zip`（1） | `projects/migrate-chat-spo/flows/archive-meetings/release/PA_Migrate_Teams_Meeting_Archive_To_SPO_20260717144000.zip` | 日時サフィックス付与 |
| 13 | `migrate_chat_spo/dist/package_validation_report.txt`（1） | `projects/migrate-chat-spo/flows/archive-meetings/validation/package_validation_report.txt` | 同名 |
| 14 | `migrate_chat_spo/doc/{Teams課内会議アーカイブ自動化_仕様書.docx, power_automate_cloud_flow_implementation_guide.md, power_automate_import_guide.md}`（3） | `projects/migrate-chat-spo/flows/archive-meetings/spec/` | 同名。単一フロー本体の仕様書群 |
| 15 | `migrate_chat_spo/doc/{sample_export_analysis.md, official_reference_findings.md}`（2） | `projects/migrate-chat-spo/references/` | 同名。案件横断の参照調査資料のため`references/`直下へ |
| 16 | `migrate_chat_spo/flow/PA_Migrate_Teams_Meeting_Archive_To_SPO.txt`（1） | `projects/migrate-chat-spo/flows/archive-meetings/spec/PA_Migrate_Teams_Meeting_Archive_To_SPO.txt` | 同名 |
| 17 | `migrate_chat_spo/dist_make_list_extract_check/{01_list_schema_evidence.md, 02_reference_flow_action_map.md, 03_implementation_design.md}`（3） | `projects/migrate-chat-spo/flows/provision-archive-lists/spec/` | 連番接頭辞（01/02/03）を除去 |
| 18 | `migrate_chat_spo/dist_make_list_extract_check/01_reference_analysis/reference_notes.md`（1） | `projects/migrate-chat-spo/references/reference_notes.md` | 案件横断の参照分析のため`references/`直下へ |
| 19 | `migrate_chat_spo/dist_make_list_extract_check/02_working_package/**`（5） | `projects/migrate-chat-spo/flows/provision-archive-lists/source/package/**` | `02_`接頭辞を除去し「生成元パッケージ」を`source/package`で明示 |
| 20 | `migrate_chat_spo/dist_make_list_extract_check/{04_validation_report.md, 05_implementation_report.md}`（2） | `projects/migrate-chat-spo/flows/provision-archive-lists/validation/` | 連番接頭辞（04/05）を除去 |
| 21 | `migrate_chat_spo/dist_make_list/CreateMeetingArchiveLists_20260717021044.zip`（1） | `projects/migrate-chat-spo/flows/provision-archive-lists/release/CreateMeetingArchiveLists_20260717021044.zip` | 同名 |
| 22 | `migrate_chat_spo/flow/_archive_multiflow/**`（10: `00_overview.txt`〜`08_error_log_and_ledger.txt`＋`README.txt`） | `projects/migrate-chat-spo/_legacy/multiflow_design/**` | 同名。旧5フロー構成設計の退避資料（案件内`_legacy`） |
| 23 | `migrate_chat_spo/dist_extract_check/**`（5） | `_legacy/dist_extract_check/**` | 同名。旧definition版の展開検証（トップレベル`_legacy`。§5参照） |
| 24 | `migrate_chat_spo/dist_make_list_extract_check/03_repacked_extract_check/**`（5） | `_legacy/repacked_extract_check/**` | `03_`接頭辞を除去。再パック検証用コピー（トップレベル`_legacy`。§5参照） |

件数合計: 3+3+3+3+3+3+3+5+5+5+5+1+1+3+2+1+3+1+5+2+1+10+5+5 は表記ゆれを避けるため上表の「配下件数」列を合計する形で検証済み＝**92件**（`move_map.json`記録件数と一致）。

## 4. scratchpadからの取り込み（rescue）13件と、取り込まなかった一回性スクリプト

### 4.1 恒久化のため取り込んだ13件（新パス。`rescued_hashes.json`のキーと一致）
1. `projects/migrate-chat-spo/flows/archive-meetings/source/build_package.py`
2. `projects/migrate-chat-spo/flows/archive-meetings/source/validate_definition.py`
3. `projects/migrate-chat-spo/flows/provision-archive-lists/source/build_list_package.py`
4. `projects/migrate-chat-spo/flows/provision-archive-lists/source/validate_list_definition.py`
5. `projects/migrate-chat-spo/check_compat.py`
6. `tools/gen_outline.py`
7. `projects/migrate-chat-spo/flows/archive-meetings/spec/SINGLE_FLOW_FACTS.md`
8. `projects/migrate-chat-spo/flows/archive-meetings/validation/action_outline.txt`
9. `projects/migrate-chat-spo/flows/archive-meetings/validation/extract_check.py`
10. `projects/migrate-chat-spo/flows/archive-meetings/validation/compare_outline.py`
11. `projects/migrate-chat-spo/references/extracted/sample2_definition_pretty.json`
12. `projects/migrate-chat-spo/_legacy/CANONICAL_REFERENCE.md`
13. `projects/migrate-chat-spo/_legacy/knowledge_base_brief.md`

上記のうち7・8・11は`projects/migrate-chat-spo/_legacy/knowledge_base_brief.md`（旧: scratchpad上のブリーフ）が参照ファイルとして名指ししていたため、ブリーフ自体の参照先を永続化する目的でも救出が必要だった。12・13は「なぜ他の資料がこの形になったか」の来歴そのものであり、削除すると再編後に経緯が追えなくなるため救出した。

### 4.2 取り込まなかった一回性スクリプト・中間生成物（概要と不採用理由）
scratchpad上には上記13件以外にも多数のファイルが残っていたが、いずれも再利用性・恒久性が無いため取り込まなかった。**これらのファイル自体は再編後にscratchpad側で参照できなくなるため、以下は残存していたファイル名からの分類であり、スクリプト内部の詳細な処理内容までは本記録の対象外。**

- **`transform_v8.py` / `v7_stage1.py` / `v7_stage2.py` / `v7_verify.py` / `renumber.py` / `PA_v7_original.txt` / `PA_v8_draft.txt` / `combined_v6.txt` / `v2_ordered_actions.txt`**: フロー設計をv2→v6→v7→v8と反復した際の中間ドラフト・変換・検証スクリプト。最終的に検証済みの`source/package/`配下のdefinition.jsonに収束しており、中間版は最終成果物に置き換えられ役目を終えている。
- **`inspect.py` / `inspect1.py`〜`inspect4.py`**: 実働サンプルの構造をその場で確認するための使い捨て調査スクリプト。恒久ツール化されたのは救出済みの`extract_check.py`/`compare_outline.py`のみで、他は一過性の問いに答えるためだけのもの。
- **`audit.py` / `audit2.py`〜`audit5.py`**: 特定バグ（コネクタ出力`body/`欠落、`PostItem`の`item`欠落等）を洗い出すための一回性監査スクリプト。発見結果はすべて`handbook/knowledge/error_catalog.md`に文章として恒久化済みであり、スクリプト自体を保持する必要性が無い。
- **`analysis2/analyze.py` / `analyze2.py` / `out2.txt`**: 参照フロー解析の試行錯誤。成果は`references/reference_notes.md`等の分析文書に集約済み。
- **`verify.py` / `verify_final.py` / `verify_result.txt` / `validate_output.txt` / `enc_check.txt` / `enc_check2.txt` / `dup_check.txt` / `trigger_anon_report.txt` / `work_actions_dump.txt` / `ref_actions_dump.txt` / `compose_bodies.txt` / `action_analysis.json` / `build_manifest_pretty.json` / `ref_def_pretty.json`**: 検証・突合作業中の一時ダンプ・出力キャプチャ。結論は`validation_report.md`/`implementation_report.md`/`package_validation_report.txt`/`error_catalog.md`に反映済み。
- **`stage1_output.txt` / `stage2_output.txt` / `section1_report.txt` / `full_report.txt` / `p1_front.txt`〜`p6_tail.txt`**: 長文資料を分割して組み立てる際の断片出力。最終成果物（spec配下の各文書）に統合済みのため断片自体は不要。
- **`extract_dist/` / `extract_ref/` / `spec_extracted/`**: ZIP/DOCXをその場展開して中身を覗くための一時作業ディレクトリ。恒久的な展開結果は`references/extracted/`配下（表§3の8〜10行目）に別途保存済み。
- **`reorg_step1_3.py` / `reorg_step4_patch.py` / `reorg_step5_test.py` / `reorg_step6_links.py` / `reorg_step7_apply.py` / `reorg_step7_scan.py` / `reorg_step10_verify.py`**: 本再編作業そのものを実行するための一回性スクリプト群。再編は今回限りの操作であり再利用対象ではないため、恒久化の対象は成果物である`move_map.json`/`rescued_hashes.json`/`originals_md5.json`の内容（本記録に転記済み）とし、スクリプト自体は不採用とした。

## 5. `_legacy`保存物とその理由

| 保存物 | 場所 | 保存理由 |
|---|---|---|
| `dist_extract_check` | `_legacy/dist_extract_check/`（トップレベル） | 単一フロー本体の**旧definition版**（`fcca0e31-...`）の展開検証記録。現行`source/package`より古く、最新資料と混同させないため退避 |
| `repacked_extract_check` | `_legacy/repacked_extract_check/`（トップレベル。旧`03_repacked_extract_check`） | `provision-archive-lists`の**再パック検証コピー**（`02_working_package`と内容完全一致）。検証済みの証跡として保持するが恒久資料本体とは区別 |
| `CANONICAL_REFERENCE.md` | `projects/migrate-chat-spo/_legacy/` | **旧5フロー構成期の正典**。単一フロー構成へ移行する前の設計方針・定数一覧で、現行の正典（`flows/archive-meetings/spec/`配下）とは方針が異なるため参照専用として退避 |
| `knowledge_base_brief.md` | `projects/migrate-chat-spo/_legacy/` | `handbook/`配下の共通知識を書き起こした際の**出所記録（ブリーフ）**。どの一次資料から何を抽出したかの来歴を保持する |
| `pre_reorg_snapshot_20260717.zip` | `_legacy/pre_reorg_snapshot_20260717.zip`（本リポジトリ内） | 再編直前の全92ファイルの**ロールバック手段**。一時領域（scratchpad）はセッションで消滅するため、唯一のロールバック手段として本リポジトリの`_legacy/`へ恒久配置した（524,682バイト） |

`projects/migrate-chat-spo/_legacy/multiflow_design/`（表§3の22行目）も同様に案件内`_legacy`に退避した旧設計資料だが、対応する旧パスは表§3にすでに記載済みのため本節では重複記載しない。

## 6. 原本4点のMD5（不変性の記録）

再編（移動・改名）によって内容が変化していないことを保証するため、`originals_md5.json`に記録されたハッシュ値と、再編後の新パスでの実測値が一致することを本記録作成時点で確認済み。

| 新パス | MD5 |
|---|---|
| `projects/migrate-chat-spo/references/raw/tmp_20260716051507.zip` | `f2b0ffc1e4dd7ad08dff20797deacaa7` |
| `projects/migrate-chat-spo/references/raw/create_meeting_list_sample_20260716105612.zip` | `5c3df379f96fbad1ab50f4d1edfd3783` |
| `projects/migrate-chat-spo/references/raw/CreateKnowledgeList_20260716161116.zip` | `2209522ad8ff3dd2f3d9ef52b36825f2` |
| `projects/migrate-chat-spo/flows/archive-meetings/spec/Teams課内会議アーカイブ自動化_仕様書.docx` | `13aa7e5781f9c9f6ca5061b49149f4a6` |

以上4点は案件の一次原本（実働サンプルZIP3点・仕様書1点）であり、以後の作業では内容を書き換えず、必要な変更は複製（`source/`配下の生成物）側で行うこと。

## 追補: 2026-07-24 の references 再配置（本記録以後の変更）

本記録は 2026-07-17 時点の再編を記録したものである。その後、**2026-07-24 に `references/` をリポジトリ直下へ移動**した。
上表・上記ハッシュ台帳の `projects/migrate-chat-spo/references/...` というパスは、以後**次のように読み替えること**。

| 旧パス（本記録の表記） | 新パス（2026-07-24 以降） |
|---|---|
| `projects/migrate-chat-spo/references/raw/**` | `references/raw/**` |
| `projects/migrate-chat-spo/references/extracted/**` | `references/extracted/**` |
| `projects/migrate-chat-spo/references/{official_reference_findings,reference_notes,sample_export_analysis}.md` | `references/*.md` |

移動理由: 参照サンプルは migrate-chat-spo 案件固有ではなく**案件をまたいで参照される**ため
（実際に teams_post_url_flows・create_initialized_sharepoint_list の両案件が参照している）。

**内容が変化していないことを確認済み**（2026-07-24 実測。本記録§ハッシュ台帳の値と一致）。

| 新パス | MD5 | 判定 |
|---|---|---|
| `references/raw/tmp_20260716051507.zip` | `f2b0ffc1e4dd7ad08dff20797deacaa7` | 一致 |
| `references/raw/create_meeting_list_sample_20260716105612.zip` | `5c3df379f96fbad1ab50f4d1edfd3783` | 一致 |
| `references/raw/CreateKnowledgeList_20260716161116.zip` | `2209522ad8ff3dd2f3d9ef52b36825f2` | 一致 |

あわせて**新規の参照原本2点が追加**された（実環境からのエクスポート。2026-07-24）。

| 新規パス | MD5 | 内容 |
|---|---|---|
| `references/raw/test_flow_20260724121852.zip` | `97617c91bc25b455f2a3e1ed725995b4` | 最小構成・**接続なし**の実エクスポート（手動トリガー＋Compose 1件） |
| `references/raw/test_scheduled_flow_20260724121802.zip` | `f7e7117087a6b70df52de6a868ef67dc` | **Recurrence（スケジュール）トリガー**の実エクスポート |

いずれも一次原本として扱い、**編集・上書き禁止**。参考点は
[../handbook/knowledge/sample_flow_reference_index.md](../handbook/knowledge/sample_flow_reference_index.md) に登録済み。

## 既知の残存事項（無害）

- `migrate_chat_spo/`（**空ディレクトリの殻のみ・0ファイル**）: 再編を実行したセッションのプロセスが
  このディレクトリを作業ディレクトリとして保持していたため、セッション中は削除できなかった。
  中身はすべて新構成へ移動済み（削除前に全ファイルをハッシュ台帳と照合し一致を確認したうえで削除）。
  セッション終了後にエクスプローラーで削除するか、PowerShellで
  `Remove-Item -LiteralPath 'C:/Users/yohei/OneDrive/ドキュメント/make_automate_flow/migrate_chat_spo' -Recurse -Force`
  を実行すれば消える。
