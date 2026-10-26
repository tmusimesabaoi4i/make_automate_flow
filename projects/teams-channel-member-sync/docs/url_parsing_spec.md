# URL解析・正規化の仕様

対象: フローAの `Scope_00_Bootstrap` / `Scope_01_ValidateInput` / `Scope_02_ParseTeamsUrl` / `Scope_03_ParseSharePointUrl`。

ここに書いた挙動は、生成済み `definition.json` の式をそのまま評価する
[../tests/run_url_parse_tests.py](../tests/run_url_parse_tests.py)（29ケース）で確認している。
設計書を再実装して検証するのではなく、**生成物を検証している**。

---

## 1. TeamsチャネルURLの解析

### 入力の例

```
https://teams.microsoft.com/l/team/19%3Aabc123def456%40thread.tacv2/conversations?groupId=<GUID>&tenantId=<GUID>
```

### 取り出す値

| 値 | 取り出し元 | 必須 |
|---|---|---|
| チームID（`varTeamId`） | クエリの `groupId` | 必須 |
| チャネルID（`varChannelId`） | パスの `/l/team/` と次の `/` の間（URLデコード後） | 必須 |
| テナントID（`varTenantId`） | クエリの `tenantId` | 任意 |
| 元のURL（`varTeamsChannelUrl`） | 入力そのまま（trim のみ） | — |

### 手順

1. **フラグメントを落とす** — `first(split(url, '#'))`
2. **パスとクエリに分ける** — パス = `first(split(x, '?'))`、クエリ = `?` 以降（無ければ空）
3. **ホストを取り出して照合する** — `toLower(first(split(last(split(path, '://')), '/')))`
   `teams.microsoft.com` または `teams.cloud.microsoft` でなければ `ERR_NOT_TEAMS_URL`
4. **クエリを正規化する** — 前後に `&` を足す: `concat('&', query, '&')`
5. **クエリ値をアンカー方式で取り出す**

   ```
   @if(contains(Q, '&groupId='),
       trim(decodeUriComponent(first(split(last(split(Q, '&groupId=')), '&')))), '')
   ```

   `&<名前>=` で分割するので、**順序が変わっても・余分なパラメータがあっても・欠けていても壊れない**。
   前後に `&` を足してあるため、`groupId` が `subGroupId` の部分一致で誤検出されることもない。
   固定位置の分割は使っていない。

6. **チャネルIDをパスから取り出す**

   ```
   @if(contains(P, '/l/team/'), last(split(P, '/l/team/')), '')      → 末尾部分
   @trim(decodeUriComponent(first(split(TAIL, '/'))))                → チャネルID
   ```

   `decodeUriComponent` が `%3A` → `:`、`%40` → `@` を復号する。
   `/conversations` が無くても、末尾にスラッシュが付いていても、最初のセグメントを取るだけなので壊れない。

7. **検証する**（最初に該当したものを返す）

   | 条件 | エラーコード |
   |---|---|
   | `groupId` が空 | `ERR_GROUPID_NOT_FOUND` |
   | `groupId` がGUID形式でない（長さ36・`-` で5分割） | `ERR_GROUPID_INVALID` |
   | チャネルIDが空 | `ERR_CHANNELID_NOT_FOUND` |
   | チャネルIDが `19:` で始まり `thread.` を含む形でない | `ERR_CHANNELID_INVALID` |

8. **テナントIDはGUID形式のときだけ採用する**。形式が違えば空にする。
   誤ったテナントIDで外部ユーザー判定をしないため。

> 【実装上の注意】チャネルIDの検証に `'@thread.'` という文字列リテラルを使っていない。
> `startsWith(ch, '19:')` と `contains(ch, 'thread.')` に分けることで、式中の `@` を増やさずに同じ判別力を得ている。

### 対応する入力の形

| 形 | 対応 | テストID |
|---|---|---|
| 通常のチャネルURL | ○ | T01 |
| チャネルIDがURLエンコード済み（`%3A` / `%40`） | ○ | T02 |
| クエリの順序が違う | ○ | T03 |
| 余分なクエリパラメータがある | ○ | T04 |
| `groupId` が無い | エラー | T05 |
| `tenantId` が無い | ○（テナントIDは空） | T06 |
| `/l/team/` が無い | エラー | T07 |
| Teams 以外のホスト | エラー | T08 |
| 末尾スラッシュ・フラグメント付き | ○ | T09 |
| チャネルIDが非エンコード（`:` `@` が生） | ○ | T10 |
| `teams.cloud.microsoft` ドメイン | ○ | T11 |
| `groupId` がGUIDでない | エラー | T12 |
| チャットのURL | エラー | T13 |
| `tenantId` の形式が不正 | ○（空にする） | T14 |
| 空文字・空白のみ | エラー | T15 |

### 対応しない形

- チャット（1対1・グループ・会議）のURL — チャネルではないため対象外
- `/l/channel/` 形式のURL — `/l/team/` を前提にしている
- 大文字化された `/L/TEAM/` — `contains` は大文字小文字を区別する（Teams が生成する機械的な文字列を前提にしている）

---

## 2. SharePointサイトURLの正規化

### 入力の例と結果

| 入力 | 結果 |
|---|---|
| `https://c.sharepoint.com/sites/pj` | `https://c.sharepoint.com/sites/pj` |
| `https://c.sharepoint.com/sites/pj/_layouts/15/viewlsts.aspx?view=14` | `https://c.sharepoint.com/sites/pj` |
| `https://c.sharepoint.com/sites/pj/Lists/MyList/AllItems.aspx` | `https://c.sharepoint.com/sites/pj` |
| `https://c.sharepoint.com/sites/pj/SitePages/Home.aspx` | `https://c.sharepoint.com/sites/pj` |
| `https://c.sharepoint.com/sites/pj/` | `https://c.sharepoint.com/sites/pj` |
| `https://c.sharepoint.com/teams/pj/_layouts/15/viewlsts.aspx` | `https://c.sharepoint.com/teams/pj` |
| `https://c.sharepoint.com/_layouts/15/viewlsts.aspx` | `https://c.sharepoint.com` |
| `https://example.com/sites/pj` | エラー `ERR_NOT_SHAREPOINT_URL` |

### 手順

1. **フラグメントを落とす** → **クエリを落とす**
2. **小文字化した文字列で位置を判定する**（切り出しは元の文字列に対して行う。`toLower` は長さを変えないので位置が一致する）
3. **管理系パスの手前で切る**

   ```
   @if(contains(L, '/_layouts/'), indexOf(L, '/_layouts/'),
    if(contains(L, '/_api/'), indexOf(L, '/_api/'),
    if(contains(L, '/lists/'), indexOf(L, '/lists/'),
    if(contains(L, '/sitepages/'), indexOf(L, '/sitepages/'),
    if(contains(L, '/forms/'), indexOf(L, '/forms/'),
    length(L))))))
   ```

4. **`/sites/` または `/teams/` があれば、その次の1セグメントで打ち切る**

   ```
   位置 = if(contains(C, '/sites/'), add(indexOf(C, '/sites/'), 7),
           if(contains(C, '/teams/'), add(indexOf(C, '/teams/'), 7), 0))
   結果 = if(greater(位置, 0),
            concat(substring(D, 0, 位置),
                   first(split(substring(D, 位置, sub(length(D), 位置)), '/'))),
            D)
   ```

5. **末尾のスラッシュを落とす** — `split` → `take` → `join` で行う

### 【重要】`if()` は使わない側の分岐も先行評価される

Power Automate の `if()` は、選ばれない側の引数も評価する（handbook/knowledge/lessons_learned.md §21）。
そのため `substring` に渡す位置は、**必ず先に Compose で確定させた安全な値**にしている。

- `indexOf` は見つからないと `-1` を返すが、それ自体は例外にならない。危険なのは `-1` を `substring` に渡したとき。
- 位置を別 Compose（`Compose_*_CutIndex` / `Compose_*_AnchorIndex`）で「見つかったときの値／見つからなければ 0 か長さ」に確定させてから `substring` に渡している。
- 末尾スラッシュ除去に `substring(s, 0, sub(length(s), 1))` を使うと、`s` が空文字のとき長さ `-1` で失敗する。`split` → `take` → `join` なら空文字でも安全。

この2点は `tests/run_url_parse_tests.py` の S10（ルートサイト）・S11（空文字）・A01（管理サイト未設定）で機械的に確認している。

---

## 3. 管理サイトURLの正規化

`Compose_AdminSiteUrl` の値にも §2 とまったく同じ正規化を適用する（`build_normalize_site_url("Admin", ...)`）。
利用者が管理画面のURLを貼り付けても、サイトルートに直してから設定リストの読み書きに使う。

検証:

| 条件 | エラーコード |
|---|---|
| `Compose_AdminSiteUrl` が空 | `ERR_ADMIN_SITE_NOT_SET` |
| ホストが `*.sharepoint.com` でない | `ERR_ADMIN_SITE_NOT_SHAREPOINT` |

---

## 4. セキュリティ上の扱い

要件§14 に対応する実装を、どこで担保しているか。

| 原則 | 実装 |
|---|---|
| Teams / SharePoint 以外の任意ホストを受け付けない | ホストを取り出して `teams.microsoft.com` / `teams.cloud.microsoft` / `*.sharepoint.com` と照合する。静的検査 P08 が Graph の宛先を `graph.microsoft.com` に固定していることも確認する |
| ユーザー入力をそのまま HTTP 要求へ連結しない | ・サイトURLは正規化＋ホスト検査を通したものだけを `dataset` に渡す<br>・**リスト名は URI に一切連結しない**（リストIDでのみ対象を特定する）<br>・チャネルIDは Graph URI に入れる前に必ず `uriComponent()` で符号化する（静的検査 P08） |
| 入力値を検証する | 空・長さ・ホスト・GUID形式・チャネルID形式を検証する。1つでも外れたら後続の Scope は何もしない（`varIsValid` ゲート） |
| 保存済みの値も信用しない | 定期フローは設定リストから読んだサイトURLについても、ホストが `*.sharepoint.com` であることを毎回検査する（静的検査 D06） |

---
関連: [../README.md](../README.md) / [../tests/test_cases.md](../tests/test_cases.md) / [design_decisions.md](design_decisions.md)
