# Word / HTML ドキュメント生成

標準コネクタだけで文書ファイルを作るときのルールです。真正な .docx が作れない制約、HTMLベース .doc の扱い、HTMLエスケープの順序、改ページ、HTML文字列の累積方法を扱います。文字列累積の一般則は [03](./03_variables_arrays_and_objects.md)、エスケープ式の型規律は [02](./02_expression_and_type_safety.md) を参照。

## 標準コネクタで真正 .docx は動的生成できない【事実】
- 【事実】標準コネクタだけでは、中身が本物の Office Open XML である .docx を動的生成できない。
  Word Online (Business) の「テンプレートに文字を入力（Populate a Word template）」はプレミアム。
- 【案件固有】今回はプレミアムを使わない方針のため、**HTMLベースの Word 互換ファイル**を採用した。
- 【事実・禁止】HTML の中身を作って**拡張子だけ `.docx` にリネームするのは禁止**。
  真正な .docx ではないため破損ファイル扱いになる。

## HTMLベースの .doc / .html の制約【事実 + 案件固有】
- 【案件固有】今回は Word 互換 HTML を `.doc` として保存した（`課内会議総括_yyyyMMdd_HHmmss.doc` 相当の命名）。
- 【要実環境確認】`.doc` を開くと Word が「本来の形式と異なる」旨の警告を出す可能性がある。
  警告を避けたい場合は `.html` 保存を代替として検討する。実環境の Word で挙動を確認する。
- 【推奨】いずれもレイアウトは HTML の表現力の範囲に限られる（高度な Word 機能は使えない）。要件と照らして選ぶ。

## HTMLエスケープの順序【事実】
- 【事実】ユーザー入力（投稿本文・氏名・ファイル名）を HTML に埋め込む前にエスケープする。
  **順序が重要で `&` を最初に**置換する。順序を誤ると二重エスケープになる。

  ```
  1. & → &amp;   （必ず最初）
  2. < → &lt;
  3. > → &gt;
  4. " → &quot;
  5. ' → &#39;
  ```

- 【推奨】各置換は「作成（Compose）」に分けて段階化すると、`replace` の入れ子ミスを防げる（[02](./02_expression_and_type_safety.md)）。
- 【事実】本文中の改行は `<br>` に変換して表示を保つ。

## 改ページは2件目以降のみ【事実】
- 【事実】会議を連結する文書で、各会議の前に改ページを入れるのは**2件目以降**だけにする。
  1件目の前に改ページを入れると先頭に空白ページができる。判定はインデックスが0より大きいとき。

  ```
  <div style="page-break-before: always;"></div>
  ```

  （`varMeetingIndex` が 0 より大きいときにのみ挿入）

## HTMLの累積は「文字列変数に追加」【事実】
- 【事実】HTML 文字列の組み立ては「文字列変数に追加（Append to string variable）」で1つの文字列変数へ連結する。
  ヘッダ→（各会議: 改ページ/見出し/本文/添付リンク）→フッタの順に追記する。
- 【事実・禁止】`concat(variables('自身'), 追加分)` を SetVariable で行う自己参照は禁止（保存エラー）。
  必ず Append to string variable を使う（[03 変数・配列・オブジェクト](./03_variables_arrays_and_objects.md)）。
- 【推奨】配列に貯めて最後に `join` する方式でも作れるが、今回は文字列直接連結（Append to string variable）に統一した。
  どちらか一方に統一し、混在させない。

## 本文のプレーンテキスト化【事実】
- 【事実】Teams 応答の本文（HTML）をプレーンテキスト化するには Content Conversion の
  「Html to text（operationId=HtmlToText）」を使う。**パラメータキーは `Content`**（`html` ではない）。
  キー名を誤ると入力欠落・エラーになる。

関連: [00 コアルール](./00_power_automate_core_rules.md) / [02 式と型](./02_expression_and_type_safety.md) / [03 変数・配列](./03_variables_arrays_and_objects.md) / [05 SharePoint/Teams](./05_sharepoint_and_teams_patterns.md)
