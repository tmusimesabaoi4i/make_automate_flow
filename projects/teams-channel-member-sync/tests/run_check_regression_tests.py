# -*- coding: utf-8 -*-
"""
静的検査そのものが機能することを証明する回帰テスト。

「validate が全緑だった」は「自分が思いついた観点は通った」でしかない
（handbook/knowledge/lessons_learned.md §27）。そこで、生成済みの定義を **わざと壊し**、
対応する検査が実際に発火することを1件ずつ確かめる。発火しない検査は
「書いてあるだけで守っていない検査」なので、ここで落とす。

  python run_check_regression_tests.py
"""
import copy
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..", "..", "..", "tools")))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..", "shared")))
sys.path.insert(0, os.path.abspath(os.path.join(
    HERE, "..", "flows", "setup-and-test-sync", "source")))

import flow_checks as fc  # noqa: E402
import validate_setup_flow as vsf  # noqa: E402

PKG = os.path.join(HERE, "..", "flows", "setup-and-test-sync", "source", "package")

results = []


def load_doc():
    flows_dir = os.path.join(PKG, "Microsoft.Flow", "flows")
    guid = [d for d in os.listdir(flows_dir) if os.path.isdir(os.path.join(flows_dir, d))][0]
    with open(os.path.join(flows_dir, guid, "definition.json"), encoding="utf-8") as f:
        return json.load(f)


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


def run_check(kind, definition, doc):
    if kind == "syntax":
        return fc.check_expression_syntax(definition)[0]
    if kind == "substring":
        return fc.check_substring_safety(definition)[0]
    if kind == "connector":
        return fc.check_connector_calls(definition, True)[0]
    if kind == "guard":
        return fc.check_deactivate_guard(definition)
    if kind == "values":
        return fc.check_no_real_values(definition, doc)
    if kind == "variables":
        return fc.check_variables_and_references(definition)[0]
    if kind == "setup":
        return vsf.extra_checks(definition, doc)
    if kind == "configview":
        return fc.check_config_list_and_view(definition, True)
    raise ValueError(kind)


def expect_detected(cid, desc, kind, code, mutate):
    doc = load_doc()
    definition = doc["properties"]["definition"]
    actions = walk(definition["actions"], {})
    mutate(definition, actions, doc)
    errors = run_check(kind, definition, doc)
    hit = [e for e in errors if e.startswith(code)]
    ok = bool(hit)
    results.append((ok, cid))
    print("%s %s %s" % ("PASS" if ok else "FAIL", cid, desc))
    if not ok:
        print("     %s が発火しなかった。検出されたのは: %s" % (code, errors[:3] or "(なし)"))
    return ok


def main():
    if not os.path.isdir(PKG):
        print("パッケージが未生成です: %s" % PKG)
        return 1

    print("=" * 78)
    print("静的検査の回帰テスト（わざと壊して、検査が発火することを確かめる）")
    print("=" * 78)

    # --- P02 式の構文 ---
    expect_detected(
        "R01", "括弧の数を1つ減らすと式の構文検査が発火する", "syntax", "P02",
        lambda d, a, doc: a["Compose_Validation_Code"].__setitem__(
            "inputs", a["Compose_Validation_Code"]["inputs"][:-1]))
    expect_detected(
        "R02", "関数名の後の '(' を消すと式の構文検査が発火する", "syntax", "P02",
        lambda d, a, doc: a["Compose_Config_Key"].__setitem__(
            "inputs", "@concat variables('varTeamId'))"))

    # --- P03 破壊的 REST ---
    expect_detected(
        "R03", "メソッドを DELETE にすると破壊的操作の検査が発火する", "connector", "P03",
        lambda d, a, doc: a["Create_Member_Item"]["inputs"]["parameters"].__setitem__(
            "parameters/method", "DELETE"))
    expect_detected(
        "R04", "URIに deleteObject を混ぜると破壊的操作の検査が発火する", "connector", "P03",
        lambda d, a, doc: a["Create_Member_Item"]["inputs"]["parameters"].__setitem__(
            "parameters/uri",
            "@concat('_api/web/lists(guid''', variables('varListId'), ''')/deleteObject()')"))
    expect_detected(
        "R05", "X-HTTP-Method を DELETE にすると検査が発火する", "connector", "P03",
        lambda d, a, doc: a["Update_Member_Item"]["inputs"]["parameters"][
            "parameters/headers"].__setitem__("X-HTTP-Method", "DELETE"))

    # --- P04 書き込みはリストIDで特定する ---
    expect_detected(
        "R06", "書き込みURIを GetByTitle にすると検査が発火する", "connector", "P04",
        lambda d, a, doc: a["Create_Member_Item"]["inputs"]["parameters"].__setitem__(
            "parameters/uri",
            "@concat('_api/web/lists/GetByTitle(''', variables('varListName'), ''')/items')"))

    # --- P05 想定外の API ---
    expect_detected(
        "R07", "想定していない REST を呼ぶと検査が発火する", "connector", "P05",
        lambda d, a, doc: a["Get_All_Lists_Member"]["inputs"]["parameters"].__setitem__(
            "parameters/uri", "_api/web/siteusers"))

    # --- P06 dataset ---
    expect_detected(
        "R08", "dataset にサイトURLを直接書くと検査が発火する", "connector", "P06",
        lambda d, a, doc: a["Get_All_Lists_Member"]["inputs"]["parameters"].__setitem__(
            "dataset", "https://contoso.sharepoint.com/sites/x"))

    # --- P07 ボディの作り方 ---
    expect_detected(
        "R09", "ボディを文字列連結で作ると検査が発火する", "connector", "P07",
        lambda d, a, doc: a["Create_Member_Item"]["inputs"]["parameters"].__setitem__(
            "parameters/body", "@concat('{\"Title\":\"', variables('varListName'), '\"}')"))

    # --- P08 Graph の宛先 ---
    expect_detected(
        "R10", "Graph 以外のホストを指すと検査が発火する", "connector", "P08",
        lambda d, a, doc: a["Get_Channel_Info"]["inputs"]["parameters"].__setitem__(
            "Uri", "@concat('https://evil.example.com/teams/', variables('varTeamId'))"))
    expect_detected(
        "R11", "チャネルIDの uriComponent を外すと検査が発火する", "connector", "P08",
        lambda d, a, doc: a["Get_Channel_Info"]["inputs"]["parameters"].__setitem__(
            "Uri", "@concat('https://graph.microsoft.com/v1.0/teams/', variables('varTeamId'),"
                   " '/channels/', variables('varChannelId'))"))

    # --- P09 離脱ガード ---
    def move_out_of_guard(d, a, doc):
        scope10 = a["Scope_10_DeactivateLeft"]
        victim = a["Update_Left_Member_Item"]
        del a["Foreach_Left_Member"]["actions"]["Update_Left_Member_Item"]
        victim["runAfter"] = {}
        scope10["actions"]["Update_Left_Member_Item"] = victim

    expect_detected(
        "R12", "無効化をガードの外へ出すと検査が発火する", "guard", "P09", move_out_of_guard)
    expect_detected(
        "R13", "ガード条件から件数チェックを外すと検査が発火する", "guard", "P09",
        lambda d, a, doc: a["Compose_Can_Deactivate"].__setitem__(
            "inputs", a["Compose_Can_Deactivate"]["inputs"].replace(
                "greater(variables('varMemberCount'), 0),", "")))

    # --- P10 ListMembers のパラメータ ---
    expect_detected(
        "R14", "threadType を推測値に変えると検査が発火する", "connector", "P10",
        lambda d, a, doc: a["Teams_List_Channel_Members"]["inputs"]["parameters"].__setitem__(
            "threadType", "Channel"))
    expect_detected(
        "R15", "body/recipient/channelId を落とすと検査が発火する", "connector", "P10",
        lambda d, a, doc: a["Teams_List_Channel_Members"]["inputs"]["parameters"].pop(
            "body/recipient/channelId"))

    # --- P11 / P12 テナント固有値 ---
    expect_detected(
        "R16", "Compose_AdminSiteUrl に値を入れたまま出すと検査が発火する", "values", "P11",
        lambda d, a, doc: a["Compose_AdminSiteUrl"].__setitem__(
            "inputs", "https://contoso.sharepoint.com/sites/admin"))
    expect_detected(
        "R17", "定義にサイトURLの実値が混ざると検査が発火する", "values", "P12",
        lambda d, a, doc: a["Compose_Config_Title"].__setitem__(
            "inputs", "contoso.sharepoint.com"))
    expect_detected(
        "R18", "定義にメールアドレスが混ざると検査が発火する", "values", "P12",
        lambda d, a, doc: a["Compose_Config_Title"].__setitem__(
            "inputs", "owner@contoso.example"))
    expect_detected(
        "R19", "定義にGUID実値が混ざると検査が発火する", "values", "P12",
        lambda d, a, doc: a["Compose_Config_Title"].__setitem__(
            "inputs", "11111111-2222-3333-4444-555555555555"))

    # --- P13 変数と参照 ---
    expect_detected(
        "R20", "未初期化の変数を参照すると検査が発火する", "variables", "P13",
        lambda d, a, doc: a["Compose_Config_Title"].__setitem__(
            "inputs", "@variables('varNotInitialized')"))
    expect_detected(
        "R21", "存在しないアクションを参照すると検査が発火する", "variables", "P13",
        lambda d, a, doc: a["Compose_Config_Title"].__setitem__(
            "inputs", "@outputs('Compose_Does_Not_Exist')"))

    # --- P16 substring の番兵（2026-08-04 の実発生エラーの再発防止） ---
    expect_detected(
        "R23", "substring から番兵を外すと検査が発火する", "substring", "P16",
        lambda d, a, doc: a["Compose_Admin_Cut"].__setitem__(
            "inputs", "@substring(outputs('Compose_Admin_NoQuery'), 0,"
                      " outputs('Compose_Admin_CutIndex'))"))

    # --- S05 / S06 インポート後の手作業なしで動くこと（2026-08-04 の実発生） ---
    expect_detected(
        "R24", "管理サイト未指定時の退避を消すと検査が発火する", "setup", "S05",
        lambda d, a, doc: a["Compose_Config_Site_Resolved"].__setitem__(
            "inputs", "@outputs('Compose_Admin_SiteRoot')"))
    expect_detected(
        "R25", "管理サイト未設定を失敗として扱うと検査が発火する", "setup", "S05",
        lambda d, a, doc: a["Set_Bootstrap_ErrorCode"]["inputs"].__setitem__(
            "value", "ERR_ADMIN_SITE_NOT_SET"))
    expect_detected(
        "R26", "次の操作の案内を消すと検査が発火する", "setup", "S06",
        lambda d, a, doc: d["actions"]["Scope_Finalize"]["actions"].pop("Compose_Next_Action"))

    # --- P17 / P18 設定リストの一致と、取得項目の表示 ---
    expect_detected(
        "R27", "既定ビューへの列追加を消すと検査が発火する", "configview", "P18",
        lambda d, a, doc: a["Condition_Has_ListId_Member"]["actions"].pop(
            "Foreach_View_Field_Member"))
    expect_detected(
        "R28", "ビューの作り直し（removeAllViewFields）を混ぜると検査が発火する",
        "configview", "P18",
        lambda d, a, doc: a["Get_List_Views_Member"]["inputs"]["parameters"].__setitem__(
            "parameters/uri",
            "@concat('_api/web/lists(guid''', variables('varListId'),"
            " ''')/views/defaultView/viewfields/removeAllViewFields()')"))
    expect_detected(
        "R29", "設定リストを別サイトから引くと検査が発火する", "configview", "P17",
        lambda d, a, doc: a["Get_Config_Items"]["inputs"]["parameters"].__setitem__(
            "dataset", "@variables('varSiteUrl')"))

    # --- P14 Apply to each の並列 ---
    expect_detected(
        "R22", "Apply to each の並列オフを外すと検査が発火する", "connector", "P14",
        lambda d, a, doc: a["Foreach_Member"].__setitem__(
            "runtimeConfiguration", {"concurrency": {"repetitions": 20}}))

    print("-" * 78)
    failed = [r for r in results if not r[0]]
    print("合格 %d / 不合格 %d（全 %d 件）"
          % (len(results) - len(failed), len(failed), len(results)))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
