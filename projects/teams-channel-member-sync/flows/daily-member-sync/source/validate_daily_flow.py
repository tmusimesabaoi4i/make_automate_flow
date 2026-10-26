# -*- coding: utf-8 -*-
"""
TeamsChannelMemberSync_Daily の静的検証。

  python source/validate_daily_flow.py

エラー0・警告0 が完成条件。エラーがあれば終了コード1で終わる。
検査の中身は次の2つに分かれる。
  - 案件横断の共通検査: tools/wdl_lint.py（L01〜L13 / M01・M02）
  - 本案件固有の検査  : shared/flow_checks.py（P01〜P15）
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BUILD = os.path.join(HERE, "package")
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..", "..", "..", "..", "..", "tools")))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..", "..", "..", "shared")))

import flow_checks as fc  # noqa: E402
import sync_blocks as sb  # noqa: E402

EXPECTED_CONN_KEYS = ["shared_teams", "shared_sharepointonline"]

EXPECTED_SCOPES = [
    "Scope_00_Bootstrap",
    "Scope_01_LocateConfigList",
    "Scope_02_ReadConfig",
    "Scope_04_CheckTeamsAccess",
    "Scope_05_EnsureMemberList",
    "Scope_06_GetMembers",
    "Scope_07_NormalizeMembers",
    "Scope_08_GetExistingItems",
    "Scope_09_SyncItems",
    "Scope_10_DeactivateLeft",
    "Scope_11_RecordResult",
    "Scope_ErrorHandler",
    "Scope_Finalize",
]

# 日本で使う前提。UTCとのずれで意図しない日に動かないよう timeZone を明示する。
EXPECTED_TIMEZONE = "Tokyo Standard Time"


def extra_checks(definition, doc):
    errors = []
    raw = json.dumps(doc, ensure_ascii=False)

    trigger = definition.get("triggers", {}).get("Recurrence")
    if trigger is None:
        errors.append("D01 Recurrence トリガーが無い")
    else:
        rec = trigger.get("recurrence", {}) or {}
        if trigger.get("type") != "Recurrence":
            errors.append("D01 トリガーの type が Recurrence でない: %r" % trigger.get("type"))
        if rec.get("frequency") != "Day" or rec.get("interval") != 1:
            errors.append("D01 1日1回になっていない: frequency=%r interval=%r"
                          % (rec.get("frequency"), rec.get("interval")))
        if rec.get("timeZone") != EXPECTED_TIMEZONE:
            errors.append("D01 timeZone が %r でない: %r" % (EXPECTED_TIMEZONE, rec.get("timeZone")))
        sch = rec.get("schedule", {}) or {}
        if not sch.get("hours") or not isinstance(sch.get("hours"), list):
            errors.append("D01 schedule.hours が指定されていない: %r" % sch.get("hours"))
        start = str(rec.get("startTime", ""))
        # timeZone を指定するときは startTime に 'Z' を付けない（付けるとUTC扱いになり
        # timeZone が無視される。learn.microsoft.com/azure/connectors/connectors-native-recurrence）
        if start.endswith("Z"):
            errors.append("D01 timeZone 指定時の startTime に 'Z' が付いている: %r" % start)
        if not re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$", start):
            errors.append("D01 startTime の書式が YYYY-MM-DDThh:mm:ss でない: %r" % start)

    from wdl_lint import walk_actions
    nodes = walk_actions(definition.get("actions", {}), "root", 0, [])
    names = {n for n, _, _, _ in nodes}
    paths = {n: p for n, _, p, _ in nodes}

    # 設定リストを作らない・消さない（定期フローは設定の読み手であって作り手ではない）
    for name, a, _, _ in nodes:
        if a.get("type") != "OpenApiConnection":
            continue
        params = (a.get("inputs", {}) or {}).get("parameters", {}) or {}
        uri = str(params.get("parameters/uri", ""))
        if params.get("dataset") == sb.DS_CONFIG and uri == "_api/web/lists":
            errors.append("D02 %s: 定期フローが設定リストを作成しようとしている" % name)
    if "Create_List_Config" in names:
        errors.append("D02 設定リストの作成アクションが定期フローに含まれている")

    # 設定が0件のときに安全終了する経路があること
    if "Compose_Not_Configured" not in names:
        errors.append("D03 設定未登録時の安全終了（Compose_Not_Configured）が無い")
    if "equals(coalesce(item()?['IsEnabled'], false), true)" not in raw:
        errors.append("D03 有効な設定だけを対象にする絞り込みが無い")

    # 同期処理は設定ループの中にあること（設定ごとに独立して動く）
    for scope_name in ("Scope_04_CheckTeamsAccess", "Scope_09_SyncItems",
                       "Scope_10_DeactivateLeft", "Scope_11_RecordResult"):
        if scope_name in paths and "Foreach_Config" not in paths[scope_name]:
            errors.append("D04 %s が Foreach_Config の中にない: %s" % (scope_name, paths[scope_name]))

    # 1件の設定の失敗が他の設定を巻き込まないこと
    rec_scope = None
    for name, a, _, _ in nodes:
        if name == "Scope_11_RecordResult":
            rec_scope = a
    if rec_scope is not None:
        states = list(rec_scope.get("runAfter", {}).values())
        if not states or sorted(states[0]) != sorted(["Succeeded", "Failed", "Skipped", "TimedOut"]):
            errors.append("D05 Scope_11_RecordResult の runAfter が4状態すべてになっていない: %r"
                          % rec_scope.get("runAfter"))

    # 保存済みの設定であってもサイトURLのホストを検査していること
    if "'.sharepoint.com'" not in raw:
        errors.append("D06 保存済みサイトURLのホスト検査が無い")
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
             "schedule              : 毎日 07:00 / %s" % EXPECTED_TIMEZONE]
    text = fc.report("TeamsChannelMemberSync_Daily", errors, warnings, info, extra)
    print(text)
    out = os.path.abspath(os.path.join(HERE, "..", "validation", "validate_result.txt"))
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        f.write(text + "\n")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
