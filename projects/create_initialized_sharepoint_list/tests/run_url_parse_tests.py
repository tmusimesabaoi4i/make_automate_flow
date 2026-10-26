# -*- coding: utf-8 -*-
"""
URL解析・リスト名検証の回帰テスト。

生成済み definition.json から Scope_Parse_And_Validate_Input のアクション列を読み出し、
tools/wdl_eval.py（案件横断のWDL式ミニ評価器）で「定義に実際に書かれている式そのもの」を
評価して、入力ごとの解析結果・エラーコードが期待どおりかを検証する。

  python run_url_parse_tests.py

【確認できること】 定義中の式チェーンが入力から produce する値。
【確認できないこと】 Power Automate 実機での挙動・SharePoint RESTの応答（要実環境確認）。
"""
import json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
# WDL式評価器は案件横断の共通ツール（tools/wdl_eval.py）。案件ごとに複製しない。
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..", "..", "..", "tools")))
from wdl_eval import Context, evaluate, eval_condition   # noqa: E402

PKG = os.path.join(HERE, "..", "flows", "create-initialized-list", "source", "package")

TENANT = "https://contoso.sharepoint.com"
SITE = TENANT + "/sites/sample_pjteam_000000000"
OK = "-"      # エラーコードが空であること

# (ID, 説明, SharePointUrl, ListName, 期待値dict)
CASES = [
    # ---------------- URL 正常系（§4・§33） ----------------
    ("U01", "リスト一覧ページURL（viewlsts.aspx）",
     SITE + "/_layouts/15/viewlsts.aspx", "SampleList",
     {"varSiteUrl": SITE, "varErrorCode": OK}),

    ("U02", "サイトのルートURL",
     SITE, "SampleList", {"varSiteUrl": SITE, "varErrorCode": OK}),

    ("U03", "URL末尾にスラッシュがある",
     SITE + "/", "SampleList", {"varSiteUrl": SITE, "varErrorCode": OK}),

    ("U04", "クエリパラメーター付きリスト一覧ページ",
     SITE + "/_layouts/15/viewlsts.aspx?view=14", "SampleList",
     {"varSiteUrl": SITE, "varErrorCode": OK}),

    ("U05", "URLの前後に空白がある",
     "   " + SITE + "/_layouts/15/viewlsts.aspx   ", "SampleList",
     {"varSiteUrl": SITE, "varErrorCode": OK}),

    ("U06", "サブサイトのリスト一覧ページ",
     SITE + "/subsite01/_layouts/15/viewlsts.aspx", "SampleList",
     {"varSiteUrl": SITE + "/subsite01", "varErrorCode": OK}),

    ("U07", "サイトルートにクエリだけが付く",
     SITE + "?foo=bar", "SampleList", {"varSiteUrl": SITE, "varErrorCode": OK}),

    ("U08", "フラグメント付きURL",
     SITE + "/_layouts/15/viewlsts.aspx#top", "SampleList",
     {"varSiteUrl": SITE, "varErrorCode": OK}),

    ("U09", "_Layouts の表記ゆれ（大文字L）",
     SITE + "/_Layouts/15/viewlsts.aspx", "SampleList",
     {"varSiteUrl": SITE, "varErrorCode": OK}),

    ("U10", "テナントルートサイト",
     TENANT, "SampleList", {"varSiteUrl": TENANT, "varErrorCode": OK}),

    # 【対象外の形式・既知の限界を記録するケース】
    # 指示書§4が対応を求めるのは「サイトルート／viewlsts.aspx／クエリ付き／サブサイト」。
    # 個別リストのビューURL（/Lists/<名前>/AllItems.aspx）は /_layouts/ を含まないため
    # サイトURLとして切り出せず、URL全体がそのまま siteUrl になる。
    # 解析段階では検出できず、実行時に _api/web が 404 を返して ERR_SITE_OR_RESOURCE_NOT_FOUND
    # で明確に失敗する（誤ったサイトに書き込む危険は無い）。docs に限界として明記する。
    ("U11", "個別リストのビューURL（対象外。実行時に404で失敗する形）",
     SITE + "/Lists/Existing/AllItems.aspx", "SampleList",
     {"varSiteUrl": SITE + "/Lists/Existing/AllItems.aspx", "varErrorCode": OK}),

    # ---------------- URL 異常系（§33） ----------------
    ("E01", "URLが空", "", "SampleList", {"varErrorCode": "ERR_URL_EMPTY"}),
    ("E02", "URLが空白のみ", "    ", "SampleList", {"varErrorCode": "ERR_URL_EMPTY"}),
    ("E03", "https でない（http）",
     "http://contoso.sharepoint.com/sites/x", "SampleList",
     {"varErrorCode": "ERR_NOT_HTTPS"}),
    ("E04", "SharePoint以外のURL",
     "https://example.com/sites/x", "SampleList",
     {"varErrorCode": "ERR_NOT_SHAREPOINT_HOST"}),
    ("E05", "sharepoint.com に似た別ホスト",
     "https://sharepoint.com.evil.example/sites/x", "SampleList",
     {"varErrorCode": "ERR_NOT_SHAREPOINT_HOST"}),

    # ---------------- リスト名 正常系（§33） ----------------
    ("L01", "日本語のリスト名", SITE, "サンプル台帳",
     {"varListName": "サンプル台帳", "varErrorCode": OK}),
    ("L02", "英数字のリスト名", SITE, "SampleList2026",
     {"varListName": "SampleList2026", "varErrorCode": OK}),
    ("L03", "空白を含むリスト名", SITE, "Sample List 2026",
     {"varListName": "Sample List 2026", "varErrorCode": OK}),
    ("L04", "前後の空白は除去して使用する", SITE, "  SampleList  ",
     {"varListName": "SampleList", "varErrorCode": OK}),
    ("L05", "ハイフン・アンダースコアを含む", SITE, "sample-list_01",
     {"varListName": "sample-list_01", "varErrorCode": OK}),

    # ---------------- リスト名 異常系（§6.2・§33） ----------------
    ("N01", "リスト名が空", SITE, "", {"varErrorCode": "ERR_LIST_NAME_EMPTY"}),
    ("N02", "リスト名が空白のみ", SITE, "   ", {"varErrorCode": "ERR_LIST_NAME_EMPTY"}),
    ("N03", "禁止文字（スラッシュ）", SITE, "Sample/List",
     {"varErrorCode": "ERR_LIST_NAME_INVALID_CHARS"}),
    ("N04", "禁止文字（バックスラッシュ）", SITE, "Sample\\List",
     {"varErrorCode": "ERR_LIST_NAME_INVALID_CHARS"}),
    ("N05", "禁止文字（コロン・アスタリスク）", SITE, "Sample:List*",
     {"varErrorCode": "ERR_LIST_NAME_INVALID_CHARS"}),
    ("N06", "禁止文字（二重引用符）", SITE, 'Sample"List',
     {"varErrorCode": "ERR_LIST_NAME_INVALID_CHARS"}),
    ("N07", "制御文字（改行）", SITE, "Sample\nList",
     {"varErrorCode": "ERR_LIST_NAME_INVALID_CHARS"}),
    ("N08", "制御文字（タブ）", SITE, "Sample\tList",
     {"varErrorCode": "ERR_LIST_NAME_INVALID_CHARS"}),
    ("N09", "先頭がピリオド", SITE, ".SampleList",
     {"varErrorCode": "ERR_LIST_NAME_INVALID_PERIOD"}),
    ("N10", "末尾がピリオド", SITE, "SampleList.",
     {"varErrorCode": "ERR_LIST_NAME_INVALID_PERIOD"}),
    ("N11", "予約名（con）", SITE, "con", {"varErrorCode": "ERR_LIST_NAME_RESERVED"}),
    ("N12", "予約名（大文字 NUL）", SITE, "NUL", {"varErrorCode": "ERR_LIST_NAME_RESERVED"}),
    ("N13", "255文字を超えるリスト名", SITE, "A" * 256,
     {"varErrorCode": "ERR_LIST_NAME_TOO_LONG"}),

    # ---------------- 判定順序（URLエラーがリスト名エラーより優先） ----------------
    ("P01", "URLもリスト名も不正 → URL側のコードを返す",
     "https://example.com/x", "Sample/List", {"varErrorCode": "ERR_NOT_SHAREPOINT_HOST"}),
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
    return result + [n for n in names if n not in placed]


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
            ctx.variables[a["inputs"]["name"]].append(evaluate_deep(a["inputs"]["value"], ctx))
        elif t == "If":
            if eval_condition(a["expression"], ctx):
                run_container(a.get("actions", {}), ctx)
            else:
                run_container(a.get("else", {}).get("actions", {}), ctx)
        elif t == "Scope":
            run_container(a.get("actions", {}), ctx)
        else:
            raise ValueError("テスト実行器が未対応のアクション種別: %s (%s)" % (t, name))


def load_definition():
    flows_dir = os.path.join(PKG, "Microsoft.Flow", "flows")
    guid = [d for d in os.listdir(flows_dir) if os.path.isdir(os.path.join(flows_dir, d))][0]
    with open(os.path.join(flows_dir, guid, "definition.json"), encoding="utf-8") as f:
        return json.load(f)["properties"]["definition"]


def main():
    if not os.path.isdir(PKG):
        print("FATAL: パッケージ未生成。先に build_list_flow.py を実行してください:", PKG)
        return 1
    definition = load_definition()
    top = definition["actions"]

    passed = failed = 0
    print("=" * 78)
    print("URL解析・リスト名検証テスト（definition.json の式をそのまま評価）")
    print("=" * 78)

    for cid, desc, url, listname, expected in CASES:
        ctx = Context(trigger_body={"SharePointUrl": url, "ListName": listname,
                                    "ListDescription": None})
        try:
            for name in topo_order(top):
                a = top[name]
                if a.get("type") != "InitializeVariable":
                    continue
                for v in a["inputs"]["variables"]:
                    ctx.variables[v["name"]] = evaluate(v["value"], ctx)
            run_container(top["Scope_Parse_And_Validate_Input"]["actions"], ctx)

            diffs = []
            for key, want in expected.items():
                got = ctx.variables.get(key)
                if key == "varErrorCode" and want == OK:
                    want = ""
                if got != want:
                    diffs.append("    %s: 期待=%r / 実際=%r" % (key, want, got))
            # エラーコードが空でないなら varIsValid は false であること（整合性）
            code = ctx.variables.get("varErrorCode")
            if bool(code) == bool(ctx.variables.get("varIsValid")):
                diffs.append("    varIsValid が varErrorCode と整合しない: code=%r isValid=%r"
                             % (code, ctx.variables.get("varIsValid")))
            if diffs:
                failed += 1
                print("FAIL %s %s" % (cid, desc))
                print("     url=%r listName=%r" % (url, listname))
                for d in diffs:
                    print(d)
            else:
                passed += 1
                print("PASS %s %s" % (cid, desc))
        except Exception as e:                                  # noqa: BLE001
            failed += 1
            print("FAIL %s %s -> 例外: %s: %s" % (cid, desc, type(e).__name__, e))
            print("     url=%r listName=%r" % (url, listname))

    print("-" * 78)
    print("合格 %d / 不合格 %d（全 %d 件）" % (passed, failed, len(CASES)))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
