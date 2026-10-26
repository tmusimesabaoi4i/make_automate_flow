# -*- coding: utf-8 -*-
"""
Teams チャネルメンバー同期 — 共通アクション生成モジュール（本案件の唯一の定義元）。

フローA（初期設定・テスト同期 / 手動 Button）とフローB（日次同期 / Recurrence）は、
同じ同期処理を実行する。Power Automate の「子フローを実行する」は Dataverse ソリューションを
必須とし（learn.microsoft.com/power-automate/create-child-flows）、本リポジトリが採用している
レガシーパッケージ形式では使えない。そこで **実行時ではなく生成時に共通化**する。
両フローの build_*.py が本モジュールを import し、まったく同じアクション辞書を埋め込む。
保守が発生する場所（Python ソース）での重複はゼロになる。

【共通ブロックの契約】
  本モジュールが生成するアクションは「変数」だけに依存する。トリガー本文も設定リストの
  アイテムも直接参照しない。各フローが下記の変数を埋めてから共通ブロックを呼ぶ。

    varSiteUrl      同期先 SharePoint サイトの正規化済みルートURL
    varListName     同期先リストの表示名
    varTeamId       チームID（groupId）
    varChannelId    チャネルID（デコード済み。例 19:xxxx@thread.tacv2）
    varTenantId     テナントID（URLに無ければ空文字。空のとき外部ユーザー判定は行わない）
    varIsValid      ここまでの処理が正常か（false なら共通ブロックは何もしない）

【不変則】definition.json は生成物。修正は必ず本モジュールか build_*.py を編集して再生成する。
"""

# =========================================================================
# 接続・ホスト・ヘッダー
# =========================================================================
# 接続参照の認証方式。レガシーパッケージには2つの形がある（handbook/rules/07）。
#
#   embedded : "authentication": "@parameters('$authentication')" ／ source: "Embedded"
#   invoker  : X-MS-APIM-Tokens を復号する式          ／ source: "Invoker"
#
# 本案件は **embedded** を採用する。理由:
#   invoker 形式は triggerOutputs().headers['X-MS-APIM-Tokens'] に依存する。この
#   ヘッダーは「フローを起動した人」の文脈があるときに載るもので、Recurrence（定期実行）
#   トリガーには起動者がいない。本リポジトリで invoker 形式の実績があるのは
#   ボタントリガーのフロー（teams_post_url_flows）だけで、定期実行フローでの実績は無い。
#   一方 embedded 形式は references/extracted の Microsoft 実エクスポート3本すべてが
#   採用しており、そのうち shared-mailbox-to-teams-notify は
#   **ポーリングトリガー（起動者のいない自動フロー）** である。手動フローについても
#   CreateKnowledgeList（ボタン＋SharePoint REST）が embedded で動作している。
#   つまり embedded だけが「両方のトリガー種別で実エクスポートの裏付けがある」形。
# 実機で差異が出た場合はこの1定数を "invoker" に変えて再生成する（docs/troubleshooting.md）。
AUTH_MODE = "embedded"

AUTH_EMBEDDED = "@parameters('$authentication')"
AUTH_INVOKER = {
    "value": "@json(decodeBase64(triggerOutputs().headers['X-MS-APIM-Tokens']))['$ConnectionKey']",
    "type": "Raw"}

AUTH = AUTH_EMBEDDED if AUTH_MODE == "embedded" else AUTH_INVOKER
CONNECTION_SOURCE = "Embedded" if AUTH_MODE == "embedded" else "Invoker"


def connection_reference(connection_name, api_name):
    """properties.connectionReferences の1エントリ。
    利用者固有の接続IDは埋め込まない（匿名GUIDはインポート時に実接続へ再マッピングされる）。"""
    ref = {"connectionName": connection_name,
           "source": CONNECTION_SOURCE,
           "id": "/providers/Microsoft.PowerApps/apis/" + api_name,
           "tier": "NotSpecified",
           "apiName": api_name.replace("shared_", "")}
    if CONNECTION_SOURCE == "Embedded":
        # Microsoft の実エクスポートに含まれるキー。Embedded のときだけ付ける。
        ref["isProcessSimpleApiReferenceConversionAlreadyDone"] = False
    return ref

HOST_SPO = {"apiId": "/providers/Microsoft.PowerApps/apis/shared_sharepointonline",
            "connectionName": "shared_sharepointonline", "operationId": "HttpRequest"}
HOST_TEAMS = {"apiId": "/providers/Microsoft.PowerApps/apis/shared_teams",
              "connectionName": "shared_teams", "operationId": None}

H_VERBOSE = {"Accept": "application/json;odata=verbose",
             "Content-Type": "application/json;odata=verbose"}
H_NOMETA = {"Accept": "application/json;odata=nometadata"}
H_MERGE_V = {"Accept": "application/json;odata=verbose",
             "Content-Type": "application/json;odata=verbose",
             "IF-MATCH": "*", "X-HTTP-Method": "MERGE"}
H_MERGE_N = {"Accept": "application/json;odata=nometadata",
             "Content-Type": "application/json;odata=nometadata",
             "IF-MATCH": "*", "X-HTTP-Method": "MERGE"}

# サイトアドレスは常に実行時に決まる値を使う（サイトURLをフロー定義へ固定しない）。
# HttpRequest の dataset が式でよいことは実環境で実証済み
# （handbook/knowledge/sharepoint_rest_list_provisioning.md §11、2026-07-24）。
DS_TARGET = "@variables('varSiteUrl')"        # 同期先サイト（メンバーリスト）
DS_CONFIG = "@variables('varConfigSiteUrl')"  # 管理サイト（設定リスト）

GRAPH_ROOT = "https://graph.microsoft.com/v1.0"

# このフローが作成・管理するアイテムだけを対象にするための印。
# 対象外の既存アイテムには絶対に触れない（要件§9・§10）。
SYNC_SOURCE = "TeamsChannelMemberSync"

# 設定リストの表示名。管理サイト上の1リストだけを設定の正本にする。
CONFIG_LIST_TITLE = "Teamsチャネルメンバー同期設定"

MEMBER_STATUS_ACTIVE = "在籍"
MEMBER_STATUS_LEFT = "離脱"

# =========================================================================
# ListMembers（Teams コネクタ）のパラメータ
#
# 【確定】threadType のワイヤ値は "channel" / "groupchat"（いずれも小文字）。
#   根拠: shared_teams のコネクタ swagger 現物 listMembersThreadType__in_path の
#         enum: ["groupchat","channel"] / x-ms-enum-values の displayName は "Group chat" / "Channel"。
#         Microsoft 公式リポジトリ microsoft/Power-Fx の旧版 swagger でも同じ形を確認。
#   公式ドキュメント（learn.microsoft.com/connectors/teams）は "Choose message type" としか
#   書いておらず enum を載せていない。UI ラベル 'Channel' は RemoveMemberFromChannel の
#   説明文で確認できる。
#
# 【要実環境確認】body（dynamic 型）配下のキー名。
#   ListMembers を threadType=channel で使った実エクスポート定義は公開例が存在しない。
#   兄弟アクション GetMessageDetails（同じ threadType 駆動の dynamic-body パターン）の
#   実エクスポート定義が body/recipient/groupId・body/recipient/channelId を使っており、
#   Microsoft 公式テストフィクスチャ Teams_GetMessageDetails_InputType.json も
#   recipient オブジェクト（required: groupId, channelId）を示している。そこからの推論。
#   実機で差異が出た場合は **この2定数だけ** を直して再生成すれば足りる。
# =========================================================================
LISTMEMBERS_THREAD_TYPE = "channel"
LISTMEMBERS_KEY_TEAM = "body/recipient/groupId"
LISTMEMBERS_KEY_CHANNEL = "body/recipient/channelId"

# メンバー取得の経路。
#   "connector_first" … ListMembers を主経路にし、失敗時だけ Graph へフォールバック（既定）
#   "graph_only"      … ListMembers を使わず Graph だけを使う
# ListMembers のパラメータ形状が実機と違うと **保存時** に
# OpenApiOperationParameterValidationFailed になる。その場合はここを "graph_only" に変えて
# 再生成すれば、同期機能を落とさずに回避できる（docs/troubleshooting.md）。
MEMBER_SOURCE_MODE = "connector_first"

# =========================================================================
# 逐語コピーの REST 断片
# handbook/knowledge/sharepoint_rest_list_provisioning.md §12 / §16 から逐語コピーしている。
# 要約から書き起こすと投影が落ちて 403 になる（同 §15 の実発生事例）。短くしないこと。
# =========================================================================
LISTS_SELECT = ("_api/web/lists?$select=Id,Title,Hidden,BaseTemplate,RootFolder/ServerRelativeUrl"
                "&$expand=RootFolder&$top=5000")
LIST_INFO_SELECT = ("?$select=Id,Title,ListItemEntityTypeFullName,RootFolder/ServerRelativeUrl"
                    "&$expand=RootFolder")
FIELDS_SELECT = "/fields?$select=Id,Title,InternalName,TypeAsString&$top=5000"

# 既存アイテムは $filter を使わず、$select + $top のページングで全件取得してから
# Filter array で絞り込む。理由:
#   1. $filter の2段エスケープ（'' 二重化 + uriComponent）の取り違えによる事故を構造的に排除できる
#   2. 非インデックス列への $filter は 5,000 件のビューしきい値で失敗するが、
#      ID順の素のページングはしきい値に触れない
ITEMS_SELECT = ("/items?$select=Id,Title,FullName,LastName,FirstName,Email,SyncKey,TeamsUserId,"
                "MembershipId,TeamId,ChannelId,MemberTenantId,MemberRoles,MembershipKind,"
                "IsExternalUser,MemberStatus,IsActive,SyncSource&$top=1000")
CONFIG_ITEMS_SELECT = ("/items?$select=Id,Title,ConfigKey,TeamsChannelUrl,TeamId,ChannelId,TenantId,"
                       "SiteUrl,ListTitle,ChannelType,MemberSource,IsEnabled,ConfigVersion&$top=500")


# =========================================================================
# 列定義
#   DisplayName = Name = ASCII で作成し、内部名を安定させる（§4）。
#   そのうえで表示名だけを日本語へ MERGE する。**新規に作成した列に対してだけ**行うため、
#   既存列の表示名・型は一切変更されない（要件§9）。
# =========================================================================
def _text(name, display, maxlen=255):
    return {"internal": name, "display": display, "type": "Text",
            "xml": '<Field Type="Text" DisplayName="%s" Name="%s" StaticName="%s" '
                   'Required="FALSE" MaxLength="%d" />' % (name, name, name, maxlen)}


def _note(name, display, lines=4):
    return {"internal": name, "display": display, "type": "Note",
            "xml": '<Field Type="Note" DisplayName="%s" Name="%s" StaticName="%s" '
                   'Required="FALSE" RichText="FALSE" NumLines="%d" />' % (name, name, name, lines)}


def _bool(name, display):
    return {"internal": name, "display": display, "type": "Boolean",
            "xml": '<Field Type="Boolean" DisplayName="%s" Name="%s" StaticName="%s" '
                   'Required="FALSE" />' % (name, name, name)}


def _date(name, display):
    return {"internal": name, "display": display, "type": "DateTime",
            "xml": '<Field Type="DateTime" DisplayName="%s" Name="%s" StaticName="%s" '
                   'Required="FALSE" Format="DateTime" />' % (name, name, name)}


def _number(name, display):
    return {"internal": name, "display": display, "type": "Number",
            "xml": '<Field Type="Number" DisplayName="%s" Name="%s" StaticName="%s" '
                   'Required="FALSE" />' % (name, name, name)}


# メンバーリスト。
# 【重要】氏名は組み込みの Title 列に入れない。Title は「同期キー」を保持するだけの
# 内部識別子とし、人が見る値（氏名・姓・名・メールアドレス）はすべて専用の列に持たせる。
# 組み込み列（Title）は既存リストを壊さないため、表示名も型も必須設定も一切変更しない。
MEMBER_FIELDS = [
    _text("FullName", "氏名"),
    _text("LastName", "姓"),
    _text("FirstName", "名"),
    _text("Email", "メールアドレス"),
    _text("SyncKey", "同期キー"),
    _text("TeamsUserId", "TeamsユーザーID"),
    _text("MembershipId", "メンバーシップID"),
    _text("TeamId", "チームID"),
    _text("ChannelId", "チャネルID"),
    _text("MemberTenantId", "メンバーテナントID"),
    _text("MemberRoles", "ロール"),
    _text("MembershipKind", "メンバー種別"),
    _bool("IsExternalUser", "外部ユーザー"),
    _text("MemberStatus", "同期状態"),
    _bool("IsActive", "有効"),
    _date("LastSyncedAt", "最終同期更新日時"),
    _text("SyncSource", "同期元"),
]

# 設定リスト。Title は設定名（人が読むためのラベル）。
CONFIG_FIELDS = [
    _text("ConfigKey", "設定キー"),
    _note("TeamsChannelUrl", "TeamsチャネルURL", 3),
    _text("TeamId", "チームID"),
    _text("ChannelId", "チャネルID"),
    _text("TenantId", "テナントID"),
    _note("SiteUrl", "SharePointサイトURL", 3),
    _text("ListTitle", "SharePointリスト名"),
    _text("ChannelType", "チャネル種別"),
    _text("MemberSource", "メンバー取得方式"),
    _bool("IsEnabled", "有効"),
    _number("ConfigVersion", "設定バージョン"),
    _date("LastTestSucceededAt", "最終テスト成功日時"),
    _date("LastSyncAt", "最終同期日時"),
    _note("LastSyncResult", "最終同期結果", 4),
    _date("UpdatedAt", "設定更新日時"),
]


# =========================================================================
# アクション生成ヘルパー
# =========================================================================
def ra(prev, states=("Succeeded",)):
    return {} if prev is None else {prev: list(states)}


def oac(host, opid, params, runafter=None):
    """OpenApiConnection アクション（コネクタ呼び出し）"""
    h = dict(host)
    h["operationId"] = opid
    return {"type": "OpenApiConnection",
            "inputs": {"parameters": params, "host": h, "authentication": AUTH},
            "runAfter": runafter or {}}


def http(method, uri, headers, body=None, runafter=None, dataset=DS_TARGET):
    """SharePoint「HTTP要求を送信します」アクション（dataset は式でよい）"""
    params = {"dataset": dataset, "parameters/method": method, "parameters/uri": uri,
              "parameters/headers": dict(headers)}
    if body is not None:
        params["parameters/body"] = body
    return {"type": "OpenApiConnection",
            "inputs": {"parameters": params, "host": dict(HOST_SPO), "authentication": AUTH},
            "runAfter": runafter or {}}


def graph(uri_expr, runafter=None):
    """Teams コネクタの「Microsoft Graph に HTTP 要求を送信する」（GET のみ使う）"""
    return oac(HOST_TEAMS, "HttpRequest",
               {"Uri": uri_expr, "Method": "GET", "ContentType": "application/json"}, runafter)


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
    """Filter array。where の中の item() は from の要素を指す。
    ループ内で外側の値と突き合わせるときは **変数**（varCurrent*）を使う。
    実績のある形に合わせるため outputs() は where に置かない。"""
    return {"type": "Query", "inputs": {"from": from_expr, "where": where_expr},
            "runAfter": runafter or {}}


def foreach(items_expr, actions, runafter=None):
    """Apply to each（変数を更新するため並列は必ずオフ）"""
    return {"type": "Foreach", "foreach": items_expr, "actions": actions,
            "runtimeConfiguration": {"concurrency": {"repetitions": 1}},
            "runAfter": runafter or {}}


def until(condition_expr, actions, runafter=None, count=200):
    return {"type": "Until", "expression": condition_expr,
            "limit": {"count": count, "timeout": "PT1H"},
            "actions": actions, "runAfter": runafter or {}}


def cond(expr_obj, true_actions, else_actions=None, runafter=None):
    a = {"type": "If", "expression": expr_obj, "actions": true_actions, "runAfter": runafter or {}}
    if else_actions:
        a["else"] = {"actions": else_actions}
    return a


def scope(inner, runafter=None):
    return {"type": "Scope", "actions": inner, "runAfter": runafter or {}}


def eq(left, right):
    return {"equals": [left, right]}


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


def is_valid():
    """共通ブロックの実行ゲート。ここまでの段階が正常なときだけ処理する。"""
    return {"and": [eq("@variables('varIsValid')", True)]}


# --- URI ビルダー: 書き込み対象は常にリストID。リスト名では特定しない ---
def list_uri(list_id_var, suffix=""):
    return "@concat('_api/web/lists(guid''', variables('%s'), ''')%s')" % (list_id_var, suffix)


def item_uri(list_id_var, item_id_expr):
    return ("@concat('_api/web/lists(guid''', variables('%s'), ''')/items(', %s, ')')"
            % (list_id_var, item_id_expr))


def field_uri(list_id_var, name_var):
    return ("@concat('_api/web/lists(guid''', variables('%s'),"
            " ''')/fields/getbyinternalnameortitle(''', variables('%s'), ''')')"
            % (list_id_var, name_var))


def view_uri(list_id_var, view_id_var, suffix=""):
    return ("@concat('_api/web/lists(guid''', variables('%s'), ''')/views(guid''',"
            " variables('%s'), ''')%s')" % (list_id_var, view_id_var, suffix))


def add_view_field_uri(list_id_var, view_id_var, name_var):
    return ("@concat('_api/web/lists(guid''', variables('%s'), ''')/views(guid''',"
            " variables('%s'), ''')/viewfields/AddViewField(''', variables('%s'), ''')')"
            % (list_id_var, view_id_var, name_var))


def relative_next(next_expr):
    """SharePoint が返す絶対URLの継続リンクをサイト相対の `_api/...` へ直す。
    `_api/` を含まない場合も split→last が元の文字列を返すため両分岐とも安全
    （if() は使わない側の分岐も先行評価される）。"""
    return ("@if(contains(%s, '/_api/'), concat('_api/', last(split(%s, '/_api/'))), %s)"
            % (next_expr, next_expr, next_expr))


def next_link_of(action_name):
    """SharePoint REST の継続リンク。odata=nometadata なら 'odata.nextLink'。
    テナント／受理ヘッダーの差で `@odata.nextLink`（v4形）や verbose の `d.__next` に
    なる可能性があるため、3形すべてを coalesce で受ける。"""
    b = "body('%s')" % action_name
    return ("@trim(string(coalesce(%s?['odata.nextLink'], %s?['@odata.nextLink'],"
            " %s?['d']?['__next'], '')))" % (b, b, b))


# =========================================================================
# URL の解析ヘルパー（両フローが使う）
# =========================================================================
def host_of(url_expr):
    """URL 文字列からホスト名（小文字）を取り出す。'://' が無くても壊れない。"""
    return "toLower(first(split(last(split(%s, '://')), '/')))" % url_expr


# substring の開始位置は「0以上 **かつ文字列長より小さい**」ことが要求される。
# したがって **空文字には substring('', 0, 0) すら適用できない**。
#   実機のエラー（2026-08-04 実発生）:
#   The template language function 'substring' parameter is out of range:
#   'start index' must be non-negative integer and should be less than the length of the string.
# 末尾に1文字の番兵を足してから切り出すことで、入力が空でも必ず成立させる。
# 番兵は length 引数で切り落とされるため結果には現れない。
SUBSTRING_SENTINEL = "#"


def safe_substring(s_expr, start_expr, length_expr):
    """空文字でも失敗しない substring。
    `0 <= start_expr <= length(s)` かつ `start_expr + length_expr <= length(s)` であれば、
    番兵によって常に `start < 長さ` が成立する。"""
    return ("substring(concat(%s, '%s'), %s, %s)"
            % (s_expr, SUBSTRING_SENTINEL, start_expr, length_expr))


def build_normalize_site_url(prefix, src_expr):
    """SharePoint の管理画面URL・一覧URLから、コネクタで使えるサイトルートURLを作る。

    (1) フラグメントとクエリを落とす
    (2) `/_layouts/` `/_api/` `/Lists/` `/SitePages/` `/Forms/` 以降を落とす
    (3) `/sites/<名前>` `/teams/<名前>` があれば、その1セグメントまでで打ち切る
    (4) 末尾のスラッシュを落とす

    大文字小文字を区別しないよう、位置の判定は小文字化した文字列で行い、切り出しは
    元の文字列に対して行う（toLower は長さを変えないので位置が一致する）。
    Logic Apps の if() は使わない側の分岐も先行評価するため、substring に渡す位置は
    必ず「先に Compose で確定させた安全な値」にする（lessons_learned §21）。

    戻り値: ((name, action) のリスト, 最終結果のアクション名)
    """
    p = prefix
    n_nofrag = "Compose_%s_NoFragment" % p
    n_noquery = "Compose_%s_NoQuery" % p
    n_lower = "Compose_%s_Lower" % p
    n_cutidx = "Compose_%s_CutIndex" % p
    n_cut = "Compose_%s_Cut" % p
    n_cutlower = "Compose_%s_CutLower" % p
    n_anchor = "Compose_%s_AnchorIndex" % p
    n_anchored = "Compose_%s_Anchored" % p
    n_final = "Compose_%s_SiteRoot" % p

    o = lambda name: "outputs('%s')" % name
    lower = o(n_lower)
    cut = o(n_cut)
    cutlower = o(n_cutlower)
    anchor = o(n_anchor)
    anchored = o(n_anchored)

    cut_index = ("@if(contains(%(L)s, '/_layouts/'), indexOf(%(L)s, '/_layouts/'),"
                 " if(contains(%(L)s, '/_api/'), indexOf(%(L)s, '/_api/'),"
                 " if(contains(%(L)s, '/lists/'), indexOf(%(L)s, '/lists/'),"
                 " if(contains(%(L)s, '/sitepages/'), indexOf(%(L)s, '/sitepages/'),"
                 " if(contains(%(L)s, '/forms/'), indexOf(%(L)s, '/forms/'),"
                 " length(%(L)s))))))" % {"L": lower})
    anchor_index = ("@if(contains(%(C)s, '/sites/'), add(indexOf(%(C)s, '/sites/'), 7),"
                    " if(contains(%(C)s, '/teams/'), add(indexOf(%(C)s, '/teams/'), 7), 0))"
                    % {"C": cutlower})
    # if() は使わない側の分岐も先行評価するため、両分岐の substring が単体で成立する
    # 必要がある。番兵付き（safe_substring）にしてあるので、cut が空文字でも壊れない。
    anchored_expr = ("@if(greater(%(A)s, 0),"
                     " concat(%(HEAD)s, first(split(%(TAIL)s, '/'))),"
                     " %(D)s)"
                     % {"A": anchor, "D": cut,
                        "HEAD": safe_substring(cut, "0", anchor),
                        "TAIL": safe_substring(cut, anchor,
                                               "sub(length(%s), %s)" % (cut, anchor))})
    # 末尾スラッシュの除去。substring で長さ-1 を取ると空文字のとき失敗するため
    # split→take→join で行う（空文字でも安全）。
    final_expr = ("@if(endsWith(%(G)s, '/'),"
                  " join(take(split(%(G)s, '/'), sub(length(split(%(G)s, '/')), 1)), '/'),"
                  " %(G)s)" % {"G": anchored})

    seq = [
        (n_nofrag, compose("@first(split(trim(coalesce(%s, '')), '#'))" % src_expr)),
        (n_noquery, compose("@first(split(%s, '?'))" % o(n_nofrag))),
        (n_lower, compose("@toLower(%s)" % o(n_noquery))),
        (n_cutidx, compose(cut_index)),
        (n_cut, compose("@" + safe_substring(o(n_noquery), "0", o(n_cutidx)))),
        (n_cutlower, compose("@toLower(%s)" % cut)),
        (n_anchor, compose(anchor_index)),
        (n_anchored, compose(anchored_expr)),
        (n_final, compose(final_expr)),
    ]
    return seq, n_final


# =========================================================================
# 変数
# 共通ブロックが読み書きする変数。InitializeVariable はトップレベルにしか置けないため
# （handbook/rules/01）、各フローがこの一覧をそのまま Initialize_* の連鎖に展開する。
# =========================================================================
SHARED_VARIABLES = [
    # --- 制御・診断 ---
    ("Initialize_IsValid", "varIsValid", "boolean", True),
    ("Initialize_Stage", "varStage", "string", "Initialize"),
    ("Initialize_FailedStage", "varFailedStage", "string", ""),
    ("Initialize_ErrorCode", "varErrorCode", "string", ""),
    ("Initialize_ErrorMessage", "varErrorMessage", "string", ""),
    ("Initialize_LastStatusCode", "varLastStatusCode", "string", "0"),
    ("Initialize_LastErrorBody", "varLastErrorBody", "string", ""),
    ("Initialize_ItemErrors", "varItemErrors", "array", []),
    # --- 管理サイト・設定リスト ---
    ("Initialize_ConfigSiteUrl", "varConfigSiteUrl", "string", ""),
    ("Initialize_ConfigListId", "varConfigListId", "string", ""),
    ("Initialize_ConfigListEntityType", "varConfigListEntityType", "string", ""),
    # --- 同期対象 ---
    ("Initialize_TeamsChannelUrl", "varTeamsChannelUrl", "string", ""),
    ("Initialize_TeamId", "varTeamId", "string", ""),
    ("Initialize_ChannelId", "varChannelId", "string", ""),
    ("Initialize_TenantId", "varTenantId", "string", ""),
    ("Initialize_ChannelType", "varChannelType", "string", ""),
    ("Initialize_ChannelDisplayName", "varChannelDisplayName", "string", ""),
    ("Initialize_SiteUrl", "varSiteUrl", "string", ""),
    ("Initialize_ListName", "varListName", "string", ""),
    ("Initialize_ListId", "varListId", "string", ""),
    ("Initialize_ListEntityType", "varListEntityType", "string", ""),
    ("Initialize_ListCreated", "varListCreated", "boolean", False),
    ("Initialize_CurrentFieldName", "varCurrentFieldName", "string", ""),
    ("Initialize_DefaultViewId", "varDefaultViewId", "string", ""),
    ("Initialize_ViewFieldsOk", "varViewFieldsOk", "boolean", False),
    # --- メンバー取得 ---
    ("Initialize_MemberSource", "varMemberSource", "string", ""),
    ("Initialize_MembersRaw", "varMembersRaw", "array", []),
    ("Initialize_MembersNormalized", "varMembersNormalized", "array", []),
    ("Initialize_MemberKeys", "varMemberKeys", "array", []),
    ("Initialize_MembersFetchComplete", "varMembersFetchComplete", "boolean", False),
    ("Initialize_MemberCount", "varMemberCount", "integer", 0),
    ("Initialize_MembersNextLink", "varMembersNextLink", "string", ""),
    ("Initialize_AllMembersFetched", "varAllMembersFetched", "boolean", False),
    ("Initialize_ResolvedEmail", "varResolvedEmail", "string", ""),
    ("Initialize_EmailLookupFailures", "varEmailLookupFailures", "integer", 0),
    # --- 既存アイテム ---
    ("Initialize_ExistingItems", "varExistingItems", "array", []),
    ("Initialize_ExistingFetchComplete", "varExistingFetchComplete", "boolean", False),
    ("Initialize_ExistingNextUri", "varExistingNextUri", "string", ""),
    ("Initialize_CurrentSyncKey", "varCurrentSyncKey", "string", ""),
    # --- 件数 ---
    ("Initialize_CreatedCount", "varCreatedCount", "integer", 0),
    ("Initialize_UpdatedCount", "varUpdatedCount", "integer", 0),
    ("Initialize_UnchangedCount", "varUnchangedCount", "integer", 0),
    ("Initialize_DeactivatedCount", "varDeactivatedCount", "integer", 0),
    ("Initialize_ErrorCount", "varErrorCount", "integer", 0),
]

# 設定ごとにリセットする変数（フローBが設定ループの先頭で使う）。
# 制御用の varIsValid と管理サイト系はループ内でリセットしない／するを個別に決める。
RESET_ON_EACH_CONFIG = [
    ("varIsValid", True), ("varStage", "PerConfig"), ("varFailedStage", ""),
    ("varErrorCode", ""), ("varErrorMessage", ""), ("varLastStatusCode", "0"),
    ("varLastErrorBody", ""), ("varItemErrors", "@json('[]')"),
    ("varChannelType", ""), ("varChannelDisplayName", ""),
    ("varListId", ""), ("varListEntityType", ""),
    ("varListCreated", False), ("varCurrentFieldName", ""),
    ("varDefaultViewId", ""), ("varViewFieldsOk", False),
    ("varMemberSource", ""), ("varMembersRaw", "@json('[]')"),
    ("varMembersNormalized", "@json('[]')"), ("varMemberKeys", "@json('[]')"),
    ("varMembersFetchComplete", False), ("varMemberCount", 0),
    ("varMembersNextLink", ""), ("varAllMembersFetched", False),
    ("varResolvedEmail", ""), ("varEmailLookupFailures", 0),
    ("varExistingItems", "@json('[]')"), ("varExistingFetchComplete", False),
    ("varExistingNextUri", ""), ("varCurrentSyncKey", ""),
    ("varCreatedCount", 0), ("varUpdatedCount", 0), ("varUnchangedCount", 0),
    ("varDeactivatedCount", 0), ("varErrorCount", 0),
]


def build_reset_sequence(suffix):
    """設定ごとの変数リセット。初期化用と区別できるよう名前に suffix を付ける
    （アクション名はフロー全体で一意であることが要求されるため）。"""
    seq = []
    for i, (vname, value) in enumerate(RESET_ON_EACH_CONFIG):
        seq.append(("Reset_%02d_%s%s" % (i + 1, vname[3:], suffix), setvar(vname, value)))
    return seq


# =========================================================================
# Scope 04: Teams チャネルへのアクセス確認とチャネル種別の判定
# =========================================================================
CHANNEL_INFO_URI = ("@concat('" + GRAPH_ROOT + "/teams/', variables('varTeamId'),"
                    " '/channels/', uriComponent(variables('varChannelId')),"
                    " '?$select=id,displayName,membershipType')")

_teams_ok, _ = chain([
    ("Set_Channel_Type", setvar(
        "varChannelType",
        "@toLower(trim(string(coalesce(body('Get_Channel_Info')?['membershipType'], 'standard'))))")),
    ("Set_Channel_Display_Name", setvar(
        "varChannelDisplayName",
        "@trim(string(coalesce(body('Get_Channel_Info')?['displayName'], '')))")),
])

_teams_ng, _ = chain([
    ("Set_Teams_Access_Invalid", setvar("varIsValid", False)),
    ("Set_Teams_Access_FailedStage", setvar("varFailedStage", "04_CheckTeamsAccess")),
    ("Set_Teams_Access_ErrorCode", setvar("varErrorCode", "ERR_TEAMS_CHANNEL_ACCESS")),
    ("Set_Teams_Access_ErrorMessage", setvar(
        "varErrorMessage",
        "Teamsチャネルの情報を取得できません。チームID・チャネルIDが正しいこと、"
        "接続したアカウントがそのチャネルのメンバーであることを確認してください。"
        "共有チャネルの場合はホストチーム（共有元のチーム）のIDを指定してください。")),
])


def build_check_teams_access(runafter=None):
    inner = {}
    inner["Set_Stage_CheckTeamsAccess"] = setvar("varStage", "04_CheckTeamsAccess")
    inner["Condition_Can_Check_Teams"] = cond(is_valid(), {
        "Get_Channel_Info": graph(CHANNEL_INFO_URI),
        "Set_Channel_Status_Code": setvar(
            "varLastStatusCode",
            "@string(coalesce(outputs('Get_Channel_Info')?['statusCode'], 0))",
            {"Get_Channel_Info": ["Succeeded", "Failed"]}),
        "Set_Channel_Error_Body": setvar(
            "varLastErrorBody", "@take(string(coalesce(body('Get_Channel_Info'), '')), 1000)",
            {"Get_Channel_Info": ["Failed", "TimedOut"]}),
        "Condition_Channel_Info_Ok": cond(
            {"and": [{"greater": ["@length(trim(string(coalesce("
                                  "body('Get_Channel_Info')?['id'], ''))))", 0]}]},
            _teams_ok, _teams_ng,
            {"Set_Channel_Status_Code": ["Succeeded", "Skipped"],
             "Set_Channel_Error_Body": ["Succeeded", "Skipped"]}),
    }, runafter=ra("Set_Stage_CheckTeamsAccess"))
    return scope(inner, runafter)


# =========================================================================
# Scope 05: リストの ensure（冪等・非破壊）
#   1. リスト一覧を取得して表示名の完全一致で探す
#   2. 無ければ **もう一度** 一覧を取り直して確認してから作成する（競合で他実行が
#      先に作っていたらそれを使う。既存を削除・再作成することはしない）
#   3. ListItemEntityTypeFullName を取得する
#   4. 列を列挙し、**不足している列だけ** createFieldAsXml で追加する
#      （既存列は表示名も型も一切変更しない）
#   破壊的 REST（deleteObject / recycle / DELETE）は1件も生成しない。
# =========================================================================
def build_ensure_list(sfx, dataset, listname_value, listid_var, entity_var, fields,
                      allow_create=True, ensure_fields=True, runafter=None):
    """sfx はアクション名の接尾辞（同一フローで2つのリストを ensure するため）。
    listname_value は '@' を付けない WDL 部分式（例 "variables('varListName')" /
    "'Teamsチャネルメンバー同期設定'"）。"""
    s = sfx
    matched = "body('Filter_Matching_Lists_%s')" % s
    first_match = "first(body('Filter_Matching_Lists_%s'))" % s
    recheck = "body('Filter_Recheck_Lists_%s')" % s
    first_recheck = "first(body('Filter_Recheck_Lists_%s'))" % s
    after = "body('Filter_Lists_After_Create_%s')" % s
    first_after = "first(body('Filter_Lists_After_Create_%s'))" % s

    # 表示名の完全一致（contains は使わない＝部分一致による誤検出を排除する）
    where_title = ("@equals(toLower(trim(coalesce(item()?['Title'], ''))),"
                   " toLower(trim(%s)))" % listname_value)

    # --- 既存が見つかった ---
    found_inner, _ = chain([
        ("Set_ListId_Existing_%s" % s,
         setvar(listid_var, "@trim(string(coalesce(%s?['Id'], '')))" % first_match)),
    ])

    # --- 作成する ---
    create_body = {
        "__metadata": {"type": "SP.List"},
        "AllowContentTypes": False,
        "BaseTemplate": 100,
        "ContentTypesEnabled": False,
        "Description": "Power Automate の Teams チャネルメンバー同期が使用するリスト",
        "Title": "@trim(%s)" % listname_value,
    }
    create_do, _ = chain([
        ("Compose_Create_List_Body_%s" % s, compose(create_body)),
        ("Create_List_%s" % s, http("POST", "_api/web/lists", H_VERBOSE,
                                    "@string(outputs('Compose_Create_List_Body_%s'))" % s,
                                    dataset=dataset)),
    ])
    # 作成の成否に関わらず取り直す（半冪等。作成失敗でも既存があれば継続する）
    create_do["Set_Create_Status_%s" % s] = setvar(
        "varLastStatusCode", "@string(coalesce(outputs('Create_List_%s')?['statusCode'], 0))" % s,
        {"Create_List_%s" % s: ["Succeeded", "Failed"]})
    create_do["Get_Lists_After_Create_%s" % s] = http(
        "GET", LISTS_SELECT, H_NOMETA, dataset=dataset,
        runafter={"Set_Create_Status_%s" % s: ["Succeeded"]})
    create_do["Filter_Lists_After_Create_%s" % s] = query(
        "@coalesce(body('Get_Lists_After_Create_%s')?['value'], json('[]'))" % s, where_title,
        ra("Get_Lists_After_Create_%s" % s))
    created_ok, _ = chain([
        ("Set_ListId_After_Create_%s" % s,
         setvar(listid_var, "@trim(string(coalesce(%s?['Id'], '')))" % first_after)),
        ("Set_List_Created_%s" % s, setvar("varListCreated", True)),
    ])
    created_ng, _ = chain([
        ("Set_Create_List_Invalid_%s" % s, setvar("varIsValid", False)),
        ("Set_Create_List_FailedStage_%s" % s, setvar("varFailedStage", "05_EnsureList_%s" % s)),
        ("Set_Create_List_ErrorCode_%s" % s, setvar("varErrorCode", "ERR_LIST_CREATE_FAILED")),
        ("Set_Create_List_ErrorMessage_%s" % s, setvar(
            "varErrorMessage",
            "対象リストを作成できませんでした。サイトURLと、接続したアカウントの"
            "リスト作成権限を確認してください。")),
    ])
    create_do["Condition_Created_%s" % s] = cond(
        {"and": [{"greater": ["@length(%s)" % after, 0]}]}, created_ok, created_ng,
        ra("Filter_Lists_After_Create_%s" % s))

    # --- 作成直前の再確認（競合で先に作られていたらそれを使う） ---
    race_inner, _ = chain([
        ("Set_ListId_Race_%s" % s,
         setvar(listid_var, "@trim(string(coalesce(%s?['Id'], '')))" % first_recheck)),
    ])
    recheck_inner = {}
    recheck_inner["Recheck_Lists_%s" % s] = http("GET", LISTS_SELECT, H_NOMETA, dataset=dataset)
    recheck_inner["Filter_Recheck_Lists_%s" % s] = query(
        "@coalesce(body('Recheck_Lists_%s')?['value'], json('[]'))" % s, where_title,
        ra("Recheck_Lists_%s" % s))
    recheck_inner["Condition_Recheck_Found_%s" % s] = cond(
        {"and": [{"greater": ["@length(%s)" % recheck, 0]}]}, race_inner, create_do,
        ra("Filter_Recheck_Lists_%s" % s))

    # --- 見つからない・作成しない場合 ---
    absent_inner, _ = chain([
        ("Set_List_Absent_Invalid_%s" % s, setvar("varIsValid", False)),
        ("Set_List_Absent_FailedStage_%s" % s, setvar("varFailedStage", "05_EnsureList_%s" % s)),
        ("Set_List_Absent_ErrorCode_%s" % s, setvar("varErrorCode", "ERR_LIST_NOT_FOUND")),
        ("Set_List_Absent_ErrorMessage_%s" % s, setvar(
            "varErrorMessage",
            "対象のリストが見つかりません。初期設定・テストフローを先に実行してください。")),
    ])

    inner = {}
    inner["Get_All_Lists_%s" % s] = http("GET", LISTS_SELECT, H_NOMETA, dataset=dataset)
    inner["Set_Lists_Status_%s" % s] = setvar(
        "varLastStatusCode", "@string(coalesce(outputs('Get_All_Lists_%s')?['statusCode'], 0))" % s,
        {"Get_All_Lists_%s" % s: ["Succeeded", "Failed"]})
    inner["Set_Lists_Error_Body_%s" % s] = setvar(
        "varLastErrorBody", "@take(string(coalesce(body('Get_All_Lists_%s'), '')), 1000)" % s,
        {"Get_All_Lists_%s" % s: ["Failed", "TimedOut"]})
    inner["Filter_Matching_Lists_%s" % s] = query(
        "@coalesce(body('Get_All_Lists_%s')?['value'], json('[]'))" % s, where_title,
        {"Set_Lists_Status_%s" % s: ["Succeeded", "Skipped"],
         "Set_Lists_Error_Body_%s" % s: ["Succeeded", "Skipped"]})
    inner["Condition_List_Found_%s" % s] = cond(
        {"and": [{"greater": ["@length(%s)" % matched, 0]}]}, found_inner,
        recheck_inner if allow_create else absent_inner,
        ra("Filter_Matching_Lists_%s" % s))

    # --- 型名の取得と列の ensure ---
    field_inner = {}
    field_inner["Set_Current_Field_Name_%s" % s] = setvar(
        "varCurrentFieldName",
        "@trim(string(coalesce(items('Foreach_Required_Field_%s')?['internal'], '')))" % s)
    field_inner["Filter_Existing_Field_%s" % s] = query(
        "@coalesce(body('Get_Fields_%s')?['value'], json('[]'))" % s,
        "@equals(trim(string(coalesce(item()?['InternalName'], ''))), variables('varCurrentFieldName'))",
        ra("Set_Current_Field_Name_%s" % s))
    create_field, _ = chain([
        ("Compose_Field_Body_%s" % s, compose({
            "parameters": {"__metadata": {"type": "SP.XmlSchemaFieldCreationInformation"},
                           "Options": 0,
                           "SchemaXml": "@items('Foreach_Required_Field_%s')?['xml']" % s}})),
        ("Create_Field_%s" % s, http("POST", list_uri(listid_var, "/fields/createFieldAsXml"),
                                     H_VERBOSE,
                                     "@string(outputs('Compose_Field_Body_%s'))" % s,
                                     dataset=dataset)),
        # 表示名だけを日本語に変える。**今この実行で作成した列に対してだけ**行うため、
        # 既存列の表示名は変わらない。
        ("Compose_Rename_Body_%s" % s, compose({
            "Title": "@items('Foreach_Required_Field_%s')?['display']" % s})),
        ("Rename_Field_%s" % s, http("POST", field_uri(listid_var, "varCurrentFieldName"),
                                     H_MERGE_N,
                                     "@string(outputs('Compose_Rename_Body_%s'))" % s,
                                     dataset=dataset)),
    ])
    create_field["Append_Field_Error_%s" % s] = append(
        "varItemErrors",
        {"stage": "05_EnsureList_%s" % s, "code": "ERR_FIELD_CREATE_FAILED",
         "field": "@variables('varCurrentFieldName')"},
        {"Create_Field_%s" % s: ["Failed", "TimedOut"]})
    create_field["Increment_Field_Error_%s" % s] = incr(
        "varErrorCount", {"Append_Field_Error_%s" % s: ["Succeeded"]})
    # 表示名の変更は見た目だけの処理。失敗しても列は使えるので同期は止めない。
    create_field["Append_Rename_Error_%s" % s] = append(
        "varItemErrors",
        {"stage": "05_EnsureList_%s" % s, "code": "WARN_FIELD_RENAME_FAILED",
         "field": "@variables('varCurrentFieldName')"},
        {"Rename_Field_%s" % s: ["Failed", "TimedOut"]})
    field_inner["Condition_Field_Missing_%s" % s] = cond(
        {"and": [eq("@length(body('Filter_Existing_Field_%s'))" % s, 0)]}, create_field,
        runafter=ra("Filter_Existing_Field_%s" % s))

    schema_seq = [
        ("Get_List_Info_%s" % s, http("GET", list_uri(listid_var, LIST_INFO_SELECT), H_NOMETA,
                                      dataset=dataset)),
        ("Set_List_EntityType_%s" % s, setvar(
            entity_var,
            "@trim(string(coalesce(body('Get_List_Info_%s')?['ListItemEntityTypeFullName'], '')))"
            % s)),
    ]
    # --- 既定ビューへ列を出す（不足分の追加だけ。既存ビューの列は消さない） ---
    # 【安全側の設計】removeAllViewFields（ビューの作り直し）は定義に一切含めない。
    # 追加（AddViewField）しかしないので、利用者が並べ替えた既存ビューを壊さない。
    # ビューが取れなかった場合は varViewFieldsOk が false のままになり、
    # 追加対象が0件になってループごとスキップされる。
    view_field_inner = {}
    view_field_inner["Set_Current_View_Field_%s" % s] = setvar(
        "varCurrentFieldName",
        "@trim(string(coalesce(items('Foreach_View_Field_%s')?['internal'], '')))" % s)
    view_field_inner["Add_View_Field_%s" % s] = http(
        "POST", add_view_field_uri(listid_var, "varDefaultViewId", "varCurrentFieldName"),
        H_MERGE_V, "@string(outputs('Compose_View_Field_Body_%s'))" % s,
        dataset=dataset, runafter=ra("Set_Current_View_Field_%s" % s))
    view_field_inner["Append_View_Field_Error_%s" % s] = append(
        "varItemErrors",
        {"stage": "05_EnsureList_%s" % s, "code": "WARN_VIEW_FIELD_ADD_FAILED",
         "field": "@variables('varCurrentFieldName')"},
        {"Add_View_Field_%s" % s: ["Failed", "TimedOut"]})

    view_seq = [
        ("Get_List_Views_%s" % s, http(
            "GET", list_uri(listid_var, "/views?$select=Id,Title,DefaultView&$top=100"),
            H_NOMETA, dataset=dataset)),
        ("Filter_Default_View_%s" % s, query(
            "@coalesce(body('Get_List_Views_%s')?['value'], json('[]'))" % s,
            "@equals(coalesce(item()?['DefaultView'], false), true)")),
        # 既定ビューは表示名ではなく DefaultView プロパティで特定する
        ("Set_Default_View_Id_%s" % s, setvar(
            "varDefaultViewId",
            "@trim(string(coalesce(first(body('Filter_Default_View_%s'))?['Id'], '')))" % s)),
        ("Get_View_Fields_%s" % s, http(
            "GET", view_uri(listid_var, "varDefaultViewId", "/ViewFields"),
            H_NOMETA, dataset=dataset)),
    ]
    view_inner, view_last = chain(view_seq)
    view_inner["Set_View_Fields_Ok_%s" % s] = setvar(
        "varViewFieldsOk", True, {"Get_View_Fields_%s" % s: ["Succeeded"]})
    view_inner["Set_View_Fields_Ng_%s" % s] = setvar(
        "varViewFieldsOk", False, {"Get_View_Fields_%s" % s: ["Failed", "TimedOut"]})
    # ビューの取得に失敗したら追加対象を0件にする（既定ビューを壊さないための保険）
    view_inner["Filter_Missing_View_Fields_%s" % s] = query(
        "@outputs('Compose_Required_Fields_%s')" % s,
        "@and(equals(variables('varViewFieldsOk'), true),"
        " not(contains(coalesce(body('Get_View_Fields_%s')?['Items'], json('[]')),"
        " item()?['internal'])))" % s,
        {"Set_View_Fields_Ok_%s" % s: ["Succeeded", "Skipped"],
         "Set_View_Fields_Ng_%s" % s: ["Succeeded", "Skipped"]})
    view_inner["Compose_View_Field_Body_%s" % s] = compose(
        {"__metadata": {"type": "SP.View"}, "SetAsDefaultView": True},
        ra("Filter_Missing_View_Fields_%s" % s))
    view_inner["Foreach_View_Field_%s" % s] = foreach(
        "@body('Filter_Missing_View_Fields_%s')" % s, view_field_inner,
        ra("Compose_View_Field_Body_%s" % s))

    if ensure_fields:
        schema_seq += [
            ("Get_Fields_%s" % s, http("GET", list_uri(listid_var, FIELDS_SELECT), H_NOMETA,
                                       dataset=dataset)),
            ("Compose_Required_Fields_%s" % s, compose(fields)),
            ("Foreach_Required_Field_%s" % s,
             foreach("@outputs('Compose_Required_Fields_%s')" % s, field_inner)),
        ]
    schema_inner, schema_last = chain(schema_seq)
    if ensure_fields:
        # ビュー整備は列整備の後（列が無いとビューにも出せない）
        for name, act in view_inner.items():
            schema_inner[name] = act
        schema_inner["Get_List_Views_%s" % s]["runAfter"] = ra(schema_last)
    inner["Condition_Has_ListId_%s" % s] = cond(
        {"and": [{"greater": ["@length(variables('%s'))" % listid_var, 0]}]}, schema_inner,
        runafter=ra("Condition_List_Found_%s" % s))

    outer = {}
    outer["Set_Stage_EnsureList_%s" % s] = setvar("varStage", "05_EnsureList_%s" % s)
    outer["Condition_Can_Ensure_%s" % s] = cond(is_valid(), inner,
                                                runafter=ra("Set_Stage_EnsureList_%s" % s))
    return scope(outer, runafter)


# =========================================================================
# Scope 06: メンバー取得
#
#  主経路 : Teams コネクタ ListMembers（threadType=channel）
#  代替経路: Teams コネクタ HttpRequest 経由の Graph
#            GET /teams/{teamId}/channels/{channelId}/members（@odata.nextLink を追跡）
#  共有チャネルのときだけ /allMembers も取得して合流する。
#  ListMembers も Graph も同じプロパティ名（displayName / email / id / roles /
#  tenantId / userId）を返すため、正規化処理は共通で足りる。
# =========================================================================
MEMBERS_URI = ("@concat('" + GRAPH_ROOT + "/teams/', variables('varTeamId'),"
               " '/channels/', uriComponent(variables('varChannelId')), '/members?$top=999')")
ALLMEMBERS_URI = ("@concat('" + GRAPH_ROOT + "/teams/', variables('varTeamId'),"
                  " '/channels/', uriComponent(variables('varChannelId')), '/allMembers')")


def _paging_block(name, first_uri, marker_action, marker):
    """Graph のページング（Do until で @odata.nextLink を追跡）。
    marker_action / marker は「どの経路で取得したか」を残す1アクション。
    varMemberSource を2回書き換えて経路の痕跡を消さないよう、経路ごとに別の変数へ記録する。"""
    page_inner = {}
    page_inner["Get_%s_Page" % name] = graph("@variables('varMembersNextLink')")
    page_inner["Set_%s_Status" % name] = setvar(
        "varLastStatusCode", "@string(coalesce(outputs('Get_%s_Page')?['statusCode'], 0))" % name,
        {"Get_%s_Page" % name: ["Succeeded", "Failed"]})
    # ページ配列をそのまま Append すると入れ子配列になるため、必ず1件ずつ追加する
    page_inner["Foreach_Append_%s" % name] = foreach(
        "@coalesce(body('Get_%s_Page')?['value'], json('[]'))" % name,
        {"Append_Raw_%s" % name: append("varMembersRaw", "@item()")},
        {"Get_%s_Page" % name: ["Succeeded"]})
    page_inner["Set_%s_NextLink" % name] = setvar(
        "varMembersNextLink",
        "@trim(string(coalesce(body('Get_%s_Page')?['@odata.nextLink'], '')))" % name,
        ra("Foreach_Append_%s" % name))

    block, _ = chain([
        (marker_action, marker),
        ("Set_%s_NextLink_First" % name, setvar("varMembersNextLink", first_uri)),
    ])
    block["Do_Until_%s_Paging" % name] = until(
        "@empty(variables('varMembersNextLink'))", page_inner,
        ra("Set_%s_NextLink_First" % name))
    return block


def build_get_members(runafter=None):
    inner = {}

    # --- 主経路: ListMembers コネクタ ---
    connector_ok = {}
    if MEMBER_SOURCE_MODE == "connector_first":
        connector_ok["Teams_List_Channel_Members"] = oac(HOST_TEAMS, "ListMembers", {
            "threadType": LISTMEMBERS_THREAD_TYPE,
            LISTMEMBERS_KEY_TEAM: "@variables('varTeamId')",
            LISTMEMBERS_KEY_CHANNEL: "@variables('varChannelId')",
        })
        connector_ok["Set_Connector_Source"] = setvar(
            "varMemberSource", "connector", {"Teams_List_Channel_Members": ["Succeeded"]})
        connector_ok["Foreach_Append_Connector_Member"] = foreach(
            "@coalesce(body('Teams_List_Channel_Members')?['value'], json('[]'))",
            {"Append_Raw_Connector_Member": append("varMembersRaw", "@item()")},
            ra("Set_Connector_Source"))
        # ListMembers が失敗した場合だけ Graph へ切り替える。
        # ListMembers はページング（x-ms-pageable）を持たないため、大規模チャネルでの
        # 取りこぼしが疑われる場合も Graph 経路（nextLink 追跡）へ切り替えられる。
        fallback = _paging_block("Graph_Members", MEMBERS_URI, "Set_Graph_Members_Source",
                                 setvar("varMemberSource", "graph"))
        for k, v in fallback.items():
            connector_ok[k] = v
        connector_ok["Set_Graph_Members_Source"]["runAfter"] = {
            "Teams_List_Channel_Members": ["Failed", "Skipped", "TimedOut"]}
        gate_after = {"Foreach_Append_Connector_Member": ["Succeeded", "Skipped"],
                      "Do_Until_Graph_Members_Paging": ["Succeeded", "Skipped"]}
    else:
        connector_ok = _paging_block("Graph_Members", MEMBERS_URI, "Set_Graph_Members_Source",
                                     setvar("varMemberSource", "graph"))
        gate_after = {"Do_Until_Graph_Members_Paging": ["Succeeded"]}

    # --- 共有チャネルの間接メンバー補完 ---
    # 【公式】/members は共有チャネルでも「直接メンバー」しか返さない。
    # 共有先チーム経由の間接メンバーを含めるには /allMembers を使う
    # （learn.microsoft.com/graph/api/channel-list-allmembers）。
    # /allMembers は $top 非対応・既定ページサイズの公式記載なしのため、
    # 返ってきた nextLink があれば追跡する（同じ Do until を使う）。
    shared_block = _paging_block("Graph_AllMembers", ALLMEMBERS_URI,
                                 "Set_AllMembers_Fetched", setvar("varAllMembersFetched", True))
    connector_ok["Condition_Shared_Channel"] = cond(
        {"and": [eq("@variables('varChannelType')", "shared")]}, shared_block,
        runafter=gate_after)

    connector_ok["Set_Members_Fetch_Complete"] = setvar(
        "varMembersFetchComplete", True, ra("Condition_Shared_Channel"))

    inner["Set_Stage_GetMembers"] = setvar("varStage", "06_GetMembers")
    inner["Condition_Can_Get_Members"] = cond(is_valid(), connector_ok,
                                              runafter=ra("Set_Stage_GetMembers"))
    return scope(inner, runafter)


# =========================================================================
# Scope 07: メンバー情報の正規化
#   - 同期キーは userId（Entra オブジェクトID）。無ければメンバーシップ id。
#     ID の内部構造は分解しない（公式にも opaque と明記されている）。
#   - メールは email → 空なら Graph /users/{userId} の mail → userPrincipalName の順で補完。
#     取得できなければ空のまま。**推測でメールを生成しない**。失敗しても同期は止めない。
#   - 直接／間接は @microsoft.graph.originalSourceMembershipUrl の有無で判定する。
#   - 外部ユーザーは URL 由来のテナントIDと突き合わせる。テナントIDが不明なときは
#     「同一テナント」と決めつけず、判定しない（false のまま）。
# =========================================================================
IT = "items('Foreach_Raw_Member')"

NORMALIZED_MEMBER = {
    "syncKey": "@variables('varCurrentSyncKey')",
    "fullName": "@outputs('Compose_Member_Full_Name')",
    "lastName": "@outputs('Compose_Member_Last_Name')",
    "firstName": "@outputs('Compose_Member_First_Name')",
    "email": "@variables('varResolvedEmail')",
    "userId": "@outputs('Compose_Member_UserId')",
    "membershipId": "@outputs('Compose_Member_MembershipId')",
    "tenantId": "@outputs('Compose_Member_TenantId')",
    "roles": "@outputs('Compose_Member_Roles')",
    "membershipKind": "@outputs('Compose_Member_Kind')",
    "isExternal": "@outputs('Compose_Member_IsExternal')",
}

USER_LOOKUP_URI = ("@concat('" + GRAPH_ROOT + "/users/', uriComponent(variables('varCurrentSyncKey')),"
                   " '?$select=mail,userPrincipalName')")

# 取得できなかったときに元の値へ戻れるよう、必ず coalesce で受ける。
GRAPH_MAIL = ("@trim(string(coalesce(body('Get_User_Profile')?['mail'],"
              " body('Get_User_Profile')?['userPrincipalName'], '')))")


def build_normalize_members(runafter=None):
    email_lookup = {}
    email_lookup["Get_User_Profile"] = graph(USER_LOOKUP_URI)
    email_lookup["Set_Resolved_Email_From_Graph"] = setvar(
        "varResolvedEmail", GRAPH_MAIL, {"Get_User_Profile": ["Succeeded"]})
    # 補完に失敗しても1件も止めない（ゲスト・外部ユーザーでは 404 になりうる）
    email_lookup["Increment_Email_Lookup_Failure"] = incr(
        "varEmailLookupFailures", {"Get_User_Profile": ["Failed", "TimedOut"]})

    # 氏名の整形。Teams の表示名には外字の代替表記や英字読みが混ざる。
    #   例: '▲高▼元 優子(TAKAMOTO Yuko)' → 氏名 '高元 優子' / 姓 '高元' / 名 '優子'
    #   1. 外字マーカー ▲ ▼ を除去する
    #   2. 括弧（半角・全角）以降を落とす（英字読みなどの併記を除く）
    #   3. 全角スペースを半角に寄せて trim する → これを氏名とする
    #   4. 最初のスペースの前を姓、後ろを名にする
    # 名の切り出しは substring を使うため、開始位置を先に安全な値へ確定させたうえで
    # 番兵付き（safe_substring）にする。スペースが無い場合は開始位置＝全長となり、
    # 名は空文字になる（姓だけが入る）。
    FULL = "outputs('Compose_Member_Full_Name')"
    POS = "outputs('Compose_Member_First_Name_Pos')"

    new_member, _ = chain([
        ("Compose_Member_Name_Raw",
         compose("@trim(string(coalesce(%s?['displayName'], '')))" % IT)),
        ("Compose_Member_Name_NoMarks", compose(
            "@replace(replace(outputs('Compose_Member_Name_Raw'), '▲', ''), '▼', '')")),
        ("Compose_Member_Name_NoParen", compose(
            "@trim(first(split(first(split(outputs('Compose_Member_Name_NoMarks'), '(')), '（')))")),
        ("Compose_Member_Full_Name", compose(
            "@trim(replace(outputs('Compose_Member_Name_NoParen'), '　', ' '))")),
        ("Compose_Member_Last_Name", compose("@trim(first(split(%s, ' ')))" % FULL)),
        ("Compose_Member_First_Name_Pos", compose(
            "@if(contains(%(F)s, ' '), add(length(first(split(%(F)s, ' '))), 1), length(%(F)s))"
            % {"F": FULL})),
        ("Compose_Member_First_Name", compose(
            "@trim(%s)" % safe_substring(FULL, POS, "sub(length(%s), %s)" % (FULL, POS)))),
        ("Compose_Member_UserId", compose("@outputs('Compose_Raw_UserId')")),
        ("Compose_Member_MembershipId", compose("@outputs('Compose_Raw_MembershipId')")),
        ("Compose_Member_TenantId", compose("@trim(string(coalesce(%s?['tenantId'], '')))" % IT)),
        ("Compose_Member_Roles",
         compose("@trim(join(coalesce(%s?['roles'], json('[]')), ','))" % IT)),
        # 間接メンバーの印。'@' はシングルクォート内の文字列リテラルなので式として安全。
        ("Compose_Member_Kind", compose(
            "@if(empty(trim(string(coalesce("
            "%s?['@microsoft.graph.originalSourceMembershipUrl'], '')))), 'direct', 'indirect')"
            % IT)),
        ("Compose_Member_IsExternal", compose(
            "@and(not(empty(variables('varTenantId'))),"
            " not(empty(outputs('Compose_Member_TenantId'))),"
            " not(equals(toLower(outputs('Compose_Member_TenantId')),"
            " toLower(variables('varTenantId')))))")),
        ("Compose_Member_Email_Raw", compose("@trim(string(coalesce(%s?['email'], '')))" % IT)),
        ("Set_Resolved_Email_First", setvar("varResolvedEmail",
                                            "@outputs('Compose_Member_Email_Raw')")),
    ])
    new_member["Condition_Email_Empty"] = cond(
        {"and": [eq("@empty(variables('varResolvedEmail'))", True),
                 eq("@empty(outputs('Compose_Member_UserId'))", False)]},
        email_lookup, runafter=ra("Set_Resolved_Email_First"))
    tail, _ = chain([
        ("Append_Member_Key", append("varMemberKeys", "@variables('varCurrentSyncKey')")),
        ("Compose_Normalized_Member", compose(NORMALIZED_MEMBER)),
        ("Append_Normalized_Member",
         append("varMembersNormalized", "@outputs('Compose_Normalized_Member')")),
    ], ra("Condition_Email_Empty"))
    new_member.update(tail)

    loop_inner = {}
    loop_inner["Compose_Raw_UserId"] = compose(
        "@trim(string(coalesce(%s?['userId'], '')))" % IT)
    loop_inner["Compose_Raw_MembershipId"] = compose(
        "@trim(string(coalesce(%s?['id'], '')))" % IT)
    # coalesce は null だけを読み飛ばす。userId が「空文字で存在する」メンバーもいるため、
    # coalesce(userId, id) では空文字が採用されてしまい、その利用者が同期から
    # 黙って落ちる。空判定を明示して membershipId へ倒す。
    loop_inner["Set_Current_Sync_Key"] = setvar(
        "varCurrentSyncKey",
        "@if(empty(outputs('Compose_Raw_UserId')), outputs('Compose_Raw_MembershipId'),"
        " outputs('Compose_Raw_UserId'))",
        ra("Compose_Raw_MembershipId"))
    loop_inner["Compose_Raw_MembershipId"]["runAfter"] = ra("Compose_Raw_UserId")
    # 直接メンバーと間接メンバーで同じ利用者が二重に現れうるため、同期キーで重複を排除する
    loop_inner["Filter_Seen_Member_Key"] = query(
        "@variables('varMemberKeys')", "@equals(item(), variables('varCurrentSyncKey'))",
        ra("Set_Current_Sync_Key"))
    loop_inner["Condition_New_Member"] = cond(
        {"and": [eq("@length(body('Filter_Seen_Member_Key'))", 0),
                 eq("@empty(variables('varCurrentSyncKey'))", False)]},
        new_member, runafter=ra("Filter_Seen_Member_Key"))

    body_inner, _ = chain([
        ("Foreach_Raw_Member", foreach("@variables('varMembersRaw')", loop_inner)),
        ("Set_Member_Count", setvar("varMemberCount", "@length(variables('varMembersNormalized'))")),
    ])

    inner = {}
    inner["Set_Stage_Normalize"] = setvar("varStage", "07_NormalizeMembers")
    inner["Condition_Can_Normalize"] = cond(is_valid(), body_inner,
                                            runafter=ra("Set_Stage_Normalize"))
    return scope(inner, runafter)


# =========================================================================
# Scope 08: 既存アイテムの取得（全件ページング → 対象だけ絞り込み）
#   同期対象は「このフローが作成した（SyncSource 一致）」かつ「同じチャネル」のアイテムだけ。
#   それ以外のアイテムには読み書きとも一切関与しない（要件§10）。
# =========================================================================
TARGET_EXISTING = "body('Filter_Target_Existing_Items')"


def build_get_existing_items(runafter=None):
    page_inner = {}
    page_inner["Get_Existing_Items_Page"] = http(
        "GET", "@variables('varExistingNextUri')", H_NOMETA)
    page_inner["Set_Existing_Page_Status"] = setvar(
        "varLastStatusCode",
        "@string(coalesce(outputs('Get_Existing_Items_Page')?['statusCode'], 0))",
        {"Get_Existing_Items_Page": ["Succeeded", "Failed"]})
    page_inner["Foreach_Append_Existing_Item"] = foreach(
        "@coalesce(body('Get_Existing_Items_Page')?['value'], json('[]'))",
        {"Append_Existing_Item": append("varExistingItems", "@item()")},
        {"Get_Existing_Items_Page": ["Succeeded"]})
    page_inner["Compose_Existing_Next_Raw"] = compose(
        next_link_of("Get_Existing_Items_Page"), ra("Foreach_Append_Existing_Item"))
    page_inner["Set_Existing_Next_Uri"] = setvar(
        "varExistingNextUri", relative_next("outputs('Compose_Existing_Next_Raw')"),
        ra("Compose_Existing_Next_Raw"))

    body_inner, _ = chain([
        ("Compose_Existing_First_Uri", compose(list_uri("varListId", ITEMS_SELECT))),
        ("Set_Existing_Next_Uri_First",
         setvar("varExistingNextUri", "@outputs('Compose_Existing_First_Uri')")),
    ])
    body_inner["Do_Until_Existing_Paging"] = until(
        "@empty(variables('varExistingNextUri'))", page_inner,
        ra("Set_Existing_Next_Uri_First"))
    body_inner["Set_Existing_Fetch_Complete"] = setvar(
        "varExistingFetchComplete", True, ra("Do_Until_Existing_Paging"))
    body_inner["Filter_Target_Existing_Items"] = query(
        "@variables('varExistingItems')",
        "@and(equals(trim(string(coalesce(item()?['ChannelId'], ''))), variables('varChannelId')),"
        " equals(trim(string(coalesce(item()?['SyncSource'], ''))), '%s'))" % SYNC_SOURCE,
        ra("Set_Existing_Fetch_Complete"))

    inner = {}
    inner["Set_Stage_GetExisting"] = setvar("varStage", "08_GetExistingItems")
    inner["Condition_Can_Get_Existing"] = cond(is_valid(), body_inner,
                                               runafter=ra("Set_Stage_GetExisting"))
    return scope(inner, runafter)


# =========================================================================
# Scope 09: 差分同期（新規作成 / 更新 / 変更なし）
#   0件 → 作成 / 1件 → 内容比較して必要なときだけ更新 / 2件以上 → 書き込まず記録
#   （handbook/knowledge/sharepoint_rest_list_provisioning.md §16 の3分岐）
# =========================================================================
MEMBER = "items('Foreach_Member')"
MATCH = "body('Filter_Match_Existing')"
FIRST_MATCH_ITEM = "first(body('Filter_Match_Existing'))"

ITEM_VALUES = {
    # 組み込みの Title には氏名を入れない。必須列を空にできないため同期キーを入れる。
    # 人が見る氏名・姓・名は専用列（FullName / LastName / FirstName）に持たせる。
    "Title": "@variables('varCurrentSyncKey')",
    "FullName": "@trim(string(coalesce(%s?['fullName'], '')))" % MEMBER,
    "LastName": "@trim(string(coalesce(%s?['lastName'], '')))" % MEMBER,
    "FirstName": "@trim(string(coalesce(%s?['firstName'], '')))" % MEMBER,
    "Email": "@trim(string(coalesce(%s?['email'], '')))" % MEMBER,
    "SyncKey": "@variables('varCurrentSyncKey')",
    "TeamsUserId": "@trim(string(coalesce(%s?['userId'], '')))" % MEMBER,
    "MembershipId": "@trim(string(coalesce(%s?['membershipId'], '')))" % MEMBER,
    "TeamId": "@variables('varTeamId')",
    "ChannelId": "@variables('varChannelId')",
    "MemberTenantId": "@trim(string(coalesce(%s?['tenantId'], '')))" % MEMBER,
    "MemberRoles": "@trim(string(coalesce(%s?['roles'], '')))" % MEMBER,
    "MembershipKind": "@trim(string(coalesce(%s?['membershipKind'], 'direct')))" % MEMBER,
    "IsExternalUser": "@coalesce(%s?['isExternal'], false)" % MEMBER,
    "MemberStatus": MEMBER_STATUS_ACTIVE,
    "IsActive": True,
    "LastSyncedAt": "@utcNow()",
    "SyncSource": SYNC_SOURCE,
}

# 変更検出。氏名・メール・ロール・メンバー種別・在籍状態のいずれかが違えば更新する。
# 何も変わっていなければ書き込まない（要件§10）。
NEEDS_UPDATE = (
    "@not(and("
    "equals(trim(string(coalesce({F}?['FullName'], ''))), trim(string(coalesce({M}?['fullName'], '')))),"
    " equals(trim(string(coalesce({F}?['LastName'], ''))), trim(string(coalesce({M}?['lastName'], '')))),"
    " equals(trim(string(coalesce({F}?['FirstName'], ''))), trim(string(coalesce({M}?['firstName'], '')))),"
    " equals(trim(string(coalesce({F}?['Email'], ''))), trim(string(coalesce({M}?['email'], '')))),"
    " equals(trim(string(coalesce({F}?['MemberRoles'], ''))), trim(string(coalesce({M}?['roles'], '')))),"
    " equals(trim(string(coalesce({F}?['MembershipKind'], ''))),"
    " trim(string(coalesce({M}?['membershipKind'], 'direct')))),"
    " equals(trim(string(coalesce({F}?['MemberStatus'], ''))), '{A}'),"
    " equals(coalesce({F}?['IsActive'], false), true)))"
).format(F=FIRST_MATCH_ITEM, M=MEMBER, A=MEMBER_STATUS_ACTIVE)


def build_sync_items(runafter=None):
    create_body = dict(ITEM_VALUES)
    create_body["__metadata"] = {"type": "@variables('varListEntityType')"}
    update_body = dict(ITEM_VALUES)
    update_body["__metadata"] = {"type": "@variables('varListEntityType')"}

    # --- 0件: 新規作成 ---
    create_inner, _ = chain([
        ("Compose_Create_Item_Body", compose(create_body)),
        ("Create_Member_Item", http("POST", list_uri("varListId", "/items"), H_VERBOSE,
                                    "@string(outputs('Compose_Create_Item_Body'))")),
    ])
    create_inner["Increment_Created_Count"] = incr(
        "varCreatedCount", {"Create_Member_Item": ["Succeeded"]})
    create_inner["Append_Create_Error"] = append(
        "varItemErrors", {"stage": "09_SyncItems", "code": "ERR_ITEM_CREATE_FAILED",
                          "syncKey": "@variables('varCurrentSyncKey')"},
        {"Create_Member_Item": ["Failed", "TimedOut"]})
    create_inner["Increment_Error_Count_Create"] = incr(
        "varErrorCount", {"Append_Create_Error": ["Succeeded"]})

    # --- 1件: 変更があれば更新 ---
    do_update, _ = chain([
        ("Compose_Update_Item_Body", compose(update_body)),
        ("Compose_Existing_Item_Id",
         compose("@string(coalesce(%s?['Id'], 0))" % FIRST_MATCH_ITEM)),
        ("Update_Member_Item", http("POST",
                                    item_uri("varListId", "outputs('Compose_Existing_Item_Id')"),
                                    H_MERGE_V,
                                    "@string(outputs('Compose_Update_Item_Body'))")),
    ])
    do_update["Increment_Updated_Count"] = incr(
        "varUpdatedCount", {"Update_Member_Item": ["Succeeded"]})
    do_update["Append_Update_Error"] = append(
        "varItemErrors", {"stage": "09_SyncItems", "code": "ERR_ITEM_UPDATE_FAILED",
                          "syncKey": "@variables('varCurrentSyncKey')"},
        {"Update_Member_Item": ["Failed", "TimedOut"]})
    do_update["Increment_Error_Count_Update"] = incr(
        "varErrorCount", {"Append_Update_Error": ["Succeeded"]})
    no_update = {"Increment_Unchanged_Count": incr("varUnchangedCount")}

    single_inner = {}
    single_inner["Compose_Needs_Update"] = compose(NEEDS_UPDATE)
    single_inner["Condition_Needs_Update"] = cond(
        {"and": [eq("@outputs('Compose_Needs_Update')", True)]}, do_update, no_update,
        ra("Compose_Needs_Update"))

    # --- 2件以上: 書き込まず記録する（どちらを正とすべきか判断できないため） ---
    dup_inner, _ = chain([
        ("Append_Duplicate_Error", append(
            "varItemErrors", {"stage": "09_SyncItems", "code": "ERR_DUPLICATE_ITEMS",
                              "syncKey": "@variables('varCurrentSyncKey')",
                              "count": "@length(%s)" % MATCH})),
        ("Increment_Error_Count_Duplicate", incr("varErrorCount")),
    ])

    loop_inner = {}
    loop_inner["Set_Current_Member_Key"] = setvar(
        "varCurrentSyncKey", "@trim(string(coalesce(%s?['syncKey'], '')))" % MEMBER)
    loop_inner["Filter_Match_Existing"] = query(
        "@%s" % TARGET_EXISTING,
        "@equals(trim(string(coalesce(item()?['SyncKey'], ''))), variables('varCurrentSyncKey'))",
        ra("Set_Current_Member_Key"))
    loop_inner["Condition_No_Match"] = cond(
        {"and": [eq("@length(%s)" % MATCH, 0)]}, create_inner,
        runafter=ra("Filter_Match_Existing"))
    loop_inner["Condition_Single_Match"] = cond(
        {"and": [eq("@length(%s)" % MATCH, 1)]}, single_inner,
        runafter={"Condition_No_Match": ["Succeeded", "Skipped"]})
    loop_inner["Condition_Duplicate_Match"] = cond(
        {"and": [{"greater": ["@length(%s)" % MATCH, 1]}]}, dup_inner,
        runafter={"Condition_Single_Match": ["Succeeded", "Skipped"]})

    body_inner = {"Foreach_Member": foreach("@variables('varMembersNormalized')", loop_inner)}

    inner = {}
    inner["Set_Stage_SyncItems"] = setvar("varStage", "09_SyncItems")
    inner["Condition_Can_Sync"] = cond(is_valid(), body_inner,
                                       runafter=ra("Set_Stage_SyncItems"))
    return scope(inner, runafter)


# =========================================================================
# Scope 10: チャネルから外れたメンバーの論理無効化
#
#   物理削除は行わない。同期状態を「離脱」・有効を false にするだけで、行は残す。
#   実行条件（すべて満たしたときだけ）:
#     - Teams からのメンバー取得が最後まで完了している
#     - 取得件数が 0 件でない（取得失敗で 0 件になった場合に全件無効化する事故を防ぐ）
#     - 既存アイテムの取得が最後まで完了している
#     - どの段階でも失敗を記録していない
#   対象は「このフローが作成した・同じチャネルの・在籍のままの」アイテムだけ。
# =========================================================================
CAN_DEACTIVATE = ("@and(equals(variables('varMembersFetchComplete'), true),"
                  " greater(variables('varMemberCount'), 0),"
                  " equals(variables('varExistingFetchComplete'), true),"
                  " equals(variables('varIsValid'), true),"
                  " empty(variables('varFailedStage')))")

LEFT_ITEM = "items('Foreach_Left_Member')"

DEACTIVATE_BODY = {
    "__metadata": {"type": "@variables('varListEntityType')"},
    "MemberStatus": MEMBER_STATUS_LEFT,
    "IsActive": False,
    "LastSyncedAt": "@utcNow()",
}


def build_deactivate_left(runafter=None):
    left_inner, _ = chain([
        ("Compose_Left_Item_Id", compose("@string(coalesce(%s?['Id'], 0))" % LEFT_ITEM)),
        ("Compose_Deactivate_Body", compose(DEACTIVATE_BODY)),
        ("Update_Left_Member_Item", http("POST",
                                         item_uri("varListId", "outputs('Compose_Left_Item_Id')"),
                                         H_MERGE_V,
                                         "@string(outputs('Compose_Deactivate_Body'))")),
    ])
    left_inner["Increment_Deactivated_Count"] = incr(
        "varDeactivatedCount", {"Update_Left_Member_Item": ["Succeeded"]})
    left_inner["Append_Deactivate_Error"] = append(
        "varItemErrors", {"stage": "10_DeactivateLeft", "code": "ERR_ITEM_DEACTIVATE_FAILED",
                          "itemId": "@outputs('Compose_Left_Item_Id')"},
        {"Update_Left_Member_Item": ["Failed", "TimedOut"]})
    left_inner["Increment_Error_Count_Deactivate"] = incr(
        "varErrorCount", {"Append_Deactivate_Error": ["Succeeded"]})

    guarded, _ = chain([
        ("Filter_Left_Members", query(
            "@%s" % TARGET_EXISTING,
            "@and(equals(trim(string(coalesce(item()?['MemberStatus'], ''))), '%s'),"
            " not(contains(variables('varMemberKeys'),"
            " trim(string(coalesce(item()?['SyncKey'], ''))))))" % MEMBER_STATUS_ACTIVE)),
        ("Foreach_Left_Member", foreach("@body('Filter_Left_Members')", left_inner)),
    ])

    inner = {}
    inner["Set_Stage_Deactivate"] = setvar("varStage", "10_DeactivateLeft")
    inner["Compose_Can_Deactivate"] = compose(CAN_DEACTIVATE, ra("Set_Stage_Deactivate"))
    inner["Condition_Can_Deactivate"] = cond(
        {"and": [eq("@outputs('Compose_Can_Deactivate')", True)]}, guarded,
        runafter=ra("Compose_Can_Deactivate"))
    return scope(inner, runafter)


# =========================================================================
# 実行結果のまとめ
#   氏名・メールアドレスはログへ複製しない（要件§12）。件数と識別子だけを残す。
# =========================================================================
def result_summary(run_kind):
    return {
        "runKind": run_kind,
        "runId": "@workflow()?['run']?['name']",
        "executedAt": "@utcNow()",
        "teamsChannelUrl": "@variables('varTeamsChannelUrl')",
        "teamId": "@variables('varTeamId')",
        "channelId": "@variables('varChannelId')",
        "tenantId": "@variables('varTenantId')",
        "channelType": "@variables('varChannelType')",
        "siteUrl": "@variables('varSiteUrl')",
        "listName": "@variables('varListName')",
        "listId": "@variables('varListId')",
        "memberSource": "@variables('varMemberSource')",
        "allMembersFetched": "@variables('varAllMembersFetched')",
        "memberCount": "@variables('varMemberCount')",
        "createdCount": "@variables('varCreatedCount')",
        "updatedCount": "@variables('varUpdatedCount')",
        "unchangedCount": "@variables('varUnchangedCount')",
        "deactivatedCount": "@variables('varDeactivatedCount')",
        "errorCount": "@variables('varErrorCount')",
        "emailLookupFailures": "@variables('varEmailLookupFailures')",
        "membersFetchComplete": "@variables('varMembersFetchComplete')",
        "failedStage": "@variables('varFailedStage')",
        "errorCode": "@variables('varErrorCode')",
        "errorMessage": "@variables('varErrorMessage')",
        "httpStatusCode": "@variables('varLastStatusCode')",
        "itemErrors": "@variables('varItemErrors')",
    }


# =========================================================================
# 共通ブロック一式（04〜10）を直列に連結して返す
# =========================================================================
def build_sync_scopes(first_runafter=None):
    """(actions_dict, last_action_name) を返す。呼び出し側はこれをそのまま自分の
    アクション辞書へ merge する。フローAはトップレベルへ、フローBは設定ループの中へ置く。"""
    out = {}
    prev = None
    for name, builder in [
        ("Scope_04_CheckTeamsAccess", build_check_teams_access),
        ("Scope_05_EnsureMemberList", lambda r: build_ensure_list(
            "Member", DS_TARGET, "variables('varListName')", "varListId", "varListEntityType",
            MEMBER_FIELDS, allow_create=True, runafter=r)),
        ("Scope_06_GetMembers", build_get_members),
        ("Scope_07_NormalizeMembers", build_normalize_members),
        ("Scope_08_GetExistingItems", build_get_existing_items),
        ("Scope_09_SyncItems", build_sync_items),
        ("Scope_10_DeactivateLeft", build_deactivate_left),
    ]:
        out[name] = builder(ra(prev) if prev else (first_runafter or {}))
        prev = name
    return out, prev
