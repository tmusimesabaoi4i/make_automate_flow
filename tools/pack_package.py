# -*- coding: utf-8 -*-
"""展開形Power AutomateパッケージをインポートZIP化する汎用スクリプト。

使い方:
    python pack_package.py <package_dir> <output.zip>

- <package_dir> 直下の manifest.json / Microsoft.Flow/... をZIPのルートに配置する
  （余分な親フォルダを作らない。レガシーパッケージのインポート要件）
- エントリはパス順で追加（再現性のため）
- 作成後にZIPを開き直し、破損チェックとエントリ数を報告する
"""
import os, sys, zipfile

if len(sys.argv) != 3:
    print("usage: python pack_package.py <package_dir> <output.zip>")
    sys.exit(1)

src, out = sys.argv[1], sys.argv[2]
if not os.path.isfile(os.path.join(src, "manifest.json")):
    print("error: manifest.json が見つかりません（package_dir 直下を指定してください）:", src)
    sys.exit(1)

files = []
for root, _, fs in os.walk(src):
    for f in fs:
        full = os.path.join(root, f)
        files.append((full, os.path.relpath(full, src).replace(os.sep, "/")))
files.sort(key=lambda x: x[1])

os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
if os.path.exists(out):
    os.remove(out)
with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
    for full, rel in files:
        z.write(full, rel)

with zipfile.ZipFile(out) as z:
    bad = z.testzip()
    names = z.namelist()
print("created:", out)
print("entries:", len(names), "/ corrupt:", bad or "none")
