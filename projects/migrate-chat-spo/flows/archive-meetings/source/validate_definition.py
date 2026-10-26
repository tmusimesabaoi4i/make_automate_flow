# -*- coding: utf-8 -*-
import json, re, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))

# 案件横断の共通リンター。どのフローにも当てはまる検査はここに集約してある
# （案件ごとに手書きすると同じ穴が再発するため）。
# handbook/checklists/import_save_validation_checklist.md §A
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..", "..", "..", "..", "..", "tools")))
from wdl_lint import lint_definition   # noqa: E402
defpath = os.path.join(HERE, "package", "Microsoft.Flow", "flows", "fcca0e31-6d8b-40a8-8d63-2441c979a2c7", "definition.json")
raw = open(defpath, encoding="utf-8").read()
flow = json.loads(raw)
definition = flow["properties"]["definition"]

errors = []
warnings = []
all_action_names = set()
all_action_names_list = []

CONTAINER_TYPES = {"Scope", "Foreach", "Until", "If"}

def walk(container, path):
    """container: dict of actionName->action. Check runAfter siblings; recurse."""
    names = set(container.keys())
    for aname, a in container.items():
        all_action_names.add(aname)
        all_action_names_list.append(aname)
        if not isinstance(a, dict):
            errors.append(f"{path}/{aname}: not a dict")
            continue
        ra = a.get("runAfter", {})
        if not isinstance(ra, dict):
            errors.append(f"{path}/{aname}: runAfter not dict")
        else:
            for target in ra.keys():
                if target not in names:
                    errors.append(f"{path}/{aname}: runAfter -> '{target}' NOT a sibling (siblings={sorted(names)})")
        # recurse
        t = a.get("type")
        if "actions" in a and isinstance(a["actions"], dict):
            walk(a["actions"], f"{path}/{aname}")
        if t == "If" and "else" in a and isinstance(a["else"], dict) and "actions" in a["else"]:
            walk(a["else"]["actions"], f"{path}/{aname}[else]")

walk(definition["actions"], "root")

# 重複アクション名（Power Automateは全体で一意を要求）
from collections import Counter
dups = [n for n, c in Counter(all_action_names_list).items() if c > 1]
if dups:
    errors.append(f"重複アクション名（全体一意違反）: {dups}")

# 変数初期化 vs 参照
init_vars = set()
def collect_init(container):
    for aname, a in container.items():
        if isinstance(a, dict):
            if a.get("type") == "InitializeVariable":
                for v in a["inputs"]["variables"]:
                    init_vars.add(v["name"])
            if "actions" in a and isinstance(a["actions"], dict):
                collect_init(a["actions"])
            if a.get("type") == "If" and "else" in a and "actions" in a.get("else", {}):
                collect_init(a["else"]["actions"])
collect_init(definition["actions"])

ref_vars = set(re.findall(r"variables\('([^']+)'\)", raw))
missing = ref_vars - init_vars
if missing:
    errors.append(f"未初期化変数の参照: {sorted(missing)}")
# 初期化したのにどこからも参照されない変数（変更の取りこぼし検知）
unreferenced = init_vars - ref_vars
if unreferenced:
    errors.append(f"未参照の初期化変数（変更取りこぼしの疑い）: {sorted(unreferenced)}")

# InitializeVariable がトップレベルにあるか（Scope等の中にあると不正）
def check_init_toplevel(container, depth):
    for aname, a in container.items():
        if isinstance(a, dict):
            if a.get("type") == "InitializeVariable" and depth > 0:
                errors.append(f"InitializeVariable '{aname}' が入れ子(depth={depth})に存在（トップレベル必須）")
            if "actions" in a and isinstance(a["actions"], dict):
                check_init_toplevel(a["actions"], depth+1)
            if a.get("type") == "If" and "else" in a and "actions" in a.get("else", {}):
                check_init_toplevel(a["else"]["actions"], depth+1)
check_init_toplevel(definition["actions"], 0)

# body()/outputs() 参照先の存在
ref_acts = set(re.findall(r"(?:body|outputs)\('([^']+)'\)", raw))
missing_acts = ref_acts - all_action_names
if missing_acts:
    warnings.append(f"body/outputs参照先が未定義の可能性: {sorted(missing_acts)}")

# 重複アクション名（同一コンテナ内はdictキーで自動的に一意。全体重複は許容だが要注意）
# ユーザー固有情報の混入
for bad in ["iihoshi", "@jpo.go.jp", "641b02f0", "c101e3dbe885", "054920e5a92b", "X-MS-APIM-Tokens"]:
    if bad in raw and bad != "X-MS-APIM-Tokens":
        errors.append(f"ユーザー固有情報の混入: '{bad}'")
# X-MS-APIM-Tokens は authentication の標準参照なのでOK（情報埋め込みではない）

# トリガーが1つか / 手動か
trigs = definition.get("triggers", {})
if list(trigs.keys()) != ["manual"] or trigs.get("manual", {}).get("kind") != "Button":
    warnings.append(f"トリガー確認: {list(trigs.keys())}")

# =========================================================================
# 保存可能性監査（§9/§10）: SetVariable自己参照・重複初期化・種別集計・接続参照
# =========================================================================
setvar_list = []       # (name, var, selfref)
append_arr, append_str, inc_dec, foreach_list = [], [], [], []
init_count = {}        # var -> count

def audit(container):
    for aname, a in container.items():
        if not isinstance(a, dict):
            continue
        t = a.get("type")
        if t == "SetVariable":
            var = a["inputs"]["name"]
            val = json.dumps(a["inputs"].get("value"), ensure_ascii=False)
            setvar_list.append((aname, var, f"variables('{var}')" in val))
        elif t == "AppendToArrayVariable":
            append_arr.append((aname, a["inputs"]["name"]))
        elif t == "AppendToStringVariable":
            append_str.append((aname, a["inputs"]["name"]))
        elif t in ("IncrementVariable", "DecrementVariable"):
            inc_dec.append((aname, a["inputs"]["name"]))
        elif t == "InitializeVariable":
            for v in a["inputs"]["variables"]:
                init_count[v["name"]] = init_count.get(v["name"], 0) + 1
        elif t == "Foreach":
            foreach_list.append((aname, a.get("foreach", "")))
        if "actions" in a and isinstance(a["actions"], dict):
            audit(a["actions"])
        if t == "If" and "else" in a and "actions" in a.get("else", {}):
            audit(a["else"]["actions"])

audit(definition["actions"])

selfrefs = [(n, v) for n, v, s in setvar_list if s]
if selfrefs:
    errors.append(f"SetVariable自己参照（保存不可）: {selfrefs}")
dup_inits = {k: c for k, c in init_count.items() if c > 1}
if dup_inits:
    errors.append(f"変数の重複初期化: {dup_inits}")

# Append/Increment 対象変数が初期化済みか
for lst, label in ((append_arr, "AppendToArrayVariable"), (append_str, "AppendToStringVariable"), (inc_dec, "Increment/Decrement")):
    for aname, var in lst:
        if var not in init_vars:
            errors.append(f"{label} '{aname}' の対象変数 '{var}' が未初期化")

# 接続参照の整合（アクションの host.connectionName vs connectionReferences定義）
conn_refs = set(flow.get("properties", {}).get("connectionReferences", {}).keys())
used_conns = set(re.findall(r'"connectionName":\s*"([^"]+)"', raw)) - {v.get("connectionName") for v in flow.get("properties", {}).get("connectionReferences", {}).values() if isinstance(v, dict)}
# レガシー形式: アクションは host.connectionName に "shared_teams" 等の論理名を持つ
used_conns = {c for c in used_conns if c.startswith("shared_")}
unused = conn_refs - used_conns
undefined = used_conns - conn_refs
if undefined:
    errors.append(f"未定義の接続参照を使用: {sorted(undefined)}")
if unused:
    warnings.append(f"未使用の接続参照（削除推奨）: {sorted(unused)}")

# PostItem 禁止検査（v7）:
# PostItem は必須の動的ボディ item を持ち、dataset/table が式だと保存時検証
# （OpenApiOperationParameterValidationFailed: missing required property 'item'）で失敗する。
# 本フローでは REST（SharePoint HttpRequest）に統一したため、PostItem の存在自体をエラーとする。
def check_no_postitem(container, path):
    for aname, a in container.items():
        if isinstance(a, dict):
            if a.get("type") == "OpenApiConnection":
                opid = a["inputs"]["host"].get("operationId")
                if opid == "PostItem":
                    errors.append(f"{path}/{aname}: PostItem は保存時検証で失敗する（REST HttpRequest へ置換すること）")
                # v10: GetFileItem は table のライブラリ名前解決（表示名/GUID要求）で
                # 実行時に失敗する（"Shared Documents" はURLセグメントであり表示名でない）。
                # 保存後URLは既知の値から決定的に構築する方針のため、存在自体をエラーとする。
                if opid == "GetFileItem":
                    errors.append(f"{path}/{aname}: GetFileItem は廃止（URLは既知の値から決定的に構築する）")
                if opid == "HttpRequest" and a["inputs"]["host"].get("connectionName") == "shared_sharepointonline":
                    p = a["inputs"]["parameters"]
                    for req in ("dataset", "parameters/method", "parameters/uri"):
                        if req not in p:
                            errors.append(f"{path}/{aname}: SharePoint HttpRequest の必須キー '{req}' が無い")
                    if p.get("parameters/method") in ("POST", "PATCH") and "parameters/body" not in p:
                        errors.append(f"{path}/{aname}: POST/PATCH なのに parameters/body が無い")
            if "actions" in a and isinstance(a["actions"], dict):
                check_no_postitem(a["actions"], f"{path}/{aname}")
            if a.get("type") == "If" and "else" in a and "actions" in a.get("else", {}):
                check_no_postitem(a["else"]["actions"], f"{path}/{aname}[else]")
check_no_postitem(definition["actions"], "root")

# コネクタ(OpenApiConnection)出力の body/ 欠落検査:
# outputs('X')?['field'] は X がコネクタの場合、封筒{statusCode,headers,body}のため
# field が 'body' 系でない限り常に null。body('X')?['field'] か outputs('X')?['body/field'] が正。
conn_actions = set()
def collect_conn(container):
    for aname, a in container.items():
        if isinstance(a, dict):
            if a.get("type") == "OpenApiConnection":
                conn_actions.add(aname)
            if "actions" in a and isinstance(a["actions"], dict):
                collect_conn(a["actions"])
            if a.get("type") == "If" and "else" in a and "actions" in a.get("else", {}):
                collect_conn(a["else"]["actions"])
collect_conn(definition["actions"])
for m in re.finditer(r"outputs\('([^']+)'\)\?\['([^']+)'\]", raw):
    act, field = m.group(1), m.group(2)
    if act in conn_actions and not field.startswith("body"):
        errors.append(f"コネクタ出力の body/ 欠落: outputs('{act}')?['{field}'] は常にnull（body('{act}')?['{field}'] が正）")

# v10: {Link} 参照の残存検査（GetFileItem廃止に伴い {Link} は定義から消えているはず）
if "{Link}" in raw:
    errors.append("{Link} 参照が残存（GetFileItem廃止後は決定的URL構築に統一すること）")

# operationId 一覧
opids = sorted(set(re.findall(r'"operationId":\s*"([^"]+)"', raw)))
print("operationIds used:", opids)
print("init vars:", len(init_vars), "referenced vars:", len(ref_vars))
print("total action names:", len(all_action_names))
print("triggers:", list(trigs.keys()), "input props:", list(trigs.get("manual", {}).get("inputs", {}).get("schema", {}).get("properties", {}).keys()))
print()
print("=== 保存可能性監査（§10集計） ===")
print(f"SetVariableアクション数: {len(setvar_list)}")
print(f"自己参照SetVariable件数: {len(selfrefs)}")
print(f"AppendToArrayVariableアクション数: {len(append_arr)}")
print(f"AppendToStringVariableアクション数: {len(append_str)}")
print(f"Increment/Decrementアクション数: {len(inc_dec)}")
print(f"Apply to each(Foreach)数: {len(foreach_list)}")
print(f"変数重複初期化件数: {len(dup_inits)}")
print(f"接続参照: 定義={sorted(conn_refs)} 使用={sorted(used_conns)}")
# ---- 共通リンター（tools/wdl_lint.py。L01〜L13） ----
for _msg in lint_definition(definition, raw):
    errors.append("[wdl_lint] " + _msg)

print()
print("=== ERRORS ===")
for e in errors: print("  ", e)
print(f"({len(errors)} errors)")
print("=== WARNINGS ===")
for w in warnings: print("  ", w)
print(f"({len(warnings)} warnings)")
