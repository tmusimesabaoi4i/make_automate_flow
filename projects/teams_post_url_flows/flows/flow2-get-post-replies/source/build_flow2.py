# -*- coding: utf-8 -*-
"""
Flow2_GetAllTeamsChannelPostRepliesFromUrl のレガシーパッケージ（展開形）を生成する。

Teams投稿URLを解析し、対象の親投稿とその**全返信**を Microsoft Teams標準コネクタの
「Send a Microsoft Graph HTTP request」で取得する。返信は @odata.nextLink を
Do until で追跡して全ページを取得し、配列変数へ1件ずつ Append して蓄積する
（SetVariable の自己参照は使わない）。

URL解析部分は Flow1 と同一の式チェーンを使う（tests/run_url_parse_tests.py で
両フローの definition.json を同じテストケースで検証している）。

【不変則】definition.json は生成物。修正は必ず本スクリプトを編集して再生成する。
"""
import json, os

HERE = os.path.dirname(os.path.abspath(__file__))
BUILD = os.path.join(HERE, "package")

FLOW_LOGICAL_NAME = "Flow2_GetAllTeamsChannelPostRepliesFromUrl"
FLOW_DISPLAY_NAME = "Flow2 Teams投稿URLから全返信を取得"

# ---- 固定GUID（本フロー用に新規採番・匿名。Flow1 とは別値） ----
FLOW_ID     = "9b3e7d05-1c84-42fa-8e69-5a0d7c31b6e2"
PKG_FOLDER  = "2c96a4e7-8b53-4d10-9f27-e6a41b085c39"
API_TEAMS   = "47d0b9e2-6a15-4c83-b7f0-91e56d2a3c84"
CONN_TEAMS  = "f052a7c6-3e18-4b94-a2d7-8c61093fb5ea"
CN_TEAMS    = "7d21c9a4e5b8406f83c1d76e2a95b408"
PKG_TELE    = "a8517e30-9f64-4c2b-83d5-72e046c19b8d"

AUTH = {"value": "@json(decodeBase64(triggerOutputs().headers['X-MS-APIM-Tokens']))['$ConnectionKey']",
        "type": "Raw"}
H_TEAMS = {"apiId": "/providers/Microsoft.PowerApps/apis/shared_teams",
           "connectionName": "shared_teams", "operationId": None}

GRAPH_ROOT = "https://graph.microsoft.com/v1.0/teams/"
# 1ページあたりの取得件数。全件取得は @odata.nextLink の追跡で行うため、
# $top は「1ページの上限」にすぎない（先頭N件で打ち切る意味ではない）。
REPLIES_PAGE_SIZE = 50


def oac(host, opid, params, runafter=None):
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
    out = {}
    prev = None
    for name, act in actions_in_order:
        act = dict(act)
        act["runAfter"] = ra(prev) if prev is not None else (first_runafter or {})
        out[name] = act
        prev = name
    return out, prev


# =========================================================================
# トップレベル変数初期化（InitializeVariable は Scope 内に置けない）
# =========================================================================
INIT_SEQ = [
    ("Initialize_InputUrl",        "varInputUrl",        "string",  "@trim(coalesce(triggerBody()?['TeamsPostUrl'], ''))"),
    ("Initialize_TenantId",        "varTenantId",        "string",  ""),
    ("Initialize_TeamId",          "varTeamId",          "string",  ""),
    ("Initialize_ChannelId",       "varChannelId",       "string",  ""),
    ("Initialize_UrlMessageId",    "varUrlMessageId",    "string",  ""),
    ("Initialize_ParentMessageId", "varParentMessageId", "string",  ""),
    ("Initialize_TargetMessageId", "varTargetMessageId", "string",  ""),
    ("Initialize_Replies",         "varReplies",         "array",   "@json('[]')"),
    ("Initialize_ResultObject",    "varResultObject",    "object",  "@json('{}')"),
    ("Initialize_ResultJson",      "varResultJson",      "string",  ""),
    ("Initialize_ErrorMessages",   "varErrorMessages",   "array",   "@json('[]')"),
    # --- 返信取得の作業用 ---
    ("Initialize_RepliesRaw",      "varRepliesRaw",      "array",   "@json('[]')"),
    ("Initialize_ReplyNextLink",   "varReplyNextLink",   "string",  ""),
    # --- 制御用（Try/Catch と診断） ---
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
# Scope_ParseUrl : Flow1 と同一の解析チェーン
# =========================================================================
Q = "outputs('Compose_Query_Normalized')"


def qparam(name):
    """クエリ値を区切り文字アンカー方式で取り出す（順不同・欠落・余分パラメータ耐性）"""
    tok = "'&" + name + "='"
    return ("@if(contains(" + Q + ", " + tok + "), "
            "trim(decodeUriComponent(first(split(last(split(" + Q + ", " + tok + ")), '&')))), '')")


PATH_RAW = "outputs('Compose_Url_Path_Raw')"
TAIL = "outputs('Compose_Message_Path_Tail')"

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
    ("Compose_Url_Without_Fragment", compose("@first(split(variables('varInputUrl'), '#'))")),
    ("Compose_Url_Path_Raw", compose("@first(split(outputs('Compose_Url_Without_Fragment'), '?'))")),
    # 末尾スラッシュ除去。Logic Apps の if() は両分岐を先行評価するため、
    # substring による長さ計算ではなく take/join 方式にする（空文字でも安全）。
    ("Compose_Url_Path_Part", compose(
        "@if(endsWith(" + PATH_RAW + ", '/'),"
        " join(take(split(" + PATH_RAW + ", '/'), sub(length(split(" + PATH_RAW + ", '/')), 1)), '/'),"
        " " + PATH_RAW + ")")),
    ("Compose_Url_Query_Part", compose(
        "@if(contains(outputs('Compose_Url_Without_Fragment'), '?'),"
        " last(split(outputs('Compose_Url_Without_Fragment'), '?')), '')")),
    ("Compose_Query_Normalized", compose("@concat('&', outputs('Compose_Url_Query_Part'), '&')")),
    ("Compose_Message_Path_Tail", compose(
        "@if(contains(outputs('Compose_Url_Path_Part'), '/l/message/'),"
        " last(split(outputs('Compose_Url_Path_Part'), '/l/message/')), '')")),
    ("Parse_ChannelId_From_Path", compose(
        "@trim(decodeUriComponent(first(split(" + TAIL + ", '/'))))")),
    ("Parse_MessageId_From_Path", compose(
        "@if(contains(" + TAIL + ", '/'),"
        " trim(decodeUriComponent(last(split(" + TAIL + ", '/')))), '')")),
    ("Parse_TenantId_From_Query", compose(qparam("tenantId"))),
    ("Parse_TeamId_From_Query", compose(qparam("groupId"))),
    ("Parse_ParentMessageId_From_Query", compose(qparam("parentMessageId"))),
    ("Set_ChannelId", setvar("varChannelId", "@outputs('Parse_ChannelId_From_Path')")),
    ("Set_UrlMessageId", setvar("varUrlMessageId", "@outputs('Parse_MessageId_From_Path')")),
    ("Set_TenantId", setvar("varTenantId", "@outputs('Parse_TenantId_From_Query')")),
    ("Set_TeamId", setvar("varTeamId", "@outputs('Parse_TeamId_From_Query')")),
    ("Set_ParentMessageId", setvar("varParentMessageId", "@outputs('Parse_ParentMessageId_From_Query')")),
    ("Determine_TargetMessageId", setvar("varTargetMessageId",
        "@if(or(empty(variables('varParentMessageId')),"
        " equals(variables('varParentMessageId'), '0')),"
        " variables('varUrlMessageId'), variables('varParentMessageId'))")),
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
# Scope_GetTeamsData : 親投稿の取得 → 全返信のページング取得 → 正規化
# =========================================================================
GRAPH_MESSAGE_URI = (
    "@concat('" + GRAPH_ROOT + "', variables('varTeamId'),"
    " '/channels/', uriComponent(variables('varChannelId')),"
    " '/messages/', variables('varTargetMessageId'))")

GRAPH_REPLIES_URI = (
    "@concat('" + GRAPH_ROOT + "', variables('varTeamId'),"
    " '/channels/', uriComponent(variables('varChannelId')),"
    " '/messages/', variables('varTargetMessageId'),"
    " '/replies?$top=" + str(REPLIES_PAGE_SIZE) + "')")

R = "items('Apply_To_Each_Raw_Reply')"

NORMALIZED_REPLY = {
    "id": "@coalesce(" + R + "?['id'], '')",
    "replyToId": "@coalesce(" + R + "?['replyToId'], '')",
    "etag": "@coalesce(" + R + "?['etag'], '')",
    "messageType": "@coalesce(" + R + "?['messageType'], '')",
    "createdDateTime": "@coalesce(" + R + "?['createdDateTime'], '')",
    "lastModifiedDateTime": "@coalesce(" + R + "?['lastModifiedDateTime'], '')",
    "from": {
        "displayName": "@coalesce(" + R + "?['from']?['user']?['displayName'], '')",
        "userId": "@coalesce(" + R + "?['from']?['user']?['id'], '')",
        # Graph の channelMessage.from.user は email を返さないため空文字にする（捏造しない）
        "email": "",
    },
    "body": {
        "contentType": "@coalesce(" + R + "?['body']?['contentType'], '')",
        "content": "@coalesce(" + R + "?['body']?['content'], '')",
    },
    "webUrl": "@coalesce(" + R + "?['webUrl'], '')",
    "attachments": "@coalesce(" + R + "?['attachments'], json('[]'))",
    "mentions": "@coalesce(" + R + "?['mentions'], json('[]'))",
    "reactions": "@coalesce(" + R + "?['reactions'], json('[]'))",
    "raw": "@" + R,
}

# --- Do until 内: 1ページ取得 → 1件ずつ Append → nextLink 更新 ---
do_until_actions = {}
do_until_actions["Get_All_Replies"] = oac(H_TEAMS, "HttpRequest", {
    "Uri": "@variables('varReplyNextLink')", "Method": "GET", "ContentType": "application/json"})
do_until_actions["Set_Replies_Status_Code"] = setvar(
    "varLastStatusCode", "@string(coalesce(outputs('Get_All_Replies')?['statusCode'], 0))",
    {"Get_All_Replies": ["Succeeded", "Failed"]})
# ページ配列をそのまま Append すると入れ子配列になるため、必ず1件ずつ追加する
do_until_actions["Process_Retrieved_Replies"] = {
    "type": "Foreach",
    "foreach": "@coalesce(body('Get_All_Replies')?['value'], json('[]'))",
    "actions": {
        "Append_Raw_Reply": {"type": "AppendToArrayVariable",
                             "inputs": {"name": "varRepliesRaw", "value": "@item()"},
                             "runAfter": {}},
    },
    "runtimeConfiguration": {"concurrency": {"repetitions": 1}},
    "runAfter": {"Get_All_Replies": ["Succeeded"]},
}
do_until_actions["Set_ReplyNextLink"] = setvar(
    "varReplyNextLink", "@coalesce(body('Get_All_Replies')?['@odata.nextLink'], '')",
    {"Process_Retrieved_Replies": ["Succeeded"]})

# --- 返信取得ブロック（親投稿が取得できた場合のみ実行） ---
replies_block = {}
replies_block["Set_ReplyNextLink_First"] = setvar("varReplyNextLink", GRAPH_REPLIES_URI)
replies_block["Do_Until_Replies_Paging"] = {
    "type": "Until",
    "expression": "@empty(variables('varReplyNextLink'))",
    "limit": {"count": 5000, "timeout": "PT1H"},
    "actions": do_until_actions,
    "runAfter": ra("Set_ReplyNextLink_First"),
}
replies_block["Apply_To_Each_Raw_Reply"] = {
    "type": "Foreach",
    "foreach": "@variables('varRepliesRaw')",
    "actions": {
        "Compose_Normalized_Reply": compose(NORMALIZED_REPLY),
        "Append_Normalized_Reply": {
            "type": "AppendToArrayVariable",
            "inputs": {"name": "varReplies", "value": "@outputs('Compose_Normalized_Reply')"},
            "runAfter": {"Compose_Normalized_Reply": ["Succeeded"]}},
    },
    "runtimeConfiguration": {"concurrency": {"repetitions": 1}},
    "runAfter": ra("Do_Until_Replies_Paging"),
}

deleted_actions, _ = chain([
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
# 親投稿が削除済みの場合は返信取得へ進まない
get_actions["Condition_Parent_Available"] = {
    "type": "If",
    "expression": {"and": [{"equals": ["@variables('varIsValid')", True]}]},
    "actions": replies_block,
    "runAfter": ra("Condition_Message_Deleted"),
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
# Scope_CreateResult
# =========================================================================
G = "body('Get_Parent_Message')"

IDENTIFIERS = {
    "tenantId": "@variables('varTenantId')",
    "teamId": "@variables('varTeamId')",
    "channelId": "@variables('varChannelId')",
    "urlMessageId": "@variables('varUrlMessageId')",
    "parentMessageId": "@variables('varParentMessageId')",
    "targetMessageId": "@variables('varTargetMessageId')",
}

RESULT_OBJECT = {
    "success": True,
    "flowName": FLOW_LOGICAL_NAME,
    "sourceUrl": "@variables('varInputUrl')",
    "retrievedAt": "@utcNow()",
    "identifiers": IDENTIFIERS,
    "parentMessage": {
        "id": "@coalesce(" + G + "?['id'], '')",
        "createdDateTime": "@coalesce(" + G + "?['createdDateTime'], '')",
        "from": {
            "displayName": "@coalesce(" + G + "?['from']?['user']?['displayName'], '')",
            "userId": "@coalesce(" + G + "?['from']?['user']?['id'], '')",
            "email": "",
        },
        "body": {
            "contentType": "@coalesce(" + G + "?['body']?['contentType'], '')",
            "content": "@coalesce(" + G + "?['body']?['content'], '')",
        },
        "webUrl": "@coalesce(" + G + "?['webUrl'], '')",
    },
    # 実際に varReplies へ格納された件数から算出する
    "replyCount": "@length(variables('varReplies'))",
    "replies": "@variables('varReplies')",
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
    "identifiers": IDENTIFIERS,
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
# Scope_ErrorHandler（Catch相当）— 参照するのは変数だけ
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
    "identifiers": IDENTIFIERS,
    # ページング途中で失敗した場合に、どこまで取得できていたかを残す
    "partialReplyCount": "@length(variables('varRepliesRaw'))",
}

handler_seq = [
    ("Compose_Handler_Error_Code", compose(HANDLER_ERROR_CODE)),
    ("Compose_Handler_Error_Message", compose(HANDLER_ERROR_MESSAGE)),
    ("Compose_Handler_Error_Details", compose(
        "@union(variables('varErrorMessages'),"
        " createArray(concat('stage=', variables('varStage')),"
        " concat('httpStatusCode=', variables('varLastStatusCode')),"
        " concat('collectedReplies=', string(length(variables('varRepliesRaw')))),"
        " concat('nextLinkAtFailure=', variables('varReplyNextLink'))))")),
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
# Scope_Finalize（Finally相当）
# =========================================================================
actions["Scope_Finalize"] = {
    "type": "Scope",
    "actions": {
        "Compose_Flow_Output": compose({
            "success": "@coalesce(variables('varResultObject')?['success'], false)",
            "replyCount": "@length(variables('varReplies'))",
            "resultObject": "@variables('varResultObject')",
            "resultJson": "@variables('varResultJson')",
        }),
    },
    "runAfter": {"Scope_ErrorHandler": ["Succeeded", "Failed", "Skipped", "TimedOut"]},
}

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
        "description": "Teams投稿URLを解析し、対象投稿への全返信を取得してJSONに正規化する",
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
