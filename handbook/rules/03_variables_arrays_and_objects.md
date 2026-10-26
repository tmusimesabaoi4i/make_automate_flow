# 変数・配列・オブジェクト（自己参照禁止・型別更新）

変数の更新方法のルールです。今回の**保存エラーの根本原因**である SetVariable の自己参照禁止と、型ごとの正しい累積方法、初期値の規律を扱います。式・型の一般則は [02](./02_expression_and_type_safety.md) を参照。

## SetVariable（変数の設定）の自己参照は全面禁止【事実・最重要】
- 【事実】「変数の設定（Set variable）」の値式に、**更新対象の変数自身**を含めると保存で失敗する。
  今回の実エラー全文（要約）:

  ```
  The inputs of workflow run action 'Set_MessagesArray' of type 'SetVariable' are not valid.
  Self reference is not supported when updating the value of variable 'varMessagesArray'.
  （コード: WorkflowRunActionInputsInvalidProperty）
  ```

- 【事実】名前が `Append...` でも、実体が SetVariable＋自己参照なら同じく禁止。
  今回検出された3件は `Set_MessagesArray` / `Set_RepliesArray` / `Append_Reply_Attachment_Candidates`
  （3件目は名前がAppendだが type は SetVariable）。**名前でなく type を見る**。

### 禁止例 → 修正例（今回の3パターン）
- 配列の累積（禁止: `union` で自身を参照）

  ```
  # 禁止（SetVariable の値式）
  union(variables('varMessagesArray'), body('Get_Channel_Messages')?['value'])
  ```
  → 修正: 「それぞれに適用する（Apply to each）」の中で1件ずつ「配列変数に追加（Append to array variable）」。
  入力は配列を保証し、追加する値は `item()`。

  ```
  # Apply to each の入力
  coalesce(body('Get_Channel_Messages')?['value'], json('[]'))
  # 配列変数に追加 の値
  item()
  ```

- 文字列の累積（禁止: `concat` で自身を参照）→ 「文字列変数に追加（Append to string variable）」で連結する。
  詳細な適用例（HTML連結）は [06 Word/HTML生成](./06_word_html_document_generation.md)。

- カウンターの加算（禁止: `add(variables('自身'), 1)`）→ 「変数を増分する（Increment variable）」を使う。

### なぜ「ページ配列を1要素としてAppend」してはいけないか
- 【推奨】ページング応答（例: 50件の配列）を Append to array variable に**そのまま渡すと、配列が入れ子になり
  1要素として追加**される（`[[...50件...]]`）。必ず Apply to each で**1件ずつ**追加する。

## 型別の正しい更新方式【事実】
| 型 | 更新に使うアクション | 追加する値の例 |
|---|---|---|
| 配列 | 配列変数に追加（Append to array variable） | `item()`（Apply to each 内） |
| 文字列 | 文字列変数に追加（Append to string variable） | 連結したいHTML等の文字列 |
| 整数 | 変数を増分する（Increment variable） | `1` などの増分値 |
| オブジェクト | 作成（Compose）で**新規構築** → 配列変数に追加 | Compose の出力 |

- 【推奨】オブジェクトは「自身に足す」概念がない。Compose で1件分のオブジェクトを組み立て、
  それを配列変数に Append する。今回の会議・添付の正規化データもこの方式。

## 初期値の規律【推奨】
- 型に合った初期値で初期化する: 配列 `json('[]')`、文字列 `''`、オブジェクト `json('{}')`、整数 `0`。
- 【事実】「変数を初期化する（Initialize variable）」はトップレベル必須（[01](./01_flow_architecture_rules.md)）。
- 【推奨】同じ変数を二重に初期化しない（重複初期化禁止）。
- 【推奨】ループごとに配列を空へ戻す「リセット」は自己参照ではないので可
  （例 `varRepliesArray = json('[]')`。返信ループの先頭で使用）。

## union による重複排除の副作用【事実】
- 【事実】`union()` は完全一致要素を統合する（重複排除）。配列連結に使うと、同一要素があると件数が減る。
  ページング連結には union を使わず、Append to array variable 方式にする。
- 【案件固有】今回はページングが重複を返さない前提とし、重複保存の防止は冪等キー台帳で行う
  （[08 エラー処理と冪等性](./08_error_handling_and_idempotency.md)）。

関連: [00 コアルール](./00_power_automate_core_rules.md) / [02 式と型](./02_expression_and_type_safety.md) / [06 Word/HTML生成](./06_word_html_document_generation.md) / [08 エラー処理](./08_error_handling_and_idempotency.md) / [エラーカタログ](../knowledge/error_catalog.md)
