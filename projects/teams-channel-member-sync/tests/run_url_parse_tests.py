# -*- coding: utf-8 -*-
"""
URL解析・正規化ロジックの回帰テスト（要件§16.1）。

生成済み definition.json から Scope_00 / Scope_01 / Scope_02 / Scope_03 のアクション列を
読み出し、tools/wdl_eval.py（案件横断のWDL式ミニ評価器）で
**定義に実際に書かれている式そのもの** を評価する。
設計書を再実装して検証するのではなく、生成物を検証する
（handbook/knowledge/lessons_learned.md §23）。

  python run_url_parse_tests.py

【確認できること】 入力URLから定義の式チェーンが produce する値。
【確認できないこと】 Power Automate 実機での挙動（要実環境確認）。
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..", "..", "..", "tools")))
from wdl_eval import Context, evaluate, eval_condition  # noqa: E402

PKG = os.path.join(HERE, "..", "flows", "setup-and-test-sync", "source", "package")

# テスト用のダミー値（実値ではない）
TEAM = "22222222-2222-2222-2222-222222222222"
TENANT = "11111111-1111-1111-1111-111111111111"
CH_ENC = "19%3Aabc123def456%40thread.tacv2"
CH_DEC = "19:abc123def456@thread.tacv2"
ADMIN = "https://contoso.sharepoint.com/sites/admin-site"
SITE = "https://contoso.sharepoint.com/sites/meti_pjteam_000000000"
OK = "-"


def team_url(path_ch=CH_ENC, query="tenantId=%s&groupId=%s" % (TENANT, TEAM),
             host="teams.microsoft.com", tail="/conversations"):
    q = ("?" + query) if query else ""
    return "https://%s/l/team/%s%s%s" % (host, path_ch, tail, q)


# (ID, 説明, TeamsチャネルURL, SharePointサイトURL, 期待値)
CASES = [
    # ---------------- Teams チャネルURL ----------------
    ("T01", "通常のTeamsチャネルURL", team_url(), SITE,
     {"varTeamId": TEAM, "varChannelId": CH_DEC, "varTenantId": TENANT,
      "varSiteUrl": SITE, "varErrorCode": OK}),

    ("T02", "URLエンコードされたチャネルID（%3A / %40）を復号できる", team_url(), SITE,
     {"varChannelId": CH_DEC, "varErrorCode": OK}),

    ("T03", "クエリパラメーターの順序が異なる（groupId が先頭）",
     team_url(query="groupId=%s&tenantId=%s" % (TEAM, TENANT)), SITE,
     {"varTeamId": TEAM, "varTenantId": TENANT, "varErrorCode": OK}),

    ("T04", "余分なクエリパラメーターがあっても解析できる",
     team_url(query="groupId=%s&tenantId=%s&allowXTenantAccess=false&ngc=true&label=x"
                    % (TEAM, TENANT)), SITE,
     {"varTeamId": TEAM, "varTenantId": TENANT, "varChannelId": CH_DEC, "varErrorCode": OK}),

    ("T05", "groupId が無いURL → ERR_GROUPID_NOT_FOUND",
     team_url(query="tenantId=%s" % TENANT), SITE,
     {"varErrorCode": "ERR_GROUPID_NOT_FOUND"}),

    ("T06", "tenantId が無いURL → 任意項目なので正常（テナントIDは空）",
     team_url(query="groupId=%s" % TEAM), SITE,
     {"varTeamId": TEAM, "varTenantId": "", "varErrorCode": OK}),

    ("T07", "チャネルIDが取得できないURL（/l/team/ が無い） → ERR_CHANNELID_NOT_FOUND",
     "https://teams.microsoft.com/l/channel/foo/conversations?groupId=%s" % TEAM, SITE,
     {"varErrorCode": "ERR_CHANNELID_NOT_FOUND"}),

    ("T08", "Teams以外のURL → ERR_NOT_TEAMS_URL",
     "https://example.com/l/team/%s/conversations?groupId=%s" % (CH_ENC, TEAM), SITE,
     {"varErrorCode": "ERR_NOT_TEAMS_URL"}),

    ("T09", "末尾スラッシュ・フラグメント付きでも解析できる",
     team_url(tail="/conversations/") + "#anchor", SITE,
     {"varTeamId": TEAM, "varChannelId": CH_DEC, "varErrorCode": OK}),

    ("T10", "非エンコードのチャネルID（':' '@' が生）でも解析できる",
     team_url(path_ch=CH_DEC), SITE,
     {"varChannelId": CH_DEC, "varErrorCode": OK}),

    ("T11", "新Teamsドメイン（teams.cloud.microsoft）でも解析できる",
     team_url(host="teams.cloud.microsoft"), SITE,
     {"varTeamId": TEAM, "varChannelId": CH_DEC, "varErrorCode": OK}),

    ("T12", "groupId がGUIDでない → ERR_GROUPID_INVALID",
     team_url(query="groupId=not-a-guid&tenantId=%s" % TENANT), SITE,
     {"varErrorCode": "ERR_GROUPID_INVALID"}),

    ("T13", "チャットのURL（チャネルIDの形式でない） → ERR_CHANNELID_INVALID",
     "https://teams.microsoft.com/l/team/19%%3Aaaa_bbb%%40unq.gbl.spaces/conversations"
     "?groupId=%s&tenantId=%s" % (TEAM, TENANT), SITE,
     {"varErrorCode": "ERR_CHANNELID_INVALID"}),

    ("T14", "tenantId の形式が不正 → 誤った値を使わず空にする",
     team_url(query="groupId=%s&tenantId=abc" % TEAM), SITE,
     {"varTeamId": TEAM, "varTenantId": "", "varErrorCode": OK}),

    ("T15", "TeamsチャネルURLが空 → ERR_CHANNEL_URL_EMPTY", "   ", SITE,
     {"varErrorCode": "ERR_CHANNEL_URL_EMPTY"}),

    # ---------------- SharePoint サイトURL ----------------
    ("S01", "通常のSharePointサイトURL", team_url(), SITE,
     {"varSiteUrl": SITE, "varErrorCode": OK}),

    ("S02", "/_layouts/15/viewlsts.aspx を含むURL → サイトルートへ正規化",
     team_url(), SITE + "/_layouts/15/viewlsts.aspx?view=14",
     {"varSiteUrl": SITE, "varErrorCode": OK}),

    ("S03", "クエリパラメーターを含むURL → クエリを落とす",
     team_url(), SITE + "?param=1&other=2",
     {"varSiteUrl": SITE, "varErrorCode": OK}),

    ("S04", "SharePoint以外のURL → ERR_NOT_SHAREPOINT_URL",
     team_url(), "https://example.com/sites/foo",
     {"varErrorCode": "ERR_NOT_SHAREPOINT_URL"}),

    ("S05", "リストの一覧画面URL（/Lists/<名前>/AllItems.aspx）→ サイトルートへ正規化",
     team_url(), SITE + "/Lists/MyList/AllItems.aspx",
     {"varSiteUrl": SITE, "varErrorCode": OK}),

    ("S06", "末尾スラッシュを落とす", team_url(), SITE + "/",
     {"varSiteUrl": SITE, "varErrorCode": OK}),

    ("S07", "/teams/ 形式のサイトURL",
     team_url(), "https://contoso.sharepoint.com/teams/pjteam_000/_layouts/15/viewlsts.aspx",
     {"varSiteUrl": "https://contoso.sharepoint.com/teams/pjteam_000", "varErrorCode": OK}),

    ("S08", "大文字混じりの /_Layouts/ でも切り落とせる（判定は小文字化して行う）",
     team_url(), SITE + "/_Layouts/15/viewlsts.aspx",
     {"varSiteUrl": SITE, "varErrorCode": OK}),

    ("S09", "サイト名の後ろに余分なパスがあっても1セグメントで打ち切る",
     team_url(), SITE + "/SitePages/Home.aspx",
     {"varSiteUrl": SITE, "varErrorCode": OK}),

    ("S10", "ルートサイト（/sites/ も /teams/ も無い）",
     team_url(), "https://contoso.sharepoint.com/_layouts/15/viewlsts.aspx",
     {"varSiteUrl": "https://contoso.sharepoint.com", "varErrorCode": OK}),

    ("S11", "SharePointサイトURLが空 → ERR_SITE_URL_EMPTY", team_url(), "",
     {"varErrorCode": "ERR_SITE_URL_EMPTY"}),

    # ---------------- 設定リストを置くサイトの決定 ----------------
    # 【2026-08-04】以前は管理サイト未設定を ERR_ADMIN_SITE_NOT_SET として失敗させていた。
    # 「インポート後に手で設定しないと1回も動かない」設計だったため、実行が2回続けて止まった。
    # 未設定を既定として成立させ、同期先サイトへ倒すよう変更した。
    ("A01", "管理サイトが未設定でも失敗しない（同期先サイトへ倒す）", team_url(), SITE,
     {"varConfigSiteUrl": SITE, "varAdminSiteSource": "target-site", "varErrorCode": OK}, ""),

    ("A02", "管理サイトURLがSharePointでない → ERR_ADMIN_SITE_NOT_SHAREPOINT",
     team_url(), SITE, {"varErrorCode": "ERR_ADMIN_SITE_NOT_SHAREPOINT"},
     "https://example.com/sites/admin"),

    ("A03", "管理サイトURLも管理画面URLからサイトルートへ正規化される",
     team_url(), SITE,
     {"varConfigSiteUrl": ADMIN, "varAdminSiteSource": "compose-admin-site",
      "varErrorCode": OK},
     ADMIN + "/_layouts/15/viewlsts.aspx?view=14"),

    ("A04", "トリガー入力の管理サイトが Compose より優先される", team_url(), SITE,
     {"varConfigSiteUrl": ADMIN, "varAdminSiteSource": "trigger-input", "varErrorCode": OK},
     "https://contoso.sharepoint.com/sites/other-admin", ADMIN),

    ("A05", "トリガー入力の管理サイトも一覧画面URLから正規化される", team_url(), SITE,
     {"varConfigSiteUrl": ADMIN, "varAdminSiteSource": "trigger-input", "varErrorCode": OK},
     "", ADMIN + "/Lists/Settings/AllItems.aspx"),

    ("A06", "管理サイトが未設定で同期先が一覧画面URLでも、正規化後のサイトへ倒す",
     team_url(), SITE + "/_layouts/15/viewlsts.aspx?view=14",
     {"varConfigSiteUrl": SITE, "varSiteUrl": SITE, "varAdminSiteSource": "target-site",
      "varErrorCode": OK}, ""),
]


def topo_order(container):
    names = list(container.keys())
    placed, result, guard = set(), [], 0
    while len(result) < len(names) and guard < 10000:
        guard += 1
        for n in names:
            if n in placed:
                continue
            if all(t in placed for t in container[n].get("runAfter", {}).keys()):
                result.append(n)
                placed.add(n)
    result += [n for n in names if n not in placed]
    return result


def evaluate_deep(node, ctx):
    if isinstance(node, dict):
        return {k: evaluate_deep(v, ctx) for k, v in node.items()}
    if isinstance(node, list):
        return [evaluate_deep(v, ctx) for v in node]
    return evaluate(node, ctx)


def run_container(container, ctx):
    for name in topo_order(container):
        a = container[name]
        t = a.get("type")
        if t == "Compose":
            ctx.outputs[name] = evaluate_deep(a["inputs"], ctx)
        elif t == "SetVariable":
            ctx.variables[a["inputs"]["name"]] = evaluate(a["inputs"]["value"], ctx)
        elif t == "AppendToArrayVariable":
            ctx.variables[a["inputs"]["name"]].append(evaluate(a["inputs"]["value"], ctx))
        elif t == "IncrementVariable":
            ctx.variables[a["inputs"]["name"]] += a["inputs"].get("value", 1)
        elif t == "If":
            if eval_condition(a["expression"], ctx):
                run_container(a.get("actions", {}), ctx)
            else:
                run_container(a.get("else", {}).get("actions", {}), ctx)
        elif t == "Scope":
            run_container(a.get("actions", {}), ctx)
        else:
            raise ValueError("テスト実行器が未対応のアクション種別: %s (%s)" % (t, name))


def load_definition(pkg_dir):
    flows_dir = os.path.join(pkg_dir, "Microsoft.Flow", "flows")
    guid = [d for d in os.listdir(flows_dir) if os.path.isdir(os.path.join(flows_dir, d))][0]
    with open(os.path.join(flows_dir, guid, "definition.json"), encoding="utf-8") as f:
        return json.load(f)["properties"]["definition"]


def main():
    if not os.path.isdir(PKG):
        print("パッケージが未生成です: %s" % PKG)
        return 1
    definition = load_definition(PKG)
    top = definition["actions"]

    passed = failed = 0
    print("=" * 78)
    print("URL解析・正規化テスト（definition.json の式をそのまま評価）")
    print("=" * 78)

    for case in CASES:
        cid, desc, ch_url, site_url = case[0], case[1], case[2], case[3]
        expected = case[4]
        admin_url = case[5] if len(case) > 5 else ADMIN      # Compose_AdminSiteUrl の値
        admin_input = case[6] if len(case) > 6 else ""       # トリガー入力の値
        ctx = Context(trigger_body={"TeamsChannelUrl": ch_url,
                                    "SharePointSiteUrl": site_url,
                                    "SharePointListName": "Teams チャネルメンバー",
                                    "AdminSiteUrl": admin_input})
        try:
            for name in topo_order(top):
                a = top[name]
                if a.get("type") != "InitializeVariable":
                    continue
                for v in a["inputs"]["variables"]:
                    ctx.variables[v["name"]] = evaluate(v["value"], ctx)
            # インポート後に設定される値を注入する（ZIP には空文字で入っている）
            ctx.outputs["Compose_AdminSiteUrl"] = admin_url
            for scope_name in ("Scope_00_Bootstrap", "Scope_01_ValidateInput",
                               "Scope_02_ParseTeamsUrl", "Scope_03_ParseSharePointUrl",
                               "Scope_03A_ResolveConfigSite"):
                run_container(top[scope_name]["actions"], ctx)

            diffs = []
            for key, want in expected.items():
                got = ctx.variables.get(key)
                if key == "varErrorCode" and want == OK:
                    want = ""
                if got != want:
                    diffs.append("    %s: 期待=%r / 実際=%r" % (key, want, got))
            if diffs:
                failed += 1
                print("FAIL %s %s" % (cid, desc))
                print("     teams=%s" % ch_url)
                print("     site =%s" % site_url)
                for d in diffs:
                    print(d)
            else:
                passed += 1
                print("PASS %s %s" % (cid, desc))
        except Exception as e:  # noqa: BLE001
            failed += 1
            print("FAIL %s %s -> 例外: %s: %s" % (cid, desc, type(e).__name__, e))
            print("     teams=%s" % ch_url)
            print("     site =%s" % site_url)

    print("-" * 78)
    print("合格 %d / 不合格 %d（全 %d 件）" % (passed, failed, len(CASES)))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
