# -*- coding: utf-8 -*-
"""
入力検証・URL正規化・ODataエスケープの回帰テスト（オフライン）。

生成済み definition.json から Scope_Validate_Input のアクション列と
$filter を組み立てるURI式を読み出し、tools/wdl_eval.py（案件横断のWDL式ミニ評価器）で
**定義に実際に書かれている式そのもの**を評価して検証する。設計書の再実装は検証しない。

  python run_offline_tests.py

【確認できること】
  定義中の式チェーンが入力から produce する値（サイトURL・エラーコード・件数・エスケープ結果）。
【確認できないこと】
  Power Automate 実機での挙動、SharePoint REST / Outlook / Content Conversion の応答、
  メールの降順整列（sort/reverse は wdl_eval 未実装）。いずれも要実環境確認。
"""
import json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
# WDL式評価器は案件横断の共通ツール（tools/wdl_eval.py）。案件ごとに複製しない。
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..", "..", "..", "tools")))
from wdl_eval import Context, evaluate, eval_condition   # noqa: E402

PKG = os.path.join(HERE, "..", "flows", "sync-mail-to-list", "source", "package")

TENANT = "https://contoso.sharepoint.com"
SITE = TENANT + "/sites/sample_pjteam_000000000"
MAILBOX = "shared-mailbox@contoso.example.com"
OK = "-"      # エラーコードが空であること

# (ID, 説明, {SharePointUrl, ListName, SharedMailboxAddress, MailCount}, 期待値dict)
CASES = [
    # ---------------- URL 正常系（指示§4.1） ----------------
    ("U01", "サイトのルートURL", SITE, "MailList", MAILBOX, 3,
     {"varSiteUrl": SITE, "varSiteOrigin": TENANT, "varErrorCode": OK}),
    ("U02", "リスト一覧ページURL（viewlsts.aspx）",
     SITE + "/_layouts/15/viewlsts.aspx", "MailList", MAILBOX, 3,
     {"varSiteUrl": SITE, "varErrorCode": OK}),
    ("U03", "クエリ文字列付きリスト一覧ページ",
     SITE + "/_layouts/15/viewlsts.aspx?view=14", "MailList", MAILBOX, 3,
     {"varSiteUrl": SITE, "varErrorCode": OK}),
    ("U04", "フラグメント付きURL",
     SITE + "/_layouts/15/viewlsts.aspx#top", "MailList", MAILBOX, 3,
     {"varSiteUrl": SITE, "varErrorCode": OK}),
    ("U05", "クエリとフラグメントの両方",
     SITE + "/_layouts/15/viewlsts.aspx?view=14#top", "MailList", MAILBOX, 3,
     {"varSiteUrl": SITE, "varErrorCode": OK}),
    ("U06", "末尾スラッシュ", SITE + "/", "MailList", MAILBOX, 3,
     {"varSiteUrl": SITE, "varErrorCode": OK}),
    ("U07", "前後に空白がある",
     "   " + SITE + "/_layouts/15/viewlsts.aspx   ", "MailList", MAILBOX, 3,
     {"varSiteUrl": SITE, "varErrorCode": OK}),
    ("U08", "_Layouts の表記ゆれ（大文字L）",
     SITE + "/_Layouts/15/viewlsts.aspx", "MailList", MAILBOX, 3,
     {"varSiteUrl": SITE, "varErrorCode": OK}),
    ("U09", "_LAYOUTS の表記ゆれ（全大文字）",
     SITE + "/_LAYOUTS/15/viewlsts.aspx", "MailList", MAILBOX, 3,
     {"varSiteUrl": SITE, "varErrorCode": OK}),
    ("U10", "サブサイトのリスト一覧ページ",
     SITE + "/subsite01/_layouts/15/viewlsts.aspx", "MailList", MAILBOX, 3,
     {"varSiteUrl": SITE + "/subsite01", "varErrorCode": OK}),
    ("U11", "テナントルートサイト", TENANT, "MailList", MAILBOX, 3,
     {"varSiteUrl": TENANT, "varSiteOrigin": TENANT, "varErrorCode": OK}),
    ("U12", "サイトルートにクエリだけが付く", SITE + "?foo=bar", "MailList", MAILBOX, 3,
     {"varSiteUrl": SITE, "varErrorCode": OK}),
    # ---------------- URL 異常系（指示§23 テスト5） ----------------
    ("U13", "URLが空", "", "MailList", MAILBOX, 3, {"varErrorCode": "ERR_URL_EMPTY"}),
    ("U14", "URLが空白のみ", "     ", "MailList", MAILBOX, 3, {"varErrorCode": "ERR_URL_EMPTY"}),
    ("U15", "https でない（http）", "http://contoso.sharepoint.com/sites/x",
     "MailList", MAILBOX, 3, {"varErrorCode": "ERR_URL_NOT_HTTPS"}),
    ("U16", "SharePoint以外のホスト", "https://example.com/sites/x",
     "MailList", MAILBOX, 3, {"varErrorCode": "ERR_URL_NOT_SHAREPOINT"}),
    ("U17", "sharepoint.com に似た別ホスト（別テナント偽装）",
     "https://sharepoint.com.evil.example/sites/x", "MailList", MAILBOX, 3,
     {"varErrorCode": "ERR_URL_NOT_SHAREPOINT"}),
    ("U18", "userinfo を含む不正URL",
     "https://user@contoso.sharepoint.com/sites/x", "MailList", MAILBOX, 3,
     {"varErrorCode": "ERR_URL_MALFORMED"}),

    # ---------------- リスト名（指示§4.2） ----------------
    ("L01", "英数字のリスト名", SITE, "MailArchive2026", MAILBOX, 3,
     {"varListName": "MailArchive2026", "varErrorCode": OK}),
    ("L02", "日本語のリスト名", SITE, "メール台帳", MAILBOX, 3,
     {"varListName": "メール台帳", "varErrorCode": OK}),
    ("L03", "空白を含むリスト名", SITE, "Mail Archive 2026", MAILBOX, 3,
     {"varListName": "Mail Archive 2026", "varErrorCode": OK}),
    ("L04", "前後の空白は除去される", SITE, "   MailList   ", MAILBOX, 3,
     {"varListName": "MailList", "varErrorCode": OK}),
    ("L05", "リスト名が空", SITE, "", MAILBOX, 3, {"varErrorCode": "ERR_LISTNAME_EMPTY"}),
    ("L06", "リスト名が空白のみ", SITE, "    ", MAILBOX, 3,
     {"varErrorCode": "ERR_LISTNAME_EMPTY"}),
    ("L07", "禁止文字（スラッシュ）", SITE, "Mail/List", MAILBOX, 3,
     {"varErrorCode": "ERR_LISTNAME_INVALID_CHARS"}),
    ("L08", "禁止文字（山括弧）", SITE, "Mail<List>", MAILBOX, 3,
     {"varErrorCode": "ERR_LISTNAME_INVALID_CHARS"}),
    ("L09", "禁止文字（ダブルクォート）", SITE, 'Mail"List', MAILBOX, 3,
     {"varErrorCode": "ERR_LISTNAME_INVALID_CHARS"}),
    ("L10", "制御文字（タブ）", SITE, "Mail\tList", MAILBOX, 3,
     {"varErrorCode": "ERR_LISTNAME_INVALID_CHARS"}),
    ("L11", "255文字超", SITE, "A" * 256, MAILBOX, 3,
     {"varErrorCode": "ERR_LISTNAME_TOO_LONG"}),
    ("L12", "先頭がピリオド", SITE, ".MailList", MAILBOX, 3,
     {"varErrorCode": "ERR_LISTNAME_INVALID_PERIOD"}),
    ("L13", "予約名", SITE, "forms", MAILBOX, 3,
     {"varErrorCode": "ERR_LISTNAME_RESERVED"}),

    # ---------------- 共有メールボックス（指示§4.3） ----------------
    ("M01", "正常なメールアドレス", SITE, "MailList", MAILBOX, 3, {"varErrorCode": OK}),
    ("M02", "アドレスが空", SITE, "MailList", "", 3, {"varErrorCode": "ERR_MAILBOX_EMPTY"}),
    ("M03", "アドレスが空白のみ", SITE, "MailList", "   ", 3,
     {"varErrorCode": "ERR_MAILBOX_EMPTY"}),
    ("M04", "@ が無い", SITE, "MailList", "sharedmailbox.example.com", 3,
     {"varErrorCode": "ERR_MAILBOX_INVALID"}),
    ("M05", "@ が複数", SITE, "MailList", "a@b@contoso.example.com", 3,
     {"varErrorCode": "ERR_MAILBOX_INVALID"}),
    ("M06", "ドメインにピリオドが無い", SITE, "MailList", "shared@localhost", 3,
     {"varErrorCode": "ERR_MAILBOX_INVALID"}),
    ("M07", "ローカル部が空", SITE, "MailList", "@contoso.example.com", 3,
     {"varErrorCode": "ERR_MAILBOX_INVALID"}),

    # ---------------- 取得件数（指示§4.4・§23 テスト6） ----------------
    ("C01", "1件（下限）", SITE, "MailList", MAILBOX, 1,
     {"varRequestedCount": 1, "varErrorCode": OK}),
    ("C02", "100件（上限）", SITE, "MailList", MAILBOX, 100,
     {"varRequestedCount": 100, "varErrorCode": OK}),
    ("C03", "0件", SITE, "MailList", MAILBOX, 0, {"varErrorCode": "ERR_COUNT_INVALID"}),
    ("C04", "負数", SITE, "MailList", MAILBOX, -5, {"varErrorCode": "ERR_COUNT_INVALID"}),
    ("C05", "小数", SITE, "MailList", MAILBOX, 3.5, {"varErrorCode": "ERR_COUNT_INVALID"}),
    ("C06", "数値以外の文字列", SITE, "MailList", MAILBOX, "abc",
     {"varErrorCode": "ERR_COUNT_INVALID"}),
    ("C07", "上限超過（101）", SITE, "MailList", MAILBOX, 101,
     {"varErrorCode": "ERR_COUNT_TOO_LARGE"}),
    ("C08", "桁あふれ（20桁）", SITE, "MailList", MAILBOX, "99999999999999999999",
     {"varErrorCode": "ERR_COUNT_TOO_LARGE"}),
    ("C09", "未指定（null）", SITE, "MailList", MAILBOX, None,
     {"varErrorCode": "ERR_COUNT_INVALID"}),

    # ---------------- 優先順位 ----------------
    ("P01", "URLエラーがリスト名エラーより優先される", "", "Mail/List", MAILBOX, 3,
     {"varErrorCode": "ERR_URL_EMPTY"}),
    ("P02", "リスト名エラーがメールボックスエラーより優先される", SITE, "", "", 3,
     {"varErrorCode": "ERR_LISTNAME_EMPTY"}),
]

# ODataエスケープのテスト（指示§15）。$filter の値に危険な文字が入っても壊れないこと。
LIST_ID = "11111111-2222-3333-4444-555555555555"
ESCAPE_CASES = [
    ("O01", "通常のInternet Message Id", "<abc123@contoso.example.com>"),
    ("O02", "シングルクォートを含む", "<o'brien'test@contoso.example.com>"),
    ("O03", "アンパサンドを含む", "<a&b&c@contoso.example.com>"),
    ("O04", "山括弧とスペースを含む", "<a b <c> d@contoso.example.com>"),
    ("O05", "日本語を含む", "<日本語のID@contoso.example.com>"),
    ("O06", "絵文字を含む", "<id-🎉-test@contoso.example.com>"),
    ("O07", "ダブルクォートと%を含む", '<a"b%c@contoso.example.com>'),
    ("O08", "長いID（250文字）", "<" + "x" * 240 + "@a.example.com>"),
]

PREFIX = "_api/web/lists(guid'" + LIST_ID + "')/items?$select=Id&$top=2&$filter=MessageId eq '"


# =========================================================================
# 定義から式を読み出して評価する最小実行器
# =========================================================================
def topo_order(container):
    names = list(container.keys())
    placed, order, guard = set(), [], 0
    while len(order) < len(names) and guard < 10000:
        guard += 1
        for n in names:
            if n in placed:
                continue
            if all(t in placed for t in container[n].get("runAfter", {}).keys()):
                order.append(n)
                placed.add(n)
    if len(order) != len(names):
        raise ValueError("runAfter が循環している: %s" % [n for n in names if n not in placed])
    return order


def evaluate_deep(node, ctx):
    if isinstance(node, dict):
        return {k: evaluate_deep(v, ctx) for k, v in node.items()}
    if isinstance(node, list):
        return [evaluate_deep(v, ctx) for v in node]
    if isinstance(node, str):
        return evaluate(node, ctx)
    return node


def run_container(container, ctx):
    for name in topo_order(container):
        a = container[name]
        t = a.get("type")
        if t == "Compose":
            ctx.outputs[name] = evaluate_deep(a["inputs"], ctx)
        elif t == "SetVariable":
            ctx.variables[a["inputs"]["name"]] = evaluate_deep(a["inputs"]["value"], ctx)
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


def find_action(container, target):
    for name, a in container.items():
        if name == target:
            return a
        if isinstance(a, dict):
            for key in ("actions",):
                if isinstance(a.get(key), dict):
                    r = find_action(a[key], target)
                    if r is not None:
                        return r
            if isinstance(a.get("else"), dict):
                r = find_action(a["else"].get("actions", {}), target)
                if r is not None:
                    return r
    return None


def init_variables(top, ctx):
    for name in topo_order(top):
        a = top[name]
        if a.get("type") != "InitializeVariable":
            continue
        for v in a["inputs"]["variables"]:
            val = v["value"]
            ctx.variables[v["name"]] = evaluate(val, ctx) if isinstance(val, str) else val


def main():
    if not os.path.isdir(PKG):
        print("FATAL: パッケージ未生成。先に build_sync_flow.py を実行してください:", PKG)
        return 1
    definition = load_definition()
    top = definition["actions"]

    passed = failed = 0
    print("=" * 78)
    print("入力検証テスト（definition.json の式をそのまま評価）")
    print("=" * 78)

    for cid, desc, url, listname, mailbox, count, expected in CASES:
        ctx = Context(trigger_body={"SharePointUrl": url, "ListName": listname,
                                    "SharedMailboxAddress": mailbox, "MailCount": count})
        try:
            init_variables(top, ctx)
            run_container(top["Scope_Validate_Input"]["actions"], ctx)

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
            # 検証NGならエラーメッセージが1件以上積まれていること
            if code and len(ctx.variables.get("varErrorMessages", [])) == 0:
                diffs.append("    エラーなのに varErrorMessages が空")
            if diffs:
                failed += 1
                print("FAIL %s %s" % (cid, desc))
                print("     url=%r list=%r mailbox=%r count=%r" % (url, listname, mailbox, count))
                for d in diffs:
                    print(d)
            else:
                passed += 1
                print("PASS %s %s" % (cid, desc))
        except Exception as e:                                  # noqa: BLE001
            failed += 1
            print("FAIL %s %s -> 例外: %s: %s" % (cid, desc, type(e).__name__, e))
            print("     url=%r list=%r mailbox=%r count=%r" % (url, listname, mailbox, count))

    print()
    print("=" * 78)
    print("ODataエスケープテスト（$filter を組み立てる実際のURI式を評価）")
    print("=" * 78)
    search = find_action(top, "Search_Existing_Item")
    if search is None:
        print("FAIL Search_Existing_Item が定義に存在しない")
        failed += 1
    else:
        uri_expr = search["inputs"]["parameters"]["parameters/uri"]
        for cid, desc, msgid in ESCAPE_CASES:
            ctx = Context(variables={"varListId": LIST_ID}, outputs={"Compose_Message_Id": msgid})
            try:
                got = evaluate(uri_expr, ctx)
                diffs = []
                if not got.startswith(PREFIX):
                    diffs.append("    URIの前半が想定と異なる: %r" % got[:80])
                if not got.endswith("'"):
                    diffs.append("    URIがクォートで閉じていない: %r" % got[-40:])
                value = got[len(PREFIX):-1] if got.startswith(PREFIX) and got.endswith("'") else ""
                # エンコード後の値に生のクォート・&・空白・#・?・山括弧が残っていないこと
                for ch, label in (("'", "シングルクォート"), ("&", "アンパサンド"),
                                  (" ", "空白"), ("#", "シャープ"), ("?", "疑問符"),
                                  ("<", "山括弧(左)"), (">", "山括弧(右)"), ('"', "ダブルクォート")):
                    if ch in value:
                        diffs.append("    エンコード後に生の%sが残っている: %r" % (label, value[:80]))
                # 入力にクォートがあれば %27%27（'' の2重化）が現れること
                if "'" in msgid and "%27%27" not in value:
                    diffs.append("    シングルクォートの2重化（%%27%%27）が行われていない: %r" % value[:80])
                if diffs:
                    failed += 1
                    print("FAIL %s %s" % (cid, desc))
                    for d in diffs:
                        print(d)
                else:
                    passed += 1
                    print("PASS %s %s" % (cid, desc))
            except Exception as e:                              # noqa: BLE001
                failed += 1
                print("FAIL %s %s -> 例外: %s: %s" % (cid, desc, type(e).__name__, e))

    total = len(CASES) + len(ESCAPE_CASES)
    print("-" * 78)
    print("合格 %d / 不合格 %d（全 %d 件）" % (passed, failed, total))
    print()
    print("※ 本テストで確認できないもの（要実環境確認）:")
    print("   - メールの受信日時降順の整列（sort/reverse は wdl_eval 未実装）")
    print("   - SharePoint REST / Outlook / Content Conversion の実応答")
    print("   - 実機での保存可否・インポート可否")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
