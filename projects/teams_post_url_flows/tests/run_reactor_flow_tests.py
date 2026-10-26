# -*- coding: utf-8 -*-
"""
Flow3（リアクションした人の一覧化）の通し回帰テスト。

生成済み definition.json の**トップレベルから最後まで**を、Graph 応答をダミーに差し替えて
tools/wdl_eval.py で評価し、最終的な varResultObject / varResultJson が期待どおりかを検証する。
URL解析の網羅は run_url_parse_tests.py（flow3 も対象）が担当し、本テストは
「投稿取得 → メンバー取得 → 重複排除・集約 → 結果JSON / エラーハンドラ」の配線を見る。

  python run_reactor_flow_tests.py

runAfter の状態遷移（Succeeded / Failed / Skipped）と Scope の失敗伝播を簡易に再現する。
反復が Failed になったときに Do until 自身が止まるか続くかは実機で未確認のため、
  strict : 反復が Failed なら Until は Failed で止まる
  lenient: 反復の失敗を無視し、終了条件だけで止まる
の両モードで全ケースを評価する（どちらでも結果が同じになることを確認）。

【確認できること】 定義中の式と配線が、想定した Graph 応答から produce する結果。
【確認できないこと】 Graph の実際の応答形・権限・Power Automate 実機の挙動（要実環境確認）。
"""
import json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..", "..", "..", "tools")))
from wdl_eval import Context, evaluate, eval_condition   # noqa: E402

PKG = os.path.join(HERE, "..", "flows", "flow3-list-post-reactors", "source", "package")

CH_ENC = "19%3Aabc123def456%40thread.tacv2"
TENANT = "11111111-1111-1111-1111-111111111111"
GROUP = "22222222-2222-2222-2222-222222222222"
PARENT_ID = "1706000000000"
URL = ("https://teams.microsoft.com/l/message/%s/%s?tenantId=%s&groupId=%s&parentMessageId=%s"
       % (CH_ENC, PARENT_ID, TENANT, GROUP, PARENT_ID))
MEMBERS_URI = "https://graph.microsoft.com/v1.0/teams/%s/channels/%s/members" % (GROUP, CH_ENC)
MEMBERS_NEXT = MEMBERS_URI + "?$skiptoken=page2"

UA, UB, UC = ("aaaaaaaa-0000-0000-0000-00000000000a", "bbbbbbbb-0000-0000-0000-00000000000b",
              "cccccccc-0000-0000-0000-00000000000c")


def reaction(uid, rtype, at):
    # Graph chatMessageReaction の形（user.user.displayName は null で返る想定）
    return {"reactionType": rtype, "displayName": rtype.capitalize(), "reactionContentUrl": None,
            "createdDateTime": at,
            "user": {"application": None, "device": None,
                     "user": {"id": uid, "displayName": None, "userIdentityType": "aadUser"}}}


def member(uid, name, mail):
    return {"@odata.type": "#microsoft.graph.aadUserConversationMember", "id": "m-" + uid,
            "roles": [], "displayName": name, "userId": uid, "email": mail}


def message(reactions):
    return {"id": PARENT_ID, "createdDateTime": "2026-10-01T00:00:00Z", "subject": "週次連絡",
            "deletedDateTime": None, "webUrl": "https://teams.microsoft.com/l/message/x",
            "from": {"user": {"id": UA, "displayName": "投稿者"}}, "reactions": reactions}


# =========================================================================
# 簡易ランタイム
# =========================================================================
def topo_order(container):
    order, done = [], set()
    pending = list(container.keys())
    while pending:
        progressed = False
        for name in list(pending):
            deps = container[name].get("runAfter", {}).keys()
            if all(d in done for d in deps):
                order.append(name)
                done.add(name)
                pending.remove(name)
                progressed = True
        if not progressed:
            raise ValueError("runAfter が循環している: %s" % pending)
    return order


def deep(node, ctx):
    if isinstance(node, dict):
        return {k: deep(v, ctx) for k, v in node.items()}
    if isinstance(node, list):
        return [deep(v, ctx) for v in node]
    return evaluate(node, ctx)


class Runtime(object):
    def __init__(self, mock, strict_until=False):
        self.mock = mock
        self.strict_until = strict_until
        self.calls = []

    def with_item(self, ctx, item, fn):
        saved = ctx.current_item
        ctx.current_item = item
        try:
            return fn()
        finally:
            ctx.current_item = saved

    def run_action(self, name, a, ctx):
        """戻り値: (状態, 内部に Failed があったか)"""
        t = a.get("type")
        if t == "InitializeVariable":
            for v in a["inputs"]["variables"]:
                ctx.variables[v["name"]] = deep(v["value"], ctx)
        elif t == "Compose":
            ctx.outputs[name] = deep(a["inputs"], ctx)
        elif t == "SetVariable":
            ctx.variables[a["inputs"]["name"]] = deep(a["inputs"]["value"], ctx)
        elif t == "AppendToArrayVariable":
            ctx.variables[a["inputs"]["name"]].append(deep(a["inputs"]["value"], ctx))
        elif t == "Scope":
            return self.run_container(a["actions"], ctx)
        elif t == "If":
            branch = a["actions"] if eval_condition(a["expression"], ctx) \
                else a.get("else", {}).get("actions", {})
            return self.run_container(branch, ctx)
        elif t == "Query":
            src = deep(a["inputs"]["from"], ctx) or []
            res = [x for x in src if self.with_item(ctx, x, lambda: evaluate(a["inputs"]["where"], ctx))]
            ctx.bodies[name] = res
            ctx.outputs[name] = {"body": res}
        elif t == "Select":
            src = deep(a["inputs"]["from"], ctx) or []
            res = [self.with_item(ctx, x, lambda: deep(a["inputs"]["select"], ctx)) for x in src]
            ctx.bodies[name] = res
            ctx.outputs[name] = {"body": res}
        elif t == "Foreach":
            any_failed = False
            for it in deep(a["foreach"], ctx) or []:
                ctx.loop_items[name] = it
                st, inner = self.with_item(ctx, it, lambda: self.run_container(a["actions"], ctx))
                any_failed = any_failed or inner
                if st == "Failed":
                    return "Failed", True
            ctx.loop_items.pop(name, None)
            return "Succeeded", any_failed
        elif t == "Until":
            for _ in range(min(a["limit"]["count"], 50)):
                st, inner = self.run_container(a["actions"], ctx)
                if st == "Failed" and self.strict_until:
                    return "Failed", True
                if evaluate(a["expression"], ctx):
                    return "Succeeded", inner
            raise AssertionError("Do until が終了しない（無限ループの疑い）: %s" % name)
        elif t == "OpenApiConnection":
            params = deep(a["inputs"]["parameters"], ctx)
            self.calls.append((name, params["Uri"]))
            ok, code, body = self.mock(name, params["Uri"])
            ctx.outputs[name] = {"statusCode": code, "headers": {}, "body": body}
            ctx.bodies[name] = body
            return ("Succeeded" if ok else "Failed"), not ok
        else:
            raise ValueError("未対応のアクション種別: %s (%s)" % (t, name))
        return "Succeeded", False

    def run_container(self, container, ctx):
        statuses, any_failed = {}, False
        for name in topo_order(container):
            a = container[name]
            ra = a.get("runAfter", {})
            if all(statuses[p] in sts for p, sts in ra.items()):
                st, inner = self.run_action(name, a, ctx)
                any_failed = any_failed or inner or st == "Failed"
            else:
                st = "Skipped"
            statuses[name] = st
        # コンテナの状態は「末端アクション（兄弟の誰からも runAfter されない）」で決まる。
        # 末端が Skipped なら runAfter を遡り、原因が Failed なら Failed とする
        # （直列 Scope の前段失敗で後段が Skipped になり、ハンドラが発火する前提と同じ規則）。
        referenced = {p for a in container.values() for p in a.get("runAfter", {})}

        def resolve(n):
            st = statuses[n]
            if st != "Skipped":
                return st
            preds = container[n].get("runAfter", {}).keys()
            return "Failed" if any(resolve(p) == "Failed" for p in preds) else "Succeeded"

        failed = any(resolve(n) == "Failed" for n in container if n not in referenced)
        return ("Failed" if failed else "Succeeded"), any_failed


def load_definition():
    flows_dir = os.path.join(PKG, "Microsoft.Flow", "flows")
    guid = [d for d in os.listdir(flows_dir) if os.path.isdir(os.path.join(flows_dir, d))][0]
    with open(os.path.join(flows_dir, guid, "definition.json"), encoding="utf-8") as f:
        return json.load(f)["properties"]["definition"]


def make_mock(msg_ok=True, msg_code=200, reactions=(), members_pages=None, members_code=200):
    """members_pages: [[member, ...], [member, ...]]。None ならメンバー取得は members_code で失敗"""
    def mock(name, uri):
        if name == "Get_Parent_Message":
            if not msg_ok:
                return False, msg_code, {"error": {"code": "NotFound"}}
            return True, 200, message(list(reactions))
        if name == "Get_Channel_Members":
            if members_pages is None:
                return False, members_code, {"error": {"code": "Forbidden"}}
            if uri == MEMBERS_URI:
                page, nxt = members_pages[0], (MEMBERS_NEXT if len(members_pages) > 1 else None)
            elif uri == MEMBERS_NEXT:
                page, nxt = members_pages[1], None
            else:
                raise AssertionError("想定外のメンバー取得URI: %s" % uri)
            body = {"value": page}
            if nxt:
                body["@odata.nextLink"] = nxt
            return True, 200, body
        raise AssertionError("想定外のコネクタ呼び出し: %s" % name)
    return mock


def run_case(definition, url, mock, strict_until=False):
    rt = Runtime(mock, strict_until)
    ctx = Context(trigger_body={"TeamsPostUrl": url})
    rt.run_container(definition["actions"], ctx)
    result = ctx.variables["varResultObject"]
    if json.loads(ctx.variables["varResultJson"]) != result:
        raise AssertionError("varResultJson が varResultObject と一致しない")
    return result, rt.calls


# =========================================================================
# ケース
# =========================================================================
R_AL = reaction(UA, "like", "2026-10-01T01:00:00Z")
R_AH = reaction(UA, "heart", "2026-10-01T01:05:00Z")
R_BL = reaction(UB, "like", "2026-10-01T02:00:00Z")
R_CL = reaction(UC, "laugh", "2026-10-01T03:00:00Z")
M_A = member(UA, "山田 太郎", "taro.yamada@example.com")
M_B = member(UB, "佐藤 花子", "hanako.sato@example.com")


def by_id(result):
    return {r["userId"]: r for r in result["reactors"]}


def case_t01(d, strict):
    """同一人物の複数リアクションを1人にまとめ、2ページのメンバー一覧から表示名・メールを補う"""
    res, calls = run_case(d, URL, make_mock(reactions=[R_AL, R_AH, R_BL], members_pages=[[M_A], [M_B]]),
                          strict)
    assert res["success"] is True, res
    assert res["reactorCount"] == 2 and res["reactionCount"] == 3, res
    a, b = by_id(res)[UA], by_id(res)[UB]
    assert (a["displayName"], a["email"], a["reactionCount"]) == ("山田 太郎", "taro.yamada@example.com", 2), a
    assert [r["reactionType"] for r in a["reactions"]] == ["like", "heart"], a
    assert (b["email"], b["memberLookup"]) == ("hanako.sato@example.com", "found"), b
    assert [r["userId"] for r in res["reactors"]] == [UA, UB], "初出順を保つ"
    assert res["memberLookup"] == {"loaded": True, "httpStatusCode": "200", "memberCount": 2}, res
    assert res["warnings"] == [], res
    assert ("Get_Channel_Members", MEMBERS_URI) in calls and ("Get_Channel_Members", MEMBERS_NEXT) in calls
    assert res["message"]["subject"] == "週次連絡"


def case_t02(d, strict):
    """メンバー一覧が 403 → 失敗にせず userId だけで返し、警告を付ける"""
    res, calls = run_case(d, URL, make_mock(reactions=[R_AL, R_BL], members_pages=None, members_code=403),
                          strict)
    assert res["success"] is True, res
    assert res["reactorCount"] == 2, res
    for r in res["reactors"]:
        assert (r["displayName"], r["email"], r["memberLookup"]) == ("", "", "unavailable"), r
    assert res["memberLookup"]["loaded"] is False and res["memberLookup"]["httpStatusCode"] == "403", res
    assert len(res["warnings"]) == 1 and res["warnings"][0].startswith("WARN_MEMBER_LOOKUP_FAILED"), res
    assert sum(1 for c in calls if c[0] == "Get_Channel_Members") == 1, "失敗後に再試行ループしない"


def case_t03(d, strict):
    """リアクション0件 → メンバー一覧を取得せず、空の一覧で成功"""
    res, calls = run_case(d, URL, make_mock(reactions=[], members_pages=[[M_A]]), strict)
    assert res["success"] is True and res["reactors"] == [] and res["reactorCount"] == 0, res
    assert res["warnings"] == [], res
    assert not any(c[0] == "Get_Channel_Members" for c in calls), calls


def case_t04(d, strict):
    """メンバー一覧に居ない人（退出者・ゲスト等）は notFound・メール空で残す"""
    res, _ = run_case(d, URL, make_mock(reactions=[R_AL, R_CL], members_pages=[[M_A, M_B]]), strict)
    c = by_id(res)[UC]
    assert (c["displayName"], c["email"], c["memberLookup"]) == ("", "", "notFound"), c
    assert by_id(res)[UA]["memberLookup"] == "found"


def case_t05(d, strict):
    """URL解析エラー → Graph を呼ばずにエラー結果"""
    res, calls = run_case(d, "https://example.com/x", make_mock(), strict)
    assert res["success"] is False and res["error"]["code"] == "ERR_NOT_TEAMS_URL", res
    assert calls == [], calls


def case_t06(d, strict):
    """投稿取得 404 → エラーハンドラが ERR_MESSAGE_NOT_FOUND を返す（メンバー取得は呼ばない）"""
    res, calls = run_case(d, URL, make_mock(msg_ok=False, msg_code=404), strict)
    assert res["success"] is False and res["error"]["code"] == "ERR_MESSAGE_NOT_FOUND", res
    assert [c[0] for c in calls] == ["Get_Parent_Message"], calls


CASES = [("T01", case_t01), ("T02", case_t02), ("T03", case_t03),
         ("T04", case_t04), ("T05", case_t05), ("T06", case_t06)]

if __name__ == "__main__":
    if not os.path.isdir(PKG):
        print("FATAL: パッケージ未生成。先に build_flow3.py を実行してください:", PKG)
        sys.exit(1)
    definition = load_definition()
    passed = failed = 0
    for mode, strict in (("lenient", False), ("strict", True)):
        for cid, fn in CASES:
            try:
                fn(definition, strict)
                passed += 1
                print("PASS [%s] %s %s" % (mode, cid, fn.__doc__))
            except Exception as e:                  # noqa: BLE001
                failed += 1
                print("FAIL [%s] %s %s -> %s: %s" % (mode, cid, fn.__doc__, type(e).__name__, e))
    print("-" * 78)
    print("合計: 合格 %d / 不合格 %d" % (passed, failed))
    sys.exit(1 if failed else 0)
