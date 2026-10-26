# -*- coding: utf-8 -*-
"""
TeamsChannelMemberSync_Daily のレガシーパッケージ（展開形）を生成する。

毎日 07:00（日本時間）に、管理サイトの設定リストから有効な設定を読み、
各設定について Teams チャネルのメンバーを SharePoint リストへ同期する。

同期処理そのものは projects/teams-channel-member-sync/shared/sync_blocks.py が生成する。
初期設定フロー（TeamsChannelMemberSync_Setup）とまったく同じアクション群が埋め込まれる。
同じ処理を2箇所に書かないための構成（Power Automate の子フローは Dataverse
ソリューションを必須とし、レガシーパッケージ形式では使えないため）。

有効な設定が1件も無いときは、無効なURLで処理を続けず「初回設定が未完了」であることを
出力して安全に終了する。

【不変則】definition.json は生成物。修正は必ず本スクリプトか sync_blocks.py を編集して再生成する。
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BUILD = os.path.join(HERE, "package")
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..", "..", "..", "shared")))

import sync_blocks as sb  # noqa: E402

FLOW_LOGICAL_NAME = "TeamsChannelMemberSync_Daily"
FLOW_DISPLAY_NAME = "Teamsチャネルメンバー同期 日次実行"

# 実行時刻。timeZone を指定するときは startTime に 'Z' を付けない
# （learn.microsoft.com/azure/connectors/connectors-native-recurrence）。
# UTCオフセットを直接書かないことで、意図しない日に実行される事故を防ぐ。
SCHEDULE_HOUR = 7
SCHEDULE_MINUTE = 0
SCHEDULE_TIMEZONE = "Tokyo Standard Time"
SCHEDULE_START = "2026-08-05T07:00:00"

# ---- 固定GUID（本フロー用に新規採番・匿名） ----
FLOW_ID = "2d9e47c6-b031-4a58-8e72-c519f6403bad"
PKG_FOLDER = "b8365e01-9d47-42fa-a06c-3e57192db4c8"
API_TEAMS = "5f4c0a93-e276-41d8-b31e-8a09c7645d20"
CONN_TEAMS = "e07b3d52-846a-4c19-9f57-2b60d18ea34f"
API_SPO = "31ca6f80-7e45-4b2d-a693-05f8c4e17b6d"
CONN_SPO = "7a9d5c28-40be-4136-8fc2-e5316b90da47"
CN_TEAMS = "6e13b0f4a5c847d29b8e0374f1a5c62d"
CN_SPO = "0b7f56d3e841429ca9d2637b05e48f1c"
PKG_TELE = "f92a4b18-63d0-4e57-8c14-7ab5309ed26f"

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
# =========================================================================
INIT_SEQ = list(sb.SHARED_VARIABLES) + [
    ("Initialize_Configs", "varConfigs", "array", []),
    ("Initialize_NoConfig", "varNoConfig", "boolean", False),
    ("Initialize_ConfigResults", "varConfigResults", "array", []),
    ("Initialize_ProcessedConfigCount", "varProcessedConfigCount", "integer", 0),
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
# インポート後に1回だけ設定する箇所
# 初期設定フローの Compose_AdminSiteUrl と **同じ値** を設定する。
# 定期フローが「設定リストがどこにあるか」を知る唯一の手段であり、
# 対象サイトを設定リストから読むという循環依存はここで断ち切られている。
# =========================================================================
actions["Compose_AdminSiteUrl"] = compose("", ra(LAST_INIT))

# =========================================================================
# Scope_00_Bootstrap : 管理サイトURLの確定
# =========================================================================
admin_seq, ADMIN_ROOT = sb.build_normalize_site_url("Admin", "outputs('Compose_AdminSiteUrl')")
ADMIN_HOST = sb.host_of("outputs('%s')" % ADMIN_ROOT)

BOOTSTRAP_CODE = (
    "@if(empty(trim(coalesce(outputs('Compose_AdminSiteUrl'), ''))), 'ERR_ADMIN_SITE_NOT_SET',"
    " if(not(endsWith(" + ADMIN_HOST + ", '.sharepoint.com')), 'ERR_ADMIN_SITE_NOT_SHAREPOINT',"
    " ''))")

bootstrap_ng, _ = chain([
    ("Set_Bootstrap_Invalid", setvar("varIsValid", False)),
    ("Set_Bootstrap_NoConfig", setvar("varNoConfig", True)),
    ("Set_Bootstrap_FailedStage", setvar("varFailedStage", "00_Bootstrap")),
    ("Set_Bootstrap_ErrorMessage", setvar(
        "varErrorMessage",
        "このフローの Compose_AdminSiteUrl が未設定です。"
        "初期設定フロー「Teamsチャネルメンバー同期 初期設定・テスト」を先に実行し、"
        "その実行結果 Compose_Result_Summary の adminSiteUrl に出ている値を、"
        "このフローの Compose_AdminSiteUrl アクションへ貼り付けて保存してください"
        "（初期設定フローの実行結果 nextAction にも同じ案内が出ます）。")),
])

bootstrap_seq = [("Set_Stage_Bootstrap", setvar("varStage", "00_Bootstrap"))] + admin_seq + [
    ("Set_ConfigSiteUrl", setvar("varConfigSiteUrl", "@outputs('%s')" % ADMIN_ROOT)),
    ("Compose_Bootstrap_Code", compose(BOOTSTRAP_CODE)),
    ("Set_Bootstrap_ErrorCode", setvar("varErrorCode", "@outputs('Compose_Bootstrap_Code')")),
]
bootstrap_inner, bootstrap_last = chain(bootstrap_seq)
bootstrap_inner["Condition_Bootstrap_Failed"] = cond(
    {"and": [{"not": eq("@outputs('Compose_Bootstrap_Code')", "")}]}, bootstrap_ng,
    runafter=ra(bootstrap_last))
actions["Scope_00_Bootstrap"] = scope(bootstrap_inner, ra("Compose_AdminSiteUrl"))

# =========================================================================
# Scope_01_LocateConfigList : 設定リストの位置と型名を特定する
# 定期フローは設定リストを **作らない**。無ければ「初回設定が未完了」として終了する。
# =========================================================================
actions["Scope_01_LocateConfigList"] = sb.build_ensure_list(
    "Config", sb.DS_CONFIG, "'%s'" % sb.CONFIG_LIST_TITLE,
    "varConfigListId", "varConfigListEntityType", sb.CONFIG_FIELDS,
    allow_create=False, ensure_fields=False, runafter=ra("Scope_00_Bootstrap"))

# =========================================================================
# Scope_02_ReadConfig : 有効な設定を読み込む
# =========================================================================
read_body, read_last = chain([
    ("Get_Config_Items", http("GET", sb.list_uri("varConfigListId", sb.CONFIG_ITEMS_SELECT),
                              sb.H_NOMETA, dataset=sb.DS_CONFIG)),
    ("Filter_Enabled_Configs", query(
        "@coalesce(body('Get_Config_Items')?['value'], json('[]'))",
        "@equals(coalesce(item()?['IsEnabled'], false), true)")),
    ("Set_Configs", setvar("varConfigs", "@body('Filter_Enabled_Configs')")),
])

read_inner = {}
read_inner["Set_Stage_ReadConfig"] = setvar("varStage", "01_ReadConfig")
read_inner["Condition_Can_Read_Config"] = cond(
    sb.is_valid(), read_body, runafter=ra("Set_Stage_ReadConfig"))
# 有効な設定が0件のときは、無効なURLで処理を続けずここで「未設定」を確定させる。
read_inner["Condition_No_Enabled_Config"] = cond(
    {"and": [eq("@length(variables('varConfigs'))", 0)]},
    dict(chain([
        ("Set_NoConfig", setvar("varNoConfig", True)),
        ("Compose_Not_Configured", compose({
            "status": "NOT_CONFIGURED",
            "message": "有効な同期設定がありません。初期設定・テストフロー"
                       "（Teamsチャネルメンバー同期 初期設定・テスト）を実行して、"
                       "TeamsチャネルURL・SharePointサイトURL・リスト名を登録してください。"
                       "初期設定フローを実行済みの場合は、その実行結果 adminSiteUrl と"
                       "このフローの Compose_AdminSiteUrl が同じ値かを確認してください"
                       "（違うサイトを見ていると設定が見つかりません）。",
            "configListTitle": sb.CONFIG_LIST_TITLE,
            "adminSiteUrl": "@variables('varConfigSiteUrl')",
            "checkedAt": "@utcNow()",
        })),
    ])[0]),
    runafter=ra("Condition_Can_Read_Config"))
actions["Scope_02_ReadConfig"] = scope(read_inner, ra("Scope_01_LocateConfigList"))

# =========================================================================
# Foreach_Config : 設定ごとに同期する
#
# ネスト深さを抑えるため、この Foreach はトップレベルに置く（If でくるまない）。
# 有効な設定が0件なら varConfigs が空配列なので、ループは1回も回らない。
#
# 1件の設定で失敗しても他の設定を巻き込まないよう、各繰り返しの最後に置く
# Scope_11_RecordResult の runAfter を4状態すべてにしてある。
# =========================================================================
CFG = "items('Foreach_Config')"

config_seq = sb.build_reset_sequence("_PerConfig") + [
    ("Set_Cfg_TeamsChannelUrl",
     setvar("varTeamsChannelUrl", "@trim(string(coalesce(%s?['TeamsChannelUrl'], '')))" % CFG)),
    ("Set_Cfg_TeamId", setvar("varTeamId", "@trim(string(coalesce(%s?['TeamId'], '')))" % CFG)),
    ("Set_Cfg_ChannelId",
     setvar("varChannelId", "@trim(string(coalesce(%s?['ChannelId'], '')))" % CFG)),
    ("Set_Cfg_TenantId",
     setvar("varTenantId", "@trim(string(coalesce(%s?['TenantId'], '')))" % CFG)),
    ("Set_Cfg_SiteUrl", setvar("varSiteUrl", "@trim(string(coalesce(%s?['SiteUrl'], '')))" % CFG)),
    ("Set_Cfg_ListName",
     setvar("varListName", "@trim(string(coalesce(%s?['ListTitle'], '')))" % CFG)),
    ("Increment_Processed_Config", incr("varProcessedConfigCount")),
]

# --- 必須項目の検証（保存済みの値であっても素通りさせない） ---
# 【セキュリティ】保存済みのサイトURLでも、SharePoint 以外のホストは受け付けない。
CFG_HOST = sb.host_of("variables('varSiteUrl')")
CONFIG_CHECK = (
    "@if(empty(variables('varTeamId')), 'ERR_CONFIG_TEAMID_MISSING',"
    " if(empty(variables('varChannelId')), 'ERR_CONFIG_CHANNELID_MISSING',"
    " if(empty(variables('varSiteUrl')), 'ERR_CONFIG_SITEURL_MISSING',"
    " if(empty(variables('varListName')), 'ERR_CONFIG_LISTNAME_MISSING',"
    " if(not(endsWith(" + CFG_HOST + ", '.sharepoint.com')), 'ERR_CONFIG_SITEURL_NOT_SHAREPOINT',"
    " '')))))")

config_seq += [
    ("Compose_Config_Check", compose(CONFIG_CHECK)),
    ("Set_Config_ErrorCode", setvar("varErrorCode", "@outputs('Compose_Config_Check')")),
]
config_inner, config_last = chain(config_seq)
config_inner["Condition_Config_Incomplete"] = cond(
    {"and": [{"not": eq("@outputs('Compose_Config_Check')", "")}]},
    dict(chain([
        ("Set_Config_Invalid", setvar("varIsValid", False)),
        ("Set_Config_FailedStage", setvar("varFailedStage", "02_ValidateConfig")),
        ("Set_Config_ErrorMessage", setvar(
            "varErrorMessage",
            "設定に必須項目の欠落、またはSharePoint以外のサイトURLがあります。"
            "初期設定・テストフローで設定を登録し直してください。")),
    ])[0]),
    runafter=ra(config_last))

# --- 共通同期ブロック（初期設定フローとまったく同じ） ---
sync_scopes, SYNC_LAST = sb.build_sync_scopes(ra("Condition_Config_Incomplete"))
config_inner.update(sync_scopes)

# --- Scope_11_RecordResult : 設定リストへ結果を書き戻す ---
SYNC_COUNTS = {
    "memberCount": "@variables('varMemberCount')",
    "created": "@variables('varCreatedCount')",
    "updated": "@variables('varUpdatedCount')",
    "unchanged": "@variables('varUnchangedCount')",
    "deactivated": "@variables('varDeactivatedCount')",
    "errors": "@variables('varErrorCount')",
    "memberSource": "@variables('varMemberSource')",
    "channelType": "@variables('varChannelType')",
    "failedStage": "@variables('varFailedStage')",
    "errorCode": "@variables('varErrorCode')",
    "runKind": "daily",
    "at": "@utcNow()",
}

record_body, record_last = chain([
    ("Compose_Record_Counts", compose(SYNC_COUNTS)),
    ("Compose_Record_Result_Text", compose("@string(outputs('Compose_Record_Counts'))")),
    ("Compose_Record_Config_Id", compose("@string(coalesce(%s?['Id'], 0))" % CFG)),
    ("Compose_Record_Body", compose({
        "__metadata": {"type": "@variables('varConfigListEntityType')"},
        "LastSyncAt": "@utcNow()",
        "LastSyncResult": "@outputs('Compose_Record_Result_Text')",
        "ChannelType": "@variables('varChannelType')",
        "MemberSource": "@variables('varMemberSource')",
    })),
    ("Update_Config_Record", http(
        "POST", sb.item_uri("varConfigListId", "outputs('Compose_Record_Config_Id')"),
        sb.H_MERGE_V, "@string(outputs('Compose_Record_Body'))", dataset=sb.DS_CONFIG)),
])
# 結果の書き戻しに失敗しても、ここで実行を落とさない（同期そのものは終わっている）
record_body["Append_Record_Error"] = append(
    "varConfigResults", {"configKey": "@trim(string(coalesce(%s?['ConfigKey'], '')))" % CFG,
                         "code": "WARN_CONFIG_RECORD_FAILED"},
    {"Update_Config_Record": ["Failed", "TimedOut"]})
record_body["Append_Config_Result"] = append(
    "varConfigResults", {
        "configKey": "@trim(string(coalesce(%s?['ConfigKey'], '')))" % CFG,
        "teamId": "@variables('varTeamId')",
        "channelId": "@variables('varChannelId')",
        "listName": "@variables('varListName')",
        "counts": "@outputs('Compose_Record_Counts')",
        "succeeded": "@and(equals(variables('varIsValid'), true),"
                     " empty(variables('varFailedStage')))",
    },
    {"Update_Config_Record": ["Succeeded", "Failed", "TimedOut", "Skipped"],
     "Append_Record_Error": ["Succeeded", "Skipped"]})

record_inner = {}
record_inner["Set_Stage_RecordResult"] = setvar("varStage", "11_RecordResult")
record_inner["Condition_Can_Record"] = cond(
    {"and": [{"greater": ["@length(variables('varConfigListId'))", 0]}]}, record_body,
    runafter=ra("Set_Stage_RecordResult"))
config_inner["Scope_11_RecordResult"] = scope(
    record_inner, {SYNC_LAST: ["Succeeded", "Failed", "Skipped", "TimedOut"]})

actions["Foreach_Config"] = foreach("@variables('varConfigs')", config_inner,
                                    ra("Scope_02_ReadConfig"))

# =========================================================================
# Scope_ErrorHandler（Catch相当）
# runAfter は直前の Foreach_Config 1本にだけ張る（複数列挙は AND 判定になる）。
# 1設定ごとの失敗は Scope_11_RecordResult が吸収するため、ここが発火するのは
# 設定の読み込み自体が失敗した場合など「想定外の失敗」だけになる。
# =========================================================================
handler_inner, _ = chain([
    ("Set_Handler_Invalid", setvar("varIsValid", False)),
    ("Compose_Handler_FailedStage", compose(
        "@if(empty(variables('varFailedStage')), variables('varStage'),"
        " variables('varFailedStage'))")),
    ("Set_Handler_FailedStage", setvar("varFailedStage",
                                       "@outputs('Compose_Handler_FailedStage')")),
    ("Compose_Handler_ErrorMessage", compose(
        "@if(empty(variables('varErrorMessage')),"
        " '想定外のエラーが発生しました。実行履歴で失敗したアクションを確認してください。',"
        " variables('varErrorMessage'))")),
    ("Set_Handler_ErrorMessage", setvar("varErrorMessage",
                                        "@outputs('Compose_Handler_ErrorMessage')")),
])
actions["Scope_ErrorHandler"] = {
    "type": "Scope", "actions": handler_inner,
    "runAfter": {"Foreach_Config": ["Failed", "Skipped", "TimedOut"]},
}

# =========================================================================
# Scope_Finalize（Finally相当）
# 氏名・メールアドレスは含めない（要件§12）。件数と識別子だけを残す。
# =========================================================================
RESULT = {
    "runKind": "daily",
    "runId": "@workflow()?['run']?['name']",
    "executedAt": "@utcNow()",
    "status": "@if(equals(variables('varNoConfig'), true), 'NOT_CONFIGURED',"
              " if(empty(variables('varFailedStage')), 'OK', 'FAILED'))",
    "adminSiteUrl": "@variables('varConfigSiteUrl')",
    "configListTitle": sb.CONFIG_LIST_TITLE,
    "enabledConfigCount": "@length(variables('varConfigs'))",
    "processedConfigCount": "@variables('varProcessedConfigCount')",
    "configResults": "@variables('varConfigResults')",
    "failedStage": "@variables('varFailedStage')",
    "errorCode": "@variables('varErrorCode')",
    "errorMessage": "@variables('varErrorMessage')",
    "httpStatusCode": "@variables('varLastStatusCode')",
}

actions["Scope_Finalize"] = {
    "type": "Scope",
    "actions": {"Compose_Result_Summary": compose(RESULT)},
    "runAfter": {"Scope_ErrorHandler": ["Succeeded", "Failed", "Skipped", "TimedOut"]},
}

# =========================================================================
# definition.json
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
        "Recurrence": {
            "type": "Recurrence",
            "recurrence": {
                "frequency": "Day",
                "interval": 1,
                "schedule": {"hours": [SCHEDULE_HOUR], "minutes": [SCHEDULE_MINUTE]},
                "timeZone": SCHEDULE_TIMEZONE,
                "startTime": SCHEDULE_START,
            },
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
        "description": "保存済みの設定を読み、Teamsチャネルのメンバーを毎日"
                       "SharePointリストへ同期する定期実行フロー",
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
