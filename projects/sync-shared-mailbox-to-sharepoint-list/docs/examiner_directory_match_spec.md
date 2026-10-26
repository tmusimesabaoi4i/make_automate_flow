# 審査官名簿との突合仕様

対象フロー: `flows/sync-mail-to-list-with-examiner-directory/`
唯一の編集元: `source/build_directory_flow.py`（`definition.json` は生成物）
オフライン検証: `tests/run_directory_match_tests.py`（**検出108件の回帰＋突合17件**）

本文から推定した審査官名を、**Teamsチャネルメンバー同期で作られた名簿**と突き合わせて、
メールアドレスとTeamsユーザーIDを取得する。検出そのものの仕様は
[examiner_detection_spec.md](examiner_detection_spec.md) を参照（本フローでも同一）。

---

## 1. 名簿リストの前提

`projects/teams-channel-member-sync/` が作成・更新するリストを読む。
**書き込みは一切しない**（検証スクリプトの検査 R1 が「名簿サイトへのRESTはGETのみ」を機械確認する）。

読む列（`$select`）:

| 内部名 | 用途 |
|---|---|
| `FullName` | 氏名。**半角スペース1つ区切りに正規化済み**（全角は半角化、`(...)`以降は除去） |
| `LastName` | 姓。最初のスペースより前。**スペースが無ければ氏名全体が入る** |
| `FirstName` | 名。スペースが無ければ空 |
| `Email` | メールアドレス。`mail` が無ければ UPN。**空になりうる** |
| `SyncKey` | **一意キー**。`userId`、無ければメンバーシップID |
| `TeamsUserId` | Entra のオブジェクトID。空になりうる |
| `MemberStatus` / `IsActive` | `在籍`/`離脱`。**離脱者も行として残る** |

### 名簿側の性質（読み取り側が前提にすること）

- **一意制約もインデックスも無い。`FullName` は一意でない**（同姓同名がありうる）
- **1つのリストに複数チャネル分のメンバーが混在しうる**（`ChannelId` で区別）
- `Email` はゲスト・外部ユーザーで空になりうる
- 離脱者は物理削除されず `IsActive = false` で残る

---

## 2. 取得のしかた

`Scope_Load_Roster` で **ループの前に1回だけ** GET する。

```
_api/web/lists(guid'{varRosterListId}')/items
  ?$select=Id,FullName,LastName,FirstName,Email,SyncKey,TeamsUserId,MemberStatus,IsActive
  &$top=5000
```

- **メール1件ごとに検索しない。** 100件のメールで100回のRESTになるため
- **`$filter` は使わない。** 2段エスケープの事故と、非インデックス列に対する
  5,000件しきい値を避ける（名簿側のフロー自身も同じ判断をしている）
- 配列変数に入れない。`body('Get_Roster_Items')?['value']` を直接参照する
  （変数化すると `Initialize` と `Set` で2アクション無駄になる）
- リストの特定は**リスト名の完全一致**（`toLower(trim(Title))`）。`GetByTitle(` は使わない

名簿リストが見つからない場合は **`ERR_ROSTER_LIST_NOT_FOUND` でメール取得前に終了**する。
設定の不備なので早く落とす（**名簿リストは作成しない**）。

---

## 3. 突合の規則

入力は `Compose_Ex_Final`（推定した審査官名）と `Compose_Ex_NameType`。
突合は `Foreach_Email` の直下（深さ4）で、**Compose と Query だけ**で行う。
コネクタを呼ばないので、突合の失敗で同期が止まることは構造的に起こらない（検査 R2）。

```
対象     = 名簿の行のうち IsActive == true      ← 在籍者のみ（利用者決定 2026-08-04）
key      = 推定名から半角スペースを除いたもの
```

| | 規則 | 判定 |
|---|---|---|
| 1 | 空白を除いた `FullName` が `key` と一致 | 1人に絞れれば `Matched` |
| 2 | 推定名が**姓のみ**のとき `LastName` が一致 | 1人に絞れれば `Matched`（`FullName` へ補完） |
| 3 | 1件以上ヒットしたが1人に絞れない | `Ambiguous`（採用しない） |
| 4 | 0件 | `NotFound` |
| 5 | 推定名が空 | `NoExaminer` |
| 6 | 名簿を読めていない | `RosterUnavailable` |

### 「1人に絞れる」の判定

**行数ではなく一意キー `SyncKey` で数える。**

```
1人 = 1件だけヒット
     または（SyncKey が空でなく、ヒットした全行の SyncKey が同じ）
```

- 同姓同名の**別人**が2行 → `SyncKey` が違うので `Ambiguous`（テスト M03）
- **同一人物**が複数チャネル分で2行 → `SyncKey` が同じなので1人（テスト M16）
- `SyncKey` が空の行が複数 → 同一性を確認できないので採用しない（テスト M17）

> 氏名で数えると「別人2名」を1人と誤認する。名簿の身元は氏名ではなく `SyncKey`。

### 空白の扱い

推定側は空白を補えないことがあり（`鵜飼和彦`）、名簿側もスペース無しの行がありうる。
**両方から空白を除いて比較する**ので、どちらの表記でも突合できる（テスト M02・M14）。

### 姓のみのときだけ名簿で補完する

`ExaminerName` 列を名簿の `FullName` で置き換えるのは、
**推定名が姓のみ（`FamilyNameOnly`）かつ `Matched`** のときだけ。
フルネームが取れているときは本文の表記を正とし、名簿の表記で上書きしない。
補完したときは診断の `completionSource` が `directory` になる。

**フルネームが取れているときに姓で引くことはしない。** 同姓の別人を拾うため（テスト M15）。

---

## 4. 列に入る値

| 内部名 | 表示名 | 値 |
|---|---|---|
| `ExaminerName` | 審査官名 | 推定名（姓のみで一意に突合できたときだけ名簿の氏名） |
| `ExaminerEmail` | 審査官メールアドレス | `Matched` のときの `Email`。**空になりうる** |
| `ExaminerTeamsUserId` | 審査官TeamsユーザーID | `Matched` のときの `TeamsUserId` |
| `ExaminerSyncKey` | 審査官同期キー | `Matched` のときの `SyncKey`（名簿のどの行か追える） |
| `ExaminerMatchedName` | 名簿上の氏名 | `Matched` のときの `FullName`（推定名との差を見る） |
| `ExaminerMatchStatus` | 名簿突合状態 | `Matched` / `Ambiguous` / `NotFound` / `NoExaminer` / `RosterUnavailable` |

突合できなくても**空文字で登録し、メール同期は止めない**。

### 診断（実行履歴）と結果JSON

`Compose_Detection_Diagnostics` に追加:
`directoryMatchStatus` / `directoryMatchedName` / `directoryEmail` / `directoryTeamsUserId` /
`directoryActiveCount` / `directoryFullNameHits` / `directoryFamilyNameHits` / `examinerNameFinal`

`warnings` に追加: `directory-email-empty` / `directory-ambiguous` / `directory-unavailable`

結果JSON: `examinerMatchedCount` / `examinerUnmatchedCount`
（分母は**審査官名を検出できた件だけ**。検出できなかった件を「突合できなかった」に数えない）

---

## 5. 既知の制限事項

| 制限 | 内容 |
|---|---|
| 名簿の件数 | `$top=5000`。**ページング未実装**。5,000件を超える名簿は取りこぼす |
| 同姓同名 | 2人以上に一致したら採用しない。`Ambiguous` として人が確認する |
| `Email` 空 | ゲスト・外部ユーザーは空になりうる。`Matched` でもアドレスが取れない（`directory-email-empty`） |
| 複数チャネル混在 | `ChannelId` では絞らない。別チャネルの同姓者が `Ambiguous` を増やす |
| 離脱者 | 在籍者のみ対象。異動前の古いメールは突合できない |
| ひらがな推定名 | 名簿に読み仮名が無いため突合しない |
| 名簿の鮮度 | `teams-channel-member-sync` は**実機未検証**。名簿自体が古い／不完全な可能性がある |
| 名簿の同期失敗 | 名簿側は想定内エラーでも「成功」で終わる設計。**古い名簿のまま突合しうる** |

---

## 6. 要実環境確認

- **インポート・保存・実行のいずれも未実施**
- 461アクションのフローが実際にインポート・保存できるか
- **2つ目のサイト（名簿）への `dataset` 指定が実機で機能するか**
  （同一接続で別サイトを参照する形。オフラインでは確認できない）
- **列処理をループ化した部分**（`Foreach_Create_Field` / `Foreach_Add_View_Field` /
  `Foreach_Verify_Field`）が実機で展開形と同じ結果になるか。
  REST の呼び方と順序は変えていないが、実行時の挙動は未検証
- 名簿リストの実在と REST の応答形（`odata=nometadata` での列名）
