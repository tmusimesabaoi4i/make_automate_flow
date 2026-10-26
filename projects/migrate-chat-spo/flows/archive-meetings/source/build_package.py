# -*- coding: utf-8 -*-
"""
PA_Migrate_Teams_Meeting_Archive_To_SPO の単一フロー・レガシーパッケージを生成する。
JSONはすべてPython辞書から json.dump で出力し、構文妥当性を保証する。
雛形 tmp_20260716051507.zip と同一のルート構造で build/ に展開する。
"""
import json, os, shutil

HERE = os.path.dirname(os.path.abspath(__file__))
BUILD = os.path.join(HERE, "package")

# ---- 固定GUID（生成済み・匿名） ----
FLOW_NAME   = "2fe554b1-6ba6-4ce0-962c-07bde4bdb6ee"   # definition.json の name / フローID
PKG_FOLDER  = "fcca0e31-6d8b-40a8-8d63-2441c979a2c7"   # Microsoft.Flow/flows/{PKG_FOLDER}/
API_TEAMS   = "27ca9dc7-3d66-4026-9b2c-6291ab68a2cd"
API_SPO     = "96a41f5e-d19e-4c3f-a873-5e37a6819a5e"
API_CONV    = "eb4515c8-8e9c-40cb-a7f9-2b3da20c720a"
CONN_TEAMS  = "a8ff7b41-1fc0-4e5a-b4ce-6d521139c5d1"
CONN_SPO    = "29a8d7aa-01ea-4a61-88fb-7adad921d7fc"
CONN_CONV   = "49df2bda-5f3d-45c2-a7ad-9cd62a6fa452"
CN_TEAMS    = "a4d41dc235a94baabc21472cf2b9f1f6"       # connectionReferences.connectionName（匿名）
CN_SPO      = "85cb934055e9451b87540f3057dac4f4"
CN_CONV     = "0c02570219494 7bdb1ba4db7b58b5d30".replace(" ", "")
PKG_TELE    = "dcf93182-0d8a-4f2e-b064-e0ed68b818d9"

AUTH = {"value": "@json(decodeBase64(triggerOutputs().headers['X-MS-APIM-Tokens']))['$ConnectionKey']", "type": "Raw"}
H_TEAMS = {"apiId": "/providers/Microsoft.PowerApps/apis/shared_teams", "connectionName": "shared_teams", "operationId": None}
H_SPO   = {"apiId": "/providers/Microsoft.PowerApps/apis/shared_sharepointonline", "connectionName": "shared_sharepointonline", "operationId": None}
H_CONV  = {"apiId": "/providers/Microsoft.PowerApps/apis/shared_conversionservice", "connectionName": "shared_conversionservice", "operationId": None}


def oac(host, opid, params):
    h = dict(host); h["operationId"] = opid
    # runAfter は明示的に {} を既定とする（キー省略はエンジン上 {} と等価だが、
    # Power Automate 標準エクスポートに合わせて明示する。後段で上書き可）。
    return {"type": "OpenApiConnection", "inputs": {"parameters": params, "host": h, "authentication": AUTH}, "runAfter": {}}


def ra(prev, states=("Succeeded",)):
    return {} if prev is None else {prev: list(states)}


# =========================================================================
# v7: SharePoint「項目の作成」(PostItem) は、dataset/table が式だと保存時検証
# （OpenApiOperationParameterValidationFailed: missing required property 'item'）
# に失敗する（動的スキーマの必須ボディ item を解決できないため。実エラー確認済み）。
# 「SharePoint に HTTP 要求を送信」(operationId=HttpRequest) + REST に置換する。
# dataset は雛形（実エクスポート）で保存実績のある静的リテラルとし、
# リスト名は URI 内の変数参照（単純文字列パラメータのため式でも保存安全）で保つ。
# ヘッダーを Accept/Content-Type とも application/json;odata=nometadata にすると
# __metadata 不要の単純JSONボディで項目作成できる（learn.microsoft.com 確認済み）。
# =========================================================================
# v8: リスト（台帳・実行ログ）の所在サイト。ファイル保存系の varSiteAddress（mROOM）とは別。
SITE_URL_STATIC = "https://metijapan.sharepoint.com/teams/pjteam_220400119"

def sp_rest_post_item(list_var, compose_name):
    """リスト項目作成のREST呼び出し（前段 Compose のオブジェクトを string() でJSON化して送る）"""
    return {"type": "OpenApiConnection", "inputs": {"parameters": {
        "dataset": SITE_URL_STATIC,
        "parameters/method": "POST",
        "parameters/uri": "@concat('_api/web/lists/getbytitle(''', variables('" + list_var + "'), ''')/items')",
        "parameters/headers": {
            "Accept": "application/json;odata=nometadata",
            "Content-Type": "application/json;odata=nometadata"},
        "parameters/body": "@string(outputs('" + compose_name + "'))"},
        "host": {"apiId": "/providers/Microsoft.PowerApps/apis/shared_sharepointonline",
                 "connectionName": "shared_sharepointonline", "operationId": "HttpRequest"},
        "authentication": AUTH}, "runAfter": {}}


# =========================================================================
# ルートレベルの変数初期化（Initialize Variable は Scope 内に置けない制約のため
# すべてトップレベルに配置する）
# =========================================================================
def initvar(name, vtype, value):
    return {"type": "InitializeVariable", "inputs": {"variables": [{"name": name, "type": vtype, "value": value}]}}


actions = {}

# --- LookbackDays の安全化（§8）: null/未入力/0以下 → 7。正の整数のみ採用。 ---
# InitializeVariable より前のトップレベル Compose で有効値を確定する。
actions["Compose_EffectiveLookbackDays"] = {
    "type": "Compose",
    "inputs": ("@if(greater(int(coalesce(triggerBody()?['LookbackDays'], 0)), 0),"
               " int(coalesce(triggerBody()?['LookbackDays'], 7)), 7)"),
    "runAfter": {},
}

# --- 初期化チェーン（runAfterで直列） ---
init_seq = [
    ("Initialize_RunId",              "string",  "@guid()"),
    ("Initialize_LookbackDays",       "integer", "@outputs('Compose_EffectiveLookbackDays')"),
    ("Initialize_EndDateUtc",         "string",  "@utcNow()"),
    ("Initialize_StartDateUtc",       "string",  "@addDays(variables('varEndDateUtc'), sub(0, variables('varLookbackDays')))"),
    ("Initialize_TeamId",             "string",  "a7ac0c68-87ba-4613-8960-13660f0f5f56"),
    ("Initialize_ChannelId",          "string",  "19:53e5d619e45b4fda8d0dc7f2858a9d64@thread.tacv2"),
    ("Initialize_SiteAddress",        "string",  "https://metijapan.sharepoint.com/sites/mROOM_240600018"),
    # v8: リスト（台帳・実行ログ）はファイル保存先と別サイトに置く（ユーザー決定）。
    # varSiteAddress=ファイル保存系（添付・総括doc）、varListSiteAddress=リスト操作系。
    ("Initialize_ListSiteAddress",    "string",  "https://metijapan.sharepoint.com/teams/pjteam_220400119"),
    ("Initialize_Library",            "string",  "Shared Documents"),
    ("Initialize_DestinationPath",    "string",  "123_伝送システム/00_共用フォルダ/60_庶務担当/99_過去の課内会議"),
    ("Initialize_LedgerList",         "string",  "MeetingArchiveLedger"),
    ("Initialize_RunLogList",         "string",  "MeetingArchiveRunLog"),
    ("Initialize_MessagesArray",      "array",   "@json('[]')"),
    ("Initialize_NextLink",           "string",  ""),
    ("Initialize_RepliesArray",       "array",   "@json('[]')"),
    ("Initialize_ReplyNextLink",      "string",  ""),
    ("Initialize_AttachmentCandidates","array",  "@json('[]')"),
    ("Initialize_MeetingAttachments", "array",   "@json('[]')"),
    ("Initialize_Meetings",           "array",   "@json('[]')"),
    ("Initialize_SortedMeetings",     "array",   "@json('[]')"),
    ("Initialize_DocumentHtml",       "string",  ""),
    ("Initialize_MeetingIndex",       "integer", 0),
    ("Initialize_SavedCount",         "integer", 0),
    ("Initialize_SkippedCount",       "integer", 0),
    ("Initialize_FailedCount",        "integer", 0),
    ("Initialize_ArchiveUrl",         "string",  ""),
    ("Initialize_RunStatus",          "string",  "Failed"),
    ("Initialize_ErrorMessage",       "string",  ""),
]
# 変数名は var + 論理名。Initialize_RunId -> varRunId のように対応させる。
name_to_var = {
    "Initialize_RunId": "varRunId", "Initialize_LookbackDays": "varLookbackDays",
    "Initialize_EndDateUtc": "varEndDateUtc", "Initialize_StartDateUtc": "varStartDateUtc",
    "Initialize_TeamId": "varTeamId", "Initialize_ChannelId": "varChannelId",
    "Initialize_SiteAddress": "varSiteAddress", "Initialize_ListSiteAddress": "varListSiteAddress",
    "Initialize_Library": "varLibrary",
    "Initialize_DestinationPath": "varDestinationPath", "Initialize_LedgerList": "varLedgerList",
    "Initialize_RunLogList": "varRunLogList",
    "Initialize_MessagesArray": "varMessagesArray", "Initialize_NextLink": "varNextLink",
    "Initialize_RepliesArray": "varRepliesArray", "Initialize_ReplyNextLink": "varReplyNextLink",
    "Initialize_AttachmentCandidates": "varAttachmentCandidates", "Initialize_MeetingAttachments": "varMeetingAttachments",
    "Initialize_Meetings": "varMeetings", "Initialize_SortedMeetings": "varSortedMeetings",
    "Initialize_DocumentHtml": "varDocumentHtml", "Initialize_MeetingIndex": "varMeetingIndex",
    "Initialize_SavedCount": "varSavedCount", "Initialize_SkippedCount": "varSkippedCount",
    "Initialize_FailedCount": "varFailedCount",
    "Initialize_ArchiveUrl": "varArchiveUrl", "Initialize_RunStatus": "varRunStatus",
    "Initialize_ErrorMessage": "varErrorMessage",
}
prev = "Compose_EffectiveLookbackDays"
for aname, vtype, value in init_seq:
    act = initvar(name_to_var[aname], vtype, value)
    act["runAfter"] = ra(prev)
    actions[aname] = act
    prev = aname
last_init = prev

# =========================================================================
# Scope_10_Get_Channel_Messages : 親投稿の全件ページング
# =========================================================================
# チャネルID（19:...@thread.tacv2）は ':' '@' を含むため uriComponent() でエンコードする。
# 実働サンプル create_meeting_list_sample は %3A/%40 エンコード済みURLで動作しており、
# 生文字列のままでは Graph が受理しない可能性がある（実働実績側に合わせる）。
graph_msgs_first = ("@concat('https://graph.microsoft.com/v1.0/teams/', variables('varTeamId'),"
                    " '/channels/', uriComponent(variables('varChannelId')), '/messages?$top=50')")
s10 = {}
s10["Set_NextLink_First"] = {"type": "SetVariable", "inputs": {"name": "varNextLink", "value": graph_msgs_first}, "runAfter": {}}
do_msgs = {
    "type": "Until",
    "expression": "@empty(variables('varNextLink'))",
    "limit": {"count": 5000, "timeout": "PT1H"},
    "actions": {
        "Get_Channel_Messages": oac(H_TEAMS, "HttpRequest", {
            "Uri": "@variables('varNextLink')", "Method": "GET", "ContentType": "application/json"}),
        # SetVariable の自己参照（union(varMessagesArray自身, ...)）は保存不可のため、
        # 取得ページの value 配列を Apply to each で1件ずつ Append する方式に変更。
        "Process_Retrieved_Messages": {"type": "Foreach",
            "foreach": "@coalesce(body('Get_Channel_Messages')?['value'], json('[]'))",
            "actions": {
                "Append_Message_To_MessagesArray": {"type": "AppendToArrayVariable",
                    "inputs": {"name": "varMessagesArray", "value": "@item()"}, "runAfter": {}},
            },
            "runtimeConfiguration": {"concurrency": {"repetitions": 1}},
            "runAfter": {"Get_Channel_Messages": ["Succeeded"]}},
        "Set_NextLink": {"type": "SetVariable",
            "inputs": {"name": "varNextLink", "value": "@coalesce(body('Get_Channel_Messages')?['@odata.nextLink'], '')"},
            "runAfter": {"Process_Retrieved_Messages": ["Succeeded"]}},
    },
    "runAfter": {"Set_NextLink_First": ["Succeeded"]},
}
s10["Do_Until_Messages_Paging"] = do_msgs
# =========================================================================
# v10: Scope_05_Ensure_Destination_Folder（保存先フォルダの事前確保）
# CreateFile は中間フォルダを自動作成しないため、実行冒頭に1回だけフォルダ階層を
# 作成（既存ならエラー→[Succeeded,Failed]で継続＝リスト作成フローの実証パターン）し、
# 最後に GET で実在検証する。検証失敗＝保存先パス/権限の問題を実行の早期に明確に失敗させる
# （従来の「全添付が黙々とFailed」を防ぐ）。DryRun=はい のときは何もしない（実フォルダを汚さない）。
# ServerRelativeUrl はフルサーバー相対（uriPath(サイトURL)+…）で構築する
# （先頭スラッシュのサイト相対はテナントルート基準に誤解決されるため）。
# 保存先パスは最大4階層まで対応（4階層未満は同一フォルダへの重複POSTになるだけで無害）。
# =========================================================================
def _folder_body(n):
    """N階層目までのフォルダ作成ボディ（verbose・SP.Folder）"""
    seg = "join(take(split(variables('varDestinationPath'), '/'), " + str(n) + "), '/')"
    url_expr = ("@{concat(uriPath(variables('varSiteAddress')), '/', variables('varLibrary'), '/', "
                + seg + ")}")
    return json.dumps({"__metadata": {"type": "SP.Folder"}, "ServerRelativeUrl": url_expr},
                      ensure_ascii=False)

def _sp_http(method, uri, headers, body=None):
    params = {"dataset": "@variables('varSiteAddress')", "parameters/method": method,
              "parameters/uri": uri, "parameters/headers": headers}
    if body is not None:
        params["parameters/body"] = body
    return {"type": "OpenApiConnection",
            "inputs": {"parameters": params,
                       "host": {"apiId": "/providers/Microsoft.PowerApps/apis/shared_sharepointonline",
                                "connectionName": "shared_sharepointonline", "operationId": "HttpRequest"},
                       "authentication": AUTH},
            "runAfter": {}}

_H_VERBOSE = {"Accept": "application/json;odata=verbose", "Content-Type": "application/json;odata=verbose"}
s05_inner = {}
prev_f = None
for n in (1, 2, 3, 4):
    name = "Create_Destination_Folder_L" + str(n)
    s05_inner[name] = _sp_http("POST", "_api/web/folders", dict(_H_VERBOSE), _folder_body(n))
    # 既存フォルダ等での失敗を許容して次の階層へ進む（真偽は最後のGETで確定）
    s05_inner[name]["runAfter"] = {} if prev_f is None else {prev_f: ["Succeeded", "Failed"]}
    prev_f = name
s05_inner["Verify_Destination_Folder"] = _sp_http(
    "GET",
    ("@concat('_api/web/GetFolderByServerRelativeUrl(''', uriPath(variables('varSiteAddress')), '/',"
     " variables('varLibrary'), '/', variables('varDestinationPath'), ''')')"),
    {"Accept": "application/json;odata=nometadata"})
s05_inner["Verify_Destination_Folder"]["runAfter"] = {prev_f: ["Succeeded", "Failed"]}

actions["Scope_05_Ensure_Destination_Folder"] = {"type": "Scope", "actions": {
    "Condition_Provision_Destination": {"type": "If",
        "expression": {"and": [{"not": {"equals": ["@coalesce(triggerBody()?['DryRun'], true)", True]}}]},
        "actions": s05_inner,
        "runAfter": {}},
}, "runAfter": ra(last_init)}

actions["Scope_10_Get_Channel_Messages"] = {"type": "Scope", "actions": s10,
    "runAfter": ra("Scope_05_Ensure_Destination_Folder")}

# =========================================================================
# Scope_20_Process_Meetings : 期間絞込 → 会議ごと処理（返信・添付・正規化）
# =========================================================================
period_where = ("@and(equals(item()?['messageType'], 'message'),"
                " and(greaterOrEquals(item()?['createdDateTime'], variables('varStartDateUtc')),"
                " lessOrEquals(item()?['createdDateTime'], variables('varEndDateUtc'))))")

# 返信ページング（会議ループ内）
# チャネルIDとメッセージIDを uriComponent() でエンコード（実働サンプルは
# uriComponent(メッセージID) を使用。メッセージIDは数値文字列だが安全側に統一）。
graph_replies_first = ("@concat('https://graph.microsoft.com/v1.0/teams/', variables('varTeamId'),"
                       " '/channels/', uriComponent(variables('varChannelId')), '/messages/',"
                       " uriComponent(items('Process_Each_Parent_Message')?['id']), '/replies?$top=50')")

# 添付候補の作成（親＋返信）。Select で sourceReplyId を付与
sel_parent = {"type": "Select",
    "inputs": {"from": "@coalesce(items('Process_Each_Parent_Message')?['attachments'], json('[]'))",
               "select": {"attachment": "@item()", "sourceReplyId": ""}}}
process_each_reply = {
    "type": "Foreach",
    "foreach": "@variables('varRepliesArray')",
    "actions": {
        "Select_Reply_Attachments": {"type": "Select",
            "inputs": {"from": "@coalesce(items('Process_Each_Reply')?['attachments'], json('[]'))",
                       "select": {"attachment": "@item()", "sourceReplyId": "@items('Process_Each_Reply')?['id']"}},
            "runAfter": {}},
        # 自己参照除去: Select結果（配列）を Apply to each で1件ずつ Append する。
        "Process_Each_Reply_Attachment": {"type": "Foreach",
            "foreach": "@body('Select_Reply_Attachments')",
            "actions": {
                "Append_Reply_Attachment_Candidate": {"type": "AppendToArrayVariable",
                    "inputs": {"name": "varAttachmentCandidates", "value": "@item()"}, "runAfter": {}},
            },
            "runtimeConfiguration": {"concurrency": {"repetitions": 1}},
            "runAfter": {"Select_Reply_Attachments": ["Succeeded"]}},
    },
    "runtimeConfiguration": {"concurrency": {"repetitions": 1}},
    "runAfter": {"Do_Until_Replies_Paging": ["Succeeded"]},
}

# 添付フィルタ（ファイル参照のみ。カード/画像/会議リンク除外）
# v9: contentUrl が「/Shared Documents/」（チームサイトの既定ライブラリ）を含む添付のみ収集対象にする。
# Teamsチャネルの添付は必ずチームサイトの Shared Documents 配下に保存される（実応答で確認）。
# 外部リンク・タブ参照等の reference 添付を除外し、取得404（不要なエラー）を根絶する。
# v10: Graphは%エンコード済みURLも返すため '/Shared%20Documents/' も許可
# （エンコード済み文書が黙って除外される取りこぼしを防ぐ）
filter_file_att = {"type": "Query",
    "inputs": {"from": "@variables('varAttachmentCandidates')",
               "where": ("@and(and(equals(item()?['attachment']?['contentType'], 'reference'),"
                         " not(empty(coalesce(item()?['attachment']?['contentUrl'], '')))),"
                         " or(contains(coalesce(item()?['attachment']?['contentUrl'], ''), '/Shared Documents/'),"
                         " contains(coalesce(item()?['attachment']?['contentUrl'], ''), '/Shared%20Documents/')))")},
    "runAfter": {"Process_Each_Reply": ["Succeeded"]}}

# --- Scope_30_Save_Attachments（会議ループ内） ---
idem_key = ("@if(empty(trim(coalesce(items('Process_Each_Attachment')?['sourceReplyId'], ''))),"
            " concat(items('Process_Each_Parent_Message')?['id'], '_', items('Process_Each_Attachment')?['attachment']?['id']),"
            " concat(items('Process_Each_Parent_Message')?['id'], '_', items('Process_Each_Attachment')?['sourceReplyId'], '_', items('Process_Each_Attachment')?['attachment']?['id']))")
# 埋め込み用（他の @式 の内側に連結する。先頭 @ を付けない＝入れ子関数として正当）
orig_name_expr = "coalesce(items('Process_Each_Attachment')?['attachment']?['name'], 'file')"
# 単独の式値用（プロパティ値としてそのまま評価させる＝先頭 @ が必要）
orig_name = "@" + orig_name_expr

# ファイル名正規化（禁止文字→_ を replace 連鎖。Compose分割）
save_att_actions = {}
save_att_actions["Compose_IdempotencyKey"] = {"type": "Compose", "inputs": idem_key, "runAfter": {}}
save_att_actions["Get_Ledger_Existing"] = oac(H_SPO, "GetItems", {
    # v8: 台帳リストはファイル保存先と別サイト（varListSiteAddress）
    "dataset": "@variables('varListSiteAddress')", "table": "@variables('varLedgerList')",
    "$filter": "@concat('IdempotencyKey eq ''', outputs('Compose_IdempotencyKey'), ''' and Status eq ''Saved''')", "$top": 1})
save_att_actions["Get_Ledger_Existing"]["runAfter"] = {"Compose_IdempotencyKey": ["Succeeded"]}

# ファイル名構築
save_att_actions["Compose_Extension"] = {"type": "Compose",
    "inputs": "@if(contains(" + orig_name_expr + ", '.'), concat('.', last(split(" + orig_name_expr + ", '.'))), '')",
    "runAfter": {"Get_Ledger_Existing": ["Succeeded"]}}
save_att_actions["Compose_BaseName"] = {"type": "Compose",
    "inputs": ("@if(contains(" + orig_name_expr + ", '.'),"
               " substring(" + orig_name_expr + ", 0, sub(length(" + orig_name_expr + "), length(outputs('Compose_Extension')))),"
               " " + orig_name_expr + ")"),
    "runAfter": {"Compose_Extension": ["Succeeded"]}}
# 禁止文字 " * : < > ? / \ | を _ へ
repl_chain = [
    ("Replace_Invalid_Quote",     "outputs('Compose_BaseName')", '"'),
    ("Replace_Invalid_Star",      "outputs('Replace_Invalid_Quote')", '*'),
    ("Replace_Invalid_Colon",     "outputs('Replace_Invalid_Star')", ':'),
    ("Replace_Invalid_Lt",        "outputs('Replace_Invalid_Colon')", '<'),
    ("Replace_Invalid_Gt",        "outputs('Replace_Invalid_Lt')", '>'),
    ("Replace_Invalid_Question",  "outputs('Replace_Invalid_Gt')", '?'),
    ("Replace_Invalid_Slash",     "outputs('Replace_Invalid_Question')", '/'),
    ("Replace_Invalid_Backslash", "outputs('Replace_Invalid_Slash')", '\\'),
    ("Replace_Invalid_Pipe",      "outputs('Replace_Invalid_Backslash')", '|'),
    # v10: 保存後URLを決定的に構築するため # と % も除去
    # （# はURLフラグメント切断、% は不正エスケープの原因になる）
    ("Replace_Invalid_Hash",      "outputs('Replace_Invalid_Pipe')", '#'),
    ("Replace_Invalid_Percent",   "outputs('Replace_Invalid_Hash')", '%'),
]
prev_r = "Compose_BaseName"
for cname, src, ch in repl_chain:
    save_att_actions[cname] = {"type": "Compose",
        "inputs": "@replace(" + src + ", '" + (ch if ch != "'" else "''") + "', '_')",
        "runAfter": {prev_r: ["Succeeded"]}}
    prev_r = cname
# 末尾空白/ピリオド除去
save_att_actions["Compose_TrimTrailing"] = {"type": "Compose",
    "inputs": ("@if(endsWith(trim(outputs('Replace_Invalid_Percent')), '.'),"
               " trim(substring(trim(outputs('Replace_Invalid_Percent')), 0, sub(length(trim(outputs('Replace_Invalid_Percent'))), 1))),"
               " trim(outputs('Replace_Invalid_Percent')))"),
    "runAfter": {"Replace_Invalid_Percent": ["Succeeded"]}}
save_att_actions["Compose_SavedName"] = {"type": "Compose",
    "inputs": ("@concat(formatDateTime(items('Process_Each_Parent_Message')?['createdDateTime'], 'yyyyMMdd'), '_',"
               " if(greater(length(outputs('Compose_TrimTrailing')), 100), substring(outputs('Compose_TrimTrailing'), 0, 100), outputs('Compose_TrimTrailing')),"
               " outputs('Compose_Extension'))"),
    "runAfter": {"Compose_TrimTrailing": ["Succeeded"]}}

# 冪等性判定 → 保存 or 再利用
# Scope_Save_File には失敗しうる危険操作のみを入れ、その Failed/TimedOut を
# 後続ハンドラで吸収して1件失敗でも会議処理を継続する（Status=Failed記録）。
# v9: 添付の取得元サイト・パスを contentUrl 自体から導出する（実環境404の根本修正）。
# 実応答の contentUrl 例: https://.../teams/{teamSite}/Shared Documents/{channel}/{file}
# 旧実装は dataset=varSiteAddress（mROOM=ファイル保存先サイト）に対して
# サイト接頭辞付きパスを渡しており、別サイト参照で 404 File not found になっていた。
# 「/Shared Documents/」の位置で分割: 前半=サイトURL、後半=サイト相対パス。
_cu = "items('Process_Each_Attachment')?['attachment']?['contentUrl']"
# v10: Graphは%エンコード済みcontentUrlも返す実例があるため、まず正規化してから分割する。
# エンコード判定は '/Shared%20Documents/' 含有に限定（生URLのファイル名にリテラル%が
# あっても誤デコードしない）。
scope_save_file = {"type": "Scope", "runAfter": {}, "actions": {
    "Compose_Source_Url": {"type": "Compose",
        "inputs": ("@if(contains(coalesce(" + _cu + ", ''), '/Shared%20Documents/'),"
                   " decodeUriComponent(" + _cu + "), " + _cu + ")"),
        "runAfter": {}},
    "Compose_Source_Site": {"type": "Compose",
        "inputs": "@substring(outputs('Compose_Source_Url'), 0, indexOf(outputs('Compose_Source_Url'), '/Shared Documents/'))",
        "runAfter": {"Compose_Source_Url": ["Succeeded"]}},
    "Compose_Source_Path": {"type": "Compose",
        "inputs": "@replace(substring(outputs('Compose_Source_Url'), indexOf(outputs('Compose_Source_Url'), '/Shared Documents/')), '%20', ' ')",
        "runAfter": {"Compose_Source_Site": ["Succeeded"]}},
    "Get_Source_File_Content": oac(H_SPO, "GetFileContentByPath", {
        "dataset": "@outputs('Compose_Source_Site')",
        "path": "@outputs('Compose_Source_Path')",
        "inferContentType": True}),
    "Create_Attachment_File": oac(H_SPO, "CreateFile", {
        "dataset": "@variables('varSiteAddress')",
        "folderPath": "@concat('/', variables('varLibrary'), '/', variables('varDestinationPath'))",
        "name": "@outputs('Compose_SavedName')",
        "body": "@body('Get_Source_File_Content')"}),
    # v10: GetFileItem（{Link}取得）は廃止。
    # 理由: table にはライブラリの表示名/GUIDが必要で、"Shared Documents"（URLセグメント）では
    # 日本語サイト（表示名「ドキュメント」）で名前解決に失敗する＝全件Failedの最有力候補。
    # 保存後URLは CreateFile 成功が保証する既知の値（サイト+ライブラリ+パス+ファイル名）から
    # 決定的に構築する（Compose_Saved_File_Url。save_real_branch 参照）。
}}
scope_save_file["actions"]["Get_Source_File_Content"]["runAfter"] = {"Compose_Source_Path": ["Succeeded"]}
scope_save_file["actions"]["Create_Attachment_File"]["runAfter"] = {"Get_Source_File_Content": ["Succeeded"]}

# 台帳項目のボディ（REST用の前段Composeオブジェクト。item/ 接頭辞なしの内部列名。
# 数値・日時は式のまま渡し、string() でJSON化される際に正しい型で出力される）
ledger_body = lambda status, saved_name, saved_url, err: {
    "Title": "@outputs('Compose_IdempotencyKey')",
    "IdempotencyKey": "@outputs('Compose_IdempotencyKey')",
    "RunId": "@variables('varRunId')",
    "MessageId": "@items('Process_Each_Parent_Message')?['id']",
    "ReplyId": "@coalesce(items('Process_Each_Attachment')?['sourceReplyId'], '')",
    "AttachmentId": "@items('Process_Each_Attachment')?['attachment']?['id']",
    "OriginalFileName": orig_name,
    "SavedFileName": saved_name, "SavedFileUrl": saved_url,
    "Status": status, "ErrorMessage": err,
    "ProcessedDateTimeUtc": "@utcNow()"}

# v10: 保存後URLは応答に依存せず、既知の値から決定的に構築する
# （CreateFile成功＝このパス・名前で作成された、の直接証明。{Link}の不確実性を全廃）。
# Scope_Save_File の前に置く＝失敗ハンドラからも常に参照可能。
saved_file_url_expr = ("@replace(concat(variables('varSiteAddress'), '/', variables('varLibrary'), '/',"
                       " variables('varDestinationPath'), '/', outputs('Compose_SavedName')), ' ', '%20')")
# v10: 失敗時の台帳ErrorMessageに自己診断情報（元URL・保存先）を埋め込む。
# 導出Compose（Scope内）は参照しない＝Compose段で失敗しても封じ込めが壊れない。
failed_msg_expr = ("@concat('添付の保存に失敗しました: ', outputs('Compose_SavedName'),"
                   " ' 元URL=', coalesce(" + _cu + ", '(なし)'),"
                   " ' 保存先=/', variables('varLibrary'), '/', variables('varDestinationPath'))")

# 保存の実処理ブランチ（Condition_DryRun の else）
save_real_branch = {
    "Compose_Saved_File_Url": {"type": "Compose", "inputs": saved_file_url_expr, "runAfter": {}},
    "Scope_Save_File": scope_save_file,
    # 成功ハンドラ（Scope_Save_File 成功後）: Composeでボディ構築→RESTで台帳へ登録
    "Compose_Ledger_Body": {"type": "Compose",
        "inputs": ledger_body("Saved", "@outputs('Compose_SavedName')", "@outputs('Compose_Saved_File_Url')", "")},
    "Create_Ledger_Item": sp_rest_post_item("varLedgerList", "Compose_Ledger_Body"),
    "Append_Saved_Meeting_Attachment": {"type": "AppendToArrayVariable", "inputs": {"name": "varMeetingAttachments", "value": {
        "originalName": orig_name, "savedName": "@outputs('Compose_SavedName')",
        "savedFileUrl": "@outputs('Compose_Saved_File_Url')", "status": "Saved"}}},
    "Increment_SavedCount": {"type": "IncrementVariable", "inputs": {"name": "varSavedCount", "value": 1}},
    # 失敗ハンドラ（Scope_Save_File の Failed/TimedOut を吸収→継続。Status=Failed記録）
    "Append_Failed_Meeting_Attachment": {"type": "AppendToArrayVariable", "inputs": {"name": "varMeetingAttachments", "value": {
        "originalName": orig_name, "savedName": "", "savedFileUrl": "", "status": "Failed"}}},
    "Compose_LedgerFailed_Body": {"type": "Compose",
        "inputs": ledger_body("Failed", "", "", failed_msg_expr)},
    "Create_Ledger_Item_Failed": sp_rest_post_item("varLedgerList", "Compose_LedgerFailed_Body"),
    "Increment_FailedCount": {"type": "IncrementVariable", "inputs": {"name": "varFailedCount", "value": 1}},
}
save_real_branch["Scope_Save_File"]["runAfter"] = {"Compose_Saved_File_Url": ["Succeeded"]}
save_real_branch["Compose_Ledger_Body"]["runAfter"] = {"Scope_Save_File": ["Succeeded"]}
save_real_branch["Create_Ledger_Item"]["runAfter"] = {"Compose_Ledger_Body": ["Succeeded"]}
save_real_branch["Append_Saved_Meeting_Attachment"]["runAfter"] = {"Create_Ledger_Item": ["Succeeded"]}
save_real_branch["Increment_SavedCount"]["runAfter"] = {"Append_Saved_Meeting_Attachment": ["Succeeded"]}
save_real_branch["Append_Failed_Meeting_Attachment"]["runAfter"] = {"Scope_Save_File": ["Failed", "TimedOut"]}
save_real_branch["Compose_LedgerFailed_Body"]["runAfter"] = {"Append_Failed_Meeting_Attachment": ["Succeeded"]}
save_real_branch["Create_Ledger_Item_Failed"]["runAfter"] = {"Compose_LedgerFailed_Body": ["Succeeded"]}
save_real_branch["Increment_FailedCount"]["runAfter"] = {"Create_Ledger_Item_Failed": ["Succeeded"]}

# DryRun分岐: true=保存せずSkipped、false=実保存ブランチ
cond_dryrun = {"type": "If",
    "expression": {"and": [{"equals": ["@coalesce(triggerBody()?['DryRun'], true)", True]}]},
    "actions": {
        "Append_DryRun_Meeting_Attachment": {"type": "AppendToArrayVariable",
            "inputs": {"name": "varMeetingAttachments", "value": {
                "originalName": orig_name, "savedName": "", "savedFileUrl": "", "status": "Skipped"}}, "runAfter": {}},
        "Increment_SkippedCount_DryRun": {"type": "IncrementVariable",
            "inputs": {"name": "varSkippedCount", "value": 1},
            "runAfter": {"Append_DryRun_Meeting_Attachment": ["Succeeded"]}},
    },
    "else": {"actions": save_real_branch},
    "runAfter": {"Compose_SavedName": ["Succeeded"]}}

# 冪等性: 既存Saved かつ ForceReprocess=false なら再利用（Skipped）
cond_idem = {"type": "If",
    "expression": {"and": [
        {"greater": ["@length(coalesce(body('Get_Ledger_Existing')?['value'], json('[]')))", 0]},
        {"not": {"equals": ["@coalesce(triggerBody()?['ForceReprocess'], false)", True]}}
    ]},
    "actions": {  # 再利用
        "Append_Existing_Meeting_Attachment": {"type": "AppendToArrayVariable",
            "inputs": {"name": "varMeetingAttachments", "value": {
                "originalName": orig_name,
                "savedName": "@first(body('Get_Ledger_Existing')?['value'])?['SavedFileName']",
                "savedFileUrl": "@first(body('Get_Ledger_Existing')?['value'])?['SavedFileUrl']",
                "status": "Skipped"}}, "runAfter": {}},
        "Increment_SkippedCount_Existing": {"type": "IncrementVariable",
            "inputs": {"name": "varSkippedCount", "value": 1},
            "runAfter": {"Append_Existing_Meeting_Attachment": ["Succeeded"]}},
    },
    "else": {"actions": {
        "Compose_Extension": save_att_actions["Compose_Extension"],
        "Compose_BaseName": save_att_actions["Compose_BaseName"],
        **{k: save_att_actions[k] for k, _, _ in repl_chain},
        "Compose_TrimTrailing": save_att_actions["Compose_TrimTrailing"],
        "Compose_SavedName": save_att_actions["Compose_SavedName"],
        "Condition_DryRun": cond_dryrun,
    }},
    "runAfter": {"Get_Ledger_Existing": ["Succeeded"]}}
# else内先頭アクションの runAfter を初期化（Compose_Extension は分岐先頭）
cond_idem["else"]["actions"]["Compose_Extension"] = dict(save_att_actions["Compose_Extension"]); cond_idem["else"]["actions"]["Compose_Extension"]["runAfter"] = {}

process_each_attachment = {
    "type": "Foreach",
    "foreach": "@body('Filter_File_Attachments')",
    "actions": {
        "Compose_IdempotencyKey": save_att_actions["Compose_IdempotencyKey"],
        "Get_Ledger_Existing": save_att_actions["Get_Ledger_Existing"],
        "Condition_Already_Saved": cond_idem,
    },
    "runtimeConfiguration": {"concurrency": {"repetitions": 1}},
    "runAfter": {},
}
# v9: Scope_30_Save_Attachments（Scope）→ Condition_Has_File_Attachments（If）に置換。
# 親・返信を問わず添付の有無を明示的に確認し、添付がある場合のみ収集ブロックを実行する
# （ユーザー提案）。Scopeのまま外側にIfを足すとネスト深さ上限8を超えるため、
# Scope自体を条件分岐へ置き換えることで深さを維持する。
cond_has_attachments = {"type": "If",
    "expression": {"and": [{"greater": ["@length(body('Filter_File_Attachments'))", 0]}]},
    "actions": {"Process_Each_Attachment": process_each_attachment},
    "runAfter": {"Filter_File_Attachments": ["Succeeded"]}}

# --- 会議ループ本体 ---
author_expr = ("@if(empty(trim(coalesce(items('Process_Each_Parent_Message')?['from']?['user']?['displayName'], ''))),"
               " '不明', trim(coalesce(items('Process_Each_Parent_Message')?['from']?['user']?['displayName'], '')))")
meeting_date = "@formatDateTime(convertFromUtc(items('Process_Each_Parent_Message')?['createdDateTime'], 'Tokyo Standard Time'), 'yyyy-MM-dd')"
posted_jst = "@concat(formatDateTime(convertFromUtc(items('Process_Each_Parent_Message')?['createdDateTime'], 'Tokyo Standard Time'), 'yyyy-MM-ddTHH:mm:ss'), '+09:00')"
sort_key = ("@concat(formatDateTime(convertFromUtc(items('Process_Each_Parent_Message')?['createdDateTime'], 'Tokyo Standard Time'), 'yyyyMMddHHmmss'),"
            " '_', items('Process_Each_Parent_Message')?['id'])")

pep_actions = {}
pep_actions["Compose_Author"]   = {"type": "Compose", "inputs": author_expr, "runAfter": {}}
pep_actions["Compose_Organizer"]= {"type": "Compose", "inputs": "不明", "runAfter": {"Compose_Author": ["Succeeded"]}}
pep_actions["Compose_MeetingDate"] = {"type": "Compose", "inputs": meeting_date, "runAfter": {"Compose_Organizer": ["Succeeded"]}}
pep_actions["Compose_PostedDateTimeJst"] = {"type": "Compose", "inputs": posted_jst, "runAfter": {"Compose_MeetingDate": ["Succeeded"]}}
pep_actions["Convert_Body_Html_To_Text"] = oac(H_CONV, "HtmlToText",
    {"Content": "@coalesce(items('Process_Each_Parent_Message')?['body']?['content'], '')"})
pep_actions["Convert_Body_Html_To_Text"]["runAfter"] = {"Compose_PostedDateTimeJst": ["Succeeded"]}
pep_actions["Set_ReplyNextLink_First"] = {"type": "SetVariable", "inputs": {"name": "varReplyNextLink", "value": graph_replies_first}, "runAfter": {"Convert_Body_Html_To_Text": ["Succeeded"]}}
pep_actions["Set_RepliesArray_Reset"] = {"type": "SetVariable", "inputs": {"name": "varRepliesArray", "value": "@json('[]')"}, "runAfter": {"Set_ReplyNextLink_First": ["Succeeded"]}}
pep_actions["Do_Until_Replies_Paging"] = {
    "type": "Until", "expression": "@empty(variables('varReplyNextLink'))",
    "limit": {"count": 5000, "timeout": "PT1H"},
    "actions": {
        "Get_Message_Replies": oac(H_TEAMS, "HttpRequest", {"Uri": "@variables('varReplyNextLink')", "Method": "GET", "ContentType": "application/json"}),
        # 自己参照除去: 返信ページの value 配列を Apply to each で1件ずつ Append する。
        "Process_Retrieved_Replies": {"type": "Foreach",
            "foreach": "@coalesce(body('Get_Message_Replies')?['value'], json('[]'))",
            "actions": {
                "Append_Reply_To_RepliesArray": {"type": "AppendToArrayVariable",
                    "inputs": {"name": "varRepliesArray", "value": "@item()"}, "runAfter": {}},
            },
            "runtimeConfiguration": {"concurrency": {"repetitions": 1}},
            "runAfter": {"Get_Message_Replies": ["Succeeded"]}},
        "Set_ReplyNextLink": {"type": "SetVariable", "inputs": {"name": "varReplyNextLink", "value": "@coalesce(body('Get_Message_Replies')?['@odata.nextLink'], '')"}, "runAfter": {"Process_Retrieved_Replies": ["Succeeded"]}},
    },
    "runAfter": {"Set_RepliesArray_Reset": ["Succeeded"]}}
pep_actions["Set_AttachmentCandidates_Parent"] = {"type": "SetVariable", "inputs": {"name": "varAttachmentCandidates", "value": "@body('Select_Parent_Attachments')"}, "runAfter": {"Select_Parent_Attachments": ["Succeeded"]}}
pep_actions["Select_Parent_Attachments"] = dict(sel_parent); pep_actions["Select_Parent_Attachments"]["runAfter"] = {"Do_Until_Replies_Paging": ["Succeeded"]}
pep_actions["Process_Each_Reply"] = dict(process_each_reply); pep_actions["Process_Each_Reply"]["runAfter"] = {"Set_AttachmentCandidates_Parent": ["Succeeded"]}
pep_actions["Filter_File_Attachments"] = dict(filter_file_att)
pep_actions["Set_MeetingAttachments_Reset"] = {"type": "SetVariable", "inputs": {"name": "varMeetingAttachments", "value": "@json('[]')"}, "runAfter": {"Filter_File_Attachments": ["Succeeded"]}}
cond_har = dict(cond_has_attachments); cond_har["runAfter"] = {"Set_MeetingAttachments_Reset": ["Succeeded"]}
pep_actions["Condition_Has_File_Attachments"] = cond_har
pep_actions["Compose_SortKey"] = {"type": "Compose", "inputs": sort_key, "runAfter": {"Condition_Has_File_Attachments": ["Succeeded"]}}
pep_actions["Append_Normalized_Meeting"] = {"type": "AppendToArrayVariable", "inputs": {"name": "varMeetings", "value": {
    "meetingDate": "@outputs('Compose_MeetingDate')",
    "postedDateTimeJst": "@outputs('Compose_PostedDateTimeJst')",
    "messageId": "@items('Process_Each_Parent_Message')?['id']",
    "author": "@outputs('Compose_Author')",
    "organizer": "@outputs('Compose_Organizer')",
    "bodyText": "@body('Convert_Body_Html_To_Text')",
    "teamsMessageUrl": "@coalesce(items('Process_Each_Parent_Message')?['webUrl'], '')",
    "attachments": "@variables('varMeetingAttachments')",
    "sortKey": "@outputs('Compose_SortKey')"}}, "runAfter": {"Compose_SortKey": ["Succeeded"]}}

process_each_parent = {"type": "Foreach", "foreach": "@body('Filter_Messages_By_Period')",
    "actions": pep_actions, "runtimeConfiguration": {"concurrency": {"repetitions": 1}},
    "runAfter": {"Filter_Messages_By_Period": ["Succeeded"]}}

s20 = {
    "Filter_Messages_By_Period": {"type": "Query", "inputs": {"from": "@variables('varMessagesArray')", "where": period_where}, "runAfter": {}},
    "Process_Each_Parent_Message": process_each_parent,
}
actions["Scope_20_Process_Meetings"] = {"type": "Scope", "actions": s20, "runAfter": ra("Scope_10_Get_Channel_Messages")}

# =========================================================================
# Scope_40_Sort_Meetings : sort() でsortKey昇順
# =========================================================================
s40 = {"Sort_Meetings": {"type": "SetVariable",
        "inputs": {"name": "varSortedMeetings", "value": "@sort(variables('varMeetings'), 'sortKey')"}, "runAfter": {}}}
actions["Scope_40_Sort_Meetings"] = {"type": "Scope", "actions": s40, "runAfter": ra("Scope_20_Process_Meetings")}

# =========================================================================
# Scope_50_Build_Word_Content : Word用HTML生成
# =========================================================================
HTML_HEAD = ('<html><head><meta charset="utf-8"><style>'
             '@page { size: A4; margin: 20mm; }'
             ' body { font-family: "Yu Gothic","Meiryo",sans-serif; font-size: 10.5pt; }'
             ' .page-break { page-break-before: always; }'
             ' .meeting-title { font-size: 16pt; font-weight: bold; }'
             ' .label { font-weight: bold; }'
             ' .attachment-list { margin-top: 8px; }'
             '</style></head><body>')

# 添付リンク（保存後URL）。成功=リンク、失敗=（保存失敗）
# href内のURLは & を &amp; にエスケープ（HTML属性値としての堅牢化）
att_link_true = ("@concat('<div><a href=\"', replace(coalesce(item()?['savedFileUrl'], ''), '&', '&amp;'), '\">',"
                 " replace(replace(replace(replace(replace(coalesce(item()?['savedName'], ''), '&', '&amp;'), '<', '&lt;'), '>', '&gt;'), '\"', '&quot;'), '''', '&#39;'),"
                 " '</a></div>')")
att_link_false = ("@concat('<div>',"
                  " replace(replace(replace(replace(replace(coalesce(item()?['originalName'], ''), '&', '&amp;'), '<', '&lt;'), '>', '&gt;'), '\"', '&quot;'), '''', '&#39;'),"
                  " if(equals(coalesce(item()?['status'], ''), 'Failed'), '（保存失敗）', '（テスト実行のため未保存）'),"
                  " '</div>')")
# HTMLの連結は「文字列変数に追加」(AppendToStringVariable) を使用（自己参照concat禁止）。
# ネストしたForeachの入力は外側ループ項目を items('Apply_To_Each_Sorted_Meeting') で明示参照。
apply_saved_att = {"type": "Foreach", "foreach": "@coalesce(items('Apply_To_Each_Sorted_Meeting')?['attachments'], json('[]'))",
    "actions": {
        "Condition_Attachment_Saved": {"type": "If",
            "expression": {"and": [{"greater": ["@length(coalesce(item()?['savedFileUrl'], ''))", 0]}]},
            "actions": {"Append_Attachment_Html": {"type": "AppendToStringVariable", "inputs": {"name": "varDocumentHtml", "value": att_link_true}, "runAfter": {}}},
            "else": {"actions": {"Append_Attachment_Failed_Html": {"type": "AppendToStringVariable", "inputs": {"name": "varDocumentHtml", "value": att_link_false}, "runAfter": {}}}},
            "runAfter": {}}},
    "runtimeConfiguration": {"concurrency": {"repetitions": 1}}, "runAfter": {}}

# 会議ごとHTML（Append を varDocumentHtml へ）。改ページは2件目以降のみ
esc = [("Escape_Ampersand", "item()?['bodyText']", '&', '&amp;'),
       ("Escape_LessThan", "outputs('Escape_Ampersand')", '<', '&lt;'),
       ("Escape_GreaterThan", "outputs('Escape_LessThan')", '>', '&gt;'),
       ("Escape_DoubleQuote", "outputs('Escape_GreaterThan')", '"', '&quot;'),
       ("Escape_SingleQuote", "outputs('Escape_DoubleQuote')", "'", '&#39;')]
apply_sorted = {"type": "Foreach", "foreach": "@variables('varSortedMeetings')", "actions": {}, "runtimeConfiguration": {"concurrency": {"repetitions": 1}}, "runAfter": {"Append_DocumentHtml_Header": ["Succeeded"]}}
asa = apply_sorted["actions"]
asa["Condition_Insert_Page_Break"] = {"type": "If", "expression": {"and": [{"greater": ["@variables('varMeetingIndex')", 0]}]},
    "actions": {"Append_Page_Break": {"type": "AppendToStringVariable", "inputs": {"name": "varDocumentHtml", "value": '<div style="page-break-before: always;"></div>'}, "runAfter": {}}},
    "runAfter": {}}
prev_e = "Condition_Insert_Page_Break"
for cname, src, ch, rep in esc:
    ch_lit = "''" if ch == "'" else ch
    asa[cname] = {"type": "Compose", "inputs": "@replace(coalesce(" + (src if src.startswith("item") else src) + ", ''), '" + ch_lit + "', '" + rep + "')", "runAfter": {prev_e: ["Succeeded"]}}
    prev_e = cname
# 改行→<br>
asa["Compose_Body_With_Breaks"] = {"type": "Compose",
    "inputs": "@replace(replace(outputs('Escape_SingleQuote'), decodeUriComponent('%0D%0A'), '<br>'), decodeUriComponent('%0A'), '<br>')",
    "runAfter": {"Escape_SingleQuote": ["Succeeded"]}}
# 会議日付表示（曜日）
# 曜日: 配列の計算インデックス角括弧アクセス（json('[...]')[dayOfWeek(...)]）は
# デザイナー式エディタで不安定になり得るため、substring による位置取得に変更。
# dayOfWeek() は 0=日曜〜6=土曜 を返す。
weekday = "substring('日月火水木金土', dayOfWeek(item()?['meetingDate']), 1)"
asa["Compose_Meeting_Header_Html"] = {"type": "Compose",
    "inputs": ("@concat('<div class=\"meeting-title\">', formatDateTime(item()?['meetingDate'], 'yyyy年M月d日'), '（', " + weekday + ", '）</div>',"
               " '<div><span class=\"label\">投稿者：</span>', item()?['author'], '</div>',"
               " '<div><span class=\"label\">主催者：</span>', item()?['organizer'], '</div>',"
               " '<div><span class=\"label\">投稿日時：</span>', item()?['postedDateTimeJst'], '</div>',"
               " '<div><span class=\"label\">内容：</span></div>',"
               " '<div>', outputs('Compose_Body_With_Breaks'), '</div>',"
               " '<div class=\"attachment-list\"><span class=\"label\">添付ファイル：</span></div>')"),
    "runAfter": {"Compose_Body_With_Breaks": ["Succeeded"]}}
asa["Append_Meeting_Header_Html"] = {"type": "AppendToStringVariable", "inputs": {"name": "varDocumentHtml", "value": "@outputs('Compose_Meeting_Header_Html')"}, "runAfter": {"Compose_Meeting_Header_Html": ["Succeeded"]}}
# 添付一覧（0件は「添付ファイルなし」）
asa["Condition_Has_Attachments"] = {"type": "If", "expression": {"and": [{"greater": ["@length(coalesce(item()?['attachments'], json('[]')))", 0]}]},
    "actions": {"Apply_To_Each_Saved_Attachment": dict(apply_saved_att, runAfter={})},
    "else": {"actions": {"Append_No_Attachments_Html": {"type": "AppendToStringVariable", "inputs": {"name": "varDocumentHtml", "value": "<div>添付ファイルなし</div>"}, "runAfter": {}}}},
    "runAfter": {"Append_Meeting_Header_Html": ["Succeeded"]}}
asa["Increment_MeetingIndex"] = {"type": "IncrementVariable", "inputs": {"name": "varMeetingIndex", "value": 1}, "runAfter": {"Condition_Has_Attachments": ["Succeeded"]}}

# HTMLは varDocumentHtml へ「文字列変数に追加」で直接連結する
# （旧: varDocHtmlParts 配列 + join → 廃止。join方式は自己参照ではないが、
#   ユーザー指示 §4.2 に従い AppendToStringVariable に統一）。
s50 = {
    "Append_DocumentHtml_Header": {"type": "AppendToStringVariable", "inputs": {"name": "varDocumentHtml", "value": HTML_HEAD}, "runAfter": {}},
    "Apply_To_Each_Sorted_Meeting": apply_sorted,
    "Append_DocumentHtml_Footer": {"type": "AppendToStringVariable", "inputs": {"name": "varDocumentHtml", "value": "</body></html>"}, "runAfter": {"Apply_To_Each_Sorted_Meeting": ["Succeeded"]}},
}
actions["Scope_50_Build_Word_Content"] = {"type": "Scope", "actions": s50, "runAfter": ra("Scope_40_Sort_Meetings")}

# =========================================================================
# Scope_60_Create_Archive_File : .doc 作成 + 保存後URL
# =========================================================================
# DryRun=false のときだけ実際に .doc を作成する（本番フォルダを汚さない）
s60_create = {
    "Create_Archive_Document": oac(H_SPO, "CreateFile", {
        "dataset": "@variables('varSiteAddress')",
        "folderPath": "@concat('/', variables('varLibrary'), '/', variables('varDestinationPath'))",
        "name": "@outputs('Compose_ArchiveFileName')",
        "body": "@variables('varDocumentHtml')"}),
    # v10: GetFileItem（{Link}）廃止。URLは既知の値から決定的に構築
    # （CreateFile成功＝このパス・名前で作成された、の直接証明）
    "Set_ArchiveUrl": {"type": "SetVariable", "inputs": {"name": "varArchiveUrl",
        "value": ("@replace(concat(variables('varSiteAddress'), '/', variables('varLibrary'), '/',"
                  " variables('varDestinationPath'), '/', outputs('Compose_ArchiveFileName')), ' ', '%20')")},
        "runAfter": {}},
}
s60_create["Create_Archive_Document"]["runAfter"] = {}
s60_create["Set_ArchiveUrl"]["runAfter"] = {"Create_Archive_Document": ["Succeeded"]}
s60 = {
    "Compose_ArchiveFileName": {"type": "Compose", "inputs": "@concat('課内会議総括_', formatDateTime(convertFromUtc(utcNow(), 'Tokyo Standard Time'), 'yyyyMMdd_HHmmss'), '.doc')", "runAfter": {}},
    "Condition_DryRun_Archive": {"type": "If",
        "expression": {"and": [{"equals": ["@coalesce(triggerBody()?['DryRun'], true)", True]}]},
        "actions": {"Set_ArchiveUrl_DryRun": {"type": "SetVariable", "inputs": {"name": "varArchiveUrl", "value": "(DryRun: 総括Wordファイルは作成していません。DryRun=いいえで実行してください)"}, "runAfter": {}}},
        "else": {"actions": s60_create},
        "runAfter": {"Compose_ArchiveFileName": ["Succeeded"]}},
}
actions["Scope_60_Create_Archive_File"] = {"type": "Scope", "actions": s60, "runAfter": ra("Scope_50_Build_Word_Content")}

# =========================================================================
# Scope_70_Write_Run_Log
# =========================================================================
s70 = {"Set_RunStatus_Success": {"type": "SetVariable", "inputs": {"name": "varRunStatus", "value": "Success"}, "runAfter": {}},
    # v7: PostItem→REST（前段Composeでボディ構築）
    "Compose_RunLog_Body": {"type": "Compose", "inputs": {
        "Title": "@concat(variables('varRunId'), '_summary')",
        "RunId": "@variables('varRunId')",
        "FlowName": "PA_Migrate_Teams_Meeting_Archive_To_SPO",
        "Level": "Info",
        "MeetingCount": "@length(variables('varSortedMeetings'))",
        "SavedCount": "@variables('varSavedCount')",
        "SkippedCount": "@variables('varSkippedCount')",
        "FailedCount": "@variables('varFailedCount')",
        "ArchiveUrl": "@variables('varArchiveUrl')",
        "Status": "@variables('varRunStatus')",
        "OccurredDateTimeUtc": "@utcNow()"}},
    "Create_Run_Log": sp_rest_post_item("varRunLogList", "Compose_RunLog_Body")}
s70["Compose_RunLog_Body"]["runAfter"] = {"Set_RunStatus_Success": ["Succeeded"]}
s70["Create_Run_Log"]["runAfter"] = {"Compose_RunLog_Body": ["Succeeded"]}
actions["Scope_70_Write_Run_Log"] = {"type": "Scope", "actions": s70, "runAfter": ra("Scope_60_Create_Archive_File")}

# =========================================================================
# Scope_90_Catch / Scope_99_Finally
# =========================================================================
s90 = {"Set_RunStatus_Failed": {"type": "SetVariable", "inputs": {"name": "varRunStatus", "value": "Failed"}, "runAfter": {}},
    "Set_ErrorMessage": {"type": "SetVariable", "inputs": {"name": "varErrorMessage", "value": "@concat('実行中にエラーが発生しました。RunId=', variables('varRunId'))}", }, "runAfter": {"Set_RunStatus_Failed": ["Succeeded"]}},
    # v7: PostItem→REST（前段Composeでボディ構築）
    "Compose_ErrorLog_Body": {"type": "Compose", "inputs": {
        "Title": "@concat(variables('varRunId'), '_error')",
        "RunId": "@variables('varRunId')",
        "FlowName": "PA_Migrate_Teams_Meeting_Archive_To_SPO",
        "Level": "Error",
        "ErrorMessage": "@variables('varErrorMessage')",
        "Status": "Failed",
        "OccurredDateTimeUtc": "@utcNow()"}},
    "Create_Error_Log": sp_rest_post_item("varRunLogList", "Compose_ErrorLog_Body")}
# エラーメッセージの式が壊れているので修正
s90["Set_ErrorMessage"]["inputs"]["value"] = "@concat('実行中にエラーが発生しました。RunId=', variables('varRunId'))"
s90["Compose_ErrorLog_Body"]["runAfter"] = {"Set_ErrorMessage": ["Succeeded"]}
s90["Create_Error_Log"]["runAfter"] = {"Compose_ErrorLog_Body": ["Succeeded"]}
actions["Scope_90_Catch"] = {"type": "Scope", "actions": s90,
    "runAfter": {"Scope_70_Write_Run_Log": ["Failed", "Skipped", "TimedOut"]}}

s99 = {"Compose_Finally_Summary": {"type": "Compose", "inputs": {
        "RunId": "@variables('varRunId')", "Status": "@variables('varRunStatus')",
        "MeetingCount": "@length(variables('varSortedMeetings'))",
        "SavedCount": "@variables('varSavedCount')", "SkippedCount": "@variables('varSkippedCount')",
        "FailedCount": "@variables('varFailedCount')",
        "ArchiveUrl": "@variables('varArchiveUrl')"}, "runAfter": {}}}
actions["Scope_99_Finally"] = {"type": "Scope", "actions": s99,
    "runAfter": {"Scope_90_Catch": ["Succeeded", "Skipped", "Failed", "TimedOut"]}}

# =========================================================================
# トリガー
# =========================================================================
triggers = {"manual": {"type": "Request", "kind": "Button", "inputs": {"schema": {
    "type": "object",
    "properties": {
        "LookbackDays": {"title": "取得対象日数", "type": "number", "description": "実行日時から何日前までのTeams投稿を取得するか（7/30/365/730）", "default": 7},
        "DryRun": {"title": "テスト実行", "type": "boolean", "description": "はい=本番保存せずテスト", "default": True},
        "ForceReprocess": {"title": "処理済みファイルを再処理する", "type": "boolean", "description": "はい=台帳を無視して再保存", "default": False},
    },
    "required": []}}}}

definition = {
    "metadata": {"creator": {}, "provisioningMethod": "FromDefinition", "creationSource": "Portal", "modifiedSources": "Portal"},
    "$schema": "https://schema.management.azure.com/providers/Microsoft.Logic/schemas/2016-06-01/workflowdefinition.json#",
    "contentVersion": "1.0.0.0",
    "parameters": {"$authentication": {"defaultValue": {}, "type": "SecureObject"}, "$connections": {"defaultValue": {}, "type": "Object"}},
    "triggers": triggers,
    "actions": actions,
}

connection_references = {
    "shared_teams": {"connectionName": CN_TEAMS, "source": "Invoker", "id": "/providers/Microsoft.PowerApps/apis/shared_teams", "tier": "NotSpecified", "apiName": "teams"},
    "shared_sharepointonline": {"connectionName": CN_SPO, "source": "Invoker", "id": "/providers/Microsoft.PowerApps/apis/shared_sharepointonline", "tier": "NotSpecified", "apiName": "sharepointonline"},
    "shared_conversionservice": {"connectionName": CN_CONV, "source": "Invoker", "id": "/providers/Microsoft.PowerApps/apis/shared_conversionservice", "tier": "NotSpecified", "apiName": "conversionservice"},
}

flow_file = {
    "name": FLOW_NAME,
    "id": "/providers/Microsoft.Flow/flows/" + FLOW_NAME,
    "type": "Microsoft.Flow/flows",
    "properties": {
        "apiId": "/providers/Microsoft.PowerApps/apis/shared_logicflows",
        "displayName": "Teams課内会議アーカイブ",
        "definition": definition,
        "connectionReferences": connection_references,
        "flowFailureAlertSubscribed": False,
        "isManaged": False,
    },
}

# =========================================================================
# パッケージ構成ファイル
# =========================================================================
root_manifest = {
    "schema": "1.0",
    "details": {"displayName": "PA_Migrate_Teams_Meeting_Archive_To_SPO", "description": "Teams課内会議アーカイブ（単一フロー）", "createdTime": "2026-07-16T00:00:00.0000000Z", "packageTelemetryId": PKG_TELE, "creator": "N/A", "sourceEnvironment": ""},
    "resources": {
        PKG_FOLDER: {"type": "Microsoft.Flow/flows", "suggestedCreationType": "New", "creationType": "Existing, New, Update",
            "details": {"displayName": "Teams課内会議アーカイブ"}, "configurableBy": "User", "hierarchy": "Root",
            "dependsOn": [API_TEAMS, CONN_TEAMS, API_SPO, CONN_SPO, API_CONV, CONN_CONV]},
        API_TEAMS: {"id": "/providers/Microsoft.PowerApps/apis/shared_teams", "name": "shared_teams", "type": "Microsoft.PowerApps/apis", "suggestedCreationType": "Existing", "details": {"displayName": "Microsoft Teams"}, "configurableBy": "System", "hierarchy": "Child", "dependsOn": []},
        CONN_TEAMS: {"type": "Microsoft.PowerApps/apis/connections", "suggestedCreationType": "Existing", "creationType": "Existing", "details": {"displayName": "Microsoft Teams への接続を選択してください"}, "configurableBy": "User", "hierarchy": "Child", "dependsOn": [API_TEAMS]},
        API_SPO: {"id": "/providers/Microsoft.PowerApps/apis/shared_sharepointonline", "name": "shared_sharepointonline", "type": "Microsoft.PowerApps/apis", "suggestedCreationType": "Existing", "details": {"displayName": "SharePoint"}, "configurableBy": "System", "hierarchy": "Child", "dependsOn": []},
        CONN_SPO: {"type": "Microsoft.PowerApps/apis/connections", "suggestedCreationType": "Existing", "creationType": "Existing", "details": {"displayName": "SharePoint への接続を選択してください"}, "configurableBy": "User", "hierarchy": "Child", "dependsOn": [API_SPO]},
        API_CONV: {"id": "/providers/Microsoft.PowerApps/apis/shared_conversionservice", "name": "shared_conversionservice", "type": "Microsoft.PowerApps/apis", "suggestedCreationType": "Existing", "details": {"displayName": "Content Conversion"}, "configurableBy": "System", "hierarchy": "Child", "dependsOn": []},
        CONN_CONV: {"type": "Microsoft.PowerApps/apis/connections", "suggestedCreationType": "Existing", "creationType": "Existing", "details": {"displayName": "Content Conversion への接続を選択してください"}, "configurableBy": "User", "hierarchy": "Child", "dependsOn": [API_CONV]},
    },
}
flows_manifest = {"packageSchemaVersion": "1.0", "flowAssets": {"assetPaths": [PKG_FOLDER]}}
apis_map = {"shared_teams": API_TEAMS, "shared_sharepointonline": API_SPO, "shared_conversionservice": API_CONV}
conns_map = {"shared_teams": CONN_TEAMS, "shared_sharepointonline": CONN_SPO, "shared_conversionservice": CONN_CONV}

# =========================================================================
# 出力
# =========================================================================
msflow = os.path.join(BUILD, "Microsoft.Flow")
if os.path.exists(msflow):
    shutil.rmtree(msflow, ignore_errors=True)
flowdir = os.path.join(BUILD, "Microsoft.Flow", "flows", PKG_FOLDER)
os.makedirs(flowdir, exist_ok=True)

def dump(path, obj):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)

dump(os.path.join(BUILD, "manifest.json"), root_manifest)
dump(os.path.join(BUILD, "Microsoft.Flow", "flows", "manifest.json"), flows_manifest)
dump(os.path.join(flowdir, "definition.json"), flow_file)
dump(os.path.join(flowdir, "apisMap.json"), apis_map)
dump(os.path.join(flowdir, "connectionsMap.json"), conns_map)

print("WROTE build package.")
# アクション数集計
def count_actions(d):
    n = 0
    for k, v in d.items():
        if isinstance(v, dict) and "type" in v:
            n += 1
            for sub in ("actions",):
                if sub in v and isinstance(v[sub], dict):
                    n += count_actions(v[sub])
            if v.get("type") in ("If",):
                for br in ("actions",):
                    pass
                if "else" in v and isinstance(v["else"], dict) and "actions" in v["else"]:
                    n += count_actions(v["else"]["actions"])
            if v.get("type") == "If" and "actions" in v:
                n += count_actions(v["actions"])
            if v.get("type") in ("Foreach", "Until", "Scope") and "actions" in v:
                pass
    return n
print("top-level actions:", len(actions))
