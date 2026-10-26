# -*- coding: utf-8 -*-
"""
Flow1_GetTeamsChannelPostFromUrl のレガシーパッケージ（展開形）を生成する。

Teams投稿URL（「リンクをコピー」で得られるURL）を解析し、対象の親投稿を
Microsoft Teams標準コネクタの「Send a Microsoft Graph HTTP request」で取得して、
共通JSON形式に正規化し Object変数 / JSON文字列変数 に格納する。

JSONはすべてPython辞書から json.dump で出力し、構文妥当性を保証する。
雛形: projects/migrate-chat-spo/flows/archive-meetings/source/build_package.py
（5ファイル構造・Invoker形式 connectionReferences・手動トリガーschema書式を踏襲）

【不変則】definition.json は生成物。修正は必ず本スクリプトを編集して再生成する。
"""
import json, os, shutil

HERE = os.path.dirname(os.path.abspath(__file__))
BUILD = os.path.join(HERE, "package")

FLOW_LOGICAL_NAME = "Flow1_GetTeamsChannelPostFromUrl"
FLOW_DISPLAY_NAME = "Flow1 Teams投稿URLから投稿を取得"

# ---- 固定GUID（本フロー用に新規採番・匿名） ----
FLOW_ID     = "3a7c1e94-0b62-4d18-9f53-6c81a2d47e05"   # definition.json の name / id
PKG_FOLDER  = "5d2b8f31-7a46-49c0-b8e2-1f93c65a0d87"   # Microsoft.Flow/flows/{PKG_FOLDER}/
API_TEAMS   = "8e4f0a26-9c31-4b7d-a05e-3d62b8147f9a"   # APIリソースGUID
CONN_TEAMS  = "b16d5c83-42e7-4a09-8f31-7e2094ca6d5b"   # 接続リソースGUID
CN_TEAMS    = "3f8a1d5c6b294e07a9d2c48e15b70f36"       # connectionReferences.connectionName（匿名）
PKG_TELE    = "c74e2810-5d93-4f26-b1a8-06e3f95d24b7"   # packageTelemetryId

AUTH = {"value": "@json(decodeBase64(triggerOutputs().headers['X-MS-APIM-Tokens']))['$ConnectionKey']",
        "type": "Raw"}
H_TEAMS = {"apiId": "/providers/Microsoft.PowerApps/apis/shared_teams",
           "connectionName": "shared_teams", "operationId": None}

GRAPH_ROOT = "https://graph.microsoft.com/v1.0/teams/"


def oac(host, opid, params, runafter=None):
    """OpenApiConnection アクション（コネクタ呼び出し）"""
    h = dict(host)
    h["operationId"] = opid
    return {"type": "OpenApiConnection",
            "inputs": {"parameters": params, "host": h, "authentication": AUTH},
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


def chain(actions_in_order, first_runafter=None):
    """(name, action) の順序リストを runAfter で直列に連結して dict にする"""
    out = {}
    prev = None
    for name, act in actions_in_order:
        act = dict(act)
        act["runAfter"] = ra(prev) if prev is not None else (first_runafter or {})
        out[name] = act
        prev = name
    return out, prev


# =========================================================================
# トップレベル変数初期化
# InitializeVariable は Scope 内に置けない（handbook/rules/01）。
# 指示書の Scope_Initialize は「トップレベルの Initialize_* 連鎖」に置き換える。
# =========================================================================
INIT_SEQ = [
    # (アクション名, 変数名, 型, 初期値)
    ("Initialize_InputUrl",        "varInputUrl",        "string",  "@trim(coalesce(triggerBody()?['TeamsPostUrl'], ''))"),
    ("Initialize_TenantId",        "varTenantId",        "string",  ""),
    ("Initialize_TeamId",          "varTeamId",          "string",  ""),
    ("Initialize_ChannelId",       "varChannelId",       "string",  ""),
    ("Initialize_UrlMessageId",    "varUrlMessageId",    "string",  ""),
    ("Initialize_ParentMessageId", "varParentMessageId", "string",  ""),
    ("Initialize_TargetMessageId", "varTargetMessageId", "string",  ""),
    ("Initialize_ResultObject",    "varResultObject",    "object",  "@json('{}')"),
    ("Initialize_ResultJson",      "varResultJson",      "string",  ""),
    ("Initialize_ErrorMessages",   "varErrorMessages",   "array",   "@json('[]')"),
    # --- 制御用（指示書§6.3の必須10変数に加えて、Try/Catch と診断のために使用） ---
    ("Initialize_IsValid",         "varIsValid",         "boolean", True),
    ("Initialize_Stage",           "varStage",           "string",  "Initialize"),
    ("Initialize_ErrorCode",       "varErrorCode",       "string",  ""),
    ("Initialize_ErrorMessage",    "varErrorMessage",    "string",  ""),
    ("Initialize_LastStatusCode",  "varLastStatusCode",  "string",  "0"),
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
# Scope_ParseUrl : URL解析（純文字列操作のみ。実在確認済み関数だけを使う）
#
# uriQuery()/uriPath()/uriComponentToString() は使わない。
#  - uriPath() がパス中の %3A を復号するか否かが本リポジトリ内で確認できず、
#    チャネルIDの復号タイミングが不定になるため split() による解析にする。
#  - uriComponentToString() の代わりに decodeUriComponent()（実績あり）を使う。
# =========================================================================
Q = "outputs('Compose_Query_Normalized')"


def qparam(name):
    """クエリ値を区切り文字アンカー方式で取り出す（順不同・欠落・余分パラメータ耐性）。

    先頭・末尾に '&' を足した正規化クエリに対し '&<name>=' で分割することで、
    parentMessageId が messageId の部分一致で誤検出されるのを防ぐ。
    """
    tok = "'&" + name + "='"
    return ("@if(contains(" + Q + ", " + tok + "), "
            "trim(decodeUriComponent(first(split(last(split(" + Q + ", " + tok + ")), '&')))), '')")


PATH_RAW = "outputs('Compose_Url_Path_Raw')"
TAIL = "outputs('Compose_Message_Path_Tail')"

# 検証コード（最初に該当したものを返す入れ子 if）
# 注1: チャット判定は '@unq.gbl.spaces' の '@' を避けて 'unq.gbl.spaces' で判定する
#      （式文字列中の '@' を増やさないため。判別能力は同じ）
# 注2: contains() は大文字小文字を区別する。判定対象はいずれも Teams が生成する
#      小文字の機械生成文字列（ホスト名・'/l/message/'）であるため実運用では問題ないが、
#      URLを手入力で大文字化した場合は ERR_NOT_TEAMS_URL になる（docs に明記）。
VALIDATION_CODE = (
    "@if(empty(variables('varInputUrl')), 'ERR_URL_EMPTY',"
    " if(not(or(contains(variables('varInputUrl'), 'teams.microsoft.com'),"
    " contains(variables('varInputUrl'), 'teams.cloud.microsoft'))), 'ERR_NOT_TEAMS_URL',"
    " if(not(contains(outputs('Compose_Url_Path_Part'), '/l/message/')), 'ERR_NOT_CHANNEL_MESSAGE_URL',"
    " if(contains(variables('varChannelId'), 'unq.gbl.spaces'), 'ERR_CHAT_URL_NOT_SUPPORTED',"
    " if(empty(variables('varTeamId')), 'ERR_GROUPID_NOT_FOUND',"
    " if(empty(variables('varChannelId')), 'ERR_CHANNELID_NOT_FOUND',"
    " if(empty(variables('varTargetMessageId')), 'ERR_MESSAGEID_NOT_FOUND',"
    " '')))))))")

VALIDATION_MESSAGE = (
    "@if(equals(variables('varErrorCode'), 'ERR_URL_EMPTY'),"
    " 'Teams投稿URLが入力されていません。',"
    " if(equals(variables('varErrorCode'), 'ERR_NOT_TEAMS_URL'),"
    " 'Microsoft TeamsのURLではありません（teams.microsoft.com / teams.cloud.microsoft を含みません）。',"
    " if(equals(variables('varErrorCode'), 'ERR_NOT_CHANNEL_MESSAGE_URL'),"
    " 'Teamsチャネル投稿のURLではありません（パスに /l/message/ が含まれていません）。',"
    " if(equals(variables('varErrorCode'), 'ERR_CHAT_URL_NOT_SUPPORTED'),"
    " 'チャット（1対1・グループ・会議）のURLは対象外です。チャネル投稿のURLを指定してください。',"
    " if(equals(variables('varErrorCode'), 'ERR_GROUPID_NOT_FOUND'),"
    " 'URLのクエリに groupId が見つかりません。チャネル投稿の「リンクをコピー」で取得したURLをそのまま貼り付けてください。',"
    " if(equals(variables('varErrorCode'), 'ERR_CHANNELID_NOT_FOUND'),"
    " 'URLのパスからチャネルIDを取得できません。',"
    " if(equals(variables('varErrorCode'), 'ERR_MESSAGEID_NOT_FOUND'),"
    " 'URLのパスからメッセージIDを取得できません。',"
    " '')))))))")

parse_seq = [
    ("Set_Stage_ParseUrl", setvar("varStage", "ParseUrl")),
    # フラグメント（#...）を除去
    ("Compose_Url_Without_Fragment", compose("@first(split(variables('varInputUrl'), '#'))")),
    # パス部分（? より前）
    ("Compose_Url_Path_Raw", compose("@first(split(outputs('Compose_Url_Without_Fragment'), '?'))")),
    # 末尾スラッシュを除去（.../{messageId}/ 形式への耐性）
    # 注: Logic Apps の if() は両分岐の引数を先行評価するため、
    #     substring(P, 0, sub(length(P), 1)) は P='' のとき長さ-1で失敗しうる。
    #     take/join 方式なら P='' でも split→[''] / take(...,0)→[] / join→'' となり安全。
    ("Compose_Url_Path_Part", compose(
        "@if(endsWith(" + PATH_RAW + ", '/'),"
        " join(take(split(" + PATH_RAW + ", '/'), sub(length(split(" + PATH_RAW + ", '/')), 1)), '/'),"
        " " + PATH_RAW + ")")),
    # クエリ部分（? より後ろ。無ければ空文字）
    ("Compose_Url_Query_Part", compose(
        "@if(contains(outputs('Compose_Url_Without_Fragment'), '?'),"
        " last(split(outputs('Compose_Url_Without_Fragment'), '?')), '')")),
    # 前後に & を付けた正規化クエリ（トークン境界を確定させる）
    ("Compose_Query_Normalized", compose("@concat('&', outputs('Compose_Url_Query_Part'), '&')")),
    # /l/message/ 以降（= "{channelId}/{messageId}"）
    ("Compose_Message_Path_Tail", compose(
        "@if(contains(outputs('Compose_Url_Path_Part'), '/l/message/'),"
        " last(split(outputs('Compose_Url_Path_Part'), '/l/message/')), '')")),
    # チャネルID（URLデコード。%3A -> ':' / %40 -> '@'）
    # TAIL='' でも split→[''] / first→'' / decodeUriComponent→'' となり安全（空なら後段の検証で弾く）
    ("Parse_ChannelId_From_Path", compose(
        "@trim(decodeUriComponent(first(split(" + TAIL + ", '/'))))")),
    # URLパス上のメッセージID（'/' が無ければ取得不能として空文字）
    ("Parse_MessageId_From_Path", compose(
        "@if(contains(" + TAIL + ", '/'),"
        " trim(decodeUriComponent(last(split(" + TAIL + ", '/')))), '')")),
    ("Parse_TenantId_From_Query", compose(qparam("tenantId"))),
    ("Parse_TeamId_From_Query", compose(qparam("groupId"))),
    ("Parse_ParentMessageId_From_Query", compose(qparam("parentMessageId"))),
    # 解析結果を変数へ確定
    ("Set_ChannelId", setvar("varChannelId", "@outputs('Parse_ChannelId_From_Path')")),
    ("Set_UrlMessageId", setvar("varUrlMessageId", "@outputs('Parse_MessageId_From_Path')")),
    ("Set_TenantId", setvar("varTenantId", "@outputs('Parse_TenantId_From_Query')")),
    ("Set_TeamId", setvar("varTeamId", "@outputs('Parse_TeamId_From_Query')")),
    ("Set_ParentMessageId", setvar("varParentMessageId", "@outputs('Parse_ParentMessageId_From_Query')")),
    # targetMessageId の決定（parentMessageId 優先。自己参照なし）
    # 補足: 親投稿のリンクでは parentMessageId=0 が付く変種がある。'0' は実在しない
    #       メッセージID（実際は13桁のepochミリ秒）なので「値なし」と同等に扱う。
    ("Determine_TargetMessageId", setvar("varTargetMessageId",
        "@if(or(empty(variables('varParentMessageId')),"
        " equals(variables('varParentMessageId'), '0')),"
        " variables('varUrlMessageId'), variables('varParentMessageId'))")),
    # 検証
    ("Validate_ParsedIdentifiers", compose(VALIDATION_CODE)),
    ("Set_ErrorCode_From_Validation", setvar("varErrorCode", "@outputs('Validate_ParsedIdentifiers')")),
    ("Set_IsValid", setvar("varIsValid", "@empty(outputs('Validate_ParsedIdentifiers'))")),
    ("Set_ErrorMessage_From_Validation", setvar("varErrorMessage", VALIDATION_MESSAGE)),
]
parse_actions, parse_last = chain(parse_seq)
parse_actions["Condition_Has_Parse_Error"] = {
    "type": "If",
    "expression": {"and": [{"equals": ["@variables('varIsValid')", False]}]},
    "actions": {
        "Append_Parse_Error_Message": {
            "type": "AppendToArrayVariable",
            "inputs": {"name": "varErrorMessages",
                       "value": "@concat(variables('varErrorCode'), ': ', variables('varErrorMessage'))"},
            "runAfter": {}},
    },
    "runAfter": ra(parse_last),
}
actions["Scope_ParseUrl"] = {"type": "Scope", "actions": parse_actions, "runAfter": ra(LAST_INIT)}

# =========================================================================
# Scope_GetTeamsData : Graph で対象投稿を取得
#
# Uri のチャネルIDは uriComponent() で再エンコードする（':' と '@' を含むため）。
# Set_LastStatusCode は runAfter=[Succeeded, Failed] で必ず実行し、
# 失敗時もハンドラが「変数経由で」HTTPステータスを読めるようにする
# （handbook/rules/08「失敗ハンドラの参照安全」）。
# =========================================================================
GRAPH_MESSAGE_URI = (
    "@concat('" + GRAPH_ROOT + "', variables('varTeamId'),"
    " '/channels/', uriComponent(variables('varChannelId')),"
    " '/messages/', variables('varTargetMessageId'))")

deleted_actions, deleted_last = chain([
    ("Set_ErrorCode_Message_Deleted", setvar("varErrorCode", "ERR_MESSAGE_DELETED")),
    ("Set_ErrorMessage_Message_Deleted", setvar("varErrorMessage",
        "対象の投稿は削除済みです（deletedDateTime が設定されています）。")),
    ("Set_IsValid_Message_Deleted", setvar("varIsValid", False)),
    ("Append_Message_Deleted_Error", {"type": "AppendToArrayVariable",
        "inputs": {"name": "varErrorMessages",
                   "value": "@concat('ERR_MESSAGE_DELETED: deletedDateTime=',"
                            " string(coalesce(body('Get_Parent_Message')?['deletedDateTime'], '')))"}}),
])

get_actions = {}
get_actions["Get_Parent_Message"] = oac(H_TEAMS, "HttpRequest", {
    "Uri": GRAPH_MESSAGE_URI, "Method": "GET", "ContentType": "application/json"})
get_actions["Set_LastStatusCode"] = setvar(
    "varLastStatusCode", "@string(coalesce(outputs('Get_Parent_Message')?['statusCode'], 0))",
    {"Get_Parent_Message": ["Succeeded", "Failed"]})
get_actions["Condition_Message_Deleted"] = {
    "type": "If",
    "expression": {"and": [{"not": {"equals": [
        "@coalesce(body('Get_Parent_Message')?['deletedDateTime'], '')", ""]}}]},
    "actions": deleted_actions,
    "runAfter": {"Get_Parent_Message": ["Succeeded"]},
}

teams_actions = {}
teams_actions["Set_Stage_GetTeamsData"] = setvar("varStage", "GetTeamsData")
teams_actions["Condition_Is_Valid"] = {
    "type": "If",
    "expression": {"and": [{"equals": ["@variables('varIsValid')", True]}]},
    "actions": get_actions,
    "runAfter": ra("Set_Stage_GetTeamsData"),
}
actions["Scope_GetTeamsData"] = {"type": "Scope", "actions": teams_actions,
                                 "runAfter": ra("Scope_ParseUrl")}

# =========================================================================
# Scope_CreateResult : 共通JSON形式へ正規化 → Object変数 → JSON文字列
#
# 成功側だけが body('Get_Parent_Message') を参照する。
# 失敗側（解析エラー・削除済み）は変数のみを参照するため、
# Graph アクションがスキップされていても式が壊れない。
# Teams/Graph が返さない項目（from.email）は捏造せず空文字にする。
# =========================================================================
G = "body('Get_Parent_Message')"

RESULT_OBJECT = {
    "success": True,
    "flowName": FLOW_LOGICAL_NAME,
    "sourceUrl": "@variables('varInputUrl')",
    "retrievedAt": "@utcNow()",
    "identifiers": {
        "tenantId": "@variables('varTenantId')",
        "teamId": "@variables('varTeamId')",
        "channelId": "@variables('varChannelId')",
        "urlMessageId": "@variables('varUrlMessageId')",
        "parentMessageId": "@variables('varParentMessageId')",
        "targetMessageId": "@variables('varTargetMessageId')",
    },
    "message": {
        "id": "@coalesce(" + G + "?['id'], '')",
        "replyToId": "@coalesce(" + G + "?['replyToId'], '')",
        "etag": "@coalesce(" + G + "?['etag'], '')",
        "messageType": "@coalesce(" + G + "?['messageType'], '')",
        "createdDateTime": "@coalesce(" + G + "?['createdDateTime'], '')",
        "lastModifiedDateTime": "@coalesce(" + G + "?['lastModifiedDateTime'], '')",
        "subject": "@coalesce(" + G + "?['subject'], '')",
        "summary": "@coalesce(" + G + "?['summary'], '')",
        "importance": "@coalesce(" + G + "?['importance'], '')",
        "from": {
            "displayName": "@coalesce(" + G + "?['from']?['user']?['displayName'], '')",
            "userId": "@coalesce(" + G + "?['from']?['user']?['id'], '')",
            # Graph の channelMessage.from.user は email を返さないため空文字にする（捏造しない）
            "email": "",
        },
        "body": {
            "contentType": "@coalesce(" + G + "?['body']?['contentType'], '')",
            "content": "@coalesce(" + G + "?['body']?['content'], '')",
        },
        "webUrl": "@coalesce(" + G + "?['webUrl'], '')",
        "attachments": "@coalesce(" + G + "?['attachments'], json('[]'))",
        "mentions": "@coalesce(" + G + "?['mentions'], json('[]'))",
        "reactions": "@coalesce(" + G + "?['reactions'], json('[]'))",
    },
    # 正規化で情報を失わないよう、コネクタ応答をそのまま保持する
    "raw": "@coalesce(" + G + ", json('{}'))",
}

ERROR_IDENTIFIERS = {
    "tenantId": "@variables('varTenantId')",
    "teamId": "@variables('varTeamId')",
    "channelId": "@variables('varChannelId')",
    "urlMessageId": "@variables('varUrlMessageId')",
    "parentMessageId": "@variables('varParentMessageId')",
    "targetMessageId": "@variables('varTargetMessageId')",
}

ERROR_RESULT_OBJECT = {
    "success": False,
    "flowName": FLOW_LOGICAL_NAME,
    "sourceUrl": "@variables('varInputUrl')",
    "retrievedAt": "@utcNow()",
    "error": {
        "code": "@variables('varErrorCode')",
        "message": "@variables('varErrorMessage')",
        "stage": "@variables('varStage')",
        "details": "@variables('varErrorMessages')",
    },
    "identifiers": ERROR_IDENTIFIERS,
}

create_actions = {}
create_actions["Set_Stage_CreateResult"] = setvar("varStage", "CreateResult")
create_actions["Condition_Build_Result"] = {
    "type": "If",
    "expression": {"and": [{"equals": ["@variables('varIsValid')", True]}]},
    "actions": {
        "Create_Result_Object": compose(RESULT_OBJECT),
        "Set_ResultObject": setvar("varResultObject", "@outputs('Create_Result_Object')",
                                   {"Create_Result_Object": ["Succeeded"]}),
    },
    "else": {"actions": {
        "Create_Error_Result_Object": compose(ERROR_RESULT_OBJECT),
        "Set_ResultObject_Error": setvar("varResultObject", "@outputs('Create_Error_Result_Object')",
                                         {"Create_Error_Result_Object": ["Succeeded"]}),
    }},
    "runAfter": ra("Set_Stage_CreateResult"),
}
create_actions["Serialize_Result_To_Json"] = setvar(
    "varResultJson", "@string(variables('varResultObject'))", ra("Condition_Build_Result"))
actions["Scope_CreateResult"] = {"type": "Scope", "actions": create_actions,
                                 "runAfter": ra("Scope_GetTeamsData")}

# =========================================================================
# Scope_ErrorHandler（Catch相当）
#
# runAfter は直前の Scope_CreateResult 1本にだけ張る。
# 複数Scopeを列挙すると AND 判定になり「前段成功・中段失敗」でハンドラが
# 発火しない。直列連鎖なら前段失敗時に後段が Skipped になるため、
# 最終Scopeの Skipped/Failed/TimedOut で確実に発火する。
#
# ハンドラ内の式は変数だけを参照する（未実行アクションの outputs を参照すると
# ハンドラ自体が壊れる。handbook/rules/08）。
# =========================================================================
HANDLER_ERROR_CODE = (
    "@if(not(empty(variables('varErrorCode'))), variables('varErrorCode'),"
    " if(equals(variables('varLastStatusCode'), '401'), 'ERR_PERMISSION_DENIED',"
    " if(equals(variables('varLastStatusCode'), '403'), 'ERR_PERMISSION_DENIED',"
    " if(equals(variables('varLastStatusCode'), '404'), 'ERR_MESSAGE_NOT_FOUND',"
    " if(equals(variables('varLastStatusCode'), '400'), 'ERR_GRAPH_BAD_REQUEST',"
    " 'ERR_UNEXPECTED_FAILURE')))))")

HANDLER_ERROR_MESSAGE = (
    "@if(not(empty(variables('varErrorMessage'))), variables('varErrorMessage'),"
    " if(equals(variables('varLastStatusCode'), '401'),"
    " 'Teamsコネクタの認証に失敗しました。接続を再作成してください。',"
    " if(equals(variables('varLastStatusCode'), '403'),"
    " '対象のチーム／チャネルを読み取る権限がありません。チームのメンバーであること、チャネルへのアクセス権を確認してください。',"
    " if(equals(variables('varLastStatusCode'), '404'),"
    " '対象の投稿が見つかりません（存在しない、削除済み、またはチーム／チャネルにアクセスできません）。',"
    " if(equals(variables('varLastStatusCode'), '400'),"
    " 'Graph要求が不正です。URLから取得した teamId / channelId / messageId の値を確認してください。',"
    " '想定外のエラーが発生しました。実行履歴で失敗したアクションを確認してください。')))))")

HANDLER_RESULT_OBJECT = {
    "success": False,
    "flowName": FLOW_LOGICAL_NAME,
    "sourceUrl": "@variables('varInputUrl')",
    "retrievedAt": "@utcNow()",
    "error": {
        "code": "@outputs('Compose_Handler_Error_Code')",
        "message": "@outputs('Compose_Handler_Error_Message')",
        "stage": "@variables('varStage')",
        "details": "@outputs('Compose_Handler_Error_Details')",
    },
    "identifiers": ERROR_IDENTIFIERS,
}

handler_seq = [
    ("Compose_Handler_Error_Code", compose(HANDLER_ERROR_CODE)),
    ("Compose_Handler_Error_Message", compose(HANDLER_ERROR_MESSAGE)),
    ("Compose_Handler_Error_Details", compose(
        "@union(variables('varErrorMessages'),"
        " createArray(concat('stage=', variables('varStage')),"
        " concat('httpStatusCode=', variables('varLastStatusCode'))))")),
    ("Handle_Error", compose(HANDLER_RESULT_OBJECT)),
    ("Set_ResultObject_Handler", setvar("varResultObject", "@outputs('Handle_Error')")),
    ("Serialize_Handler_Result_To_Json", setvar("varResultJson", "@string(variables('varResultObject'))")),
]
handler_actions, _ = chain(handler_seq)
actions["Scope_ErrorHandler"] = {
    "type": "Scope", "actions": handler_actions,
    "runAfter": {"Scope_CreateResult": ["Failed", "Skipped", "TimedOut"]},
}

# =========================================================================
# Scope_Finalize（Finally相当）: 成否に関わらず最終結果を出力に露出する
# =========================================================================
actions["Scope_Finalize"] = {
    "type": "Scope",
    "actions": {
        "Compose_Flow_Output": compose({
            "success": "@coalesce(variables('varResultObject')?['success'], false)",
            "resultObject": "@variables('varResultObject')",
            "resultJson": "@variables('varResultJson')",
        }),
    },
    "runAfter": {"Scope_ErrorHandler": ["Succeeded", "Failed", "Skipped", "TimedOut"]},
}

# =========================================================================
# definition.json
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
            "type": "Request",
            "kind": "Button",
            "inputs": {"schema": {
                "type": "object",
                "properties": {
                    "TeamsPostUrl": {
                        "title": "Teams投稿URL",
                        "type": "string",
                        "description": "Teamsチャネル投稿の「リンクをコピー」で取得したURLを貼り付けてください",
                    },
                },
                "required": ["TeamsPostUrl"],
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
            "shared_teams": {
                "connectionName": CN_TEAMS,
                "source": "Invoker",
                "id": "/providers/Microsoft.PowerApps/apis/shared_teams",
                "tier": "NotSpecified",
                "apiName": "teams",
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
        "description": "Teams投稿URLを解析し、対象のチャネル投稿を取得してJSONに正規化する",
        "createdTime": "2026-07-24T00:00:00.0000000Z",
        "packageTelemetryId": PKG_TELE,
        "creator": "N/A",
        "sourceEnvironment": "",
    },
    "resources": {
        PKG_FOLDER: {
            "type": "Microsoft.Flow/flows",
            "suggestedCreationType": "New",
            "creationType": "Existing, New, Update",
            "details": {"displayName": FLOW_DISPLAY_NAME},
            "configurableBy": "User",
            "hierarchy": "Root",
            "dependsOn": [API_TEAMS, CONN_TEAMS],
        },
        API_TEAMS: {
            "id": "/providers/Microsoft.PowerApps/apis/shared_teams",
            "name": "shared_teams",
            "type": "Microsoft.PowerApps/apis",
            "suggestedCreationType": "Existing",
            "details": {"displayName": "Microsoft Teams"},
            "configurableBy": "System",
            "hierarchy": "Child",
            "dependsOn": [],
        },
        CONN_TEAMS: {
            "type": "Microsoft.PowerApps/apis/connections",
            "suggestedCreationType": "Existing",
            "creationType": "Existing",
            "details": {"displayName": "Microsoft Teams への接続を選択してください"},
            "configurableBy": "User",
            "hierarchy": "Child",
            "dependsOn": [API_TEAMS],
        },
    },
}

flows_manifest = {"packageSchemaVersion": "1.0", "flowAssets": {"assetPaths": [PKG_FOLDER]}}
apis_map = {"shared_teams": API_TEAMS}
connections_map = {"shared_teams": CONN_TEAMS}


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
