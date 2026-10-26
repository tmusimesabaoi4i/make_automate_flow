# -*- coding: utf-8 -*-
"""
SyncSharedMailboxToSharePointList の展開形パッケージを静的検証する（検証の正典）。

雛形:
  projects/create_initialized_sharepoint_list/flows/create-initialized-list/source/validate_list_flow.py
  projects/teams_post_url_flows/flows/flow1-get-channel-post/source/validate_flow1.py

本フロー固有の主眼は「既存リストと既存メールを絶対に壊さないこと」の機械化（指示§25）。
次の各項目は設計レビューではなく**走査で0件／全件を保証**する。

  A. 定義中に GetByTitle( が1件も無い（リスト名で対象を特定する経路が存在しない）
  B. 書き込み系RESTのURIは必ず variables('varListId') を含む（新規作成POSTのみ例外）
  C. 破壊的REST（deleteObject / recycle / X-HTTP-Method:DELETE）が1件も無い
  D. 列作成・表示名変更・Title変更・ビュー操作は varCreatedInThisRun ガード配下にある
  E. removeAllViewFields() が varCreatedInThisRun ガード配下にのみ存在する
  F. Outlook 側の operationId は GetEmailsV3 のみ（既読化・移動・削除・送信が無い）
  G. Outlook アクションが共有メールボックスを式で指定し、メールを変更しない設定になっている
  H. 全 SharePoint アクションの dataset が @variables('varSiteUrl')（サイトURLの固定禁止）
  I. $filter を組み立てるURI式が '' 2重化と uriComponent() の両方を経由している
  J. 同名リスト判定が equals（完全一致）で、contains（部分一致）を使っていない
  K. 既定ビューの ViewQuery が ReceivedDateTime の降順を含む
  L. 5列の SchemaXml が妥当（MessageId=一意/索引、BodyPlainText=RichText FALSE）
  M. スコープの実行順が 検証→存在確認→作成→スキーマ確認→取得→同期 になっている
  N. メール取得と同期が varIsValid / varSchemaOk のガード配下にある

終了コード: エラーがあれば 1、無ければ 0。
"""
import json, re, os, sys
import xml.etree.ElementTree as ET
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
PKG = os.path.join(HERE, "package")

# 案件横断の共通リンター。どのフローにも当てはまる検査はここに集約してある
# （案件ごとに手書きすると同じ穴が再発するため）。新しい案件の validate_*.py も必ず import する。
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..", "..", "..", "..", "..", "tools")))
from wdl_lint import lint_definition, lint_markdown   # noqa: E402

MAX_MAIL_COUNT = 100
FIELD_TYPES = {"MessageId": "Text", "ReceivedDateTime": "DateTime", "SenderAddress": "Text",
               "Subject": "Text", "BodyPlainText": "Note"}
FIELD_ORDER = ["MessageId", "ReceivedDateTime", "SenderAddress", "Subject", "BodyPlainText"]

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
    print("FATAL: パッケージが見つかりません。先に build_sync_flow.py を実行してください:", PKG)
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
action_index = {}   # name -> {"path":..., "guards":[条件式JSON...], "action":dict, "depth":int}


def guard_signature(expr_obj):
    return json.dumps(expr_obj, ensure_ascii=False, sort_keys=True)


def walk(container, path, guards, depth):
    names = set(container.keys())
    for aname, a in container.items():
        all_action_names.add(aname)
        all_action_names_list.append(aname)
        if not isinstance(a, dict):
            fail("%s/%s: アクションが dict ではない" % (path, aname))
            continue
        action_index[aname] = {"path": path, "guards": list(guards), "action": a, "depth": depth}
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
            walk(a["actions"], "%s/%s" % (path, aname), g, depth + 1)
        if t == "If" and isinstance(a.get("else"), dict) and isinstance(a["else"].get("actions"), dict):
            # else 側は条件の否定なので、ガードとしては数えない（安全側）
            walk(a["else"]["actions"], "%s/%s[else]" % (path, aname), guards, depth + 1)


walk(definition["actions"], "root", [], 0)

dups = [n for n, c in Counter(all_action_names_list).items() if c > 1]
if dups:
    fail("アクション名の全体重複（Power Automateは全体一意を要求）: %s" % dups)

max_depth = max(e["depth"] for e in action_index.values()) + 1
if max_depth > 8:
    fail("ネスト深さが上限8を超えている: %d" % max_depth)

# =========================================================================
# 2. 変数（初期化 / 参照 / 自己参照 / 重複初期化 / トップレベル配置）
# =========================================================================
init_vars, init_count = set(), {}
setvar_list, append_arr, append_str, inc_dec, foreach_list, until_list = [], [], [], [], [], []


def audit(container, depth):
    for aname, a in container.items():
        if not isinstance(a, dict):
            continue
        t = a.get("type")
        if t == "InitializeVariable":
            if depth > 0:
                fail("InitializeVariable '%s' が入れ子(depth=%d)にある（トップレベル必須）"
                     % (aname, depth))
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
for v in sorted(init_vars - ref_vars):
    warnings.append("書き込みのみで参照されない変数: %s" % v)

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

REQUIRED_VARS = [
    "varInputSharePointUrl", "varListName", "varMailbox", "varRawCount", "varRequestedCount",
    "varIsValid", "varStage", "varErrorCode", "varErrorMessage", "varErrorMessages",
    "varLastStatusCode", "varSiteUrl", "varSiteOrigin", "varSiteId", "varListExists",
    "varListId", "varListEntityType", "varListServerRelativeUrl", "varListUrl",
    "varCreatedInThisRun", "varDefaultViewId", "varSchemaOk", "varMissingFields",
    "varIncompatibleFields", "varSchemaWarnings", "varFetchedCount", "varCreatedCount",
    "varUpdatedCount", "varDuplicateCount", "varFailedCount", "varTruncatedCount",
    "varDuplicates", "varItemErrors", "varTruncatedItems",
    "varStatus", "varResultObject", "varResultJson",
]
missing_req = [v for v in REQUIRED_VARS if v not in init_vars]
if missing_req:
    fail("必須変数が未定義: %s" % missing_req)

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
EXPECTED_CONNS = {"shared_sharepointonline", "shared_office365", "shared_conversionservice"}
if conn_refs != EXPECTED_CONNS:
    fail("接続は SharePoint / Office 365 Outlook / Content Conversion の3本であるべき: %s"
         % sorted(conn_refs))
for k, v in flow["properties"].get("connectionReferences", {}).items():
    if v.get("source") != "Invoker":
        fail("接続参照 %s が Invoker 形式でない: %s" % (k, v.get("source")))

# =========================================================================
# 5. 式の検査（'@' 位置 / 関数許可リスト）
# =========================================================================
# 本リポジトリの実働 definition.json に出現実績がある関数のみを許可する。
# sort / reverse は handbook/rules/02 の実績集合に記載があり、
# handbook/knowledge/expression_examples.md §14 に「sortは昇順のみ・降順はreverse併用」の規約がある。
ALLOWED_FUNCS = {
    "concat", "substring", "replace", "split", "trim", "length", "indexOf", "endsWith",
    "startsWith", "join", "string", "guid", "toLower",
    "first", "last", "take", "union", "createArray", "array", "sort", "reverse", "json",
    "if", "not", "and", "or", "equals", "empty", "contains", "greater", "greaterOrEquals",
    "less", "lessOrEquals", "coalesce",
    "int", "sub", "add",
    "utcNow", "addDays", "formatDateTime", "convertFromUtc",
    "uriComponent", "decodeUriComponent", "uriPath", "decodeBase64",
    "variables", "outputs", "body", "item", "items", "parameters", "triggerBody", "triggerOutputs",
}


def scan_bad_at(s):
    """式先頭 / @{ 補間 / 文字列リテラル内 以外の '@' の位置を返す"""
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

# '@{...}' は式の補間として評価される。中身が関数呼び出しでないと、インポート時に
#   Unable to parse template language expression 'xxx':
#   expected token 'LeftParenthesis' and actual 'EndOfData'.
# で失敗する。表示テキスト中の 'name@{placeholder}.example.com' のような記述が典型例。
INTERP_RE = re.compile(r"@\{([^}]*)\}")

for path, s in expr_strings:
    bad = scan_bad_at(s)
    if bad:
        fail("不正な '@' 位置 %s at %s: %r" % (bad, path, s[:120]))
    for m in INTERP_RE.finditer(s):
        inner = m.group(1).strip()
        if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*\s*\(", inner):
            fail("'@{...}' の中身が式（関数呼び出し）でない。インポート時に "
                 "Unable to parse template language expression になる: at %s: %r"
                 % (path, s[:120]))
    if s.startswith("@") or "@{" in s:
        for fname in re.findall(r"([A-Za-z_][A-Za-z0-9_]*)\s*\(", strip_literals(s)):
            used_funcs.add(fname)
if used_funcs - ALLOWED_FUNCS:
    fail("許可リスト外の関数を使用（実在確認が取れていない）: %s" % sorted(used_funcs - ALLOWED_FUNCS))

# =========================================================================
# 6. コネクタ形式の検査
# =========================================================================
NO_BODY_POST = ("removeAllViewFields()",)

spo_actions, outlook_actions, conv_actions = {}, {}, {}
for n in sorted(conn_actions):
    a = action_index[n]["action"]
    h = a["inputs"]["host"]
    p = a["inputs"].get("parameters", {})
    cn, opid = h.get("connectionName"), h.get("operationId")
    if a["inputs"].get("authentication") is None:
        fail("%s: authentication が無い" % n)
    if cn == "shared_sharepointonline":
        spo_actions[n] = p
        if opid != "HttpRequest":
            fail("%s: SharePoint 側の operationId は HttpRequest のみ許可: %s" % (n, opid))
        for req in ("dataset", "parameters/method", "parameters/uri"):
            if req not in p:
                fail("%s: SharePoint HttpRequest の必須パラメータ '%s' が無い" % (n, req))
        # H. サイトURLをフローへ固定しない
        if p.get("dataset") != "@variables('varSiteUrl')":
            fail("安全違反: %s の dataset が @variables('varSiteUrl') でない: %r" % (n, p.get("dataset")))
        if not isinstance(p.get("parameters/headers"), dict):
            fail("%s: parameters/headers がオブジェクトでない" % n)
        method = p.get("parameters/method")
        uri = str(p.get("parameters/uri", ""))
        has_body = "parameters/body" in p
        if method == "GET" and has_body:
            fail("%s: GET にボディが付いている" % n)
        if method == "POST" and not has_body and not any(k in uri for k in NO_BODY_POST):
            fail("%s: POST にボディが無い（メソッド呼び出し以外）" % n)
        if method not in ("GET", "POST"):
            fail("%s: 想定外のHTTPメソッド: %r" % (n, method))
        hdr = p.get("parameters/headers", {})
        xm = hdr.get("X-HTTP-Method")
        if xm and xm not in ("MERGE",):
            fail("安全違反: %s の X-HTTP-Method が MERGE 以外: %r" % (n, xm))
        if xm == "MERGE" and hdr.get("IF-MATCH") != "*":
            fail("%s: MERGE なのに IF-MATCH:* が無い" % n)
        body = str(p.get("parameters/body", ""))
        if body and not re.match(r"^@string\(outputs\('[^']+'\)\)$", body):
            fail("%s: ボディが @string(outputs('Compose_X')) 形式でない: %r" % (n, body[:80]))
    elif cn == "shared_office365":
        outlook_actions[n] = (opid, p)
    elif cn == "shared_conversionservice":
        conv_actions[n] = (opid, p)
    else:
        fail("%s: 想定外のコネクタ: %s" % (n, cn))

# --- F/G. Outlook はメールを読むだけ ---
FORBIDDEN_OL_OPS = ("MarkAsRead", "Move", "Delete", "Flag", "SendEmail", "ReplyTo", "Forward",
                    "ExportEmail", "UpdateMyContact")
for n, (opid, p) in outlook_actions.items():
    if opid != "GetEmailsV3":
        fail("安全違反: Outlook の operationId は GetEmailsV3 のみ許可: %s -> %s" % (n, opid))
    if not str(p.get("mailboxAddress", "")).startswith("@variables("):
        fail("%s: mailboxAddress が変数式でない（共有メールボックスを固定してはいけない）: %r"
             % (n, p.get("mailboxAddress")))
    if p.get("includeAttachments") is not False:
        fail("%s: includeAttachments が false でない（添付の内容は取得しない）" % n)
    if p.get("fetchOnlyUnread") is not False:
        fail("%s: fetchOnlyUnread が false でない（既読・未読の両方が対象）" % n)
    if not str(p.get("top", "")).startswith("@variables("):
        fail("%s: top が変数式でない（取得件数はトリガー入力から取る）" % n)
for op in FORBIDDEN_OL_OPS:
    if ('"operationId": "%s' % op) in raw:
        fail("安全違反: メールを変更する操作が定義に含まれている: %s" % op)
if not outlook_actions:
    fail("Outlook のメール取得アクションが存在しない")

for n, (opid, p) in conv_actions.items():
    if opid != "HtmlToText":
        fail("Content Conversion の operationId は HtmlToText のみ許可: %s -> %s" % (n, opid))
    if "Content" not in p:
        fail("%s: HtmlToText の必須パラメータ 'Content' が無い" % n)

# --- Foreach の並列オフ / Until の上限 ---
for aname, a in foreach_list:
    rep = a.get("runtimeConfiguration", {}).get("concurrency", {}).get("repetitions")
    if rep != 1:
        fail("%s: Apply to each の並列オフ未設定（concurrency.repetitions=%r）" % (aname, rep))
for aname, a in until_list:
    lim = a.get("limit", {})
    if not lim.get("count") or not lim.get("timeout"):
        fail("%s: Do until の limit(count/timeout) が未設定" % aname)

# =========================================================================
# 7. 安全要件（本フローの主眼）
# =========================================================================
# --- A. GetByTitle( を使わない ---
if raw.count("GetByTitle(") != 0:
    fail("安全違反: GetByTitle( が %d 件ある（対象はリストIDで特定すること）" % raw.count("GetByTitle("))

# --- C. 破壊的RESTが無い ---
for token, label in (("deleteObject(", "列/オブジェクトの削除"),
                     ("/recycle(", "ごみ箱への移動"),
                     ("recycleItem(", "アイテムのごみ箱移動"),
                     ('"X-HTTP-Method": "DELETE"', "DELETEメソッド")):
    if token in raw:
        fail("安全違反: 破壊的REST（%s）が定義に含まれている: %s" % (label, token))

# --- B. 書き込み系RESTのURIは varListId を含む（新規作成POSTのみ例外） ---
CREATE_LIST_ACTION = "Create_List"
for n, p in spo_actions.items():
    if p.get("parameters/method") != "POST":
        continue
    uri = str(p.get("parameters/uri", ""))
    if n == CREATE_LIST_ACTION:
        if uri != "_api/web/lists":
            fail("安全違反: %s のURIが '_api/web/lists' でない: %r" % (n, uri))
        continue
    if "variables('varListId')" not in uri:
        fail("安全違反: 書き込み系REST %s のURIに varListId が無い: %r" % (n, uri[:100]))
    if "variables('varListName')" in uri:
        fail("安全違反: 書き込み系REST %s のURIがリスト名を含む: %r" % (n, uri[:100]))

# --- D/E. 初期化系は varCreatedInThisRun ガード配下 ---
MUST_BE_GUARDED = (["Create_Field_" + f for f in FIELD_ORDER]
                   + ["Rename_Field_" + f for f in FIELD_ORDER]
                   + ["Add_View_Field_" + f for f in FIELD_ORDER]
                   + ["Deactivate_Title_Required", "Remove_All_Default_View_Fields",
                      "Set_Default_View_Sort"])
for n in MUST_BE_GUARDED:
    e = action_index.get(n)
    if not e:
        fail("安全違反: 必須アクション %s が存在しない" % n)
        continue
    if not any("varCreatedInThisRun" in g for g in e["guards"]):
        fail("安全違反: %s が varCreatedInThisRun ガード配下にない（既存リストを変更しうる）" % n)

# removeAllViewFields は1件だけ、かつガード配下
rm = [n for n, p in spo_actions.items() if "removeAllViewFields()" in str(p.get("parameters/uri", ""))]
if len(rm) != 1:
    fail("安全違反: removeAllViewFields() のアクションが1件でない: %s" % rm)

# --- O. $expand したナビゲーションプロパティは $select にも投影を書く ---
# 投影を省くと SharePoint はナビゲーション先の全プロパティを実体化しようとし、
# アクセス権の無いリスト（カタログ等のシステムリスト）を含む列挙で 403 になる。
# 実環境で成功実績のある形式は $select に `RootFolder/ServerRelativeUrl` を含む。
for n, p in spo_actions.items():
    uri = str(p.get("parameters/uri", ""))
    if "$expand=" not in uri or "$select=" not in uri:
        continue
    for m in re.finditer(r"\$expand=([A-Za-z0-9_,/]+)", uri):
        for exp in m.group(1).split(","):
            exp = exp.strip()
            if exp and (exp + "/") not in uri:
                fail("安全違反: %s は $expand=%s しているのに $select に '%s/<プロパティ>' の"
                     "投影が無い（アクセス不能なリストで 403 になりうる）: %r"
                     % (n, exp, exp, uri[:120]))

# --- I. $filter のエスケープ ---
filter_uris = [(n, str(p.get("parameters/uri", ""))) for n, p in spo_actions.items()
               if "$filter=" in str(p.get("parameters/uri", ""))]
if not filter_uris:
    fail("メッセージIDによる重複判定の $filter が存在しない")
for n, uri in filter_uris:
    if "uriComponent(" not in uri:
        fail("安全違反: %s の $filter が uriComponent() を経由していない" % n)
    if "replace(" not in uri or "''''" not in uri:
        fail("安全違反: %s の $filter がシングルクォートの2重化を行っていない" % n)

# --- J. 同名リスト判定は完全一致 ---
for qn in ("Filter_Matching_Lists", "Filter_Recheck_Lists", "Filter_Retry_Lists"):
    e = action_index.get(qn)
    if not e or e["action"].get("type") != "Query":
        fail("安全違反: %s（Query）が存在しない" % qn)
        continue
    where = str(e["action"]["inputs"].get("where", ""))
    if not where.startswith("@equals("):
        fail("安全違反: %s の判定が equals（完全一致）でない: %r" % (qn, where[:80]))
    if "contains(" in where:
        fail("安全違反: %s が contains（部分一致）を使っている" % qn)
    if "toLower(" not in where or "trim(" not in where:
        fail("%s が大文字小文字/前後空白の正規化を行っていない" % qn)

# --- K. 既定ビューの並び順 ---
vq = action_index.get("Compose_View_Query_Body")
if not vq:
    fail("Compose_View_Query_Body が存在しない")
else:
    q = str(vq["action"]["inputs"].get("ViewQuery", ""))
    if "ReceivedDateTime" not in q or "Ascending='FALSE'" not in q:
        fail("既定ビューの並び順が ReceivedDateTime の降順になっていない: %r" % q)
    if "Name='ID'" not in q:
        warnings.append("既定ビューの第2ソートキー（ID）が設定されていない")

# --- L. 列の SchemaXml ---
for f in FIELD_ORDER:
    c = action_index.get("Compose_Field_Body_" + f)
    if not c:
        fail("Compose_Field_Body_%s が存在しない" % f)
        continue
    params = c["action"]["inputs"].get("parameters", {})
    if params.get("__metadata", {}).get("type") != "SP.XmlSchemaFieldCreationInformation":
        fail("%s: __metadata.type が SP.XmlSchemaFieldCreationInformation でない" % f)
    if params.get("Options") != 0:
        fail("%s: Options が 0 でない（内部名が表示名から自動生成されなくなる）" % f)
    xml = params.get("SchemaXml", "")
    try:
        el = ET.fromstring(xml)
    except Exception as ex:
        fail("%s: SchemaXml がXMLとしてパースできない: %s" % (f, ex))
        continue
    if el.tag != "Field":
        fail("%s: SchemaXml のルート要素が Field でない" % f)
    for attr in ("Name", "StaticName", "DisplayName"):
        if el.get(attr) != f:
            fail("%s: SchemaXml の %s が内部名と一致しない: %r" % (f, attr, el.get(attr)))
    if el.get("Type") != FIELD_TYPES[f]:
        fail("%s: SchemaXml の Type が %s でない: %r" % (f, FIELD_TYPES[f], el.get("Type")))
    if f == "MessageId":
        if el.get("Required") != "TRUE":
            fail("MessageId: Required が TRUE でない")
        if el.get("Indexed") != "TRUE" or el.get("EnforceUniqueValues") != "TRUE":
            fail("MessageId: Indexed / EnforceUniqueValues が TRUE でない（重複防止に必要）")
    if f == "BodyPlainText":
        if el.get("RichText") != "FALSE":
            fail("BodyPlainText: RichText が FALSE でない（HTMLをそのまま保存してはいけない）")
        if el.get("AppendOnly") != "FALSE":
            fail("BodyPlainText: AppendOnly が FALSE でない（追記型の変更履歴を有効化しない）")
    if f == "ReceivedDateTime" and el.get("Indexed") != "TRUE":
        warnings.append("ReceivedDateTime にインデックスが設定されていない")

# --- M. スコープの実行順 ---
def topo_index(container):
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
EXPECTED_SCOPE_ORDER = ["Scope_Validate_Input", "Scope_Check_List", "Scope_Create_List",
                        "Scope_Init_List_Schema", "Scope_Configure_View", "Scope_Verify_Schema",
                        "Scope_Get_Emails", "Scope_Sync_Items", "Scope_Create_Result",
                        "Scope_Handle_Error", "Scope_Finalize"]
positions = []
for s in EXPECTED_SCOPE_ORDER:
    if s not in top_order:
        fail("必須スコープが存在しない: %s" % s)
    else:
        positions.append((s, top_order.index(s)))
if len(positions) == len(EXPECTED_SCOPE_ORDER):
    if [p for _, p in positions] != sorted(p for _, p in positions):
        fail("安全違反: スコープの実行順が想定と異なる: %s" % positions)

# --- N. メール取得・同期はガード配下 ---
for n in ("Get_Emails", "Foreach_Email"):
    e = action_index.get(n)
    if not e:
        fail("必須アクションが存在しない: %s" % n)
        continue
    g = " ".join(e["guards"])
    if "varIsValid" not in g or "varSchemaOk" not in g:
        fail("安全違反: %s が varIsValid / varSchemaOk のガード配下にない（検証前に実行されうる）" % n)

# --- 破壊的処理の順序: 存在確認 → 作成 ---
if ("Recheck_Lists_Before_Create" not in action_index
        or "Filter_Recheck_Lists" not in action_index):
    fail("安全違反: リスト作成直前の再確認が存在しない（同時実行による二重作成の防止）")

# --- Catch Scope の runAfter は1本だけ ---
he = action_index.get("Scope_Handle_Error")
if he:
    ra_map = he["action"].get("runAfter", {})
    if list(ra_map.keys()) != ["Scope_Create_Result"]:
        fail("Catch Scope の runAfter は Scope_Create_Result 1本だけにする（AND判定で不発になる）: %s"
             % sorted(ra_map.keys()))
    if set(ra_map.get("Scope_Create_Result", [])) != {"Failed", "Skipped", "TimedOut"}:
        fail("Catch Scope の runAfter 状態が [Failed, Skipped, TimedOut] でない")

# =========================================================================
# 8. トリガー
# =========================================================================
trigs = definition.get("triggers", {})
if list(trigs.keys()) != ["manual"]:
    fail("トリガーは manual 1件であるべき: %s" % list(trigs.keys()))
else:
    tr = trigs["manual"]
    if tr.get("kind") != "Button" or tr.get("type") != "Request":
        fail("トリガーが手動（Request/Button）でない: %s/%s" % (tr.get("type"), tr.get("kind")))
    sch = tr["inputs"]["schema"]
    props = sch.get("properties", {})
    EXPECTED_INPUTS = {
        "SharePointUrl": ("string", "SharePointサイトまたはリスト一覧URL"),
        "ListName": ("string", "作成するリスト名"),
        "SharedMailboxAddress": ("string", "共有メールボックスのアドレス"),
        "MailCount": ("integer", "取得件数"),
    }
    for k, (typ, title) in EXPECTED_INPUTS.items():
        if k not in props:
            fail("トリガー入力 %s が無い" % k)
            continue
        if props[k].get("type") != typ:
            fail("トリガー入力 %s の型が %s でない: %s" % (k, typ, props[k].get("type")))
        if props[k].get("title") != title:
            fail("トリガー入力 %s の表示名が想定と異なる: %r" % (k, props[k].get("title")))
        if k not in sch.get("required", []):
            fail("トリガー入力 %s が required に無い" % k)
    if set(props.keys()) != set(EXPECTED_INPUTS.keys()):
        fail("トリガー入力が4項目でない: %s" % sorted(props.keys()))
    # 表示テキストに '@' を書かない。'@{' が式補間として解釈されインポートが失敗する。
    # メールアドレスの例は docs/ に置き、スキーマの説明文には書かない。
    for k, v in props.items():
        for fld in ("title", "description"):
            if "@" in str(v.get(fld, "")):
                fail("トリガー入力 %s の %s に '@' が含まれる"
                     "（'@{' が式補間として解釈されインポートに失敗する）: %r"
                     % (k, fld, v.get(fld)))
    if str(MAX_MAIL_COUNT) not in json.dumps(props.get("MailCount", {}), ensure_ascii=False):
        warnings.append("MailCount の説明に上限（%d）が書かれていない" % MAX_MAIL_COUNT)

# 上限チェックが定義に実在するか（黙って切り捨てないこと）
if "ERR_COUNT_TOO_LARGE" not in raw:
    fail("取得件数の上限超過を弾く経路（ERR_COUNT_TOO_LARGE）が定義に無い")
if ("greater(outputs('Compose_Count_Numeric'), %d)" % MAX_MAIL_COUNT) not in raw:
    fail("取得件数の上限が %d で検査されていない" % MAX_MAIL_COUNT)

# =========================================================================
# 8.5 共通リンター（tools/wdl_lint.py）
#     どのフローにも当てはまる検査は共通ツール側に集約している。
#     本案件のドキュメントに載せた REST 断片も同じ規則で検査する
#     （文書に 403 になる形が残っていると、次の実装がそれをコピーするため）。
# =========================================================================
for msg in lint_definition(definition, raw):
    fail("[wdl_lint] " + msg)

DOC_DIRS = [os.path.join(HERE, "..", "spec"),
            os.path.abspath(os.path.join(HERE, "..", "..", "..", "docs")),
            os.path.abspath(os.path.join(HERE, "..", "..", "..", "tests"))]
doc_files = []
for d in DOC_DIRS:
    if os.path.isdir(d):
        for f in sorted(os.listdir(d)):
            if f.lower().endswith(".md"):
                doc_files.append(os.path.join(d, f))
readme = os.path.abspath(os.path.join(HERE, "..", "..", "..", "README.md"))
if os.path.isfile(readme):
    doc_files.append(readme)
for f in doc_files:
    rel = os.path.relpath(f, os.path.join(HERE, "..", "..", "..")).replace(os.sep, "/")
    for msg in lint_markdown(open(f, encoding="utf-8").read(), rel):
        fail("[wdl_lint/md] " + msg)

# =========================================================================
# 9. 実値混入（匿名化リーク）
# =========================================================================
LEAK_PATTERNS = [
    (r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b", "GUID実値"),
    (r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}", "メールアドレス"),
    (r"[A-Za-z0-9\-]+\.sharepoint\.com", "SharePointサイトURL"),
]
scan_target = json.dumps({"triggers": definition["triggers"], "actions": definition["actions"]},
                         ensure_ascii=False)
for pat, label in LEAK_PATTERNS:
    hits = set(re.findall(pat, scan_target))
    hits = {h for h in hits if "{tenant}" not in h and "{siteName}" not in h}
    if hits:
        fail("実値の混入（%s）: %s" % (label, sorted(hits)))

# =========================================================================
# 出力
# =========================================================================
opids = sorted({action_index[n]["action"]["inputs"]["host"].get("operationId")
                for n in conn_actions})
print("=== SyncSharedMailboxToSharePointList 静的検証 ===")
print("package folder GUID :", PKG_FOLDER)
print("flow displayName    :", flow["properties"]["displayName"])
print("operationIds        :", opids)
print("connectionReferences:", sorted(conn_refs))
print("アクション総数      :", len(all_action_names))
print("最大ネスト深さ      :", max_depth, "（上限8）")
print("SharePoint REST     :", len(spo_actions), "（GET %d / POST %d）"
      % (sum(1 for p in spo_actions.values() if p.get("parameters/method") == "GET"),
         sum(1 for p in spo_actions.values() if p.get("parameters/method") == "POST")))
print("Outlook             :", len(outlook_actions))
print("Content Conversion  :", len(conv_actions))
print("初期化変数          :", len(init_vars))
print("SetVariable         :", len(setvar_list), "（うち自己参照", len(selfrefs), "）")
print("AppendToArray       :", len(append_arr))
print("Increment           :", len(inc_dec))
print("Foreach             :", len(foreach_list))
print("使用関数            :", sorted(used_funcs))
print("トップレベル実行順  :", " -> ".join(n for n in top_order if n.startswith("Scope_")))
print()
print("--- 安全検査サマリ ---")
print("GetByTitle( の出現            :", raw.count("GetByTitle("), "（0であること）")
print("破壊的REST（delete/recycle）  :", sum(raw.count(t) for t in
      ("deleteObject(", "/recycle(", "recycleItem(", '"X-HTTP-Method": "DELETE"')), "（0であること）")
print("メール変更操作の出現          :", sum(1 for op in FORBIDDEN_OL_OPS
      if ('"operationId": "%s' % op) in raw), "（0であること）")
print("ガード必須アクション          :", len(MUST_BE_GUARDED),
      "件すべて varCreatedInThisRun 配下")
print("$filter のエスケープ          :", len(filter_uris), "件すべて '' 2重化＋uriComponent()")
print("dataset の式指定              :", len(spo_actions), "件すべて @variables('varSiteUrl')")
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
