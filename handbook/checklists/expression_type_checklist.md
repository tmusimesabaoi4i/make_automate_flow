# 式の型チェックリスト

式を書く際・レビューする際に機械的に確認する項目。
詳細は[../knowledge/expression_examples.md](../knowledge/expression_examples.md)を参照。関連ルール: [../rules/02_expression_and_type_safety.md](../rules/02_expression_and_type_safety.md)

- [ ] trim()の対象が文字列であることを確認した（配列・オブジェクト・Boolean・数値・バイナリに直接trimしていない）
- [ ] coalesce()の候補がすべて同一型であることを確認した（文字列は`''`、配列は`json('[]')`、オブジェクトは`json('{}')`）
- [ ] Apply to eachの入力が配列であることを保証している（`coalesce(x, json('[]'))`またはFilter/Select/Queryの出力）
- [ ] 日付関数（formatDateTime/convertFromUtc等）へ空文字列やnullをそのまま渡していないか確認した（事前に存在確認している）
- [ ] Booleanのfalse・数値の0を「未設定」として扱っていないか確認した（coalesceの後にequals/greaterで明示比較している）
- [ ] SetVariableの値式に、更新対象と同名の`variables('...')`参照（自己参照）が無いことを確認した
- [ ] 参照している変数がすべて事前にInitializeVariableで初期化済みであることを確認した（未定義変数参照が無い）
- [ ] 式文字列内の`@`が、式の先頭または`@{...}`補間以外の位置に出現していないことを確認した（ネストした@の禁止）
- [ ] 配列の計算インデックスアクセス（`配列[式]`のような角括弧アクセス）を避け、substring等の関数で代替しているか確認した
- [ ] **`if()`の「通らない側」の引数も単体で安全に評価できることを確認した**（`if()`は両分岐を先行評価する。特に`substring(x, 0, sub(length(x),1))`のような長さ計算は空文字で失敗する）
- [ ] **`substring`の第1引数が空文字になりうる箇所を洗い出し、番兵付き（`substring(concat(S, '#'), …)`）にした**（開始位置は「文字列長より小さい」必要があり、`substring('', 0, 0)`も実行時エラーになる。2026-08-04実発生）
- [ ] **入力が空のテストケースを用意し、生成済み`definition.json`の式を`tools/wdl_eval.py`で評価した**（正常系だけでは空文字起因の実行時エラーは表面化しない）
- [ ] 使用している関数がすべて実在確認済みの集合に含まれることを確認した（推測で関数名を書いていない。可能なら検証スクリプトの許可リスト検査で機械確認する）
- [ ] sort()を降順で使う必要がある箇所はreverse()を併用しているか確認した
- [ ] union()を配列連結に使う場合、重複排除の副作用（完全一致要素の統合）を許容できるか確認した

関連: [../knowledge/error_catalog.md](../knowledge/error_catalog.md)
