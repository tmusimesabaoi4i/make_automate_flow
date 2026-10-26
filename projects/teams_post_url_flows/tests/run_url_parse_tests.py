# -*- coding: utf-8 -*-
"""
URL解析ロジックの回帰テスト。

生成済み definition.json から Scope_ParseUrl のアクション列を読み出し、
tools/wdl_eval.py（案件横断のWDL式ミニ評価器）で「定義に実際に書かれている式そのもの」を
評価して、入力URLごとの解析結果が期待どおりかを検証する。

  python run_url_parse_tests.py            # Flow1 / Flow2 / Flow3 のすべてを検証
  python run_url_parse_tests.py flow1      # 片方だけ

【確認できること】 定義中の式チェーンが入力URLから produce する値。
【確認できないこと】 Power Automate 実機での挙動（要実環境確認）。
"""
import json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
# WDL式評価器は案件横断の共通ツール（tools/wdl_eval.py）。案件ごとに複製しない。
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..", "..", "..", "tools")))
from wdl_eval import Context, evaluate, eval_condition   # noqa: E402

FLOWS = {
    "flow1": os.path.join(HERE, "..", "flows", "flow1-get-channel-post", "source", "package"),
    "flow2": os.path.join(HERE, "..", "flows", "flow2-get-post-replies", "source", "package"),
    "flow3": os.path.join(HERE, "..", "flows", "flow3-list-post-reactors", "source", "package"),
}

CH_ENC = "19%3Aabc123def456%40thread.tacv2"
CH_DEC = "19:abc123def456@thread.tacv2"
TENANT = "11111111-1111-1111-1111-111111111111"
GROUP = "22222222-2222-2222-2222-222222222222"
PARENT_ID = "1706000000000"
REPLY_ID = "1706000999000"

OK = "-"   # 正常（エラーコード空）

# (ID, 説明, 入力URL, 期待値dict)
CASES = [
    # ---------------- 正常系 ----------------
    ("N01", "親投稿のURL（parentMessageId が messageId と同値）",
     "https://teams.microsoft.com/l/message/%s/%s?tenantId=%s&groupId=%s&parentMessageId=%s"
     "&teamName=Sales&channelName=General&createdTime=%s" % (CH_ENC, PARENT_ID, TENANT, GROUP, PARENT_ID, PARENT_ID),
     {"varTenantId": TENANT, "varTeamId": GROUP, "varChannelId": CH_DEC,
      "varUrlMessageId": PARENT_ID, "varParentMessageId": PARENT_ID,
      "varTargetMessageId": PARENT_ID, "varErrorCode": OK}),

    ("N02", "返信のURL（parentMessageId が親を指す）→ 親投稿へ解決される",
     "https://teams.microsoft.com/l/message/%s/%s?tenantId=%s&groupId=%s&parentMessageId=%s"
     % (CH_ENC, REPLY_ID, TENANT, GROUP, PARENT_ID),
     {"varUrlMessageId": REPLY_ID, "varParentMessageId": PARENT_ID,
      "varTargetMessageId": PARENT_ID, "varErrorCode": OK}),

    ("N03", "URLエンコードされたチャネルID（%3A / %40）を復号できる",
     "https://teams.microsoft.com/l/message/%s/%s?tenantId=%s&groupId=%s"
     % (CH_ENC, PARENT_ID, TENANT, GROUP),
     {"varChannelId": CH_DEC, "varErrorCode": OK}),

    ("N04", "クエリパラメーターの順番が異なる（groupId が先頭・tenantId が末尾）",
     "https://teams.microsoft.com/l/message/%s/%s?groupId=%s&parentMessageId=%s&tenantId=%s"
     % (CH_ENC, REPLY_ID, GROUP, PARENT_ID, TENANT),
     {"varTenantId": TENANT, "varTeamId": GROUP, "varTargetMessageId": PARENT_ID,
      "varErrorCode": OK}),

    ("N05", "parentMessageId が存在しないURL → パス上の messageId を採用",
     "https://teams.microsoft.com/l/message/%s/%s?tenantId=%s&groupId=%s"
     % (CH_ENC, PARENT_ID, TENANT, GROUP),
     {"varParentMessageId": "", "varTargetMessageId": PARENT_ID, "varErrorCode": OK}),

    ("N06", "parentMessageId=0（親投稿リンクの変種）→ パス上の messageId を採用",
     "https://teams.microsoft.com/l/message/%s/%s?tenantId=%s&groupId=%s&parentMessageId=0"
     % (CH_ENC, PARENT_ID, TENANT, GROUP),
     {"varParentMessageId": "0", "varTargetMessageId": PARENT_ID, "varErrorCode": OK}),

    ("N07", "末尾に追加パラメーターがあっても解析できる",
     "https://teams.microsoft.com/l/message/%s/%s?tenantId=%s&groupId=%s&parentMessageId=%s"
     "&teamName=%%E5%%96%%B6%%E6%%A5%%AD&channelName=General&createdTime=%s&allowXTenantAccess=false"
     % (CH_ENC, REPLY_ID, TENANT, GROUP, PARENT_ID, PARENT_ID),
     {"varTargetMessageId": PARENT_ID, "varTeamId": GROUP, "varErrorCode": OK}),

    ("N08", "非エンコードのチャネルID（':' '@' が生）でも解析できる",
     "https://teams.microsoft.com/l/message/%s/%s?tenantId=%s&groupId=%s"
     % (CH_DEC, PARENT_ID, TENANT, GROUP),
     {"varChannelId": CH_DEC, "varUrlMessageId": PARENT_ID, "varErrorCode": OK}),

    ("N09", "URLの前後に空白がある → trim される",
     "   https://teams.microsoft.com/l/message/%s/%s?tenantId=%s&groupId=%s   "
     % (CH_ENC, PARENT_ID, TENANT, GROUP),
     {"varChannelId": CH_DEC, "varUrlMessageId": PARENT_ID, "varErrorCode": OK}),

    ("N10", "フラグメント（#...）が付いていても解析できる",
     "https://teams.microsoft.com/l/message/%s/%s?tenantId=%s&groupId=%s#anchor"
     % (CH_ENC, PARENT_ID, TENANT, GROUP),
     {"varUrlMessageId": PARENT_ID, "varErrorCode": OK}),

    ("N11", "パス末尾にスラッシュがあっても messageId を取り出せる",
     "https://teams.microsoft.com/l/message/%s/%s/?tenantId=%s&groupId=%s"
     % (CH_ENC, PARENT_ID, TENANT, GROUP),
     {"varUrlMessageId": PARENT_ID, "varErrorCode": OK}),

    ("N12", "新Teamsドメイン（teams.cloud.microsoft）でも解析できる",
     "https://teams.cloud.microsoft/l/message/%s/%s?tenantId=%s&groupId=%s"
     % (CH_ENC, PARENT_ID, TENANT, GROUP),
     {"varChannelId": CH_DEC, "varTargetMessageId": PARENT_ID, "varErrorCode": OK}),

    # ---------------- 異常系 ----------------
    ("E01", "空文字", "", {"varErrorCode": "ERR_URL_EMPTY"}),
    ("E02", "空白のみ", "    ", {"varErrorCode": "ERR_URL_EMPTY"}),

    ("E03", "Teams以外のURL", "https://example.com/some/page?groupId=%s" % GROUP,
     {"varErrorCode": "ERR_NOT_TEAMS_URL"}),

    ("E04", "TeamsのチャットURL（/l/chat/ 形式）",
     "https://teams.microsoft.com/l/chat/19%3Aaaa_bbb%40unq.gbl.spaces/conversations?tenantId=" + TENANT,
     {"varErrorCode": "ERR_NOT_CHANNEL_MESSAGE_URL"}),

    ("E05", "チャットスレッドのメッセージURL（unq.gbl.spaces）",
     "https://teams.microsoft.com/l/message/19%%3Aaaa_bbb%%40unq.gbl.spaces/%s?tenantId=%s"
     % (PARENT_ID, TENANT),
     {"varErrorCode": "ERR_CHAT_URL_NOT_SUPPORTED"}),

    ("E06", "groupId が無いURL",
     "https://teams.microsoft.com/l/message/%s/%s?tenantId=%s" % (CH_ENC, PARENT_ID, TENANT),
     {"varErrorCode": "ERR_GROUPID_NOT_FOUND"}),

    ("E07", "チャネルIDが無いURL",
     "https://teams.microsoft.com/l/message//%s?tenantId=%s&groupId=%s" % (PARENT_ID, TENANT, GROUP),
     {"varErrorCode": "ERR_CHANNELID_NOT_FOUND"}),

    ("E08", "メッセージIDが無いURL",
     "https://teams.microsoft.com/l/message/%s?tenantId=%s&groupId=%s" % (CH_ENC, TENANT, GROUP),
     {"varErrorCode": "ERR_MESSAGEID_NOT_FOUND"}),
]


# =========================================================================
# 定義の実行（Compose / SetVariable / If / AppendToArrayVariable のみ）
# =========================================================================
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
        elif t == "If":
            if eval_condition(a["expression"], ctx):
                run_container(a.get("actions", {}), ctx)
            else:
                run_container(a.get("else", {}).get("actions", {}), ctx)
        elif t == "Scope":
            run_container(a.get("actions", {}), ctx)
        else:
            raise ValueError("テスト実行器が未対応のアクション種別: %s (%s)" % (t, name))


def evaluate_deep(node, ctx):
    """Compose の入力（文字列 / 入れ子オブジェクト）を再帰的に評価する"""
    if isinstance(node, dict):
        return {k: evaluate_deep(v, ctx) for k, v in node.items()}
    if isinstance(node, list):
        return [evaluate_deep(v, ctx) for v in node]
    return evaluate(node, ctx)


def load_definition(pkg_dir):
    flows_dir = os.path.join(pkg_dir, "Microsoft.Flow", "flows")
    guid = [d for d in os.listdir(flows_dir) if os.path.isdir(os.path.join(flows_dir, d))][0]
    with open(os.path.join(flows_dir, guid, "definition.json"), encoding="utf-8") as f:
        return json.load(f)["properties"]["definition"]


def run_flow(flow_key):
    pkg = FLOWS[flow_key]
    if not os.path.isdir(pkg):
        print("SKIP %s: パッケージ未生成 (%s)" % (flow_key, pkg))
        return 0, 0
    definition = load_definition(pkg)
    top = definition["actions"]

    passed = failed = 0
    print("=" * 78)
    print("[%s] URL解析テスト（definition.json の式をそのまま評価）" % flow_key)
    print("=" * 78)

    for cid, desc, url, expected in CASES:
        ctx = Context(trigger_body={"TeamsPostUrl": url})
        try:
            # トップレベルの変数初期化
            for name in topo_order(top):
                a = top[name]
                if a.get("type") != "InitializeVariable":
                    continue
                for v in a["inputs"]["variables"]:
                    ctx.variables[v["name"]] = evaluate(v["value"], ctx)
            # URL解析スコープのみ実行（Graph呼び出し以降はオフラインでは実行しない）
            run_container(top["Scope_ParseUrl"]["actions"], ctx)
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
                print("     URL: %s" % url)
                for d in diffs:
                    print(d)
            else:
                passed += 1
                print("PASS %s %s" % (cid, desc))
        except Exception as e:                      # noqa: BLE001
            failed += 1
            print("FAIL %s %s -> 例外: %s: %s" % (cid, desc, type(e).__name__, e))
            print("     URL: %s" % url)
    print("-" * 78)
    print("[%s] 合格 %d / 不合格 %d（全 %d 件）" % (flow_key, passed, failed, len(CASES)))
    print()
    return passed, failed


if __name__ == "__main__":
    targets = sys.argv[1:] or list(FLOWS.keys())
    total_p = total_f = 0
    for key in targets:
        p, f = run_flow(key)
        total_p += p
        total_f += f
    print("=" * 78)
    print("合計: 合格 %d / 不合格 %d" % (total_p, total_f))
    sys.exit(1 if total_f else 0)
