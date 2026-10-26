# 利用手順書

インポート済みの `CreateInitializedSharePointList` を実際に使う手順です。インポート自体は [installation.md](installation.md) を参照してください。

---

## 1. このフローができること・しないこと

| できること | しないこと |
|---|---|
| 指定サイトに同名リストが無ければ新規作成する | **同名リストがある場合は何もしない**（既存リストを変更しない） |
| 作成したリストの削除可能な列をすべて削除する | 既存リストの列を削除する |
| `sample_raw`（拡張リッチテキスト）を1列だけ作る | 既存リストのビューを変更する |
| 既定ビューの表示列を `sample_raw` だけにする | リストのアイテムを削除する |
| 添付ファイル機能を無効化する | 削除できないシステム列を強制削除する |
| 初期化に失敗したら今回作ったリストだけを削除する | リスト名を根拠にリストを削除する |

---

## 2. 入力

| 内部名 | 表示名 | 型 | 必須 |
|---|---|---|---|
| `SharePointUrl` | SharePointサイトまたはリスト一覧URL | テキスト | **はい** |
| `ListName` | 作成するリスト名 | テキスト | **はい** |
| `ListDescription` | リストの説明 | テキスト | いいえ |

### SharePointUrl に入れられるもの

```text
https://{tenant}.sharepoint.com/sites/{site}
https://{tenant}.sharepoint.com/sites/{site}/_layouts/15/viewlsts.aspx
https://{tenant}.sharepoint.com/sites/{site}/_layouts/15/viewlsts.aspx?view=14
https://{tenant}.sharepoint.com/sites/{site}/{subsite}/_layouts/15/viewlsts.aspx
https://{tenant}.sharepoint.com                     ← テナントルートサイト
```

前後の空白・末尾のスラッシュ・フラグメント（`#...`）は自動で除去されます。

**個別リストのビューURL（`.../Lists/<名前>/AllItems.aspx`）は対象外です。** 解析段階では検出できず、実行時に 404（`ERR_SITE_OR_RESOURCE_NOT_FOUND`）で失敗します。サイトのトップページかリスト一覧ページのURLを使ってください。

### ListName の制約

- 前後の空白は自動で除去され、**除去後の値**が使われます
- **入力した名前を勝手に別の名前へ変更することはありません。** 使えない名前はエラーとして返します
- 日本語・空白・ハイフン・アンダースコアは使えます
- 使えないもの: `" # % * : < > ? / \ | { } ~`、タブ・改行、先頭/末尾のピリオド、255文字超、予約名（`con` `nul` `forms` 等）

### ListDescription

省略すると次が設定されます。

```text
Power Automateにより作成された初期化済みリスト
```

---

## 3. 実行方法

1. 「マイフロー」でフローを開きます。
2. 「実行」（またはデザイナーの「テスト」→「手動」）をクリックします。
3. 3つの入力欄に値を入れます（説明は空欄可）。
4. 「実行」をクリックします。

手動トリガー（ボタン）なので、Power Automate モバイルアプリの「ボタン」タブからも実行できます。

---

## 4. 結果の確認方法

### 4-1. 実行履歴で見る

実行履歴を開き、一番下の **`Scope_Finalize` → `Compose_Flow_Output`** の「出力」タブを見ます。

```json
{
  "success": true,
  "status": "Created",
  "resultObject": { … },
  "resultJson": "{…}"
}
```

`status` が最も重要です。

| status | 意味 | 次にすること |
|---|---|---|
| `Created` | 新規作成＋初期化が完了 | SharePoint でリストを確認 |
| `AlreadyExists` | 同名リストがあったため何もしなかった | **正常**。別の名前で実行するか、既存リストをそのまま使う |
| `AlreadyExistsOrConflict` | 作成が競合または権限不足で失敗 | `errors[]` の `httpStatusCode` を確認 |
| `InitializationFailed` | 作成はできたが初期化に失敗 | `rollbackPerformed` を確認。false なら `createdListId` のリストを手動削除 |
| `Failed` | 入力検証やサイト疎通で失敗 | `errors[]` のエラーコードを確認 |

### 4-2. 個別のアクションで見る

| 見たいもの | アクション |
|---|---|
| 抽出されたサイトURL | `Parse_SiteUrl` / `Set_SiteUrl` |
| 入力検証の結果 | `Compose_Input_Validation_Code`（空なら正常） |
| サイトの疎通結果 | `Verify_SharePoint_Web` |
| 同名リストの判定 | `Filter_Matching_List_Names` / `Determine_List_Existence` |
| 作成したリストID | `Store_Created_List_Id` |
| 削除した列 | `Append_Deleted_Field`（ループ内） |
| `sample_raw` の検証 | `Verify_SampleRaw_Field` / `Compose_SampleRaw_Verification` |
| 既定ビューの最終列 | `Verify_Default_View_Fields` / `Store_Final_View_Fields` |

### 4-3. 変数

| 変数 | 型 | 内容 |
|---|---|---|
| `varResultObject` | Object | 構造化された結果（[json_schema.md](json_schema.md)） |
| `varResultJson` | String | 上記のJSON文字列 |
| `varCreatedListId` | String | 今回作成したリストのID（**すべての書き込み対象を決める値**） |
| `varDeletedFields` | Array | 削除した列 |
| `varSkippedFields` | Array | 削除しなかったシステム列＋理由 |
| `varFinalViewFields` | Array | 既定ビューの最終表示列 |

---

## 5. 作成されたリストの確認

`status: "Created"` になったら、SharePoint 画面で確認してください。

| 確認項目 | 期待 |
|---|---|
| 既定ビューの列 | データ列は `sample_raw` の1列だけ |
| `Title` `ID` `Created` `Modified` 等 | 既定ビューに**表示されていない** |
| `sample_raw` の型 | 「複数行テキスト」＋リッチテキスト（拡張リッチテキスト） |
| 添付ファイル | 無効 |
| アイテム | 0件 |

> 選択チェックボックス・行メニュー・編集操作など SharePoint の UI が自動表示する操作要素は「列」ではありません。これらが見えていても問題ありません。
>
> リスト設定画面には削除できないシステム列（`Title` 等）が残ります。これは**許容される状態**です（指示書§25）。利用者から見えるデータ列が `sample_raw` だけになっていれば目的は満たされています。

### sample_raw に保存できるもの

```html
<a href="https://example.com">リンク</a>
<b>太字</b> と <i>斜体</i>
複数行の
テキスト
```

`RichTextMode="FullHtml"` の列なので、HTML とハイパーリンクをそのまま保持できます。

---

## 6. 同じリスト名で2回実行した場合

1回目: `Created`（新規作成＋初期化）
2回目: `AlreadyExists`（**1回目に作ったリストには一切触れません**）

再初期化はしません。作り直したい場合は、SharePoint 画面で手動でリストを削除してから再実行してください。

---

## 7. 後続処理で使う

本フローは結果を変数に格納するところまでを担当します。結果を別の場所へ渡したい場合は次を検討してください。

- **同じフローにアクションを追加する**: `Scope_Finalize` の後ろに追加し、`variables('varResultJson')` を渡す
- **作成したリストへ項目を投入する**: `variables('varCreatedListId')` を使って `_api/web/lists(guid'{listId}')/items` へ POST する

改修する場合は `flows/create-initialized-list/source/build_list_flow.py` を編集して再生成してください（`definition.json` を直接編集しないでください）。

---

## 8. エラーが出たとき

フローは**エラーでも最後まで実行され**、結果はエラー形式のJSONとして格納されます。実行履歴が赤くならない場合もあるため、必ず `Compose_Flow_Output` の `success` と `status` を確認してください。

エラーコードごとの対処は [troubleshooting.md](troubleshooting.md) を参照してください。

---

関連: [installation.md](installation.md) / [json_schema.md](json_schema.md) / [safety_mechanisms.md](safety_mechanisms.md) / [troubleshooting.md](troubleshooting.md)
