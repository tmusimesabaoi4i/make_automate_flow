# -*- coding: utf-8 -*-
"""
同期ロジック（差分判定・離脱ガード・正規化・ページング）の回帰テスト（要件§16.3・§16.4）。

生成済み definition.json から実際の式・Filter array の条件を取り出して評価する。
設計書の再実装ではなく生成物を検証する（handbook/knowledge/lessons_learned.md §23）。

  python run_sync_logic_tests.py

【確認できること】 与えたメンバー配列・既存アイテム配列に対して、定義中の式が返す判定。
【確認できないこと】 Power Automate 実機での挙動、コネクタ応答（要実環境確認）。
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..", "..", "..", "tools")))
from wdl_eval import Context, evaluate  # noqa: E402

PKG = os.path.join(HERE, "..", "flows", "daily-member-sync", "source", "package")

TEAM = "22222222-2222-2222-2222-222222222222"
TENANT = "11111111-1111-1111-1111-111111111111"
OTHER_TENANT = "33333333-3333-3333-3333-333333333333"
CHANNEL = "19:abc123def456@thread.tacv2"
OTHER_CHANNEL = "19:zzz999@thread.tacv2"
SYNC_SOURCE = "TeamsChannelMemberSync"

results = []


def check(cid, desc, got, want):
    ok = got == want
    results.append((ok, cid, desc, got, want))
    print("%s %s %s" % ("PASS" if ok else "FAIL", cid, desc))
    if not ok:
        print("     期待=%r / 実際=%r" % (want, got))


def load_definition(pkg_dir):
    flows_dir = os.path.join(pkg_dir, "Microsoft.Flow", "flows")
    guid = [d for d in os.listdir(flows_dir) if os.path.isdir(os.path.join(flows_dir, d))][0]
    with open(os.path.join(flows_dir, guid, "definition.json"), encoding="utf-8") as f:
        return json.load(f)["properties"]["definition"]


def walk(container, out):
    for name, a in container.items():
        if not isinstance(a, dict):
            continue
        out[name] = a
        if isinstance(a.get("actions"), dict):
            walk(a["actions"], out)
        if a.get("type") == "If" and isinstance(a.get("else"), dict):
            walk(a["else"].get("actions", {}), out)
    return out


def evaluate_deep(node, ctx):
    if isinstance(node, dict):
        return {k: evaluate_deep(v, ctx) for k, v in node.items()}
    if isinstance(node, list):
        return [evaluate_deep(v, ctx) for v in node]
    return evaluate(node, ctx)


def run_query(action, ctx):
    """Filter array（type: Query）を評価して、条件に合う要素だけを返す"""
    src = evaluate(action["inputs"]["from"], ctx)
    where = action["inputs"]["where"]
    out = []
    for it in (src or []):
        sub = Context(ctx.variables, ctx.outputs, ctx.bodies, ctx.trigger_body,
                      current_item=it, loop_items=ctx.loop_items)
        if evaluate(where, sub):
            out.append(it)
    return out


def _split_name(name):
    parts = name.split(" ", 1)
    return parts[0], (parts[1].strip() if len(parts) > 1 else "")


def member(sync_key, name, email, roles="", kind="direct",
           user_id=None, membership_id="mem-1", tenant=TENANT, external=False):
    last, first = _split_name(name)
    return {"syncKey": sync_key, "fullName": name, "lastName": last, "firstName": first,
            "email": email, "userId": sync_key if user_id is None else user_id,
            "membershipId": membership_id, "tenantId": tenant, "roles": roles,
            "membershipKind": kind, "isExternal": external}


def item(item_id, sync_key, name, email, roles="", kind="direct",
         status="在籍", active=True, channel=CHANNEL, source=SYNC_SOURCE):
    last, first = _split_name(name)
    # Title には氏名を入れない（同期キーを保持する内部識別子として扱う）
    return {"Id": item_id, "SyncKey": sync_key, "Title": sync_key,
            "FullName": name, "LastName": last, "FirstName": first, "Email": email,
            "MemberRoles": roles, "MembershipKind": kind, "MemberStatus": status,
            "IsActive": active, "ChannelId": channel, "SyncSource": source}


def main():
    if not os.path.isdir(PKG):
        print("パッケージが未生成です: %s" % PKG)
        return 1
    definition = load_definition(PKG)
    A = walk(definition["actions"], {})

    base_vars = {
        "varTeamId": TEAM, "varChannelId": CHANNEL, "varTenantId": TENANT,
        "varListEntityType": "SP.Data.TeamsMembersListItem",
        "varMemberKeys": [], "varCurrentSyncKey": "",
        "varExistingItems": [], "varMembersFetchComplete": True,
        "varMemberCount": 3, "varExistingFetchComplete": True,
        "varIsValid": True, "varFailedStage": "",
    }

    print("=" * 78)
    print("同期ロジックテスト（definition.json の式・Filter条件をそのまま評価）")
    print("=" * 78)

    # -------------------------------------------------------------
    # 1. 対象アイテムの絞り込み（同期対象外には触れない）
    # -------------------------------------------------------------
    existing = [
        item(1, "u1", "山田 太郎", "taro@example.test"),
        item(2, "u2", "鈴木 花子", "hanako@example.test"),
        item(3, "u9", "別チャネルの人", "x@example.test", channel=OTHER_CHANNEL),
        item(4, "u8", "手動で作られた行", "y@example.test", source=""),
    ]
    ctx = Context(dict(base_vars, varExistingItems=existing))
    target = run_query(A["Filter_Target_Existing_Items"], ctx)
    check("Q01", "同じチャネル・このフローが作った行だけを対象にする",
          sorted(i["Id"] for i in target), [1, 2])
    check("Q02", "別チャネルのアイテムを対象に含めない",
          any(i["Id"] == 3 for i in target), False)
    check("Q03", "このフロー以外が作ったアイテムを対象に含めない",
          any(i["Id"] == 4 for i in target), False)

    ctx.bodies["Filter_Target_Existing_Items"] = target

    # -------------------------------------------------------------
    # 2. 突き合わせ（新規 / 既存 / 重複）
    # -------------------------------------------------------------
    def match_for(key, targets=None):
        c = Context(dict(base_vars, varCurrentSyncKey=key), bodies={})
        c.bodies["Filter_Target_Existing_Items"] = targets if targets is not None else target
        c.variables["varExistingItems"] = existing
        return run_query(A["Filter_Match_Existing"], c)

    check("M01", "初回同期: 既存が無ければ一致0件（新規作成へ分岐）",
          len(match_for("newuser", [])), 0)
    check("M02", "2回目の同期: 同期キーで1件に一致する（重複作成しない）",
          len(match_for("u1")), 1)
    check("M03", "メンバー追加: 未登録のキーは一致0件",
          len(match_for("u3")), 0)
    dup = [item(10, "u1", "山田 太郎", "taro@example.test"),
           item(11, "u1", "山田 太郎", "taro@example.test")]
    check("M04", "同じ同期キーが2件あると一致2件（書き込まず記録へ分岐）",
          len(match_for("u1", dup)), 2)

    # -------------------------------------------------------------
    # 3. 変更検出（不要な更新をしない）
    # -------------------------------------------------------------
    def needs_update(existing_item, m):
        c = Context(dict(base_vars, varCurrentSyncKey=m["syncKey"]),
                    bodies={"Filter_Match_Existing": [existing_item]},
                    loop_items={"Foreach_Member": m})
        return evaluate(A["Compose_Needs_Update"]["inputs"], c)

    same = item(1, "u1", "山田 太郎", "taro@example.test")
    check("U01", "変更なし: 更新しない",
          needs_update(same, member("u1", "山田 太郎", "taro@example.test")), False)
    check("U02", "氏名変更: 更新する",
          needs_update(same, member("u1", "山田 二郎", "taro@example.test")), True)
    check("U02b", "姓だけが変わっても更新する",
          needs_update(same, member("u1", "田中 太郎", "taro@example.test")), True)
    check("U03", "メールアドレス変更: 更新する",
          needs_update(same, member("u1", "山田 太郎", "jiro@example.test")), True)
    check("U04", "ロール変更（メンバー→所有者）: 更新する",
          needs_update(same, member("u1", "山田 太郎", "taro@example.test", roles="owner")), True)
    check("U05", "メンバー種別が直接→間接に変わった: 更新する",
          needs_update(same, member("u1", "山田 太郎", "taro@example.test", kind="indirect")), True)
    check("U06", "離脱扱いだった人が戻ってきた: 在籍へ更新する",
          needs_update(item(1, "u1", "山田 太郎", "taro@example.test",
                            status="離脱", active=False),
                       member("u1", "山田 太郎", "taro@example.test")), True)
    check("U07", "メールが空のまま変わらない: 更新しない",
          needs_update(item(1, "u1", "ゲスト", ""), member("u1", "ゲスト", "")), False)
    check("U08", "メールが空→取得できた: 更新する",
          needs_update(item(1, "u1", "ゲスト", ""),
                       member("u1", "ゲスト", "guest@partner.test")), True)

    # -------------------------------------------------------------
    # 4. 離脱者の抽出と、無効化ガード
    # -------------------------------------------------------------
    def left_members(keys, targets=None):
        c = Context(dict(base_vars, varMemberKeys=keys))
        c.bodies["Filter_Target_Existing_Items"] = targets if targets is not None else target
        return run_query(A["Filter_Left_Members"], c)

    check("L01", "チャネルから外れた人を抽出する",
          [i["Id"] for i in left_members(["u1"])], [2])
    check("L02", "全員在籍していれば離脱者は0件",
          len(left_members(["u1", "u2"])), 0)
    check("L03", "すでに離脱済みの行は二重に処理しない",
          len(left_members([], [item(1, "u1", "x", "y", status="離脱", active=False)])), 0)

    def can_deactivate(**over):
        v = dict(base_vars)
        v.update(over)
        return evaluate(A["Compose_Can_Deactivate"]["inputs"], Context(v))

    check("G01", "正常時: 無効化してよい", can_deactivate(), True)
    check("G02", "Teams取得が0件: 無効化しない（全件無効化事故の防止）",
          can_deactivate(varMemberCount=0), False)
    check("G03", "Teams取得が完了していない: 無効化しない",
          can_deactivate(varMembersFetchComplete=False), False)
    check("G04", "既存アイテムの取得が完了していない: 無効化しない",
          can_deactivate(varExistingFetchComplete=False), False)
    check("G05", "どこかの段階で失敗している: 無効化しない",
          can_deactivate(varFailedStage="06_GetMembers"), False)
    check("G06", "入力・設定が不正: 無効化しない", can_deactivate(varIsValid=False), False)

    # -------------------------------------------------------------
    # 5. メンバー情報の正規化
    # -------------------------------------------------------------
    def norm(raw, tenant=TENANT, out_name=None):
        c = Context(dict(base_vars, varTenantId=tenant), loop_items={"Foreach_Raw_Member": raw})
        for n in ("Compose_Raw_UserId", "Compose_Raw_MembershipId"):
            c.outputs[n] = evaluate(A[n]["inputs"], c)
        c.variables["varCurrentSyncKey"] = evaluate(
            A["Set_Current_Sync_Key"]["inputs"]["value"], c)
        for n in ("Compose_Member_Name_Raw", "Compose_Member_Name_NoMarks",
                  "Compose_Member_Name_NoParen", "Compose_Member_Full_Name",
                  "Compose_Member_Last_Name", "Compose_Member_First_Name_Pos",
                  "Compose_Member_First_Name", "Compose_Member_UserId",
                  "Compose_Member_MembershipId", "Compose_Member_TenantId",
                  "Compose_Member_Roles", "Compose_Member_Kind",
                  "Compose_Member_IsExternal", "Compose_Member_Email_Raw"):
            c.outputs[n] = evaluate(A[n]["inputs"], c)
        c.variables["varResolvedEmail"] = c.outputs["Compose_Member_Email_Raw"]
        if out_name:
            return c.outputs[out_name]
        return evaluate_deep(A["Compose_Normalized_Member"]["inputs"], c)

    inside = {"id": "mem-1", "userId": "u1", "displayName": "山田 太郎",
              "email": "taro@example.test", "tenantId": TENANT, "roles": []}
    guest = {"id": "mem-2", "userId": "u2", "displayName": "ゲスト太郎",
             "email": "", "tenantId": TENANT, "roles": ["guest"]}
    external = {"id": "mem-3", "userId": "u3", "displayName": "社外 花子",
                "email": "hanako@partner.test", "tenantId": OTHER_TENANT, "roles": []}
    indirect = dict(inside, id="mem-4", userId="u4",
                    **{"@microsoft.graph.originalSourceMembershipUrl":
                       "https://graph.microsoft.com/v1.0/teams/x/members/y"})
    nouser = {"id": "mem-5", "userId": "", "displayName": "IDなし",
              "email": "", "tenantId": "", "roles": []}

    check("N01", "同期キーは userId を使う", norm(inside)["syncKey"], "u1")
    check("N02", "userId が無ければメンバーシップIDを同期キーにする",
          norm(nouser)["syncKey"], "mem-5")
    check("N03", "ロールは配列を結合して保持する（ゲスト）",
          norm(guest)["roles"], "guest")
    check("N04", "メールが空でも正規化は成立する（推測で生成しない）",
          norm(guest)["email"], "")
    check("N05", "同一テナントのメンバーは外部ユーザーにしない",
          norm(inside)["isExternal"], False)
    check("N06", "別テナントのメンバーは外部ユーザーと判定する",
          norm(external)["isExternal"], True)
    check("N07", "テナントIDが不明なときは外部と決めつけない",
          norm(external, tenant="")["isExternal"], False)
    check("N08", "直接メンバーは direct", norm(inside)["membershipKind"], "direct")
    check("N09", "共有チャネルの間接メンバーは indirect",
          norm(indirect)["membershipKind"], "indirect")
    check("N10", "ユーザーIDやメンバーシップIDを分解せずそのまま保持する",
          (norm(inside)["userId"], norm(inside)["membershipId"]), ("u1", "mem-1"))

    # -------------------------------------------------------------
    # 5B. 氏名の整形（外字マーカー・英字読みの併記・姓名の分割）
    # -------------------------------------------------------------
    def name_of(display):
        n = norm({"id": "m", "userId": "u", "displayName": display,
                  "email": "", "tenantId": TENANT, "roles": []})
        return (n["fullName"], n["lastName"], n["firstName"])

    check("D01", "外字マーカーと英字読みを除いて姓名に分ける（要件の例）",
          name_of("▲高▼元 優子(TAKAMOTO Yuko)"), ("高元 優子", "高元", "優子"))
    check("D02", "通常の「姓 名」表記", name_of("山田 太郎"), ("山田 太郎", "山田", "太郎"))
    check("D03", "全角スペース区切りも半角に寄せて分ける",
          name_of("山田　太郎"), ("山田 太郎", "山田", "太郎"))
    check("D04", "全角括弧の併記も除去する",
          name_of("佐藤 花子（SATO Hanako）"), ("佐藤 花子", "佐藤", "花子"))
    check("D05", "外字マーカーが名側にあっても除去する",
          name_of("斎藤 ▲徳▼子"), ("斎藤 徳子", "斎藤", "徳子"))
    check("D06", "スペースが無い表記は全体を姓にし、名は空にする",
          name_of("山田太郎"), ("山田太郎", "山田太郎", ""))
    check("D07", "表示名が空でも落ちない", name_of(""), ("", "", ""))
    check("D08", "スペースが2つ以上あっても最初の1つで分ける",
          name_of("山田 太郎 二世"), ("山田 太郎 二世", "山田", "太郎 二世"))
    check("D09", "英字名（半角スペース1つ）も同じ規則で分ける",
          name_of("Taro Yamada"), ("Taro Yamada", "Taro", "Yamada"))
    check("D10", "前後の空白は落とす", name_of("  山田 太郎  "), ("山田 太郎", "山田", "太郎"))

    # -------------------------------------------------------------
    # 6. 書き込みボディ（メールが空でも組み立てられる／固定値が入る）
    # -------------------------------------------------------------
    m = member("u2", "ゲスト太郎", "", roles="guest")
    c = Context(dict(base_vars, varCurrentSyncKey="u2"), loop_items={"Foreach_Member": m})
    body = evaluate_deep(A["Compose_Create_Item_Body"]["inputs"], c)
    check("B01", "Title に氏名を入れない（同期キーを入れる）", body["Title"], "u2")
    check("B01b", "氏名・姓・名は専用列に入る",
          (body["FullName"], body["LastName"], body["FirstName"]), ("ゲスト太郎", "ゲスト太郎", ""))
    check("B02", "メールが空でもボディを組み立てられる", body["Email"], "")
    check("B03", "同期キーが列に入る", body["SyncKey"], "u2")
    check("B04", "このフローが作ったことを示す印が入る", body["SyncSource"], SYNC_SOURCE)
    check("B05", "作成時は在籍・有効", (body["MemberStatus"], body["IsActive"]), ("在籍", True))
    check("B06", "対象チャネルが記録される", body["ChannelId"], CHANNEL)
    check("B07", "リストの型名が __metadata に入る（テナント差の構造的回避）",
          body["__metadata"]["type"], "SP.Data.TeamsMembersListItem")

    d = evaluate_deep(A["Compose_Deactivate_Body"]["inputs"], Context(dict(base_vars)))
    check("B08", "無効化は論理削除（同期状態=離脱・有効=false）",
          (d["MemberStatus"], d["IsActive"]), ("離脱", False))
    check("B09", "無効化ボディに氏名・メールを含めない（他の列を消さない）",
          sorted(d.keys()), sorted(["__metadata", "MemberStatus", "IsActive", "LastSyncedAt"]))

    # -------------------------------------------------------------
    # 7. ページング（既定ページサイズを超えても欠落しない）
    # -------------------------------------------------------------
    def next_uri(page_body):
        c2 = Context(dict(base_vars), bodies={"Get_Existing_Items_Page": page_body})
        c2.outputs["Compose_Existing_Next_Raw"] = evaluate(
            A["Compose_Existing_Next_Raw"]["inputs"], c2)
        return evaluate(A["Set_Existing_Next_Uri"]["inputs"]["value"], c2)

    abs_link = ("https://contoso.sharepoint.com/sites/x/_api/web/lists(guid'abc')"
                "/items?$skiptoken=Paged%3dTRUE%26p_ID%3d1000")
    check("P01", "SharePoint の継続リンク（odata.nextLink）をサイト相対に直す",
          next_uri({"value": [], "odata.nextLink": abs_link}),
          "_api/web/lists(guid'abc')/items?$skiptoken=Paged%3dTRUE%26p_ID%3d1000")
    check("P02", "v4形（@odata.nextLink）でも受け取れる",
          next_uri({"value": [], "@odata.nextLink": abs_link}).startswith("_api/"), True)
    check("P03", "verbose 形（d.__next）でも受け取れる",
          next_uri({"d": {"__next": abs_link}}).startswith("_api/"), True)
    check("P04", "継続リンクが無ければ空文字（ループ終了）",
          next_uri({"value": []}), "")

    graph_next = "https://graph.microsoft.com/v1.0/teams/x/channels/y/members?$skiptoken=abc"
    c3 = Context(dict(base_vars),
                 bodies={"Get_Graph_Members_Page": {"value": [], "@odata.nextLink": graph_next}})
    check("P05", "Graph の継続リンクは完全URLのまま次の要求に使う",
          evaluate(A["Set_Graph_Members_NextLink"]["inputs"]["value"], c3), graph_next)
    c4 = Context(dict(base_vars), bodies={"Get_Graph_Members_Page": {"value": []}})
    check("P06", "Graph の継続リンクが無ければ空文字（ループ終了）",
          evaluate(A["Set_Graph_Members_NextLink"]["inputs"]["value"], c4), "")
    check("P07", "Do until の終了条件が「継続リンクが空」になっている",
          A["Do_Until_Existing_Paging"]["expression"],
          "@empty(variables('varExistingNextUri'))")

    print("-" * 78)
    failed = [r for r in results if not r[0]]
    print("合格 %d / 不合格 %d（全 %d 件）" % (len(results) - len(failed), len(failed), len(results)))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
