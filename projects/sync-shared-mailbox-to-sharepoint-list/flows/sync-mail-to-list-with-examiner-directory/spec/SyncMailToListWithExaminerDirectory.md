# SyncMailToListWithExaminerDirectory — 審査官名簿との突合付き同期フロー

| 項目 | 値 |
|---|---|
| 論理名 | `SyncMailToListWithExaminerDirectory` |
| 表示名 | 共有メールボックスのメールをSharePointリストへ同期（審査官名・出願番号の推定＋名簿突合） |
| トリガー | 手動（`manual` = Request + Button）＋ 入力**6項目** |
| コネクタ | SharePoint / Office 365 Outlook / Content Conversion（すべて標準・既存2フローと同一） |
| アクション総数 | **461 / 500**（うち検出＋突合 156。すべて Compose / Query） |
| 変数 | 53 / 250 ｜ 最長式 6,693 / 8,192 ｜ ネスト深さ **7 / 8** |
| パッケージ | レガシー5ファイル構造・接続参照は Invoker形式＋匿名GUID |
| 静的検証 | **0 errors / 0 warnings** |
| オフラインテスト | 検出**108 / 108** ＋ 突合**17 / 17** |
| 実環境 | **未実施**（インポート・保存・実行とも未確認） |

> **`definition.json` は生成物**。修正は必ず `../source/build_directory_flow.py` を編集して再生成する。

---

## 1. 目的

`sync-mail-to-list-with-examiner-detection` と同じ検出処理に加えて、
推定した審査官名を **Teamsチャネルメンバー同期で作られた審査官名簿**と突き合わせ、
**Teams投稿に必要なメールアドレスとユーザーID**をリストへ登録する。

名簿は**読み取りだけ**。書き込みは一切行わない。

---

## 2. 既存2フローとの差分

| # | 差分 | 内容 |
|---|---|---|
| 1 | 入力 | `RosterSharePointUrl` / `RosterListName` を追加（4項目 → **6項目**） |
| 2 | 列 | 名簿突合の5列を追加（7列 → **12列**） |
| 3 | 名簿参照 | `Scope_Load_Roster` を追加。**同期先とは別のサイトでもよい**（`dataset` を分ける） |
| 4 | 突合 | `Foreach_Email` 直下に `Filter_Dir_*` / `Compose_Dir_*` を追加（深さは増やさない） |
| 5 | **列処理のループ化** | 列作成・既定ビュー・スキーマ検証を**列定義配列の Apply to each** に変更（下記） |
| 6 | GUID | 12個すべて新規採番（既存2フローとの交差0を検証スクリプトで機械確認） |

**既存2フローのファイルは1つも変更していない**（SHA-256で確認済み）。

### 列処理をループ化した理由

展開形のままだと**1列あたり12アクション**（列作成6＋スキーマ検証5＋ビュー1）かかり、
5列増やすと 491 → 551 で上限500を超える。ループ化すると**列数によらず一定**になる。

| スコープ | 展開形（7列） | ループ（12列） |
|---|---:|---:|
| `Scope_Init_List_Schema` | 51 | **14** |
| `Scope_Verify_Schema` | 51 | **22** |
| `Scope_Configure_View` | 20 | **15** |

- 列定義は `Compose_Field_Definitions`（必ず実行される `Scope_Validate_Input` に置く）
- 3つのループはすべて**並列オフ**（`repetitions = 1`）。ビューの列順を保つため
- 列の存在確認は外した。`Scope_Init_List_Schema` は `varCreatedInThisRun == true`、
  つまり**この実行で作ったばかりの空リスト**でしか動かないため
- 同リポジトリの `create_initialized_sharepoint_list` が既に同じ形を使っている

> ⚠ **要実環境確認**: 5列版は展開形のまま実機で成功している。
> ループ化は**REST の呼び方と順序を変えていない**が、実行時の挙動は未検証。

---

## 3. トリガー入力（6項目）

| 内部名 | 表示名 | 型 | 必須 |
|---|---|---|---|
| `SharePointUrl` | SharePointサイトまたはリスト一覧URL | string | ✓ |
| `ListName` | 作成するリスト名 | string | ✓ |
| `SharedMailboxAddress` | 共有メールボックスのアドレス | string | ✓ |
| `MailCount` | 取得件数（1〜100） | integer | ✓ |
| **`RosterSharePointUrl`** | **審査官名簿のSharePointサイトまたはリスト一覧URL** | string | ✓ |
| **`RosterListName`** | **審査官名簿のリスト名** | string | ✓ |

名簿URLの正規化は同期先と**同じ式**を使う（`_url_chain()` で生成。規則が2箇所で食い違わない）。

---

## 4. リストの列構成（12列）

既存7列（メッセージID／日時／送信元アドレス／件名／本文／審査官名／出願番号）に加えて:

| 表示名 | 内部名 | 型 |
|---|---|---|
| 審査官メールアドレス | `ExaminerEmail` | 1行テキスト |
| 審査官TeamsユーザーID | `ExaminerTeamsUserId` | 1行テキスト |
| 審査官同期キー | `ExaminerSyncKey` | 1行テキスト |
| 名簿上の氏名 | `ExaminerMatchedName` | 1行テキスト |
| 名簿突合状態 | `ExaminerMatchStatus` | 1行テキスト |

既定ビューの列順は上記の順。並び順は `ReceivedDateTime` 降順＋`ID` 降順。
`Title` 列は削除せず、必須解除して既定ビューから外す。

**確信度・スコア・診断は列にしない**（実行履歴と結果JSONで確認する）。

---

## 5. 審査官名・出願番号の推定

`sync-mail-to-list-with-examiner-detection` と**同一**。
仕様は [../../../docs/examiner_detection_spec.md](../../../docs/examiner_detection_spec.md)。

検出108件のテストを本フローのパッケージに対しても実行し、
**チェーンが無傷であること**を毎回確認している（`run_directory_match_tests.py` の冒頭）。

---

## 6. 名簿との突合

仕様は [../../../docs/examiner_directory_match_spec.md](../../../docs/examiner_directory_match_spec.md)。要点:

- 名簿は `Scope_Load_Roster` で**ループの前に1回だけ**取得（メール件数によらずREST 2回）
- 対象は **`IsActive = true` の在籍者のみ**
- 規則1（フルネーム一致）→ 規則2（姓のみのとき `LastName` 一致）の順
- 「1人に絞れる」は**行数ではなく一意キー `SyncKey`** で数える
- 空白は**両側から除いて**比較する
- 姓のみのときだけ名簿の氏名へ補完する（`completionSource = directory`）
- 突合できなくても空文字で登録し、**メール同期は止めない**

| 突合状態 | 意味 |
|---|---|
| `Matched` | 1人に絞れた |
| `Ambiguous` | 複数ヒットして絞れない（採用しない） |
| `NotFound` | 名簿に該当なし |
| `NoExaminer` | そもそも審査官名を検出できていない |
| `RosterUnavailable` | 名簿を読めていない |

---

## 7. エラー時の動作

既存のエラーコードに加えて:

| コード | 意味 | 動作 |
|---|---|---|
| `ERR_ROSTER_URL_EMPTY` | 名簿サイトURLが未入力 | 入力検証で終了 |
| `ERR_ROSTER_URL_INVALID` | 名簿サイトURLの形式が不正 | 入力検証で終了 |
| `ERR_ROSTER_LISTNAME_EMPTY` | 名簿リスト名が未入力 | 入力検証で終了 |
| `ERR_ROSTER_LIST_NOT_FOUND` | 名簿リストが見つからない | **メール取得前に終了**（名簿は作成しない） |

名簿リストの解決失敗は設定の不備なので早く落とす。
一方、**1件ごとの突合失敗は列に状態を書くだけ**で同期は続ける。

---

## 8. インポート方法・接続設定

1. `../release/` の中で**日時が最も新しいZIP**を使う（古いものは履歴）
2. Power Automate →「マイフロー」→「インポート」→「パッケージのインポート（レガシー）」
3. フローのインポート設定を**「新規作成として」**にする
4. **3つの接続参照**（SharePoint / Office 365 Outlook / Content Conversion）に実接続を割り当てる
5. インポート後、**フローを開いてそのまま一度保存**する（保存時にしか出ないエラーがある）
6. フローチェッカーを実行して警告0を確認する
7. まず**取得件数3件**で試験実行し、`Compose_Detection_Diagnostics` の
   `directoryMatchStatus` を実行履歴で確認する

> 名簿サイトと同期先サイトが別テナントの場合は動作しない（同じ接続で両方へアクセスする）。

### 必要な権限

- 同期先サイト: 参照＋（新規作成する場合）リスト・列・ビューの管理
- **名簿サイト: 参照のみ**（本フローは名簿へ書き込まない）
- 共有メールボックス: 読み取り（フルアクセス）

---

## 9. テスト方法

```powershell
cd D:\make_automate_flow
$f = "projects/sync-shared-mailbox-to-sharepoint-list/flows/sync-mail-to-list-with-examiner-directory"
python "$f/source/build_directory_flow.py"
python "$f/source/validate_directory_flow.py"                                            # errors 0 / warnings 0
python tools/wdl_lint.py --all .                                                         # 指摘 0
python projects/sync-shared-mailbox-to-sharepoint-list/tests/run_directory_match_tests.py  # 検出108＋突合17
python "$f/validation/extract_check.py"                                                  # errors 0
```

検出そのもののテストは `run_detection_tests.py`（既存フロー対象・108件）。

---

## 10. 既知の制約

| 制約 | 内容 |
|---|---|
| アクション数 | **461 / 500**。列はループ化したので増やしても増えないが、処理を足す余地は39 |
| 名簿の件数 | `$top=5000`。**ページング未実装**。5,000件超は取りこぼす |
| 同姓同名 | 2人以上に一致したら採用しない（`Ambiguous`） |
| `Email` 空 | ゲスト・外部ユーザーは空になりうる。`Matched` でもアドレスが取れない |
| 複数チャネル混在 | `ChannelId` では絞らない。別チャネルの同姓者が `Ambiguous` を増やす |
| 離脱者 | 在籍者のみ対象。異動前の古いメールは突合できない |
| ひらがな推定名 | 名簿に読み仮名が無いため突合しない |
| 名簿の鮮度 | `teams-channel-member-sync` は実機未検証。名簿自体が古い／不完全な可能性がある |
| テナント | 同期先と名簿が別テナントだと動作しない |

検出側の制約（スレッド深度・姓名の空白・3文字姓の表など）は
[examiner_detection_spec.md](../../../docs/examiner_detection_spec.md) §14 を参照。

## 11. 要実環境確認

- **インポート・保存・実行のいずれも未実施**
- 461アクションのフローが実際にインポート・保存できるか
- **2つ目のサイト（名簿）への `dataset` 指定が実機で機能するか**
- **列処理のループ化**が実機で展開形と同じ結果になるか（REST の呼び方と順序は不変）
- 名簿リストの REST 応答形（`odata=nometadata` での列名）
- 実データでの突合率（テストは合成データ17件）
