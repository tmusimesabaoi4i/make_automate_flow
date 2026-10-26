# -*- coding: utf-8 -*-
"""
リリースZIPを再展開して、source/package と1バイトも違わないことを確かめる（両フロー共通）。

ZIP を作った後に「実際に配るもの」を検査する。ビルド結果を信じるのではなく、
配布物そのものを開いて確かめる（handbook/knowledge/lessons_learned.md §23）。

  検査1 ZIPが壊れていない
  検査2 ルート直下が5ファイル構造で、余分なエントリ（__MACOSX / .DS_Store / ディレクトリ）が無い
  検査3 すべてのJSONがパースできる
  検査4 GUID3点一致（assetPaths / rootリソースキー / フォルダ名）
  検査5 apisMap / connectionsMap の値が manifest.resources に実在する
  検査6 connectionReferences のキーが apisMap / connectionsMap と一致する
  検査7 展開結果が source/package と SHA-256 で完全一致する
"""
import hashlib
import json
import os
import zipfile

EXPECTED_ENTRIES = {
    "manifest.json",
    "Microsoft.Flow/flows/manifest.json",
}
FLOW_FILES = {"definition.json", "apisMap.json", "connectionsMap.json"}


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def latest_zip(release_dir):
    if not os.path.isdir(release_dir):
        return None
    zips = sorted([os.path.join(release_dir, f) for f in os.listdir(release_dir)
                   if f.lower().endswith(".zip")])
    return zips[-1] if zips else None


def check(zip_path, package_dir):
    """(errors, info) を返す"""
    errors = []
    info = {"zip": os.path.basename(zip_path)}

    with zipfile.ZipFile(zip_path) as z:
        bad = z.testzip()
        if bad is not None:
            errors.append("E1 ZIPが壊れている: %s" % bad)
            return errors, info
        names = z.namelist()
        info["entries"] = len(names)

        for n in names:
            if n.startswith("__MACOSX") or n.endswith(".DS_Store"):
                errors.append("E2 余分なエントリが混入している: %s" % n)
            if n.endswith("/"):
                errors.append("E2 ディレクトリエントリが混入している: %s" % n)

        flow_dirs = sorted({n.split("/")[2] for n in names
                            if n.startswith("Microsoft.Flow/flows/") and n.count("/") == 3})
        if len(flow_dirs) != 1:
            errors.append("E2 フローフォルダが1つでない: %s" % flow_dirs)
            return errors, info
        pkg = flow_dirs[0]
        info["packageGuid"] = pkg

        expected = set(EXPECTED_ENTRIES) | {"Microsoft.Flow/flows/%s/%s" % (pkg, f)
                                            for f in FLOW_FILES}
        if set(names) != expected:
            errors.append("E2 5ファイル構造と違う。実際=%s" % sorted(names))

        docs = {}
        for n in names:
            try:
                docs[n] = json.loads(z.read(n).decode("utf-8"))
            except Exception as e:  # noqa: BLE001
                errors.append("E3 JSONとして読めない %s: %s" % (n, e))
        if errors:
            return errors, info

        root_manifest = docs["manifest.json"]
        flows_manifest = docs["Microsoft.Flow/flows/manifest.json"]
        definition_doc = docs["Microsoft.Flow/flows/%s/definition.json" % pkg]
        apis_map = docs["Microsoft.Flow/flows/%s/apisMap.json" % pkg]
        conns_map = docs["Microsoft.Flow/flows/%s/connectionsMap.json" % pkg]

        asset_paths = sorted(flows_manifest.get("flowAssets", {}).get("assetPaths", []))
        resources = root_manifest.get("resources", {})
        root_guids = sorted([k for k, v in resources.items() if v.get("hierarchy") == "Root"])
        if not (asset_paths == root_guids == [pkg]):
            errors.append("E4 GUID3点不一致: assetPaths=%s root=%s folder=%s"
                          % (asset_paths, root_guids, pkg))

        for label, m in (("apisMap", apis_map), ("connectionsMap", conns_map)):
            for k, guid in m.items():
                if guid not in resources:
                    errors.append("E5 %s の %s=%s が manifest.resources に無い" % (label, k, guid))

        ref_keys = sorted((definition_doc.get("properties", {})
                           .get("connectionReferences") or {}).keys())
        if ref_keys != sorted(apis_map.keys()) or ref_keys != sorted(conns_map.keys()):
            errors.append("E6 connectionReferences と apisMap/connectionsMap のキーが不一致: "
                          "refs=%s apis=%s conns=%s"
                          % (ref_keys, sorted(apis_map.keys()), sorted(conns_map.keys())))
        info["connectionReferences"] = ref_keys
        info["displayName"] = definition_doc.get("properties", {}).get("displayName")

        # 検査7 バイト一致
        for n in sorted(names):
            src = os.path.join(package_dir, *n.split("/"))
            if not os.path.isfile(src):
                errors.append("E7 source/package に対応ファイルが無い: %s" % n)
                continue
            if _sha256(src) != _sha256_bytes(z.read(n)):
                errors.append("E7 ZIP内容が source/package と一致しない: %s" % n)
    return errors, info


def run(release_dir, package_dir, out_path, zip_path=None, title=""):
    zip_path = zip_path or latest_zip(release_dir)
    if zip_path is None:
        text = "=== %s ZIP再展開検査 ===\n  release/ にZIPがありません。" % title
        print(text)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(text + "\n")
        return 1

    errors, info = check(zip_path, package_dir)
    lines = ["=== %s ZIP再展開検査 ===" % title]
    for k, v in info.items():
        lines.append("%-22s: %s" % (k, v))
    lines.append("")
    lines.append("=== ERRORS ===")
    lines += ["  " + e for e in errors] if errors else ["  (0 errors)"]
    text = "\n".join(lines)
    print(text)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(text + "\n")
    return 1 if errors else 0
