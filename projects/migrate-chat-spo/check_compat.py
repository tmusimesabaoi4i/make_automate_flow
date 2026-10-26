# -*- coding: utf-8 -*-
"""リスト作成フロー（作る側）とアーカイブフローv8（使う側）の互換性を機械突合する"""
import json, re, os
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
CREATE_DEF = os.path.join(HERE, r"flows\provision-archive-lists\source\package\Microsoft.Flow\flows\7c3e50b2-91a4-4f2e-8f5a-6f1de2a9c4b7\definition.json")
ARCHIVE_DEF = os.path.join(HERE, r"flows\archive-meetings\source\package\Microsoft.Flow\flows\fcca0e31-6d8b-40a8-8d63-2441c979a2c7\definition.json")

issues, notes = [], []

# ============ 作る側の抽出 ============
c = json.loads(open(CREATE_DEF, encoding="utf-8").read())
c_actions = {}
def flatten(cont):
    for k, v in cont.items():
        c_actions[k] = v
        if isinstance(v, dict):
            if "actions" in v: flatten(v["actions"])
            if v.get("type") == "If" and "actions" in v.get("else", {}): flatten(v["else"]["actions"])
flatten(c["properties"]["definition"]["actions"])

created_lists = {}
for pfx in ("Ledger", "RunLog"):
    created_lists[pfx] = c_actions["Compose_" + pfx + "ListTitle"]["inputs"]

created_fields = {"Ledger": {}, "RunLog": {}}
for aname, a in c_actions.items():
    if a.get("type") == "OpenApiConnection":
        body = a["inputs"]["parameters"].get("parameters/body", "")
        if isinstance(body, str) and "SchemaXml" in body:
            el = ET.fromstring(json.loads(body)["parameters"]["SchemaXml"])
            pfx = "Ledger" if "_Ledger_" in aname else "RunLog"
            created_fields[pfx][el.get("Name")] = {"type": el.get("Type"), "required": el.get("Required")}

c_sites = set(re.findall(r'"dataset":\s*"([^"]+)"', open(CREATE_DEF, encoding="utf-8").read()))

# ============ 使う側の抽出 ============
arc = json.loads(open(ARCHIVE_DEF, encoding="utf-8").read())
a_actions = {}
def flatten2(cont):
    for k, v in cont.items():
        a_actions[k] = v
        if isinstance(v, dict):
            if "actions" in v: flatten2(v["actions"])
            if v.get("type") == "If" and "actions" in v.get("else", {}): flatten2(v["else"]["actions"])
flatten2(arc["properties"]["definition"]["actions"])

var_init = {}
for aname, a in a_actions.items():
    if a.get("type") == "InitializeVariable":
        v = a["inputs"]["variables"][0]
        var_init[v["name"]] = v.get("value")

used_lists = {"Ledger": var_init.get("varLedgerList"), "RunLog": var_init.get("varRunLogList")}
list_site_var = var_init.get("varListSiteAddress")
file_site_var = var_init.get("varSiteAddress")

write_cols = {"Ledger": set(), "RunLog": set()}
for aname, target in [("Compose_Ledger_Body", "Ledger"), ("Compose_LedgerFailed_Body", "Ledger"),
                      ("Compose_RunLog_Body", "RunLog"), ("Compose_ErrorLog_Body", "RunLog")]:
    write_cols[target] |= set(a_actions[aname]["inputs"].keys())

numeric_written = set()
for aname in ("Compose_RunLog_Body", "Compose_ErrorLog_Body"):
    for k, v in a_actions[aname]["inputs"].items():
        if isinstance(v, str) and (v.startswith("@length(") or "Count" in v):
            numeric_written.add(k)

gle = a_actions["Get_Ledger_Existing"]["inputs"]["parameters"]
filter_expr = str(gle.get("$filter", ""))
filter_cols = set(re.findall(r"([A-Za-z]+) eq ", filter_expr))
reuse_blob = json.dumps({n: a for n, a in a_actions.items()
                         if "Existing" in n or "Append_Existing" in n})
read_cols = set(re.findall(r"\[.([A-Za-z]+).\]\?\Z", ""))  # placeholder
read_cols = set(re.findall(r"\?\['(SavedFileName|SavedFileUrl)'\]", reuse_blob))
gle_dataset = gle.get("dataset")

rest4 = {}
for aname in ("Create_Ledger_Item", "Create_Ledger_Item_Failed", "Create_Run_Log", "Create_Error_Log"):
    p = a_actions[aname]["inputs"]["parameters"]
    m = re.search(r"variables\('(\w+)'\)", str(p.get("parameters/uri", "")))
    rest4[aname] = {"list_var": m.group(1) if m else None, "dataset": p.get("dataset")}

# ============ 突合 ============
print("=" * 70)
print("互換性突合（作る側=CreateMeetingArchiveLists / 使う側=アーカイブv8）")
print("=" * 70)

print("\n【1】リスト名の一致")
for pfx in ("Ledger", "RunLog"):
    ok = created_lists[pfx] == used_lists[pfx]
    print("  %s: 作る側='%s' / 使う側='%s' -> %s" % (pfx, created_lists[pfx], used_lists[pfx], "一致" if ok else "不一致!!"))
    if not ok: issues.append("リスト名不一致(%s)" % pfx)

print("\n【2】サイトの一致")
create_site = list(c_sites)[0] if len(c_sites) == 1 else None
print("  作る側dataset:", c_sites)
print("  使う側 varListSiteAddress:", list_site_var)
print("  使う側 Get_Ledger_Existing dataset:", gle_dataset)
if create_site != list_site_var:
    issues.append("varListSiteAddressが作成サイトと不一致")
if gle_dataset != "@variables('varListSiteAddress')":
    issues.append("Get_Ledger_Existingがリストサイト変数を使っていない")
for aname, info in rest4.items():
    ok = info["dataset"] == create_site
    print("  使う側 %s: dataset=%s -> %s" % (aname, info["dataset"], "一致" if ok else "不一致!!"))
    if not ok: issues.append("%sのdatasetが作成サイトと不一致" % aname)
print("  （参考）ファイル保存サイト varSiteAddress:", file_site_var, "（別サイト・意図どおり）")

print("\n【3】書き込み先リスト変数の対応")
expect_var = {"Create_Ledger_Item": "varLedgerList", "Create_Ledger_Item_Failed": "varLedgerList",
              "Create_Run_Log": "varRunLogList", "Create_Error_Log": "varRunLogList"}
for aname, want in expect_var.items():
    got = rest4[aname]["list_var"]
    print("  %s: %s -> %s" % (aname, got, "正" if got == want else "取り違え!!"))
    if got != want: issues.append("%sのリスト変数取り違え" % aname)

print("\n【4】列の突合（書き込む列が作成されるか）")
for pfx in ("Ledger", "RunLog"):
    created = set(created_fields[pfx].keys()) | {"Title"}
    written = write_cols[pfx]
    missing = written - created
    extra = set(created_fields[pfx].keys()) - written
    print("  %s: 書き込み%d列 / 作成%d列+Title(既定)" % (pfx, len(written), len(created_fields[pfx])))
    print("    書き込み列:", ", ".join(sorted(written)))
    print("    書き込むのに作られない列:", sorted(missing) if missing else "なし")
    if missing: issues.append("%s: 未作成列への書き込み %s" % (pfx, missing))
    if extra: notes.append("%s: 作成されるが書き込まれない列 %s" % (pfx, sorted(extra)))

print("\n【5】読み取り・$filter列の存在（Ledger）")
ledger_created = set(created_fields["Ledger"].keys()) | {"Title"}
print("  $filter式:", filter_expr)
for colset, label in ((filter_cols, "$filter"), (read_cols, "既存流用の応答参照")):
    miss = colset - ledger_created
    print("  %s列 %s -> %s" % (label, sorted(colset), "全て作成される" if not miss else "未作成!! %s" % miss))
    if miss: issues.append("%s列が未作成: %s" % (label, miss))

print("\n【6】$filter対象列の型（Note型は$filter不可）")
for col in sorted(filter_cols):
    t = created_fields["Ledger"].get(col, {}).get("type")
    print("  %s: %s -> %s" % (col, t, "OK" if t == "Text" else "NG!!"))
    if t != "Text": issues.append("$filter列%sの型が%s" % (col, t))

print("\n【7】数値で書き込む列の型（RunLog）")
for col in sorted(numeric_written):
    t = created_fields["RunLog"].get(col, {}).get("type")
    print("  %s: 書き込み=数値 / 列型=%s -> %s" % (col, t, "OK" if t == "Number" else "NG!!"))
    if t != "Number": issues.append("%sの型不一致" % col)

print("\n【8】空文字が書き込まれ得る列のRequired=FALSE")
for pfx in ("Ledger", "RunLog"):
    for col in ("ReplyId", "SavedFileName", "SavedFileUrl", "ErrorMessage", "ArchiveUrl"):
        if col in created_fields[pfx]:
            r = created_fields[pfx][col]["required"]
            print("  %s.%s: Required=%s -> %s" % (pfx, col, r, "OK" if r == "FALSE" else "NG!!"))
            if r != "FALSE": issues.append("%s.%sがRequired" % (pfx, col))

print("\n【9】Title列の供給（既定リストのTitleは必須）")
for pfx in ("Ledger", "RunLog"):
    has_title = "Title" in write_cols[pfx]
    print("  %s: 書き込みボディにTitle %s" % (pfx, "あり -> OK" if has_title else "なし -> NG!!"))
    if not has_title: issues.append("%sにTitle未供給" % pfx)

print("\n" + "=" * 70)
if issues:
    print("【判定】不一致 %d件:" % len(issues))
    for i in issues: print("  x", i)
else:
    print("【判定】完全互換: 不一致0件")
if notes:
    print("参考:")
    for n in notes: print("  -", n)
