# -*- coding: utf-8 -*-
"""
CreateInitializedSharePointList の展開形パッケージを静的検証する（検証の正典）。

雛形:
  projects/teams_post_url_flows/flows/flow1-get-channel-post/source/validate_flow1.py
  projects/migrate-chat-spo/flows/provision-archive-lists/source/validate_list_definition.py

本フロー固有の主眼は「既存リストを絶対に壊さないこと」の機械化（指示書§36）。
特に次の5つは、設計レビューではなく**走査で0件を保証**する。

  A. 定義中に GetByTitle( が1件も無い（＝リスト名で対象を特定する経路が存在しない）
  B. 書き込み系RESTのURIは必ず variables('varCreatedListId') を含む（新規作成POSTを除く）
  C. リスト作成は varListExists==false のガード配下にある
  D. 初期化・ロールバックは varCreatedInThisRun==true のガード配下にある
  E. 同名リスト確認が リスト作成より runAfter 順で前にある

終了コード: エラーがあれば 1、無ければ 0。
"""
import json, re, os, sys
import xml.etree.ElementTree as ET
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
PKG = os.path.join(HERE, "package")

# 案件横断の共通リンター。どのフローにも当てはまる検査はここに集約してある
# （案件ごとに手書きすると同じ穴が再発するため）。
# handbook/checklists/import_save_validation_checklist.md §A
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..", "..", "..", "..", "..", "tools")))
from wdl_lint import lint_definition   # noqa: E402

errors = []
warnings = []


def fail(msg):
    errors.append(msg)


# =========================================================================
# 0. パッケージ構造・GUID3点一致
# =========================================================================
root_manifest_path = os.path.join(PKG, "manifest.json")
flows_manifest_path = os.path.join(PKG, "Microsoft.Flow", "flows", "manifest.json")
if not os.path.isfile(root_manifest_path) or not os.path.isfile(flows_manifest_path):
    print("FATAL: パッケージが見つかりません。先に build_list_flow.py を実行してください:", PKG)
    sys.exit(1)

root_manifest = json.load(open(root_manifest_path, encoding="utf-8"))
flows_manifest = json.load(open(flows_manifest_path, encoding="utf-8"))

asset_paths = flows_manifest.get("flowAssets", {}).get("assetPaths", [])
root_flow_guids = [k for k, v in root_manifest.get("resources", {}).items()
                   if v.get("hierarchy") == "Root"]
flows_dir = os.path.join(PKG, "Microsoft.Flow", "flows")
folder_guids = sorted(d for d in os.listdir(flows_dir)
                      if os.path.isdir(os.path.join(flows_dir, d)))

if not (sorted(asset_paths) == sorted(root_flow_guids) == folder_guids):
    fail("パッケージGUIDの3点不一致: rootManifest(Root)=%s / フォルダ=%s / assetPaths=%s"
         % (sorted(root_flow_guids), folder_guids, sorted(asset_paths)))
if len(folder_guids) != 1:
    fail("フロー資産フォルダが1件ではありません: %s" % folder_guids)

PKG_FOLDER = folder_guids[0]
flow_dir = os.path.join(flows_dir, PKG_FOLDER)
defpath = os.path.join(flow_dir, "definition.json")
for name in ("definition.json", "apisMap.json", "connectionsMap.json"):
    if not os.path.isfile(os.path.join(flow_dir, name)):
        fail("必須ファイルが無い: Microsoft.Flow/flows/%s/%s" % (PKG_FOLDER, name))

raw = open(defpath, encoding="utf-8").read()
flow = json.loads(raw)
apis_map = json.load(open(os.path.join(flow_dir, "apisMap.json"), encoding="utf-8"))
connections_map = json.load(open(os.path.join(flow_dir, "connectionsMap.json"), encoding="utf-8"))

root_res = root_manifest.get("resources", {})
root_dep = set(root_res.get(PKG_FOLDER, {}).get("dependsOn", []))
for label, m in (("apisMap", apis_map), ("connectionsMap", connections_map)):
    for logical, guid in m.items():
        if guid not in root_res:
            fail("%s の %s -> %s が rootManifest.resources に存在しない" % (label, logical, guid))
        if guid not in root_dep:
            fail("%s の %s -> %s が dependsOn に含まれていない" % (label, logical, guid))
extra_dep = root_dep - set(apis_map.values()) - set(connections_map.values())
if extra_dep:
    fail("dependsOn に apisMap/connectionsMap と対応しないGUIDがある: %s" % sorted(extra_dep))

definition = flow["properties"]["definition"]

# =========================================================================
# 1. アクション走査（runAfter兄弟整合 / 重複名 / ガード文脈の記録）
# =========================================================================
all_action_names = set()
all_action_names_list = []
# name -> {"path":..., "guards":[条件式のJSON文字列...], "action":dict}
action_index = {}


def guard_signature(expr_obj):
    return json.dumps(expr_obj, ensure_ascii=False, sort_keys=True)


def walk(container, path, guards):
    names = set(container.keys())
    for aname, a in container.items():
        all_action_names.add(aname)
        all_action_names_list.append(aname)
        if not isinstance(a, dict):
            fail("%s/%s: アクションが dict ではない" % (path, aname))
            continue
        action_index[aname] = {"path": path, "guards": list(guards), "action": a}
        ra = a.get("runAfter", {})
        if not isinstance(ra, dict):
            fail("%s/%s: runAfter が dict ではない" % (path, aname))
        else:
            for target in ra.keys():
                if target not in names:
                    fail("%s/%s: runAfter -> '%s' が同一コンテナの兄弟に存在しない（兄弟=%s）"
                         % (path, aname, target, sorted(names)))
                for st in ra[target]:
                    if st not in ("Succeeded", "Failed", "Skipped", "TimedOut"):
                        fail("%s/%s: runAfter の状態値が不正: %s" % (path, aname, st))
        t = a.get("type")
        if "actions" in a and isinstance(a["actions"], dict):
            g = guards + ([guard_signature(a["expression"])] if t == "If" else [])
            walk(a["actions"], "%s/%s" % (path, aname), g)
        if t == "If" and isinstance(a.get("else"), dict) and isinstance(a["else"].get("actions"), dict):
            # else 側は条件の否定なので、ガードとしては数えない（安全側）
            walk(a["else"]["actions"], "%s/%s[else]" % (path, aname), guards)


walk(definition["actions"], "root", [])

dups = [n for n, c in Counter(all_action_names_list).items() if c > 1]
if dups:
    fail("アクション名の全体重複（Power Automateは全体一意を要求）: %s" % dups)

# =========================================================================
# 2. 変数（初期化 / 参照 / 自己参照 / 重複初期化 / トップレベル配置）
# =========================================================================
init_vars, init_count = set(), {}
setvar_list, append_arr, append_str, inc_dec, foreach_list = [], [], [], [], []


def audit(container, depth):
    for aname, a in container.items():
        if not isinstance(a, dict):
            continue
        t = a.get("type")
        if t == "InitializeVariable":
            if depth > 0:
                fail("InitializeVariable '%s' が入れ子(depth=%d)にある（トップレベル必須）" % (aname, depth))
            for v in a["inputs"]["variables"]:
                init_vars.add(v["name"])
                init_count[v["name"]] = init_count.get(v["name"], 0) + 1
        elif t == "SetVariable":
            var = a["inputs"]["name"]
            val = json.dumps(a["inputs"].get("value"), ensure_ascii=False)
            setvar_list.append((aname, var, ("variables('%s')" % var) in val))
        elif t == "AppendToArrayVariable":
            append_arr.append((aname, a["inputs"]["name"]))
        elif t == "AppendToStringVariable":
            append_str.append((aname, a["inputs"]["name"]))
        elif t in ("IncrementVariable", "DecrementVariable"):
            inc_dec.append((aname, a["inputs"]["name"]))
        elif t == "Foreach":
            foreach_list.append((aname, a))
        if "actions" in a and isinstance(a["actions"], dict):
            audit(a["actions"], depth + 1)
        if t == "If" and isinstance(a.get("else"), dict):
            audit(a["else"].get("actions", {}), depth + 1)


audit(definition["actions"], 0)

ref_vars = set(re.findall(r"variables\('([^']+)'\)", raw))
written_vars = ({v for _, v, _ in setvar_list} | {v for _, v in append_arr}
                | {v for _, v in append_str} | {v for _, v in inc_dec})

if ref_vars - init_vars:
    fail("未初期化変数の参照: %s" % sorted(ref_vars - init_vars))
if init_vars - ref_vars - written_vars:
    fail("初期化したが読み書きされない変数: %s" % sorted(init_vars - ref_vars - written_vars))

selfrefs = [(n, v) for n, v, s in setvar_list if s]
if selfrefs:
    fail("SetVariable自己参照（保存時 WorkflowRunActionInputsInvalidProperty）: %s" % selfrefs)
dup_inits = {k: c for k, c in init_count.items() if c > 1}
if dup_inits:
    fail("変数の重複初期化: %s" % dup_inits)
for lst, label in ((append_arr, "AppendToArrayVariable"), (append_str, "AppendToStringVariable"),
                   (inc_dec, "Increment/Decrement")):
    for aname, var in lst:
        if var not in init_vars:
            fail("%s '%s' の対象変数 '%s' が未初期化" % (label, aname, var))

# 指示書§28 の必須変数がすべて存在するか
REQUIRED_VARS = [
    "varInputSharePointUrl", "varSiteUrl", "varSiteId", "varSiteTitle", "varListName",
    "varListDescription", "varExistingLists", "varMatchedLists", "varListExists",
    "varCreatedListId", "varCreatedListTitle", "varCreatedListRootFolder", "varCreatedInThisRun",
    "varDeletedFields", "varSkippedFields", "varFieldDeleteErrors",
    "varDefaultViewId", "varDefaultViewTitle", "varFinalViewFields",
    "varStatus", "varResultObject", "varResultJson", "varErrorMessages",
]
missing_req = [v for v in REQUIRED_VARS if v not in init_vars]
if missing_req:
    fail("指示書§28 の必須変数が未定義: %s" % missing_req)

# =========================================================================
# 3. アクション参照 / コネクタ封筒
# =========================================================================
ref_acts = set(re.findall(r"(?:body|outputs)\('([^']+)'\)", raw))
if ref_acts - all_action_names:
    fail("body()/outputs() の参照先アクションが存在しない: %s" % sorted(ref_acts - all_action_names))

conn_actions = {n for n, e in action_index.items() if e["action"].get("type") == "OpenApiConnection"}
ENVELOPE_KEYS = ("body", "statusCode", "headers")
for m in re.finditer(r"outputs\('([^']+)'\)\?\['([^']+)'\]", raw):
    act, field = m.group(1), m.group(2)
    if act in conn_actions and not field.startswith(ENVELOPE_KEYS):
        fail("コネクタ出力の body/ 欠落: outputs('%s')?['%s'] は常にnull（body('%s')?['%s'] が正）"
             % (act, field, act, field))

# =========================================================================
# 4. 接続参照
# =========================================================================
conn_refs = set(flow["properties"].get("connectionReferences", {}).keys())
used_conns = {action_index[n]["action"]["inputs"]["host"].get("connectionName") for n in conn_actions}
if used_conns - conn_refs:
    fail("未定義の接続参照を使用: %s" % sorted(used_conns - conn_refs))
if conn_refs - used_conns:
    fail("未使用の接続参照: %s" % sorted(conn_refs - used_conns))
if conn_refs != set(apis_map.keys()) or conn_refs != set(connections_map.keys()):
    fail("connectionReferences と apisMap/connectionsMap のキー不一致")
if conn_refs != {"shared_sharepointonline"}:
    fail("接続は SharePoint 1本であるべき: %s" % sorted(conn_refs))

# =========================================================================
# 5. 式の検査（'@' 位置 / 関数許可リスト）
# =========================================================================
ALLOWED_FUNCS = {
    "concat", "substring", "replace", "split", "trim", "length", "indexOf", "endsWith",
    "startsWith", "join", "string", "guid", "toLower",
    "first", "last", "take", "union", "createArray", "array", "sort", "reverse", "json",
    "if", "not", "and", "or", "equals", "empty", "contains", "greater", "greaterOrEquals",
    "lessOrEquals", "coalesce",
    "int", "sub", "add",
    "utcNow", "addDays", "formatDateTime", "convertFromUtc",
    "uriComponent", "decodeUriComponent", "uriPath", "decodeBase64",
    "variables", "outputs", "body", "item", "items", "parameters", "triggerBody", "triggerOutputs",
}
# toLower は本リポジトリ初使用。指示書§9.2が明示指定し、公式のWDL関数リファレンスに実在する。


def scan_bad_at(s):
    bad, i, n, in_str = [], 0, len(s), False
    starts_expr = s.startswith("@")
    while i < n:
        c = s[i]
        if in_str:
            if c == "'":
                if i + 1 < n and s[i + 1] == "'":
                    i += 2
                    continue
                in_str = False
        else:
            if c == "'":
                in_str = True
            elif c == "@":
                if not ((i == 0 and starts_expr) or (i + 1 < n and s[i + 1] == "{")):
                    bad.append(i)
        i += 1
    return bad


def strip_literals(s):
    """式から単一引用符の文字列リテラルを取り除く。
    REST の URI 片（'..lists(guid'' や ''AddViewField(..'）を関数名と誤検出しないため。"""
    out, i, n, in_str = [], 0, len(s), False
    while i < n:
        c = s[i]
        if in_str:
            if c == "'":
                if i + 1 < n and s[i + 1] == "'":
                    i += 2
                    continue
                in_str = False
        else:
            if c == "'":
                in_str = True
            else:
                out.append(c)
        i += 1
    return "".join(out)


used_funcs = set()
expr_strings = []


def collect_strings(node, path):
    if isinstance(node, dict):
        for k, v in node.items():
            collect_strings(v, "%s.%s" % (path, k))
    elif isinstance(node, list):
        for idx, v in enumerate(node):
            collect_strings(v, "%s[%d]" % (path, idx))
    elif isinstance(node, str):
        expr_strings.append((path, node))


collect_strings({"triggers": definition["triggers"], "actions": definition["actions"]}, "definition")
for path, s in expr_strings:
    bad = scan_bad_at(s)
    if bad:
        fail("不正な '@' 位置 %s at %s: %r" % (bad, path, s[:120]))
    if s.startswith("@") or "@{" in s:
        for fname in re.findall(r"([A-Za-z_][A-Za-z0-9_]*)\s*\(", strip_literals(s)):
            used_funcs.add(fname)
if used_funcs - ALLOWED_FUNCS:
    fail("許可リスト外の関数を使用（実在確認が取れていない）: %s" % sorted(used_funcs - ALLOWED_FUNCS))

# =========================================================================
# 6. SharePoint REST の形式検査
# =========================================================================
# ボディを持たないPOST（メソッド呼び出し）は例外として許可する
NO_BODY_POST = ("removeAllViewFields()", "deleteObject()")

http_actions = {}
for n in conn_actions:
    a = action_index[n]["action"]
    h = a["inputs"]["host"]
    p = a["inputs"].get("parameters", {})
    http_actions[n] = p
    if h.get("connectionName") != "shared_sharepointonline" or h.get("operationId") != "HttpRequest":
        fail("%s: 想定外のコネクタ/操作 (%s/%s)" % (n, h.get("connectionName"), h.get("operationId")))
    for req in ("dataset", "parameters/method", "parameters/uri"):
        if req not in p:
            fail("%s: 必須パラメータ '%s' が無い" % (n, req))
    if a["inputs"].get("authentication") is None:
        fail("%s: authentication が無い" % n)
    if p.get("dataset") != "@variables('varSiteUrl')":
        fail("%s: dataset が @variables('varSiteUrl') でない（サイトURLの固定は禁止）: %r"
             % (n, p.get("dataset")))
    headers = p.get("parameters/headers")
    if not isinstance(headers, dict):
        fail("%s: parameters/headers がオブジェクトでない" % n)
        headers = {}
    method = p.get("parameters/method")
    uri = str(p.get("parameters/uri", ""))
    body = p.get("parameters/body")
    if method == "GET" and body is not None:
        fail("%s: GET なのに body がある" % n)
    # ボディ不要なPOST: RESTメソッド呼び出し（removeAllViewFields()/deleteObject()）と
    # X-HTTP-Method:DELETE によるリソース削除
    body_optional = (any(k in uri for k in NO_BODY_POST)
                     or headers.get("X-HTTP-Method") == "DELETE")
    if method == "POST" and body is None and not body_optional:
        fail("%s: POST なのに body が無い（メソッド呼び出し・DELETE以外）" % n)
    if headers.get("X-HTTP-Method") in ("MERGE", "DELETE") and headers.get("IF-MATCH") != "*":
        fail("%s: X-HTTP-Method=%s なのに IF-MATCH:* が無い" % (n, headers.get("X-HTTP-Method")))
    if body is not None and "__metadata" in json.dumps(body, ensure_ascii=False):
        warnings.append("%s: body に __metadata 文字列（Compose経由なら想定内）" % n)

# Compose で組み立てる __metadata ボディの Content-Type は verbose であること
for n, p in http_actions.items():
    body = p.get("parameters/body")
    if not isinstance(body, str) or not body.startswith("@string(outputs("):
        continue
    src = re.findall(r"@string\(outputs\('([^']+)'\)\)", body)
    if not src:
        continue
    compose_inputs = action_index.get(src[0], {}).get("action", {}).get("inputs")
    if isinstance(compose_inputs, dict) and "__metadata" in json.dumps(compose_inputs, ensure_ascii=False):
        ct = p.get("parameters/headers", {}).get("Content-Type", "")
        if "verbose" not in ct:
            fail("%s: __metadata を含むボディだが Content-Type が verbose でない: %r" % (n, ct))

# =========================================================================
# 7. 【安全要件】既存リストを壊さないことの機械検査（指示書§36）
# =========================================================================
# --- A. GetByTitle( が定義中に1件も無い（リスト名で対象を特定する経路が存在しない） ---
if "GetByTitle(" in raw:
    fail("安全違反: 定義に GetByTitle( が存在する（対象はリストIDでのみ特定すること）")

# --- B. 書き込み系RESTのURIは必ず varCreatedListId を含む ---
CREATE_LIST_ACTION = "Create_Generic_List"
for n, p in http_actions.items():
    if p.get("parameters/method") != "POST":
        continue
    uri = str(p.get("parameters/uri", ""))
    if n == CREATE_LIST_ACTION:
        if uri != "_api/web/lists":
            fail("%s: 新規作成のURIが '_api/web/lists' でない: %r" % (n, uri))
        continue
    if "variables('varCreatedListId')" not in uri:
        fail("安全違反: 書き込み系 %s のURIに varCreatedListId が含まれない: %r" % (n, uri))
    if "varListName" in uri:
        fail("安全違反: 書き込み系 %s のURIが varListName を参照している" % n)

# --- C. リスト作成が varListExists==false のガード配下にある ---
create_guards = " ".join(action_index.get(CREATE_LIST_ACTION, {}).get("guards", []))
if CREATE_LIST_ACTION not in action_index:
    fail("安全違反: %s が存在しない" % CREATE_LIST_ACTION)
elif "varListExists" not in create_guards or "false" not in create_guards.lower():
    fail("安全違反: %s が varListExists==false のガード配下にない（guards=%s）"
         % (CREATE_LIST_ACTION, create_guards[:200]))

# --- D. 初期化・ロールバックが varCreatedInThisRun==true のガード配下にある ---
MUST_BE_GUARDED = [
    "Verify_Empty_List", "Disable_Attachments", "Deactivate_Title_Required",
    "Get_All_List_Fields", "Delete_Deletable_Field", "Create_SampleRaw_Field",
    "Verify_SampleRaw_Field", "Get_Default_View", "Remove_All_Default_View_Fields",
    "Add_SampleRaw_To_Default_View", "Verify_Default_View_Fields",
    "Rollback_Newly_Created_List",
]
for n in MUST_BE_GUARDED:
    if n not in action_index:
        fail("安全違反: 必須アクション %s が存在しない" % n)
        continue
    g = " ".join(action_index[n]["guards"])
    if "varCreatedInThisRun" not in g:
        fail("安全違反: %s が varCreatedInThisRun ガード配下にない（guards=%s）" % (n, g[:200]))

# ロールバックは varListExists==false も条件に含むこと
rb_guards = " ".join(action_index.get("Rollback_Newly_Created_List", {}).get("guards", []))
if "varListExists" not in rb_guards:
    fail("安全違反: ロールバックのガードに varListExists の判定が無い")
if "varCreatedListId" not in rb_guards:
    fail("安全違反: ロールバックのガードに varCreatedListId の非空判定が無い")

# --- E. 同名リスト確認がリスト作成より runAfter 順で前にある ---
def topo_index(container):
    """トップレベルScopeの実行順（runAfter位相順）を返す"""
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
    return order + [n for n in names if n not in placed]


top_order = topo_index(definition["actions"])
def scope_pos(scope_name):
    return top_order.index(scope_name) if scope_name in top_order else -1


if scope_pos("Scope_Check_Existing_List") < 0 or scope_pos("Scope_Create_List") < 0:
    fail("安全違反: 同名リスト確認スコープまたは作成スコープが存在しない")
elif scope_pos("Scope_Check_Existing_List") >= scope_pos("Scope_Create_List"):
    fail("安全違反: 同名リスト確認がリスト作成より後になっている")

# --- F. 作成失敗後にリストを取得するアクションが無い ---
# Create_Generic_List に対して Failed を含む runAfter を持つアクションが、
# GET でリストを取得するものであってはならない（§10・§31）。
for n, e in action_index.items():
    ra_map = e["action"].get("runAfter", {})
    if CREATE_LIST_ACTION in ra_map and "Failed" in ra_map[CREATE_LIST_ACTION]:
        if e["action"].get("type") == "OpenApiConnection":
            fail("安全違反: 作成失敗経路(%s)でRESTを呼び出している（同名リスト取得の禁止）" % n)

# --- G. 列削除が CanBeDeleted 判定を経由している ---
flt = action_index.get("Filter_Deletable_Fields", {}).get("action")
if not flt or flt.get("type") != "Query":
    fail("安全違反: Filter_Deletable_Fields（Query）が存在しない")
else:
    where = str(flt["inputs"].get("where", ""))
    if "CanBeDeleted" not in where:
        fail("安全違反: 削除対象の絞り込みに CanBeDeleted 判定が無い")
    if "sample_raw" not in where:
        fail("Filter_Deletable_Fields が sample_raw を除外していない")
del_loop = action_index.get("Apply_to_each_DeleteField", {}).get("action")
if not del_loop:
    fail("Apply_to_each_DeleteField が存在しない")
elif del_loop.get("foreach") != "@body('Filter_Deletable_Fields')":
    fail("安全違反: 列削除ループの入力が Filter_Deletable_Fields の出力でない: %r"
         % del_loop.get("foreach"))

# --- H. Foreach の並列オフ ---
for aname, a in foreach_list:
    rep = a.get("runtimeConfiguration", {}).get("concurrency", {}).get("repetitions")
    if rep != 1:
        fail("%s: Apply to each の並列オフ未設定（concurrency.repetitions=%r）" % (aname, rep))

# =========================================================================
# 8. sample_raw の SchemaXml 検査（§18）
# =========================================================================
sr_body = action_index.get("Compose_SampleRaw_Field_Body", {}).get("action", {}).get("inputs")
if not isinstance(sr_body, dict):
    fail("Compose_SampleRaw_Field_Body が存在しない（Composeオブジェクトであること）")
else:
    params = sr_body.get("parameters", {})
    if params.get("__metadata", {}).get("type") != "SP.XmlSchemaFieldCreationInformation":
        fail("sample_raw 作成ボディの __metadata.type が SP.XmlSchemaFieldCreationInformation でない")
    if params.get("Options") != 0:
        fail("sample_raw 作成ボディの Options が 0 でない")
    schema = params.get("SchemaXml", "")
    try:
        el = ET.fromstring(schema)
    except Exception as e:                                     # noqa: BLE001
        el = None
        fail("sample_raw の SchemaXml がXMLとして不正: %s" % e)
    if el is not None:
        if el.tag != "Field":
            fail("sample_raw の SchemaXml ルート要素が Field でない: %s" % el.tag)
        expect = {"Type": "Note", "Name": "sample_raw", "StaticName": "sample_raw",
                  "DisplayName": "sample_raw", "Required": "FALSE", "RichText": "TRUE",
                  "RichTextMode": "FullHtml", "AppendOnly": "FALSE"}
        for k, v in expect.items():
            if el.get(k) != v:
                fail("sample_raw SchemaXml の %s が %r でない: %r" % (k, v, el.get(k)))

# =========================================================================
# 9. トリガー検査（§3）
# =========================================================================
trigs = definition.get("triggers", {})
if list(trigs.keys()) != ["manual"]:
    fail("トリガーが manual 単独でない: %s" % list(trigs.keys()))
else:
    mt = trigs["manual"]
    if mt.get("kind") != "Button" or mt.get("type") != "Request":
        fail("トリガー種別が手動ボタンでない")
    sch = mt.get("inputs", {}).get("schema", {})
    props = sch.get("properties", {})
    req = sch.get("required", [])
    for key, title, required in (("SharePointUrl", "SharePointサイトまたはリスト一覧URL", True),
                                 ("ListName", "作成するリスト名", True),
                                 ("ListDescription", "リストの説明", False)):
        if key not in props:
            fail("トリガー入力 '%s' が無い" % key)
            continue
        if props[key].get("type") != "string":
            fail("%s の型が string でない" % key)
        if props[key].get("title") != title:
            fail("%s の表示名が %r でない: %r" % (key, title, props[key].get("title")))
        if required and key not in req:
            fail("%s が required に入っていない" % key)
        if not required and key in req:
            fail("%s は任意であるべきだが required に入っている" % key)

# =========================================================================
# 10. 実値混入（匿名化）検査
# =========================================================================
body_text = json.dumps({"triggers": definition["triggers"], "actions": definition["actions"]},
                       ensure_ascii=False)
LEAK_PATTERNS = [
    (r"https://[A-Za-z0-9\-]+\.sharepoint\.com", "SharePointサイトURLの実値"),
    (r"\bdigitalgojp\b", "テナント名の実値"),
    (r"\bmetijapan\b", "テナント名の実値"),
    (r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b", "GUID実値"),
    (r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}", "メールアドレス"),
]
for pat, label in LEAK_PATTERNS:
    hits = re.findall(pat, body_text)
    if hits:
        fail("実値混入の疑い（%s）: %s" % (label, sorted(set(hits))[:5]))

# =========================================================================
# 出力
# =========================================================================
opids = sorted(set(re.findall(r'"operationId":\s*"([^"]+)"', raw)))
print("=== CreateInitializedSharePointList 静的検証 ===")
print("package folder GUID :", PKG_FOLDER)
print("flow displayName    :", flow["properties"]["displayName"])
print("operationIds        :", opids)
print("connectionReferences:", sorted(conn_refs))
print("アクション総数      :", len(all_action_names))
print("HTTP要求アクション  :", len(http_actions))
print("初期化変数          :", len(init_vars))
print("SetVariable         :", len(setvar_list), "（うち自己参照", len(selfrefs), "）")
print("AppendToArray       :", len(append_arr))
print("Foreach             :", len(foreach_list))
print("使用関数            :", sorted(used_funcs))
print("トップレベル実行順  :", " -> ".join(n for n in top_order if n.startswith("Scope_")))
print()
print("--- 安全検査サマリ ---")
print("GetByTitle( の出現            :", raw.count("GetByTitle("), "（0であること）")
print("書き込みRESTのID指定          : 新規作成を除き全件 varCreatedListId 使用")
print("初期化ガード配下のアクション  :", len(MUST_BE_GUARDED), "件すべて varCreatedInThisRun 配下")
print("同名確認→作成の順序           : Scope_Check_Existing_List(%d) < Scope_Create_List(%d)"
      % (scope_pos("Scope_Check_Existing_List"), scope_pos("Scope_Create_List")))
# =========================================================================
# 共通リンター（tools/wdl_lint.py。L01〜L13）
#   どのフローにも当てはまる検査は共通ツール側に集約している。
# =========================================================================
for _msg in lint_definition(definition, raw):
    fail("[wdl_lint] " + _msg)

print()
print("=== ERRORS ===")
for e in errors:
    print("  ", e)
print("(%d errors)" % len(errors))
print("=== WARNINGS ===")
for w in warnings:
    print("  ", w)
print("(%d warnings)" % len(warnings))

sys.exit(1 if errors else 0)
