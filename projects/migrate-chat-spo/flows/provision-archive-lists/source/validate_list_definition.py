# -*- coding: utf-8 -*-
"""CreateMeetingArchiveLists パッケージの静的検証（指示§14ベース）。"""
import json, re, os, sys
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
WORK = os.path.join(HERE, "package")

# 案件横断の共通リンター。どのフローにも当てはまる検査はここに集約してある
# （案件ごとに手書きすると同じ穴が再発するため）。
# handbook/checklists/import_save_validation_checklist.md §A
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..", "..", "..", "..", "..", "tools")))
from wdl_lint import lint_definition   # noqa: E402

errors, warnings = [], []

# ---- 1. JSON検証（5ファイル）＋GUID3点一致 ----
root_manifest = json.load(open(os.path.join(WORK, "manifest.json"), encoding="utf-8"))
flows_manifest = json.load(open(os.path.join(WORK, "Microsoft.Flow", "flows", "manifest.json"), encoding="utf-8"))
asset_paths = flows_manifest["flowAssets"]["assetPaths"]
if len(asset_paths) != 1:
    errors.append(f"assetPathsが1件でない: {asset_paths}")
asset_guid = asset_paths[0]

flow_res = [k for k, v in root_manifest["resources"].items() if v.get("type") == "Microsoft.Flow/flows"]
if flow_res != [asset_guid]:
    errors.append(f"GUID3点一致違反: manifest resources={flow_res} vs assetPaths={asset_guid}")
folder = os.path.join(WORK, "Microsoft.Flow", "flows", asset_guid)
if not os.path.isdir(folder):
    errors.append(f"GUID3点一致違反: フォルダ {asset_guid} が存在しない")

defpath = os.path.join(folder, "definition.json")
flow = json.load(open(defpath, encoding="utf-8"))
apis_map = json.load(open(os.path.join(folder, "apisMap.json"), encoding="utf-8"))
conns_map = json.load(open(os.path.join(folder, "connectionsMap.json"), encoding="utf-8"))
raw = open(defpath, encoding="utf-8").read()

# API/接続リソースGUIDの整合
for m, label in ((apis_map, "apisMap"), (conns_map, "connectionsMap")):
    for k, guid in m.items():
        if guid not in root_manifest["resources"]:
            errors.append(f"{label}: GUID {guid} がルートmanifest resourcesに無い")
# 依存関係
flow_deps = root_manifest["resources"][asset_guid]["dependsOn"]
for guid in list(apis_map.values()) + list(conns_map.values()):
    if guid not in flow_deps:
        errors.append(f"フローのdependsOnに {guid} が無い")

d = flow["properties"]["definition"]
actions_root = d["actions"]

# ---- 2. アクション参照検証 ----
all_names, setvar_count, postitem_count = [], 0, 0
foreach_count = 0

def walk(container, path):
    names = set(container.keys())
    for aname, a in container.items():
        all_names.append(aname)
        t = a.get("type")
        global setvar_count, postitem_count, foreach_count
        if t in ("SetVariable", "InitializeVariable", "AppendToArrayVariable", "AppendToStringVariable"):
            setvar_count += 1
        if t == "Foreach":
            foreach_count += 1
        if t == "OpenApiConnection" and a["inputs"]["host"].get("operationId") == "PostItem":
            postitem_count += 1
        ra = a.get("runAfter", {})
        for target, states in ra.items():
            if target not in names:
                errors.append(f"{path}/{aname}: runAfter -> '{target}' が同階層に無い")
            for s in states:
                if s not in ("Succeeded", "Failed", "Skipped", "TimedOut"):
                    errors.append(f"{path}/{aname}: 不正なrunAfterステータス '{s}'")
        if "actions" in a and isinstance(a["actions"], dict):
            walk(a["actions"], f"{path}/{aname}")
        if t == "If" and "else" in a and "actions" in a.get("else", {}):
            walk(a["else"]["actions"], f"{path}/{aname}[else]")

walk(actions_root, "root")
from collections import Counter
dups = [n for n, c in Counter(all_names).items() if c > 1]
if dups:
    errors.append(f"アクション名の重複: {dups}")
if setvar_count:
    errors.append(f"変数系アクションが存在（本フローはCompose統一のはず）: {setvar_count}件")
if postitem_count:
    errors.append(f"PostItemが存在（保存検証で失敗する）: {postitem_count}件")

# outputs()/body() 参照先の実在
name_set = set(all_names)
for m in re.finditer(r"(?:outputs|body)\('([^']+)'\)", raw):
    if m.group(1) not in name_set:
        errors.append(f"未定義アクション参照: {m.group(0)}")

# ネスト@検査（式文字列の先頭/@{以外の@）
def illegal_at(s):
    res, in_lit = [], False
    for i, ch in enumerate(s):
        if ch == "'":
            in_lit = not in_lit
        elif ch == '@' and not in_lit and i > 0 and (i + 1 >= len(s) or s[i + 1] != '{'):
            res.append(i)
    return res

def walk_strings(obj):
    if isinstance(obj, dict):
        for v in obj.values():
            walk_strings(v)
    elif isinstance(obj, list):
        for v in obj:
            walk_strings(v)
    elif isinstance(obj, str) and (obj.startswith('@') or '@{' in obj):
        if obj.startswith('@') and illegal_at(obj):
            errors.append(f"ネスト@の疑い: {obj[:80]}")

walk_strings(d)

# ---- 3. REST検証 ----
knowledge_tokens = ["tmplist", "KnowledgeTag", "KnowledgeTitle", "KnowledgePrimaryTag",
                    "KnowledgeSummary", "KnowledgeBody", "varTagList", "addRowPrimaryTag",
                    "CreateKnowledgeList", "getTagList"]
pkg_all = ""
for root_, _, fs in os.walk(WORK):
    for f in fs:
        pkg_all += open(os.path.join(root_, f), encoding="utf-8").read()
for tok in knowledge_tokens:
    if tok in pkg_all:
        errors.append(f"Knowledge固有トークン残存: '{tok}'")

ledger_x_runlog = 0
def check_rest(container, path):
    global ledger_x_runlog
    for aname, a in container.items():
        if a.get("type") == "OpenApiConnection":
            p = a["inputs"]["parameters"]
            method = p.get("parameters/method")
            uri = str(p.get("parameters/uri", ""))
            headers = p.get("parameters/headers", {})
            body = p.get("parameters/body")
            if "dataset" not in p or not method or "parameters/uri" not in p:
                errors.append(f"{aname}: dataset/method/uri のいずれか欠落")
            if not isinstance(headers, dict):
                errors.append(f"{aname}: headersがオブジェクトでない")
            if method == "POST" and body is None and "removeAllViewFields" not in uri:
                errors.append(f"{aname}: POSTなのにbodyが無い（removeAllViewFields以外）")
            if method == "GET" and body is not None:
                errors.append(f"{aname}: GETにbodyがある")
            # MERGE系はIF-MATCH必須
            if headers.get("X-HTTP-Method") == "MERGE" and headers.get("IF-MATCH") != "*":
                errors.append(f"{aname}: MERGEにIF-MATCH:*が無い")
            # AddViewField/MERGE系ボディはverbose、GET系はnometadata
            if body and "__metadata" in str(body) and "verbose" not in headers.get("Content-Type", ""):
                errors.append(f"{aname}: __metadataボディなのにContent-Typeがverboseでない")
            # 取り違え検査
            if "_Ledger" in aname or "Ledger" in aname:
                if "RunLogListTitle" in json.dumps(a):
                    ledger_x_runlog += 1
                    errors.append(f"{aname}: Ledger系アクションがRunLogのComposeを参照")
            if "RunLog" in aname:
                if "LedgerListTitle" in json.dumps(a):
                    ledger_x_runlog += 1
                    errors.append(f"{aname}: RunLog系アクションがLedgerのComposeを参照")
        if "actions" in a and isinstance(a["actions"], dict):
            check_rest(a["actions"], f"{path}/{aname}")
        if a.get("type") == "If" and "else" in a and "actions" in a.get("else", {}):
            check_rest(a["else"]["actions"], f"{path}/{aname}[else]")

check_rest(actions_root, "root")

# ---- 4. SchemaXml のXML妥当性 ＋ 全RESTボディのJSON妥当性 ----
# parameters/body はJSON文字列として格納されるため、アクションを走査して
# body文字列を json.loads → SchemaXml を取り出して XML パースする。
xml_count = 0
body_json_count = 0
expected_fields = {}  # 内部名 -> 型（生成定義から収集し、後で期待列一覧と突合）

def check_bodies(container, path):
    global xml_count, body_json_count
    for aname, a in container.items():
        if a.get("type") == "OpenApiConnection":
            body = a["inputs"]["parameters"].get("parameters/body")
            if isinstance(body, str) and body.strip().startswith("{"):
                try:
                    parsed = json.loads(body)
                    body_json_count += 1
                except json.JSONDecodeError as e:
                    # Title等に @{...} 補間を含むボディはJSONとしても妥当なはず（値は文字列）
                    errors.append(f"{aname}: parameters/body がJSONとしてパース不能: {e}")
                    continue
                sx = None
                if isinstance(parsed, dict):
                    sx = parsed.get("parameters", {}).get("SchemaXml") if isinstance(parsed.get("parameters"), dict) else None
                if sx:
                    xml_count += 1
                    try:
                        el = ET.fromstring(sx)
                        if el.tag != "Field":
                            errors.append(f"{aname}: SchemaXmlのルートがFieldでない")
                        name = el.get("Name", "")
                        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9]*", name):
                            errors.append(f"{aname}: 内部名が不正（空白/日本語/記号）: '{name}'")
                        expected_fields[name] = el.get("Type", "")
                        # アクション名と列名の一致（取り違え防止）
                        if name not in aname:
                            errors.append(f"{aname}: アクション名と列名'{name}'が不一致")
                    except ET.ParseError as e:
                        errors.append(f"{aname}: SchemaXml XMLパース失敗: {e}")
        if "actions" in a and isinstance(a["actions"], dict):
            check_bodies(a["actions"], f"{path}/{aname}")
        if a.get("type") == "If" and "else" in a and "actions" in a.get("else", {}):
            check_bodies(a["else"]["actions"], f"{path}/{aname}[else]")

check_bodies(actions_root, "root")

# 期待列一覧との突合（両リスト分。作成アクションが漏れなく存在するか）
EXPECT = {
    "Ledger": {"IdempotencyKey": "Text", "RunId": "Text", "MessageId": "Text", "ReplyId": "Text",
               "AttachmentId": "Text", "OriginalFileName": "Text", "SavedFileName": "Text",
               "SavedFileUrl": "Note", "Status": "Text", "ErrorMessage": "Note", "ProcessedDateTimeUtc": "Text"},
    "RunLog": {"RunId": "Text", "FlowName": "Text", "Level": "Text", "Status": "Text",
               "MeetingCount": "Number", "SavedCount": "Number", "SkippedCount": "Number", "FailedCount": "Number",
               "ArchiveUrl": "Note", "ErrorMessage": "Note", "OccurredDateTimeUtc": "Text"},
}
for prefix, cols in EXPECT.items():
    for col, ctype in cols.items():
        act = f"Create_{prefix}_{col}"
        if act not in name_set:
            errors.append(f"列作成アクション欠落: {act}")
if xml_count != 22:
    errors.append(f"SchemaXml数が22でない: {xml_count}（Ledger11＋RunLog11のはず）")
# 型の突合（同名列は両リストで同型のためexpected_fieldsはマージされる）
merged = {}
for cols in EXPECT.values():
    for c, t in cols.items():
        if c in merged and merged[c] != t:
            errors.append(f"期待定義内の型矛盾: {c}")
        merged[c] = t
for name, t in expected_fields.items():
    if merged.get(name) != t:
        errors.append(f"生成された列型が期待と不一致: {name}={t}（期待 {merged.get(name)}）")

# ---- 4b. 追加検査（設計監査の推奨） ----
# コネクタ出力の封筒問題: outputs('OpenApiConnectionアクション')?['プロパティ'] は常にnull
conn_actions = set()
def collect_conn(container):
    for aname, a in container.items():
        if a.get("type") == "OpenApiConnection":
            conn_actions.add(aname)
        if "actions" in a and isinstance(a["actions"], dict):
            collect_conn(a["actions"])
        if a.get("type") == "If" and "else" in a and "actions" in a.get("else", {}):
            collect_conn(a["else"]["actions"])
collect_conn(actions_root)
for m in re.finditer(r"outputs\('([^']+)'\)\?\['([^']+)'\]", raw):
    if m.group(1) in conn_actions and not m.group(2).startswith("body"):
        errors.append(f"コネクタ出力のbody/欠落: outputs('{m.group(1)}')?['{m.group(2)}']")

# SchemaXml: DisplayName==Name（ASCII前提の内部名一致保証）＋ 型別属性の純度
def check_schema_purity(container):
    for aname, a in container.items():
        if a.get("type") == "OpenApiConnection":
            body = a["inputs"]["parameters"].get("parameters/body")
            if isinstance(body, str) and "SchemaXml" in body:
                sx = json.loads(body)["parameters"]["SchemaXml"]
                el = ET.fromstring(sx)
                if el.get("DisplayName") != el.get("Name"):
                    errors.append(f"{aname}: DisplayName!=Name（内部名一致保証が崩れる）")
                t = el.get("Type")
                attrs = set(el.keys())
                if t == "Number" and attrs & {"MaxLength", "RichText", "RichTextMode", "NumLines"}:
                    errors.append(f"{aname}: Number型に異型属性 {attrs}")
                if t == "Text" and attrs & {"RichText", "RichTextMode", "NumLines"}:
                    errors.append(f"{aname}: Text型に異型属性 {attrs}")
                if t == "Note" and attrs & {"MaxLength"}:
                    errors.append(f"{aname}: Note型に異型属性 MaxLength")
        if "actions" in a and isinstance(a["actions"], dict):
            check_schema_purity(a["actions"])
        if a.get("type") == "If" and "else" in a and "actions" in a.get("else", {}):
            check_schema_purity(a["else"]["actions"])
check_schema_purity(actions_root)

# If式が and+equals+length の実績形式か
def check_if_shape(container):
    for aname, a in container.items():
        if a.get("type") == "If":
            expr = a.get("expression", {})
            ok = (isinstance(expr, dict) and "and" in expr and
                  all("equals" in c and str(c["equals"][0]).startswith("@length(")
                      for c in expr["and"]))
            if not ok:
                errors.append(f"{aname}: If式が実績形式（and+equals+length）でない: {json.dumps(expr)[:80]}")
        if "actions" in a and isinstance(a["actions"], dict):
            check_if_shape(a["actions"])
        if a.get("type") == "If" and "else" in a and "actions" in a.get("else", {}):
            check_if_shape(a["else"]["actions"])
check_if_shape(actions_root)

# dataset が全アクションで一致
datasets = set(re.findall(r'"dataset":\s*"([^"]+)"', raw))
if len(datasets) != 1:
    errors.append(f"datasetが不一致: {datasets}")

# ---- 5. トリガー・接続参照 ----
trigs = d.get("triggers", {})
if list(trigs.keys()) != ["manual"] or trigs["manual"].get("kind") != "Button":
    errors.append(f"トリガー不正: {list(trigs.keys())}")
conn_refs = flow["properties"]["connectionReferences"]
if list(conn_refs.keys()) != ["shared_sharepointonline"]:
    errors.append(f"接続参照が想定外: {list(conn_refs.keys())}")
used_conns = set(re.findall(r'"connectionName":\s*"(shared_[^"]+)"', raw))
if used_conns - set(conn_refs.keys()):
    errors.append(f"未定義の接続参照: {used_conns - set(conn_refs.keys())}")

opids = sorted(set(re.findall(r'"operationId":\s*"([^"]+)"', raw)))

print("=== CreateMeetingArchiveLists 静的検証 ===")
print(f"総アクション数(トリガー除く): {len(all_names)}")
print(f"operationId: {opids}")
print(f"SchemaXml検査数: {xml_count} / 変数系アクション: {setvar_count} / PostItem: {postitem_count} / Foreach: {foreach_count}")
print(f"Ledger/RunLog取り違え: {ledger_x_runlog}件")
print(f"GUID3点一致: assetGuid={asset_guid}")

# ---- 共通リンター（tools/wdl_lint.py。L01〜L13） ----
for _msg in lint_definition(flow["properties"]["definition"], raw):
    errors.append("[wdl_lint] " + _msg)

print()
print("=== ERRORS ===")
for e in errors:
    print("  ", e)
print(f"({len(errors)} errors)")
print("=== WARNINGS ===")
for w in warnings:
    print("  ", w)
print(f"({len(warnings)} warnings)")
sys.exit(1 if errors else 0)
