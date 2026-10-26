# -*- coding: utf-8 -*-
"""
CreateInitializedSharePointList のレガシーパッケージ（展開形）を生成する。

実行時に指定されたSharePointサイトURLとリスト名を受け取り、
**同名リストが存在しない場合に限って** 新しい汎用リストを作成し、
利用者から見える列を sample_raw（拡張リッチテキスト）だけに初期化する。

安全設計の柱（既存リストを絶対に壊さないための構造）:
  1. 同名リスト確認（非表示リスト含む・大文字小文字/前後空白を無視）を作成より前に必ず通す
  2. 作成に失敗したら AlreadyExistsOrConflict で終了し、**同名リストを取得しに行かない**
  3. 初期化系のRESTは URI に必ず varCreatedListId を使い、リスト名で対象を特定しない
  4. 初期化は varCreatedInThisRun == true のガード配下でのみ実行する
  5. ロールバックは「今回の作成応答から得たリストID」でのみ DELETE する

REST形式は実働リファレンス CreateKnowledgeList（実環境動作実績あり。
references/extracted/reference_original/）から流用している。
生成スクリプトの骨格は provision-archive-lists/source/build_list_package.py に倣う。

【不変則】definition.json は生成物。修正は必ず本スクリプトを編集して再生成する。
"""
import json, os

HERE = os.path.dirname(os.path.abspath(__file__))
BUILD = os.path.join(HERE, "package")

FLOW_LOGICAL_NAME = "CreateInitializedSharePointList"
FLOW_DISPLAY_NAME = "SharePointリスト新規作成＋初期化（既存リスト保護）"

# ---- 固定GUID（本フロー用に新規採番・匿名） ----
FLOW_ID    = "6b41d9c2-8e07-4a35-9f16-2c58e0b7d34a"
PKG_FOLDER = "d07c8e5a-3f92-4b61-a8d4-15e69c2f0b73"
API_SPO    = "4a82f61d-9c37-40e5-b273-8f0d61a95c48"
CONN_SPO   = "e93b7d04-6a51-4c82-9e37-b0f5142d68ac"
CN_SPO     = "b5e0a94c7d3142f8ae61c05d972b3f4e"   # connectionReferences.connectionName（匿名）
PKG_TELE   = "12f6c4b8-70d3-49ea-8b52-c9107e6a3f5d"

# 接続参照は Invoker 形式（2026-07-24 に実環境インポート・実行成功を確認した形）。
# 参照フローの Embedded 形式も正当だが、実接続名の実値を流用しないため Invoker を採用する。
AUTH = {"value": "@json(decodeBase64(triggerOutputs().headers['X-MS-APIM-Tokens']))['$ConnectionKey']",
        "type": "Raw"}
HOST = {"apiId": "/providers/Microsoft.PowerApps/apis/shared_sharepointonline",
        "connectionName": "shared_sharepointonline", "operationId": "HttpRequest"}

# ---- ヘッダー（実働リファレンスで実証済みの組み合わせ） ----
H_VERBOSE = {"Accept": "application/json;odata=verbose",
             "Content-Type": "application/json;odata=verbose"}
H_NOMETA = {"Accept": "application/json;odata=nometadata"}
H_MERGE_V = {"Accept": "application/json;odata=verbose",
             "Content-Type": "application/json;odata=verbose",
             "IF-MATCH": "*", "X-HTTP-Method": "MERGE"}
# Title の Required 解除はリファレンス deactivateSPOTitle が nometadata で成功している
H_MERGE_N = {"Accept": "application/json;odata=nometadata",
             "Content-Type": "application/json;odata=nometadata",
             "IF-MATCH": "*", "X-HTTP-Method": "MERGE"}
H_DELETE = {"Accept": "application/json;odata=nometadata",
            "IF-MATCH": "*", "X-HTTP-Method": "DELETE"}

# サイトアドレスは常に実行時に解析した値を使う（サイトURLをフローへ固定しない）
DATASET = "@variables('varSiteUrl')"

# sample_raw の Field XML（指示書§18.2 のとおり）
SAMPLE_RAW_SCHEMA_XML = (
    '<Field Type="Note" Name="sample_raw" StaticName="sample_raw" DisplayName="sample_raw"'
    ' Required="FALSE" NumLines="12" RichText="TRUE" RichTextMode="FullHtml"'
    ' IsolateStyles="TRUE" RestrictedMode="FALSE" AppendOnly="FALSE" />')

DEFAULT_DESCRIPTION = "Power Automateにより作成された初期化済みリスト"


# =========================================================================
# アクション生成ヘルパー
# =========================================================================
def http(method, uri, headers, body=None, runafter=None):
    """SharePoint「HTTP要求を送信します」アクション"""
    params = {"dataset": DATASET, "parameters/method": method, "parameters/uri": uri,
              "parameters/headers": dict(headers)}
    if body is not None:
        params["parameters/body"] = body
    return {"type": "OpenApiConnection",
            "inputs": {"parameters": params, "host": dict(HOST), "authentication": AUTH},
            "runAfter": runafter or {}}


def ra(prev, states=("Succeeded",)):
    return {} if prev is None else {prev: list(states)}


def initvar(name, vtype, value):
    return {"type": "InitializeVariable",
            "inputs": {"variables": [{"name": name, "type": vtype, "value": value}]}}


def compose(expr, runafter=None):
    return {"type": "Compose", "inputs": expr, "runAfter": runafter or {}}


def setvar(name, value, runafter=None):
    return {"type": "SetVariable", "inputs": {"name": name, "value": value},
            "runAfter": runafter or {}}


def append(name, value, runafter=None):
    return {"type": "AppendToArrayVariable", "inputs": {"name": name, "value": value},
            "runAfter": runafter or {}}


def query(from_expr, where_expr, runafter=None):
    return {"type": "Query", "inputs": {"from": from_expr, "where": where_expr},
            "runAfter": runafter or {}}


def foreach(items_expr, actions, runafter=None):
    """Apply to each（配列変数を更新するため並列は必ずオフ）"""
    return {"type": "Foreach", "foreach": items_expr, "actions": actions,
            "runtimeConfiguration": {"concurrency": {"repetitions": 1}},
            "runAfter": runafter or {}}


def chain(seq, first_runafter=None):
    """(name, action) の順序リストを runAfter で直列連結する"""
    out, prev = {}, None
    for name, act in seq:
        act = dict(act)
        act["runAfter"] = ra(prev) if prev is not None else (first_runafter or {})
        out[name] = act
        prev = name
    return out, prev


def cond(expr_obj, true_actions, else_actions=None, runafter=None):
    a = {"type": "If", "expression": expr_obj, "actions": true_actions, "runAfter": runafter or {}}
    if else_actions:
        a["else"] = {"actions": else_actions}
    return a


def eq(left, right):
    return {"equals": [left, right]}


# --- URI ビルダー: 対象は常に「今回作成したリストID」。リスト名では特定しない ---
def list_uri(suffix=""):
    return ("@concat('_api/web/lists(guid''', variables('varCreatedListId'), ''')"
            + suffix + "')")


def view_uri(suffix=""):
    return ("@concat('_api/web/lists(guid''', variables('varCreatedListId'),"
            " ''')/views(guid''', variables('varDefaultViewId'), ''')" + suffix + "')")


# =========================================================================
# トップレベル変数初期化
# InitializeVariable は Scope 内に置けない（handbook/rules/01）。
# 指示書§26 の Scope_Initialize はこのトップレベル連鎖で代替する。
# =========================================================================
DESC_EXPR = ("@if(empty(trim(coalesce(triggerBody()?['ListDescription'], ''))),"
             " '" + DEFAULT_DESCRIPTION + "',"
             " trim(coalesce(triggerBody()?['ListDescription'], '')))")

INIT_SEQ = [
    # --- 指示書§28 の必須変数 ---
    ("Initialize_Input_SharePointUrl", "varInputSharePointUrl", "string",
     "@trim(coalesce(triggerBody()?['SharePointUrl'], ''))"),
    ("Initialize_SiteUrl",             "varSiteUrl",            "string",  ""),
    ("Initialize_SiteId",              "varSiteId",             "string",  ""),
    ("Initialize_SiteTitle",           "varSiteTitle",          "string",  ""),
    ("Initialize_VerifiedUrl",         "varVerifiedUrl",        "string",  ""),
    ("Initialize_ListName",            "varListName",           "string",
     "@trim(coalesce(triggerBody()?['ListName'], ''))"),
    ("Initialize_ListDescription",     "varListDescription",    "string",  DESC_EXPR),
    ("Initialize_ExistingLists",       "varExistingLists",      "array",   "@json('[]')"),
    ("Initialize_MatchedLists",        "varMatchedLists",       "array",   "@json('[]')"),
    ("Initialize_ListExists",          "varListExists",         "boolean", False),
    ("Initialize_CreatedListId",       "varCreatedListId",      "string",  ""),
    ("Initialize_CreatedListTitle",    "varCreatedListTitle",   "string",  ""),
    ("Initialize_CreatedListRootFolder", "varCreatedListRootFolder", "string", ""),
    ("Initialize_CreatedInThisRun",    "varCreatedInThisRun",   "boolean", False),
    ("Initialize_DeletedFields",       "varDeletedFields",      "array",   "@json('[]')"),
    ("Initialize_SkippedFields",       "varSkippedFields",      "array",   "@json('[]')"),
    ("Initialize_FieldDeleteErrors",   "varFieldDeleteErrors",  "array",   "@json('[]')"),
    ("Initialize_DefaultViewId",       "varDefaultViewId",      "string",  ""),
    ("Initialize_DefaultViewTitle",    "varDefaultViewTitle",   "string",  ""),
    ("Initialize_FinalViewFields",     "varFinalViewFields",    "array",   "@json('[]')"),
    ("Initialize_Status",              "varStatus",             "string",  "NotStarted"),
    ("Initialize_ResultObject",        "varResultObject",       "object",  "@json('{}')"),
    ("Initialize_ResultJson",          "varResultJson",         "string",  ""),
    ("Initialize_ErrorMessages",       "varErrorMessages",      "array",   "@json('[]')"),
    # --- 制御・診断用（Try/Catch と結果組み立てのために追加） ---
    ("Initialize_IsValid",             "varIsValid",            "boolean", True),
    ("Initialize_Stage",               "varStage",              "string",  "Initialize"),
    ("Initialize_ErrorCode",           "varErrorCode",          "string",  ""),
    ("Initialize_ErrorMessage",        "varErrorMessage",       "string",  ""),
    ("Initialize_LastStatusCode",      "varLastStatusCode",     "string",  "0"),
    ("Initialize_RollbackPerformed",   "varRollbackPerformed",  "boolean", False),
    ("Initialize_ItemCount",           "varItemCount",          "integer", 0),
    ("Initialize_SampleRawCreated",    "varSampleRawCreated",   "boolean", False),
    ("Initialize_ExistingListInfo",    "varExistingListInfo",   "object",  "@json('{}')"),
]

actions = {}
prev = None
for aname, vname, vtype, value in INIT_SEQ:
    act = initvar(vname, vtype, value)
    act["runAfter"] = ra(prev)
    actions[aname] = act
    prev = aname
LAST_INIT = prev

# =========================================================================
# Scope_Parse_And_Validate_Input : URL解析とリスト名検証（§5・§6）
# =========================================================================
U_FRAG = "outputs('Compose_Url_Without_Fragment')"
U_NORM = "outputs('Compose_Url_Normalized_Layouts')"
P_SITE = "outputs('Parse_SiteUrl')"

# SharePointのリスト名で使用できない文字（順に replace で除去して長さ比較する）。
# 制御文字はタブ・CR・LF のみ検出できる（他の制御文字は式で検出できない＝docs に明記）。
FORBIDDEN_CHARS = ['"', "#", "%", "*", ":", "<", ">", "?", "/", "\\", "|", "{", "}", "~"]
CONTROL_SEQS = ["%09", "%0D", "%0A"]


def _sanitize_expr():
    """禁止文字・制御文字を除去した文字列を作る式（長さ比較で混入を検出する）"""
    expr = "variables('varListName')"
    for ch in FORBIDDEN_CHARS:
        lit = "''''" if ch == "'" else "'" + ch + "'"
        if ch == "\\":
            lit = "'\\'"
        expr = "replace(" + expr + ", " + lit + ", '')"
    for seq in CONTROL_SEQS:
        expr = "replace(" + expr + ", decodeUriComponent('" + seq + "'), '')"
    return "@" + expr


RESERVED_NAMES = ["con", "prn", "aux", "nul", "forms", "_catalogs", "_private",
                  "_vti_bin", "_vti_pvt", "_vti_cnf", "app packages", "appdata"]
RESERVED_ARRAY = "createArray(" + ", ".join("'" + n + "'" for n in RESERVED_NAMES) + ")"

VALIDATE_SITE_URL = (
    "@if(empty(variables('varInputSharePointUrl')), 'ERR_URL_EMPTY',"
    " if(not(startsWith(" + P_SITE + ", 'https://')), 'ERR_NOT_HTTPS',"
    " if(not(endsWith(outputs('Compose_Site_Host'), '.sharepoint.com')), 'ERR_NOT_SHAREPOINT_HOST',"
    " if(empty(" + P_SITE + "), 'ERR_SITE_URL_NOT_EXTRACTED',"
    " ''))))")

VALIDATE_LIST_NAME = (
    "@if(empty(variables('varListName')), 'ERR_LIST_NAME_EMPTY',"
    " if(greater(length(variables('varListName')), 255), 'ERR_LIST_NAME_TOO_LONG',"
    " if(not(equals(length(variables('varListName')),"
    " length(outputs('Compose_ListName_Sanitized')))), 'ERR_LIST_NAME_INVALID_CHARS',"
    " if(startsWith(variables('varListName'), '.'), 'ERR_LIST_NAME_INVALID_PERIOD',"
    " if(endsWith(variables('varListName'), '.'), 'ERR_LIST_NAME_INVALID_PERIOD',"
    " if(contains(" + RESERVED_ARRAY + ", toLower(variables('varListName'))), 'ERR_LIST_NAME_RESERVED',"
    " ''))))))")

ERROR_MESSAGE_MAP = (
    "@if(equals(variables('varErrorCode'), 'ERR_URL_EMPTY'),"
    " 'SharePointのURLが入力されていません。',"
    " if(equals(variables('varErrorCode'), 'ERR_NOT_HTTPS'),"
    " 'URLが https:// で始まっていません。',"
    " if(equals(variables('varErrorCode'), 'ERR_NOT_SHAREPOINT_HOST'),"
    " 'SharePointのURLではありません（ホスト名が .sharepoint.com で終わっていません）。',"
    " if(equals(variables('varErrorCode'), 'ERR_SITE_URL_NOT_EXTRACTED'),"
    " 'URLからサイトURLを抽出できませんでした。',"
    " if(equals(variables('varErrorCode'), 'ERR_LIST_NAME_EMPTY'),"
    " 'リスト名が入力されていません（前後の空白を除くと空になります）。',"
    " if(equals(variables('varErrorCode'), 'ERR_LIST_NAME_TOO_LONG'),"
    " 'リスト名が長すぎます（255文字以内にしてください）。',"
    " if(equals(variables('varErrorCode'), 'ERR_LIST_NAME_INVALID_CHARS'),"
    " 'リスト名にSharePointで使用できない文字または制御文字が含まれています。',"
    " if(equals(variables('varErrorCode'), 'ERR_LIST_NAME_INVALID_PERIOD'),"
    " 'リスト名の先頭または末尾にピリオドは使用できません。',"
    " if(equals(variables('varErrorCode'), 'ERR_LIST_NAME_RESERVED'),"
    " 'リスト名がSharePointの予約名に該当します。',"
    " '')))))))))")

parse_seq = [
    ("Set_Stage_Parse_Input", setvar("varStage", "ParseAndValidateInput")),
    # フラグメント（#...）を除去
    ("Compose_Url_Without_Fragment",
     compose("@first(split(variables('varInputSharePointUrl'), '#'))")),
    # /_layouts/ の表記ゆれ（_Layouts / _LAYOUTS）を小文字形へ正規化してから分割する
    ("Compose_Url_Normalized_Layouts",
     compose("@replace(replace(" + U_FRAG + ", '/_Layouts/', '/_layouts/'),"
             " '/_LAYOUTS/', '/_layouts/')")),
    # /_layouts/ があればその直前まで、無ければクエリ文字列を除去
    ("Compose_Url_Before_Layouts",
     compose("@if(contains(" + U_NORM + ", '/_layouts/'),"
             " first(split(" + U_NORM + ", '/_layouts/')),"
             " first(split(" + U_NORM + ", '?')))")),
    # 末尾スラッシュ除去。if() は両分岐を先行評価するため substring の長さ計算を使わない
    # （空文字入力で sub(length,1) が -1 になり実行時エラーになりうる）。
    ("Parse_SiteUrl",
     compose("@if(endsWith(outputs('Compose_Url_Before_Layouts'), '/'),"
             " join(take(split(outputs('Compose_Url_Before_Layouts'), '/'),"
             " sub(length(split(outputs('Compose_Url_Before_Layouts'), '/')), 1)), '/'),"
             " outputs('Compose_Url_Before_Layouts'))")),
    # ホスト名（スキームの大文字小文字に依存しないよう '//' で分割して取り出す）
    ("Compose_Site_Host",
     compose("@first(split(last(split(" + P_SITE + ", '//')), '/'))")),
    ("Compose_ListName_Sanitized", compose(_sanitize_expr())),
    ("Validate_SiteUrl", compose(VALIDATE_SITE_URL)),
    ("Validate_ListName", compose(VALIDATE_LIST_NAME)),
    ("Compose_Input_Validation_Code",
     compose("@if(not(empty(outputs('Validate_SiteUrl'))), outputs('Validate_SiteUrl'),"
             " outputs('Validate_ListName'))")),
    ("Set_SiteUrl", setvar("varSiteUrl", "@outputs('Parse_SiteUrl')")),
    ("Set_ErrorCode_From_Input_Validation",
     setvar("varErrorCode", "@outputs('Compose_Input_Validation_Code')")),
    ("Set_IsValid_From_Input_Validation",
     setvar("varIsValid", "@empty(outputs('Compose_Input_Validation_Code'))")),
    ("Set_ErrorMessage_From_Input_Validation", setvar("varErrorMessage", ERROR_MESSAGE_MAP)),
]
parse_actions, parse_last = chain(parse_seq)
parse_actions["Condition_Has_Input_Error"] = cond(
    {"and": [eq("@variables('varIsValid')", False)]},
    {"Append_Input_Error_Message": append(
        "varErrorMessages",
        "@concat(variables('varErrorCode'), ': ', variables('varErrorMessage'))")},
    runafter=ra(parse_last))
actions["Scope_Parse_And_Validate_Input"] = {"type": "Scope", "actions": parse_actions,
                                             "runAfter": ra(LAST_INIT)}

# =========================================================================
# Scope_Verify_SharePoint_Site : 対象サイトへの疎通確認（§8）
# 直後の Set_Site_Status_Code は runAfter=[Succeeded, Failed] で必ず実行し、
# 失敗時もエラーハンドラが「変数経由で」HTTPステータスを読めるようにする。
# =========================================================================
verify_inner, _ = chain([
    ("Store_Site_Id", setvar("varSiteId",
        "@trim(string(coalesce(body('Verify_SharePoint_Web')?['Id'], '')))")),
    ("Store_Site_Title", setvar("varSiteTitle",
        "@trim(string(coalesce(body('Verify_SharePoint_Web')?['Title'], '')))")),
    ("Store_Verified_Url", setvar("varVerifiedUrl",
        "@trim(string(coalesce(body('Verify_SharePoint_Web')?['Url'], '')))")),
], first_runafter={"Verify_SharePoint_Web": ["Succeeded"]})

verify_actions = {}
verify_actions["Verify_SharePoint_Web"] = http(
    "GET", "_api/web?$select=Id,Title,Url", H_NOMETA)
verify_actions["Set_Site_Status_Code"] = setvar(
    "varLastStatusCode", "@string(coalesce(outputs('Verify_SharePoint_Web')?['statusCode'], 0))",
    {"Verify_SharePoint_Web": ["Succeeded", "Failed"]})
verify_actions.update(verify_inner)

site_scope_actions = {}
site_scope_actions["Set_Stage_Verify_Site"] = setvar("varStage", "VerifySharePointSite")
site_scope_actions["Condition_Input_Is_Valid"] = cond(
    {"and": [eq("@variables('varIsValid')", True)]},
    verify_actions, runafter=ra("Set_Stage_Verify_Site"))
actions["Scope_Verify_SharePoint_Site"] = {
    "type": "Scope", "actions": site_scope_actions,
    "runAfter": ra("Scope_Parse_And_Validate_Input")}

# =========================================================================
# Scope_Check_Existing_List : 同名リストの存在確認（§9）
# 非表示リストも対象に含める（$top=5000・Hidden を取得）。
# 比較は toLower(trim(...)) 同士＝大文字小文字と前後空白の違いを同一視する。
# =========================================================================
LISTS_URI = ("_api/web/lists?$select=Id,Title,Hidden,BaseTemplate,"
             "RootFolder/ServerRelativeUrl&$expand=RootFolder&$top=5000")

check_inner, check_last = chain([
    ("Get_All_Lists", http("GET", LISTS_URI, H_NOMETA)),
    ("Store_Existing_Lists", setvar("varExistingLists",
        "@coalesce(body('Get_All_Lists')?['value'], json('[]'))")),
    ("Filter_Matching_List_Names", query(
        "@variables('varExistingLists')",
        "@equals(toLower(trim(coalesce(item()?['Title'], ''))),"
        " toLower(trim(variables('varListName'))))")),
    ("Store_Matched_Lists", setvar("varMatchedLists", "@body('Filter_Matching_List_Names')")),
    ("Determine_List_Existence", setvar("varListExists",
        "@greater(length(variables('varMatchedLists')), 0)")),
])

check_scope_actions = {}
check_scope_actions["Set_Stage_Check_Existing"] = setvar("varStage", "CheckExistingList")
check_scope_actions["Condition_Check_Guard"] = cond(
    {"and": [eq("@variables('varIsValid')", True)]},
    check_inner, runafter=ra("Set_Stage_Check_Existing"))
actions["Scope_Check_Existing_List"] = {
    "type": "Scope", "actions": check_scope_actions,
    "runAfter": ra("Scope_Verify_SharePoint_Site")}

# =========================================================================
# Scope_Create_List : 新規作成（§11）と競合対策（§10）
#
# ボディは Compose のオブジェクトを string() でJSON化して渡す。
# 文字列連結で組み立てないため、リスト名・説明に " 改行 \ が含まれても壊れない。
#
# 作成が2xx以外だった場合は AlreadyExistsOrConflict で終了し、
# **同名リストを取得しに行かない**（指示書§10・§31。検証スクリプトで機械確認する）。
# =========================================================================
CREATE_LIST_BODY_OBJ = {
    "__metadata": {"type": "SP.List"},
    "AllowContentTypes": False,
    "BaseTemplate": 100,
    "ContentTypesEnabled": False,
    "Description": "@variables('varListDescription')",
    "Title": "@variables('varListName')",
}

created_ok, _ = chain([
    ("Store_Created_List_Id", setvar("varCreatedListId",
        "@trim(string(coalesce(body('Create_Generic_List')?['d']?['Id'], '')))")),
    ("Store_Created_List_Title", setvar("varCreatedListTitle",
        "@trim(string(coalesce(body('Create_Generic_List')?['d']?['Title'], '')))")),
    ("Set_Created_In_This_Run", setvar("varCreatedInThisRun", True)),
    ("Get_Created_List_By_Id", http(
        "GET", list_uri("?$select=Id,Title&$expand=RootFolder"), H_NOMETA)),
    ("Store_Created_List_RootFolder", setvar("varCreatedListRootFolder",
        "@trim(string(coalesce(body('Get_Created_List_By_Id')?['RootFolder']?['ServerRelativeUrl'], '')))")),
    ("Set_Status_Created_Pending", setvar("varStatus", "CreatedPendingInitialization")),
])

created_ng, _ = chain([
    ("Set_Status_Conflict", setvar("varStatus", "AlreadyExistsOrConflict")),
    ("Set_ErrorCode_Conflict", setvar("varErrorCode", "ERR_CREATE_CONFLICT")),
    ("Set_ErrorMessage_Conflict", setvar("varErrorMessage",
        "リストの作成に失敗しました（他の実行が同名リストを作成した可能性があります）。既存リストには一切変更を加えていません。")),
    ("Set_IsValid_Conflict", setvar("varIsValid", False)),
    ("Append_Conflict_Message", append("varErrorMessages",
        "@concat('ERR_CREATE_CONFLICT: httpStatusCode=', variables('varLastStatusCode'))")),
])

create_inner = {}
create_inner["Compose_Create_List_Body"] = compose(CREATE_LIST_BODY_OBJ)
create_inner["Create_Generic_List"] = http(
    "POST", "_api/web/lists", H_VERBOSE, "@string(outputs('Compose_Create_List_Body'))",
    ra("Compose_Create_List_Body"))
create_inner["Set_Create_Status_Code"] = setvar(
    "varLastStatusCode", "@string(coalesce(outputs('Create_Generic_List')?['statusCode'], 0))",
    {"Create_Generic_List": ["Succeeded", "Failed"]})
create_inner["Condition_Create_Succeeded"] = cond(
    {"and": [{"greaterOrEquals": ["@int(variables('varLastStatusCode'))", 200]},
             {"lessOrEquals": ["@int(variables('varLastStatusCode'))", 299]}]},
    created_ok, created_ng, ra("Set_Create_Status_Code"))

create_scope_actions = {}
create_scope_actions["Set_Stage_Create_List"] = setvar("varStage", "CreateList")
create_scope_actions["Condition_List_Not_Exists"] = cond(
    {"and": [eq("@variables('varListExists')", False),
             eq("@variables('varIsValid')", True)]},
    create_inner, runafter=ra("Set_Stage_Create_List"))
actions["Scope_Create_List"] = {
    "type": "Scope", "actions": create_scope_actions,
    "runAfter": ra("Scope_Check_Existing_List")}

# =========================================================================
# 初期化系スコープ共通のガード
# varCreatedInThisRun=true（＝今回の実行で作成したリスト）のときだけ実行する。
# 既存リストが対象になる経路は構造的に存在しない。
# =========================================================================
INIT_GUARD = {"and": [eq("@variables('varCreatedInThisRun')", True),
                      eq("@variables('varIsValid')", True)]}

# =========================================================================
# Scope_Initialize_List : 空確認・添付無効化・Title の Required 解除（§13・§14・§17）
# =========================================================================
not_empty_actions, _ = chain([
    ("Set_ErrorCode_List_Not_Empty", setvar("varErrorCode", "ERR_LIST_NOT_EMPTY")),
    ("Set_ErrorMessage_List_Not_Empty", setvar("varErrorMessage",
        "作成直後のリストにアイテムが存在します。異常のため初期化を中止しました（アイテムの削除は行いません）。")),
    ("Set_IsValid_List_Not_Empty", setvar("varIsValid", False)),
    ("Append_List_Not_Empty_Message", append("varErrorMessages",
        "@concat('ERR_LIST_NOT_EMPTY: itemCount=', string(variables('varItemCount')))")),
])

empty_ok_actions, _ = chain([
    # 添付ファイル機能を無効化（リファレンス EnableAttachments と同形。値だけ false）
    ("Disable_Attachments", http("POST", list_uri(), H_MERGE_V,
        "@string(outputs('Compose_Disable_Attachments_Body'))")),
    # Title は削除できないシステム列。可能な範囲で必須を解除する
    # （リファレンス deactivateSPOTitle と同一形式・nometadata で実績あり）
    ("Deactivate_Title_Required", http(
        "POST", list_uri("/fields/getbyinternalnameortitle(''Title'')"), H_MERGE_N,
        "@string(outputs('Compose_Title_Not_Required_Body'))")),
])

init_list_inner, _ = chain([
    ("Compose_Disable_Attachments_Body",
     compose({"__metadata": {"type": "SP.List"}, "EnableAttachments": False})),
    ("Compose_Title_Not_Required_Body", compose({"Required": False})),
    ("Verify_Empty_List", http("GET", list_uri("/ItemCount"), H_NOMETA)),
    ("Store_Item_Count", setvar("varItemCount",
        "@int(coalesce(body('Verify_Empty_List')?['value'], 0))")),
])
init_list_inner["Condition_List_Is_Empty"] = cond(
    {"and": [eq("@variables('varItemCount')", 0)]},
    empty_ok_actions, not_empty_actions, ra("Store_Item_Count"))

init_scope_actions = {}
init_scope_actions["Set_Stage_Initialize_List"] = setvar("varStage", "InitializeList")
init_scope_actions["Condition_Initialize_Guard"] = cond(
    INIT_GUARD, init_list_inner, runafter=ra("Set_Stage_Initialize_List"))
actions["Scope_Initialize_List"] = {
    "type": "Scope", "actions": init_scope_actions, "runAfter": ra("Scope_Create_List")}

# =========================================================================
# Scope_Delete_Deletable_Fields : 削除可能な列だけを削除（§15・§16・§17）
#
# 削除対象は CanBeDeleted=true かつ InternalName != sample_raw。
# **列名の固定リストでは判定しない**（Title等のシステム列を強制削除しないため）。
# Apply to each は並列オフ。失敗した列は記録し、初期化全体を成功扱いにしない。
# =========================================================================
FIELDS_SELECT = ("/fields?$select=Id,Title,InternalName,StaticName,CanBeDeleted,Hidden,"
                 "ReadOnlyField,Sealed,FromBaseType,Required,TypeAsString")

DELETE_FIELD_URI = ("@concat('_api/web/lists(guid''', variables('varCreatedListId'),"
                    " ''')/fields(guid''', items('Apply_to_each_DeleteField')?['Id'],"
                    " ''')/deleteObject()')")

delete_loop_actions = {}
delete_loop_actions["Delete_Deletable_Field"] = http("POST", DELETE_FIELD_URI, H_NOMETA)
delete_loop_actions["Append_Deleted_Field"] = append("varDeletedFields", {
    "id": "@coalesce(items('Apply_to_each_DeleteField')?['Id'], '')",
    "internalName": "@coalesce(items('Apply_to_each_DeleteField')?['InternalName'], '')",
    "title": "@coalesce(items('Apply_to_each_DeleteField')?['Title'], '')",
    "typeAsString": "@coalesce(items('Apply_to_each_DeleteField')?['TypeAsString'], '')",
}, {"Delete_Deletable_Field": ["Succeeded"]})
delete_loop_actions["Append_Field_Delete_Error"] = append("varFieldDeleteErrors", {
    "internalName": "@coalesce(items('Apply_to_each_DeleteField')?['InternalName'], '')",
    "title": "@coalesce(items('Apply_to_each_DeleteField')?['Title'], '')",
    "httpStatusCode": "@string(coalesce(outputs('Delete_Deletable_Field')?['statusCode'], 0))",
}, {"Delete_Deletable_Field": ["Failed", "TimedOut"]})

skip_loop_actions = {"Append_Skipped_System_Field": append("varSkippedFields", {
    "internalName": "@coalesce(items('Apply_to_each_SystemField')?['InternalName'], '')",
    "title": "@coalesce(items('Apply_to_each_SystemField')?['Title'], '')",
    "typeAsString": "@coalesce(items('Apply_to_each_SystemField')?['TypeAsString'], '')",
    "reason": "CanBeDeleted=false のため削除しない（既定ビューからは除外済み。フォームからの非表示化は未実施）",
})}

fields_inner, _ = chain([
    ("Get_All_List_Fields", http("GET", list_uri(FIELDS_SELECT), H_NOMETA)),
    ("Filter_Deletable_Fields", query(
        "@coalesce(body('Get_All_List_Fields')?['value'], json('[]'))",
        "@and(equals(coalesce(item()?['CanBeDeleted'], false), true),"
        " not(equals(coalesce(item()?['InternalName'], ''), 'sample_raw')))")),
    ("Filter_System_Fields", query(
        "@coalesce(body('Get_All_List_Fields')?['value'], json('[]'))",
        "@equals(coalesce(item()?['CanBeDeleted'], false), false)")),
    ("Apply_to_each_SystemField", foreach("@body('Filter_System_Fields')", skip_loop_actions)),
    ("Apply_to_each_DeleteField", foreach("@body('Filter_Deletable_Fields')", delete_loop_actions)),
])

del_scope_actions = {}
del_scope_actions["Set_Stage_Delete_Fields"] = setvar("varStage", "DeleteDeletableFields")
del_scope_actions["Condition_Delete_Fields_Guard"] = cond(
    INIT_GUARD, fields_inner, runafter=ra("Set_Stage_Delete_Fields"))
actions["Scope_Delete_Deletable_Fields"] = {
    "type": "Scope", "actions": del_scope_actions, "runAfter": ra("Scope_Initialize_List")}

# =========================================================================
# Scope_Create_SampleRaw_Field : sample_raw の作成と確認（§18・§19）
# =========================================================================
SAMPLE_RAW_BODY_OBJ = {
    "parameters": {
        "__metadata": {"type": "SP.XmlSchemaFieldCreationInformation"},
        "SchemaXml": SAMPLE_RAW_SCHEMA_XML,
        "Options": 0,
    }
}

SR = "body('Verify_SampleRaw_Field')"
SAMPLE_RAW_OK = (
    "@and(and(equals(coalesce(" + SR + "?['InternalName'], ''), 'sample_raw'),"
    " equals(coalesce(" + SR + "?['Required'], true), false)),"
    " and(equals(coalesce(" + SR + "?['Hidden'], true), false),"
    " and(equals(coalesce(" + SR + "?['TypeAsString'], ''), 'Note'),"
    " contains(coalesce(" + SR + "?['SchemaXml'], ''), 'RichTextMode=\"FullHtml\"'))))")

sr_ng_actions, _ = chain([
    ("Set_ErrorCode_SampleRaw_Invalid", setvar("varErrorCode", "ERR_SAMPLERAW_VERIFICATION_FAILED")),
    ("Set_ErrorMessage_SampleRaw_Invalid", setvar("varErrorMessage",
        "sample_raw列の検証に失敗しました（内部名・必須・非表示・型・リッチテキスト設定のいずれかが期待と異なります）。")),
    ("Set_IsValid_SampleRaw_Invalid", setvar("varIsValid", False)),
    ("Append_SampleRaw_Invalid_Message", append("varErrorMessages",
        "@concat('ERR_SAMPLERAW_VERIFICATION_FAILED: typeAsString=',"
        " string(coalesce(body('Verify_SampleRaw_Field')?['TypeAsString'], '')))")),
])

sr_inner, _ = chain([
    ("Compose_SampleRaw_Field_Body", compose(SAMPLE_RAW_BODY_OBJ)),
    ("Create_SampleRaw_Field", http("POST", list_uri("/fields/createFieldAsXml"), H_VERBOSE,
        "@string(outputs('Compose_SampleRaw_Field_Body'))")),
    ("Verify_SampleRaw_Field", http("GET", list_uri(
        "/fields/getbyinternalnameortitle(''sample_raw'')"
        "?$select=Id,Title,InternalName,StaticName,TypeAsString,Required,Hidden,ReadOnlyField,SchemaXml"),
        H_NOMETA)),
    ("Compose_SampleRaw_Verification", compose(SAMPLE_RAW_OK)),
])
sr_inner["Condition_SampleRaw_Valid"] = cond(
    {"and": [eq("@outputs('Compose_SampleRaw_Verification')", True)]},
    {"Set_SampleRaw_Created": setvar("varSampleRawCreated", True)},
    sr_ng_actions, ra("Compose_SampleRaw_Verification"))

sr_scope_actions = {}
sr_scope_actions["Set_Stage_Create_SampleRaw"] = setvar("varStage", "CreateSampleRawField")
sr_scope_actions["Condition_Create_SampleRaw_Guard"] = cond(
    INIT_GUARD, sr_inner, runafter=ra("Set_Stage_Create_SampleRaw"))
actions["Scope_Create_SampleRaw_Field"] = {
    "type": "Scope", "actions": sr_scope_actions,
    "runAfter": ra("Scope_Delete_Deletable_Fields")}

# =========================================================================
# Scope_Configure_Default_View : 既定ビューを sample_raw だけにする（§20〜§24）
# ビューは DefaultView プロパティで特定する（「すべてのアイテム」等の名前では判定しない）。
# =========================================================================
ADD_VIEW_BODY_OBJ = {"__metadata": {"type": "SP.View"}, "SetAsDefaultView": True}

view_found_actions, _ = chain([
    ("Remove_All_Default_View_Fields",
     http("POST", view_uri("/viewfields/removeAllViewFields()"), H_NOMETA)),
    ("Add_SampleRaw_To_Default_View",
     http("POST", view_uri("/viewfields/AddViewField(''sample_raw'')"), H_MERGE_V,
          "@string(outputs('Compose_Add_View_Field_Body'))")),
    ("Verify_Default_View_Fields", http("GET", view_uri("/ViewFields"), H_NOMETA)),
    ("Store_Final_View_Fields", setvar("varFinalViewFields",
        "@coalesce(body('Verify_Default_View_Fields')?['Items'], json('[]'))")),
])

view_missing_actions, _ = chain([
    ("Set_ErrorCode_View_Not_Found", setvar("varErrorCode", "ERR_DEFAULT_VIEW_NOT_FOUND")),
    ("Set_ErrorMessage_View_Not_Found", setvar("varErrorMessage",
        "既定ビュー（DefaultView=true）を特定できませんでした。")),
    ("Set_IsValid_View_Not_Found", setvar("varIsValid", False)),
    ("Append_View_Not_Found_Message", append("varErrorMessages",
        "ERR_DEFAULT_VIEW_NOT_FOUND: DefaultView=true のビューが見つかりません")),
])

view_inner, _ = chain([
    ("Compose_Add_View_Field_Body", compose(ADD_VIEW_BODY_OBJ)),
    ("Get_Default_View", http("GET", list_uri(
        "/views?$select=Id,Title,DefaultView,Hidden,ViewType,RowLimit"), H_NOMETA)),
    ("Filter_Default_View", query(
        "@coalesce(body('Get_Default_View')?['value'], json('[]'))",
        "@equals(coalesce(item()?['DefaultView'], false), true)")),
    ("Store_Default_View_Id", setvar("varDefaultViewId",
        "@trim(string(coalesce(first(body('Filter_Default_View'))?['Id'], '')))")),
    ("Store_Default_View_Title", setvar("varDefaultViewTitle",
        "@trim(string(coalesce(first(body('Filter_Default_View'))?['Title'], '')))")),
])
view_inner["Condition_Default_View_Found"] = cond(
    {"and": [{"greater": ["@length(variables('varDefaultViewId'))", 0]}]},
    view_found_actions, view_missing_actions, ra("Store_Default_View_Title"))

view_scope_actions = {}
view_scope_actions["Set_Stage_Configure_View"] = setvar("varStage", "ConfigureDefaultView")
view_scope_actions["Condition_Configure_View_Guard"] = cond(
    INIT_GUARD, view_inner, runafter=ra("Set_Stage_Configure_View"))
actions["Scope_Configure_Default_View"] = {
    "type": "Scope", "actions": view_scope_actions,
    "runAfter": ra("Scope_Create_SampleRaw_Field")}

# =========================================================================
# Scope_Validate_Result : 最終判定（§25）
# =========================================================================
FINAL_VALIDATION = (
    "@if(not(equals(variables('varItemCount'), 0)), 'ERR_LIST_NOT_EMPTY',"
    " if(not(equals(variables('varSampleRawCreated'), true)), 'ERR_SAMPLERAW_MISSING',"
    " if(greater(length(variables('varFieldDeleteErrors')), 0), 'ERR_FIELD_DELETE_FAILED',"
    " if(empty(variables('varDefaultViewId')), 'ERR_DEFAULT_VIEW_NOT_FOUND',"
    " if(not(equals(length(variables('varFinalViewFields')), 1)), 'ERR_VIEW_FIELDS_NOT_ONLY_SAMPLERAW',"
    " if(not(equals(string(first(variables('varFinalViewFields'))), 'sample_raw')),"
    " 'ERR_VIEW_FIELDS_NOT_ONLY_SAMPLERAW',"
    " ''))))))")

validate_inner, _ = chain([
    ("Compose_Final_Validation_Code", compose(FINAL_VALIDATION)),
    # 既存のエラーコードを保つ／無ければ最終検証の結果を採用する。
    # SetVariable の値式で varErrorCode 自身を参照すると自己参照エラーになるため、
    # 一度 Compose に出してから代入する。
    ("Compose_Final_Error_Code", compose(
        "@if(empty(outputs('Compose_Final_Validation_Code')), variables('varErrorCode'),"
        " outputs('Compose_Final_Validation_Code'))")),
    ("Set_Final_Error_Code", setvar("varErrorCode", "@outputs('Compose_Final_Error_Code')")),
    ("Set_Status_Final", setvar("varStatus",
        "@if(and(equals(variables('varIsValid'), true),"
        " empty(outputs('Compose_Final_Validation_Code'))), 'Created', 'InitializationFailed')")),
])

validate_scope_actions = {}
validate_scope_actions["Set_Stage_Validate_Result"] = setvar("varStage", "ValidateResult")
validate_scope_actions["Condition_Validate_Guard"] = cond(
    {"and": [eq("@variables('varCreatedInThisRun')", True)]},
    validate_inner, runafter=ra("Set_Stage_Validate_Result"))
actions["Scope_Validate_Result"] = {
    "type": "Scope", "actions": validate_scope_actions,
    "runAfter": ra("Scope_Configure_Default_View")}

# =========================================================================
# Scope_Handle_AlreadyExists : 同名リストがあった場合（§9.3）
# 既存リストへの変更は一切行わない。存在確認で得た情報を結果に載せるだけ。
# =========================================================================
EXISTING_INFO = {
    "id": "@trim(string(coalesce(first(variables('varMatchedLists'))?['Id'], '')))",
    "title": "@trim(string(coalesce(first(variables('varMatchedLists'))?['Title'], '')))",
    "hidden": "@coalesce(first(variables('varMatchedLists'))?['Hidden'], false)",
    "serverRelativeUrl":
        "@trim(string(coalesce(first(variables('varMatchedLists'))?['RootFolder']?['ServerRelativeUrl'], '')))",
}

already_inner, _ = chain([
    ("Return_Already_Exists", compose(EXISTING_INFO)),
    ("Set_Existing_List_Info", setvar("varExistingListInfo", "@outputs('Return_Already_Exists')")),
    ("Set_Status_Already_Exists", setvar("varStatus", "AlreadyExists")),
])

already_scope_actions = {}
already_scope_actions["Set_Stage_Handle_AlreadyExists"] = setvar("varStage", "HandleAlreadyExists")
already_scope_actions["Condition_Already_Exists"] = cond(
    {"and": [eq("@variables('varListExists')", True)]},
    already_inner, runafter=ra("Set_Stage_Handle_AlreadyExists"))
actions["Scope_Handle_AlreadyExists"] = {
    "type": "Scope", "actions": already_scope_actions,
    "runAfter": ra("Scope_Validate_Result")}

# =========================================================================
# Scope_Handle_Error（Catch相当）
# runAfter は直前の1本だけに張る。複数Scopeを列挙すると AND 判定になり
# 「前段成功・中段失敗」でハンドラが発火しない。直列連鎖なら前段失敗時に
# 後段が Skipped になるため、最終Scopeの Skipped/Failed/TimedOut で確実に捕捉できる。
# ハンドラ内の式は変数だけを参照する（未実行アクションの outputs を参照しない）。
# =========================================================================
HANDLER_CODE = (
    "@if(not(empty(variables('varErrorCode'))), variables('varErrorCode'),"
    " if(equals(variables('varLastStatusCode'), '401'), 'ERR_PERMISSION_DENIED',"
    " if(equals(variables('varLastStatusCode'), '403'), 'ERR_PERMISSION_DENIED',"
    " if(equals(variables('varLastStatusCode'), '404'), 'ERR_SITE_OR_RESOURCE_NOT_FOUND',"
    " if(equals(variables('varLastStatusCode'), '400'), 'ERR_BAD_REQUEST',"
    " 'ERR_UNEXPECTED_FAILURE')))))")

HANDLER_MESSAGE = (
    "@if(not(empty(variables('varErrorMessage'))), variables('varErrorMessage'),"
    " if(equals(variables('varLastStatusCode'), '401'),"
    " 'SharePointへの認証に失敗しました。接続を作り直してください。',"
    " if(equals(variables('varLastStatusCode'), '403'),"
    " '対象サイトに対する権限が不足しています（サイトの参照、またはリスト・列・ビューの管理権限を確認してください）。',"
    " if(equals(variables('varLastStatusCode'), '404'),"
    " '対象のサイトまたはリソースが見つかりません。入力したURLがSharePointサイトのURLか確認してください。',"
    " if(equals(variables('varLastStatusCode'), '400'),"
    " 'SharePointへの要求が不正です。リスト名に使用できない文字が含まれていないか確認してください。',"
    " '想定外のエラーが発生しました。実行履歴で失敗したアクションを確認してください。')))))")

handler_inner, _ = chain([
    ("Compose_Handler_Error_Code", compose(HANDLER_CODE)),
    ("Compose_Handler_Error_Message", compose(HANDLER_MESSAGE)),
    ("Handle_Error", compose(
        "@union(variables('varErrorMessages'),"
        " createArray(concat('stage=', variables('varStage')),"
        " concat('httpStatusCode=', variables('varLastStatusCode')),"
        " concat('createdInThisRun=', string(variables('varCreatedInThisRun'))),"
        " concat('createdListId=', variables('varCreatedListId'))))")),
    ("Set_Error_Code_From_Handler", setvar("varErrorCode", "@outputs('Compose_Handler_Error_Code')")),
    ("Set_Error_Message_From_Handler", setvar("varErrorMessage",
        "@outputs('Compose_Handler_Error_Message')")),
    ("Set_Error_Messages_From_Handler", setvar("varErrorMessages", "@outputs('Handle_Error')")),
    ("Set_Status_Failed", setvar("varStatus",
        "@if(equals(variables('varCreatedInThisRun'), true), 'InitializationFailed', 'Failed')")),
])
actions["Scope_Handle_Error"] = {
    "type": "Scope", "actions": handler_inner,
    "runAfter": {"Scope_Handle_AlreadyExists": ["Failed", "Skipped", "TimedOut"]}}

# =========================================================================
# Scope_Rollback_New_List : 今回作成したリストだけを削除する（§27）
#
# 削除対象は varCreatedListId と完全一致するリストのみ。
# リスト名での再検索は行わない（既存リストの誤削除を構造的に防ぐ）。
# =========================================================================
rollback_inner, _ = chain([
    ("Rollback_Newly_Created_List", http("POST", list_uri(), H_DELETE)),
    ("Set_Rollback_Performed", setvar("varRollbackPerformed", True)),
])

rollback_scope_actions = {}
rollback_scope_actions["Condition_Rollback_Allowed"] = cond(
    {"and": [eq("@variables('varCreatedInThisRun')", True),
             eq("@variables('varListExists')", False),
             {"greater": ["@length(variables('varCreatedListId'))", 0]},
             {"not": eq("@variables('varStatus')", "Created")}]},
    rollback_inner)
actions["Scope_Rollback_New_List"] = {
    "type": "Scope", "actions": rollback_scope_actions,
    "runAfter": {"Scope_Handle_Error": ["Succeeded", "Failed", "Skipped", "TimedOut"]}}

# =========================================================================
# Scope_Finalize : 結果JSONの組み立て（§29）
# すべての状態が確定した後に1箇所で組み立てる。参照するのは変数だけ。
# =========================================================================
SITE_OBJ = {"id": "@variables('varSiteId')", "title": "@variables('varSiteTitle')",
            "url": "@variables('varVerifiedUrl')"}

CREATED_RESULT = {
    "success": True,
    "status": "Created",
    "created": True,
    "message": "リストを新規作成し、初期化しました。",
    "site": SITE_OBJ,
    "list": {
        "id": "@variables('varCreatedListId')",
        "title": "@variables('varCreatedListTitle')",
        "rootFolder": "@variables('varCreatedListRootFolder')",
        "itemCount": "@variables('varItemCount')",
    },
    "initialization": {
        "deletedFields": "@variables('varDeletedFields')",
        "skippedSystemFields": "@variables('varSkippedFields')",
        "sampleRawCreated": "@variables('varSampleRawCreated')",
        "sampleRawInternalName": "sample_raw",
        "sampleRawType": "EnhancedRichText",
        "defaultViewId": "@variables('varDefaultViewId')",
        "defaultViewTitle": "@variables('varDefaultViewTitle')",
        "defaultViewFields": "@variables('varFinalViewFields')",
    },
}

ALREADY_EXISTS_RESULT = {
    "success": True,
    "status": "AlreadyExists",
    "created": False,
    "message": "同名のリストが既に存在するため、作成処理を実行しませんでした。",
    "siteUrl": "@variables('varSiteUrl')",
    "listName": "@variables('varListName')",
    "existingList": "@variables('varExistingListInfo')",
}

FAILED_RESULT = {
    "success": False,
    "status": "@variables('varStatus')",
    "created": "@variables('varCreatedInThisRun')",
    "message": "@variables('varErrorMessage')",
    "stage": "@variables('varStage')",
    "siteUrl": "@variables('varSiteUrl')",
    "listName": "@variables('varListName')",
    "createdListId": "@variables('varCreatedListId')",
    "rollbackPerformed": "@variables('varRollbackPerformed')",
    "errors": "@variables('varErrorMessages')",
}

build_created = {
    "Build_Result_Object": compose(CREATED_RESULT),
    "Set_Result_Object_Created": setvar("varResultObject", "@outputs('Build_Result_Object')",
                                        ra("Build_Result_Object")),
}
build_failed = {
    "Build_Error_Result": compose(FAILED_RESULT),
    "Set_Result_Object_Failed": setvar("varResultObject", "@outputs('Build_Error_Result')",
                                       ra("Build_Error_Result")),
}
build_already = {
    "Build_AlreadyExists_Result": compose(ALREADY_EXISTS_RESULT),
    "Set_Result_Object_AlreadyExists": setvar(
        "varResultObject", "@outputs('Build_AlreadyExists_Result')",
        ra("Build_AlreadyExists_Result")),
}

finalize_actions = {}
finalize_actions["Condition_Result_Is_AlreadyExists"] = cond(
    {"and": [eq("@variables('varStatus')", "AlreadyExists")]},
    build_already,
    {"Condition_Result_Is_Created": cond(
        {"and": [eq("@variables('varStatus')", "Created")]},
        build_created, build_failed)})
finalize_actions["Serialize_Result_To_Json"] = setvar(
    "varResultJson", "@string(variables('varResultObject'))",
    ra("Condition_Result_Is_AlreadyExists"))
finalize_actions["Compose_Flow_Output"] = compose({
    "success": "@coalesce(variables('varResultObject')?['success'], false)",
    "status": "@variables('varStatus')",
    "resultObject": "@variables('varResultObject')",
    "resultJson": "@variables('varResultJson')",
}, ra("Serialize_Result_To_Json"))

actions["Scope_Finalize"] = {
    "type": "Scope", "actions": finalize_actions,
    "runAfter": {"Scope_Rollback_New_List": ["Succeeded", "Failed", "Skipped", "TimedOut"]}}

# =========================================================================
# definition.json / manifest 群
# =========================================================================
definition = {
    "metadata": {"creator": {}, "provisioningMethod": "FromDefinition",
                 "creationSource": "Portal", "modifiedSources": "Portal"},
    "$schema": "https://schema.management.azure.com/providers/Microsoft.Logic/schemas/2016-06-01/workflowdefinition.json#",
    "contentVersion": "1.0.0.0",
    "parameters": {
        "$authentication": {"defaultValue": {}, "type": "SecureObject"},
        "$connections": {"defaultValue": {}, "type": "Object"},
    },
    "triggers": {
        "manual": {
            "type": "Request", "kind": "Button",
            "inputs": {"schema": {
                "type": "object",
                "properties": {
                    "SharePointUrl": {
                        "title": "SharePointサイトまたはリスト一覧URL",
                        "type": "string",
                        "description": "例: https://{tenant}.sharepoint.com/sites/{siteName} または .../_layouts/15/viewlsts.aspx",
                    },
                    "ListName": {
                        "title": "作成するリスト名",
                        "type": "string",
                        "description": "作成するリストの名前。同名リストが既に存在する場合は何も作成しません",
                    },
                    "ListDescription": {
                        "title": "リストの説明",
                        "type": "string",
                        "description": "省略時は「" + DEFAULT_DESCRIPTION + "」が設定されます",
                    },
                },
                "required": ["SharePointUrl", "ListName"],
            }},
        },
    },
    "actions": actions,
}

flow = {
    "name": FLOW_ID,
    "id": "/providers/Microsoft.Flow/flows/" + FLOW_ID,
    "type": "Microsoft.Flow/flows",
    "properties": {
        "apiId": "/providers/Microsoft.PowerApps/apis/shared_logicflows",
        "displayName": FLOW_DISPLAY_NAME,
        "definition": definition,
        "connectionReferences": {
            "shared_sharepointonline": {
                "connectionName": CN_SPO,
                "source": "Invoker",
                "id": "/providers/Microsoft.PowerApps/apis/shared_sharepointonline",
                "tier": "NotSpecified",
                "apiName": "sharepointonline",
            },
        },
        "flowFailureAlertSubscribed": False,
        "isManaged": False,
    },
}

root_manifest = {
    "schema": "1.0",
    "details": {
        "displayName": FLOW_LOGICAL_NAME,
        "description": "指定サイトに同名リストが無い場合だけ、初期化済みリスト（sample_rawのみ）を作成する",
        "createdTime": "2026-07-24T00:00:00.0000000Z",
        "packageTelemetryId": PKG_TELE,
        "creator": "N/A",
        "sourceEnvironment": "",
    },
    "resources": {
        PKG_FOLDER: {
            "type": "Microsoft.Flow/flows", "suggestedCreationType": "New",
            "creationType": "Existing, New, Update",
            "details": {"displayName": FLOW_DISPLAY_NAME},
            "configurableBy": "User", "hierarchy": "Root",
            "dependsOn": [API_SPO, CONN_SPO],
        },
        API_SPO: {
            "id": "/providers/Microsoft.PowerApps/apis/shared_sharepointonline",
            "name": "shared_sharepointonline", "type": "Microsoft.PowerApps/apis",
            "suggestedCreationType": "Existing",
            "details": {"displayName": "SharePoint"},
            "configurableBy": "System", "hierarchy": "Child", "dependsOn": [],
        },
        CONN_SPO: {
            "type": "Microsoft.PowerApps/apis/connections",
            "suggestedCreationType": "Existing", "creationType": "Existing",
            "details": {"displayName": "SharePoint への接続を選択してください"},
            "configurableBy": "User", "hierarchy": "Child", "dependsOn": [API_SPO],
        },
    },
}

flows_manifest = {"packageSchemaVersion": "1.0", "flowAssets": {"assetPaths": [PKG_FOLDER]}}
apis_map = {"shared_sharepointonline": API_SPO}
connections_map = {"shared_sharepointonline": CONN_SPO}


def write_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def clean_build(path):
    """既存の生成物を消す。OneDrive同期中はフォルダ削除が拒否されることがあるため、
    ファイル削除を主とし、フォルダ削除の失敗は無視する（全ファイルを毎回書き直すため無害）。"""
    if not os.path.isdir(path):
        return
    for root, dirs, fs in os.walk(path, topdown=False):
        for f in fs:
            try:
                os.remove(os.path.join(root, f))
            except OSError as e:
                print("warn: 削除できないファイル（上書きで継続）:", os.path.join(root, f), e)
        for d in dirs:
            try:
                os.rmdir(os.path.join(root, d))
            except OSError:
                pass


clean_build(BUILD)

flow_dir = os.path.join(BUILD, "Microsoft.Flow", "flows", PKG_FOLDER)
write_json(os.path.join(BUILD, "manifest.json"), root_manifest)
write_json(os.path.join(BUILD, "Microsoft.Flow", "flows", "manifest.json"), flows_manifest)
write_json(os.path.join(flow_dir, "definition.json"), flow)
write_json(os.path.join(flow_dir, "apisMap.json"), apis_map)
write_json(os.path.join(flow_dir, "connectionsMap.json"), connections_map)

print("built:", BUILD)
for root, _, fs in os.walk(BUILD):
    for f in sorted(fs):
        print("  ", os.path.relpath(os.path.join(root, f), BUILD).replace(os.sep, "/"))
