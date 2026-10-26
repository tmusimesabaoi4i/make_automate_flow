# -*- coding: utf-8 -*-
"""
Flow3_ListTeamsChannelPostReactorsFromUrl のレガシーパッケージ（展開形）を生成する。

Teams投稿URL（「リンクをコピー」で得られるURL）を解析し、対象の親投稿を
Microsoft Teams標準コネクタの「Send a Microsoft Graph HTTP request」で取得して、
その投稿にリアクションした人を一覧化し JSON（Object変数 / JSON文字列変数）に格納する。

Graph の reactions[].user.user には表示名・メールが入らないことが多いため、
チャネルメンバー一覧（GET /teams/{id}/channels/{id}/members）を取得して userId で突合し、
displayName / email を補う。メンバー一覧が取れない場合（権限不足等）は
userId だけの一覧に警告を付けて返し、フロー全体は失敗させない。

JSONはすべてPython辞書から json.dump で出力し、構文妥当性を保証する。
雛形: projects/teams_post_url_flows/flows/flow1-get-channel-post/source/build_flow1.py
（URL解析・投稿取得・エラー処理は Flow1 と同一。Flow1 は実環境でインポート・実行成功済み）

【不変則】definition.json は生成物。修正は必ず本スクリプトを編集して再生成する。
"""
import json, os, shutil

HERE = os.path.dirname(os.path.abspath(__file__))
BUILD = os.path.join(HERE, "package")

FLOW_LOGICAL_NAME = "Flow3_ListTeamsChannelPostReactorsFromUrl"
FLOW_DISPLAY_NAME = "Flow3 Teams投稿URLからリアクションした人を一覧化"

# ---- 固定GUID（本フロー用に新規採番・匿名） ----
FLOW_ID     = "bdb82d3c-31d2-4a02-80ac-54cd6cecb3d2"   # definition.json の name / id
PKG_FOLDER  = "324d318b-a431-46c0-84d3-979eadb9cab8"   # Microsoft.Flow/flows/{PKG_FOLDER}/
API_TEAMS   = "45ef819e-8e54-4fb7-8e5c-fcd52c415d0d"   # APIリソースGUID
CONN_TEAMS  = "e6b957ad-a93d-4a05-b953-bf5eb97f635d"   # 接続リソースGUID
CN_TEAMS    = "e4a55cc5349b4793a371d2d2f686e783"       # connectionReferences.connectionName（匿名）
PKG_TELE    = "c58d2419-b070-42a2-bb65-6f8000604e17"   # packageTelemetryId

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


def nonblank(value):
    """空文字・false を同値の式に置き換える。

    「変数の設定」の値に空文字 "" を渡したところ、デザイナーの保存時に
    「'値' は必須です」で拒否された（Flow3 の実環境で発生）。false も同じく
    未入力と判定される恐れがあるため、初期化・設定の値には空欄に見えない式を渡す。
    """
    if value == "" and isinstance(value, str):
        return "@string('')"
    if value is False:
        return "@false"
    return value


def initvar(name, vtype, value):
    return {"type": "InitializeVariable",
            "inputs": {"variables": [{"name": name, "type": vtype, "value": nonblank(value)}]}}


def compose(expr, runafter=None):
    return {"type": "Compose", "inputs": expr, "runAfter": runafter or {}}


def setvar(name, value, runafter=None):
    return {"type": "SetVariable", "inputs": {"name": name, "value": nonblank(value)},
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
    # --- Flow3: リアクション一覧化 ---
    ("Initialize_RawReactions",        "varRawReactions",        "array",   "@json('[]')"),
    ("Initialize_Members",             "varMembers",             "array",   "@json('[]')"),
    ("Initialize_MemberNextLink",      "varMemberNextLink",      "string",  ""),
    ("Initialize_MembersStatusCode",   "varMembersStatusCode",   "string",  "0"),
    ("Initialize_MembersLookupFailed", "varMembersLookupFailed", "boolean", False),
    ("Initialize_MembersLoaded",       "varMembersLoaded",       "boolean", False),
    ("Initialize_Reactions",           "varReactions",           "array",   "@json('[]')"),
    ("Initialize_ReactorUserIds",      "varReactorUserIds",      "array",   "@json('[]')"),
    ("Initialize_Reactors",            "varReactors",            "array",   "@json('[]')"),
    ("Initialize_Warnings",            "varWarnings",            "array",   "@json('[]')"),
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
# 後続Scopeが body('Get_Parent_Message') を参照しなくて済むよう、リアクションを変数へ退避する
# （解析エラーで Get_Parent_Message が Skipped のとき、条件式から body() を参照すると壊れるため）
get_actions["Set_RawReactions"] = setvar(
    "varRawReactions", "@coalesce(body('Get_Parent_Message')?['reactions'], json('[]'))",
    {"Get_Parent_Message": ["Succeeded"]})

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
# Scope_GetChannelMembers : displayName / email 補完用のチャネルメンバー一覧
#
# リアクションが1件以上あるときだけ取得する。@odata.nextLink を Do until で追跡する。
# 取得失敗（403等）はフロー全体の失敗にしない:
#   - ループ内で Get_Channel_Members の Failed/TimedOut を受けて varMembersLookupFailed を立て、
#     Do until の終了条件で止める（Do until が失敗後も反復を続ける場合の保険）
#   - ループ外で Do until の Failed/TimedOut を受けて varMembersLookupFailed を立てる
#     （失敗を「処理済み」にするため Scope 自体は成功で抜ける）
# 後段は varMembersLoaded だけを見て、取得できなかった場合は警告付きで続行する。
# =========================================================================
GRAPH_MEMBERS_URI = (
    "@concat('" + GRAPH_ROOT + "', variables('varTeamId'),"
    " '/channels/', uriComponent(variables('varChannelId')), '/members')")

member_loop_actions = {}
member_loop_actions["Get_Channel_Members"] = oac(H_TEAMS, "HttpRequest", {
    "Uri": "@variables('varMemberNextLink')", "Method": "GET", "ContentType": "application/json"})
member_loop_actions["Set_Members_Status_Code"] = setvar(
    "varMembersStatusCode", "@string(coalesce(outputs('Get_Channel_Members')?['statusCode'], 0))",
    {"Get_Channel_Members": ["Succeeded", "Failed", "TimedOut"]})
# 突合に使う3項目だけを1件ずつ追加する（ページ配列をそのまま Append すると入れ子配列になる）
member_loop_actions["Process_Retrieved_Members"] = {
    "type": "Foreach",
    "foreach": "@coalesce(body('Get_Channel_Members')?['value'], json('[]'))",
    "actions": {
        "Append_Member": {"type": "AppendToArrayVariable",
                          "inputs": {"name": "varMembers", "value": {
                              "userId": "@coalesce(item()?['userId'], '')",
                              "displayName": "@coalesce(item()?['displayName'], '')",
                              "email": "@coalesce(item()?['email'], '')",
                          }},
                          "runAfter": {}},
    },
    "runtimeConfiguration": {"concurrency": {"repetitions": 1}},
    "runAfter": {"Get_Channel_Members": ["Succeeded"]},
}
member_loop_actions["Set_MemberNextLink"] = setvar(
    "varMemberNextLink", "@coalesce(body('Get_Channel_Members')?['@odata.nextLink'], '')",
    {"Process_Retrieved_Members": ["Succeeded"]})
# 取得失敗時は失敗フラグを立て、Do until の終了条件で止める。
# SetVariable の値に空文字 "" を渡すと、デザイナーの保存時に「'値' は必須です」で
# 拒否されることがあるため、nextLink を空にする方式は採らない（実環境で発生）。
member_loop_actions["Set_Members_Lookup_Failed_In_Loop"] = setvar(
    "varMembersLookupFailed", True, {"Get_Channel_Members": ["Failed", "TimedOut"]})

members_block = {}
members_block["Set_MemberNextLink_First"] = setvar("varMemberNextLink", GRAPH_MEMBERS_URI)
members_block["Do_Until_Members_Paging"] = {
    "type": "Until",
    "expression": "@or(empty(variables('varMemberNextLink')), variables('varMembersLookupFailed'))",
    "limit": {"count": 5000, "timeout": "PT1H"},
    "actions": member_loop_actions,
    "runAfter": ra("Set_MemberNextLink_First"),
}
members_block["Set_MembersLoaded"] = setvar(
    "varMembersLoaded", "@not(variables('varMembersLookupFailed'))",
    {"Do_Until_Members_Paging": ["Succeeded"]})
members_block["Mark_Member_Lookup_Failed"] = setvar(
    "varMembersLookupFailed", True, {"Do_Until_Members_Paging": ["Failed", "TimedOut"]})

member_scope_actions = {}
member_scope_actions["Set_Stage_GetChannelMembers"] = setvar("varStage", "GetChannelMembers")
member_scope_actions["Condition_Has_Reactions"] = {
    "type": "If",
    "expression": {"and": [{"equals": [
        "@and(variables('varIsValid'), greater(length(variables('varRawReactions')), 0))", True]}]},
    "actions": members_block,
    "runAfter": ra("Set_Stage_GetChannelMembers"),
}
actions["Scope_GetChannelMembers"] = {"type": "Scope", "actions": member_scope_actions,
                                      "runAfter": ra("Scope_GetTeamsData")}

# =========================================================================
# Scope_BuildReactors : リアクション1件ごとの正規化 → 人単位に集約
#
# 1) Apply_To_Each_Reaction: メンバー一覧を userId で Filter して表示名・メールを補い、
#    varReactions へ追加。初出の userId だけ varReactorUserIds へ追加する（重複排除）。
# 2) Apply_To_Each_Reactor: userId ごとに varReactions を Filter し、
#    1人1件（リアクション種別の一覧付き）にまとめて varReactors へ追加する。
# ループ内では外側の現在要素を items('<ループ名>') で参照する
# （Filter array の where 内の item() はフィルタ対象側の要素を指すため）。
# 前段 Scope_GetChannelMembers が失敗しても続行する（runAfter に Failed/TimedOut を含める）。
# =========================================================================
RX = "items('Apply_To_Each_Reaction')"
MEMBER = "outputs('Compose_Matched_Member')"

NORMALIZED_REACTION = {
    "userId": "@outputs('Compose_Reaction_UserId')",
    "displayName": "@coalesce(" + MEMBER + "?['displayName'], " + RX + "?['user']?['user']?['displayName'], '')",
    "email": "@coalesce(" + MEMBER + "?['email'], '')",
    "userIdentityType": "@coalesce(" + RX + "?['user']?['user']?['userIdentityType'], '')",
    # found=メンバー一覧で一致 / notFound=一覧に無い（退出者・ゲスト等） / unavailable=一覧を取得できなかった
    "memberLookup": ("@if(not(variables('varMembersLoaded')), 'unavailable',"
                     " if(empty(body('Filter_Member_For_Reaction')), 'notFound', 'found'))"),
    "reactionType": "@coalesce(" + RX + "?['reactionType'], '')",
    "reactionDisplayName": "@coalesce(" + RX + "?['displayName'], '')",
    "createdDateTime": "@coalesce(" + RX + "?['createdDateTime'], '')",
}

reaction_loop = {
    "Compose_Reaction_UserId": compose("@coalesce(" + RX + "?['user']?['user']?['id'], '')"),
    "Filter_Member_For_Reaction": {
        "type": "Query",
        "inputs": {"from": "@variables('varMembers')",
                   "where": "@equals(item()?['userId'], outputs('Compose_Reaction_UserId'))"},
        "runAfter": ra("Compose_Reaction_UserId")},
    # 一致なしなら first([]) = null となり、後段の ?[] 参照も null（coalesce で空文字）
    "Compose_Matched_Member": compose("@first(body('Filter_Member_For_Reaction'))",
                                      ra("Filter_Member_For_Reaction")),
    "Compose_Normalized_Reaction": compose(NORMALIZED_REACTION, ra("Compose_Matched_Member")),
    "Append_Normalized_Reaction": {
        "type": "AppendToArrayVariable",
        "inputs": {"name": "varReactions", "value": "@outputs('Compose_Normalized_Reaction')"},
        "runAfter": ra("Compose_Normalized_Reaction")},
    "Condition_Is_New_Reactor": {
        "type": "If",
        "expression": {"and": [{"equals": [
            "@and(not(empty(outputs('Compose_Reaction_UserId'))),"
            " not(contains(variables('varReactorUserIds'), outputs('Compose_Reaction_UserId'))))", True]}]},
        "actions": {
            "Append_Reactor_UserId": {
                "type": "AppendToArrayVariable",
                "inputs": {"name": "varReactorUserIds", "value": "@outputs('Compose_Reaction_UserId')"},
                "runAfter": {}},
        },
        "runAfter": ra("Append_Normalized_Reaction")},
}

UID = "items('Apply_To_Each_Reactor')"
FIRST_R = "first(body('Filter_Reactions_Of_User'))"

REACTOR = {
    "userId": "@" + UID,
    "displayName": "@coalesce(" + FIRST_R + "?['displayName'], '')",
    "email": "@coalesce(" + FIRST_R + "?['email'], '')",
    "userIdentityType": "@coalesce(" + FIRST_R + "?['userIdentityType'], '')",
    "memberLookup": "@coalesce(" + FIRST_R + "?['memberLookup'], '')",
    "reactionCount": "@length(body('Filter_Reactions_Of_User'))",
    "reactions": "@body('Select_Reaction_Summary')",
}

reactor_loop = {
    "Filter_Reactions_Of_User": {
        "type": "Query",
        "inputs": {"from": "@variables('varReactions')",
                   "where": "@equals(item()?['userId'], " + UID + ")"},
        "runAfter": {}},
    "Select_Reaction_Summary": {
        "type": "Select",
        "inputs": {"from": "@body('Filter_Reactions_Of_User')",
                   "select": {"reactionType": "@item()?['reactionType']",
                              "reactionDisplayName": "@item()?['reactionDisplayName']",
                              "createdDateTime": "@item()?['createdDateTime']"}},
        "runAfter": ra("Filter_Reactions_Of_User")},
    "Compose_Reactor": compose(REACTOR, ra("Select_Reaction_Summary")),
    "Append_Reactor": {
        "type": "AppendToArrayVariable",
        "inputs": {"name": "varReactors", "value": "@outputs('Compose_Reactor')"},
        "runAfter": ra("Compose_Reactor")},
}

build_block = {}
build_block["Condition_Member_Lookup_Unavailable"] = {
    "type": "If",
    "expression": {"and": [{"equals": [
        "@and(not(variables('varMembersLoaded')), greater(length(variables('varRawReactions')), 0))", True]}]},
    "actions": {
        "Append_Member_Lookup_Warning": {
            "type": "AppendToArrayVariable",
            "inputs": {"name": "varWarnings", "value": (
                "@concat('WARN_MEMBER_LOOKUP_FAILED: チャネルメンバー一覧を取得できなかったため、"
                "displayName / email が空の場合があります（httpStatusCode=',"
                " variables('varMembersStatusCode'), '）。')")},
            "runAfter": {}},
    },
    "runAfter": {},
}
build_block["Apply_To_Each_Reaction"] = {
    "type": "Foreach",
    "foreach": "@variables('varRawReactions')",
    "actions": reaction_loop,
    "runtimeConfiguration": {"concurrency": {"repetitions": 1}},
    "runAfter": ra("Condition_Member_Lookup_Unavailable"),
}
build_block["Apply_To_Each_Reactor"] = {
    "type": "Foreach",
    "foreach": "@variables('varReactorUserIds')",
    "actions": reactor_loop,
    "runtimeConfiguration": {"concurrency": {"repetitions": 1}},
    "runAfter": ra("Apply_To_Each_Reaction"),
}

build_scope_actions = {}
build_scope_actions["Set_Stage_BuildReactors"] = setvar("varStage", "BuildReactors")
build_scope_actions["Condition_Can_Build_Reactors"] = {
    "type": "If",
    "expression": {"and": [{"equals": ["@variables('varIsValid')", True]}]},
    "actions": build_block,
    "runAfter": ra("Set_Stage_BuildReactors"),
}
actions["Scope_BuildReactors"] = {
    "type": "Scope", "actions": build_scope_actions,
    "runAfter": {"Scope_GetChannelMembers": ["Succeeded", "Failed", "TimedOut"]},
}

# =========================================================================
# Scope_CreateResult : 結果JSON → Object変数 → JSON文字列
#
# 成功側だけが body('Get_Parent_Message') を参照する。
# 失敗側（解析エラー・削除済み）は変数のみを参照するため、
# Graph アクションがスキップされていても式が壊れない。
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
        "createdDateTime": "@coalesce(" + G + "?['createdDateTime'], '')",
        "subject": "@coalesce(" + G + "?['subject'], '')",
        "from": {
            "displayName": "@coalesce(" + G + "?['from']?['user']?['displayName'], '')",
            "userId": "@coalesce(" + G + "?['from']?['user']?['id'], '')",
        },
        "webUrl": "@coalesce(" + G + "?['webUrl'], '')",
    },
    "memberLookup": {
        "loaded": "@variables('varMembersLoaded')",
        "httpStatusCode": "@variables('varMembersStatusCode')",
        "memberCount": "@length(variables('varMembers'))",
    },
    # 実際に変数へ格納された件数から算出する
    "reactorCount": "@length(variables('varReactors'))",
    "reactionCount": "@length(variables('varReactions'))",
    "reactors": "@variables('varReactors')",
    "reactions": "@variables('varReactions')",
    "warnings": "@variables('varWarnings')",
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
                                 "runAfter": ra("Scope_BuildReactors")}

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
        "description": "Teams投稿URLを解析し、対象のチャネル投稿にリアクションした人を一覧化してJSONに格納する",
        "createdTime": "2026-10-26T00:00:00.0000000Z",
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
