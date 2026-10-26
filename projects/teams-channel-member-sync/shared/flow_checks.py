# -*- coding: utf-8 -*-
"""
Teams チャネルメンバー同期 — 本案件固有の静的検査（両フロー共通）。

案件横断の検査は tools/wdl_lint.py に集約されている。ここに書くのは
「この2フローだけに当てはまる不変条件」で、いずれも
**要件書で禁止されている事故を、定義から機械的に排除できているか**を確かめるもの。

  P01 パッケージ5ファイル構造・GUID3点一致・接続マップの整合
  P02 すべての '@' 式が構文として解釈できる（括弧の数え間違いを機械検出する）
  P03 破壊的 REST が1件も無い（DELETE / deleteObject / recycle / リスト削除）
  P04 SharePoint の書き込みURIは必ずリストIDで対象を指定している
  P05 REST の URI が許可した形だけでできている（想定外のAPIを呼んでいない）
  P06 dataset は必ず変数（サイトURLをフロー定義へ固定していない）
  P07 REST ボディは必ず Compose + string()（文字列連結でJSONを組んでいない）
  P08 Graph の宛先が graph.microsoft.com だけで、チャネルIDは uriComponent 済み
  P09 離脱者の無効化が必ずガード条件の配下にある
  P10 ListMembers のパラメータが揃っている
  P11 Compose_AdminSiteUrl が空（テナント固有値をZIPへ入れていない）
  P12 実値の混入が無い（GUID / *.sharepoint.com / メール / チャネルID）
  P13 変数の初期化漏れ・未使用、outputs()/body() の参照先の実在
  P14 Foreach はすべて並列オフ
  P15 ビュー・列の破壊的変更が無い（既存列の型変更・ビュー再構築をしていない）
  P16 substring が空文字でも成立する形（番兵付き）で書かれている
  P17 設定リストの参照が2フローで一致する（同じ名前・同じサイト変数）
  P18 取得した項目が既定ビューに出る（列追加はする／ビューの作り直しはしない）
"""
import json
import os
import re

# tools/ は呼び出し側（validate_*.py）が sys.path へ入れている
from wdl_lint import walk_actions, collect_strings, BAD_AT_ALLOWED  # noqa: E402
from wdl_eval import Parser, tokenize  # noqa: E402

DS_ALLOWED = ("@variables('varSiteUrl')", "@variables('varConfigSiteUrl')")

# 2フローが同じ設定リストを見ることを機械確認するための literal。
# sync_blocks.CONFIG_LIST_TITLE と一致していなければならない。
CONFIG_LIST_TITLE_LITERAL = "Teamsチャネルメンバー同期設定"

# 破壊的、あるいは本案件で使わないと決めた REST の断片。
# ビューは「列の追加（AddViewField）」だけ許可する。removeAllViewFields（作り直し）は
# 利用者が並べ替えた既存ビューを壊すため、定義に一切含めない。
FORBIDDEN_URI_FRAGMENTS = [
    "deleteObject", "recycle", "/recycle(", "removeAllViewFields",
    "breakroleinheritance", "roleassignments",
]
FORBIDDEN_METHODS = ["DELETE", "PUT"]
# X-HTTP-Method で許可するのは MERGE のみ（DELETE / PUT を紛れ込ませない）
ALLOWED_XHTTP = ("MERGE",)

# REST URI に許される形。これ以外が出てきたら「想定外のAPIを呼んでいる」として落とす。
ALLOWED_URI_EXACT = ["_api/web/lists"]               # リスト作成（POST）
ALLOWED_URI_FRAGMENTS = [
    "_api/web/lists?$select=",                       # リスト一覧（コレクション列挙）
    "_api/web/lists(guid'",                          # リストIDで特定する読み書き
]

GRAPH_PREFIX = "https://graph.microsoft.com/v1.0/"

LEAK_PATTERNS = [
    (r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b",
     "GUID実値"),
    (r"19[:%]3?[Aa]?[0-9a-zA-Z_%\-]+(?:@|%40)thread", "チャネルID実値"),
    (r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}", "メールアドレス"),
    (r"[A-Za-z0-9\-]+\.sharepoint\.com", "SharePointサイトURL"),
]

VAR_FUNCS = ("SetVariable", "AppendToArrayVariable", "AppendToStringVariable",
             "IncrementVariable", "DecrementVariable")


# =========================================================================
# P01 パッケージ構造
# =========================================================================
def check_package(build_dir, expected_conn_keys):
    """展開形パッケージの構造・GUID3点一致・接続マップを検査する"""
    errors = []
    root_manifest_path = os.path.join(build_dir, "manifest.json")
    flows_manifest_path = os.path.join(build_dir, "Microsoft.Flow", "flows", "manifest.json")
    for p in (root_manifest_path, flows_manifest_path):
        if not os.path.isfile(p):
            errors.append("P01 必須ファイルが無い: %s" % p)
    if errors:
        return errors, None, None

    root_manifest = json.load(open(root_manifest_path, encoding="utf-8"))
    flows_manifest = json.load(open(flows_manifest_path, encoding="utf-8"))

    flows_dir = os.path.join(build_dir, "Microsoft.Flow", "flows")
    folder_guids = sorted([d for d in os.listdir(flows_dir)
                           if os.path.isdir(os.path.join(flows_dir, d))])
    asset_paths = sorted(flows_manifest.get("flowAssets", {}).get("assetPaths", []))
    resources = root_manifest.get("resources", {})
    root_flow_guids = sorted([k for k, v in resources.items()
                              if v.get("hierarchy") == "Root"])

    if not (asset_paths == root_flow_guids == folder_guids):
        errors.append("P01 パッケージGUIDの3点不一致: assetPaths=%s / rootResources=%s / folders=%s"
                      % (asset_paths, root_flow_guids, folder_guids))
        return errors, None, None

    pkg = folder_guids[0]
    flow_dir = os.path.join(flows_dir, pkg)
    expected_files = {"definition.json", "apisMap.json", "connectionsMap.json"}
    actual = set(os.listdir(flow_dir))
    if actual != expected_files:
        errors.append("P01 フローフォルダの構成が想定と違う: %s" % sorted(actual))

    all_files = []
    for r, _, fs in os.walk(build_dir):
        for f in fs:
            all_files.append(os.path.relpath(os.path.join(r, f), build_dir).replace(os.sep, "/"))
    if len(all_files) != 5:
        errors.append("P01 レガシーパッケージは5ファイル構成であるべき: %s" % sorted(all_files))

    apis_map = json.load(open(os.path.join(flow_dir, "apisMap.json"), encoding="utf-8"))
    conns_map = json.load(open(os.path.join(flow_dir, "connectionsMap.json"), encoding="utf-8"))
    if sorted(apis_map.keys()) != sorted(expected_conn_keys):
        errors.append("P01 apisMap のキーが想定と違う: %s" % sorted(apis_map.keys()))
    if sorted(conns_map.keys()) != sorted(expected_conn_keys):
        errors.append("P01 connectionsMap のキーが想定と違う: %s" % sorted(conns_map.keys()))

    depends = resources[pkg].get("dependsOn", [])
    for label, m in (("apisMap", apis_map), ("connectionsMap", conns_map)):
        for k, guid in m.items():
            if guid not in resources:
                errors.append("P01 %s の %s=%s が manifest.resources に無い" % (label, k, guid))
            if guid not in depends:
                errors.append("P01 %s の %s=%s が Root の dependsOn に無い" % (label, k, guid))
    extra = [g for g in depends if g not in set(list(apis_map.values()) + list(conns_map.values()))]
    if extra:
        errors.append("P01 Root の dependsOn に余分なGUIDがある: %s" % extra)

    api_guids = {k for k, v in resources.items() if v.get("type") == "Microsoft.PowerApps/apis"}
    for guid, res in resources.items():
        if res.get("type") != "Microsoft.PowerApps/apis/connections":
            continue
        dep = res.get("dependsOn", [])
        if len(dep) != 1 or dep[0] not in api_guids:
            errors.append("P01 接続リソース %s の dependsOn がAPIリソース1件を指していない: %s"
                          % (guid, dep))

    doc = json.load(open(os.path.join(flow_dir, "definition.json"), encoding="utf-8"))
    return errors, doc, pkg


# =========================================================================
# P02 式の構文検査
# =========================================================================
def check_expression_syntax(definition):
    """定義中のすべての '@' 式を実際にパースする。
    括弧の数え間違い・閉じ忘れをレビューではなく機械で捕まえるための検査。
    未実装の関数名はここでは問題にしない（構文だけを見る）。"""
    errors = []
    strings = collect_strings({"triggers": definition.get("triggers", {}),
                               "actions": definition.get("actions", {})}, "definition", [])
    checked = 0
    for path, s in strings:
        if not s.startswith("@") or s in BAD_AT_ALLOWED:
            continue
        try:
            Parser(tokenize(s[1:])).parse()
            checked += 1
        except Exception as e:  # noqa: BLE001  構文エラーはすべて拾う
            errors.append("P02 式を解釈できない at %s: %s / %r" % (path, e, s[:160]))
    return errors, checked


# =========================================================================
# P16 substring は必ず番兵付きで書く
#
# 【実発生 2026-08-04】Power Automate の substring は開始位置が
# **文字列長より小さい**ことを要求する。したがって空文字には substring('', 0, 0) すら
# 適用できず、`Compose_Admin_Cut` が実行時に落ちた。
#   The template language function 'substring' parameter is out of range:
#   'start index' must be non-negative integer and should be less than the length of the string.
# 「空にならないはず」という前提を置かず、`substring(concat(S, '#'), ...)` の形に
# 統一して、定義の形として空文字でも成立させる。
# =========================================================================
def check_substring_safety(definition):
    errors = []
    strings = collect_strings({"triggers": definition.get("triggers", {}),
                               "actions": definition.get("actions", {})}, "definition", [])
    count = 0
    for path, s in strings:
        for m in re.finditer(r"substring\(", s):
            count += 1
            if not s[m.end():].startswith("concat("):
                errors.append(
                    "P16 substring の第1引数に番兵が無い（空文字だと実行時に落ちる）"
                    " at %s: %r" % (path, s[max(0, m.start() - 40):m.end() + 60]))
    return errors, count


# =========================================================================
# P03〜P08, P10, P14, P15 コネクタ呼び出しの検査
# =========================================================================
def check_connector_calls(definition, expect_listmembers):
    errors = []
    info = {"spoActions": 0, "graphActions": 0, "listMembers": 0, "writeActions": 0}
    nodes = walk_actions(definition.get("actions", {}), "root", 0, [])

    for name, a, path, _ in nodes:
        if a.get("type") == "Foreach":
            rep = (a.get("runtimeConfiguration", {}).get("concurrency", {}) or {}).get("repetitions")
            if rep != 1:
                errors.append("P14 %s: Apply to each の並列オフが未設定（repetitions=%r）"
                              % (name, rep))
        if a.get("type") != "OpenApiConnection":
            continue
        inputs = a.get("inputs", {}) or {}
        params = inputs.get("parameters", {}) or {}
        host = inputs.get("host", {}) or {}
        opid = host.get("operationId")
        conn = host.get("connectionName")

        if conn == "shared_sharepointonline":
            info["spoActions"] += 1
            if opid != "HttpRequest":
                errors.append("P05 %s: SharePoint は HttpRequest だけを使う（operationId=%s）"
                              % (name, opid))
                continue
            ds = params.get("dataset")
            if ds not in DS_ALLOWED:
                errors.append("P06 %s: dataset が許可した変数でない: %r" % (name, ds))
            method = str(params.get("parameters/method", "")).upper()
            uri = str(params.get("parameters/uri", ""))
            headers = params.get("parameters/headers", {}) or {}
            body = params.get("parameters/body")

            if method in FORBIDDEN_METHODS:
                errors.append("P03 %s: 破壊的メソッド %s を使っている" % (name, method))
            xhttp = headers.get("X-HTTP-Method")
            if xhttp is not None and xhttp not in ALLOWED_XHTTP:
                errors.append("P03 %s: X-HTTP-Method が %r（許可は %s のみ）"
                              % (name, xhttp, ALLOWED_XHTTP))
            for frag in FORBIDDEN_URI_FRAGMENTS:
                if frag.lower() in uri.lower():
                    errors.append("P03 %s: 使用を禁じた REST 断片 %r を含む" % (name, frag))
            if "getbytitle(" in uri.lower():
                errors.append("P04 %s: GetByTitle( で対象を特定している"
                              "（名前の取り違えで既存リストを壊しうる。リストIDを使う）" % name)

            is_write = method == "POST"
            if is_write:
                info["writeActions"] += 1
                # リスト作成そのもの以外の書き込みは、必ずリストIDで対象を指定する
                if uri not in ALLOWED_URI_EXACT and "lists(guid'" not in uri:
                    errors.append("P04 %s: 書き込みURIがリストIDを含まない: %r" % (name, uri[:120]))
                if body is None:
                    errors.append("P07 %s: POST にボディが無い" % name)
                elif not re.match(r"^@string\(outputs\('Compose_[A-Za-z0-9_]+'\)\)$", str(body)):
                    errors.append("P07 %s: ボディが @string(outputs('Compose_...')) 形式でない: %r"
                                  % (name, str(body)[:120]))
            else:
                if body is not None:
                    errors.append("P07 %s: GET にボディが付いている" % name)

            if uri.startswith("@variables("):
                if uri != "@variables('varExistingNextUri')":
                    errors.append("P05 %s: 変数由来のURIは継続リンクだけを想定している: %r"
                                  % (name, uri))
            elif uri not in ALLOWED_URI_EXACT and not any(f in uri for f in ALLOWED_URI_FRAGMENTS):
                errors.append("P05 %s: 許可していない REST URI: %r" % (name, uri[:140]))

        elif conn == "shared_teams":
            if opid == "HttpRequest":
                info["graphActions"] += 1
                uri = str(params.get("Uri", ""))
                if str(params.get("Method", "GET")).upper() != "GET":
                    errors.append("P08 %s: Graph 呼び出しは GET のみ（Method=%r）"
                                  % (name, params.get("Method")))
                if uri.startswith("@variables("):
                    if uri != "@variables('varMembersNextLink')":
                        errors.append("P08 %s: 変数由来の Graph URI は継続リンクだけを想定: %r"
                                      % (name, uri))
                elif GRAPH_PREFIX not in uri:
                    errors.append("P08 %s: Graph の宛先が %s ではない: %r"
                                  % (name, GRAPH_PREFIX, uri[:140]))
                if "/channels/" in uri and "uriComponent(variables('varChannelId'))" not in uri:
                    errors.append("P08 %s: チャネルIDが uriComponent() で符号化されていない: %r"
                                  % (name, uri[:140]))
            elif opid == "ListMembers":
                info["listMembers"] += 1
                if params.get("threadType") != "channel":
                    errors.append("P10 %s: threadType が 'channel' でない: %r"
                                  % (name, params.get("threadType")))
                for key in ("body/recipient/groupId", "body/recipient/channelId"):
                    if key not in params:
                        errors.append("P10 %s: 必須パラメータ %s が無い" % (name, key))
                if params.get("body/recipient/groupId") != "@variables('varTeamId')":
                    errors.append("P10 %s: groupId が varTeamId でない" % name)
                if params.get("body/recipient/channelId") != "@variables('varChannelId')":
                    errors.append("P10 %s: channelId が varChannelId でない" % name)
            else:
                errors.append("P05 %s: 想定していない Teams operationId: %r" % (name, opid))
        else:
            errors.append("P05 %s: 想定していないコネクタ: %r" % (name, conn))

    if expect_listmembers and info["listMembers"] != 1:
        errors.append("P10 ListMembers アクションが %d 個（1個であるべき）" % info["listMembers"])
    return errors, info


# =========================================================================
# P09 離脱者の無効化はガード配下にあるか
# =========================================================================
def check_config_list_and_view(definition, expect_view=True):
    """P17 設定リストの参照が2フローで一致するか / P18 取得項目が既定ビューに出るか"""
    errors = []
    raw = json.dumps(definition, ensure_ascii=False)
    nodes = walk_actions(definition.get("actions", {}), "root", 0, [])
    names = {n for n, _, _, _ in nodes}

    # --- P17 設定リストは「同じ名前」を「同じサイト変数」で引く ---
    # 手動フローと定期フローが別のリストを見てしまうと、保存した設定が読まれない。
    # リスト名は共有定数（sync_blocks.CONFIG_LIST_TITLE）、サイトは varConfigSiteUrl に固定する。
    if CONFIG_LIST_TITLE_LITERAL not in raw:
        errors.append("P17 設定リスト名の literal '%s' が定義に無い（共有定数から生成していない）"
                      % CONFIG_LIST_TITLE_LITERAL)
    for name, a, _, _ in nodes:
        if a.get("type") != "OpenApiConnection":
            continue
        params = (a.get("inputs", {}) or {}).get("parameters", {}) or {}
        if "Config" not in name:
            continue
        if params.get("dataset") not in (None, "@variables('varConfigSiteUrl')"):
            errors.append("P17 %s: 設定リストの操作なのに dataset が varConfigSiteUrl でない: %r"
                          % (name, params.get("dataset")))
    for needle in ("variables('varConfigListId')", "variables('varConfigSiteUrl')"):
        if needle not in raw:
            errors.append("P17 設定リストの特定に %s を使っていない" % needle)

    # --- P18 取得した項目が既定ビューに出る ---
    if expect_view:
        if "Foreach_View_Field_Member" not in names:
            errors.append("P18 メンバーリストの既定ビューへ列を追加する処理が無い"
                          "（Title だけが表示される状態になる）")
        if "AddViewField" not in raw:
            errors.append("P18 AddViewField が定義に無い")
    if "removeAllViewFields" in raw:
        errors.append("P18 removeAllViewFields が定義にある（既存ビューを作り直してはいけない）")
    return errors


def check_deactivate_guard(definition):
    errors = []
    nodes = walk_actions(definition.get("actions", {}), "root", 0, [])
    found = False
    for name, a, path, _ in nodes:
        if name != "Update_Left_Member_Item":
            continue
        found = True
        if "Condition_Can_Deactivate" not in path:
            errors.append("P09 %s がガード条件 Condition_Can_Deactivate の配下にない: %s"
                          % (name, path))
        if "Foreach_Left_Member" not in path:
            errors.append("P09 %s が Filter_Left_Members の結果ループの中にない: %s" % (name, path))
    if not found:
        errors.append("P09 離脱者の無効化アクション Update_Left_Member_Item が見つからない")

    # ガード式そのものの内容も確認する（条件が緩められていないか）
    raw = json.dumps(definition, ensure_ascii=False)
    for needle in ("equals(variables('varMembersFetchComplete'), true)",
                   "greater(variables('varMemberCount'), 0)",
                   "equals(variables('varExistingFetchComplete'), true)",
                   "empty(variables('varFailedStage'))"):
        if needle not in raw:
            errors.append("P09 離脱ガードの条件が欠けている: %s" % needle)
    return errors


# =========================================================================
# P11 / P12 テナント固有値の混入
# =========================================================================
def check_no_real_values(definition, doc):
    errors = []
    nodes = walk_actions(definition.get("actions", {}), "root", 0, [])
    by_name = {n: a for n, a, _, _ in nodes}

    admin = by_name.get("Compose_AdminSiteUrl")
    if admin is None:
        errors.append("P11 Compose_AdminSiteUrl が無い（インポート後に設定する箇所）")
    elif admin.get("inputs") != "":
        errors.append("P11 Compose_AdminSiteUrl に値が入ったままになっている: %r"
                      % (admin.get("inputs"),))

    raw = json.dumps(definition, ensure_ascii=False)
    for pattern, label in LEAK_PATTERNS:
        hits = re.findall(pattern, raw)
        if hits:
            errors.append("P12 定義に%sが混入している: %s" % (label, sorted(set(hits))[:5]))

    props = doc.get("properties", {})
    for key, ref in (props.get("connectionReferences") or {}).items():
        if ref.get("connectionName", "") == "":
            errors.append("P12 connectionReferences[%s].connectionName が空" % key)
    meta = definition.get("metadata", {})
    if meta.get("creator") != {}:
        errors.append("P12 metadata.creator が匿名化されていない: %r" % (meta.get("creator"),))
    return errors


# =========================================================================
# P13 変数と参照の整合
# =========================================================================
def check_variables_and_references(definition):
    errors = []
    warnings = []
    actions = definition.get("actions", {})
    nodes = walk_actions(actions, "root", 0, [])
    names = {n for n, _, _, _ in nodes}

    initialized = []
    for _, a, _, _ in nodes:
        if a.get("type") == "InitializeVariable":
            for v in (a.get("inputs", {}) or {}).get("variables", []) or []:
                initialized.append(v.get("name"))
    dups = [v for v in set(initialized) if initialized.count(v) > 1]
    if dups:
        errors.append("P13 同じ変数を2回初期化している: %s" % sorted(dups))
    initset = set(initialized)

    raw = json.dumps(definition, ensure_ascii=False)
    referenced = set(re.findall(r"variables\('([^']+)'\)", raw))
    mutated = set()
    for _, a, _, _ in nodes:
        if a.get("type") in VAR_FUNCS:
            mutated.add((a.get("inputs", {}) or {}).get("name"))
    unknown = (referenced | mutated) - initset - {None}
    if unknown:
        errors.append("P13 初期化されていない変数を参照・更新している: %s" % sorted(unknown))
    unused = initset - referenced - mutated
    if unused:
        warnings.append("P13 初期化したが一度も使っていない変数: %s" % sorted(unused))

    for m in re.finditer(r"(?:outputs|body)\('([^']+)'\)", raw):
        target = m.group(1)
        if target not in names and target != "manual":
            errors.append("P13 存在しないアクションを参照している: %s" % target)
    return errors, warnings


# =========================================================================
# 実行本体
# =========================================================================
def run_all(build_dir, expected_conn_keys, expect_listmembers, expected_scopes,
            expect_view=True):
    """(errors, warnings, info) を返す"""
    errors, warnings, info = [], [], {}

    pkg_errors, doc, pkg = check_package(build_dir, expected_conn_keys)
    errors += pkg_errors
    if doc is None:
        return errors, warnings, info

    definition = doc["properties"]["definition"]
    raw = json.dumps(doc, ensure_ascii=False)

    # 案件横断の共通リンター（handbook/checklists/import_save_validation_checklist.md §A）
    from wdl_lint import lint_definition, summarize
    errors += lint_definition(definition, raw)

    syn_errors, checked = check_expression_syntax(definition)
    errors += syn_errors
    info["expressionsChecked"] = checked

    sub_errors, sub_count = check_substring_safety(definition)
    errors += sub_errors
    info["substringCalls"] = sub_count

    conn_errors, conn_info = check_connector_calls(definition, expect_listmembers)
    errors += conn_errors
    info.update(conn_info)

    errors += check_deactivate_guard(definition)
    errors += check_config_list_and_view(definition, expect_view)
    errors += check_no_real_values(definition, doc)

    var_errors, var_warnings = check_variables_and_references(definition)
    errors += var_errors
    warnings += var_warnings

    nodes = walk_actions(definition.get("actions", {}), "root", 0, [])
    names = {n for n, _, _, _ in nodes}
    missing = [s for s in expected_scopes if s not in names]
    if missing:
        errors.append("P15 想定した Scope が定義に無い: %s" % missing)

    info.update(summarize(definition))
    info["packageGuid"] = pkg
    info["displayName"] = doc["properties"]["displayName"]
    info["connectionReferences"] = sorted((doc["properties"].get("connectionReferences") or {}).keys())
    info["authMode"] = ("embedded"
                        if '"@parameters(\'$authentication\')"' in raw or
                           "@parameters('$authentication')" in raw
                        else "invoker")
    return errors, warnings, info


def report(title, errors, warnings, info, extra_lines=()):
    lines = ["=== %s 静的検証 ===" % title]
    for k in ("packageGuid", "displayName", "connectionReferences", "authMode",
              "actions", "maxDepth", "maxExpr", "expressionsChecked", "substringCalls",
              "spoActions", "graphActions", "listMembers", "writeActions"):
        if k in info:
            lines.append("%-22s: %s" % (k, info[k]))
    lines += list(extra_lines)
    lines.append("")
    lines.append("=== ERRORS ===")
    lines += ["  " + e for e in errors] if errors else ["  (0 errors)"]
    lines.append("=== WARNINGS ===")
    if warnings:
        lines += ["  " + w for w in warnings]
    else:
        lines.append("  (0 warnings)")
    return "\n".join(lines)
