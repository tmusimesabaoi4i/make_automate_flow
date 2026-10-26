# -*- coding: utf-8 -*-
"""
TeamsChannelMemberSync_Setup のレガシーパッケージ（展開形）を生成する。

TeamsチャネルURL・SharePointサイトURL・リスト名を手動で受け取り、
  1. 入力形式を検証し
  2. Teams チャネルURLから チームID / チャネルID / テナントID を取り出し
  3. SharePoint サイトURLをコネクタで使えるサイトルートへ正規化し
  4. Teams チャネルと SharePoint サイト・リストへ実際にアクセスできることを確かめ
  5. メンバーを取得して SharePoint リストへ同期（テスト同期）し
  6. **すべて成功したときだけ** 管理サイトの設定リストへ設定を保存する。

同期処理そのものは projects/teams-channel-member-sync/shared/sync_blocks.py が生成する。
日次フロー（TeamsChannelMemberSync_Daily）とまったく同じアクション群が埋め込まれる。

【不変則】definition.json は生成物。修正は必ず本スクリプトか sync_blocks.py を編集して再生成する。
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BUILD = os.path.join(HERE, "package")
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..", "..", "..", "shared")))

import sync_blocks as sb  # noqa: E402

FLOW_LOGICAL_NAME = "TeamsChannelMemberSync_Setup"
FLOW_DISPLAY_NAME = "Teamsチャネルメンバー同期 初期設定・テスト"

# ---- 固定GUID（本フロー用に新規採番・匿名） ----
FLOW_ID = "6b41d9a7-2e08-4c53-9d16-7fa2c58e304b"      # definition.json の name / id
PKG_FOLDER = "1f7ac52d-6390-4b81-a4e7-92c0d3865fe1"   # Microsoft.Flow/flows/{PKG_FOLDER}/
API_TEAMS = "a3d5e2b8-47c1-4906-b8f3-5e17d0c94a26"
CONN_TEAMS = "9c62f014-8be7-4d35-a1c8-63f5827bd0e4"
API_SPO = "4e80b13c-5df9-42a7-96b2-c8710ade5f39"
CONN_SPO = "d51968ea-3c74-4f28-b0d6-71a94e2c8563"
CN_TEAMS = "7d2e83b1c96f4a05be31d478c2016e9a"         # connectionReferences のキー側の値（匿名）
CN_SPO = "c48f102ba75d43e69017fb3d825ac6e4"
PKG_TELE = "8a05c3f7-1d62-49be-b743-0e26f9c58d1a"

compose = sb.compose
setvar = sb.setvar
append = sb.append
incr = sb.incr
query = sb.query
foreach = sb.foreach
cond = sb.cond
scope = sb.scope
chain = sb.chain
http = sb.http
eq = sb.eq
ra = sb.ra

# =========================================================================
# トップレベル変数初期化
# InitializeVariable は Scope 内に置けない（handbook/rules/01）ため、
# 共通ブロックが使う変数もすべてここで初期化する。
# =========================================================================
INIT_SEQ = list(sb.SHARED_VARIABLES) + [
    ("Initialize_InputChannelUrl", "varInputChannelUrl", "string", ""),
    ("Initialize_InputSiteUrl", "varInputSiteUrl", "string", ""),
    ("Initialize_InputListName", "varInputListName", "string", ""),
    ("Initialize_DisableOtherConfigs", "varDisableOtherConfigs", "boolean", False),
    ("Initialize_ConfigKey", "varConfigKey", "string", ""),
    ("Initialize_ConfigSaved", "varConfigSaved", "boolean", False),
    ("Initialize_AdminSiteSource", "varAdminSiteSource", "string", ""),
]

actions = {}
prev = None
for aname, vname, vtype, value in INIT_SEQ:
    act = sb.initvar(vname, vtype, value)
    act["runAfter"] = ra(prev)
    actions[aname] = act
    prev = aname
LAST_INIT = prev

# =========================================================================
# 管理サイトURL（任意）
#
# 設定リストをどのサイトに置くかを、既定で固定したい場合だけここに入れる。
# **空のままでよい。** 空なら、実行時に入力された同期先サイトへ設定リストを作る。
# 「インポート後に手で設定しないと1回も動かない」設計にしないため、
# 未設定を既定として成立させている（2026-08-04 の実行で2回続けて止まった反省）。
# ZIP にテナント固有の値を含めないため、既定値は空文字
# （検証スクリプトが「空文字であること」を機械確認する）。
# =========================================================================
actions["Compose_AdminSiteUrl"] = compose("", ra(LAST_INIT))

# =========================================================================
# Scope_00_Bootstrap : 管理サイトURLの候補を正規化する
#
# 優先順位: トリガー入力 > Compose_AdminSiteUrl > （空。後段で同期先サイトへ倒す）
# ここでは **空を失敗にしない**。SharePoint 以外のホストが指定されたときだけ弾く。
# =========================================================================
ADMIN_INPUT = "trim(coalesce(triggerBody()?['AdminSiteUrl'], ''))"
ADMIN_COMPOSE = "trim(coalesce(outputs('Compose_AdminSiteUrl'), ''))"
ADMIN_CANDIDATE = ("@if(not(empty(" + ADMIN_INPUT + ")), " + ADMIN_INPUT + ", "
                   + ADMIN_COMPOSE + ")")

admin_seq, ADMIN_ROOT = sb.build_normalize_site_url(
    "Admin", "outputs('Compose_Admin_Candidate')")
ADMIN_HOST = sb.host_of("outputs('%s')" % ADMIN_ROOT)

BOOTSTRAP_CODE = (
    "@if(and(not(empty(outputs('Compose_Admin_Candidate'))),"
    " not(endsWith(" + ADMIN_HOST + ", '.sharepoint.com'))),"
    " 'ERR_ADMIN_SITE_NOT_SHAREPOINT', '')")

bootstrap_ng, _ = chain([
    ("Set_Bootstrap_Invalid", setvar("varIsValid", False)),
    ("Set_Bootstrap_FailedStage", setvar("varFailedStage", "00_Bootstrap")),
    ("Set_Bootstrap_ErrorMessage", setvar(
        "varErrorMessage",
        "管理サイトURLとして指定された値が SharePoint Online のURLではありません。"
        "https://<テナント名>.sharepoint.com/sites/<サイト名> の形式で指定するか、"
        "空にして同期先サイトへ設定リストを作らせてください。")),
])

bootstrap_seq = [
    ("Set_Stage_Bootstrap", setvar("varStage", "00_Bootstrap")),
    ("Compose_Admin_Candidate", compose(ADMIN_CANDIDATE)),
] + admin_seq + [
    ("Compose_Bootstrap_Code", compose(BOOTSTRAP_CODE)),
    ("Set_Bootstrap_ErrorCode", setvar("varErrorCode", "@outputs('Compose_Bootstrap_Code')")),
]
bootstrap_inner, bootstrap_last = chain(bootstrap_seq)
bootstrap_inner["Condition_Bootstrap_Failed"] = cond(
    {"and": [{"not": eq("@outputs('Compose_Bootstrap_Code')", "")}]}, bootstrap_ng,
    runafter=ra(bootstrap_last))
actions["Scope_00_Bootstrap"] = scope(bootstrap_inner, ra("Compose_AdminSiteUrl"))

# =========================================================================
# Scope_01_ValidateInput : 入力3項目の形式検証
#
# 【セキュリティ】ホストを明示的に検査し、Teams / SharePoint 以外のホストは受け付けない。
# 入力値をそのまま HTTP 要求へ連結しない:
#   - サイトURLは正規化してホスト検査を通したものだけを dataset に渡す
#   - リスト名は URI に連結せず、リストID経由でのみ対象を特定する
#   - チャネルIDは Graph URI に入れる前に必ず uriComponent() でエンコードする
# =========================================================================
CH_URL = "outputs('Compose_Input_Channel_Url')"
CH_NOFRAG = "outputs('Compose_Channel_NoFragment')"
CH_PATH = "outputs('Compose_Channel_Path')"
CH_HOST = "outputs('Compose_Channel_Host')"
SITE_HOST = "outputs('Compose_Site_Host')"

VALIDATION_CODE = (
    "@if(empty(variables('varInputChannelUrl')), 'ERR_CHANNEL_URL_EMPTY',"
    " if(empty(variables('varInputSiteUrl')), 'ERR_SITE_URL_EMPTY',"
    " if(empty(variables('varInputListName')), 'ERR_LIST_NAME_EMPTY',"
    " if(greater(length(variables('varInputListName')), 255), 'ERR_LIST_NAME_TOO_LONG',"
    " if(not(or(equals(" + CH_HOST + ", 'teams.microsoft.com'),"
    " equals(" + CH_HOST + ", 'teams.cloud.microsoft'))), 'ERR_NOT_TEAMS_URL',"
    " if(not(endsWith(" + SITE_HOST + ", '.sharepoint.com')), 'ERR_NOT_SHAREPOINT_URL',"
    " ''))))))")

VALIDATION_MESSAGE = (
    "@if(equals(variables('varErrorCode'), 'ERR_CHANNEL_URL_EMPTY'),"
    " 'TeamsチャネルURLが入力されていません。',"
    " if(equals(variables('varErrorCode'), 'ERR_SITE_URL_EMPTY'),"
    " 'SharePointサイトURLが入力されていません。',"
    " if(equals(variables('varErrorCode'), 'ERR_LIST_NAME_EMPTY'),"
    " 'SharePointリスト名が入力されていません。',"
    " if(equals(variables('varErrorCode'), 'ERR_LIST_NAME_TOO_LONG'),"
    " 'SharePointリスト名が長すぎます（255文字以内で指定してください）。',"
    " if(equals(variables('varErrorCode'), 'ERR_NOT_TEAMS_URL'),"
    " 'Microsoft TeamsのURLではありません。teams.microsoft.com もしくは teams.cloud.microsoft の"
    "チャネルURLを貼り付けてください。',"
    " if(equals(variables('varErrorCode'), 'ERR_NOT_SHAREPOINT_URL'),"
    " 'SharePoint OnlineのURLではありません。サイトのトップページのURLを指定してください。',"
    " ''))))))")

validate_seq = [
    ("Set_Stage_ValidateInput", setvar("varStage", "01_ValidateInput")),
    ("Compose_Input_Channel_Url",
     compose("@trim(coalesce(triggerBody()?['TeamsChannelUrl'], ''))")),
    ("Compose_Input_Site_Url",
     compose("@trim(coalesce(triggerBody()?['SharePointSiteUrl'], ''))")),
    ("Compose_Input_List_Name",
     compose("@trim(coalesce(triggerBody()?['SharePointListName'], ''))")),
    ("Set_InputChannelUrl", setvar("varInputChannelUrl", "@" + CH_URL)),
    ("Set_InputSiteUrl", setvar("varInputSiteUrl", "@outputs('Compose_Input_Site_Url')")),
    ("Set_InputListName", setvar("varInputListName", "@outputs('Compose_Input_List_Name')")),
    ("Set_TeamsChannelUrl", setvar("varTeamsChannelUrl", "@variables('varInputChannelUrl')")),
    ("Set_ListName", setvar("varListName", "@variables('varInputListName')")),
    ("Set_DisableOtherConfigs", setvar(
        "varDisableOtherConfigs",
        "@equals(coalesce(triggerBody()?['DisableOtherConfigs'], false), true)")),
    # ホスト検査用（フラグメント・クエリを落としてからホストを取り出す）
    ("Compose_Channel_NoFragment", compose("@first(split(variables('varInputChannelUrl'), '#'))")),
    ("Compose_Channel_Path", compose("@first(split(" + CH_NOFRAG + ", '?'))")),
    ("Compose_Channel_Host", compose("@" + sb.host_of(CH_PATH))),
    ("Compose_SiteInput_NoFragment", compose("@first(split(variables('varInputSiteUrl'), '#'))")),
    ("Compose_SiteInput_Path", compose("@first(split(outputs('Compose_SiteInput_NoFragment'), '?'))")),
    ("Compose_Site_Host", compose("@" + sb.host_of("outputs('Compose_SiteInput_Path')"))),
]
validate_inner, validate_last = chain(validate_seq)
validate_gate, validate_gate_last = chain([
    ("Compose_Validation_Code", compose(VALIDATION_CODE)),
    ("Set_Input_ErrorCode", setvar("varErrorCode", "@outputs('Compose_Validation_Code')")),
    ("Set_Input_ErrorMessage", setvar("varErrorMessage", VALIDATION_MESSAGE)),
])
validate_gate["Condition_Input_Invalid"] = cond(
    {"and": [{"not": eq("@variables('varErrorCode')", "")}]},
    dict(chain([
        ("Set_Input_Invalid", setvar("varIsValid", False)),
        ("Set_Input_FailedStage", setvar("varFailedStage", "01_ValidateInput")),
    ])[0]),
    runafter=ra(validate_gate_last))
validate_inner["Condition_Can_Validate"] = cond(
    sb.is_valid(), validate_gate, runafter=ra(validate_last))
actions["Scope_01_ValidateInput"] = scope(validate_inner, ra("Scope_00_Bootstrap"))

# =========================================================================
# Scope_02_ParseTeamsUrl : TeamsチャネルURLから識別子を取り出す
#
# クエリは「&<名前>=」でアンカーして取り出す（順序不定・余分なパラメータ・欠落に耐える）。
# 固定位置の分割はしない。チャネルIDは %3A / %40 を decodeUriComponent で復号する。
# =========================================================================
Q = "outputs('Compose_Channel_Query_Normalized')"


def qparam(name):
    """クエリ値を区切り文字アンカー方式で取り出す（build_flow1.py の実証済みヘルパ）。
    先頭・末尾に '&' を足した正規化クエリを '&<name>=' で分割することで、
    部分一致による誤検出（groupId と subGroupId 等）を防ぐ。"""
    tok = "'&" + name + "='"
    return ("@if(contains(" + Q + ", " + tok + "), "
            "trim(decodeUriComponent(first(split(last(split(" + Q + ", " + tok + ")), '&')))), '')")


TAIL = "outputs('Compose_Channel_Path_Tail')"
GUID_OK = ("and(equals(length(%(V)s), 36), equals(length(split(%(V)s, '-')), 5))")

# 4段の入れ子 if。閉じ括弧は if の数と一致させる（誤ると保存時に式パースエラー）。
PARSE_CODE = (
    "@if(empty(variables('varTeamId')), 'ERR_GROUPID_NOT_FOUND',"
    " if(not(" + GUID_OK % {"V": "variables('varTeamId')"} + "), 'ERR_GROUPID_INVALID',"
    " if(empty(variables('varChannelId')), 'ERR_CHANNELID_NOT_FOUND',"
    " if(not(and(startsWith(variables('varChannelId'), '19:'),"
    " contains(variables('varChannelId'), 'thread.'))), 'ERR_CHANNELID_INVALID',"
    " ''))))")

PARSE_MESSAGE = (
    "@if(equals(variables('varErrorCode'), 'ERR_GROUPID_NOT_FOUND'),"
    " 'URLのクエリに groupId が見つかりません。Teamsのチャネルで「チャネルへのリンクを取得」した"
    "URLをそのまま貼り付けてください。',"
    " if(equals(variables('varErrorCode'), 'ERR_GROUPID_INVALID'),"
    " 'URLの groupId がGUIDの形式ではありません。',"
    " if(equals(variables('varErrorCode'), 'ERR_CHANNELID_NOT_FOUND'),"
    " 'URLのパスからチャネルIDを取得できません（/l/team/ が含まれていません）。',"
    " if(equals(variables('varErrorCode'), 'ERR_CHANNELID_INVALID'),"
    " 'URLから取り出した値がチャネルIDの形式ではありません。チャットのURLではなく"
    "チャネルのURLを指定してください。',"
    " ''))))")

parse_body_seq = [
    ("Compose_Channel_Query_Part",
     compose("@if(contains(" + CH_NOFRAG + ", '?'), last(split(" + CH_NOFRAG + ", '?')), '')")),
    ("Compose_Channel_Query_Normalized",
     compose("@concat('&', outputs('Compose_Channel_Query_Part'), '&')")),
    ("Parse_TeamId_From_Query", compose(qparam("groupId"))),
    ("Parse_TenantId_From_Query", compose(qparam("tenantId"))),
    # /l/team/ 以降（= "{チャネルID}/conversations..."）。末尾スラッシュにも耐える。
    ("Compose_Channel_Path_Tail",
     compose("@if(contains(" + CH_PATH + ", '/l/team/'),"
             " last(split(" + CH_PATH + ", '/l/team/')), '')")),
    ("Parse_ChannelId_From_Path",
     compose("@trim(decodeUriComponent(first(split(" + TAIL + ", '/'))))")),
    ("Set_TeamId", setvar("varTeamId", "@outputs('Parse_TeamId_From_Query')")),
    ("Set_ChannelId", setvar("varChannelId", "@outputs('Parse_ChannelId_From_Path')")),
    # テナントIDは任意。形式が違えば「不明」として空にする（誤った値で外部判定をしない）。
    ("Compose_TenantId_Checked",
     compose("@if(" + GUID_OK % {"V": "outputs('Parse_TenantId_From_Query')"} + ","
             " outputs('Parse_TenantId_From_Query'), '')")),
    ("Set_TenantId", setvar("varTenantId", "@outputs('Compose_TenantId_Checked')")),
    ("Compose_Parse_Code", compose(PARSE_CODE)),
    ("Set_Parse_ErrorCode", setvar("varErrorCode", "@outputs('Compose_Parse_Code')")),
    ("Set_Parse_ErrorMessage", setvar("varErrorMessage", PARSE_MESSAGE)),
]
parse_body, parse_body_last = chain(parse_body_seq)
parse_body["Condition_Parse_Invalid"] = cond(
    {"and": [{"not": eq("@variables('varErrorCode')", "")}]},
    dict(chain([
        ("Set_Parse_Invalid", setvar("varIsValid", False)),
        ("Set_Parse_FailedStage", setvar("varFailedStage", "02_ParseTeamsUrl")),
    ])[0]),
    runafter=ra(parse_body_last))

parse_inner = {}
parse_inner["Set_Stage_ParseTeamsUrl"] = setvar("varStage", "02_ParseTeamsUrl")
parse_inner["Condition_Can_Parse_Teams"] = cond(
    sb.is_valid(), parse_body, runafter=ra("Set_Stage_ParseTeamsUrl"))
actions["Scope_02_ParseTeamsUrl"] = scope(parse_inner, ra("Scope_01_ValidateInput"))

# =========================================================================
# Scope_03_ParseSharePointUrl : サイトURLの正規化
# =========================================================================
site_seq, SITE_ROOT = sb.build_normalize_site_url("Site", "variables('varInputSiteUrl')")
site_body, site_last = chain(site_seq + [
    ("Set_SiteUrl", setvar("varSiteUrl", "@outputs('%s')" % SITE_ROOT)),
])
site_body["Condition_Site_Url_Empty"] = cond(
    {"and": [eq("@empty(variables('varSiteUrl'))", True)]},
    dict(chain([
        ("Set_Site_Invalid", setvar("varIsValid", False)),
        ("Set_Site_FailedStage", setvar("varFailedStage", "03_ParseSharePointUrl")),
        ("Set_Site_ErrorCode", setvar("varErrorCode", "ERR_SITE_URL_NOT_RESOLVED")),
        ("Set_Site_ErrorMessage", setvar(
            "varErrorMessage",
            "SharePointサイトURLからサイトのルートURLを取り出せませんでした。"
            "サイトのトップページのURLを指定してください。")),
    ])[0]),
    runafter=ra(site_last))

site_inner = {}
site_inner["Set_Stage_ParseSiteUrl"] = setvar("varStage", "03_ParseSharePointUrl")
site_inner["Condition_Can_Parse_Site"] = cond(
    sb.is_valid(), site_body, runafter=ra("Set_Stage_ParseSiteUrl"))
actions["Scope_03_ParseSharePointUrl"] = scope(site_inner, ra("Scope_02_ParseTeamsUrl"))

# =========================================================================
# Scope_03A_ResolveConfigSite : 設定リストを置くサイトを確定する
#
# 管理サイトが指定されていなければ **同期先サイト** に設定リストを作る。
# こうすることで、インポート後の手作業なしでも初回実行が完了する。
# どちらを使ったかは結果に出し、日次フローへ貼り付ける値を利用者へ提示する。
# =========================================================================
ADMIN_SOURCE = ("@if(not(empty(" + ADMIN_INPUT + ")), 'trigger-input',"
                " if(not(empty(" + ADMIN_COMPOSE + ")), 'compose-admin-site',"
                " 'target-site'))")

resolve_ng, _ = chain([
    ("Set_Resolve_Invalid", setvar("varIsValid", False)),
    ("Set_Resolve_FailedStage", setvar("varFailedStage", "03A_ResolveConfigSite")),
    ("Set_Resolve_ErrorCode", setvar("varErrorCode", "ERR_CONFIG_SITE_NOT_RESOLVED")),
    ("Set_Resolve_ErrorMessage", setvar(
        "varErrorMessage",
        "設定リストを置くサイトを決められませんでした。SharePointサイトURLを見直してください。")),
])

resolve_body, resolve_last = chain([
    ("Compose_Config_Site_Resolved", compose(
        "@if(empty(outputs('%s')), variables('varSiteUrl'), outputs('%s'))"
        % (ADMIN_ROOT, ADMIN_ROOT))),
    ("Compose_Admin_Site_Source", compose(ADMIN_SOURCE)),
    # 結果出力（Scope_Finalize）からは変数だけを参照する。未実行アクションの
    # outputs() を参照すると、失敗経路でハンドラ自体が壊れる（handbook/rules/08）。
    ("Set_AdminSiteSource", setvar("varAdminSiteSource",
                                   "@outputs('Compose_Admin_Site_Source')")),
    ("Set_ConfigSiteUrl", setvar("varConfigSiteUrl",
                                 "@outputs('Compose_Config_Site_Resolved')")),
])
resolve_body["Condition_Config_Site_Empty"] = cond(
    {"and": [eq("@empty(variables('varConfigSiteUrl'))", True)]}, resolve_ng,
    runafter=ra(resolve_last))

resolve_inner = {}
resolve_inner["Set_Stage_ResolveConfigSite"] = setvar("varStage", "03A_ResolveConfigSite")
resolve_inner["Condition_Can_Resolve_Config_Site"] = cond(
    sb.is_valid(), resolve_body, runafter=ra("Set_Stage_ResolveConfigSite"))
actions["Scope_03A_ResolveConfigSite"] = scope(
    resolve_inner, ra("Scope_03_ParseSharePointUrl"))

# =========================================================================
# Scope_03B_EnsureConfigList : 設定リストを用意する
# 既存があれば絶対に作り直さない。不足している列だけを追加する。
# =========================================================================
actions["Scope_03B_EnsureConfigList"] = sb.build_ensure_list(
    "Config", sb.DS_CONFIG, "'%s'" % sb.CONFIG_LIST_TITLE,
    "varConfigListId", "varConfigListEntityType", sb.CONFIG_FIELDS,
    allow_create=True, ensure_fields=True, runafter=ra("Scope_03A_ResolveConfigSite"))

# =========================================================================
# Scope_04〜Scope_10 : 共通同期ブロック（日次フローとまったく同じ）
# =========================================================================
sync_scopes, SYNC_LAST = sb.build_sync_scopes(ra("Scope_03B_EnsureConfigList"))
actions.update(sync_scopes)

# =========================================================================
# Scope_11_SaveConfig : すべて成功したときだけ設定を保存する
#
# テストが失敗した場合は、最後に正常動作していた設定を一切書き換えない。
# 同じチャネルの設定が既にあれば更新（ConfigVersion を1つ進める）、無ければ作成、
# 2件以上あれば書き込まずに記録する（どれを正とすべきか判断できないため）。
# =========================================================================
ALL_SUCCEEDED = ("@and(equals(variables('varIsValid'), true),"
                 " empty(variables('varFailedStage')),"
                 " equals(variables('varErrorCount'), 0),"
                 " equals(variables('varMembersFetchComplete'), true))")

CONFIG_MATCH = "body('Filter_Config_Match')"
FIRST_CONFIG = "first(body('Filter_Config_Match'))"

CONFIG_VALUES = {
    "Title": "@outputs('Compose_Config_Title')",
    "ConfigKey": "@variables('varConfigKey')",
    "TeamsChannelUrl": "@variables('varTeamsChannelUrl')",
    "TeamId": "@variables('varTeamId')",
    "ChannelId": "@variables('varChannelId')",
    "TenantId": "@variables('varTenantId')",
    "SiteUrl": "@variables('varSiteUrl')",
    "ListTitle": "@variables('varListName')",
    "ChannelType": "@variables('varChannelType')",
    "MemberSource": "@variables('varMemberSource')",
    "IsEnabled": True,
    "LastTestSucceededAt": "@utcNow()",
    "LastSyncAt": "@utcNow()",
    "LastSyncResult": "@outputs('Compose_Config_Sync_Result')",
    "UpdatedAt": "@utcNow()",
}

SYNC_COUNTS = {
    "memberCount": "@variables('varMemberCount')",
    "created": "@variables('varCreatedCount')",
    "updated": "@variables('varUpdatedCount')",
    "unchanged": "@variables('varUnchangedCount')",
    "deactivated": "@variables('varDeactivatedCount')",
    "errors": "@variables('varErrorCount')",
    "memberSource": "@variables('varMemberSource')",
    "runKind": "setup",
    "at": "@utcNow()",
}

create_config, _ = chain([
    ("Compose_Create_Config_Body", compose(dict(
        CONFIG_VALUES, __metadata={"type": "@variables('varConfigListEntityType')"},
        ConfigVersion=1))),
    ("Create_Config_Item", http("POST", sb.list_uri("varConfigListId", "/items"), sb.H_VERBOSE,
                                "@string(outputs('Compose_Create_Config_Body'))",
                                dataset=sb.DS_CONFIG)),
    ("Set_Config_Saved_Created", setvar("varConfigSaved", True)),
])
create_config["Append_Config_Create_Error"] = append(
    "varItemErrors", {"stage": "11_SaveConfig", "code": "ERR_CONFIG_CREATE_FAILED"},
    {"Create_Config_Item": ["Failed", "TimedOut"]})
create_config["Increment_Error_Config_Create"] = incr(
    "varErrorCount", {"Append_Config_Create_Error": ["Succeeded"]})

update_config, _ = chain([
    ("Compose_Config_Item_Id", compose("@string(coalesce(%s?['Id'], 0))" % FIRST_CONFIG)),
    ("Compose_Config_Next_Version",
     compose("@add(coalesce(%s?['ConfigVersion'], 0), 1)" % FIRST_CONFIG)),
    ("Compose_Update_Config_Body", compose(dict(
        CONFIG_VALUES, __metadata={"type": "@variables('varConfigListEntityType')"},
        ConfigVersion="@outputs('Compose_Config_Next_Version')"))),
    ("Update_Config_Item", http(
        "POST", sb.item_uri("varConfigListId", "outputs('Compose_Config_Item_Id')"),
        sb.H_MERGE_V, "@string(outputs('Compose_Update_Config_Body'))", dataset=sb.DS_CONFIG)),
    ("Set_Config_Saved_Updated", setvar("varConfigSaved", True)),
])
update_config["Append_Config_Update_Error"] = append(
    "varItemErrors", {"stage": "11_SaveConfig", "code": "ERR_CONFIG_UPDATE_FAILED"},
    {"Update_Config_Item": ["Failed", "TimedOut"]})
update_config["Increment_Error_Config_Update"] = incr(
    "varErrorCount", {"Append_Config_Update_Error": ["Succeeded"]})

dup_config, _ = chain([
    ("Append_Config_Duplicate_Error", append(
        "varItemErrors", {"stage": "11_SaveConfig", "code": "ERR_CONFIG_DUPLICATE",
                          "count": "@length(%s)" % CONFIG_MATCH})),
    ("Increment_Error_Config_Duplicate", incr("varErrorCount")),
])

# 「置き換え」を選んだときだけ、他チャネルの有効な設定を無効化する。
# 設定は削除しない（履歴として残す）。
other_inner, _ = chain([
    ("Compose_Other_Config_Id",
     compose("@string(coalesce(items('Foreach_Other_Config')?['Id'], 0))")),
    ("Compose_Disable_Config_Body", compose({
        "__metadata": {"type": "@variables('varConfigListEntityType')"},
        "IsEnabled": False,
        "UpdatedAt": "@utcNow()"})),
    ("Disable_Other_Config", http(
        "POST", sb.item_uri("varConfigListId", "outputs('Compose_Other_Config_Id')"),
        sb.H_MERGE_V, "@string(outputs('Compose_Disable_Config_Body'))", dataset=sb.DS_CONFIG)),
])
other_inner["Append_Disable_Config_Error"] = append(
    "varItemErrors", {"stage": "11_SaveConfig", "code": "WARN_CONFIG_DISABLE_FAILED",
                      "itemId": "@outputs('Compose_Other_Config_Id')"},
    {"Disable_Other_Config": ["Failed", "TimedOut"]})

disable_others, _ = chain([
    ("Filter_Other_Configs", query(
        "@coalesce(body('Get_Config_Items')?['value'], json('[]'))",
        "@and(not(equals(trim(string(coalesce(item()?['ConfigKey'], ''))),"
        " variables('varConfigKey'))),"
        " equals(coalesce(item()?['IsEnabled'], false), true))")),
    ("Foreach_Other_Config", foreach("@body('Filter_Other_Configs')", other_inner)),
])

save_body, save_body_last = chain([
    ("Compose_Config_Key",
     compose("@concat(variables('varTeamId'), '_', variables('varChannelId'))")),
    ("Set_Config_Key", setvar("varConfigKey", "@outputs('Compose_Config_Key')")),
    ("Compose_Config_Title", compose(
        "@if(empty(variables('varChannelDisplayName')), variables('varConfigKey'),"
        " variables('varChannelDisplayName'))")),
    ("Compose_Sync_Counts", compose(SYNC_COUNTS)),
    ("Compose_Config_Sync_Result", compose("@string(outputs('Compose_Sync_Counts'))")),
    ("Get_Config_Items", http("GET", sb.list_uri("varConfigListId", sb.CONFIG_ITEMS_SELECT),
                              sb.H_NOMETA, dataset=sb.DS_CONFIG)),
    ("Filter_Config_Match", query(
        "@coalesce(body('Get_Config_Items')?['value'], json('[]'))",
        "@equals(trim(string(coalesce(item()?['ConfigKey'], ''))), variables('varConfigKey'))")),
])
save_body["Condition_Config_New"] = cond(
    {"and": [eq("@length(%s)" % CONFIG_MATCH, 0)]}, create_config, runafter=ra(save_body_last))
save_body["Condition_Config_Single"] = cond(
    {"and": [eq("@length(%s)" % CONFIG_MATCH, 1)]}, update_config,
    runafter={"Condition_Config_New": ["Succeeded", "Skipped"]})
save_body["Condition_Config_Duplicate"] = cond(
    {"and": [{"greater": ["@length(%s)" % CONFIG_MATCH, 1]}]}, dup_config,
    runafter={"Condition_Config_Single": ["Succeeded", "Skipped"]})
save_body["Condition_Disable_Others"] = cond(
    {"and": [eq("@variables('varDisableOtherConfigs')", True),
             eq("@variables('varConfigSaved')", True)]}, disable_others,
    runafter={"Condition_Config_Duplicate": ["Succeeded", "Skipped"]})

save_inner = {}
save_inner["Set_Stage_SaveConfig"] = setvar("varStage", "11_SaveConfig")
save_inner["Compose_All_Succeeded"] = compose(ALL_SUCCEEDED, ra("Set_Stage_SaveConfig"))
save_inner["Condition_All_Succeeded"] = cond(
    {"and": [eq("@outputs('Compose_All_Succeeded')", True)]}, save_body,
    runafter=ra("Compose_All_Succeeded"))
actions["Scope_11_SaveConfig"] = scope(save_inner, ra(SYNC_LAST))

# =========================================================================
# Scope_ErrorHandler（Catch相当）
#
# runAfter は直前の Scope_11_SaveConfig 1本にだけ張る。複数Scopeを列挙すると
# AND 判定になり「前段成功・中段失敗」でハンドラが発火しない。
# ハンドラ内の式は変数だけを参照する（未実行アクションの outputs を参照すると
# ハンドラ自体が壊れる）。
# =========================================================================
HANDLER_CODE = (
    "@if(not(empty(variables('varErrorCode'))), variables('varErrorCode'),"
    " if(equals(variables('varLastStatusCode'), '401'), 'ERR_UNAUTHORIZED',"
    " if(equals(variables('varLastStatusCode'), '403'), 'ERR_FORBIDDEN',"
    " if(equals(variables('varLastStatusCode'), '404'), 'ERR_NOT_FOUND',"
    " 'ERR_UNEXPECTED_FAILURE'))))")

HANDLER_MESSAGE = (
    "@if(not(empty(variables('varErrorMessage'))), variables('varErrorMessage'),"
    " if(equals(variables('varLastStatusCode'), '401'),"
    " '接続の認証に失敗しました。Teams / SharePoint の接続を作り直してください。',"
    " if(equals(variables('varLastStatusCode'), '403'),"
    " '対象へのアクセス権がありません。チャネルのメンバーであること、"
    "SharePointサイトへの編集権限があることを確認してください。',"
    " if(equals(variables('varLastStatusCode'), '404'),"
    " '対象が見つかりません。チームID・チャネルID・サイトURL・リスト名を確認してください。',"
    " '想定外のエラーが発生しました。実行履歴で失敗したアクションを確認してください。'))))")

handler_inner, _ = chain([
    ("Set_Handler_Invalid", setvar("varIsValid", False)),
    ("Compose_Handler_Error_Code", compose(HANDLER_CODE)),
    ("Compose_Handler_Error_Message", compose(HANDLER_MESSAGE)),
    ("Set_Handler_ErrorCode", setvar("varErrorCode", "@outputs('Compose_Handler_Error_Code')")),
    ("Set_Handler_ErrorMessage",
     setvar("varErrorMessage", "@outputs('Compose_Handler_Error_Message')")),
    ("Compose_Handler_FailedStage", compose(
        "@if(empty(variables('varFailedStage')), variables('varStage'),"
        " variables('varFailedStage'))")),
    ("Set_Handler_FailedStage", setvar("varFailedStage",
                                       "@outputs('Compose_Handler_FailedStage')")),
])
actions["Scope_ErrorHandler"] = {
    "type": "Scope", "actions": handler_inner,
    "runAfter": {"Scope_11_SaveConfig": ["Failed", "Skipped", "TimedOut"]},
}

# =========================================================================
# Scope_Finalize（Finally相当）: 成否に関わらず結果を出力へ露出する
# 氏名・メールアドレスは含めない（要件§12）。
# =========================================================================
RESULT = dict(sb.result_summary("setup"))
RESULT["success"] = ("@and(equals(variables('varIsValid'), true),"
                     " empty(variables('varFailedStage')))")
RESULT["configSaved"] = "@variables('varConfigSaved')"
RESULT["configKey"] = "@variables('varConfigKey')"
RESULT["configListTitle"] = sb.CONFIG_LIST_TITLE
RESULT["adminSiteUrl"] = "@variables('varConfigSiteUrl')"
RESULT["adminSiteSource"] = "@variables('varAdminSiteSource')"
RESULT["nextAction"] = "@outputs('Compose_Next_Action')"

# 「次に何をすればよいか」を実行結果に必ず出す。
# 日次フローに貼り付ける値を、探させずにそのまま提示する。
NEXT_ACTION = (
    "@if(equals(variables('varConfigSaved'), true),"
    " concat('この設定を毎日実行するには、フロー「Teamsチャネルメンバー同期 日次実行」を開き、"
    "Compose_AdminSiteUrl アクションに次の値を貼り付けて保存し、フローをオンにしてください: ',"
    " variables('varConfigSiteUrl')),"
    " concat('設定は保存されていません。errorCode / errorMessage を確認して、"
    "修正のうえ再実行してください。失敗した段階: ', variables('varFailedStage')))")

finalize_inner, _ = chain([
    ("Compose_Next_Action", compose(NEXT_ACTION)),
    ("Compose_Result_Summary", compose(RESULT)),
])
actions["Scope_Finalize"] = {
    "type": "Scope",
    "actions": finalize_inner,
    "runAfter": {"Scope_ErrorHandler": ["Succeeded", "Failed", "Skipped", "TimedOut"]},
}

# =========================================================================
# definition.json
#
# トリガー入力の title / description に '@' を書かない。'@{' は式の補間として
# 解釈され、インポート時に Unable to parse template language expression になる
# （handbook/knowledge/error_catalog.md #3）。
# =========================================================================
definition = {
    "metadata": {"creator": {}, "provisioningMethod": "FromDefinition",
                 "creationSource": "Portal", "modifiedSources": "Portal"},
    "$schema": "https://schema.management.azure.com/providers/Microsoft.Logic/schemas/"
               "2016-06-01/workflowdefinition.json#",
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
                    "TeamsChannelUrl": {
                        "title": "TeamsチャネルURL",
                        "type": "string",
                        "description": "Teamsのチャネルで「チャネルへのリンクを取得」した"
                                       "URLをそのまま貼り付けてください",
                    },
                    "SharePointSiteUrl": {
                        "title": "SharePointサイトURL",
                        "type": "string",
                        "description": "同期先サイトのURL。一覧画面や設定画面のURLでも"
                                       "サイトのルートへ自動で正規化します",
                    },
                    "SharePointListName": {
                        "title": "SharePointリスト名",
                        "type": "string",
                        "description": "メンバーを書き込むリストの表示名。"
                                       "存在しない場合は作成します",
                    },
                    "DisableOtherConfigs": {
                        "title": "他のチャネル設定を無効化する",
                        "type": "boolean",
                        "description": "はいを選ぶと、テスト成功後にほかのチャネルの"
                                       "設定をすべて無効にして、この設定だけを日次実行の"
                                       "対象にします",
                    },
                    "AdminSiteUrl": {
                        "title": "設定リストを置くサイトのURL（任意）",
                        "type": "string",
                        "description": "空でかまいません。空の場合は上のSharePointサイトへ"
                                       "設定リストを作成します。別のサイトでまとめて管理"
                                       "したいときだけ指定してください",
                    },
                },
                "required": ["TeamsChannelUrl", "SharePointSiteUrl", "SharePointListName"],
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
            "shared_teams": sb.connection_reference(CN_TEAMS, "shared_teams"),
            "shared_sharepointonline": sb.connection_reference(CN_SPO, "shared_sharepointonline"),
        },
        "flowFailureAlertSubscribed": False,
        "isManaged": False,
    },
}

root_manifest = {
    "schema": "1.0",
    "details": {
        "displayName": FLOW_LOGICAL_NAME,
        "description": "TeamsチャネルURL・SharePointサイトURL・リスト名を受け取り、"
                       "テスト同期に成功したときだけ設定を保存する初期設定フロー",
        "createdTime": "2026-08-04T00:00:00.0000000Z",
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
            "dependsOn": [API_TEAMS, CONN_TEAMS, API_SPO, CONN_SPO],
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
        API_SPO: {
            "id": "/providers/Microsoft.PowerApps/apis/shared_sharepointonline",
            "name": "shared_sharepointonline",
            "type": "Microsoft.PowerApps/apis",
            "suggestedCreationType": "Existing",
            "details": {"displayName": "SharePoint"},
            "configurableBy": "System",
            "hierarchy": "Child",
            "dependsOn": [],
        },
        CONN_SPO: {
            "type": "Microsoft.PowerApps/apis/connections",
            "suggestedCreationType": "Existing",
            "creationType": "Existing",
            "details": {"displayName": "SharePoint への接続を選択してください"},
            "configurableBy": "User",
            "hierarchy": "Child",
            "dependsOn": [API_SPO],
        },
    },
}

flows_manifest = {"packageSchemaVersion": "1.0", "flowAssets": {"assetPaths": [PKG_FOLDER]}}
apis_map = {"shared_teams": API_TEAMS, "shared_sharepointonline": API_SPO}
connections_map = {"shared_teams": CONN_TEAMS, "shared_sharepointonline": CONN_SPO}


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
