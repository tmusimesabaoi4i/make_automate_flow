# -*- coding: utf-8 -*-
"""
Flow2_GetAllTeamsChannelPostRepliesFromUrl の展開形パッケージを静的検証する（検証の正典）。

雛形: projects/migrate-chat-spo/flows/archive-meetings/source/validate_definition.py
SharePoint固有検査（PostItem / GetFileItem / {Link}）を外し、本件向けの検査を追加した。

追加した検査:
  - 不正な '@' 位置（式先頭・@{} 補間・文字列リテラル内 以外の '@'）
  - 関数許可リスト（本リポジトリの実働 definition.json に出現実績のある関数のみ）
  - Teams HttpRequest の必須パラメータ（Uri / Method / connectionName）
  - Apply to each（Foreach）の並列オフ（concurrency.repetitions == 1）
  - トリガー（manual / Button / TeamsPostUrl が required）
  - 実値混入（テナントGUID・チャネルID・メールアドレス・SharePointサイトURL）
  - パッケージGUIDの3点一致 と apisMap / connectionsMap / connectionReferences の突合

終了コード: エラーがあれば 1、無ければ 0。
"""
import json, re, os, sys
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
    print("FATAL: パッケージが見つかりません。先に build_flow2.py を実行してください:", PKG)
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
    fail("パッケージGUIDの3点不一致: rootManifest.resources(Root)=%s / flowsフォルダ=%s / assetPaths=%s"
         % (sorted(root_flow_guids), folder_guids, sorted(asset_paths)))

if len(folder_guids) != 1:
    fail("フロー資産フォルダが1件ではありません: %s" % folder_guids)

PKG_FOLDER = folder_guids[0]
flow_dir = os.path.join(flows_dir, PKG_FOLDER)
defpath = os.path.join(flow_dir, "definition.json")

for name in ("definition.json", "apisMap.json", "connectionsMap.json"):
    p = os.path.join(flow_dir, name)
    if not os.path.isfile(p):
        fail("必須ファイルが無い: Microsoft.Flow/flows/%s/%s" % (PKG_FOLDER, name))

raw = open(defpath, encoding="utf-8").read()
flow = json.loads(raw)
apis_map = json.load(open(os.path.join(flow_dir, "apisMap.json"), encoding="utf-8"))
connections_map = json.load(open(os.path.join(flow_dir, "connectionsMap.json"), encoding="utf-8"))

# apisMap / connectionsMap の値が rootManifest.resources に実在し、dependsOn と一致するか
root_res = root_manifest.get("resources", {})
root_dep = set(root_res.get(PKG_FOLDER, {}).get("dependsOn", []))
for label, m in (("apisMap", apis_map), ("connectionsMap", connections_map)):
    for logical, guid in m.items():
        if guid not in root_res:
            fail("%s の %s -> %s が rootManifest.resources に存在しない" % (label, logical, guid))
        if guid not in root_dep:
            fail("%s の %s -> %s が Root リソースの dependsOn に含まれていない" % (label, logical, guid))
extra_dep = root_dep - set(apis_map.values()) - set(connections_map.values())
if extra_dep:
    fail("dependsOn に apisMap/connectionsMap と対応しないGUIDがある: %s" % sorted(extra_dep))

definition = flow["properties"]["definition"]

# =========================================================================
# 1. アクション走査（runAfter 兄弟整合 / 重複名 / 再帰収集）
# =========================================================================
all_action_names = set()
all_action_names_list = []
containers_seen = []


def walk(container, path):
    names = set(container.keys())
    for aname, a in container.items():
        all_action_names.add(aname)
        all_action_names_list.append(aname)
        if not isinstance(a, dict):
            fail("%s/%s: アクションが dict ではない" % (path, aname))
            continue
        ra = a.get("runAfter", {})
        if not isinstance(ra, dict):
            fail("%s/%s: runAfter が dict ではない" % (path, aname))
        else:
            for target in ra.keys():
                if target not in names:
                    fail("%s/%s: runAfter -> '%s' が同一コンテナの兄弟に存在しない（兄弟=%s）"
                         % (path, aname, target, sorted(names)))
        t = a.get("type")
        if "actions" in a and isinstance(a["actions"], dict):
            containers_seen.append((aname, t))
            walk(a["actions"], "%s/%s" % (path, aname))
        if t == "If" and isinstance(a.get("else"), dict) and isinstance(a["else"].get("actions"), dict):
            walk(a["else"]["actions"], "%s/%s[else]" % (path, aname))


walk(definition["actions"], "root")

dups = [n for n, c in Counter(all_action_names_list).items() if c > 1]
if dups:
    fail("アクション名の全体重複（Power Automateは全体一意を要求）: %s" % dups)

# =========================================================================
# 2. 変数（初期化 / 参照 / 自己参照 / 重複初期化 / トップレベル配置）
# =========================================================================
init_vars = set()
init_count = {}
setvar_list = []
append_arr, append_str, inc_dec, foreach_list, until_list = [], [], [], [], []


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
        elif t == "Until":
            until_list.append((aname, a))
        if "actions" in a and isinstance(a["actions"], dict):
            audit(a["actions"], depth + 1)
        if t == "If" and isinstance(a.get("else"), dict) and isinstance(a["else"].get("actions"), dict):
            audit(a["else"]["actions"], depth + 1)


audit(definition["actions"], 0)

ref_vars = set(re.findall(r"variables\('([^']+)'\)", raw))
# 書き込み対象（SetVariable / Append / Increment の name）も「使用中」とみなす
written_vars = {v for _, v, _ in setvar_list} | {v for _, v in append_arr} \
    | {v for _, v in append_str} | {v for _, v in inc_dec}

missing = ref_vars - init_vars
if missing:
    fail("未初期化変数の参照: %s" % sorted(missing))
unused = init_vars - ref_vars - written_vars
if unused:
    fail("初期化したが読み書きされない変数（変更取りこぼしの疑い）: %s" % sorted(unused))
write_only = init_vars - ref_vars
if write_only:
    warnings.append("書き込みのみで読み出しの無い変数: %s" % sorted(write_only))

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

# =========================================================================
# 3. アクション参照（body() / outputs()）と コネクタ封筒
# =========================================================================
ref_acts = set(re.findall(r"(?:body|outputs)\('([^']+)'\)", raw))
missing_acts = ref_acts - all_action_names
if missing_acts:
    fail("body()/outputs() の参照先アクションが存在しない: %s" % sorted(missing_acts))

conn_actions = set()


def collect_conn(container):
    for aname, a in container.items():
        if isinstance(a, dict):
            if a.get("type") == "OpenApiConnection":
                conn_actions.add(aname)
            if "actions" in a and isinstance(a["actions"], dict):
                collect_conn(a["actions"])
            if a.get("type") == "If" and isinstance(a.get("else"), dict):
                collect_conn(a["else"].get("actions", {}))


collect_conn(definition["actions"])

# コネクタの outputs() は封筒 {statusCode, headers, body}。
# body 以外のフィールド直下参照は常に null（statusCode / headers は封筒の正当キー）
ENVELOPE_KEYS = ("body", "statusCode", "headers")
for m in re.finditer(r"outputs\('([^']+)'\)\?\['([^']+)'\]", raw):
    act, field = m.group(1), m.group(2)
    if act in conn_actions and not field.startswith(ENVELOPE_KEYS):
        fail("コネクタ出力の body/ 欠落: outputs('%s')?['%s'] は常にnull（body('%s')?['%s'] が正）"
             % (act, field, act, field))

# =========================================================================
# 4. 接続参照の突合
# =========================================================================
conn_refs = set(flow["properties"].get("connectionReferences", {}).keys())
used_conns = set()


def collect_used(container):
    for aname, a in container.items():
        if isinstance(a, dict):
            if a.get("type") == "OpenApiConnection":
                used_conns.add(a["inputs"]["host"].get("connectionName"))
            if "actions" in a and isinstance(a["actions"], dict):
                collect_used(a["actions"])
            if a.get("type") == "If" and isinstance(a.get("else"), dict):
                collect_used(a["else"].get("actions", {}))


collect_used(definition["actions"])
if used_conns - conn_refs:
    fail("未定義の接続参照を使用: %s" % sorted(used_conns - conn_refs))
if conn_refs - used_conns:
    fail("未使用の接続参照（削除するか使用する）: %s" % sorted(conn_refs - used_conns))
if conn_refs != set(apis_map.keys()) or conn_refs != set(connections_map.keys()):
    fail("connectionReferences のキーと apisMap/connectionsMap のキーが不一致: refs=%s apis=%s conns=%s"
         % (sorted(conn_refs), sorted(apis_map), sorted(connections_map)))

# =========================================================================
# 5. 式の検査（'@' 位置 / 関数許可リスト）
# =========================================================================
# 本リポジトリの実働 definition.json に出現実績がある関数のみを許可する。
# 実在が不確かな関数を推測で使わないための機械的な歯止め。
ALLOWED_FUNCS = {
    # 文字列
    "concat", "substring", "replace", "split", "trim", "length", "indexOf", "endsWith",
    "startsWith", "join", "string", "guid",
    # 配列・オブジェクト
    "first", "last", "take", "union", "createArray", "array", "sort", "reverse", "json",
    # 論理・比較
    "if", "not", "and", "or", "equals", "empty", "contains", "greater", "greaterOrEquals",
    "less", "lessOrEquals", "coalesce",
    # 数値
    "int", "sub", "add", "mul", "div", "float",
    # 日付
    "utcNow", "addDays", "formatDateTime", "convertFromUtc", "dayOfWeek",
    # URI
    "uriComponent", "decodeUriComponent", "uriPath", "decodeBase64",
    # 参照
    "variables", "outputs", "body", "item", "items", "parameters",
    "triggerBody", "triggerOutputs",
}

BAD_AT_ALLOWED_KEYS = {"@odata.nextLink", "@odata.count", "@odata.context"}


def scan_bad_at(s):
    """式先頭 / @{ 補間 / 文字列リテラル内 以外の '@' の位置を返す"""
    bad, i, n = [], 0, len(s)
    in_str = False
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
                if i == 0 and starts_expr:
                    pass
                elif i + 1 < n and s[i + 1] == "{":
                    pass
                else:
                    bad.append(i)
        i += 1
    return bad


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
    if s in BAD_AT_ALLOWED_KEYS:
        continue
    bad = scan_bad_at(s)
    if bad:
        fail("不正な '@' 位置 %s at %s: %r" % (bad, path, s[:120]))
    if s.startswith("@") or "@{" in s:
        for fname in re.findall(r"([A-Za-z_][A-Za-z0-9_]*)\s*\(", s):
            used_funcs.add(fname)

unknown_funcs = used_funcs - ALLOWED_FUNCS
if unknown_funcs:
    fail("許可リスト外の関数を使用（実在確認が取れていない）: %s" % sorted(unknown_funcs))

# =========================================================================
# 6. コネクタ・ループ・トリガーの検査
# =========================================================================
def check_actions(container, path):
    for aname, a in container.items():
        if not isinstance(a, dict):
            continue
        t = a.get("type")
        if t == "OpenApiConnection":
            h = a["inputs"]["host"]
            p = a["inputs"].get("parameters", {})
            if h.get("connectionName") != "shared_teams":
                fail("%s/%s: 想定外のコネクタ '%s'（本フローは shared_teams のみ）"
                     % (path, aname, h.get("connectionName")))
            if h.get("operationId") != "HttpRequest":
                fail("%s/%s: 想定外の operationId '%s'（本フローは HttpRequest のみ）"
                     % (path, aname, h.get("operationId")))
            for req in ("Uri", "Method"):
                if req not in p:
                    fail("%s/%s: Teams HttpRequest の必須パラメータ '%s' が無い" % (path, aname, req))
            if p.get("Method") != "GET":
                fail("%s/%s: 読み取り専用フローだが Method が '%s'" % (path, aname, p.get("Method")))
            if a["inputs"].get("authentication") is None:
                fail("%s/%s: authentication が無い" % (path, aname))
        if t == "Foreach":
            rep = a.get("runtimeConfiguration", {}).get("concurrency", {}).get("repetitions")
            if rep != 1:
                fail("%s/%s: Apply to each の並列オフ未設定（concurrency.repetitions=%r）"
                     % (path, aname, rep))
        if t == "Until":
            lim = a.get("limit", {})
            if not lim.get("count") or not lim.get("timeout"):
                fail("%s/%s: Do until の limit(count/timeout) が未設定" % (path, aname))
        if "actions" in a and isinstance(a["actions"], dict):
            check_actions(a["actions"], "%s/%s" % (path, aname))
        if t == "If" and isinstance(a.get("else"), dict):
            check_actions(a["else"].get("actions", {}), "%s/%s[else]" % (path, aname))


check_actions(definition["actions"], "root")

trigs = definition.get("triggers", {})
if list(trigs.keys()) != ["manual"]:
    fail("トリガーが manual 単独でない: %s" % list(trigs.keys()))
else:
    mt = trigs["manual"]
    if mt.get("kind") != "Button" or mt.get("type") != "Request":
        fail("トリガー種別が手動ボタンでない: type=%s kind=%s" % (mt.get("type"), mt.get("kind")))
    sch = mt.get("inputs", {}).get("schema", {})
    props = sch.get("properties", {})
    if "TeamsPostUrl" not in props:
        fail("トリガー入力 'TeamsPostUrl' が無い")
    else:
        if props["TeamsPostUrl"].get("type") != "string":
            fail("TeamsPostUrl の型が string でない")
        if props["TeamsPostUrl"].get("title") != "Teams投稿URL":
            fail("TeamsPostUrl の表示名が 'Teams投稿URL' でない")
    if "TeamsPostUrl" not in sch.get("required", []):
        fail("TeamsPostUrl が required に入っていない（必須:はい）")

# =========================================================================
# 7. 実値混入（匿名化）検査 — definition の triggers/actions のみを対象にする
#    （name/id のパッケージGUIDは匿名の採番値なので対象外）
# =========================================================================
body_text = json.dumps({"triggers": definition["triggers"], "actions": definition["actions"]},
                       ensure_ascii=False)
LEAK_PATTERNS = [
    (r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b", "GUID実値"),
    (r"19[:%]3?[Aa]?[0-9a-zA-Z_%\-]+(?:@|%40)thread", "チャネルID実値"),
    (r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}", "メールアドレス"),
    (r"[A-Za-z0-9\-]+\.sharepoint\.com", "SharePointサイトURL"),
]
for pat, label in LEAK_PATTERNS:
    hits = re.findall(pat, body_text)
    if hits:
        fail("実値混入の疑い（%s）: %s" % (label, sorted(set(hits))[:5]))

# =========================================================================
# 出力
# =========================================================================
opids = sorted(set(re.findall(r'"operationId":\s*"([^"]+)"', raw)))
print("=== Flow2_GetAllTeamsChannelPostRepliesFromUrl 静的検証 ===")
print("package folder GUID :", PKG_FOLDER)
print("flow displayName    :", flow["properties"]["displayName"])
print("operationIds        :", opids)
print("connectionReferences:", sorted(conn_refs))
print("アクション総数      :", len(all_action_names))
print("初期化変数          :", len(init_vars), sorted(init_vars))
print("SetVariable         :", len(setvar_list), "（うち自己参照", len(selfrefs), "）")
print("AppendToArray       :", len(append_arr))
print("Foreach / Until     :", len(foreach_list), "/", len(until_list))
print("使用関数            :", sorted(used_funcs))
print("トリガー入力        :", list(trigs.get("manual", {}).get("inputs", {})
                                     .get("schema", {}).get("properties", {}).keys()))
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
