# -*- coding: utf-8 -*-
"""
TeamsChannelMemberSync_Setup の静的検証。

  python source/validate_setup_flow.py

エラー0・警告0 が完成条件。エラーがあれば終了コード1で終わる。
検査の中身は次の2つに分かれる。
  - 案件横断の共通検査: tools/wdl_lint.py（L01〜L13 / M01・M02）
  - 本案件固有の検査  : shared/flow_checks.py（P01〜P15）
文章のチェックリストと二重管理しないため、検証の正典はこのスクリプト（が呼ぶ2モジュール）。
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BUILD = os.path.join(HERE, "package")
# tools/ はリポジトリルート直下。source/ から5階層上がる。
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..", "..", "..", "..", "..", "tools")))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..", "..", "..", "shared")))

import flow_checks as fc  # noqa: E402
import sync_blocks as sb  # noqa: E402

EXPECTED_CONN_KEYS = ["shared_teams", "shared_sharepointonline"]

# 要件§12 の「どの単位で失敗したか判別できること」に1対1で対応する Scope。
EXPECTED_SCOPES = [
    "Scope_00_Bootstrap",
    "Scope_01_ValidateInput",
    "Scope_02_ParseTeamsUrl",
    "Scope_03_ParseSharePointUrl",
    "Scope_03A_ResolveConfigSite",
    "Scope_03B_EnsureConfigList",
    "Scope_04_CheckTeamsAccess",
    "Scope_05_EnsureMemberList",
    "Scope_06_GetMembers",
    "Scope_07_NormalizeMembers",
    "Scope_08_GetExistingItems",
    "Scope_09_SyncItems",
    "Scope_10_DeactivateLeft",
    "Scope_11_SaveConfig",
    "Scope_ErrorHandler",
    "Scope_Finalize",
]


def extra_checks(definition, doc):
    """このフローだけの追加検査"""
    errors = []
    raw = json.dumps(doc, ensure_ascii=False)
    trigger = definition.get("triggers", {}).get("manual")
    if trigger is None:
        errors.append("S01 手動トリガー（manual）が無い")
    else:
        if trigger.get("type") != "Request" or trigger.get("kind") != "Button":
            errors.append("S01 トリガーの type/kind が Request/Button でない: %r / %r"
                          % (trigger.get("type"), trigger.get("kind")))
        props = ((trigger.get("inputs") or {}).get("schema") or {}).get("properties") or {}
        required = ((trigger.get("inputs") or {}).get("schema") or {}).get("required") or []
        for key in ("TeamsChannelUrl", "SharePointSiteUrl", "SharePointListName"):
            if key not in props:
                errors.append("S01 トリガー入力 %s が無い" % key)
            if key not in required:
                errors.append("S01 トリガー入力 %s が必須になっていない" % key)

    # 設定の保存は「全段成功」の配下だけで起きる
    from wdl_lint import walk_actions
    nodes = walk_actions(definition.get("actions", {}), "root", 0, [])
    names = {n for n, _, _, _ in nodes}
    by_name = {n: a for n, a, _, _ in nodes}
    for name, _, path, _ in nodes:
        if name in ("Create_Config_Item", "Update_Config_Item"):
            if "Condition_All_Succeeded" not in path:
                errors.append("S02 %s が Condition_All_Succeeded の配下にない: %s" % (name, path))
    for needle in ("equals(variables('varIsValid'), true)",
                   "empty(variables('varFailedStage'))",
                   "equals(variables('varErrorCount'), 0)",
                   "equals(variables('varMembersFetchComplete'), true)"):
        if needle not in raw:
            errors.append("S02 設定保存のガード条件が欠けている: %s" % needle)

    # 設定リストのアイテムを消す経路が存在しないこと
    if re.search(r"Delete_Config|deleteObject|recycle", raw, re.IGNORECASE):
        errors.append("S03 設定リストに対する破壊的操作が定義に含まれている")

    # URL解析が固定位置の分割に頼っていないこと（クエリはアンカー方式）
    if "'&groupId='" not in raw or "'&tenantId='" not in raw:
        errors.append("S04 クエリ解析がアンカー方式（'&<名前>=' で分割）になっていない")
    if "decodeUriComponent" not in raw:
        errors.append("S04 チャネルIDの URL デコードが無い")

    # S05 インポート後の手作業なしで初回実行が完了できること
    #   管理サイトが未指定なら同期先サイトへ倒す。この退避経路が消えると、
    #   「設定しないと1回も動かない」状態に逆戻りする（2026-08-04 の実発生）。
    if "Compose_Config_Site_Resolved" not in names:
        errors.append("S05 管理サイト未指定時の退避（Compose_Config_Site_Resolved）が無い")
    else:
        expr = str(by_name["Compose_Config_Site_Resolved"].get("inputs", ""))
        if "variables('varSiteUrl')" not in expr:
            errors.append("S05 管理サイト未指定時に同期先サイトへ倒していない: %r" % expr[:120])
    if "ERR_ADMIN_SITE_NOT_SET" in raw:
        errors.append("S05 管理サイト未設定を失敗として扱っている"
                      "（未設定でも同期先サイトで動けるようにする）")
    # S06 次にすべきことを実行結果に必ず出す
    if "Compose_Next_Action" not in names:
        errors.append("S06 実行結果に次の操作の案内（Compose_Next_Action）が無い")
    return errors


def main():
    errors, warnings, info = fc.run_all(
        BUILD, EXPECTED_CONN_KEYS,
        expect_listmembers=(sb.MEMBER_SOURCE_MODE == "connector_first"),
        expected_scopes=EXPECTED_SCOPES)

    if info:
        doc_path = os.path.join(BUILD, "Microsoft.Flow", "flows", info["packageGuid"],
                                "definition.json")
        doc = json.load(open(doc_path, encoding="utf-8"))
        errors += extra_checks(doc["properties"]["definition"], doc)

    extra = ["memberSourceMode      : %s" % sb.MEMBER_SOURCE_MODE,
             "configListTitle       : %s" % sb.CONFIG_LIST_TITLE,
             "memberFieldCount      : %d" % len(sb.MEMBER_FIELDS),
             "configFieldCount      : %d" % len(sb.CONFIG_FIELDS)]
    text = fc.report("TeamsChannelMemberSync_Setup", errors, warnings, info, extra)
    print(text)
    out = os.path.abspath(os.path.join(HERE, "..", "validation", "validate_result.txt"))
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        f.write(text + "\n")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
