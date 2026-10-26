# -*- coding: utf-8 -*-
"""
SyncMailToListWithExaminerDetection のレガシーパッケージ（展開形）を生成する。

既存の sync-mail-to-list（実環境インポート・実行成功）を**逐語コピー**した土台に、
  (1) 業務用列を5列→7列（ExaminerName / ApplicationNumber を追加）
  (2) 件名とプレーンテキスト本文からの審査官名・出願番号の推定
を足したもの。既存フローは1文字も変更していない。

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

FLOW_LOGICAL_NAME = "SyncMailToListWithExaminerDirectory"
FLOW_DISPLAY_NAME = "共有メールボックスのメールをSharePointリストへ同期（審査官名・出願番号の推定＋名簿突合）"

MAX_MAIL_COUNT = 100          # 指示§4.4 / 調整制限300コール/60秒と実行時間上限から決定
MAX_BODY_LENGTH = 63999       # SharePoint 複数行テキスト（Note）の上限
MAX_TEXT_LENGTH = 255         # 1行テキスト（Text）の上限

# ---- 固定GUID（本フロー用に新規採番・匿名。実テナントの値は一切含まない） ----
FLOW_ID    = "288e9485-103d-4e27-bf51-e4853d8a7b72"
PKG_FOLDER = "a294f628-5f49-4860-8733-1cafa584ec01"
API_SPO    = "e210764f-df64-4d5d-b512-9d712b3992f7"
CONN_SPO   = "9a7ada7f-1d62-4151-abd7-ee1ce6d3305d"
API_OL     = "ba8d1540-a095-4214-8eeb-b08b45b9b819"
CONN_OL    = "ffc66190-1e87-431d-9bb0-7692b9b8923a"
API_CC     = "14f9d08e-a1d5-4b62-b635-669497c866de"
CONN_CC    = "43d3c6ee-53a1-4ce4-9096-b329a892f63f"
CN_SPO     = "b402077b09c640af860b09f787946062"   # connectionReferences.connectionName（匿名）
CN_OL      = "5f2304188c78412fbd1d7c5c33549b22"
CN_CC      = "b91871d52c1949109265bf38224de9dc"
PKG_TELE   = "1a1aa5bd-a8ab-43ad-b000-5af286df111b"

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
# 審査官名簿のサイト。同期先とは別サイトでもよいので dataset を分ける。
# **読み取り専用**（検証スクリプトの検査 R1 が「このデータセットを使うのは GET だけ」を機械確認する）。
DATASET_ROSTER = "@variables('varRosterSiteUrl')"

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
    {
        "internal": "ExaminerName", "display": "審査官名", "type": "Text",
        "xml": ('<Field Type="Text" Name="ExaminerName" StaticName="ExaminerName"'
                ' DisplayName="ExaminerName" Required="FALSE" MaxLength="255" />'),
    },
    {
        "internal": "ApplicationNumber", "display": "出願番号", "type": "Text",
        "xml": ('<Field Type="Text" Name="ApplicationNumber" StaticName="ApplicationNumber"'
                ' DisplayName="ApplicationNumber" Required="FALSE" MaxLength="255" />'),
    },
    # --- 審査官名簿との突合結果（本フローで追加した5列） ---
    {
        "internal": "ExaminerEmail", "display": "審査官メールアドレス", "type": "Text",
        "xml": ('<Field Type="Text" Name="ExaminerEmail" StaticName="ExaminerEmail"'
                ' DisplayName="ExaminerEmail" Required="FALSE" MaxLength="255" />'),
    },
    {
        "internal": "ExaminerTeamsUserId", "display": "審査官TeamsユーザーID", "type": "Text",
        "xml": ('<Field Type="Text" Name="ExaminerTeamsUserId"'
                ' StaticName="ExaminerTeamsUserId" DisplayName="ExaminerTeamsUserId"'
                ' Required="FALSE" MaxLength="255" />'),
    },
    {
        "internal": "ExaminerSyncKey", "display": "審査官同期キー", "type": "Text",
        "xml": ('<Field Type="Text" Name="ExaminerSyncKey" StaticName="ExaminerSyncKey"'
                ' DisplayName="ExaminerSyncKey" Required="FALSE" MaxLength="255" />'),
    },
    {
        "internal": "ExaminerMatchedName", "display": "名簿上の氏名", "type": "Text",
        "xml": ('<Field Type="Text" Name="ExaminerMatchedName"'
                ' StaticName="ExaminerMatchedName" DisplayName="ExaminerMatchedName"'
                ' Required="FALSE" MaxLength="255" />'),
    },
    {
        "internal": "ExaminerMatchStatus", "display": "名簿突合状態", "type": "Text",
        "xml": ('<Field Type="Text" Name="ExaminerMatchStatus"'
                ' StaticName="ExaminerMatchStatus" DisplayName="ExaminerMatchStatus"'
                ' Required="FALSE" MaxLength="255" />'),
    },
]

# 既定ビューの並び順（指示§11）。第2キーに ID 降順を入れて同時刻の順序を安定させる。
VIEW_QUERY = ("<OrderBy><FieldRef Name='ReceivedDateTime' Ascending='FALSE' />"
              "<FieldRef Name='ID' Ascending='FALSE' /></OrderBy>")


# =========================================================================
# アクション生成ヘルパー
# =========================================================================
def http(method, uri, headers, body=None, runafter=None, dataset=None):
    """SharePoint「HTTP要求を送信します」アクション

    dataset を省略すると同期先サイト（varSiteUrl）。
    審査官名簿を読むときだけ DATASET_ROSTER を明示的に渡す。
    どちらの場合も**実値URLは埋め込まない**（変数参照のみ）。
    """
    params = {"dataset": dataset or DATASET, "parameters/method": method,
              "parameters/uri": uri, "parameters/headers": dict(headers)}
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


def field_uri_expr(name_expr, suffix=""):
    """内部名を**式**で与える版（ループ内で items(...) を使うため）。

    field_uri() は内部名をリテラルとして @concat の中へ埋め込むので、
    ループ変数を渡すには `@{...}` の入れ子が必要になり式として不正になる。
    連結の項として渡す形にすれば入れ子にならない。
    """
    return ("@concat('_api/web/lists(guid''', variables('varListId'),"
            " ''')/fields/getbyinternalnameortitle(''', " + name_expr
            + ", ''')" + suffix + "')")


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
    # --- 審査官名簿（読み取り専用） ---
    ("Initialize_InputRosterUrl", "varInputRosterUrl", "string",
     "@trim(coalesce(triggerBody()?['RosterSharePointUrl'], ''))"),
    ("Initialize_RosterListName", "varRosterListName", "string",
     "@trim(coalesce(triggerBody()?['RosterListName'], ''))"),
    ("Initialize_RosterSiteUrl", "varRosterSiteUrl", "string", ""),
    ("Initialize_RosterListId", "varRosterListId", "string", ""),
    ("Initialize_RosterReady", "varRosterReady", "boolean", False),
    ("Initialize_ExaminerMatchedCount", "varExaminerMatchedCount", "integer", 0),
    ("Initialize_ExaminerUnmatchedCount", "varExaminerUnmatchedCount", "integer", 0),
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
    # --- 検出（審査官名・出願番号）の集計。SharePointの列は増やさない（指示§10） ---
    ("Initialize_ExaminerFoundCount", "varExaminerFoundCount", "integer", 0),
    ("Initialize_ApplicationFoundCount", "varApplicationFoundCount", "integer", 0),
    ("Initialize_NeedsReviewCount", "varNeedsReviewCount", "integer", 0),
    ("Initialize_DetectionReviews", "varDetectionReviews", "array", []),
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
    " if(equals(variables('varErrorCode'), 'ERR_ROSTER_URL_EMPTY'),"
    " '審査官名簿のSharePointサイトURLが入力されていません。',"
    " if(equals(variables('varErrorCode'), 'ERR_ROSTER_URL_INVALID'),"
    " '審査官名簿のSharePointサイトURLの形式が正しくありません。',"
    " if(equals(variables('varErrorCode'), 'ERR_ROSTER_LISTNAME_EMPTY'),"
    " '審査官名簿のリスト名が入力されていません。',"
    " if(equals(variables('varErrorCode'), 'ERR_ROSTER_LIST_NOT_FOUND'),"
    " '審査官名簿のリストが見つかりません。サイトURLとリスト名を確認してください。'"
    " 'リストは作成しません。',"
    " '')))))))))))))))))")

# 名簿サイトのURLも同じ規則で正規化する。式は同期先と完全に同じ形を使い、
# 参照する変数と Compose 名だけを差し替える（規則が2箇所で食い違わないようにするため）。
def _url_chain(prefix, src_var):
    frag = "outputs('Compose_%s_Url_No_Fragment')" % prefix
    qry = "outputs('Compose_%s_Url_No_Query')" % prefix
    lay = "outputs('Compose_%s_Url_Before_Layouts')" % prefix
    site = "outputs('Compose_%s_Site_Url')" % prefix
    host = "outputs('Compose_%s_Site_Host')" % prefix
    return [
        ("Compose_%s_Url_No_Fragment" % prefix,
         compose("@first(split(variables('%s'), '#'))" % src_var)),
        ("Compose_%s_Url_No_Query" % prefix, compose("@first(split(%s, '?'))" % frag)),
        ("Compose_%s_Url_Before_Layouts" % prefix, compose(
            "@substring(concat(%s, '#'), 0, length(first(split(toLower(%s), '/_layouts/'))))"
            % (qry, qry))),
        ("Compose_%s_Site_Url" % prefix, compose(
            "@if(endsWith(%s, '/'), join(take(split(%s, '/'), sub(length(split(%s, '/')), 1)),"
            " '/'), %s)" % (lay, lay, lay, lay))),
        ("Compose_%s_Site_Host" % prefix,
         compose("@first(split(last(split(%s, '//')), '/'))" % site)),
        ("Validate_%s_Url" % prefix, compose(
            "@if(empty(variables('%s')), 'ERR_ROSTER_URL_EMPTY',"
            " if(not(startsWith(%s, 'https://')), 'ERR_ROSTER_URL_INVALID',"
            " if(not(endsWith(%s, '.sharepoint.com')), 'ERR_ROSTER_URL_INVALID',"
            " if(empty(%s), 'ERR_ROSTER_URL_INVALID',"
            " if(empty(variables('varRosterListName')), 'ERR_ROSTER_LISTNAME_EMPTY',"
            " '')))))" % (src_var, site, host, site))),
    ]


validate_seq = [
    ("Set_Stage_Validate_Input", setvar("varStage", "ValidateInput")),
    # 列定義の配列。列作成・既定ビュー・スキーマ検証の3スコープが**すべてここを参照**する。
    # 必ず実行される Scope_Validate_Input に置く（Verify_Schema は既存リスト経路でも動くため、
    # varCreatedInThisRun のガード配下に置くと参照できなくなる）。
    ("Compose_Field_Definitions", compose(
        [{"internal": f["internal"], "display": f["display"],
          "type": f["type"], "xml": f["xml"]} for f in FIELDS])),
    ("Compose_Url_No_Fragment",
     compose("@first(split(variables('varInputSharePointUrl'), '#'))")),
    ("Compose_Url_No_Query", compose("@first(split(" + U_FRAG + ", '?'))")),
    ("Compose_Url_Before_Layouts", compose(URL_BEFORE_LAYOUTS)),
    ("Compose_Site_Url", compose(SITE_URL_EXPR)),
    ("Compose_Site_Host", compose(SITE_HOST_EXPR)),
    ("Compose_Site_Origin", compose(SITE_ORIGIN_EXPR)),
] + _url_chain("Roster", "varInputRosterUrl") + [
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
             " if(not(empty(outputs('Validate_Count'))), outputs('Validate_Count'),"
             " outputs('Validate_Roster_Url')))))")),
    ("Set_RosterSiteUrl", setvar("varRosterSiteUrl", "@outputs('Compose_Roster_Site_Url')")),
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
# 列ごとにアクションを展開せず、**列定義の配列を Apply to each で回す**。
# 展開形だと1列あたり6アクション（存在確認2＋作成2＋改名2）かかり、
# 12列で72アクションになって500の上限に収まらない。ループなら列数によらず一定。
# 同リポジトリの create_initialized_sharepoint_list が同じ形（Apply_to_each_DeleteField）。
#
# 列の存在確認（旧 Filter_Existing_Field_*）は**外した**。このスコープは
# varCreatedInThisRun == true、つまり**この実行で作ったばかりの空リスト**でしか動かないため、
# 列が既に存在することが構造上ありえない（下の Condition_Created_In_This_Run）。
create_field_body = {"parameters": {"__metadata": {"type": "SP.XmlSchemaFieldCreationInformation"},
                                    "Options": 0,
                                    "SchemaXml": "@items('Foreach_Create_Field')?['xml']"}}
create_field_inner, _ = chain([
    ("Compose_Field_Body", compose(create_field_body)),
    ("Create_Field", http("POST", list_uri("/fields/createFieldAsXml"), H_VERBOSE,
                          "@string(outputs('Compose_Field_Body'))")),
    # 表示名だけを日本語へ変更する（内部名は変わらないため後続の $filter / 参照は壊れない）。
    # 作成と同じ回で改名するので、ループは1つで済む。
    ("Compose_Rename_Body", compose({"Title": "@items('Foreach_Create_Field')?['display']"})),
    ("Rename_Field", http("POST", field_uri_expr("items('Foreach_Create_Field')?['internal']"),
                          H_MERGE_N, "@string(outputs('Compose_Rename_Body'))")),
])
init_field_seq = [
    ("Get_Fields_Before_Init", http("GET", list_uri(FIELDS_SELECT), H_NOMETA)),
    ("Foreach_Create_Field", foreach("@outputs('Compose_Field_Definitions')",
                                     create_field_inner)),
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
# 既定ビューへの列追加もループにする。**並列オフ（foreach ヘルパーが強制）**なので
# 列の順序は Compose_Field_Definitions の並びどおりに保たれる。
view_seq.append(
    ("Foreach_Add_View_Field", foreach(
        "@outputs('Compose_Field_Definitions')",
        {"Add_View_Field": http(
            "POST",
            "@concat('_api/web/lists(guid''', variables('varListId'),"
            " ''')/views(guid''', variables('varDefaultViewId'),"
            " ''')/viewfields/AddViewField(''', items('Foreach_Add_View_Field')?['internal'],"
            " ''')')",
            H_MERGE_V, "@string(outputs('Compose_Add_View_Field_Body'))")})))
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
# スキーマ検証もループにする（展開形だと1列あたり5アクション＝12列で60）。
# ループ内の Query は「実際の列一覧」を毎回フィルタするだけで、REST 呼び出しは増えない
# （Get_List_Fields_For_Schema の1回だけ。展開形と同じ）。
_sf = "body('Filter_Schema_Field')"
schema_seq += [
    ("Foreach_Verify_Field", foreach("@outputs('Compose_Field_Definitions')", dict(chain([
        ("Filter_Schema_Field", query(
            "@coalesce(body('Get_List_Fields_For_Schema')?['value'], json('[]'))",
            "@equals(coalesce(item()?['InternalName'], ''),"
            " items('Foreach_Verify_Field')?['internal'])")),
        ("Condition_Schema_Field", cond(
            {"and": [eq("@length(" + _sf + ")", 0)]},
            {"Append_Missing_Field": append(
                "varMissingFields", "@items('Foreach_Verify_Field')?['internal']")},
            {"Condition_Schema_Type": cond(
                {"and": [{"not": eq(
                    "@coalesce(first(" + _sf + ")?['TypeAsString'], '')",
                    "@items('Foreach_Verify_Field')?['type']")}]},
                {"Append_Incompatible_Field": append("varIncompatibleFields", {
                    "internalName": "@items('Foreach_Verify_Field')?['internal']",
                    "expected": "@items('Foreach_Verify_Field')?['type']",
                    "actual": "@coalesce(first(" + _sf + ")?['TypeAsString'], '')"})})})),
    ])[0]))),
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
actions["Scope_Get_Emails"] = scope(emails_scope_actions, ra("Scope_Load_Roster"))


# =========================================================================
# Scope_Load_Roster : 審査官名簿を1回だけ読み込む（**読み取り専用**）
#
# メール1件ごとに名簿を検索すると、100件で100回のRESTになる。
# 名簿は実行中に変わらないので**ループの前で1回だけ全件取得**し、
# ループ内は Filter array（Query）で突合する。
# 同じ形が既にある: Get_Fields_Before_Init の結果を7回の Filter が使い回している。
#
# 配列変数には入れない。body('Get_Roster_Items') を直接参照すれば足りる
# （変数にすると Initialize と Set で2アクション無駄になる）。
# =========================================================================
ROSTER_ITEMS_SELECT = (
    "/items?$select=Id,FullName,LastName,FirstName,Email,SyncKey,TeamsUserId,"
    "MemberStatus,IsActive&$top=5000")


def roster_list_uri(suffix=""):
    return ("@concat('_api/web/lists(guid''', variables('varRosterListId'),"
            " ''')" + suffix + "')")


# 名簿リストの特定はリスト名の完全一致（GetByTitle( は使わない。不変則）。
# 大文字小文字と前後空白を無視するのは同期先リストの Filter_Matching_Lists と同じ規則。
roster_found_inner, _ = chain([
    ("Set_Roster_List_Id", setvar(
        "varRosterListId",
        "@trim(string(coalesce(first(body('Filter_Roster_Lists'))?['Id'], '')))")),
    ("Get_Roster_Items", http("GET", roster_list_uri(ROSTER_ITEMS_SELECT), H_NOMETA,
                              dataset=DATASET_ROSTER)),
    ("Set_Roster_Ready", setvar(
        "varRosterReady",
        "@equals(string(coalesce(outputs('Get_Roster_Items')?['statusCode'], 0)), '200')",
        {"Get_Roster_Items": ["Succeeded", "Failed"]})),
])
roster_missing_inner, _ = chain([
    ("Set_ErrorCode_Roster", setvar("varErrorCode", "ERR_ROSTER_LIST_NOT_FOUND")),
    ("Set_ErrorMessage_Roster", setvar(
        "varErrorMessage",
        "審査官名簿のリストが見つかりません。サイトURLとリスト名を確認してください。"
        "名簿リストは作成しません。")),
    ("Set_IsValid_Roster", setvar("varIsValid", False)),
    ("Append_Roster_Error", append(
        "varErrorMessages",
        "@concat('ERR_ROSTER_LIST_NOT_FOUND: ', variables('varRosterListName'))")),
])
roster_inner, roster_last = chain([
    ("Get_Roster_Lists", http("GET", LISTS_SELECT, H_NOMETA, dataset=DATASET_ROSTER)),
    ("Set_Roster_Lists_Status_Code", setvar(
        "varLastStatusCode",
        "@string(coalesce(outputs('Get_Roster_Lists')?['statusCode'], 0))",
        {"Get_Roster_Lists": ["Succeeded", "Failed"]})),
    ("Filter_Roster_Lists", query(
        "@coalesce(body('Get_Roster_Lists')?['value'], json('[]'))",
        "@equals(toLower(trim(coalesce(item()?['Title'], ''))),"
        " toLower(trim(variables('varRosterListName'))))")),
])
roster_inner["Condition_Roster_List_Found"] = cond(
    {"and": [eq("@length(body('Filter_Roster_Lists'))", 1)]},
    roster_found_inner, roster_missing_inner, runafter=ra(roster_last))

roster_scope_actions = {}
roster_scope_actions["Set_Stage_Load_Roster"] = setvar("varStage", "LoadRoster")
roster_scope_actions["Condition_Load_Roster_Allowed"] = cond(
    {"and": [eq("@variables('varIsValid')", True), eq("@variables('varSchemaOk')", True)]},
    roster_inner, runafter=ra("Set_Stage_Load_Roster"))
actions["Scope_Load_Roster"] = scope(roster_scope_actions, ra("Scope_Verify_Schema"))


# =========================================================================
# Scope_Sync_Items : メール1件ずつの登録／更新（指示§14）
# =========================================================================
IT = "items('Foreach_Email')"
ITEM_VALUES = {
    "ReceivedDateTime": "@if(empty(outputs('Compose_Received')), null, outputs('Compose_Received'))",
    "SenderAddress": "@outputs('Compose_Sender')",
    "Subject": "@outputs('Compose_Subject')",
    "BodyPlainText": "@variables('varItemBodyFinal')",
    # 推定結果。取得できなくても空文字で登録し、メール同期は止めない（指示§11）
    # 審査官名は名簿で一意に補完できたときだけ名簿の表記へ置き換わる（Compose_Dir_Name）。
    "ExaminerName": "@outputs('Compose_Dir_Name')",
    "ApplicationNumber": "@outputs('Compose_App_Final')",
    # 名簿突合の結果。突合できなくても空文字で登録する（同期は止めない）。
    "ExaminerEmail": "@outputs('Compose_Dir_Result')?['email']",
    "ExaminerTeamsUserId": "@outputs('Compose_Dir_Result')?['teamsUserId']",
    "ExaminerSyncKey": "@outputs('Compose_Dir_Result')?['syncKey']",
    "ExaminerMatchedName": "@outputs('Compose_Dir_Result')?['matchedName']",
    "ExaminerMatchStatus": "@outputs('Compose_Dir_Status')",
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

# =========================================================================
# 審査官名・出願番号の推定（指示§5〜§10）
#
# 設計の要点（Power Automate の制約から導いた形。docs/examiner_detection_spec.md に詳細）:
#   1. **すべて Compose / Query**。コネクタを1つも呼ばないので検出は実行時に失敗しない
#      → 「検出の失敗でメール同期を止めない」（指示§11）を構造的に保証する
#   2. **コンテナ（Foreach / If）を1つも増やさない**。既存の最深経路が 7/8 のため、
#      検出アクションはすべて Foreach_Email の直下（深さ4）に並ぶ
#   3. 正規表現が無いので「全出現位置を探す」は **split によるアンカー分割**で代替する。
#      split(text, ANCHOR) の k+1 番目の要素＝k 番目の出現の直後の文字列
#   4. substring は範囲外で実行時エラーになる。**必ずパディング定数を連結してから
#      定数オフセットでのみ切る**（検証スクリプトの P3 が機械確認する）
#   5. アクション数上限 500（公式）。1候補あたりの Compose を 3〜4 に抑えている
# =========================================================================
SENT = "<<<TS>>>"                 # スレッド区切りのセンチネル
NCUT = "◆"                   # 名前切り出しのセンチネル（◆）
MK_ROLE = "◇R◇"         # 審査官／審査官補 のマーカー（◇R◇）
MK_TAN = "◇T◇"          # 「担当審査官:」のマーカー（最も強い手掛かり）
MK_LBL = "◇L◇"          # 「審査官:」「ご担当者:」のマーカー
MK_INT = "◇I◇"          # 自己紹介（特許庁の…）のマーカー
MK_ORG = "◇O◇"          # 組織名のマーカー（姓の切れ目を学ぶために使う）
PAD16 = " " * 16
PAD24 = " " * 24
PAD64 = " " * 64

APP_SLOTS = 5          # 本文から見る「特願」の出現数（利用者決定: 現在3＋引用2相当）
# 審査官パターンごとの出現数。**パターン別**にしてアクション数を配分する。
# 1候補につき Compose 3つ（Ctx / Name / Cand）を使うため、1スロット＝3アクション。
# 基礎点の高い T / R / N（役職語・ラベルが隣接する強い手掛かり）に枠を厚く割り当て、
# 弱い L / I / D は2スロットに絞る（利用者決定 2026-08-04。500アクション上限のため）。
EX_SLOTS = {"T": 3, "R": 3, "N": 3, "L": 2, "I": 2, "D": 2}

# -------------------------------------------------------------------------
# スコア表（補助資料§3.4「定数又は設定として管理し、根拠が追跡できる構造にする」）
#
# ここが唯一の定義箇所。式の中に即値を書かない。
# 各候補は適用された項目を "b"（内訳）に記録し、診断の examinerEvidence /
# applicationEvidence に出るので、なぜその候補が勝ったかを実行履歴から追える。
#
# 補助資料の数値をそのまま固定していない箇所:
#   - 「役職隣接 +80」は採らない。R(80)/N(75) の**基礎点そのもの**が役職隣接を表しており、
#     独立加点にすると同じ根拠を二重計上する（資料の疑似コードの不備。docs §13 に記録）。
#   - スレッド深度の -(depth×20) は段階定数にした（段数を数える手段が無いため）。
# -------------------------------------------------------------------------
EX_SCORES = {
    "current": 100,      # 現在のメッセージ
    "quote1": -20,       # 直前の引用
    "quote2": -60,       # さらに古い引用
    "head": 40,          # 現在メッセージの冒頭200文字以内（宛名ブロック）
    "jpo_near": 40,      # 直前24文字に 特許庁／部署名
    "tantou": 40,        # 文脈に「担当審査官」
    "gotantou": 20,      # 文脈に「ご担当」
    "honorific": 10,     # 文脈に「様」「殿」
    "same_section": 30,  # 採用した出願番号と同じ区画にいる
    "repeated": 20,      # 同じ氏名が本文に2回以上出る
    "external": -100,    # 直前24文字に 弁理士／特許事務所 等
    "cc": -80,           # 直前12文字に Cc:
    "participant": -60,  # 直前12文字に 参加者／出席者／同席
    "hiragana": -30,     # ひらがな表記のみ（漢字表記より弱い証拠）
}
APP_SCORES = {
    "base": 50, "subject": 180,
    "current": 100, "quote1": -20, "quote2": -60,
    "label": 40,         # 文脈に「出願番号」
    "topic": 20,         # 文脈に「案件」「標記」「表題」「本件」
    "other_case": -80,   # 文脈に「別件」「誤り」「誤送信」
    "consistency_max": 40,   # 同じ番号が本文に何回出るか（上限）
}
# パターンの優先度。スコア同点時の決定順（補助資料に規定が無いため新設）。
# 実機の sort の安定性に依存すると結果が不定になりうるので、キーに埋め込んで決定的にする。
EX_PATTERN_RANK = {"T": 6, "R": 5, "N": 4, "L": 3, "I": 2, "D": 1, "S": 6}

# ソートキーのオフセット。
# sort は昇順の**文字列**比較なので、キーの桁数が揃っていないと大小が逆転する
# （"9990" > "10150" になり、スコアが低いほうが勝ってしまう）。
# 「スコア＋オフセット」が**常に5桁**に収まることが正しさの条件。
# 10000 では減点が重なってスコアが負になった瞬間に4桁へ落ちる。実際にこれを踏んだ
# （引用2段目の −60 を入れたらテスト A08 が逆転した）。下の assert で構造的に防ぐ。
SORT_OFFSET = 20000


def _assert_sort_key_width(table, bases, label):
    """スコア＋オフセットが常に5桁（10000〜99999）に収まることを生成時に確かめる"""
    neg = sum(v for v in table.values() if v < 0)
    pos = sum(v for v in table.values() if v > 0)
    lo, hi = SORT_OFFSET + min(bases) + neg, SORT_OFFSET + max(bases) + pos
    assert 10000 <= lo, "%s: ソートキーが4桁に落ちる（最小 %d）" % (label, lo)
    assert hi <= 99999, "%s: ソートキーが6桁に伸びる（最大 %d）" % (label, hi)


_assert_sort_key_width(EX_SCORES, [45, 100 + 60], "EX_SCORES")
_assert_sort_key_width({k: v for k, v in APP_SCORES.items()
                        if k not in ("base", "subject")},
                       [APP_SCORES["base"],
                        APP_SCORES["base"] + APP_SCORES["subject"]], "APP_SCORES")

TAB = "decodeUriComponent('%09')"
CR = "decodeUriComponent('%0D')"
LF = "decodeUriComponent('%0A')"


def lit(s):
    """WDL の文字列リテラル（シングルクォートは2重化する）"""
    return "'" + s.replace("'", "''") + "'"


def out(n):
    return "outputs('" + n + "')"


def rep_lit(expr, pairs):
    for a, b in pairs:
        expr = "replace(%s, %s, %s)" % (expr, lit(a), lit(b))
    return expr


def rep_expr(expr, from_expr, to_lit):
    return "replace(%s, %s, %s)" % (expr, from_expr, lit(to_lit))


def or_contains(target, words):
    e = "contains(%s, %s)" % (target, lit(words[0]))
    for w in words[1:]:
        e = "or(%s, contains(%s, %s))" % (e, target, lit(w))
    return e


def all_hiragana(expr):
    """全体がひらがなか。ひらがなを全部除去して空になるかで判定する
    （数字の妥当性を digits_removed で見るのと同じ手法）。空文字は false。"""
    e = expr
    for h in HIRAGANA:
        e = "replace(%s, %s, %s)" % (e, lit(h), lit(""))
    return "and(equals(%s, %s), not(equals(%s, %s)))" % (e, lit(""), expr, lit(""))


def digits_removed(expr):
    e = expr
    for d in "0123456789":
        e = "replace(%s, '%s', '')" % (e, d)
    return e


def tail_last(expr, n, pad):
    """expr の末尾 n 文字。パディングを連結してから定数オフセットで切る（範囲外にならない）"""
    p = "concat(%s, %s)" % (lit(pad), expr)
    return "substring(%s, sub(length(%s), %d), %d)" % (p, p, n, n)


def slot_after(parts, k):
    """k 番目の出現の直後の文字列。要素が足りなければ空文字"""
    return "if(greater(length(%s), %d), last(take(%s, %d)), '')" % (parts, k, parts, k + 1)


def slot_before(parts, k):
    """k 番目の出現の直前までの文字列。要素が足りなければ空文字"""
    return "if(greater(length(%s), %d), last(take(%s, %d)), '')" % (parts, k, parts, k)


# ---- 正規化表（指示§6。人名そのものは変えず、数字・記号・空白と定型誤記だけを直す） ----
HTML_ENTITIES = [("&gt;", ">"), ("&lt;", "<"), ("&quot;", '"'), ("&#39;", "'"),
                 ("&nbsp;", " "), ("&amp;", "&")]        # &amp; は最後（二重復元の防止）
FULLWIDTH_DIGITS = [(chr(0xFF10 + i), str(i)) for i in range(10)]
HYPHENS = [("－", "-"), ("ー", "-"), ("−", "-"), ("–", "-"),
           ("—", "-"), ("‐", "-")]
PUNCT = [("　", " "), ("：", ":"), ("，", ","), ("（", "("), ("）", ")")]
SPACE_SQUEEZE = [("    ", " "), ("   ", " "), ("  ", " ")]
TYPO_FIX = [("審審査第四部", "審査第四部"), ("特許庁審査官", "特許庁 審査官")]

THREAD_SEPARATORS = ["-----Original Message-----", "差出人:", "送信日時:",
                     "From:", "Sent:", "wrote:", "On "]

# 名前の切り出し区切り。**半角スペースは入れない**（姓名間の空白を保つため。指示§9.1）
# 装飾記号（罫線）も区切りにする。HTMLメールをテキスト化したものには
# 「＊＊＊＊…＊＊ 審査第◯部 山田太郎 審査官殿」のように、
# 注意書きの罫線と宛名が1行に潰れて入ってくることがある。
# これらの記号は日本語の人名に現れないので、区切りにしてよい。
DECORATION_MARKS = ["＊", "*", "＝", "=", "─", "━", "＿", "_", "●", "○", "■", "□",
                    "▲", "△", "※", "～", "~", "＋", "+", "＃", "#", "＄", "$",
                    "％", "%", "＆", "&", "！", "!", "？", "?", "＄", "…"]
NAME_DELIMS = ["様", "さま", "殿", "先生", "御中", "、", "。", "・", ",", ".", "(", ")",
               ":", ";", "[", "]", "【", "】", "<", ">", "\"", "/", "|", "@",
               "です", "でございます", "と申します", "宛", "各位", "-"] + DECORATION_MARKS

# 後方切り出し（役職の直前の名前を取る）だけで追加する区切り。
# 「本日は山田太郎 審査官」から「山田太郎」を取るために助詞で切る。
# 人名に含まれうる「の」も切ってしまうが、取りこぼしは他パターンが補う（docs に明記）。
BACK_DELIMS = ["は", "が", "を", "に", "へ", "と", "も", "で", "や", "の", "から", "より",
               "ます", "でした", "います", "本日", "昨日", "先日", "今回"]

# 先頭2文字が平仮名の候補は人名として採用しない。
# 日本語の姓は先頭2文字が平仮名にならないという字種の規則を使う。
# 後方切り出しが助詞で切っても「加えて○○」「として○○」のように動詞・接続語が残るため、
# 長さや区切りだけでは弾けない。字種で判定するのが構造的な対策。
# 先頭2文字だけを見るので「井上さゆり」のように名が平仮名の人名は残せる。
HIRAGANA = [chr(c) for c in range(0x3041, 0x3097)]

# 例外: **全体がひらがな**の候補は人名として受け入れる（補助資料 PATTERN 12「ひらがな姓」）。
# 上の規則を素直に適用すると「さとう 審査官殿」を落としてしまうため。
# 誤検出の元だった「加えて米倉」「にご対応いただき」は**漢字混じり**なので、
# 「全体がひらがな」という条件だけで従来どおり弾ける。字種で切り分けられるのが要点。
# さらに次の2つで絞る:
#   - 下の機能語（助詞・挨拶・動詞）を含まないこと
#   - 役職語・ラベル・自己紹介が隣接するパターン（T/R/N/L/I）であること。
#     部署宛名パターン D（基礎点45・「様」の直前）は手掛かりが弱すぎるので対象外
HIRAGANA_STOPWORDS = ["ました", "います", "ください", "よろしく", "ありがとう", "お世話",
                      "いただき", "ございます", "ですが", "につき", "および", "または",
                      "こちら", "そちら", "および", "なお", "また", "ため", "こと", "もの",
                      "ところ", "とおり", "ほど", "から", "まで", "より", "など", "ので",
                      "です", "ます", "する", "した", "して", "ある", "いる", "おり"]
# ひらがな名として認めるパターン（D は除く。上のコメント参照）
HIRAGANA_OK_PATTERNS = ("T", "R", "N", "L", "I", "S")

# 候補名から取り除く語（敬称・役職・組織名を含めない。指示§9.1）
CLEAN_STRIP = ["審査官補", "審査官", "担当", "特許庁", "審査第四部", "審査第一部", "審査第二部",
               "審査第三部", "伝送システム", "移動体通信システム", "様", "さま", "殿", "先生",
               "株式会社", "特許事務所", "法律事務所", "弁理士法人", "知的財産法務本部", "の"]

# 組織名のアンカー。この直後には「特許庁 中野」「特許庁の中野です」のように
# **姓だけ**が書かれることが多い。ここから採った姓は**スコアには参加させず**、
# 空白の無い氏名をどこで切るかを決めるためだけに使う（推測で切らないため）。
ORG_ANCHORS = ["特許庁", "審査第一部", "審査第二部", "審査第三部", "審査第四部",
               "伝送システム", "移動体通信システム"]

# **3文字の姓**だけを列挙した表。姓名の切れ目を決めるときの根拠の1つとして使う。
# 2文字の姓は入れない——「長谷部」を「長谷／部」と切ってしまうため。
# 4文字ちょうどの氏名は根拠が無ければ 2＋2 で切るので、
# その既定を上書きする必要があるのは3文字姓だけ。
KNOWN_SURNAMES_3 = ["佐々木", "長谷川", "五十嵐", "小笠原", "宇都宮", "久保田", "大和田",
                    "小野寺", "佐久間", "阿久津", "長谷部", "日下部", "東海林", "御手洗",
                    "我孫子", "海老原", "大河原", "宇佐美", "小田切", "百合草"]

# 残っていたら人名として認めない語
EXCLUDED_NAME_WORDS = ["弁理士", "代理人", "出願人", "発明者", "担当者", "御中", "各位",
                       "事務所", "法人", "部長", "課長", "係", "会社", "部", "陪席", "同席"]

EXTERNAL_PARTY_WORDS = ["弁理士", "代理人", "出願人", "発明者", "株式会社",
                        "特許事務所", "法律事務所", "弁理士法人"]
PARTICIPANT_WORDS = ["参加者", "出席者", "同席"]
CC_WORDS = ["Cc:", "CC:", "cc:"]
ATTENDING_WORDS = ["陪席"]

# **名前の直前12文字**にこれらがあれば候補ごと除外する（主担当審査官ではないため）。
# 減点だけだと「候補がそれしか無い」場合に採用されてしまう（テスト X01〜X04 で検出）。
# 判定を直前12文字に限るのは、主担当の後に陪席が書かれているだけで
# 主担当まで除外しないため（テスト E07）。
NEAR_EXCLUDE_WORDS = (ATTENDING_WORDS + PARTICIPANT_WORDS + CC_WORDS
                      + ["弁理士", "代理人", "出願人", "発明者", "事務所", "法人", "株式会社"])

det_seq = []


def det(name, expr):
    det_seq.append((name, compose(expr)))
    return name


def det_obj(name, obj):
    det_seq.append((name, compose(obj)))
    return name


# -------------------------------------------------------------------------
# 1. 正規化
# -------------------------------------------------------------------------
_b = "variables('varItemBodyText')"
det("Compose_Det_Body_N1", "@" + rep_expr(rep_expr(rep_lit(_b, HTML_ENTITIES), CR, ""), TAB, " "))
det("Compose_Det_Body_N2", "@" + rep_lit(out("Compose_Det_Body_N1"),
                                         FULLWIDTH_DIGITS + HYPHENS + PUNCT))
det("Compose_Det_Body_Norm", "@" + rep_lit(out("Compose_Det_Body_N2"), SPACE_SQUEEZE + TYPO_FIX))
det("Compose_Det_Subject_Norm",
    "@" + rep_lit(rep_lit("outputs('Compose_Subject')", HTML_ENTITIES),
                  FULLWIDTH_DIGITS + HYPHENS + PUNCT + SPACE_SQUEEZE))

BODY = out("Compose_Det_Body_Norm")
SUBJ = out("Compose_Det_Subject_Norm")

# -------------------------------------------------------------------------
# 2. スレッド分割（二値：現在／引用）
#    区切り語の直前にセンチネルを差し込み、最初のセクション＝現在のメール本文とする。
#    候補が現在パートに属するかは「そのパターンの出現数が現在パート内で何件か」で判定する。
# -------------------------------------------------------------------------
det("Compose_Det_Marked", "@" + rep_lit(BODY, [(s, SENT + s) for s in THREAD_SEPARATORS]))
det("Compose_Det_Current", "@first(split(%s, %s))" % (out("Compose_Det_Marked"), lit(SENT)))
# 現在＋直前の引用（＝先頭2区画）。深度を3段階
#   0 現在のメッセージ / 1 直前の引用 / 2 さらに古い引用
# に分けるために使う（補助資料§3.3）。
# 区画そのものを配列として持ち回ることはできない（ループが無い）ので、
# 「アンカーのk番目の出現が、どの範囲までに収まっているか」で深度を決める。
det("Compose_Det_Through1",
    "@join(take(split(%s, %s), 2), '')" % (out("Compose_Det_Marked"), lit(SENT)))
CUR = out("Compose_Det_Current")
TH1 = out("Compose_Det_Through1")


def depth_tier(k, cur_occ, th1_occ):
    """k番目の出現の深度段階。0=現在 / 1=直前の引用 / 2=さらに古い引用"""
    return ("if(lessOrEquals(%d, %s), 0, if(lessOrEquals(%d, %s), 1, 2))"
            % (k, cur_occ, k, th1_occ))


def depth_score(tier_expr, table):
    return ("if(equals(%s, 0), %d, if(equals(%s, 1), %d, %d))"
            % (tier_expr, table["current"], tier_expr, table["quote1"], table["quote2"]))

# -------------------------------------------------------------------------
# 3. 出願番号（指示§8）
# -------------------------------------------------------------------------
det("Compose_App_Parts", "@split(%s, '特願')" % BODY)
det("Compose_App_CurOcc", "@sub(length(split(%s, '特願')), 1)" % CUR)
det("Compose_App_Th1Occ", "@sub(length(split(%s, '特願')), 1)" % TH1)
APARTS = out("Compose_App_Parts")


def app_candidate(sfx, tail_expr, prev_expr, ctx_override, base_score, tier_expr):
    """出願番号候補を4つの Compose で作る（Padded / Number / Ctx / Cand）"""
    depth_expr = depth_score(tier_expr, APP_SCORES)
    pad = det("Compose_App_Padded" + sfx,
              "@concat(%s, %s)" % (rep_lit("take(%s, 24)" % tail_expr, [(" ", ""), (",", "")]),
                                   lit(PAD16)))
    c12 = "substring(%s, 0, 12)" % out(pad)
    c11 = "substring(%s, 0, 11)" % out(pad)
    c10 = "substring(%s, 0, 10)" % out(pad)
    # 6桁: 11文字が「4桁+ハイフン+6桁」かつ 12文字目が数字でないこと（7桁以上を弾く）
    # 5桁: 10文字が「4桁+ハイフン+5桁」かつ 11文字目が数字でないこと
    # 黙って先頭6桁を切り取らない（指示§10「明らかに形式不正な候補は登録しない」）
    ok6 = "and(equals(%s, '-'), not(equals(%s, '-')))" % (digits_removed(c11), digits_removed(c12))
    ok5 = "and(equals(%s, '-'), not(equals(%s, '-')))" % (digits_removed(c10), digits_removed(c11))
    num = det("Compose_App_Number" + sfx,
              "@if(%s, %s, if(%s, %s, ''))" % (ok6, c11, ok5, c10))
    if ctx_override:
        ctx = det("Compose_App_Ctx" + sfx, "@" + ctx_override)
    else:
        ctx = det("Compose_App_Ctx" + sfx,
                  "@concat(%s, take(%s, 64))" % (tail_last(prev_expr, 64, PAD64), tail_expr))
    # 一貫性ボーナス（GROUP BY の代替。同じ番号が本文に何回出るかで加点）
    cmax = APP_SCORES["consistency_max"]
    safe = "if(empty(%s), 'ZZNOTFOUNDZZ', %s)" % (out(num), out(num))
    occ = "sub(length(split(%s, %s)), 1)" % (BODY, safe)
    bonus = ("if(greaterOrEquals(%s, 5), %d, if(equals(%s, 4), %d,"
             " if(equals(%s, 3), %d, if(equals(%s, 2), %d, 0))))"
             % (occ, cmax, occ, cmax * 3 // 4, occ, cmax // 2, occ, cmax // 4))
    score = ("add(add(add(add(add(%d, %s), if(contains(%s, '出願番号'), %d, 0)),"
             " if(%s, %d, 0)), if(%s, %d, 0)), %s)"
             % (base_score, depth_expr, out(ctx), APP_SCORES["label"],
                or_contains(out(ctx), ["案件", "標記", "表題", "本件"]), APP_SCORES["topic"],
                or_contains(out(ctx), ["別件", "誤り", "誤送信"]), APP_SCORES["other_case"],
                bonus))
    # 採用根拠の内訳。なぜこの番号が勝ったかを実行履歴から追えるようにする（資料§3.4）。
    ev = ("concat('base=%d;', 'section=', string(%s), ';depth=', string(%s),"
          " if(contains(%s, '出願番号'), ';label', ''),"
          " if(%s, ';topic', ''), if(%s, ';other-case', ''), ';consistency=', string(%s))"
          % (base_score, tier_expr, depth_expr, out(ctx),
             or_contains(out(ctx), ["案件", "標記", "表題", "本件"]),
             or_contains(out(ctx), ["別件", "誤り", "誤送信"]), bonus))
    # ソートキー。SORT_OFFSET で必ず5桁に揃える（桁数が揃わないと文字列比較が逆転する）。
    # 同点時は**浅い区画（現在＞引用）を優先**する。sort の安定性に頼らず順序を決める。
    key = "concat(string(add(%s, %d)), string(sub(2, %s)))" % (score, SORT_OFFSET, tier_expr)
    det_obj("Compose_App_Cand" + sfx, {
        "n": "@" + out(num), "s": "@" + score, "k": "@" + key, "t": "@" + tier_expr,
        "b": "@" + ev, "m": "@concat('特願', %s)" % out(num), "d": "@" + depth_expr})
    return "Compose_App_Cand" + sfx


app_cands = []
for k in range(1, APP_SLOTS + 1):
    app_cands.append(app_candidate(
        "_B%d" % k, slot_after(APARTS, k), slot_before(APARTS, k), None, APP_SCORES["base"],
        depth_tier(k, out("Compose_App_CurOcc"), out("Compose_App_Th1Occ"))))

# 件名の出願番号は強く優先する（補助資料 決定規則12・§3.1）。件名は常に深度0。
det("Compose_App_SubjParts", "@split(%s, '特願')" % SUBJ)
app_cands.append(app_candidate(
    "_S1", slot_after(out("Compose_App_SubjParts"), 1), "''", SUBJ,
    APP_SCORES["base"] + APP_SCORES["subject"], "0"))

det("Compose_App_All", "@createArray(%s)" % ", ".join(out(n) for n in app_cands))
det_seq.append(("Filter_App_Valid",
                query("@" + out("Compose_App_All"), "@not(equals(item()?['n'], ''))")))
det("Compose_App_Best",
    "@if(equals(length(body('Filter_App_Valid')), 0), json('{}'),"
    " first(reverse(sort(body('Filter_App_Valid'), 'k'))))")
det("Compose_App_Final", "@trim(string(coalesce(%s?['n'], '')))" % out("Compose_App_Best"))
APP_SCORE = "int(coalesce(%s?['s'], 0))" % out("Compose_App_Best")
# 第2候補との差。差が小さければ「どちらの案件か決められない」＝要確認にする
det("Compose_App_Ranked", "@reverse(sort(body('Filter_App_Valid'), 'k'))")
det("Compose_App_Second",
    "@if(greater(length(body('Filter_App_Valid')), 1), last(take(%s, 2)), json('{}'))"
    % out("Compose_App_Ranked"))
det("Compose_App_ScoreDiff",
    "@if(empty(%s), 0, if(lessOrEquals(length(body('Filter_App_Valid')), 1), 999,"
    " sub(%s, int(coalesce(%s?['s'], 0)))))"
    % (out("Compose_App_Final"), APP_SCORE, out("Compose_App_Second")))

# -------------------------------------------------------------------------
# 4. 審査官名（指示§9）
#    5パターン × 3スロット ＋ 件名ラベル1件。各候補 3 Compose（Name / Ctx / Cand）。
# -------------------------------------------------------------------------
det("Compose_Ex_MarkRole", "@" + rep_lit(BODY, [("審査官補", MK_ROLE), ("審査官", MK_ROLE)]))
det("Compose_Ex_MarkTan", "@" + rep_lit(BODY, [("担当審査官:", MK_TAN)]))
det("Compose_Ex_MarkLbl", "@" + rep_lit(BODY, [("担当審査官:", "担当審査官:"),
                                               ("審査官:", MK_LBL), ("ご担当者:", MK_LBL)]))
det("Compose_Ex_MarkInt", "@" + rep_lit(BODY, [("特許庁の", MK_INT), ("伝送システムの", MK_INT)]))
det("Compose_Ex_CurRole", "@" + rep_lit(CUR, [("審査官補", MK_ROLE), ("審査官", MK_ROLE)]))
det("Compose_Ex_CurTan", "@" + rep_lit(CUR, [("担当審査官:", MK_TAN)]))
det("Compose_Ex_CurLbl", "@" + rep_lit(CUR, [("担当審査官:", "担当審査官:"),
                                             ("審査官:", MK_LBL), ("ご担当者:", MK_LBL)]))
det("Compose_Ex_CurInt", "@" + rep_lit(CUR, [("特許庁の", MK_INT), ("伝送システムの", MK_INT)]))

# (パターンID, 基礎点, 方向, 分割対象の式, 現在パート出現数, 現在＋直前引用の出現数)
# アンカーの置換規則。Th1（現在＋直前の引用）側は Compose を増やさないよう、
# 置換を数え上げの式に直接埋め込む（TH1 は短い参照なので式長に効かない）。
EX_ANCHOR_REPL = {
    MK_TAN: [("担当審査官:", MK_TAN)],
    MK_ROLE: [("審査官補", MK_ROLE), ("審査官", MK_ROLE)],
    MK_LBL: [("担当審査官:", "担当審査官:"), ("審査官:", MK_LBL), ("ご担当者:", MK_LBL)],
    MK_INT: [("特許庁の", MK_INT), ("伝送システムの", MK_INT)],
}
EX_PATTERNS = []
for pid, base, direction, marked, curmarked, mark in (
        ("T", 100, "f", "Compose_Ex_MarkTan", "Compose_Ex_CurTan", MK_TAN),
        ("R", 80, "f", "Compose_Ex_MarkRole", "Compose_Ex_CurRole", MK_ROLE),
        ("N", 75, "b", "Compose_Ex_MarkRole", "Compose_Ex_CurRole", MK_ROLE),
        ("L", 60, "f", "Compose_Ex_MarkLbl", "Compose_Ex_CurLbl", MK_LBL),
        ("I", 55, "f", "Compose_Ex_MarkInt", "Compose_Ex_CurInt", MK_INT),
        ("D", 45, "b", None, None, "様")):
    th1_src = rep_lit(TH1, EX_ANCHOR_REPL[mark]) if mark in EX_ANCHOR_REPL else TH1
    if marked:
        pn = det("Compose_Ex_Parts" + pid, "@split(%s, %s)" % (out(marked), lit(mark)))
        cn = det("Compose_Ex_CurOcc" + pid,
                 "@sub(length(split(%s, %s)), 1)" % (out(curmarked), lit(mark)))
    else:
        pn = det("Compose_Ex_Parts" + pid, "@split(%s, %s)" % (BODY, lit(mark)))
        cn = det("Compose_Ex_CurOcc" + pid, "@sub(length(split(%s, %s)), 1)" % (CUR, lit(mark)))
    tn = det("Compose_Ex_Th1Occ" + pid,
             "@sub(length(split(%s, %s)), 1)" % (th1_src, lit(mark)))
    EX_PATTERNS.append((pid, base, direction, out(pn), out(cn), out(tn)))


def cut_forward(expr):
    e = rep_lit("take(%s, 24)" % expr, [(d, NCUT) for d in NAME_DELIMS])
    e = rep_expr(rep_expr(e, LF, NCUT), TAB, NCUT)
    return "first(split(%s, %s))" % (e, lit(NCUT))


def cut_backward(expr):
    e = rep_lit(tail_last(expr, 24, PAD24),
                [(d, NCUT) for d in NAME_DELIMS + BACK_DELIMS])
    e = rep_expr(rep_expr(e, LF, NCUT), TAB, NCUT)
    return "last(split(%s, %s))" % (e, lit(NCUT))


def clean_name(expr):
    return "trim(%s)" % rep_lit(expr, [(w, "") for w in CLEAN_STRIP])


def name_tail(ref):
    """空白区切りの**末尾**から人名を取り出す。`ref` は短い参照式であること。

    切り出した文字列には、除去しきれない組織名が前に残る:
        「＊＊＊＊＊＊ 審査第◯部◯◯◯ 山田太郎」  → 山田太郎
        「◯◯◯◯ 審査第◯部◯◯◯ 山中 実」        → 山中 実
    CLEAN_STRIP は既知の組織名しか消せず、部署の実名は消せない。
    そこで**構造**で決める。人名は空白区切りの末尾1〜2トークンで、それより前は組織名。

      - 末尾トークンが4文字以上 → それ自体が氏名（前のトークンは組織名）
      - 末尾トークンが1〜3文字 → 名の可能性がある。直前トークンが2〜3文字で
        平仮名始まりでなければ姓とみなして結合する

    直前トークンに2〜3文字を要求するのが要点。日本語の姓はこの長さに収まるが、
    部署名（「医療機器」「審査第◯部◯◯」など）はまず収まらない。

    `ref` を8回展開するため、**切り出し式そのものを渡してはいけない**
    （1式8,192文字を超える）。Compose に一度落としてから参照する。
    """
    a = "reverse(take(reverse(split(trim(%s), %s)), 2))" % (ref, lit(" "))
    prev, tail = "first(%s)" % a, "last(%s)" % a
    kana = ", ".join(lit(h) for h in HIRAGANA)
    joinable = ("and(and(greater(length(%s), 1), lessOrEquals(length(%s), 3)),"
                " and(and(greaterOrEquals(length(%s), 2), lessOrEquals(length(%s), 3)),"
                " not(contains(createArray(%s), take(%s, 1)))))"
                % (a, tail, prev, prev, kana, prev))
    return "if(%s, concat(%s, %s, %s), %s)" % (joinable, prev, lit(" "), tail, tail)


def ex_candidate(sfx, base, name_expr, ctx_expr, tier_expr, near_expr,
                 fore_expr=None, extra=0, pid="S"):
    """審査官候補を3つの Compose で作る（Ctx / Name / Cand）。

    near_expr は「名前の直前12文字」。陪席・同席・Cc の判定はこの近傍だけで行う。
    後方64文字まで見ると、主担当のあとに陪席審査官が書かれているだけで
    主担当まで除外されてしまう（テスト E07 で検出した不具合）。
    """
    if fore_expr is None:
        fore_expr = lit("")
    depth_expr = depth_score(tier_expr, EX_SCORES)
    # 文脈・近傍・切り出し原文を**1つのオブジェクト**にまとめる。
    # 以前はそれぞれを式として持ち回っていたが、near_expr は or_contains で16回、
    # ctx_expr は3回展開されるため、1式が 6,890 文字まで膨らんでいた。
    # オブジェクトのキー参照にすれば1参照40文字程度で済む。
    det_obj("Compose_Ex_Ctx" + sfx, {
        "c": "@" + ctx_expr, "n": "@" + near_expr, "f": "@" + fore_expr,
        "r": "@" + clean_name(name_expr)})
    cx = out("Compose_Ex_Ctx" + sfx)
    C, near_expr, fore_expr = cx + "?['c']", cx + "?['n']", cx + "?['f']"
    nm = det("Compose_Ex_Name" + sfx, "@" + name_tail(cx + "?['r']"))
    N = out(nm)
    kana = ", ".join(lit(h) for h in HIRAGANA)
    head1 = "take(%s, 1)" % N
    # 2文字目は「先頭2文字から先頭1文字を除いたもの」で取る（substring を使わずに済む）
    head2 = "replace(take(%s, 2), take(%s, 1), %s)" % (N, N, lit(""))
    all_kana = all_hiragana(N)
    if pid in HIRAGANA_OK_PATTERNS:
        # 補助資料 PATTERN 12。役職語・ラベル・自己紹介が隣接するパターンでのみ、
        # 「全体がひらがな・2〜6文字・機能語を含まない」候補を人名として認める。
        hira_ok = ("and(and(%s, and(greaterOrEquals(length(%s), 2),"
                   " lessOrEquals(length(%s), 6))), not(%s))"
                   % (all_kana, N, N, or_contains(N, HIRAGANA_STOPWORDS)))
    else:
        hira_ok = "false"
    # 先頭2文字が平仮名なら人名としない。ただし上の hira_ok を満たすものは通す。
    head_ok = ("or(and(not(contains(createArray(%s), %s)),"
               " not(contains(createArray(%s), %s))), %s)"
               % (kana, head1, kana, head2, hira_ok))
    valid = ("and(and(and(greater(length(%s), 1), lessOrEquals(length(%s), 12)),"
             " and(equals(%s, %s), not(%s))), %s)"
             % (N, N, digits_removed(N), N, or_contains(N, EXCLUDED_NAME_WORDS), head_ok))

    # --- 加減点（すべて EX_SCORES から取る。式の中に即値を書かない） ---
    s = EX_SCORES
    head_near = "contains(take(%s, 200), %s)" % (CUR, N)          # 冒頭の宛名付近
    jpo_near = or_contains(fore_expr, ORG_ANCHORS)                # 特許庁／部署名に近接
    honor = or_contains(C, ["様", "殿", "先生"])
    ext = or_contains(fore_expr, EXTERNAL_PARTY_WORDS)
    ccw = or_contains(near_expr, CC_WORDS)
    ptc = or_contains(near_expr, PARTICIPANT_WORDS)
    # 採用した出願番号と同じ区画にいるか（資料の「同じ email section」）。
    # Compose_App_Best は審査官セクションより前で確定しているのでそのまま参照できる。
    same_sec = ("and(not(empty(%s)), equals(%s, int(coalesce(%s?['t'], 9))))"
                % (out("Compose_App_Final"), tier_expr, out("Compose_App_Best")))
    # 同じ氏名が本文に2回以上出るか（資料の「繰り返し出現」）。
    safe_n = "if(equals(%s, %s), 'ZZNOTFOUNDZZ', %s)" % (N, lit(""), N)
    repeated = "greaterOrEquals(sub(length(split(%s, %s)), 1), 2)" % (BODY, safe_n)
    terms = [
        ("%d" % (base + extra), None, "base"),
        (depth_expr, None, "depth"),
        ("if(contains(%s, '担当審査官'), %d, 0)" % (C, s["tantou"]),
         "contains(%s, '担当審査官')" % C, "tantou"),
        ("if(contains(%s, 'ご担当'), %d, 0)" % (C, s["gotantou"]),
         "contains(%s, 'ご担当')" % C, "gotantou"),
        ("if(%s, %d, 0)" % (honor, s["honorific"]), honor, "honorific"),
        ("if(%s, %d, 0)" % (head_near, s["head"]), head_near, "head"),
        ("if(%s, %d, 0)" % (jpo_near, s["jpo_near"]), jpo_near, "jpo-near"),
        ("if(%s, %d, 0)" % (same_sec, s["same_section"]), same_sec, "same-section"),
        ("if(%s, %d, 0)" % (repeated, s["repeated"]), repeated, "repeated"),
        ("if(%s, %d, 0)" % (all_kana, s["hiragana"]), all_kana, "hiragana"),
        ("if(%s, %d, 0)" % (ext, s["external"]), ext, "external"),
        ("if(%s, %d, 0)" % (ccw, s["cc"]), ccw, "cc"),
        ("if(%s, %d, 0)" % (ptc, s["participant"]), ptc, "participant"),
    ]
    score = terms[0][0]
    for t, _cond, _label in terms[1:]:
        score = "add(%s, %s)" % (score, t)
    # 採用根拠の内訳。どの項目が効いたかを実行履歴から追える（資料§3.4）。
    ev = "concat(%s, ';section=', string(%s))" % (
        lit("p=%s;base=%d" % (pid, base + extra)), tier_expr)
    for _t, cond, label in terms[2:]:
        ev = "concat(%s, if(%s, %s, %s))" % (ev, cond, lit(";" + label), lit(""))
    near_excluded = or_contains(near_expr, NEAR_EXCLUDE_WORDS)
    # ソートキー。SORT_OFFSET で必ず5桁に揃える（桁数が揃わないと文字列比較が逆転する）。
    # 続けて**パターン優先度**と**浅い区画優先**を連結し、同点でも順序が決まるようにする
    # （実機の sort の安定性に依存させない。補助資料には同点規則が無いので新設）。
    key = ("concat(string(add(%s, %d)), '%d', string(sub(2, %s)))"
           % (score, SORT_OFFSET, EX_PATTERN_RANK.get(pid, 0), tier_expr))
    det_obj("Compose_Ex_Cand" + sfx, {
        "n": "@" + N, "s": "@" + score, "k": "@" + key, "p": sfx, "b": "@" + ev,
        "v": "@and(%s, not(%s))" % (valid, near_excluded),
        "h": "@" + all_kana, "t": "@" + tier_expr, "d": "@" + depth_expr})
    return "Compose_Ex_Cand" + sfx


ex_cands = []
for pid, base, direction, parts, curocc, th1occ in EX_PATTERNS:
    for k in range(1, EX_SLOTS[pid] + 1):
        sfx = "_%s%d" % (pid, k)
        tier = depth_tier(k, curocc, th1occ)
        if direction == "f":
            after, before = slot_after(parts, k), slot_before(parts, k)
            name = cut_forward(after)
        else:
            after, before = slot_after(parts, k), slot_before(parts, k)
            name = cut_backward(before)
        ctx = "concat(%s, take(%s, 64))" % (tail_last(before, 64, PAD64), after)
        near = tail_last(before, 12, PAD24)     # 名前の直前12文字（陪席・Ccの除外に使う）
        # 名前の直前24文字。修飾語（弁理士・特許事務所など）は名前の前に来るため、
        # 外部関係者の減点はこの範囲だけで見る。後方の署名で審査官を減点しない。
        fore = tail_last(before, 24, PAD24)
        ex_cands.append(ex_candidate(sfx, base, name, ctx, tier, near, fore, pid=pid))

# 件名のラベル候補（指示§9.2「件名に記載されている」）。件名は常に深度0。
det("Compose_Ex_SubjLbl", "@" + rep_lit(SUBJ, [("担当審査官:", MK_LBL), ("審査官:", MK_LBL)]))
det("Compose_Ex_SubjParts", "@split(%s, %s)" % (out("Compose_Ex_SubjLbl"), lit(MK_LBL)))
ex_cands.append(ex_candidate(
    "_S1", 60, cut_forward(slot_after(out("Compose_Ex_SubjParts"), 1)), SUBJ, "0",
    lit(""), extra=60, pid="S"))

det("Compose_Ex_All", "@createArray(%s)" % ", ".join(out(n) for n in ex_cands))
det_seq.append(("Filter_Ex_Valid",
                query("@" + out("Compose_Ex_All"), "@equals(item()?['v'], true)")))
det("Compose_Ex_Ranked", "@reverse(sort(body('Filter_Ex_Valid'), 'k'))")
det("Compose_Ex_Best",
    "@if(equals(length(body('Filter_Ex_Valid')), 0), json('{}'), first(%s))"
    % out("Compose_Ex_Ranked"))
det("Compose_Ex_Second",
    "@if(greater(length(body('Filter_Ex_Valid')), 1), last(take(%s, 2)), json('{}'))"
    % out("Compose_Ex_Ranked"))
BEST_NAME = "trim(string(coalesce(%s?['n'], '')))" % out("Compose_Ex_Best")
det("Compose_Ex_BestName", "@" + BEST_NAME)

# -------------------------------------------------------------------------
# 組織名アンカーから採る名前（スコアには参加させない）
#
# 「特許庁審査第◯部◯◯◯　青木　健」のように、**敬称も役職も付かない署名**は
# どのパターンのアンカーにも掛からない。しかしここには姓名が揃って書かれている。
# ここから採った名前は、姓のみ→フルネーム補完と、姓名の切れ目の判断に使う。
# -------------------------------------------------------------------------
det("Compose_Ex_OrgParts",
    "@split(%s, %s)" % (rep_lit(BODY, [(w, MK_ORG) for w in ORG_ANCHORS]), lit(MK_ORG)))
_org = out("Compose_Ex_OrgParts")
# 先頭2件と**末尾2件**を見る。宛名は本文の先頭に、署名は末尾に置かれるため、
# 出現の中央だけを見ても取りこぼす（長い引用スレッドでは組織名が8回以上出る）。
# アンカーが1つも無いときは空にする（本文冒頭を名前として拾わないため）。
_org_slots = (slot_after(_org, 1), slot_after(_org, 2),
              "if(greater(length(%s), 2), last(take(%s, sub(length(%s), 1))), %s)"
              % (_org, _org, _org, lit("")),
              "if(greater(length(%s), 1), last(%s), %s)" % (_org, _org, lit("")))
# 4件ぶんの切り出しを**1つの配列**に入れる。Compose を4つに分けると
# アクション数の上限（500）に届いてしまうため。
# 組織名の直後が改行のことがある（特許庁＼n審査第◯部＼n姓）。
# cut_forward は先頭から区切りまでを採るので、先に trim しないと空になる。
det("Compose_Ex_FamRaw", "@createArray(%s)"
    % ", ".join(clean_name(cut_forward("trim(%s)" % s)) for s in _org_slots))
for _i in range(1, len(_org_slots) + 1):
    det_obj("Compose_Ex_Fam%d" % _i,
            {"n": "@" + name_tail("last(take(%s, %d))" % (out("Compose_Ex_FamRaw"), _i))})
det("Compose_Ex_FamPool",
    "@union(body('Filter_Ex_Valid'), createArray(%s))"
    % ", ".join(out("Compose_Ex_Fam%d" % i) for i in range(1, len(_org_slots) + 1)))

# 姓のみ→フルネーム補完（指示§9.3。ちょうど1件のときだけ補完する）
# 候補は Filter_Ex_Valid だけでなく**組織名アンカー由来の名前も含める**。
# 妥当性検査を通っていない名前が混ざるので、ここで長さと数字を確認する。
# 最良候補が空のときに補完してしまわないよう、長さ0を明示的に弾く。
det_seq.append(("Filter_Ex_Completion", query(
    "@" + out("Compose_Ex_FamPool"),
    "@and(and(greater(length(%s), 0), startsWith(item()?['n'], %s)),"
    " and(greater(length(item()?['n']), length(%s)),"
    " and(lessOrEquals(length(item()?['n']), 12), equals(%s, item()?['n']))))"
    % (out("Compose_Ex_BestName"), out("Compose_Ex_BestName"),
       out("Compose_Ex_BestName"), digits_removed("item()?['n']")))))
# 「フルネーム候補がちょうど1件」は**候補の行数**ではなく**異なる名前が1種類**で判定する。
# 同じ名前を複数のパターンが拾うのは普通に起きるため（テスト F01 で検出した不具合）。
# 名前で並べ替えて先頭と末尾が一致すれば、名前は1種類だけと言える。
det("Compose_Ex_CompletionSorted", "@sort(body('Filter_Ex_Completion'), 'n')")
det("Compose_Ex_Completed",
    "@trim(string(coalesce(if(and(and(greater(length(%s), 0),"
    " equals(first(%s)?['n'], last(%s)?['n'])),"
    " lessOrEquals(length(%s), 3)), first(%s)?['n'], %s), '')))"
    % (out("Compose_Ex_CompletionSorted"), out("Compose_Ex_CompletionSorted"),
       out("Compose_Ex_CompletionSorted"), out("Compose_Ex_BestName"),
       out("Compose_Ex_CompletionSorted"), out("Compose_Ex_BestName")))

# -------------------------------------------------------------------------
# 姓名の間の半角スペース（利用者決定 2026-08-04）
#
# **推測では切らない。** 「日本の姓は2文字」といった決め打ちをすると
# 佐々木・長谷川のような3文字姓を必ず誤分割する。
# 代わりに、切れ目の根拠を**同じスレッドの中の実データ**からだけ採る。
#
#   規則A: 既に空白があるならそのまま（正規化済みなので半角1個）
#   規則B: 空白除去形が一致する**空白付きの候補**がスレッド内にちょうど1種類あれば
#          そちらを採用する（例: 引用部に「吉村 真治郎」がある）
#   規則C: その氏名の**接頭辞になっている姓**がちょうど1種類あればそこで切る。
#          姓は「組織名アンカーの直後」「有効候補」「既知の3文字姓」から採る
#   規則D: 根拠が無くても**4文字ちょうど**なら 2＋2 で切る（日本語の氏名の大多数）
#   規則E: 5文字以上で根拠が無ければ切らない
#
# 規則Cの候補が2種類以上あるときは規則Dへ落ちる（曖昧な根拠は使わない）。
# -------------------------------------------------------------------------
EX_KEY = out("Compose_Ex_CompletedKey")
det("Compose_Ex_CompletedKey",
    "@replace(%s, %s, %s)" % (out("Compose_Ex_Completed"), lit(" "), lit("")))

# 規則B: 空白付きの同一人物表記
det_seq.append(("Filter_Ex_Variant", query(
    "@body('Filter_Ex_Valid')",
    "@and(contains(item()?['n'], %s), equals(replace(item()?['n'], %s, %s), %s))"
    % (lit(" "), lit(" "), lit(""), EX_KEY))))
det("Compose_Ex_Variant",
    "@if(and(greater(length(body('Filter_Ex_Variant')), 0),"
    " equals(first(sort(body('Filter_Ex_Variant'), 'n'))?['n'],"
    " last(sort(body('Filter_Ex_Variant'), 'n'))?['n'])),"
    " first(sort(body('Filter_Ex_Variant'), 'n'))?['n'], %s)" % lit(""))

# 規則C: 姓の候補プール＝組織名アンカー由来の名前＋有効候補＋既知の3文字姓
_n = "item()?['n']"
_kana = ", ".join(lit(h) for h in HIRAGANA)
# 姓として採るのは 2〜4 文字・数字なし・空白なし・先頭2文字が平仮名でない語で、
# かつ対象の氏名の**真の接頭辞**であること。
# 1文字姓（林・原など）を採らないのは、1文字の一致は偶然でも起こりうるため
# （切らなければ現状維持で済むが、誤って切ると誤った氏名を保存してしまう）。
# 除外語（弁理士・部長など）の検査は不要。接頭辞の元である最良候補が既に検査済みで、
# その接頭辞が除外語を含むことはありえない。
det_seq.append(("Filter_Ex_Prefix", query(
    "@union(%s, createArray(%s))"
    % (out("Compose_Ex_FamPool"),
       ", ".join("json('{\"n\":\"%s\"}')" % s for s in KNOWN_SURNAMES_3)),
    "@and(and(and(greaterOrEquals(length(%s), 2), lessOrEquals(length(%s), 4)),"
    " and(startsWith(%s, %s), less(length(%s), length(%s)))),"
    " and(and(equals(%s, %s), not(contains(%s, %s))),"
    " and(not(contains(createArray(%s), take(%s, 1))),"
    " not(contains(createArray(%s), replace(take(%s, 2), take(%s, 1), %s))))))"
    % (_n, _n, EX_KEY, _n, _n, EX_KEY,
       digits_removed(_n), _n, _n, lit(" "),
       _kana, _n, _kana, _n, _n, lit("")))))
# 規則D: 根拠が無くても**4文字ちょうど**の氏名は 2＋2 で切る。
# ただし**ひらがな表記には適用しない**。「おうさか」を「おう さか」と切る根拠は無く、
# 漢字の姓名と違って2文字＋2文字という構造の裏付けも無いため
# （テスト P07 で検出。ひらがな姓を受け入れたことで初めて現れた不具合）。
# 日本語の4文字氏名は姓2＋名2が大多数で、実データでも
# 「伊東和重」「小林正明」のように空白付き表記も姓のみ表記も現れないことが多い。
# 5文字以上は 2＋3 と 3＋2 のどちらとも決められないので切らない。
# 3文字姓（佐々木健など）は KNOWN_SURNAMES_3 が規則Cで先に効くため、この既定に落ちない。
# 見つからないときはセンチネルを返す。空文字を返すと後段の split の区切りが
# 空文字になり実行時エラーになるため（if は両分岐を先に評価する）。
det("Compose_Ex_Surname",
    "@if(and(greater(length(body('Filter_Ex_Prefix')), 0),"
    " equals(first(sort(body('Filter_Ex_Prefix'), 'n'))?['n'],"
    " last(sort(body('Filter_Ex_Prefix'), 'n'))?['n'])),"
    " first(sort(body('Filter_Ex_Prefix'), 'n'))?['n'],"
    " if(and(equals(length(%s), 4), not(%s)), take(%s, 2), %s))"
    % (EX_KEY, all_hiragana(EX_KEY), EX_KEY, lit(MK_ORG)))
# 名の部分。素の replace(氏名, 姓, '') だと姓が名の中にも出るとき（例: 田中田）に
# 2箇所とも消えてしまう。センチネルを前に付けてから「センチネル＋姓」を消すことで、
# 先頭の1回だけを確実に除去する（姓は接頭辞なので必ず先頭で一致する）。
det("Compose_Ex_Given",
    "@replace(concat(%s, %s), concat(%s, %s), %s)"
    % (lit(MK_ORG), EX_KEY, lit(MK_ORG), out("Compose_Ex_Surname"), lit("")))
det("Compose_Ex_Spaced",
    "@if(greater(length(%s), length(%s)), %s,"
    " if(not(equals(%s, %s)), %s,"
    " if(equals(%s, %s), %s, concat(%s, %s, %s))))"
    % (out("Compose_Ex_Completed"), EX_KEY, out("Compose_Ex_Completed"),
       out("Compose_Ex_Variant"), lit(""), out("Compose_Ex_Variant"),
       out("Compose_Ex_Surname"), lit(MK_ORG), out("Compose_Ex_Completed"),
       out("Compose_Ex_Surname"), lit(" "), out("Compose_Ex_Given")))

det("Compose_Ex_Final", "@trim(string(coalesce(%s, '')))" % out("Compose_Ex_Spaced"))

# -------------------------------------------------------------------------
# 5. 信頼度・診断（SharePointには列を作らない。指示§10）
# -------------------------------------------------------------------------
EX_SCORE = "int(coalesce(%s?['s'], 0))" % out("Compose_Ex_Best")
EX_DIFF = ("if(equals(length(body('Filter_Ex_Valid')), 1), 999,"
           " sub(%s, int(coalesce(%s?['s'], 0))))" % (EX_SCORE, out("Compose_Ex_Second")))
det("Compose_Ex_ScoreDiff", "@if(empty(%s), 0, %s)" % (out("Compose_Ex_Final"), EX_DIFF))
det("Compose_Ex_Confidence",
    "@if(empty(%s), 'Not Found', if(less(%s, 60), 'Low',"
    " if(less(%s, 15), 'Ambiguous', if(greaterOrEquals(%s, 180), 'High', 'Medium'))))"
    % (out("Compose_Ex_Final"), EX_SCORE, out("Compose_Ex_ScoreDiff"), EX_SCORE))
det("Compose_App_Confidence",
    "@if(empty(%s), 'Not Found', if(less(%s, 15), 'Ambiguous',"
    " if(greaterOrEquals(%s, 160), 'High', if(greaterOrEquals(%s, 100), 'Medium', 'Low'))))"
    % (out("Compose_App_Final"), out("Compose_App_ScoreDiff"), APP_SCORE, APP_SCORE))
# -------------------------------------------------------------------------
# 出力データ構造（補助資料§5）。**列は7列のまま**で、ここは診断（実行履歴）に出す。
# すべて既存 Compose のキー追加なのでアクションは増えない。
# -------------------------------------------------------------------------
EXF = out("Compose_Ex_Final")
EXBEST = out("Compose_Ex_Best")
# 氏名の種別。空白を含むか4文字以上なら姓名が揃っているとみなす。
# 3文字以下は「林一郎」のような1文字姓＋2文字名も姓のみ扱いになるが、
# **要確認側に倒す**ほうが安全（静かに確定させない）。
det("Compose_Ex_NameType",
    "@if(empty(%s), 'NotFound', if(equals(coalesce(%s?['h'], false), true), 'HiraganaName',"
    " if(or(contains(%s, ' '), greaterOrEquals(length(%s), 4)),"
    " 'FullName', 'FamilyNameOnly')))" % (EXF, EXBEST, EXF, EXF))
# 姓のみ／ひらがなのまま確定できていないもの。フルネームを捏造しない（資料§4）。
det("Compose_Det_NeedsReview",
    "@or(or(or(equals(%s, 'Not Found'), equals(%s, 'Not Found')),"
    " or(equals(%s, 'Low'), equals(%s, 'Low'))), or(or(equals(%s, 'Ambiguous'),"
    " equals(%s, 'Ambiguous')),"
    " not(or(equals(%s, 'FullName'), equals(%s, 'NotFound')))))"
    % (out("Compose_Ex_Confidence"), out("Compose_App_Confidence"),
       out("Compose_Ex_Confidence"), out("Compose_App_Confidence"),
       out("Compose_Ex_Confidence"), out("Compose_App_Confidence"),
       out("Compose_Ex_NameType"), out("Compose_Ex_NameType")))
# 採用した審査官が**送信者本人**であると言える場合だけメールアドレスを載せる。
# 根拠は「現在のメッセージに『特許庁の〈姓〉です』形式の自己紹介がある」こと。
# 名簿もメンバー一覧も使わない（資料§6。同姓者を理由に人物を確定しない）。
_ex_first = "first(split(%s, %s))" % (EXF, lit(" "))
INTRO_OK = ("and(not(empty(%s)), or(contains(%s, concat('特許庁の', %s)),"
            " contains(%s, concat('伝送システムの', %s))))"
            % (EXF, CUR, _ex_first, CUR, _ex_first))
# 区画。件名由来の候補はパターン接尾辞が _S で始まる。
SRC_SECTION = ("if(empty(%s), '', if(startsWith(coalesce(%s?['p'], ''), '_S'), 'subject',"
               " if(equals(coalesce(%s?['t'], 0), 0), 'current',"
               " if(equals(coalesce(%s?['t'], 0), 1), 'quote1', 'quote2'))))"
               % (EXF, EXBEST, EXBEST, EXBEST))


# =========================================================================
# 審査官名簿との突合（Foreach_Email 直下・深さ4。コンテナを増やさない）
#
# 名簿は Scope_Load_Roster で1回だけ取得済み。ここは Query と Compose だけで、
# コネクタを呼ばない（検出と同じく、突合の失敗で同期が止まらないことを構造的に保証する）。
#
#   規則1 完全一致  空白を除いた FullName が推定名と一致
#   規則2 姓で一致  推定名が姓のみのとき LastName が一致
#   規則3 2件以上   → Ambiguous（採用しない。推定名はそのまま残す）
#   規則4 0件       → NotFound
#   規則5 推定名が空 → NoExaminer
#   規則6 名簿が読めていない → RosterUnavailable
#
# 「ちょうど1件」は**行数ではなく一意キー SyncKey の種類数**で数える。
# 名簿には一意制約が無く、同姓同名の別人も、同一人物の複数チャネル分の行も入りうる。
# =========================================================================
ROSTER_SRC = "coalesce(body('Get_Roster_Items')?['value'], json('[]'))"
_rn = "coalesce(item()?['FullName'], '')"

# 在籍者だけを対象にする（利用者決定 2026-08-04）。離脱者は行として残るため明示的に外す。
det_seq.append(("Filter_Dir_Active", query(
    "@" + ROSTER_SRC, "@equals(coalesce(item()?['IsActive'], false), true)")))

DIR_KEY = "replace(%s, %s, %s)" % (EXF, lit(" "), lit(""))
det("Compose_Dir_Key", "@" + DIR_KEY)
DK = out("Compose_Dir_Key")

# 規則1: 空白を無視した氏名の一致。名簿の FullName は半角スペース区切りに正規化済みだが、
# 推定側は空白を補えないことがあるので、両方から空白を除いて比べる。
det_seq.append(("Filter_Dir_Full", query(
    "@body('Filter_Dir_Active')",
    "@and(not(equals(%s, %s)), equals(replace(%s, %s, %s), %s))"
    % (DK, lit(""), _rn, lit(" "), lit(""), DK))))
# 規則2: 姓のみのときだけ LastName で引く。フルネームが取れているのに姓で引くと
# 同姓の別人を拾ってしまうため、NameType で明示的に絞る。
det_seq.append(("Filter_Dir_Last", query(
    "@body('Filter_Dir_Active')",
    "@and(equals(%s, 'FamilyNameOnly'), equals(coalesce(item()?['LastName'], ''), %s))"
    % (out("Compose_Ex_NameType"), EXF))))


def _one_person(filter_name):
    """その Filter の結果が**1人**に絞れているか。

    人物の同一性は氏名ではなく**名簿の一意キー SyncKey** で見る。
    名簿には一意制約が無く同姓同名が入りうるので、氏名で数えると
    「別人2名」を1人と誤認する（テスト M03 で検出）。
    逆に、同じ人物が複数チャネル分の行として入っていると行数は2以上になるが、
    SyncKey は同じなので1人として扱える。

    SyncKey が空の行が複数ある場合は同一性を確認できないので1人とみなさない。
    """
    s = "sort(body('%s'), 'SyncKey')" % filter_name
    return ("and(greater(length(body('%s')), 0),"
            " or(equals(length(body('%s')), 1),"
            " and(not(equals(coalesce(first(%s)?['SyncKey'], %s), %s)),"
            " equals(first(%s)?['SyncKey'], last(%s)?['SyncKey']))))"
            % (filter_name, filter_name, s, lit(""), lit(""), s, s))


DIR_FULL_ONE = _one_person("Filter_Dir_Full")
DIR_LAST_ONE = _one_person("Filter_Dir_Last")
# 採用する行。規則1を優先し、無ければ規則2。どちらも決まらなければ空オブジェクト。
det("Compose_Dir_Row",
    "@if(%s, first(sort(body('Filter_Dir_Full'), 'SyncKey')),"
    " if(%s, first(sort(body('Filter_Dir_Last'), 'SyncKey')), json('{}')))"
    % (DIR_FULL_ONE, DIR_LAST_ONE))
DROW = out("Compose_Dir_Row")

det("Compose_Dir_Status",
    "@if(not(equals(variables('varRosterReady'), true)), 'RosterUnavailable',"
    " if(empty(%s), 'NoExaminer',"
    " if(or(%s, %s), 'Matched',"
    " if(or(greater(length(body('Filter_Dir_Full')), 0),"
    " greater(length(body('Filter_Dir_Last')), 0)), 'Ambiguous', 'NotFound'))))"
    % (EXF, DIR_FULL_ONE, DIR_LAST_ONE))

det_obj("Compose_Dir_Result", {
    "email": "@trim(string(coalesce(%s?['Email'], '')))" % DROW,
    "teamsUserId": "@trim(string(coalesce(%s?['TeamsUserId'], '')))" % DROW,
    "syncKey": "@trim(string(coalesce(%s?['SyncKey'], '')))" % DROW,
    "matchedName": "@trim(string(coalesce(%s?['FullName'], '')))" % DROW,
})
# 姓しか取れていないときだけ、名簿の氏名でフルネームへ補完する（利用者決定）。
# フルネームが取れているときは名簿側の表記で上書きしない（本文の表記を正とする）。
det("Compose_Dir_Name",
    "@if(and(equals(%s, 'FamilyNameOnly'), equals(%s, 'Matched')),"
    " %s?['matchedName'], %s)"
    % (out("Compose_Ex_NameType"), out("Compose_Dir_Status"),
       out("Compose_Dir_Result"), EXF))


def warn(cond, label):
    return "if(%s, createArray(%s), json('[]'))" % (cond, lit(label))


det_obj("Compose_Detection_Diagnostics", {
    "messageId": "@outputs('Compose_Message_Id')",
    # --- 名簿突合（本フローで追加） ---
    "directoryMatchStatus": "@" + out("Compose_Dir_Status"),
    "directoryMatchedName": "@%s?['matchedName']" % out("Compose_Dir_Result"),
    "directoryEmail": "@%s?['email']" % out("Compose_Dir_Result"),
    "directoryTeamsUserId": "@%s?['teamsUserId']" % out("Compose_Dir_Result"),
    "directoryActiveCount": "@length(body('Filter_Dir_Active'))",
    "directoryFullNameHits": "@length(body('Filter_Dir_Full'))",
    "directoryFamilyNameHits": "@length(body('Filter_Dir_Last'))",
    # 列に入る最終的な審査官名（名簿で補完された場合は名簿の表記）
    "examinerNameFinal": "@" + out("Compose_Dir_Name"),
    "examinerName": "@" + out("Compose_Ex_Final"),
    "examinerNameType": "@" + out("Compose_Ex_NameType"),
    "primaryExaminerEmail": "@if(%s, outputs('Compose_Sender'), '')" % INTRO_OK,
    "primaryExaminerEmailEvidence":
        "@if(%s, 'self-introduction-in-current', 'not-derivable')" % INTRO_OK,
    "sourceSection": "@" + SRC_SECTION,
    "examinerEvidence": "@coalesce(%s?['b'], '')" % EXBEST,
    "applicationEvidence": "@coalesce(%s?['b'], '')" % out("Compose_App_Best"),
    # 補完の出どころ。名簿で補完した場合は directory（本文内の証拠より弱いので区別する）
    "completionSource":
        "@if(not(equals(%s, %s)), 'directory',"
        " if(equals(%s, %s), 'none', 'thread'))"
        % (out("Compose_Dir_Name"), EXF,
           out("Compose_Ex_Completed"), out("Compose_Ex_BestName")),
    "ambiguityReason":
        "@if(empty(%s), 'not-found',"
        " if(equals(%s, 'HiraganaName'), 'hiragana-unresolved',"
        " if(equals(%s, 'FamilyNameOnly'), 'multiple-family-name',"
        " if(less(%s, 15), 'score-tie',"
        " if(less(%s, 60), 'low-score', '')))))"
        % (EXF, out("Compose_Ex_NameType"), out("Compose_Ex_NameType"),
           out("Compose_Ex_ScoreDiff"), EX_SCORE),
    "warnings": "@union(%s, %s, %s, %s, %s, %s, %s, %s)" % (
        warn("equals(%s, 'FamilyNameOnly')" % out("Compose_Ex_NameType"), "family-name-only"),
        warn("equals(%s, 'HiraganaName')" % out("Compose_Ex_NameType"), "hiragana-name"),
        warn("and(not(empty(%s)), less(%s, 60))" % (EXF, EX_SCORE), "examiner-low-score"),
        warn("equals(%s, 'Ambiguous')" % out("Compose_App_Confidence"), "application-ambiguous"),
        warn("empty(%s)" % out("Compose_App_Final"), "application-not-found"),
        # 名簿突合の警告。Matched でもゲスト・外部ユーザーはメールが空になりうる。
        warn("and(equals(%s, 'Matched'), empty(%s?['email']))"
             % (out("Compose_Dir_Status"), out("Compose_Dir_Result")), "directory-email-empty"),
        warn("equals(%s, 'Ambiguous')" % out("Compose_Dir_Status"), "directory-ambiguous"),
        warn("equals(%s, 'RosterUnavailable')" % out("Compose_Dir_Status"),
             "directory-unavailable")),
    "examinerRawName": "@" + out("Compose_Ex_BestName"),
    # 姓のみ→フルネーム補完が働いたか（空白挿入は別項目なので Completed と比べる）
    "examinerNameCompleted": "@not(equals(%s, %s))" % (out("Compose_Ex_Completed"),
                                                       out("Compose_Ex_BestName")),
    "examinerIsFamilyNameOnly": "@and(lessOrEquals(length(%s), 3), not(empty(%s)))"
                                % (out("Compose_Ex_Final"), out("Compose_Ex_Final")),
    # 姓名の間に空白を入れた根拠。'original'=元から空白あり / 'variant'=規則B /
    # 'surname'=規則C（スレッド内の姓で切った） / 'none'=根拠が無いので切っていない
    "examinerSpacingSource":
        "@if(greater(length(%s), length(%s)), 'original',"
        " if(not(equals(%s, '')), 'variant',"
        " if(equals(%s, %s), 'none', 'surname')))"
        % (out("Compose_Ex_Completed"), out("Compose_Ex_CompletedKey"),
           out("Compose_Ex_Variant"), out("Compose_Ex_Surname"), lit(MK_ORG)),
    "examinerPattern": "@coalesce(%s?['p'], '')" % out("Compose_Ex_Best"),
    "examinerScore": "@" + EX_SCORE,
    "examinerScoreDiff": "@" + out("Compose_Ex_ScoreDiff"),
    # 0=現在のメッセージ / 1=直前の引用 / 2=さらに古い引用
    "examinerThreadDepth": "@int(coalesce(%s?['t'], 0))" % out("Compose_Ex_Best"),
    "examinerConfidence": "@" + out("Compose_Ex_Confidence"),
    "examinerCandidateCount": "@length(body('Filter_Ex_Valid'))",
    "applicationNumber": "@" + out("Compose_App_Final"),
    "applicationMatchedText": "@coalesce(%s?['m'], '')" % out("Compose_App_Best"),
    "applicationScore": "@" + APP_SCORE,
    "applicationThreadDepth": "@int(coalesce(%s?['t'], 0))" % out("Compose_App_Best"),
    "applicationConfidence": "@" + out("Compose_App_Confidence"),
    "applicationCandidateCount": "@length(body('Filter_App_Valid'))",
    "needsManualReview": "@" + out("Compose_Det_NeedsReview"),
})


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
] + det_seq          # 検出はここに直列で連なる（すべて深さ4。コンテナを増やさない）
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

item_actions["Condition_Det_Examiner_Found"] = cond(
    {"and": [{"greater": ["@length(outputs('Compose_Ex_Final'))", 0]}]},
    {"Increment_Examiner_Found_Count": incr("varExaminerFoundCount")},
    runafter=ra("Condition_Item_Convert_Failed"))
item_actions["Condition_Det_Application_Found"] = cond(
    {"and": [{"greater": ["@length(outputs('Compose_App_Final'))", 0]}]},
    {"Increment_Application_Found_Count": incr("varApplicationFoundCount")},
    runafter=ra("Condition_Det_Examiner_Found"))
# 名簿突合の集計。審査官名を検出できた件だけを分母にする
# （そもそも審査官名が無い件を「突合できなかった」に数えると実態がぼやける）。
item_actions["Condition_Dir_Matched"] = cond(
    {"and": [eq("@outputs('Compose_Dir_Status')", "Matched")]},
    {"Increment_Examiner_Matched_Count": incr("varExaminerMatchedCount")},
    {"Condition_Dir_Unmatched": cond(
        {"and": [{"greater": ["@length(outputs('Compose_Ex_Final'))", 0]}]},
        {"Increment_Examiner_Unmatched_Count": incr("varExaminerUnmatchedCount")})},
    runafter=ra("Condition_Det_Application_Found"))
# 要確認のものだけを記録する（100件でも結果JSONが肥大しない）
review_inner, _ = chain([
    ("Append_Detection_Review", append("varDetectionReviews", {
        "messageId": "@outputs('Compose_Message_Id')",
        "examinerName": "@outputs('Compose_Ex_Final')",
        "examinerNameType": "@outputs('Compose_Ex_NameType')",
        "examinerConfidence": "@outputs('Compose_Ex_Confidence')",
        "applicationNumber": "@outputs('Compose_App_Final')",
        "applicationConfidence": "@outputs('Compose_App_Confidence')",
        "ambiguityReason": "@outputs('Compose_Detection_Diagnostics')?['ambiguityReason']",
        "directoryMatchStatus": "@outputs('Compose_Dir_Status')",
        "warnings": "@outputs('Compose_Detection_Diagnostics')?['warnings']"})),
    ("Increment_Needs_Review_Count", incr("varNeedsReviewCount")),
])
item_actions["Condition_Det_Needs_Review"] = cond(
    {"and": [eq("@outputs('Compose_Det_NeedsReview')", True)]},
    review_inner, runafter=ra("Condition_Dir_Matched"))

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
    "examinerFoundCount": "@variables('varExaminerFoundCount')",
    "examinerMatchedCount": "@variables('varExaminerMatchedCount')",
    "examinerUnmatchedCount": "@variables('varExaminerUnmatchedCount')",
    "applicationFoundCount": "@variables('varApplicationFoundCount')",
    "needsReviewCount": "@variables('varNeedsReviewCount')",
    "detectionReviews": "@variables('varDetectionReviews')",
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
                    "RosterSharePointUrl": {
                        "title": "審査官名簿のSharePointサイトまたはリスト一覧URL",
                        "type": "string",
                        "description": "審査官名簿が置かれているサイトのURL。"
                                       "同期先と同じサイトでも別サイトでも構いません。"
                                       "名簿は読み取るだけで、書き込みは一切行いません",
                    },
                    "RosterListName": {
                        "title": "審査官名簿のリスト名",
                        "type": "string",
                        "description": "TeamsチャネルメンバーをSharePointへ同期して作成したリストの名前。"
                                       "氏名・メールアドレス・TeamsユーザーIDの列が必要です",
                    },
                },
                "required": ["SharePointUrl", "ListName", "SharedMailboxAddress", "MailCount",
                             "RosterSharePointUrl", "RosterListName"],
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
        "description": "共有メールボックスの最新メールを、審査官名・出願番号の推定付きでSharePointリストへ登録／更新する",
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
