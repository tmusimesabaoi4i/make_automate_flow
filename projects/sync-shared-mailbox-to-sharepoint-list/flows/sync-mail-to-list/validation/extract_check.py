# -*- coding: utf-8 -*-
"""
release/ の最新ZIPを再展開して、インポート可能な形になっているかを検査する。

  python extract_check.py            # 最新ZIPを検査
  python extract_check.py <zip>      # ZIPを指定して検査

検査項目:
  1. ZIPが破損なく開ける・全エントリを展開できる
  2. レガシーパッケージの5ファイル構造がZIPのルート直下から始まっている
     （余分な親フォルダを作っていない）
  3. __MACOSX / .DS_Store / ディレクトリエントリの混入が無い
  4. 全JSONが構文エラーなくパースできる
  5. パッケージGUIDの3点一致
  6. apisMap / connectionsMap の値が rootManifest.resources と dependsOn に実在する
  7. definition.json の connectionReferences のキーが apisMap/connectionsMap と一致する
  8. 展開結果が source/package/ の内容とバイト単位で一致する（ZIP化で壊れていない）
  9. 中身の実在確認（トリガー4入力 / 3コネクタ / 5列 / ビュー並び順）
  9b. 安全要件の再確認（GetByTitle 0件 / 破壊的REST 0件 / メール変更操作 0件 / 実値0件）

展開先は ./extracted/ （検証用の一時コピー。source/package が正典）。
終了コード: エラーがあれば 1、無ければ 0。
"""
import hashlib, json, os, re, shutil, sys, zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
FLOW_DIR = os.path.dirname(HERE)
RELEASE = os.path.join(FLOW_DIR, "release")
SOURCE_PKG = os.path.join(FLOW_DIR, "source", "package")
EXTRACT_TO = os.path.join(HERE, "extracted")

errors = []
notes = []

EXPECTED_TOP = {"manifest.json", "Microsoft.Flow/flows/manifest.json"}
FORBIDDEN_SUBSTR = ("__MACOSX", ".DS_Store", "Thumbs.db")
FIELD_ORDER = ["MessageId", "ReceivedDateTime", "SenderAddress", "Subject", "BodyPlainText"]


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def pick_zip():
    if len(sys.argv) > 1:
        return os.path.abspath(sys.argv[1])
    if not os.path.isdir(RELEASE):
        return None
    zips = sorted(f for f in os.listdir(RELEASE) if f.lower().endswith(".zip"))
    return os.path.join(RELEASE, zips[-1]) if zips else None


zip_path = pick_zip()
if not zip_path or not os.path.isfile(zip_path):
    print("FATAL: 検査対象のZIPが見つかりません:", RELEASE)
    sys.exit(1)

print("=== ZIP再展開検査 ===")
print("対象ZIP :", os.path.relpath(zip_path, FLOW_DIR).replace(os.sep, "/"))

# --- 1〜3. ZIPを開いてエントリを確認 ---
with zipfile.ZipFile(zip_path) as z:
    bad = z.testzip()
    if bad:
        errors.append("ZIPが破損している（最初の不正エントリ: %s）" % bad)
    names = z.namelist()
    for n in names:
        if any(s in n for s in FORBIDDEN_SUBSTR):
            errors.append("混入してはいけないエントリ: %s" % n)
        if n.endswith("/"):
            errors.append("ディレクトリエントリが含まれている: %s" % n)
    if os.path.isdir(EXTRACT_TO):
        shutil.rmtree(EXTRACT_TO, ignore_errors=True)
    os.makedirs(EXTRACT_TO, exist_ok=True)
    z.extractall(EXTRACT_TO)

print("エントリ数:", len(names))
for n in sorted(names):
    print("   ", n)

missing_top = EXPECTED_TOP - set(names)
if missing_top:
    errors.append("ZIPルート直下に必須ファイルが無い（余分な親フォルダの疑い）: %s" % sorted(missing_top))

# --- 4. 全JSONのパース ---
json_files = []
for root, _, fs in os.walk(EXTRACT_TO):
    for f in fs:
        p = os.path.join(root, f)
        rel = os.path.relpath(p, EXTRACT_TO).replace(os.sep, "/")
        if f.lower().endswith(".json"):
            json_files.append((rel, p))
        else:
            errors.append("JSON以外のファイルが含まれている（レガシーパッケージはJSONのみ）: %s" % rel)

parsed = {}
for rel, p in json_files:
    try:
        with open(p, encoding="utf-8") as f:
            parsed[rel] = json.load(f)
    except Exception as e:                                   # noqa: BLE001
        errors.append("JSON構文エラー %s: %s" % (rel, e))

if len(json_files) != 5:
    errors.append("パッケージ内JSONが5ファイルでない: %d件" % len(json_files))

# --- 5〜7. GUID整合 ---
root_manifest = parsed.get("manifest.json", {})
flows_manifest = parsed.get("Microsoft.Flow/flows/manifest.json", {})
asset_paths = flows_manifest.get("flowAssets", {}).get("assetPaths", [])
root_flow_guids = [k for k, v in root_manifest.get("resources", {}).items()
                   if v.get("hierarchy") == "Root"]
flows_dir = os.path.join(EXTRACT_TO, "Microsoft.Flow", "flows")
folder_guids = sorted(d for d in os.listdir(flows_dir)
                      if os.path.isdir(os.path.join(flows_dir, d))) if os.path.isdir(flows_dir) else []

if not (sorted(asset_paths) == sorted(root_flow_guids) == folder_guids):
    errors.append("パッケージGUIDの3点不一致: rootManifest(Root)=%s / フォルダ=%s / assetPaths=%s"
                  % (sorted(root_flow_guids), folder_guids, sorted(asset_paths)))
else:
    notes.append("パッケージGUID 3点一致: %s" % folder_guids[0])

if folder_guids:
    guid = folder_guids[0]
    defn = parsed.get("Microsoft.Flow/flows/%s/definition.json" % guid, {})
    apis_map = parsed.get("Microsoft.Flow/flows/%s/apisMap.json" % guid, {})
    conns_map = parsed.get("Microsoft.Flow/flows/%s/connectionsMap.json" % guid, {})
    res = root_manifest.get("resources", {})
    dep = set(res.get(guid, {}).get("dependsOn", []))
    for label, m in (("apisMap", apis_map), ("connectionsMap", conns_map)):
        for logical, g in m.items():
            if g not in res:
                errors.append("%s の %s -> %s が rootManifest.resources に無い" % (label, logical, g))
            if g not in dep:
                errors.append("%s の %s -> %s が dependsOn に無い" % (label, logical, g))
    conn_refs = set(defn.get("properties", {}).get("connectionReferences", {}).keys())
    if conn_refs != set(apis_map.keys()) or conn_refs != set(conns_map.keys()):
        errors.append("connectionReferences と apisMap/connectionsMap のキー不一致: %s / %s / %s"
                      % (sorted(conn_refs), sorted(apis_map), sorted(conns_map)))
    else:
        notes.append("接続参照キー一致: %s" % sorted(conn_refs))
    if len(dep) != 6:
        errors.append("dependsOn が API3＋接続3＝6件でない: %d件" % len(dep))

    # --- 9. 中身の実在確認（ZIPから展開した定義に対して行う） ---
    props = defn.get("properties", {})
    d = props.get("definition", {})
    trig = d.get("triggers", {}).get("manual", {})
    schema = trig.get("inputs", {}).get("schema", {})
    tprops = schema.get("properties", {})
    treq = schema.get("required", [])
    if trig.get("kind") != "Button":
        errors.append("手動（Button）トリガーが存在しない")
    for key in ("SharePointUrl", "ListName", "SharedMailboxAddress", "MailCount"):
        if key not in tprops:
            errors.append("トリガー入力 %s が存在しない" % key)
        if key not in treq:
            errors.append("%s が required でない" % key)
    if tprops.get("MailCount", {}).get("type") != "integer":
        errors.append("MailCount が integer 型でない")

    raw_def = json.dumps(defn, ensure_ascii=False)
    for cn, label in (("shared_sharepointonline", "SharePoint"),
                      ("shared_office365", "Office 365 Outlook"),
                      ("shared_conversionservice", "Content Conversion")):
        if ('"connectionName": "%s"' % cn) not in raw_def:
            errors.append("%s コネクタのアクションが存在しない" % label)
    for opid in ("HttpRequest", "GetEmailsV3", "HtmlToText"):
        if ('"operationId": "%s"' % opid) not in raw_def:
            errors.append("operationId %s のアクションが存在しない" % opid)
    for f in FIELD_ORDER:
        if ("AddViewField(''%s'')" % f) not in raw_def:
            errors.append("既定ビューへの %s 追加が存在しない" % f)
    if "createFieldAsXml" not in raw_def:
        errors.append("列作成（createFieldAsXml）が存在しない")
    if "removeAllViewFields()" not in raw_def:
        errors.append("既定ビュー列の全削除が存在しない")
    if "ReceivedDateTime" not in raw_def or "Ascending='FALSE'" not in raw_def:
        errors.append("既定ビューの日時降順（ViewQuery）が存在しない")
    else:
        notes.append("既定ビューは ReceivedDateTime の降順")
    if 'EnforceUniqueValues=\\"TRUE\\"' not in raw_def and 'EnforceUniqueValues="TRUE"' not in raw_def:
        errors.append("MessageId の一意制約（EnforceUniqueValues）が存在しない")
    else:
        notes.append("MessageId は一意制約＋インデックス付き")
    if 'RichText=\\"FALSE\\"' not in raw_def and 'RichText="FALSE"' not in raw_def:
        errors.append("BodyPlainText の RichText=\"FALSE\" が無い（HTMLをそのまま保存しない）")

    # --- 9b. 安全要件（ZIP側でも再確認する） ---
    if "GetByTitle(" in raw_def:
        errors.append("安全違反: 展開した定義に GetByTitle( が存在する")
    else:
        notes.append("GetByTitle( の出現 0 件（対象はリストIDでのみ特定）")
    destructive = [t for t in ("deleteObject(", "/recycle(", "recycleItem(",
                               '"X-HTTP-Method": "DELETE"') if t in raw_def]
    if destructive:
        errors.append("安全違反: 破壊的RESTが存在する: %s" % destructive)
    else:
        notes.append("破壊的REST（削除・ごみ箱）の出現 0 件")
    mail_mod = [op for op in ("MarkAsRead", "Move", "Delete", "Flag", "SendEmail", "Forward")
                if ('"operationId": "%s' % op) in raw_def]
    if mail_mod:
        errors.append("安全違反: メールを変更する操作が存在する: %s" % mail_mod)
    else:
        notes.append("メール変更操作（既読化・移動・削除・送信）の出現 0 件")
    for marker, label in (
            ("Scope_Validate_Input", "入力検証スコープ"),
            ("Scope_Check_List", "同名リスト確認スコープ"),
            ("Scope_Create_List", "リスト作成スコープ"),
            ("Scope_Verify_Schema", "スキーマ確認スコープ"),
            ("Scope_Get_Emails", "メール取得スコープ"),
            ("Scope_Sync_Items", "同期スコープ"),
            ("varCreatedInThisRun", "初期化ガード変数"),
            ("Recheck_Lists_Before_Create", "作成直前の再確認"),
            ("ERR_COUNT_TOO_LARGE", "取得件数の上限チェック")):
        if marker not in raw_def:
            errors.append("%s（%s）が定義に存在しない" % (marker, label))
    # 実テナント名を含むサイトURL・メールアドレスの埋め込みを検出する。
    # プレースホルダ（https://{tenant}.sharepoint.com）は '{' を含むため一致しない。
    leaked = re.findall(r"https://[A-Za-z0-9\-]+\.sharepoint\.com", raw_def)
    if leaked:
        errors.append("安全違反: サイトURLの実値が定義に埋め込まれている: %s" % sorted(set(leaked))[:3])
    else:
        notes.append("サイトURLの実値埋め込み 0 件（実行時にURLから解決）")
    mails = [m for m in re.findall(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}", raw_def)
             if "{tenant}" not in m]
    if mails:
        errors.append("安全違反: メールアドレスの実値が埋め込まれている: %s" % sorted(set(mails))[:3])
    else:
        notes.append("メールアドレスの実値埋め込み 0 件（実行時に入力から取得）")

    notes.append("displayName: %s" % props.get("displayName"))

# --- 8. source/package との一致 ---
if os.path.isdir(SOURCE_PKG):
    src_files = {}
    for root, _, fs in os.walk(SOURCE_PKG):
        for f in fs:
            p = os.path.join(root, f)
            src_files[os.path.relpath(p, SOURCE_PKG).replace(os.sep, "/")] = p
    ext_files = {rel: p for rel, p in json_files}
    only_src = set(src_files) - set(ext_files)
    only_ext = set(ext_files) - set(src_files)
    if only_src:
        errors.append("ZIPに含まれていない source/package のファイル: %s" % sorted(only_src))
    if only_ext:
        errors.append("source/package に無いファイルがZIPに含まれる: %s" % sorted(only_ext))
    for rel in sorted(set(src_files) & set(ext_files)):
        if sha256(src_files[rel]) != sha256(ext_files[rel]):
            errors.append("ZIP化で内容が変化している: %s" % rel)
    if not only_src and not only_ext and not any("内容が変化" in e for e in errors):
        notes.append("展開結果は source/package とバイト単位で一致")
else:
    errors.append("source/package が存在しない（先に build_sync_flow.py を実行すること）")

print()
for n in notes:
    print("  OK:", n)
print()
print("=== ERRORS ===")
for e in errors:
    print("  ", e)
print("(%d errors)" % len(errors))
print("展開先:", os.path.relpath(EXTRACT_TO, FLOW_DIR).replace(os.sep, "/"),
      "（検証用コピー。正典は source/package）")

sys.exit(1 if errors else 0)
