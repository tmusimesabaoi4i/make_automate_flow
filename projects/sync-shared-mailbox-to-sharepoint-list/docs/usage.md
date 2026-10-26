# 使い方

## 1. できること・しないこと

| する | しない |
|---|---|
| 同名リストが無いときだけ新規作成する | 既存リストの削除・上書き・改名 |
| 新規リストに業務用5列と既定ビュー（日時降順）を設定する | 既存リストの列・ビュー・設定の変更 |
| 共有メールボックスの最新メールを取得する | メールの既読化・移動・削除・フラグ・送信 |
| 同じメッセージIDのアイテムがあれば更新する | 同じメールを二重に登録する |
| 本文をプレーンテキストにして保存する | HTMLのまま保存する／`Body Preview` だけを保存する |
| 上限を超えた件数指定を実行前に拒否する | 指定件数を黙って切り捨てる |

---

## 2. 入力

| 表示名 | 説明 | 例 |
|---|---|---|
| SharePointサイトまたはリスト一覧URL | サイトURL・「サイトのコンテンツ」・`viewlsts.aspx` のいずれでも可 | `https://{tenant}.sharepoint.com/sites/{siteName}` |
| 作成するリスト名 | 前後の空白は自動で除去。同名があればそのリストを使う | `メール台帳` |
| 共有メールボックスのアドレス | 監視対象の共有メールボックス | `shared-mailbox@{tenant}.example.com` |
| 取得件数 | **1〜100**の整数 | `20` |

### URLはどれを貼ってもよい

次のいずれも同じサイトURLに正規化される。

```text
https://{tenant}.sharepoint.com/sites/{siteName}
https://{tenant}.sharepoint.com/sites/{siteName}/
https://{tenant}.sharepoint.com/sites/{siteName}/_layouts/15/viewlsts.aspx
https://{tenant}.sharepoint.com/sites/{siteName}/_layouts/15/viewlsts.aspx?view=14
https://{tenant}.sharepoint.com/sites/{siteName}/_Layouts/15/viewlsts.aspx#top
    ↓ すべて
https://{tenant}.sharepoint.com/sites/{siteName}
```

**貼れないURL**: 個別リストのビューURL（`.../Lists/{listName}/AllItems.aspx`）。
サイトURLとして切り出せず、実行時に「サイトが見つかりません」で失敗する。
サイトのトップページか「サイトのコンテンツ」のURLを使う。詳細は
[url_parsing_spec.md](url_parsing_spec.md) §2。

### URLに含まれるリスト名は使われない

リスト名は「作成するリスト名」入力だけから決まる。URLに含まれるリスト名は採用しない。

---

## 3. 実行方法

1. Power Automate →「マイフロー」→ 対象フローを開く
2. 「**実行**」→ 4項目を入力 →「実行」
3. 「フローの実行が正常に開始されました」と出たら、実行履歴で結果を見る

初めて実行するときは**取得件数3件**から始める。

---

## 4. 結果の確認

実行履歴を開き、いちばん下の `Scope_Finalize` → `Compose_Flow_Output` の「出力」を見る。

```json
{
  "success": true,
  "status": "Created",
  "resultObject": {
    "listCreated": true,
    "listUrl": "https://{tenant}.sharepoint.com/sites/{siteName}/Lists/メール台帳",
    "requestedCount": 20,
    "fetchedCount": 17,
    "createdCount": 15,
    "updatedCount": 2,
    "duplicateCount": 0,
    "failedCount": 0,
    "truncatedCount": 0
  }
}
```

| 見るところ | 意味 |
|---|---|
| `status` | `Created`＝リストを作った / `Existing`＝既存リストを使った / `Error`＝失敗 |
| `listUrl` | 作成・使用したリストのURL。そのまま開ける |
| `requestedCount` vs `fetchedCount` | 差があるのは「メールがその件数だけ無かった」だけ。異常ではない |
| `createdCount` / `updatedCount` | 新規登録／更新の件数 |
| `duplicateCount` | 同じメッセージIDが2件以上あって**書き込みを見送った**件数 |
| `failedCount` | 件単位で失敗した件数。`itemErrors[]` に理由が入る |
| `truncatedCount` | 本文が長すぎて切り詰めた件数。`truncatedItems[]` に記録 |

失敗時は `resultObject.error.code` / `.message` / `.stage` を見る。
一覧は [json_schema.md](json_schema.md)。

---

## 5. 作成されたリストの確認

`listUrl` を開く。

- 列は左から **メッセージID / 日時 / 送信元アドレス / 件名 / 本文**
- 並び順は**日時の降順**（最新のメールが上）
- 「タイトル」列は既定ビューから外してあるが、**削除はしていない**（設定→列 に残っている）

---

## 6. 同じ入力で2回目を実行すると

- リストは**作り直されない**（`status` が `Existing`）
- 既に登録済みのメールは**更新**される（`updatedCount` が増える）
- **アイテム数は増えない**

メールの内容が変わることは通常ないが、「取得できる最新の情報へ更新する」動作になっている（指示§14）。

---

## 7. 既存のリストを使いたいとき

同名のリストが既にある場合、**リスト自体は一切変更されない**。
次の5列が**内部名**で存在し、型が互換であるときだけ同期が行われる。

| 内部名 | 型 |
|---|---|
| `MessageId` | 1行テキスト |
| `ReceivedDateTime` | 日付と時刻 |
| `SenderAddress` | 1行テキスト |
| `Subject` | 1行テキスト |
| `BodyPlainText` | 複数行テキスト |

条件を満たさない場合は `ERR_SCHEMA_INCOMPATIBLE` で安全に終了し、
`missingFields` / `incompatibleFields` に何が足りないかが入る。
**リストを勝手に直すことはしない。** 手で列を追加するか、別のリスト名を指定する。

> 表示名は自由に変更してよい。判定は内部名で行うため、
> 「メッセージID」を「Message ID」に変えても処理は壊れない。

---

## 8. 後続処理で使う

結果は Compose のため、そのまま参照できる。

```text
成功判定    : outputs('Compose_Flow_Output')?['success']
リストURL   : outputs('Compose_Flow_Output')?['resultObject']?['listUrl']
新規件数    : outputs('Compose_Flow_Output')?['resultObject']?['createdCount']
```

`resultJson` は文字列化した同じ内容。子フロー呼び出しや HTTP 送信の本文にそのまま使える。

---

## 9. エラーが出たとき

[troubleshooting.md](troubleshooting.md) にエラーコード別の対処をまとめてある。

まず見るのは次の3つ。

1. `resultObject.error.code` — 何が起きたか
2. `resultObject.error.stage` — どこで起きたか
3. 実行履歴でその `stage` のスコープを開き、赤いアクションの「入力」「出力」
