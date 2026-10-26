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
     （rootManifest.resources の Root キー ＝ Microsoft.Flow/flows のフォルダ名
       ＝ Microsoft.Flow/flows/manifest.json の flowAssets.assetPaths）
  6. apisMap / connectionsMap の値が rootManifest.resources と dependsOn に実在する
  7. definition.json の connectionReferences のキーが apisMap/connectionsMap と一致する
  8. 展開結果が source/package/ の内容とバイト単位で一致する（ZIP化で壊れていない）
  9. トリガー・Teamsアクションの実在（フロー名 / TeamsPostUrl / HttpRequest）

展開先は ./extracted/ （検証用の一時コピー。source/package が正典）。
終了コード: エラーがあれば 1、無ければ 0。
"""
import hashlib, json, os, shutil, sys, zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
FLOW_DIR = os.path.dirname(HERE)
RELEASE = os.path.join(FLOW_DIR, "release")
SOURCE_PKG = os.path.join(FLOW_DIR, "source", "package")
EXTRACT_TO = os.path.join(HERE, "extracted")

errors = []
notes = []

EXPECTED_TOP = {"manifest.json", "Microsoft.Flow/flows/manifest.json"}
FORBIDDEN_SUBSTR = ("__MACOSX", ".DS_Store", "Thumbs.db")


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

    # --- 9. 中身の実在確認 ---
    props = defn.get("properties", {})
    d = props.get("definition", {})
    trig = d.get("triggers", {}).get("manual", {})
    tprops = trig.get("inputs", {}).get("schema", {}).get("properties", {})
    if trig.get("kind") != "Button":
        errors.append("手動（Button）トリガーが存在しない")
    if "TeamsPostUrl" not in tprops:
        errors.append("トリガー入力 TeamsPostUrl が存在しない")
    if "TeamsPostUrl" not in trig.get("inputs", {}).get("schema", {}).get("required", []):
        errors.append("TeamsPostUrl が required でない")
    raw_def = json.dumps(defn, ensure_ascii=False)
    if '"connectionName": "shared_teams"' not in raw_def:
        errors.append("Teamsコネクタのアクションが存在しない")
    if '"operationId": "HttpRequest"' not in raw_def:
        errors.append("Teams HttpRequest アクションが存在しない")
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
    errors.append("source/package が存在しない（先に build_*.py を実行すること）")

print()
for n in notes:
    print("  OK:", n)
print()
print("=== ERRORS ===")
for e in errors:
    print("  ", e)
print("(%d errors)" % len(errors))
print("展開先:", os.path.relpath(EXTRACT_TO, FLOW_DIR).replace(os.sep, "/"), "（検証用コピー。正典は source/package）")

sys.exit(1 if errors else 0)
