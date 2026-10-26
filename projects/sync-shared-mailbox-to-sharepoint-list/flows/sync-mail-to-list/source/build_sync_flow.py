# -*- coding: utf-8 -*-
"""
SyncSharedMailboxToSharePointList のレガシーパッケージ（展開形）を生成する。

手動実行時に指定された共有メールボックスから最新メールを取得し、
指定SharePointサイト上のリストへ登録（新規）または更新（既存）する。

安全設計の柱（既存リスト・既存メールを絶対に壊さないための構造）:
  1. 入力検証を通過するまで SharePoint / Outlook へ一切書き込まない
  2. 同名リスト確認（非表示リスト含む・大文字小文字/前後空白を無視・完全一致）を作成より前に必ず通す
  3. 同名リストがある場合は列・ビュー・設定を一切変更しない（スキーマ確認だけ行う）
  4. 初期化系（列作成・Title変更・ビュー操作）は varCreatedInThisRun == true のガード配下のみ
  5. 書き込み系RESTのURIは必ず varListId を使う。GetByTitle( は1件も使わない
  6. 破壊的REST（deleteObject / recycle / DELETE）は1件も持たない
  7. メールは読むだけ。既読化・移動・削除・フラグ・送信のアクションを持たない
  8. メッセージIDの重複判定は $filter の完全一致。値は '' 2重化 + uriComponent() でエスケープ

REST形式は実働リファレンス CreateKnowledgeList / create_initialized_sharepoint_list
（実環境インポート・実行実績あり）から流用している。
Scope による Try/Catch/Finally と結果JSONは teams_post_url_flows に倣う。

【不変則】definition.json は生成物。修正は必ず本スクリプトを編集して再生成する。
"""
import json, os

HERE = os.path.dirname(os.path.abspath(__file__))
BUILD = os.path.join(HERE, "package")

FLOW_LOGICAL_NAME = "SyncSharedMailboxToSharePointList"
FLOW_DISPLAY_NAME = "共有メールボックスのメールをSharePointリストへ同期"

MAX_MAIL_COUNT = 100          # 指示§4.4 / 調整制限300コール/60秒と実行時間上限から決定
MAX_BODY_LENGTH = 63999       # SharePoint 複数行テキスト（Note）の上限
MAX_TEXT_LENGTH = 255         # 1行テキスト（Text）の上限

# ---- 固定GUID（本フロー用に新規採番・匿名。実テナントの値は一切含まない） ----
FLOW_ID    = "3a7c1e58-42d9-4b06-8e73-c51f9a2d6b84"
PKG_FOLDER = "9e5b28d1-7c34-4af0-b962-13d8e7a05c6f"
API_SPO    = "6d24b83f-05ae-4197-8c5b-72f1a9e34d08"
CONN_SPO   = "b81f5c07-3e62-49da-97b4-0af6d2e51c93"
API_OL     = "45c0e93a-1b78-4d26-8f51-e6a34b07d95c"
CONN_OL    = "72e6a1d5-9f03-4c81-b47e-58d0c93a26fb"
API_CC     = "1f83d64b-c027-45e9-a3d8-90b715e4c62a"
CONN_CC    = "d509b72e-6a41-4f38-95c0-2b8e1d7a64f3"
CN_SPO     = "a1c93e6d70b4482fb85e26d1c07f3a94"   # connectionReferences.connectionName（匿名）
CN_OL      = "5f28b7d1c3e04a69b071e4a92d38c5b6"
CN_CC      = "e6b04a37d1f9425c8a3b70e952d1c48f"
PKG_TELE   = "8c1d47f0-25b6-4e93-a70d-63f8b1e40c25"

# 接続参照は Invoker 形式（2026-07-24 に実環境インポート・実行成功を確認した形）。
AUTH = {"value": "@json(decodeBase64(triggerOutputs().headers['X-MS-APIM-Tokens']))['$ConnectionKey']",
        "type": "Raw"}
HOST_SPO = {"apiId": "/providers/Microsoft.PowerApps/apis/shared_sharepointonline",
            "connectionName": "shared_sharepointonline", "operationId": "HttpRequest"}
HOST_OL = {"apiId": "/providers/Microsoft.PowerApps/apis/shared_office365",
           "connectionName": "shared_office365", "operationId": "GetEmailsV3"}
HOST_CC = {"apiId": "/providers/Microsoft.PowerApps/apis/shared_conversionservice",
           "connectionName": "shared_conversionservice", "operationId": "HtmlToText"}

# ---- ヘッダー（実働リファレンスで実証済みの組み合わせ） ----
H_VERBOSE = {"Accept": "application/json;odata=verbose",
             "Content-Type": "application/json;odata=verbose"}
H_NOMETA = {"Accept": "application/json;odata=nometadata"}
H_MERGE_V = {"Accept": "application/json;odata=verbose",
             "Content-Type": "application/json;odata=verbose",
             "IF-MATCH": "*", "X-HTTP-Method": "MERGE"}
H_MERGE_N = {"Accept": "application/json;odata=nometadata",
             "Content-Type": "application/json;odata=nometadata",
             "IF-MATCH": "*", "X-HTTP-Method": "MERGE"}

# サイトアドレスは常に実行時に解析した値を使う（サイトURLをフローへ固定しない）
DATASET = "@variables('varSiteUrl')"

# =========================================================================
# 列定義（指示§9・§10）
#   内部名は表示名から独立した安定ASCII。DisplayName=Name=StaticName=ASCII で
#   作成すると内部名が指定どおりになる（handbook/knowledge/sharepoint_rest_list_provisioning.md §4）。
#   そのうえで表示名だけを日本語へ MERGE でリネームする（内部名は変わらない）。
# =========================================================================
FIELDS = [
    {
        "internal": "MessageId", "display": "メッセージID", "type": "Text",
        "xml": ('<Field Type="Text" Name="MessageId" StaticName="MessageId"'
                ' DisplayName="MessageId" Required="TRUE" MaxLength="255"'
                ' Indexed="TRUE" EnforceUniqueValues="TRUE" />'),
    },
    {
        "internal": "ReceivedDateTime", "display": "日時", "type": "DateTime",
        "xml": ('<Field Type="DateTime" Name="ReceivedDateTime" StaticName="ReceivedDateTime"'
                ' DisplayName="ReceivedDateTime" Required="FALSE" Format="DateTime"'
                ' Indexed="TRUE" />'),
    },
    {
        "internal": "SenderAddress", "display": "送信元アドレス", "type": "Text",
        "xml": ('<Field Type="Text" Name="SenderAddress" StaticName="SenderAddress"'
                ' DisplayName="SenderAddress" Required="FALSE" MaxLength="255" />'),
    },
    {
        "internal": "Subject", "display": "件名", "type": "Text",
        "xml": ('<Field Type="Text" Name="Subject" StaticName="Subject"'
                ' DisplayName="Subject" Required="FALSE" MaxLength="255" />'),
    },
    {
        "internal": "BodyPlainText", "display": "本文", "type": "Note",
        "xml": ('<Field Type="Note" Name="BodyPlainText" StaticName="BodyPlainText"'
                ' DisplayName="BodyPlainText" Required="FALSE" NumLines="10"'
                ' RichText="FALSE" AppendOnly="FALSE" />'),
    },
]

# 既定ビューの並び順（指示§11）。第2キーに ID 降順を入れて同時刻の順序を安定させる。
VIEW_QUERY = ("<OrderBy><FieldRef Name='ReceivedDateTime' Ascending='FALSE' />"
              "<FieldRef Name='ID' Ascending='FALSE' /></OrderBy>")


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
            "inputs": {"parameters": params, "host": dict(HOST_SPO), "authentication": AUTH},
            "runAfter": runafter or {}}


def oac(host, params, runafter=None):
    """SharePoint 以外のコネクタアクション（Outlook / Content Conversion）"""
    return {"type": "OpenApiConnection",
            "inputs": {"parameters": params, "host": dict(host), "authentication": AUTH},
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


def incr(name, runafter=None):
    return {"type": "IncrementVariable", "inputs": {"name": name, "value": 1},
            "runAfter": runafter or {}}


def query(from_expr, where_expr, runafter=None):
    return {"type": "Query", "inputs": {"from": from_expr, "where": where_expr},
            "runAfter": runafter or {}}


def foreach(items_expr, actions, runafter=None):
    """Apply to each（変数を更新するため並列は必ずオフ）"""
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


def scope(inner, runafter=None):
    return {"type": "Scope", "actions": inner, "runAfter": runafter or {}}


# --- URI ビルダー: 対象は常にリストID。リスト名では特定しない（GetByTitle( を使わない） ---
def list_uri(suffix=""):
    return "@concat('_api/web/lists(guid''', variables('varListId'), ''')" + suffix + "')"


def view_uri(suffix=""):
    return ("@concat('_api/web/lists(guid''', variables('varListId'),"
            " ''')/views(guid''', variables('varDefaultViewId'), ''')" + suffix + "')")


def field_uri(internal_name, suffix=""):
    return ("@concat('_api/web/lists(guid''', variables('varListId'),"
            " ''')/fields/getbyinternalnameortitle(''" + internal_name + "'')" + suffix + "')")


# 【重要】$expand したナビゲーションプロパティは $select にも投影を書く（`RootFolder/ServerRelativeUrl`）。
# 投影を省くと SharePoint は全リスト（カタログ等のシステムリストを含む）の RootFolder 全体を
# 実体化しようとし、アクセス権の無いリストで 403 Access denied になる。
# この形は create_initialized_sharepoint_list が 2026-07-24 に実環境で成功した形式と同一。
LISTS_SELECT = ("_api/web/lists?$select=Id,Title,Hidden,BaseTemplate,RootFolder/ServerRelativeUrl"
                "&$expand=RootFolder&$top=5000")
FIELDS_SELECT = "/fields?$select=Id,Title,InternalName,TypeAsString&$top=5000"

# メッセージIDの $filter（指示§15）。
#   1. replace(x, '''', '''''') …… シングルクォートを2重化して OData のリテラル境界を守る
#   2. uriComponent(...)        …… & < > # 空白 日本語 絵文字 を安全にエンコードする
#      （サーバ側で %27%27 が '' に復号され、エスケープ済みクォートとして解釈される）
SEARCH_ITEM_URI = (
    "@concat('_api/web/lists(guid''', variables('varListId'),"
    " ''')/items?$select=Id&$top=2&$filter=MessageId eq ''',"
    " uriComponent(replace(outputs('Compose_Message_Id'), '''', '''''')), '''')")

UPDATE_ITEM_URI = ("@concat('_api/web/lists(guid''', variables('varListId'),"
                   " ''')/items(', outputs('Compose_Existing_Item_Id'), ')')")

RETRY_UPDATE_ITEM_URI = ("@concat('_api/web/lists(guid''', variables('varListId'),"
                         " ''')/items(', outputs('Compose_Retry_Item_Id'), ')')")


# =========================================================================
# トップレベル変数初期化
# InitializeVariable は Scope 内に置けない（handbook/rules/01）。
# =========================================================================
INIT_SEQ = [
    # --- 入力 ---
    ("Initialize_InputSharePointUrl", "varInputSharePointUrl", "string",
     "@trim(coalesce(triggerBody()?['SharePointUrl'], ''))"),
    ("Initialize_ListName", "varListName", "string",
     "@trim(coalesce(triggerBody()?['ListName'], ''))"),
    ("Initialize_Mailbox", "varMailbox", "string",
     "@trim(coalesce(triggerBody()?['SharedMailboxAddress'], ''))"),
    # 件数は int() を直接使わない。int('abc') は実行時エラーになり、if() は両分岐を
    # 先行評価するため「条件で守る」ことができない。まず文字列で受けて数字だけか検査する。
    ("Initialize_RawCount", "varRawCount", "string",
     "@trim(string(coalesce(triggerBody()?['MailCount'], 0)))"),
    ("Initialize_RequestedCount", "varRequestedCount", "integer", 0),
    # --- 検証・制御 ---
    ("Initialize_IsValid", "varIsValid", "boolean", True),
    ("Initialize_Stage", "varStage", "string", "Initialize"),
    ("Initialize_ErrorCode", "varErrorCode", "string", ""),
    ("Initialize_ErrorMessage", "varErrorMessage", "string", ""),
    ("Initialize_ErrorMessages", "varErrorMessages", "array", []),
    ("Initialize_LastStatusCode", "varLastStatusCode", "string", "0"),
    # 失敗したコネクタ応答の本文を退避する（ハンドラは変数だけを読むため）。
    # take() は対象が短くてもエラーにならない（substring と違い範囲外にならない）。
    ("Initialize_LastErrorBody", "varLastErrorBody", "string", ""),
    # --- サイト・リスト ---
    ("Initialize_SiteUrl", "varSiteUrl", "string", ""),
    ("Initialize_SiteOrigin", "varSiteOrigin", "string", ""),
    ("Initialize_SiteId", "varSiteId", "string", ""),
    ("Initialize_ListExists", "varListExists", "boolean", False),
    ("Initialize_ListId", "varListId", "string", ""),
    ("Initialize_ListEntityType", "varListEntityType", "string", ""),
    ("Initialize_ListServerRelativeUrl", "varListServerRelativeUrl", "string", ""),
    ("Initialize_ListUrl", "varListUrl", "string", ""),
    ("Initialize_CreatedInThisRun", "varCreatedInThisRun", "boolean", False),
    ("Initialize_DefaultViewId", "varDefaultViewId", "string", ""),
    ("Initialize_SchemaOk", "varSchemaOk", "boolean", False),
    ("Initialize_MissingFields", "varMissingFields", "array", []),
    ("Initialize_IncompatibleFields", "varIncompatibleFields", "array", []),
    ("Initialize_SchemaWarnings", "varSchemaWarnings", "array", []),
    # --- メール同期 ---
    ("Initialize_FetchedCount", "varFetchedCount", "integer", 0),
    ("Initialize_CreatedCount", "varCreatedCount", "integer", 0),
    ("Initialize_UpdatedCount", "varUpdatedCount", "integer", 0),
    ("Initialize_DuplicateCount", "varDuplicateCount", "integer", 0),
    ("Initialize_FailedCount", "varFailedCount", "integer", 0),
    ("Initialize_TruncatedCount", "varTruncatedCount", "integer", 0),
    ("Initialize_Duplicates", "varDuplicates", "array", []),
    ("Initialize_ItemErrors", "varItemErrors", "array", []),
    ("Initialize_TruncatedItems", "varTruncatedItems", "array", []),
    # --- ループ内の作業変数（各反復の先頭でリセットする。自己参照はしない） ---
    ("Initialize_ItemBodyText", "varItemBodyText", "string", ""),
    ("Initialize_ItemBodyFinal", "varItemBodyFinal", "string", ""),
    ("Initialize_ItemError", "varItemError", "string", ""),
    ("Initialize_ItemCreateFailed", "varItemCreateFailed", "boolean", False),
    # --- 結果 ---
    ("Initialize_Status", "varStatus", "string", "Error"),
    ("Initialize_ResultObject", "varResultObject", "object", "@json('{}')"),
    ("Initialize_ResultJson", "varResultJson", "string", ""),
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
# Scope_Validate_Input : 入力検証とサイトURLの正規化（指示§4・§5）
# =========================================================================
U_FRAG = "outputs('Compose_Url_No_Fragment')"
U_QUERY = "outputs('Compose_Url_No_Query')"
U_LAYOUT = "outputs('Compose_Url_Before_Layouts')"
P_SITE = "outputs('Compose_Site_Url')"

# SharePointのリスト名で使用できない文字（順に replace で除去して長さ比較する）。
# 制御文字はタブ・CR・LF のみ検出できる（他の制御文字は式で検出できない＝docs に明記）。
FORBIDDEN_CHARS = ['"', "#", "%", "*", ":", "<", ">", "?", "/", "\\", "|", "{", "}", "~", "&"]
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


def _digits_removed_expr():
    """数字を全て除去する式。結果が空なら「数字だけの文字列」＝int() を安全に適用できる"""
    expr = "variables('varRawCount')"
    for d in "0123456789":
        expr = "replace(" + expr + ", '" + d + "', '')"
    return "@" + expr


RESERVED_NAMES = ["con", "prn", "aux", "nul", "forms", "_catalogs", "_private",
                  "_vti_bin", "_vti_pvt", "_vti_cnf", "app packages", "appdata"]
RESERVED_ARRAY = "createArray(" + ", ".join("'" + n + "'" for n in RESERVED_NAMES) + ")"

# サイトURLの正規化。固定文字数では切らない。
#   substring(concat(U, '#'), 0, length(first(split(toLower(U), '/_layouts/'))))
#   '/_layouts/' が無いとき length は U 全体の長さになり U がそのまま返る。
#   大文字小文字の表記ゆれ（/_Layouts/ 等）にも依存しない。
#
# 【重要】末尾の '#' は番兵。substring の開始位置は「0以上 **かつ文字列長より小さい**」
# ことが要求されるため、U が空文字だと substring(U, 0, 0) でも実行時に落ちる。
#   The template language function 'substring' parameter is out of range:
#   'start index' must be non-negative integer and should be less than the length of the string.
# （2026-08-04 に teams-channel-member-sync の同型コードで実発生。
#   handbook/knowledge/error_catalog.md の「substring と空文字」の節を参照）
# 番兵は length 引数で切り落とされるため結果には現れない。
URL_BEFORE_LAYOUTS = ("@substring(concat(" + U_QUERY + ", '#'), 0,"
                      " length(first(split(toLower(" + U_QUERY + "), '/_layouts/'))))")

# 末尾スラッシュ除去。if() は両分岐を先行評価するため substring の長さ計算を使わない
# （空文字入力で sub(length,1) が -1 になり実行時エラーになりうる）。
SITE_URL_EXPR = ("@if(endsWith(" + U_LAYOUT + ", '/'),"
                 " join(take(split(" + U_LAYOUT + ", '/'),"
                 " sub(length(split(" + U_LAYOUT + ", '/')), 1)), '/'),"
                 " " + U_LAYOUT + ")")

SITE_ORIGIN_EXPR = ("@if(greaterOrEquals(length(split(" + P_SITE + ", '/')), 3),"
                    " join(take(split(" + P_SITE + ", '/'), 3), '/'), '')")

SITE_HOST_EXPR = "@first(split(last(split(" + P_SITE + ", '//')), '/'))"

VALIDATE_SITE_URL = (
    "@if(empty(variables('varInputSharePointUrl')), 'ERR_URL_EMPTY',"
    " if(not(startsWith(" + P_SITE + ", 'https://')), 'ERR_URL_NOT_HTTPS',"
    " if(not(endsWith(outputs('Compose_Site_Host'), '.sharepoint.com')), 'ERR_URL_NOT_SHAREPOINT',"
    " if(contains(outputs('Compose_Site_Host'), '@'), 'ERR_URL_MALFORMED',"
    " if(empty(outputs('Compose_Site_Origin')), 'ERR_URL_MALFORMED',"
    " if(empty(" + P_SITE + "), 'ERR_URL_MALFORMED',"
    " ''))))))")

VALIDATE_LIST_NAME = (
    "@if(empty(variables('varListName')), 'ERR_LISTNAME_EMPTY',"
    " if(greater(length(variables('varListName')), 255), 'ERR_LISTNAME_TOO_LONG',"
    " if(not(equals(length(variables('varListName')),"
    " length(outputs('Compose_ListName_Sanitized')))), 'ERR_LISTNAME_INVALID_CHARS',"
    " if(startsWith(variables('varListName'), '.'), 'ERR_LISTNAME_INVALID_PERIOD',"
    " if(endsWith(variables('varListName'), '.'), 'ERR_LISTNAME_INVALID_PERIOD',"
    " if(contains(" + RESERVED_ARRAY + ", toLower(variables('varListName'))), 'ERR_LISTNAME_RESERVED',"
    " ''))))))")

MB = "variables('varMailbox')"
VALIDATE_MAILBOX = (
    "@if(empty(" + MB + "), 'ERR_MAILBOX_EMPTY',"
    " if(not(equals(length(split(" + MB + ", '@')), 2)), 'ERR_MAILBOX_INVALID',"
    " if(empty(first(split(" + MB + ", '@'))), 'ERR_MAILBOX_INVALID',"
    " if(not(contains(last(split(" + MB + ", '@')), '.')), 'ERR_MAILBOX_INVALID',"
    " if(startsWith(last(split(" + MB + ", '@')), '.'), 'ERR_MAILBOX_INVALID',"
    " if(endsWith(last(split(" + MB + ", '@')), '.'), 'ERR_MAILBOX_INVALID',"
    " ''))))))")

# 数字だけ・9桁以内であることを確認したうえでのみ int() へ渡す（オーバーフローと型エラーの回避）
COUNT_SAFE_EXPR = (
    "@if(and(and(not(empty(variables('varRawCount'))),"
    " empty(outputs('Compose_Count_Digits_Removed'))),"
    " lessOrEquals(length(variables('varRawCount')), 9)), variables('varRawCount'), '0')")

VALIDATE_COUNT = (
    "@if(empty(variables('varRawCount')), 'ERR_COUNT_INVALID',"
    " if(not(empty(outputs('Compose_Count_Digits_Removed'))), 'ERR_COUNT_INVALID',"
    " if(greater(length(variables('varRawCount')), 9), 'ERR_COUNT_TOO_LARGE',"
    " if(lessOrEquals(outputs('Compose_Count_Numeric'), 0), 'ERR_COUNT_INVALID',"
    " if(greater(outputs('Compose_Count_Numeric'), " + str(MAX_MAIL_COUNT) + "), 'ERR_COUNT_TOO_LARGE',"
    " '')))))")

ERROR_MESSAGE_MAP = (
    "@if(equals(variables('varErrorCode'), 'ERR_URL_EMPTY'),"
    " 'SharePointのURLが入力されていません。',"
    " if(equals(variables('varErrorCode'), 'ERR_URL_NOT_HTTPS'),"
    " 'URLが https:// で始まっていません。',"
    " if(equals(variables('varErrorCode'), 'ERR_URL_NOT_SHAREPOINT'),"
    " 'SharePointのURLではありません（ホスト名が .sharepoint.com で終わっていません）。',"
    " if(equals(variables('varErrorCode'), 'ERR_URL_MALFORMED'),"
    " 'URLの形式が正しくありません。サイトURLを抽出できませんでした。',"
    " if(equals(variables('varErrorCode'), 'ERR_LISTNAME_EMPTY'),"
    " 'リスト名が入力されていません（前後の空白を除くと空になります）。',"
    " if(equals(variables('varErrorCode'), 'ERR_LISTNAME_TOO_LONG'),"
    " 'リスト名が長すぎます（255文字以内にしてください）。',"
    " if(equals(variables('varErrorCode'), 'ERR_LISTNAME_INVALID_CHARS'),"
    " 'リスト名にSharePointで使用できない文字または制御文字が含まれています。',"
    " if(equals(variables('varErrorCode'), 'ERR_LISTNAME_INVALID_PERIOD'),"
    " 'リスト名の先頭または末尾にピリオドは使用できません。',"
    " if(equals(variables('varErrorCode'), 'ERR_LISTNAME_RESERVED'),"
    " 'リスト名がSharePointの予約名に該当します。',"
    " if(equals(variables('varErrorCode'), 'ERR_MAILBOX_EMPTY'),"
    " '共有メールボックスのアドレスが入力されていません。',"
    " if(equals(variables('varErrorCode'), 'ERR_MAILBOX_INVALID'),"
    " '共有メールボックスのアドレスがメールアドレスの形式ではありません。',"
    " if(equals(variables('varErrorCode'), 'ERR_COUNT_INVALID'),"
    " '取得件数は1以上の整数で指定してください（0・負数・小数・数値以外は指定できません）。',"
    " if(equals(variables('varErrorCode'), 'ERR_COUNT_TOO_LARGE'),"
    " '取得件数が上限（" + str(MAX_MAIL_COUNT) + "件）を超えています。件数を減らして再実行してください。',"
    " '')))))))))))))")

validate_seq = [
    ("Set_Stage_Validate_Input", setvar("varStage", "ValidateInput")),
    ("Compose_Url_No_Fragment",
     compose("@first(split(variables('varInputSharePointUrl'), '#'))")),
    ("Compose_Url_No_Query", compose("@first(split(" + U_FRAG + ", '?'))")),
    ("Compose_Url_Before_Layouts", compose(URL_BEFORE_LAYOUTS)),
    ("Compose_Site_Url", compose(SITE_URL_EXPR)),
    ("Compose_Site_Host", compose(SITE_HOST_EXPR)),
    ("Compose_Site_Origin", compose(SITE_ORIGIN_EXPR)),
    ("Compose_ListName_Sanitized", compose(_sanitize_expr())),
    ("Compose_Count_Digits_Removed", compose(_digits_removed_expr())),
    ("Compose_Count_Safe", compose(COUNT_SAFE_EXPR)),
    ("Compose_Count_Numeric", compose("@int(outputs('Compose_Count_Safe'))")),
    ("Validate_SiteUrl", compose(VALIDATE_SITE_URL)),
    ("Validate_ListName", compose(VALIDATE_LIST_NAME)),
    ("Validate_Mailbox", compose(VALIDATE_MAILBOX)),
    ("Validate_Count", compose(VALIDATE_COUNT)),
    ("Compose_Input_Validation_Code",
     compose("@if(not(empty(outputs('Validate_SiteUrl'))), outputs('Validate_SiteUrl'),"
             " if(not(empty(outputs('Validate_ListName'))), outputs('Validate_ListName'),"
             " if(not(empty(outputs('Validate_Mailbox'))), outputs('Validate_Mailbox'),"
             " outputs('Validate_Count'))))")),
    ("Set_SiteUrl", setvar("varSiteUrl", "@outputs('Compose_Site_Url')")),
    ("Set_SiteOrigin", setvar("varSiteOrigin", "@outputs('Compose_Site_Origin')")),
    ("Set_RequestedCount", setvar("varRequestedCount", "@outputs('Compose_Count_Numeric')")),
    ("Set_ErrorCode_From_Input_Validation",
     setvar("varErrorCode", "@outputs('Compose_Input_Validation_Code')")),
    ("Set_IsValid_From_Input_Validation",
     setvar("varIsValid", "@empty(outputs('Compose_Input_Validation_Code'))")),
    ("Set_ErrorMessage_From_Input_Validation", setvar("varErrorMessage", ERROR_MESSAGE_MAP)),
]
validate_actions, validate_last = chain(validate_seq)
validate_actions["Condition_Has_Input_Error"] = cond(
    {"and": [eq("@variables('varIsValid')", False)]},
    {"Append_Input_Error_Message": append(
        "varErrorMessages",
        "@concat(variables('varErrorCode'), ': ', variables('varErrorMessage'))")},
    runafter=ra(validate_last))
actions["Scope_Validate_Input"] = scope(validate_actions, ra(LAST_INIT))


# =========================================================================
# Scope_Check_List : サイト疎通と同名リストの完全一致判定（指示§6）
# =========================================================================
MATCHED = "body('Filter_Matching_Lists')"
FIRST_MATCH = "first(body('Filter_Matching_Lists'))"

check_found_inner, _ = chain([
    ("Set_ListExists_True", setvar("varListExists", True)),
    ("Set_ListId_From_Existing",
     setvar("varListId", "@trim(string(coalesce(" + FIRST_MATCH + "?['Id'], '')))")),
    ("Set_List_ServerRelativeUrl_From_Existing",
     setvar("varListServerRelativeUrl",
            "@trim(string(coalesce(" + FIRST_MATCH + "?['RootFolder']?['ServerRelativeUrl'], '')))")),
])

check_not_generic_inner, _ = chain([
    ("Set_ErrorCode_Not_Generic", setvar("varErrorCode", "ERR_LIST_NOT_GENERIC")),
    ("Set_ErrorMessage_Not_Generic", setvar(
        "varErrorMessage",
        "同名のリストは非表示リストまたはシステムリストです。別のリスト名を指定してください。")),
    ("Set_IsValid_Not_Generic", setvar("varIsValid", False)),
    ("Append_Not_Generic_Error", append(
        "varErrorMessages", "ERR_LIST_NOT_GENERIC: 同名の非表示／システムリストが存在します。")),
])

check_ambiguous_inner, _ = chain([
    ("Set_ErrorCode_Ambiguous", setvar("varErrorCode", "ERR_LIST_AMBIGUOUS")),
    ("Set_ErrorMessage_Ambiguous", setvar(
        "varErrorMessage", "同名のリストが複数見つかりました。安全のため処理を中止しました。")),
    ("Set_IsValid_Ambiguous", setvar("varIsValid", False)),
    ("Append_Ambiguous_Error", append(
        "varErrorMessages", "ERR_LIST_AMBIGUOUS: 同名リストが複数存在します。")),
])

check_inner = {}
check_inner["Verify_SharePoint_Web"] = http("GET", "_api/web?$select=Id,Title,Url", H_NOMETA)
check_inner["Set_Site_Status_Code"] = setvar(
    "varLastStatusCode", "@string(coalesce(outputs('Verify_SharePoint_Web')?['statusCode'], 0))",
    {"Verify_SharePoint_Web": ["Succeeded", "Failed"]})
check_inner["Store_Site_Id"] = setvar(
    "varSiteId", "@trim(string(coalesce(body('Verify_SharePoint_Web')?['Id'], '')))",
    ra("Verify_SharePoint_Web"))
check_inner["Get_All_Lists"] = http("GET", LISTS_SELECT, H_NOMETA, runafter=ra("Store_Site_Id"))
check_inner["Set_Lists_Status_Code"] = setvar(
    "varLastStatusCode", "@string(coalesce(outputs('Get_All_Lists')?['statusCode'], 0))",
    {"Get_All_Lists": ["Succeeded", "Failed"]})
check_inner["Set_Lists_Error_Body"] = setvar(
    "varLastErrorBody", "@take(string(coalesce(body('Get_All_Lists'), '')), 2000)",
    {"Get_All_Lists": ["Failed", "TimedOut"]})
# 正規化後の完全一致（contains は使わない＝部分一致誤検出の排除）。非表示リストも対象に含める。
check_inner["Filter_Matching_Lists"] = query(
    "@coalesce(body('Get_All_Lists')?['value'], json('[]'))",
    "@equals(toLower(trim(coalesce(item()?['Title'], ''))), toLower(variables('varListName')))",
    ra("Get_All_Lists"))
check_inner["Condition_Lists_Ambiguous"] = cond(
    {"and": [{"greater": ["@length(" + MATCHED + ")", 1]}]},
    check_ambiguous_inner, runafter=ra("Filter_Matching_Lists"))
check_inner["Condition_List_Single_Match"] = cond(
    {"and": [eq("@length(" + MATCHED + ")", 1)]},
    {"Condition_List_Is_Generic": cond(
        {"and": [eq("@coalesce(" + FIRST_MATCH + "?['Hidden'], false)", False),
                 eq("@coalesce(" + FIRST_MATCH + "?['BaseTemplate'], 0)", 100)]},
        check_found_inner, check_not_generic_inner)},
    runafter=ra("Condition_Lists_Ambiguous"))

check_scope_actions = {}
check_scope_actions["Set_Stage_Check_List"] = setvar("varStage", "CheckList")
check_scope_actions["Condition_Input_Is_Valid"] = cond(
    {"and": [eq("@variables('varIsValid')", True)]},
    check_inner, runafter=ra("Set_Stage_Check_List"))
actions["Scope_Check_List"] = scope(check_scope_actions, ra("Scope_Validate_Input"))


# =========================================================================
# Scope_Create_List : 同名リストが無いときだけ作成する（指示§7）
# 既存リストの削除・上書き・改名は一切行わない。
# =========================================================================
CREATE_LIST_BODY = {
    "__metadata": {"type": "SP.List"},
    "AllowContentTypes": False,
    "BaseTemplate": 100,
    "ContentTypesEnabled": False,
    "Description": "Power Automateにより作成されたメール同期用リスト",
    "Title": "@variables('varListName')",
}
RECHECK_MATCH = "body('Filter_Recheck_Lists')"
FIRST_RECHECK = "first(body('Filter_Recheck_Lists'))"
RETRY_MATCH = "body('Filter_Retry_Lists')"
FIRST_RETRY = "first(body('Filter_Retry_Lists'))"

# 競合で他の実行が先に作成していた場合は、そのリストを既存として扱う（削除も上書きもしない）
race_inner, _ = chain([
    ("Set_ListExists_Race", setvar("varListExists", True)),
    ("Set_ListId_Race",
     setvar("varListId", "@trim(string(coalesce(" + FIRST_RECHECK + "?['Id'], '')))")),
    ("Set_List_ServerRelativeUrl_Race",
     setvar("varListServerRelativeUrl",
            "@trim(string(coalesce(" + FIRST_RECHECK + "?['RootFolder']?['ServerRelativeUrl'], '')))")),
    ("Append_Race_Warning", append(
        "varSchemaWarnings", "同時実行により別の実行がリストを作成済みでした。既存リストとして処理します。")),
])

create_ok_inner, _ = chain([
    ("Set_ListId_From_Create",
     setvar("varListId", "@trim(string(coalesce(body('Create_List')?['d']?['Id'], '')))")),
    ("Set_CreatedInThisRun", setvar("varCreatedInThisRun", True)),
    ("Set_ListExists_After_Create", setvar("varListExists", True)),
])

create_failed_race_inner, _ = chain([
    ("Set_ListExists_After_Failure", setvar("varListExists", True)),
    ("Set_ListId_After_Failure",
     setvar("varListId", "@trim(string(coalesce(" + FIRST_RETRY + "?['Id'], '')))")),
    ("Set_List_ServerRelativeUrl_After_Failure",
     setvar("varListServerRelativeUrl",
            "@trim(string(coalesce(" + FIRST_RETRY + "?['RootFolder']?['ServerRelativeUrl'], '')))")),
    ("Append_Create_Race_Warning", append(
        "varSchemaWarnings", "作成は失敗しましたが同名リストが存在したため、既存リストとして処理します。")),
])

create_failed_hard_inner, _ = chain([
    ("Set_ErrorCode_Create_Failed", setvar("varErrorCode", "ERR_LIST_CREATE_FAILED")),
    ("Set_ErrorMessage_Create_Failed", setvar(
        "varErrorMessage",
        "リストの作成に失敗しました。サイトへの権限とリスト名を確認してください。")),
    ("Set_IsValid_Create_Failed", setvar("varIsValid", False)),
    ("Append_Create_Failed_Error", append(
        "varErrorMessages",
        "@concat('ERR_LIST_CREATE_FAILED: httpStatusCode=', variables('varLastStatusCode'))")),
])

create_do_inner = {}
create_do_inner["Compose_Create_List_Body"] = compose(CREATE_LIST_BODY)
create_do_inner["Create_List"] = http(
    "POST", "_api/web/lists", H_VERBOSE, "@string(outputs('Compose_Create_List_Body'))",
    ra("Compose_Create_List_Body"))
create_do_inner["Set_Create_Status_Code"] = setvar(
    "varLastStatusCode", "@string(coalesce(outputs('Create_List')?['statusCode'], 0))",
    {"Create_List": ["Succeeded", "Failed"]})
create_do_inner["Set_Create_Error_Body"] = setvar(
    "varLastErrorBody", "@take(string(coalesce(body('Create_List'), '')), 2000)",
    {"Create_List": ["Failed", "TimedOut"]})
create_do_inner["Retry_Get_Lists_After_Failure"] = http(
    "GET", LISTS_SELECT, H_NOMETA, runafter={"Create_List": ["Failed", "TimedOut"]})
create_do_inner["Filter_Retry_Lists"] = query(
    "@coalesce(body('Retry_Get_Lists_After_Failure')?['value'], json('[]'))",
    "@equals(toLower(trim(coalesce(item()?['Title'], ''))), toLower(variables('varListName')))",
    ra("Retry_Get_Lists_After_Failure"))
create_do_inner["Condition_Create_Failed_But_Exists"] = cond(
    {"and": [{"greater": ["@length(" + RETRY_MATCH + ")", 0]}]},
    create_failed_race_inner, create_failed_hard_inner, ra("Filter_Retry_Lists"))
create_do_inner["Condition_Create_Succeeded"] = cond(
    {"and": [{"greaterOrEquals": ["@int(variables('varLastStatusCode'))", 200]},
             {"lessOrEquals": ["@int(variables('varLastStatusCode'))", 299]}]},
    create_ok_inner, runafter={"Create_List": ["Succeeded"]})

create_inner = {}
create_inner["Recheck_Lists_Before_Create"] = http("GET", LISTS_SELECT, H_NOMETA)
create_inner["Filter_Recheck_Lists"] = query(
    "@coalesce(body('Recheck_Lists_Before_Create')?['value'], json('[]'))",
    "@equals(toLower(trim(coalesce(item()?['Title'], ''))), toLower(variables('varListName')))",
    ra("Recheck_Lists_Before_Create"))
create_inner["Condition_Recheck_Found"] = cond(
    {"and": [{"greater": ["@length(" + RECHECK_MATCH + ")", 0]}]},
    race_inner, create_do_inner, ra("Filter_Recheck_Lists"))

create_scope_actions = {}
create_scope_actions["Set_Stage_Create_List"] = setvar("varStage", "CreateList")
create_scope_actions["Condition_Should_Create_List"] = cond(
    {"and": [eq("@variables('varIsValid')", True), eq("@variables('varListExists')", False)]},
    create_inner, runafter=ra("Set_Stage_Create_List"))
actions["Scope_Create_List"] = scope(create_scope_actions, ra("Scope_Check_List"))


# =========================================================================
# Scope_Init_List_Schema : 今回作成したリストにだけ列を作る（指示§9・§10）
# varCreatedInThisRun == true のガード配下。既存リストの列は絶対に触らない。
# =========================================================================
init_field_seq = [("Get_Fields_Before_Init", http("GET", list_uri(FIELDS_SELECT), H_NOMETA))]

for f in FIELDS:
    n = f["internal"]
    body_obj = {"parameters": {"__metadata": {"type": "SP.XmlSchemaFieldCreationInformation"},
                               "Options": 0, "SchemaXml": f["xml"]}}
    create_field_inner, _ = chain([
        ("Compose_Field_Body_" + n, compose(body_obj)),
        ("Create_Field_" + n, http("POST", list_uri("/fields/createFieldAsXml"), H_VERBOSE,
                                   "@string(outputs('Compose_Field_Body_" + n + "'))")),
    ])
    init_field_seq += [
        ("Filter_Existing_Field_" + n, query(
            "@coalesce(body('Get_Fields_Before_Init')?['value'], json('[]'))",
            "@equals(coalesce(item()?['InternalName'], ''), '" + n + "')")),
        ("Condition_Create_Field_" + n, cond(
            {"and": [eq("@length(body('Filter_Existing_Field_" + n + "'))", 0)]},
            create_field_inner)),
    ]

# 表示名だけを日本語へ変更する（内部名は変わらないため後続の $filter / 参照は壊れない）
for f in FIELDS:
    n = f["internal"]
    init_field_seq += [
        ("Compose_Rename_Body_" + n, compose({"Title": f["display"]})),
        ("Rename_Field_" + n, http("POST", field_uri(n), H_MERGE_N,
                                   "@string(outputs('Compose_Rename_Body_" + n + "'))")),
    ]

# Title 列は削除せず、必須解除だけ行う（件名は Subject 列に保存する）
init_field_seq += [
    ("Compose_Title_Not_Required_Body", compose({"Required": False})),
    ("Deactivate_Title_Required", http("POST", field_uri("Title"), H_MERGE_N,
                                       "@string(outputs('Compose_Title_Not_Required_Body'))")),
    # 一意制約が実際に反映されたかを確認し、反映されていなければ警告として結果に残す
    ("Verify_MessageId_Field", http(
        "GET", field_uri("MessageId",
                         "?$select=InternalName,TypeAsString,Indexed,EnforceUniqueValues"),
        H_NOMETA)),
]
init_field_actions, init_field_last = chain(init_field_seq)
init_field_actions["Condition_Unique_Not_Enforced"] = cond(
    {"and": [eq("@coalesce(body('Verify_MessageId_Field')?['EnforceUniqueValues'], false)", False)]},
    {"Append_Unique_Warning": append(
        "varSchemaWarnings",
        "MessageId 列に一意制約が適用されませんでした。重複登録の防止はフロー側の検索のみに依存します。")},
    runafter=ra(init_field_last))

init_scope_actions = {}
init_scope_actions["Set_Stage_Init_Schema"] = setvar("varStage", "InitListSchema")
init_scope_actions["Condition_Created_In_This_Run"] = cond(
    {"and": [eq("@variables('varCreatedInThisRun')", True), eq("@variables('varIsValid')", True)]},
    init_field_actions, runafter=ra("Set_Stage_Init_Schema"))
actions["Scope_Init_List_Schema"] = scope(init_scope_actions, ra("Scope_Create_List"))


# =========================================================================
# Scope_Configure_View : 既定ビューの列と並び順（指示§11）
# varCreatedInThisRun == true のガード配下。既存リストのビューは絶対に触らない。
# =========================================================================
view_seq = [
    ("Set_Default_View_Id", setvar(
        "varDefaultViewId",
        "@trim(string(coalesce(first(body('Filter_Default_View'))?['Id'], '')))")),
    ("Remove_All_Default_View_Fields",
     http("POST", view_uri("/viewfields/removeAllViewFields()"), H_NOMETA)),
    ("Compose_Add_View_Field_Body", compose({"__metadata": {"type": "SP.View"},
                                             "SetAsDefaultView": True})),
]
for f in FIELDS:
    n = f["internal"]
    view_seq.append(
        ("Add_View_Field_" + n,
         http("POST", view_uri("/viewfields/AddViewField(''" + n + "'')"), H_MERGE_V,
              "@string(outputs('Compose_Add_View_Field_Body'))")))
view_seq += [
    ("Compose_View_Query_Body", compose({"__metadata": {"type": "SP.View"},
                                         "ViewQuery": VIEW_QUERY})),
    ("Set_Default_View_Sort", http("POST", view_uri(), H_MERGE_V,
                                   "@string(outputs('Compose_View_Query_Body'))")),
    ("Verify_Default_View_Fields", http("GET", view_uri("/ViewFields"), H_NOMETA)),
]
view_ok_inner, _ = chain(view_seq)

view_ng_inner, _ = chain([
    ("Append_View_Warning", append(
        "varSchemaWarnings", "既定ビューが特定できなかったため、ビューの列と並び順を設定できませんでした。")),
])

view_inner = {}
view_inner["Get_List_Views"] = http(
    "GET", list_uri("/views?$select=Id,Title,DefaultView&$top=100"), H_NOMETA)
view_inner["Filter_Default_View"] = query(
    "@coalesce(body('Get_List_Views')?['value'], json('[]'))",
    "@equals(coalesce(item()?['DefaultView'], false), true)",
    ra("Get_List_Views"))
view_inner["Condition_Default_View_Found"] = cond(
    {"and": [{"greater": ["@length(body('Filter_Default_View'))", 0]}]},
    view_ok_inner, view_ng_inner, ra("Filter_Default_View"))

view_scope_actions = {}
view_scope_actions["Set_Stage_Configure_View"] = setvar("varStage", "ConfigureView")
view_scope_actions["Condition_Configure_View_Allowed"] = cond(
    {"and": [eq("@variables('varCreatedInThisRun')", True), eq("@variables('varIsValid')", True)]},
    view_inner, runafter=ra("Set_Stage_Configure_View"))
actions["Scope_Configure_View"] = scope(view_scope_actions, ra("Scope_Init_List_Schema"))


# =========================================================================
# Scope_Verify_Schema : 必要な列が揃っているかの確認（指示§8）
# 既存リストでも新規作成リストでも通す最後の関門。列は一切変更しない。
# =========================================================================
schema_seq = [
    ("Get_List_Info", http("GET", list_uri(
        "?$select=Id,Title,ListItemEntityTypeFullName,RootFolder/ServerRelativeUrl"
        "&$expand=RootFolder"), H_NOMETA)),
    ("Set_List_Status_Code", setvar(
        "varLastStatusCode", "@string(coalesce(outputs('Get_List_Info')?['statusCode'], 0))")),
    ("Set_List_Entity_Type", setvar(
        "varListEntityType",
        "@trim(string(coalesce(body('Get_List_Info')?['ListItemEntityTypeFullName'], '')))")),
    # SetVariable の値式で varListServerRelativeUrl 自身を参照すると保存時に
    # 自己参照エラーになるため、フォールバックの合成は Compose に切り出す。
    ("Compose_List_ServerRelativeUrl", compose(
        "@trim(string(coalesce(body('Get_List_Info')?['RootFolder']?['ServerRelativeUrl'],"
        " variables('varListServerRelativeUrl'))))")),
    ("Set_List_ServerRelativeUrl_Final", setvar(
        "varListServerRelativeUrl", "@outputs('Compose_List_ServerRelativeUrl')")),
    ("Set_List_Url", setvar(
        "varListUrl",
        "@concat(variables('varSiteOrigin'), variables('varListServerRelativeUrl'))")),
    ("Get_List_Fields_For_Schema", http("GET", list_uri(FIELDS_SELECT), H_NOMETA)),
]
for f in FIELDS:
    n, t = f["internal"], f["type"]
    schema_seq += [
        ("Filter_Schema_Field_" + n, query(
            "@coalesce(body('Get_List_Fields_For_Schema')?['value'], json('[]'))",
            "@equals(coalesce(item()?['InternalName'], ''), '" + n + "')")),
        ("Condition_Schema_Field_" + n, cond(
            {"and": [eq("@length(body('Filter_Schema_Field_" + n + "'))", 0)]},
            {"Append_Missing_Field_" + n: append("varMissingFields", n)},
            {"Condition_Schema_Type_" + n: cond(
                {"and": [{"not": eq(
                    "@coalesce(first(body('Filter_Schema_Field_" + n + "'))?['TypeAsString'], '')",
                    t)}]},
                {"Append_Incompatible_Field_" + n: append("varIncompatibleFields", {
                    "internalName": n, "expected": t,
                    "actual": "@coalesce(first(body('Filter_Schema_Field_" + n
                              + "'))?['TypeAsString'], '')"})})})),
    ]
schema_seq += [
    ("Set_SchemaOk", setvar(
        "varSchemaOk",
        "@and(equals(length(variables('varMissingFields')), 0),"
        " equals(length(variables('varIncompatibleFields')), 0))")),
]
schema_actions, schema_last = chain(schema_seq)
schema_actions["Condition_Schema_Incompatible"] = cond(
    {"and": [eq("@variables('varSchemaOk')", False)]},
    dict(chain([
        ("Set_ErrorCode_Schema", setvar("varErrorCode", "ERR_SCHEMA_INCOMPATIBLE")),
        ("Set_ErrorMessage_Schema", setvar(
            "varErrorMessage",
            "同名リストは存在しますが、必要な列が不足しているか型が互換ではありません。"
            "リストは変更していません。")),
        ("Set_IsValid_Schema", setvar("varIsValid", False)),
        ("Append_Schema_Error", append(
            "varErrorMessages",
            "@concat('ERR_SCHEMA_INCOMPATIBLE: missing=', string(variables('varMissingFields')),"
            " ' incompatible=', string(variables('varIncompatibleFields')))")),
    ])[0]),
    runafter=ra(schema_last))

schema_scope_actions = {}
schema_scope_actions["Set_Stage_Verify_Schema"] = setvar("varStage", "VerifySchema")
schema_scope_actions["Condition_Verify_Schema_Allowed"] = cond(
    {"and": [eq("@variables('varIsValid')", True), eq("@variables('varListExists')", True)]},
    schema_actions, runafter=ra("Set_Stage_Verify_Schema"))
actions["Scope_Verify_Schema"] = scope(schema_scope_actions, ra("Scope_Configure_View"))


# =========================================================================
# Scope_Get_Emails : 共有メールボックスからの取得（指示§12）
# 読み取りのみ。既読化・移動・削除・フラグ・送信のアクションは一切持たない。
# =========================================================================
# 取得アクションの出力順は公式に保証されていないため、受信日時で降順に並べ替えてから
# 上位N件を採用する（sort は昇順のみ。降順は reverse を併用する）。
SORTED_EMAILS = ("@take(reverse(sort(coalesce(body('Get_Emails')?['value'], json('[]')),"
                 " 'receivedDateTime')), variables('varRequestedCount'))")

emails_inner = {}
emails_inner["Get_Emails"] = oac(HOST_OL, {
    "mailboxAddress": "@variables('varMailbox')",
    "folderPath": "Inbox",
    "top": "@variables('varRequestedCount')",
    "fetchOnlyUnread": False,
    "includeAttachments": False,
})
emails_inner["Set_Emails_Status_Code"] = setvar(
    "varLastStatusCode", "@string(coalesce(outputs('Get_Emails')?['statusCode'], 0))",
    {"Get_Emails": ["Succeeded", "Failed"]})
emails_inner["Set_Emails_Error_Body"] = setvar(
    "varLastErrorBody", "@take(string(coalesce(body('Get_Emails'), '')), 2000)",
    {"Get_Emails": ["Failed", "TimedOut"]})
emails_inner["Compose_Sorted_Emails"] = compose(SORTED_EMAILS, ra("Get_Emails"))
emails_inner["Set_Fetched_Count"] = setvar(
    "varFetchedCount", "@length(outputs('Compose_Sorted_Emails'))", ra("Compose_Sorted_Emails"))

emails_scope_actions = {}
emails_scope_actions["Set_Stage_Get_Emails"] = setvar("varStage", "GetEmails")
emails_scope_actions["Condition_Get_Emails_Allowed"] = cond(
    {"and": [eq("@variables('varIsValid')", True), eq("@variables('varSchemaOk')", True)]},
    emails_inner, runafter=ra("Set_Stage_Get_Emails"))
actions["Scope_Get_Emails"] = scope(emails_scope_actions, ra("Scope_Verify_Schema"))


# =========================================================================
# Scope_Sync_Items : メール1件ずつの登録／更新（指示§14）
# =========================================================================
IT = "items('Foreach_Email')"
ITEM_VALUES = {
    "ReceivedDateTime": "@if(empty(outputs('Compose_Received')), null, outputs('Compose_Received'))",
    "SenderAddress": "@outputs('Compose_Sender')",
    "Subject": "@outputs('Compose_Subject')",
    "BodyPlainText": "@variables('varItemBodyFinal')",
}
CREATE_ITEM_BODY = dict(ITEM_VALUES)
CREATE_ITEM_BODY["__metadata"] = {"type": "@variables('varListEntityType')"}
CREATE_ITEM_BODY["MessageId"] = "@outputs('Compose_Message_Id')"
UPDATE_ITEM_BODY = dict(ITEM_VALUES)
UPDATE_ITEM_BODY["__metadata"] = {"type": "@variables('varListEntityType')"}

SEARCH_RESULT = "coalesce(body('Search_Existing_Item')?['value'], json('[]'))"
RETRY_SEARCH_RESULT = "coalesce(body('Research_After_Create_Failure')?['value'], json('[]'))"

# --- 本文の変換（HTML→プレーンテキスト） ---
convert_inner, _ = chain([
    ("Convert_Body_To_Text", oac(HOST_CC, {"Content": "@outputs('Compose_Body_Html')"})),
])
convert_inner["Set_Convert_Status_Code"] = setvar(
    "varLastStatusCode", "@string(coalesce(outputs('Convert_Body_To_Text')?['statusCode'], 0))",
    {"Convert_Body_To_Text": ["Succeeded", "Failed"]})
convert_inner["Set_Item_Body_Text"] = setvar(
    "varItemBodyText", "@string(coalesce(body('Convert_Body_To_Text'), ''))",
    {"Convert_Body_To_Text": ["Succeeded"]})
# 変換に失敗したらHTMLをそのまま登録せず、その1件だけを失敗として記録する
convert_inner["Set_Item_Error_Convert_Failed"] = setvar(
    "varItemError", "ERR_BODY_CONVERSION_FAILED",
    {"Convert_Body_To_Text": ["Failed", "TimedOut"]})

# --- 本文長の調整（黙って切り捨てず truncatedItems に記録する） ---
truncate_inner, _ = chain([
    ("Compose_Body_Truncated",
     compose("@substring(variables('varItemBodyText'), 0, " + str(MAX_BODY_LENGTH) + ")")),
    ("Set_Item_Body_Final_Truncated",
     setvar("varItemBodyFinal", "@outputs('Compose_Body_Truncated')")),
    ("Append_Truncated_Item", append("varTruncatedItems", {
        "messageId": "@outputs('Compose_Message_Id')",
        "originalLength": "@length(variables('varItemBodyText'))",
        "storedLength": str(MAX_BODY_LENGTH)})),
    ("Increment_Truncated_Count", incr("varTruncatedCount")),
])
no_truncate_inner, _ = chain([
    ("Set_Item_Body_Final_Full", setvar("varItemBodyFinal", "@variables('varItemBodyText')")),
])

# --- 重複異常（2件以上） ---
duplicate_inner, _ = chain([
    ("Append_Duplicate_Record", append("varDuplicates", {
        "messageId": "@outputs('Compose_Message_Id')",
        "count": "@length(" + SEARCH_RESULT + ")",
        "itemIds": "@" + SEARCH_RESULT})),
    ("Increment_Duplicate_Count", incr("varDuplicateCount")),
])

# --- 更新（1件） ---
update_inner, _ = chain([
    ("Compose_Existing_Item_Id",
     compose("@string(coalesce(first(" + SEARCH_RESULT + ")?['Id'], 0))")),
    ("Compose_Update_Item_Body", compose(UPDATE_ITEM_BODY)),
    ("Update_Existing_Item", http("POST", UPDATE_ITEM_URI, H_MERGE_V,
                                  "@string(outputs('Compose_Update_Item_Body'))")),
    ("Increment_Updated_Count", incr("varUpdatedCount")),
])
update_inner["Set_Update_Status_Code"] = setvar(
    "varLastStatusCode", "@string(coalesce(outputs('Update_Existing_Item')?['statusCode'], 0))",
    {"Update_Existing_Item": ["Succeeded", "Failed"]})
update_inner["Append_Update_Error"] = append(
    "varItemErrors", {"messageId": "@outputs('Compose_Message_Id')",
                      "code": "ERR_ITEM_UPDATE_FAILED",
                      "httpStatusCode": "@variables('varLastStatusCode')"},
    {"Set_Update_Status_Code": ["Succeeded"], "Update_Existing_Item": ["Failed", "TimedOut"]})
update_inner["Increment_Failed_Count_Update"] = incr(
    "varFailedCount", {"Append_Update_Error": ["Succeeded"]})

# --- 新規作成（0件） ---
create_item_inner, _ = chain([
    ("Compose_Create_Item_Body", compose(CREATE_ITEM_BODY)),
    ("Create_List_Item", http("POST", list_uri("/items"), H_VERBOSE,
                              "@string(outputs('Compose_Create_Item_Body'))")),
])
create_item_inner["Set_Create_Item_Status_Code"] = setvar(
    "varLastStatusCode", "@string(coalesce(outputs('Create_List_Item')?['statusCode'], 0))",
    {"Create_List_Item": ["Succeeded", "Failed"]})
create_item_inner["Increment_Created_Count"] = incr(
    "varCreatedCount", {"Create_List_Item": ["Succeeded"]})
create_item_inner["Set_Item_Create_Failed"] = setvar(
    "varItemCreateFailed", True, {"Create_List_Item": ["Failed", "TimedOut"]})

# --- 作成失敗時のフォールバック（同時実行で他方が先に作成したケースを吸収） ---
retry_found_inner, _ = chain([
    ("Compose_Retry_Item_Id",
     compose("@string(coalesce(first(" + RETRY_SEARCH_RESULT + ")?['Id'], 0))")),
    ("Compose_Retry_Update_Body", compose(UPDATE_ITEM_BODY)),
    ("Update_Item_After_Create_Failure",
     http("POST", RETRY_UPDATE_ITEM_URI, H_MERGE_V,
          "@string(outputs('Compose_Retry_Update_Body'))")),
    ("Increment_Updated_Count_After_Retry", incr("varUpdatedCount")),
])
retry_not_found_inner, _ = chain([
    ("Append_Create_Item_Error", append("varItemErrors", {
        "messageId": "@outputs('Compose_Message_Id')",
        "code": "ERR_ITEM_CREATE_FAILED",
        "httpStatusCode": "@variables('varLastStatusCode')"})),
    ("Increment_Failed_Count_Create", incr("varFailedCount")),
])
retry_inner, _ = chain([
    ("Research_After_Create_Failure", http("GET", SEARCH_ITEM_URI, H_NOMETA)),
])
retry_inner["Condition_Retry_Found"] = cond(
    {"and": [{"greater": ["@length(" + RETRY_SEARCH_RESULT + ")", 0]}]},
    retry_found_inner, retry_not_found_inner,
    {"Research_After_Create_Failure": ["Succeeded", "Failed"]})

# --- メッセージIDが使えない場合 ---
bad_id_inner, _ = chain([
    ("Append_Bad_MessageId_Error", append("varItemErrors", {
        "messageId": "@outputs('Compose_Message_Id')",
        "code": "ERR_ITEM_MESSAGE_ID_UNUSABLE",
        "detail": "メッセージIDが空、または255文字を超えています。"})),
    ("Increment_Failed_Count_BadId", incr("varFailedCount")),
])
convert_failed_inner, _ = chain([
    ("Append_Convert_Error", append("varItemErrors", {
        "messageId": "@outputs('Compose_Message_Id')",
        "code": "ERR_BODY_CONVERSION_FAILED",
        "detail": "本文のプレーンテキスト変換に失敗したため、この1件は登録していません。"})),
    ("Increment_Failed_Count_Convert", incr("varFailedCount")),
])

MSG_ID_OK = {"and": [
    {"greater": ["@length(outputs('Compose_Message_Id'))", 0]},
    {"lessOrEquals": ["@length(outputs('Compose_Message_Id'))", MAX_TEXT_LENGTH]},
    eq("@variables('varItemError')", ""),
]}

item_seq = [
    ("Set_Item_Body_Text_Reset", setvar("varItemBodyText", "")),
    ("Set_Item_Body_Final_Reset", setvar("varItemBodyFinal", "")),
    ("Set_Item_Error_Reset", setvar("varItemError", "")),
    ("Set_Item_Create_Failed_Reset", setvar("varItemCreateFailed", False)),
    ("Compose_Message_Id", compose(
        "@trim(string(coalesce(" + IT + "?['internetMessageId'], " + IT + "?['id'], '')))")),
    ("Compose_Subject", compose("@trim(string(coalesce(" + IT + "?['subject'], '')))")),
    ("Compose_Sender", compose("@trim(string(coalesce(" + IT + "?['from'], '')))")),
    ("Compose_Received", compose("@trim(string(coalesce(" + IT + "?['receivedDateTime'], '')))")),
    ("Compose_Body_Html", compose("@string(coalesce(" + IT + "?['body'], ''))")),
    ("Condition_Item_Has_Body", cond(
        {"and": [{"greater": ["@length(outputs('Compose_Body_Html'))", 0]}]}, convert_inner)),
]
item_actions, item_last = chain(item_seq)

sync_body_inner = {}
sync_body_inner["Condition_Body_Too_Long"] = cond(
    {"and": [{"greater": ["@length(variables('varItemBodyText'))", MAX_BODY_LENGTH]}]},
    truncate_inner, no_truncate_inner)
sync_body_inner["Search_Existing_Item"] = http(
    "GET", SEARCH_ITEM_URI, H_NOMETA, runafter=ra("Condition_Body_Too_Long"))
sync_body_inner["Set_Search_Status_Code"] = setvar(
    "varLastStatusCode", "@string(coalesce(outputs('Search_Existing_Item')?['statusCode'], 0))",
    {"Search_Existing_Item": ["Succeeded", "Failed"]})
# 検索自体が失敗した場合は「一致0件」と誤認せず、その1件を失敗として記録する
# （誤認すると重複作成の原因になる。指示§17）
sync_body_inner["Append_Search_Error"] = append(
    "varItemErrors", {"messageId": "@outputs('Compose_Message_Id')",
                      "code": "ERR_ITEM_SEARCH_FAILED",
                      "httpStatusCode": "@variables('varLastStatusCode')"},
    {"Search_Existing_Item": ["Failed", "TimedOut"]})
sync_body_inner["Increment_Failed_Count_Search"] = incr(
    "varFailedCount", {"Append_Search_Error": ["Succeeded"]})
sync_body_inner["Condition_Item_Is_Duplicate"] = cond(
    {"and": [{"greater": ["@length(" + SEARCH_RESULT + ")", 1]}]},
    duplicate_inner, runafter=ra("Search_Existing_Item"))
sync_body_inner["Condition_Item_Exists"] = cond(
    {"and": [eq("@length(" + SEARCH_RESULT + ")", 1)]},
    update_inner, runafter=ra("Condition_Item_Is_Duplicate"))
sync_body_inner["Condition_Item_Is_New"] = cond(
    {"and": [eq("@length(" + SEARCH_RESULT + ")", 0)]},
    create_item_inner, runafter=ra("Condition_Item_Exists"))
sync_body_inner["Condition_Create_Failed_Fallback"] = cond(
    {"and": [eq("@variables('varItemCreateFailed')", True)]},
    retry_inner, runafter=ra("Condition_Item_Is_New"))

item_actions["Condition_Item_Ready"] = cond(MSG_ID_OK, sync_body_inner, runafter=ra(item_last))
item_actions["Condition_Item_Message_Id_Unusable"] = cond(
    {"and": [{"or": [
        eq("@length(outputs('Compose_Message_Id'))", 0),
        {"greater": ["@length(outputs('Compose_Message_Id'))", MAX_TEXT_LENGTH]}]}]},
    bad_id_inner, runafter=ra("Condition_Item_Ready"))
# メッセージID不正と本文変換失敗が同時に起きても二重計上しないよう、ID条件も併せて見る
item_actions["Condition_Item_Convert_Failed"] = cond(
    {"and": [eq("@variables('varItemError')", "ERR_BODY_CONVERSION_FAILED"),
             {"greater": ["@length(outputs('Compose_Message_Id'))", 0]},
             {"lessOrEquals": ["@length(outputs('Compose_Message_Id'))", MAX_TEXT_LENGTH]}]},
    convert_failed_inner, runafter=ra("Condition_Item_Message_Id_Unusable"))

sync_inner = {}
sync_inner["Foreach_Email"] = foreach("@outputs('Compose_Sorted_Emails')", item_actions)

sync_scope_actions = {}
sync_scope_actions["Set_Stage_Sync_Items"] = setvar("varStage", "SyncItems")
sync_scope_actions["Condition_Sync_Allowed"] = cond(
    {"and": [eq("@variables('varIsValid')", True), eq("@variables('varSchemaOk')", True)]},
    sync_inner, runafter=ra("Set_Stage_Sync_Items"))
actions["Scope_Sync_Items"] = scope(sync_scope_actions, ra("Scope_Get_Emails"))


# =========================================================================
# Scope_Create_Result : 正常系の結果確定（想定内エラーもここで組み立てる）
# =========================================================================
result_ok_inner, _ = chain([
    ("Set_Status_Success", setvar(
        "varStatus", "@if(equals(variables('varCreatedInThisRun'), true), 'Created', 'Existing')")),
])
result_ng_inner, _ = chain([
    ("Set_Status_Error", setvar("varStatus", "Error")),
])

result_scope_actions = {}
result_scope_actions["Set_Stage_Create_Result"] = setvar("varStage", "CreateResult")
result_scope_actions["Condition_Result_Is_Success"] = cond(
    {"and": [eq("@variables('varIsValid')", True), eq("@variables('varSchemaOk')", True)]},
    result_ok_inner, result_ng_inner, ra("Set_Stage_Create_Result"))
actions["Scope_Create_Result"] = scope(result_scope_actions, ra("Scope_Sync_Items"))


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
    " if(equals(variables('varLastStatusCode'), '429'), 'ERR_THROTTLED',"
    " 'ERR_UNEXPECTED_FAILURE'))))))")

HANDLER_MESSAGE = (
    "@if(not(empty(variables('varErrorMessage'))), variables('varErrorMessage'),"
    " if(equals(variables('varLastStatusCode'), '401'),"
    " 'SharePointまたはOutlookへの認証に失敗しました。接続を作り直してください。',"
    " if(equals(variables('varLastStatusCode'), '403'),"
    " '権限が不足しています。サイトの編集権限と共有メールボックスへのアクセス権を確認してください。',"
    " if(equals(variables('varLastStatusCode'), '404'),"
    " '対象のサイト・リストまたはメールボックスが見つかりません。入力値を確認してください。',"
    " if(equals(variables('varLastStatusCode'), '400'),"
    " '要求が不正です。リスト名・メールボックスのアドレス・取得件数を確認してください。',"
    " if(equals(variables('varLastStatusCode'), '429'),"
    " '呼び出し回数の制限に達しました。しばらく待ってから件数を減らして再実行してください。',"
    " '想定外のエラーが発生しました。実行履歴で失敗したアクションを確認してください。'))))))")

handler_inner, _ = chain([
    ("Compose_Handler_Error_Code", compose(HANDLER_CODE)),
    ("Compose_Handler_Error_Message", compose(HANDLER_MESSAGE)),
    ("Compose_Handler_Error_Details", compose(
        "@union(variables('varErrorMessages'),"
        " createArray(concat('stage=', variables('varStage')),"
        " concat('httpStatusCode=', variables('varLastStatusCode')),"
        " concat('listCreatedInThisRun=', string(variables('varCreatedInThisRun'))),"
        " concat('listId=', variables('varListId')),"
        " concat('fetchedCount=', string(variables('varFetchedCount'))),"
        " concat('lastErrorBody=', variables('varLastErrorBody'))))")),
    ("Set_Error_Code_From_Handler",
     setvar("varErrorCode", "@outputs('Compose_Handler_Error_Code')")),
    ("Set_Error_Message_From_Handler",
     setvar("varErrorMessage", "@outputs('Compose_Handler_Error_Message')")),
    ("Set_Error_Messages_From_Handler",
     setvar("varErrorMessages", "@outputs('Compose_Handler_Error_Details')")),
    ("Set_Status_From_Handler", setvar("varStatus", "Error")),
])
actions["Scope_Handle_Error"] = scope(
    handler_inner, {"Scope_Create_Result": ["Failed", "Skipped", "TimedOut"]})


# =========================================================================
# Scope_Finalize : 結果JSONの組み立て（指示§19）
# すべての状態が確定した後に1箇所で組み立てる。参照するのは変数だけ。
# =========================================================================
RESULT_COMMON = {
    "flowName": FLOW_LOGICAL_NAME,
    "completedAt": "@utcNow()",
    "siteUrl": "@variables('varSiteUrl')",
    "siteId": "@variables('varSiteId')",
    "listName": "@variables('varListName')",
    "listCreated": "@variables('varCreatedInThisRun')",
    "listId": "@variables('varListId')",
    "listUrl": "@variables('varListUrl')",
    "mailbox": "@variables('varMailbox')",
    "requestedCount": "@variables('varRequestedCount')",
    "fetchedCount": "@variables('varFetchedCount')",
    "createdCount": "@variables('varCreatedCount')",
    "updatedCount": "@variables('varUpdatedCount')",
    "duplicateCount": "@variables('varDuplicateCount')",
    "failedCount": "@variables('varFailedCount')",
    "truncatedCount": "@variables('varTruncatedCount')",
    "duplicates": "@variables('varDuplicates')",
    "itemErrors": "@variables('varItemErrors')",
    "truncatedItems": "@variables('varTruncatedItems')",
    "schemaWarnings": "@variables('varSchemaWarnings')",
    "missingFields": "@variables('varMissingFields')",
    "incompatibleFields": "@variables('varIncompatibleFields')",
}

SUCCESS_RESULT = dict(RESULT_COMMON)
SUCCESS_RESULT["success"] = True
SUCCESS_RESULT["status"] = "@variables('varStatus')"
SUCCESS_RESULT["message"] = (
    "@if(equals(variables('varCreatedInThisRun'), true),"
    " 'リストを新規作成し、メールを同期しました。',"
    " '既存リストへメールを同期しました。')")

ERROR_RESULT = dict(RESULT_COMMON)
ERROR_RESULT["success"] = False
ERROR_RESULT["status"] = "Error"
ERROR_RESULT["message"] = "@variables('varErrorMessage')"
ERROR_RESULT["error"] = {
    "code": "@variables('varErrorCode')",
    "message": "@variables('varErrorMessage')",
    "stage": "@variables('varStage')",
    "details": "@variables('varErrorMessages')",
}

build_success, _ = chain([
    ("Create_Success_Result", compose(SUCCESS_RESULT)),
    ("Set_Result_Object_Success",
     setvar("varResultObject", "@outputs('Create_Success_Result')")),
])
build_error, _ = chain([
    ("Create_Error_Result", compose(ERROR_RESULT)),
    ("Set_Result_Object_Error", setvar("varResultObject", "@outputs('Create_Error_Result')")),
])

finalize_actions = {}
finalize_actions["Condition_Result_Is_Error"] = cond(
    {"and": [eq("@variables('varStatus')", "Error")]}, build_error, build_success)
finalize_actions["Serialize_Result_To_Json"] = setvar(
    "varResultJson", "@string(variables('varResultObject'))",
    ra("Condition_Result_Is_Error"))
finalize_actions["Compose_Flow_Output"] = compose({
    "success": "@coalesce(variables('varResultObject')?['success'], false)",
    "status": "@variables('varStatus')",
    "resultObject": "@variables('varResultObject')",
    "resultJson": "@variables('varResultJson')",
}, ra("Serialize_Result_To_Json"))

actions["Scope_Finalize"] = scope(
    finalize_actions, {"Scope_Handle_Error": ["Succeeded", "Failed", "Skipped", "TimedOut"]})


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
                        "description": "同名リストが存在する場合はそのリストを使用します（リスト自体は変更しません）",
                    },
                    "SharedMailboxAddress": {
                        "title": "共有メールボックスのアドレス",
                        "type": "string",
                        # 【重要】この文字列に '@' を書かない。'@{' は Power Automate に
                        # 式の補間として解釈され、中身が関数呼び出しでないとインポート時に
                        # 「Unable to parse template language expression」で失敗する。
                        # 表示テキストにメールアドレスの例を書かないこと（例は docs/usage.md に置く）。
                        "description": "監視対象の共有メールボックスの完全なメールアドレス。"
                                       "メールは読み取るだけで、既読化・移動・削除は行いません",
                    },
                    "MailCount": {
                        "title": "取得件数",
                        "type": "integer",
                        "description": "1〜" + str(MAX_MAIL_COUNT) + " の整数。超過した場合は処理を行わずエラーで終了します",
                    },
                },
                "required": ["SharePointUrl", "ListName", "SharedMailboxAddress", "MailCount"],
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
                "connectionName": CN_SPO, "source": "Invoker",
                "id": "/providers/Microsoft.PowerApps/apis/shared_sharepointonline",
                "tier": "NotSpecified", "apiName": "sharepointonline",
            },
            "shared_office365": {
                "connectionName": CN_OL, "source": "Invoker",
                "id": "/providers/Microsoft.PowerApps/apis/shared_office365",
                "tier": "NotSpecified", "apiName": "office365",
            },
            "shared_conversionservice": {
                "connectionName": CN_CC, "source": "Invoker",
                "id": "/providers/Microsoft.PowerApps/apis/shared_conversionservice",
                "tier": "NotSpecified", "apiName": "conversionservice",
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
        "description": "共有メールボックスの最新メールを、指定サイトのSharePointリストへ登録／更新する",
        "createdTime": "2026-08-03T00:00:00.0000000Z",
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
            "dependsOn": [API_SPO, CONN_SPO, API_OL, CONN_OL, API_CC, CONN_CC],
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
        API_OL: {
            "id": "/providers/Microsoft.PowerApps/apis/shared_office365",
            "name": "shared_office365", "type": "Microsoft.PowerApps/apis",
            "suggestedCreationType": "Existing",
            "details": {"displayName": "Office 365 Outlook"},
            "configurableBy": "System", "hierarchy": "Child", "dependsOn": [],
        },
        CONN_OL: {
            "type": "Microsoft.PowerApps/apis/connections",
            "suggestedCreationType": "Existing", "creationType": "Existing",
            "details": {"displayName": "Office 365 Outlook への接続を選択してください"},
            "configurableBy": "User", "hierarchy": "Child", "dependsOn": [API_OL],
        },
        API_CC: {
            "id": "/providers/Microsoft.PowerApps/apis/shared_conversionservice",
            "name": "shared_conversionservice", "type": "Microsoft.PowerApps/apis",
            "suggestedCreationType": "Existing",
            "details": {"displayName": "Content Conversion"},
            "configurableBy": "System", "hierarchy": "Child", "dependsOn": [],
        },
        CONN_CC: {
            "type": "Microsoft.PowerApps/apis/connections",
            "suggestedCreationType": "Existing", "creationType": "Existing",
            "details": {"displayName": "Content Conversion への接続を選択してください"},
            "configurableBy": "User", "hierarchy": "Child", "dependsOn": [API_CC],
        },
    },
}

flows_manifest = {"packageSchemaVersion": "1.0", "flowAssets": {"assetPaths": [PKG_FOLDER]}}
apis_map = {"shared_sharepointonline": API_SPO, "shared_office365": API_OL,
            "shared_conversionservice": API_CC}
connections_map = {"shared_sharepointonline": CONN_SPO, "shared_office365": CONN_OL,
                   "shared_conversionservice": CONN_CC}


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
