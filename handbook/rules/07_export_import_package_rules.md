# エクスポート / インポート・パッケージルール

フローをレガシーパッケージ（.zip）として組み立て・匿名化・検査し、インポートするときのルールです。接続の再設定は [04](./04_connectors_permissions_and_dlp.md)、変数・式の検査観点は [02](./02_expression_and_type_safety.md)/[03](./03_variables_arrays_and_objects.md) を参照。

## レガシーパッケージ か ソリューション か【事実】
- 【事実】今回は「パッケージ（レガシー）」形式の .zip を採用。中身は JSON のみで **XML は含まない**。
  Dataverse ベースの「ソリューション」形式とは別物なので混同しない。
- 【推奨】どちらの形式で配布するかを最初に決める。雛形（既存パッケージ）と同じ形式に合わせる。

## 5ファイル構造【事実】
- 【事実】レガシーパッケージの構造（プレースホルダー `{guid}` はフローGUID）:

  ```
  manifest.json                                   （ルート: schema/details/resources）
  Microsoft.Flow/flows/manifest.json              （flowAssets.assetPaths）
  Microsoft.Flow/flows/{guid}/definition.json     （フロー本体）
  Microsoft.Flow/flows/{guid}/apisMap.json        （接続参照キー→API GUID）
  Microsoft.Flow/flows/{guid}/connectionsMap.json （接続参照キー→接続 GUID）
  ```

- 【事実】`apisMap.json` / `connectionsMap.json` は connectionReferences のキー→リソースGUID の対応表。
  ルート `manifest.json` の `dependsOn` は使用API・接続の全GUIDを含む（3コネクタなら API3＋接続3）。

## パッケージGUIDの3点一致【事実】
- 【事実】フロー資産GUID（`{guid}`）は**3箇所を完全一致**させる: ルート`manifest.json`の`resources`キー（`hierarchy:"Root"`のリソース）＝`Microsoft.Flow/flows`フォルダ名＝`Microsoft.Flow/flows/manifest.json`の`flowAssets.assetPaths`要素。
- 【事実】APIリソース／接続リソースのGUIDも、ルート`manifest.json`の`resources`キーと`apisMap.json`／`connectionsMap.json`の値（コネクタ論理名→GUID）を一致させる。
- 【事実】`definition.json`内の`name`/`id`（実フローGUID）は上記のフロー資産GUIDとは**別物**でよい（二重GUID構造。一致は不要）。
- 【推奨】`properties.name`/`id`は新規インポートで自動再採番されるため一致は気にしなくてよい。上記3点一致と`apisMap`/`connectionsMap`の対応は、本ファイル下記「検査」節の機械走査項目に含めて0件不一致を確認する。

## connectionReferences の2方式【事実】
- 【事実】どちらも実在の正当形式。プロジェクト内で**どちらか一方に統一**する。
  - (a) Embedded ＋ `authentication="@parameters('$authentication')"`（実働サンプルが使用）。
  - (b) Invoker ＋ X-MS-APIM-Tokens 復号式（雛形サンプル・当方採用。実環境インポート成功実績あり）。
- 【事実】接続参照のキーは `shared_teams-2` のように自動採番サフィックスが付くことがある。
  **アクションの `host.connectionName` は connectionReferences のキーと完全一致**させる。
- 【事実】`authentication` は参照式であって秘密情報ではない（雛形と同一の標準形）。トークンは埋め込まない。

## 匿名化【事実】
- 【事実】配布パッケージから次を除去（新規GUID・空値へ）: `creator.id` / `tenantId` / 接続GUID / メールアドレス。
  `metadata.creator` は空オブジェクト、`details.creator` は `"N/A"` 等の非個人値にする。
- 【事実】匿名化した接続情報（実在しない接続GUID）は、インポート時にユーザーが選択した実接続へ
  正しく再マッピングされる。公式の明言は無いが、**実環境でのインポート後に実行が成功したことで実証済み**。
  確認日 2026-07-24 / 根拠: teams_post_url_flows（**Teams** 接続1本）と
  create_initialized_sharepoint_list（**SharePoint** 接続1本）の2案件で成功。
  いずれも Invoker形式＋匿名GUID。接続数が多い構成での同挙動は個別に確認する。

## 検査（インポート前に機械走査・すべて0件に）【推奨】
- 【推奨】次を機械走査し、0件になるまで直す:
  JSON構文 / **GUID重複**（フローGUID・接続GUIDの衝突）/ **runAfter の兄弟整合**（参照先が同階層に実在）/
  変数の初期化＝参照の一致 / 重複アクション名 / SetVariable自己参照 / 重複初期化 / 接続参照の突合（apisMap・connectionsMap と一致）/
  不正な `@` / operationId 実在 / 匿名化リーク（実値の残留）。
- 【事実】ZIP 直下の階層は雛形と一致させる。`__MACOSX` / `.DS_Store` を混入させない。
- 【推奨】**JSON は JSON として編集**する（パーサで読み書き）。正規表現による文字列置換で構造を壊さない。

## インポート成功 ≠ 完成【事実・最重要】
- 【事実】今回インポートは通ったが**保存で失敗**した（SetVariable 自己参照。[03](./03_variables_arrays_and_objects.md)）。
  「インポートできた＝完成」ではない。
- 【推奨】インポート後は必ず次を行う:
  1. フローを**開く**。
  2. **即保存**する（保存時にしか出ないエラー＝自己参照・重複名等をここで発見）。
  3. **フローチェッカー**を実行し警告を確認する。
  4. **小規模テスト**（小さい対象期間）で実際に動かす（段階テストは [08](./08_error_handling_and_idempotency.md)）。
- 【事実】今回の実環境インポートは未検証。検証済みは JSON パース・参照整合・ZIP再展開が雛形と同一構造であることのみ。
  「インポート成功済み」とは書かない。

関連: [00 コアルール](./00_power_automate_core_rules.md) / [03 変数・配列](./03_variables_arrays_and_objects.md) / [04 コネクタ・権限](./04_connectors_permissions_and_dlp.md) / [08 エラー処理](./08_error_handling_and_idempotency.md) / [エラーカタログ](../knowledge/error_catalog.md)
